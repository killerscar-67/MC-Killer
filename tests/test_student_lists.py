import html
import io
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch
from mcmark.student_lists import student,parse_import,parse_grid,validate_students,export_list
from mcmark.web import create_app,connect,process_job


class StudentListTests(unittest.TestCase):
    def test_grid_updates_keep_references_and_omitted_rows(self):
        old=[student({'class':'5A','number':'01','name':'Example'}),student({'class':'5A','number':'2','name':'Kept'})]
        payload=[{'record_id':old[0]['record_id'],'class':'5B','number':'03','english_name':'Updated','chinese_name':'測試','active':'false'},
                 {'class':'5A','number':'04','english_name':'New','chinese_name':'新生'}, {'class':'','number':'','active':'true'}]
        rows,changes=parse_grid(json.dumps(payload),old)
        self.assertEqual(len(rows),3);self.assertEqual(len(changes),2)
        updated=next(r for r in rows if r['record_id']==old[0]['record_id'])
        self.assertEqual(updated['student_id'],'03');self.assertFalse(updated['active']);self.assertIn(old[1],rows)
        for bad in (None,{},[1],[{'class':5}],[{'record_id':'foreign'}],[payload[0],payload[0]],
                    [{'class':'5A','number':'2','name':'not an allowed key'}],
                    [{'class':'5A','number':'02','english_name':'Duplicate'}], [{}]*201):
            with self.assertRaises(ValueError):parse_grid(json.dumps(bad),old)
        with self.assertRaises(ValueError):parse_grid('not json',old)
        with self.assertRaises(ValueError):parse_grid('[]',old)

    def test_stable_import_and_explicit_withdrawal(self):
        rows,_=parse_import('class,number,english_name,chinese_name\n5A,01,Example,測試\n'.encode(),'students.csv',[])
        rid=rows[0]['record_id'];self.assertEqual(rows[0]['student_id'],'01')
        update=export_list(rows).decode('utf-8-sig').replace(',5A,01,',',5B,02,').replace(',true',',false').encode()
        changed,_=parse_import(update,'students.csv',rows)
        self.assertEqual(changed[0]['record_id'],rid);self.assertEqual(changed[0]['class'],'5B');self.assertFalse(changed[0]['active'])
        self.assertEqual(changed[0]['chinese_name'],'測試')
        for content in (b'class,number,name\n5A,1,Other',b'record_id,class,number,name\nforeign,5A,1,Other'):
            with self.assertRaises(ValueError):parse_import(content,'update.csv',rows)
        one=student({'class':'5A','number':'1','name':'One'});two=student({'class':'5A','number':'01','name':'Two'})
        with self.assertRaises(ValueError):validate_students([one,two])
        two['active']=False;self.assertEqual(len(validate_students([one,two])),2)

    def test_xlsx_and_formula_safe_export(self):
        from openpyxl import Workbook
        book=Workbook();book.active.append(['class','number','english_name']);book.active.append(['5A',1,'=Not a formula to execute'])
        out=io.BytesIO();book.save(out);rows,_=parse_import(out.getvalue(),'students.xlsx',[])
        self.assertEqual(rows[0]['student_id'],'1');self.assertIn("'=Not a formula",export_list(rows).decode('utf-8-sig'))


class SavedRosterWebTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.data=Path(self.tmp.name);self.app=create_app(self.data,testing=True,start_worker=False)
        with connect(self.data) as db:
            for user in ('list-owner','other-owner'):db.execute('INSERT INTO users(id,email,password) VALUES(?,?,?)',(user,user+'@example.test',''))
        self.client=self.app.test_client()
        with self.client.session_transaction() as s:s.update(user='list-owner',email='teacher@example.test',csrf='token',auth_method='password')
        response=self.client.post('/rosters',data={'csrf':'token','title':'Form 5','school_year':'2026-2027'});self.rid=response.headers['Location'].rsplit('/',1)[-1]

    def tearDown(self):self.tmp.cleanup()

    def roster(self):
        with connect(self.data) as db:return dict(db.execute('SELECT * FROM rosters WHERE id=?',(self.rid,)).fetchone())

    def add(self,number='1'):
        return self.client.post('/rosters/'+self.rid,data={'csrf':'token','version':str(self.roster()['version']),'action':'add','class':'5A','number':number,'english_name':'Student '+number,'chinese_name':'測試','active':'true'})

    def edit_student(self,record,**changes):
        return self.client.post('/rosters/'+self.rid,data={'csrf':'token','version':str(self.roster()['version']),'action':'edit','record_id':record['record_id'],'class':record['class'],'number':record['student_id'],'english_name':record['english_name'],'chinese_name':record['chinese_name'],'active':'true',**changes})

    def job(self,jid):
        with connect(self.data) as db:return dict(db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone())

    def assessment(self):
        from PIL import Image
        image=io.BytesIO();Image.new('RGB',(600,800),'white').save(image,format='PNG');image.seek(0)
        preview=self.client.post('/roster/preview',data={'csrf':'token','roster_id':self.rid}).json
        response=self.client.post('/assessments/new',data={'csrf':'token','title':'Roster test','count':'1','key':'A','identity_mode':'roster','roster_id':self.rid,'roster_version':str(preview['version']),'roster_digest':preview['digest'],'roster_order_confirmed':'yes','scans':(image,'scan.png')})
        self.assertEqual(response.status_code,302);return response.headers['Location'].rsplit('/',1)[-1]

    def ready(self,jid):
        from mcmark.core import grade
        job=self.job(jid);config=json.loads(job['config']);r=config['roster'][0]
        row={'file':'scan.png','page':1,'name':r['name'],'class':r['class'],'student_id':r['student_id'],'student_record_id':r['record_id'],'identity_source':'roster_order','metadata_details':{},'sheet_review_issues':[],'review_required':False,**grade([{'selected':['A'],'review_reasons':[]}],config)}
        with connect(self.data) as db:db.execute("UPDATE jobs SET state='ready',results=? WHERE id=?",(json.dumps([row]),jid))
        return self.job(jid)

    def test_edit_withdrawal_history_snapshot_stale_and_ownership(self):
        self.assertEqual(self.add().status_code,302);record=json.loads(self.roster()['students'])[0];jid=self.assessment();before=self.job(jid)['config'];old_version=self.roster()['version']
        self.assertEqual(self.edit_student(record,**{'class':'5B','number':'9','english_name':'Changed','active':'false'}).status_code,302)
        self.assertEqual(json.loads(self.roster()['students'])[0]['record_id'],record['record_id']);self.assertEqual(self.job(jid)['config'],before)
        self.assertEqual(self.client.post('/rosters/'+self.rid,data={'csrf':'token','version':str(old_version),'action':'add'}).status_code,409)
        self.assertEqual(self.client.post('/rosters/'+self.rid,data={}).status_code,400)
        self.assertEqual(self.client.get('/assessments/new?roster='+self.rid).status_code,200)
        with self.client.session_transaction() as s:s['user']='other-owner'
        for path in ('/rosters/'+self.rid,'/rosters/'+self.rid+'/export','/assessments/'+jid+'/candidates'):
            self.assertEqual(self.client.get(path).status_code,404)
        self.assertEqual(self.client.post('/roster/preview',data={'csrf':'token','roster_id':self.rid}).status_code,404)
        with connect(self.data) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM roster_audit WHERE roster=?',(self.rid,)).fetchone()[0],3)

    def test_bulk_preview_is_not_save_and_confirmation_requires_fresh_version(self):
        response=self.client.post('/rosters/'+self.rid,data={'csrf':'token','version':'1','action':'import','file':(io.BytesIO(b'class,number,name\n5A,1,Test'),'students.csv')})
        self.assertEqual(response.status_code,200);self.assertEqual(json.loads(self.roster()['students']),[])
        proposal=html.unescape(re.search(r'name="proposal" value="([^"]+)"',response.data.decode()).group(1))
        self.assertEqual(self.client.post('/rosters/'+self.rid,data={'csrf':'token','version':'1','action':'confirm_import','proposal':proposal}).status_code,302)
        self.assertEqual(len(json.loads(self.roster()['students'])),1)
        self.assertEqual(self.client.post('/rosters/'+self.rid,data={'csrf':'token','version':'1','action':'confirm_import','proposal':proposal}).status_code,409)

    def test_paste_preview_confirmation_error_recovery_and_security(self):
        url='/rosters/'+self.rid
        payload=[{'class':'5A','number':'01','english_name':'Example','chinese_name':'測試'}]
        data={'csrf':'token','version':'1','action':'paste','grid':json.dumps(payload)}
        response=self.client.post(url,data=data)
        self.assertEqual(response.status_code,200);self.assertEqual(json.loads(self.roster()['students']),[])
        proposal=html.unescape(re.search(r'name="proposal" value="([^"]+)"',response.data.decode()).group(1))
        self.assertEqual(self.client.post(url,data={**data,'action':'confirm_import','proposal':proposal}).status_code,302)
        saved=json.loads(self.roster()['students'])[0];self.assertEqual(saved['student_id'],'01')
        self.assertEqual(self.client.post(url,data=data).status_code,409)
        invalid={'class':'bad','number':'2','english_name':'<script>not executable</script>'}
        response=self.client.post(url,data={**data,'version':'2','grid':json.dumps([invalid])})
        self.assertEqual(response.status_code,400);self.assertIn(b'Use a class',response.data)
        self.assertNotIn(b'<script>not executable',response.data);self.assertIn(b'roster-grid-initial',response.data)
        self.assertEqual(len(json.loads(self.roster()['students'])),1)
        self.assertEqual(self.client.post(url,data={**data,'csrf':''}).status_code,400)
        with self.client.session_transaction() as s:s['user']='other-owner'
        self.assertEqual(self.client.post(url,data={**data,'version':'2'}).status_code,404)

    def test_explicit_candidate_update_preserves_submitted_identity_and_finalization_gate(self):
        self.add();jid=self.assessment();ready=self.ready(jid);record=json.loads(self.roster()['students'])[0]
        self.edit_student(record,english_name='Changed name');self.add('2');current=json.loads(self.roster()['students'])
        response=self.client.post(f'/assessments/{jid}/candidates',data={'csrf':'token','version':str(ready['updated']),'roster_version':str(self.roster()['version']),'candidate':[r['record_id'] for r in current]})
        self.assertEqual(response.status_code,302);job=self.job(jid);config=json.loads(job['config'])
        self.assertEqual(config['roster'][0]['name'],'Student 1');self.assertEqual(len(config['roster']),2)
        self.assertEqual(self.client.post(f'/assessments/{jid}/finalize',data={'csrf':'token'}).status_code,409)
        export=self.client.get(f'/assessments/{jid}/export/submissions');self.assertIn(b'Not submitted',export.data)
        self.assertEqual(self.client.get(f'/assessments/{jid}/candidates').status_code,200)
        self.assertEqual(self.client.post(f'/assessments/{jid}/candidates',data={'csrf':'token','version':str(job['updated']),'roster_version':str(self.roster()['version']),'candidate':[record['record_id']]}).status_code,302)
        self.assertEqual(self.client.post(f'/assessments/{jid}/finalize',data={'csrf':'token'}).status_code,302)
        self.assertEqual(self.client.post(f'/assessments/{jid}/candidates',data={'csrf':'token','version':str(self.job(jid)['updated'])}).status_code,409)
        self.assertEqual(self.client.post(f'/assessments/{jid}/identities',data={'csrf':'token','version':str(self.job(jid)['updated'])}).status_code,409)

    def test_identity_reassignment_keeps_evidence_and_audit_stale_checks(self):
        self.add();jid=self.assessment();self.ready(jid);self.add('2');candidates=json.loads(self.roster()['students']);job=self.job(jid)
        self.client.post(f'/assessments/{jid}/candidates',data={'csrf':'token','version':str(job['updated']),'roster_version':str(self.roster()['version']),'candidate':[r['record_id'] for r in candidates]})
        job=self.job(jid);other=candidates[1]['record_id']
        self.assertEqual(self.client.get(f'/assessments/{jid}/identities').status_code,200)
        response=self.client.post(f'/assessments/{jid}/identities',data={'csrf':'token','version':str(job['updated']),'student_0':other})
        self.assertEqual(response.status_code,302);row=json.loads(self.job(jid)['results'])[0]
        self.assertEqual(row['name'],'Student 2');self.assertEqual(row['identity_source'],'teacher_roster');self.assertEqual(row['original_identity']['name'],'Student 1')
        self.assertEqual(self.client.post(f'/assessments/{jid}/identities',data={'csrf':'token','version':str(job['updated']),'student_0':other}).status_code,409)
        job=self.job(jid)
        self.assertEqual(self.client.post(f'/assessments/{jid}/identities',data={'csrf':'token','version':str(job['updated']),'student_0':'foreign-record'}).status_code,400)

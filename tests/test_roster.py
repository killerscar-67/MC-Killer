import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mcmark.roster import parse_roster, roster_digest, with_absences, assign_roster, submission_csv
from mcmark.web import create_app, connect, process_job


CSV='class,number,name\n3a,03,Third Student\n3A,01,\u6e2c\u8a66\n3A,02,Absent Student\n'.encode('utf-8-sig')


class RosterTests(unittest.TestCase):
    def test_csv_sorts_numbers_preserves_names_and_rejects_ambiguous_lists(self):
        rows=parse_roster(CSV)
        self.assertEqual([r['student_id'] for r in rows],['01','02','03'])
        self.assertEqual(rows[0]['name'],'\u6e2c\u8a66')
        for content in (b'',b'class,number,name\n3A,1,A\n3A,01,B',
                        b'class,number,name\n3A,1,A\n3B,2,B',
                        b'class,number,name\n3A,O1,A',b'name\nOnly Name'):
            with self.assertRaises(ValueError): parse_roster(content)

    def test_absences_assignments_count_gate_and_csv_export(self):
        rows=with_absences(parse_roster(CSV),['02'])
        config={'identity_mode':'roster','roster':rows,'assessment_subject':'Math'}
        results=[{},{}];assign_roster(results,config)
        self.assertEqual([r['student_id'] for r in results],['01','03'])
        self.assertEqual(results[0]['identity_source'],'roster_order')
        with self.assertRaises(ValueError): assign_roster([{}],config)
        with self.assertRaises(ValueError): with_absences(parse_roster(CSV),['99'])
        with self.assertRaises(ValueError): with_absences(parse_roster(CSV),['01','02','03'])
        export=submission_csv(config,results).decode('utf-8-sig')
        self.assertIn('Absent,Not expected',export)
        self.assertIn('Present,Submitted,2',export)

    def test_pipeline_never_calls_ocr_and_keeps_all_written_images(self):
        import cv2
        from mcmark.cli import run
        root=Path(__file__).resolve().parents[1]
        config=json.loads((root/'mcmark/layouts/delia-layout.json').read_text())
        config.update(identity_mode='roster',roster=with_absences(parse_roster(CSV),['02']),
                      assessment_subject='Math',template_image=str(root/'mcmark/layouts/delia-template.png'))
        config['questions']=[{**config['questions'][0],'answer':'A'}]
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp);source=directory/'input';source.mkdir()
            image=cv2.imread(config['template_image'],0)
            for name in ('001.png','002.png'): cv2.imwrite(str(source/name),image)
            with patch('mcmark.ocr.recognize',side_effect=AssertionError('Roster mode must not run OCR')) as ocr:
                self.assertEqual(run([source],config,directory/'output'),0)
            ocr.assert_not_called()
            results=json.loads((directory/'output/results.json').read_text(encoding='utf-8'))
            self.assertEqual([r['student_id'] for r in results],['01','03'])
            self.assertEqual([Path(r['file']).name for r in results],['001.png','002.png'])
            for row in results:
                self.assertFalse(any(s.startswith('metadata_') for s in row['sheet_review_issues']))
                self.assertEqual(len(row['metadata_details']),5)
                self.assertTrue(all(Path(d['crop']).is_file() for d in row['metadata_details'].values()))
                self.assertTrue(all(d['status']=='image_only' for d in row['metadata_details'].values()))


class RosterWebTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.data=Path(self.tmp.name)
        self.app=create_app(self.data,testing=True,start_worker=False)
        with connect(self.data) as db:
            for user in ('alice','bob'):
                db.execute('INSERT INTO users(id,email,password) VALUES(?,?,?)',(user,user+'@school.test','unused'))
        self.client=self.app.test_client()
        with self.client.session_transaction() as session:
            session.update(user='alice',email='alice@school.test',csrf='token',auth_method='password')

    def tearDown(self): self.tmp.cleanup()

    def form(self,**changes):
        from PIL import Image
        image=io.BytesIO();Image.new('RGB',(600,800),'white').save(image,format='PNG');image.seek(0)
        roster=parse_roster(CSV)
        return {'csrf':'token','title':'Roster exam','count':'1','key':'A','wrong':'0','pass':'50','subject':'Math',
                'identity_mode':'roster','roster_digest':roster_digest(roster),'roster_order_confirmed':'yes',
                'absent':['02','03'],'roster':(io.BytesIO(CSV),'class.csv'),'scans':(image,'scan.png'),**changes}

    def test_preview_is_private_csrf_protected_and_unicode_safe(self):
        self.assertIn(b'Class list &amp; absences',self.client.get('/assessments/new').data)
        response=self.client.post('/roster/preview',data={'csrf':'token','roster':(io.BytesIO(CSV),'class.csv')})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json['students'][0]['name'],'\u6e2c\u8a66')
        self.assertEqual(response.headers['Cache-Control'],'no-store')
        self.assertEqual(self.client.post('/roster/preview',data={}).status_code,400)
        anonymous=self.app.test_client()
        with anonymous.session_transaction() as session: session['csrf']='valid-token'
        self.assertEqual(anonymous.post('/roster/preview',data={'csrf':'valid-token','roster':(io.BytesIO(CSV),'class.csv')}).status_code,302)

    def test_mismatched_count_or_unconfirmed_roster_never_queues(self):
        for changes in ({'absent':[]},{'roster_digest':'wrong'},{'roster_order_confirmed':''}):
            self.assertEqual(self.client.post('/assessments/new',data=self.form(**changes)).status_code,400)
        with connect(self.data) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0],0)

    def test_worker_assigns_roster_and_exports_private_submission_record(self):
        response=self.client.post('/assessments/new',data=self.form())
        self.assertEqual(response.status_code,302)
        jid=response.headers['Location'].rsplit('/',1)[-1]
        with connect(self.data) as db: job=dict(db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone())
        config=json.loads(job['config'])
        self.assertEqual(config['identity_mode'],'roster')
        def processing(inputs,config,output):
            from mcmark.core import grade
            output=Path(output);output.mkdir(parents=True)
            row={'file':'scan.png','page':1,'name':'','class':'','student_id':'','metadata_details':{},'sheet_review_issues':[],'review_required':False,
                 **grade([{'selected':['A'],'review_reasons':[]}],config)}
            (output/'results.json').write_text(json.dumps([row]),encoding='utf-8')
            return 0
        with patch('mcmark.cli.run',side_effect=processing): process_job(self.data,job)
        with connect(self.data) as db:
            saved=dict(db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone())
            actions=[r[0] for r in db.execute('SELECT action FROM audit WHERE job=?',(jid,)).fetchall()]
        self.assertEqual(saved['state'],'ready')
        self.assertEqual(json.loads(saved['results'])[0]['name'],'\u6e2c\u8a66')
        self.assertIn('roster_confirmed',actions);self.assertIn('roster_assigned',actions)
        page=self.client.get(f'/assessments/{jid}/sheets/0')
        self.assertNotIn(b'name="confirm_metadata"',page.data)
        self.assertIn(b'no OCR was run',page.data)
        export=self.client.get(f'/assessments/{jid}/export/submissions')
        self.assertEqual(export.status_code,200)
        self.assertIn('\u6e2c\u8a66'.encode('utf-8'),export.data)
        self.assertEqual(self.client.post(f'/assessments/{jid}/sheets/0/review',data={'csrf':'token','version':str(saved['updated']),'confirm_metadata':'yes'}).status_code,400)
        other=self.app.test_client()
        with other.session_transaction() as session: session.update(user='bob',email='bob@school.test',csrf='other',auth_method='password')
        self.assertEqual(other.get(f'/assessments/{jid}/export/submissions').status_code,404)
        self.assertEqual(other.get(f'/assessments/{jid}').status_code,404)
        self.assertEqual(self.client.post(f'/assessments/{jid}/finalize',data={'csrf':'token'}).status_code,302)
        self.assertEqual(self.client.post(f'/assessments/{jid}/review',data={'csrf':'token','version':str(saved['updated'])}).status_code,409)

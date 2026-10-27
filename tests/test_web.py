import io
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from werkzeug.security import generate_password_hash
from mcmark.web import create_app,connect,process_job
from mcmark.core import grade


class TeacherWebTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.data=Path(self.tmp.name)
        self.app=create_app(self.data,testing=True,start_worker=False)
        self.client=self.app.test_client()
        with connect(self.data) as db:
            db.execute('INSERT INTO users(id,email,password) VALUES(?,?,?)',('alice','alice@school.test',generate_password_hash('a-long-test-password',method='pbkdf2:sha256:1000')))
            db.execute('INSERT INTO users(id,email,password) VALUES(?,?,?)',('bob','bob@school.test',generate_password_hash('a-long-test-password',method='pbkdf2:sha256:1000')))
        self.client.get('/login')
        with self.client.session_transaction() as session: self.csrf=session['csrf']
        response=self.client.post('/login',data={'csrf':self.csrf,'email':'alice@school.test','password':'a-long-test-password'})
        self.assertEqual(response.status_code,302)
        with self.client.session_transaction() as session: self.csrf=session['csrf']

    def tearDown(self): self.tmp.cleanup()

    def upload(self):
        from PIL import Image
        image=io.BytesIO()
        Image.new('RGB',(600,800),'white').save(image,format='PNG')
        image.seek(0)
        response=self.client.post('/assessments/new',data={'csrf':self.csrf,'title':'S3 chapter test','subject':'Math','level':'S3','count':'2','key':'AB','wrong':'0','pass':'50','scans':(image,'scan.png')})
        self.assertEqual(response.status_code,302)
        return response.headers['Location'].rsplit('/',1)[-1]

    def ready(self,jid):
        with connect(self.data) as db:
            job=db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone()
            config=json.loads(job['config'])
            answers=[{'selected':['A'],'raw_selected':['A'],'review_reasons':[]},{'selected':['B','C'],'raw_selected':['B','C'],'review_reasons':['multiple']}]
            row={'file':'scan.png','page':1,'name':'Student','class':'3A','student_id':'01','subject_paper':'Math','signature':'','metadata_details':{},'sheet_review_issues':['metadata_unrecognized'],'review_required':True,'score_is_provisional':True,**grade(answers,config)}
            db.execute("UPDATE jobs SET state='ready',results=? WHERE id=?",(json.dumps([row]),jid))
        return row

    def test_pages_csrf_and_validation(self):
        self.assertEqual(self.client.get('/').status_code,200)
        self.assertEqual(self.client.get('/assessments/new').status_code,200)
        self.assertEqual(self.client.post('/assessments/new',data={}).status_code,400)
        bad=self.client.post('/assessments/new',data={'csrf':self.csrf,'count':'2','key':'AX'})
        self.assertEqual(bad.status_code,400)
        self.assertEqual(self.client.get('/assessments/does-not-exist').status_code,404)

    def test_teacher_isolation_for_pages_images_exports_and_edits(self):
        jid=self.upload();self.ready(jid)
        output=self.data/'batches'/jid/'output/review'
        output.mkdir(parents=True);(output/'image.png').write_bytes(b'test')
        other=self.app.test_client()
        with other.session_transaction() as session: session.update(user='bob',csrf='token')
        for path in [f'/assessments/{jid}',f'/assessments/{jid}/sheets/0',f'/assessments/{jid}/export/students',f'/assessments/{jid}/images/review/image.png']:
            self.assertEqual(other.get(path).status_code,404)
        self.assertEqual(other.post(f'/assessments/{jid}/sheets/0/review',data={'csrf':'token'}).status_code,404)
        self.assertEqual(self.client.get(f'/assessments/{jid}/images/../manifest.json').status_code,404)

    def test_review_regrades_identity_audit_exports_and_finalization(self):
        jid=self.upload();self.ready(jid)
        self.assertEqual(self.client.get(f'/assessments/{jid}').status_code,200)
        self.assertEqual(self.client.get(f'/assessments/{jid}/sheets/0').status_code,200)
        self.assertEqual(self.client.post(f'/assessments/{jid}/finalize',data={'csrf':self.csrf}).status_code,409)
        with connect(self.data) as db: version=str(db.execute('SELECT updated FROM jobs WHERE id=?',(jid,)).fetchone()[0])
        form={'csrf':self.csrf,'version':version,'q2':'B','confirm_metadata':'yes','name':'Corrected name','class':'3C','student_id':'40','signature':'Teacher checked image','subject_paper':'Math','note':'C crossed out'}
        self.assertEqual(self.client.post(f'/assessments/{jid}/sheets/0/review',data=form).status_code,302)
        self.assertEqual(self.client.post(f'/assessments/{jid}/sheets/0/review',data=form).status_code,409)
        with connect(self.data) as db:
            job=db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone()
            row=json.loads(job['results'])[0]
            self.assertEqual(row['score'],2)
            self.assertEqual(row['original_metadata']['class'],'3A')
            self.assertEqual(row['class'],'3C')
            self.assertFalse(row['review_required'])
            self.assertEqual(row['responses'][1]['raw_selected'],['B','C'])
            self.assertGreater(db.execute('SELECT COUNT(*) FROM audit WHERE job=?',(jid,)).fetchone()[0],1)
        download=self.client.get(f'/assessments/{jid}/export/students')
        self.assertEqual(download.status_code,200)
        self.assertIn(b'Corrected name',download.data)
        self.assertEqual(self.client.post(f'/assessments/{jid}/finalize',data={'csrf':self.csrf}).status_code,302)
        self.assertEqual(self.client.post(f'/assessments/{jid}/sheets/0/review',data=form).status_code,409)

    def test_bulk_blank_confirmation_leaves_uncertain_marks_pending(self):
        jid=self.upload();self.ready(jid)
        with connect(self.data) as db:
            job=db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone()
            rows=json.loads(job['results'])
            for a in rows[0]['responses']: a['selected']=[]
            rows[0]['responses'][0]['review_reasons']=['blank']
            rows[0]['responses'][1]['review_reasons']=['blank','faint_or_partial_mark']
            db.execute('UPDATE jobs SET results=? WHERE id=?',(json.dumps(rows),jid))
            version=str(job['updated'])
        response=self.client.post(f'/assessments/{jid}/sheets/0/review',data={
            'csrf':self.csrf,'version':version,'confirm_clean_blanks':'yes'})
        self.assertEqual(response.status_code,302)
        with connect(self.data) as db:
            row=json.loads(db.execute('SELECT results FROM jobs WHERE id=?',(jid,)).fetchone()[0])[0]
        self.assertEqual(row['responses'][0]['teacher_review']['decision'],[])
        self.assertNotIn('teacher_review',row['responses'][1])
        self.assertTrue(row['review_required'])

    def grouped_fixture(self):
        jid=self.upload();row=self.ready(jid)
        import copy
        second=copy.deepcopy(row);second['name']='Other student'
        with connect(self.data) as db:
            db.execute('UPDATE jobs SET results=? WHERE id=?',(json.dumps([row,second]),jid))
            version=str(db.execute('SELECT updated FROM jobs WHERE id=?',(jid,)).fetchone()[0])
        return jid,version

    def test_group_review_shows_pending_and_saves_multiple_students(self):
        jid,version=self.grouped_fixture()
        page=self.client.get(f'/assessments/{jid}/review')
        self.assertEqual(page.status_code,200)
        self.assertIn(b'Question 2',page.data)
        self.assertNotIn(b'<select',page.data)
        self.assertIn(b'type="radio" name="s0q2" value="B"',page.data)
        self.assertIn(b'type="radio" name="s0q2" value="B|C"',page.data)
        self.assertIn(b'question-review-list',page.data)
        self.assertIn(b'Other student',page.data)
        self.assertNotIn(b'name="s0q1"',page.data)
        form={'csrf':self.csrf,'version':version,'s0q2':'B','s1q2':'BLANK','note':'Compared row images'}
        self.assertEqual(self.client.post(f'/assessments/{jid}/review',data=form).status_code,302)
        with connect(self.data) as db:
            rows=json.loads(db.execute('SELECT results FROM jobs WHERE id=?',(jid,)).fetchone()[0])
            self.assertEqual(db.execute("SELECT COUNT(*) FROM audit WHERE job=? AND action='question_group_reviewed'",(jid,)).fetchone()[0],1)
        self.assertEqual(rows[0]['responses'][1]['selected'],['B'])
        self.assertEqual(rows[1]['responses'][1]['selected'],[])
        self.assertEqual(rows[0]['responses'][1]['raw_selected'],['B','C'])
        self.assertTrue(rows[0]['review_required']) # identity still unresolved
        self.assertEqual(rows[0]['score'],2)
        self.assertEqual(self.client.post(f'/assessments/{jid}/review',data=form).status_code,409)

    def test_group_review_invalid_batch_rolls_back_and_keeps_pending(self):
        jid,version=self.grouped_fixture()
        form={'csrf':self.csrf,'version':version,'s0q2':'B','s1q2':'Z'}
        self.assertEqual(self.client.post(f'/assessments/{jid}/review',data=form).status_code,400)
        with connect(self.data) as db:
            row=json.loads(db.execute('SELECT results FROM jobs WHERE id=?',(jid,)).fetchone()[0])[0]
        self.assertEqual(row['responses'][1]['selected'],['B','C'])
        self.assertNotIn('teacher_review',row['responses'][1])
        self.assertEqual(self.client.post(f'/assessments/{jid}/review',data={'csrf':self.csrf,'version':version}).status_code,302)
        self.assertIn(b'name="s0q2"',self.client.get(f'/assessments/{jid}/review').data)

    def test_visual_batch_controls_exclude_ambiguous_rows(self):
        jid,version=self.grouped_fixture()
        with connect(self.data) as db:
            rows=json.loads(db.execute('SELECT results FROM jobs WHERE id=?',(jid,)).fetchone()[0])
            a=rows[0]['responses'][1]
            a.update(selected=['B'],review_reasons=['stray_ink_or_cancellation'],review_crop='review/test.png')
            rows[1]['responses'][1]['review_crop']='review/test.png'
            db.execute('UPDATE jobs SET results=? WHERE id=?',(json.dumps(rows),jid))
        page=self.client.get(f'/assessments/{jid}/review')
        self.assertEqual(page.status_code,200)
        self.assertEqual(page.data.count(b'data-batch-choice'),1)
        self.assertIn(b'data-field="decision-s0q2"',page.data)
        self.assertNotIn(b'data-field="decision-s1q2"',page.data)
        self.assertIn(b'value="" checked',page.data)

    def test_group_review_ownership_csrf_and_finalization(self):
        jid,version=self.grouped_fixture()
        other=self.app.test_client()
        with other.session_transaction() as session: session.update(user='bob',csrf='token')
        self.assertEqual(other.get(f'/assessments/{jid}/review').status_code,404)
        self.assertEqual(other.post(f'/assessments/{jid}/review',data={'csrf':'token','version':version}).status_code,404)
        self.assertEqual(self.client.post(f'/assessments/{jid}/review',data={'version':version}).status_code,400)
        with connect(self.data) as db:db.execute('UPDATE jobs SET finalized=1 WHERE id=?',(jid,))
        self.assertEqual(self.client.post(f'/assessments/{jid}/review',data={'csrf':self.csrf,'version':version,'s0q2':'B'}).status_code,409)

    def test_disguised_and_nonfinite_uploads_rejected(self):
        response=self.client.post('/assessments/new',data={'csrf':self.csrf,'title':'Bad','count':'1','key':'A','wrong':'0','pass':'50','scans':(io.BytesIO(b'not an image'),'scan.png')})
        self.assertEqual(response.status_code,400)
        self.assertEqual(list((self.data/'batches').glob('*')),[])
        response=self.client.post('/assessments/new',data={'csrf':self.csrf,'title':'Bad','count':'1','key':'A','wrong':'nan','pass':'50'})
        self.assertEqual(response.status_code,400)

    def test_worker_persists_success_and_failure(self):
        jid=self.upload()
        with connect(self.data) as db: job=dict(db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone())
        out=self.data/'batches'/jid/'output';out.mkdir()
        (out/'results.json').write_text('[{"score": 1}]')
        with patch('mcmark.cli.run',return_value=0): process_job(self.data,job)
        with connect(self.data) as db: self.assertEqual(db.execute('SELECT state FROM jobs WHERE id=?',(jid,)).fetchone()[0],'ready')
        with patch('mcmark.cli.run',return_value=2): process_job(self.data,job)
        with connect(self.data) as db: self.assertEqual(db.execute('SELECT state FROM jobs WHERE id=?',(jid,)).fetchone()[0],'failed')

    def test_restart_marks_incomplete_jobs_for_retry(self):
        jid=self.upload()
        with connect(self.data) as db: db.execute("UPDATE jobs SET state='processing' WHERE id=?",(jid,))
        with patch('threading.Thread'):
            create_app(self.data,testing=True,start_worker=True)
        with connect(self.data) as db: self.assertEqual(db.execute('SELECT state FROM jobs WHERE id=?',(jid,)).fetchone()[0],'failed')

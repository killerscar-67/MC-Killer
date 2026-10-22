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
            db.execute('INSERT INTO users VALUES(?,?,?)',('alice','alice@school.test',generate_password_hash('a-long-test-password',method='pbkdf2:sha256:1000')))
            db.execute('INSERT INTO users VALUES(?,?,?)',('bob','bob@school.test',generate_password_hash('a-long-test-password',method='pbkdf2:sha256:1000')))
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

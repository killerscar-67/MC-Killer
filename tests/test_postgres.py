"""Real PostgreSQL application checks; CI supplies a disposable database."""
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


@unittest.skipUnless(os.environ.get('MCK_TEST_DATABASE_URL'),'Disposable PostgreSQL integration database not configured')
class PostgresIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        from psycopg.conninfo import conninfo_to_dict,make_conninfo
        cls.admin=os.environ['MCK_TEST_DATABASE_URL']
        root=Path(__file__).resolve().parents[1]
        # The test database is explicitly disposable; never point this at a hosted project.
        with psycopg.connect(cls.admin,autocommit=True) as db:
            db.execute('DROP SCHEMA IF EXISTS mc_killer CASCADE')
            for migration in sorted((root/'supabase/migrations').glob('*.sql')):
                db.execute(migration.read_text())
            db.execute("CREATE ROLE mck_ci_app LOGIN PASSWORD 'ci-only-password'")
            db.execute('GRANT mc_killer_backend TO mck_ci_app')
        info=conninfo_to_dict(cls.admin)
        info.update(user='mck_ci_app',password='ci-only-password')
        cls.runtime=make_conninfo(**info)

    def test_real_database_app_review_export_and_access_boundaries(self):
        import psycopg
        from mcmark.web import create_app,connect
        from mcmark.core import grade
        with tempfile.TemporaryDirectory() as data, patch.dict(os.environ,{'MCK_DATABASE_URL':self.runtime,'MCK_DB_SSLMODE':'disable','MCK_AUTH_MODE':'password'}):
            app=create_app(data,testing=True,start_worker=False)
            client=app.test_client()
            with connect(data) as db:
                db.execute('INSERT INTO users(id,email,password) VALUES(?,?,?)',('pg-teacher','pg@delia.edu.hk',''))
            with client.session_transaction() as session: session.update(user='pg-teacher',auth_method='password',csrf='token')
            from PIL import Image
            image=io.BytesIO();Image.new('RGB',(600,800),'white').save(image,format='PNG');image.seek(0)
            response=client.post('/assessments/new',data={'csrf':'token','title':'Postgres test','count':'1','key':'A','wrong':'0','pass':'50','scans':(image,'scan.png')})
            self.assertEqual(response.status_code,302)
            jid=response.headers['Location'].rsplit('/',1)[-1]
            with connect(data) as db:
                job=db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone()
                config=json.loads(job['config'])
                row=dict(file='scan.png',page=1,metadata_details={},sheet_review_issues=[],review_required=True,**grade([{'selected':['B'],'raw_selected':['B'],'review_reasons':['uncertain_density']}],config))
                db.execute("UPDATE jobs SET state='ready',results=? WHERE id=?",(json.dumps([row]),jid))
                version=str(job['updated'])
            self.assertEqual(client.get('/').status_code,200)
            self.assertEqual(client.get(f'/assessments/{jid}/sheets/0').status_code,200)
            review=client.post(f'/assessments/{jid}/sheets/0/review',data={'csrf':'token','version':version,'q1':'A'})
            self.assertEqual(review.status_code,302)
            self.assertEqual(client.get(f'/assessments/{jid}/export/classes').status_code,200)
            self.assertEqual(client.post(f'/assessments/{jid}/finalize',data={'csrf':'token'}).status_code,302)
            with connect(data) as db:
                row=json.loads(db.execute('SELECT results FROM jobs WHERE id=?',(jid,)).fetchone()[0])[0]
                self.assertEqual(row['score'],1)
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    db.execute('DELETE FROM audit')
            # Anonymous/default PUBLIC privileges provide no schema access.
            with psycopg.connect(self.admin) as db:
                db.execute('CREATE ROLE mck_ci_outsider NOLOGIN')
                db.execute('SET LOCAL ROLE mck_ci_outsider')
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    db.execute('SELECT * FROM mc_killer.jobs')

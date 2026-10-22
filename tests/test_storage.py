import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

from mcmark.storage import SupabaseStorage, StorageError, configured_storage, safe_path, relative_evidence, validate_evidence
from mcmark.web import create_app, connect, process_job


class MemoryStorage(SupabaseStorage):
    def __init__(self):
        super().__init__('https://example.supabase.co', 'test-key', 'mc-killer-scans')
        self.objects = {}

    def check(self):
        pass

    def put(self, key, content, content_type=None):
        self.objects[key] = content

    def get(self, key):
        return self.objects[key]


class StorageTests(unittest.TestCase):
    def test_migration_rebases_old_paths_and_requires_every_evidence_file(self):
        jid='a'*32
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/'backup/batches'/jid/'output'
            (output/'review/metadata').mkdir(parents=True)
            old='/data/batches/'+jid+'/output/'
            rows=relative_evidence([{'metadata_details':{'name':{'crop':old+'review/metadata/name.png'}},
                                     'responses':[{'review_crop':old+'review/question.png'}]}],output,jid)
            self.assertEqual(rows[0]['metadata_details']['name']['crop'],'review/metadata/name.png')
            for relative in ('review/00001.png','review/metadata/name.png','review/question.png'):
                with self.assertRaises(StorageError): validate_evidence(rows,output)
                (output/relative).write_bytes(b'evidence')
            self.assertEqual(len(validate_evidence(rows,output)),3)

    def test_integrity_and_traversal(self):
        store = MemoryStorage()
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/'source'
            source.mkdir()
            (source/'scan.pdf').write_bytes(b'original')
            store.save_tree('batch/input', source)
            store.restore_tree('batch/input', Path(directory)/'restored')
            self.assertEqual((Path(directory)/'restored/scan.pdf').read_bytes(), b'original')
            store.objects['batch/input/scan.pdf'] = b'corrupted'
            with self.assertRaises(StorageError):
                store.restore_tree('batch/input', Path(directory)/'bad')
        for value in ('../secret', '/absolute', 'a/../../b', 'a\\b', 'a//b'):
            with self.assertRaises(StorageError):
                safe_path(value)

    def test_private_bucket_and_fail_closed(self):
        store = MemoryStorage()
        with patch.object(store, 'request', return_value=Mock(json=lambda: {'public': True})):
            with self.assertRaises(StorageError): SupabaseStorage.check(store)
        with patch.dict(os.environ, {'MCK_STORAGE_BACKEND':'local', 'MCK_REQUIRE_PERSISTENT_STORAGE':'1'}):
            with self.assertRaises(RuntimeError): configured_storage()

    def test_request_keeps_credentials_backend_and_disallows_redirects(self):
        store = SupabaseStorage('https://example.supabase.co', 'sb_secret_test', 'scans')
        response = Mock(status_code=200, content=b'evidence')
        with patch('mcmark.storage.requests.request', return_value=response) as request:
            self.assertEqual(store.get('batch/review.png'), b'evidence')
            self.assertFalse(request.call_args.kwargs['allow_redirects'])
            self.assertEqual(request.call_args.kwargs['headers'], {'apikey':'sb_secret_test'})

    def test_upload_restart_processing_and_private_review(self):
        from PIL import Image
        store = MemoryStorage()
        with tempfile.TemporaryDirectory() as directory, patch('mcmark.web.configured_storage', return_value=store):
            data = Path(directory)
            app = create_app(data, testing=True, start_worker=False)
            with connect(data) as db:
                for user in ('alice', 'bob'):
                    db.execute('INSERT INTO users(id,email,password) VALUES(?,?,?)', (user,user+'@school.test','unused'))
            client = app.test_client()
            with client.session_transaction() as session:
                session.update(user='alice', csrf='token', auth_method='password')
            image = io.BytesIO()
            Image.new('RGB',(600,800),'white').save(image,format='PNG')
            image.seek(0)
            form = {'csrf':'token','title':'Storage test','count':'1','key':'A','wrong':'0','pass':'50','scans':(image,'Student Name.png')}
            response = client.post('/assessments/new',data=form)
            self.assertEqual(response.status_code,302)
            jid = response.headers['Location'].rsplit('/',1)[-1]
            with connect(data) as db:
                job = dict(db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone())
            self.assertFalse((data/'batches'/jid).exists())
            self.assertTrue(any(key.endswith('/_manifest.json') for key in store.objects))

            def process(inputs, config, output):
                self.assertTrue(list(Path(inputs[0]).glob('*.png')))
                output = Path(output)
                (output/'review').mkdir(parents=True)
                (output/'review/00001.png').write_bytes(b'evidence')
                (output/'results.json').write_text(json.dumps([{'score':1,'crop':str((output/'review/00001.png').resolve())}]))
                return 0
            with patch('mcmark.cli.run', side_effect=process):
                process_job(data,job)
            with connect(data) as db:
                saved = dict(db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone())
            self.assertEqual(saved['state'],'ready')
            self.assertEqual(json.loads(saved['results'])[0]['crop'],'review/00001.png')
            self.assertFalse((data/'batches'/jid).exists())
            # Evidence upload failure must not publish ready results.
            with patch('mcmark.cli.run', side_effect=process), patch.object(store,'save_tree',side_effect=StorageError('Outage')):
                process_job(data,job)
            with connect(data) as db:
                self.assertEqual(db.execute('SELECT state FROM jobs WHERE id=?',(jid,)).fetchone()[0],'failed')
                db.execute("UPDATE jobs SET state='ready' WHERE id=?",(jid,))
            # A fresh app instance, no local evidence files.
            client = create_app(data,testing=True,start_worker=False).test_client()
            with client.session_transaction() as session: session.update(user='alice',csrf='token',auth_method='password')
            self.assertEqual(client.get(f'/assessments/{jid}/images/review/00001.png').data,b'evidence')
            with client.session_transaction() as session: session['user']='bob'
            with patch.object(store,'get', side_effect=AssertionError('Unauthorized storage read')):
                self.assertEqual(client.get(f'/assessments/{jid}/images/review/00001.png').status_code,404)

    def test_upload_failure_does_not_enqueue(self):
        from PIL import Image
        store = MemoryStorage()
        with tempfile.TemporaryDirectory() as directory, patch('mcmark.web.configured_storage', return_value=store):
            app = create_app(directory,testing=True,start_worker=False)
            with connect(directory) as db:
                db.execute('INSERT INTO users(id,email,password) VALUES(?,?,?)',('alice','alice@school.test','unused'))
            client = app.test_client()
            with client.session_transaction() as session: session.update(user='alice',csrf='token',auth_method='password')
            image=io.BytesIO()
            Image.new('RGB',(600,800),'white').save(image,format='PNG')
            image.seek(0)
            with patch.object(store,'put',side_effect=StorageError('Storage unavailable')):
                response=client.post('/assessments/new',data={'csrf':'token','title':'Test','count':'1','key':'A','wrong':'0','pass':'50','scans':(image,'scan.png')})
            self.assertEqual(response.status_code,503)
            with connect(directory) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0],0)

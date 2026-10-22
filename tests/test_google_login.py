import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from mcmark.web import create_app,connect,initialize


class GoogleLoginTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'MCK_AUTH_MODE':'google','MCK_GOOGLE_CLIENT_ID':'test-client.apps.googleusercontent.com','MCK_GOOGLE_CLIENT_SECRET':'test-secret','MCK_GOOGLE_REDIRECT_URI':'https://marking.school.test/auth/google/callback'})
        self.env.start()
        self.app=create_app(self.tmp.name,testing=True,start_worker=False)
        self.client=self.app.test_client()
        self.google=self.app.extensions['mck_google']
        with connect(self.tmp.name) as db:
            db.execute('INSERT INTO users(id,email,password) VALUES(?,?,?)',('teacher','teacher@delia.edu.hk',''))

    def tearDown(self):
        self.env.stop();self.tmp.cleanup()

    def claims(self,**changes):
        return {'sub':'google-sub-123','email':'teacher@delia.edu.hk','email_verified':True,'hd':'delia.edu.hk',**changes}

    def callback(self,claims,**token):
        with patch.object(self.google,'authorize_access_token',return_value={'id_token':'validated-by-library','userinfo':claims,**token}):
            return self.client.get('/auth/google/callback')

    def test_google_login_binds_subject_and_retains_no_tokens(self):
        self.assertEqual(self.callback(self.claims()).status_code,302)
        with self.client.session_transaction() as session:
            self.assertEqual(session['user'],'teacher')
            self.assertEqual(session['auth_method'],'google')
            self.assertNotIn('id_token',session)
            self.assertNotIn('access_token',session)
        self.assertEqual(self.client.get('/').status_code,200)
        with connect(self.tmp.name) as db:
            self.assertEqual(db.execute('SELECT google_sub FROM users WHERE id=?',('teacher',)).fetchone()[0],'google-sub-123')

    def test_rejects_personal_accounts_spoofed_domains_and_unverified_email(self):
        for changes in [{'hd':None},{'hd':'other.edu.hk'},{'email':'teacher@gmail.com'},{'email':'teacher@delia.edu.hk.evil.test'},{'email_verified':False},{'email_verified':'true'},{'sub':''}]:
            with self.subTest(changes=changes):
                self.assertEqual(self.callback(self.claims(**changes)).status_code,403)
        self.assertEqual(self.callback(self.claims(),id_token=None).status_code,403)

    def test_domain_members_are_not_automatically_authorized(self):
        self.assertEqual(self.callback(self.claims(email='student@delia.edu.hk')).status_code,403)
        with connect(self.tmp.name) as db: db.execute('UPDATE users SET enabled=0 WHERE id=?',('teacher',))
        self.assertEqual(self.callback(self.claims()).status_code,403)

    def test_identity_cannot_be_relinked_and_revocation_stops_existing_sessions(self):
        self.assertEqual(self.callback(self.claims()).status_code,302)
        self.assertEqual(self.callback(self.claims(sub='different-sub')).status_code,403)
        with connect(self.tmp.name) as db: db.execute('UPDATE users SET enabled=0 WHERE id=?',('teacher',))
        self.assertEqual(self.client.get('/').status_code,302)

    def test_password_signin_cannot_bypass_google_mode(self):
        page=self.client.get('/login')
        self.assertIn(b'Sign in with Google',page.data)
        self.assertNotIn(b'name="password"',page.data)
        with self.client.session_transaction() as session: csrf=session['csrf']
        self.assertEqual(self.client.post('/login',data={'csrf':csrf,'email':'teacher@delia.edu.hk','password':'anything'}).status_code,405)
        with self.client.session_transaction() as session: session.update(user='teacher',auth_method='password')
        self.assertEqual(self.client.get('/').status_code,302)

    def test_missing_configuration_and_unsafe_callback_fail_closed(self):
        self.app.config['GOOGLE_CLIENT_ID']=''
        self.assertEqual(self.client.get('/auth/google').status_code,503)
        self.app.config['GOOGLE_CLIENT_ID']='client'
        self.app.config['GOOGLE_REDIRECT_URI']='http://untrusted.example/auth/google/callback'
        self.assertEqual(self.client.get('/auth/google').status_code,503)

    def test_provider_errors_and_missing_state_are_rejected(self):
        with patch.object(self.google,'authorize_access_token',side_effect=ValueError('invalid signature or nonce')):
            self.assertEqual(self.client.get('/auth/google/callback').status_code,403)
        # Real Authlib must reject an unsolicited callback before it exchanges codes.
        self.assertEqual(self.client.get('/auth/google/callback?code=fake&state=unknown').status_code,403)

    def test_old_database_migration_is_idempotent(self):
        initialize(self.tmp.name);initialize(self.tmp.name)
        with connect(self.tmp.name) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM users').fetchone()[0],1)
            columns={r['name'] for r in db.execute('PRAGMA table_info(users)')}
            self.assertTrue({'enabled','google_sub'}.issubset(columns))

    def test_authorization_uses_state_nonce_pkce_and_fixed_callback(self):
        from urllib.parse import urlparse,parse_qs
        metadata={'authorization_endpoint':'https://accounts.google.com/o/oauth2/v2/auth','token_endpoint':'https://oauth2.googleapis.com/token','issuer':'https://accounts.google.com','jwks_uri':'https://www.googleapis.com/oauth2/v3/certs'}
        with patch.object(self.google,'load_server_metadata',return_value=metadata):
            response=self.client.get('/auth/google')
        self.assertEqual(response.status_code,302)
        query=parse_qs(urlparse(response.headers['Location']).query)
        self.assertEqual(query['hd'],['delia.edu.hk'])
        self.assertEqual(query['code_challenge_method'],['S256'])
        self.assertEqual(query['redirect_uri'],['https://marking.school.test/auth/google/callback'])
        self.assertTrue(query.get('nonce'))
        self.assertTrue(query.get('state'))

    def test_migrates_real_old_schema_without_losing_users(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as old:
            with sqlite3.connect(str(Path(old)/'school.sqlite')) as db:
                db.execute('CREATE TABLE users(id TEXT PRIMARY KEY,email TEXT UNIQUE NOT NULL,password TEXT NOT NULL)')
                db.execute('INSERT INTO users VALUES(?,?,?)',('legacy','legacy@delia.edu.hk','old-hash'))
            initialize(old)
            with connect(old) as db:
                user=db.execute('SELECT * FROM users').fetchone()
                self.assertEqual(user['password'],'old-hash')
                self.assertEqual(user['enabled'],1)
                self.assertIsNone(user['google_sub'])

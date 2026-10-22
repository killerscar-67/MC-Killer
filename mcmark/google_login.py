"""Google Workspace sign-in, with an explicit approved-teacher list."""
import secrets
import sqlite3
from urllib.parse import urlparse

from flask import abort, redirect, session, url_for
from authlib.integrations.flask_client import OAuth

DOMAIN = 'delia.edu.hk'


def register_google(app, connect, data):
    oauth=OAuth(app)
    google=oauth.register(name='google',client_id=app.config['GOOGLE_CLIENT_ID'],client_secret=app.config['GOOGLE_CLIENT_SECRET'],
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={'scope':'openid email profile','code_challenge_method':'S256','timeout':15})
    app.extensions['mck_google']=google

    def configured():
        if app.config['AUTH_MODE']!='google': abort(404)
        if not all(app.config.get(k) for k in ('GOOGLE_CLIENT_ID','GOOGLE_CLIENT_SECRET','GOOGLE_REDIRECT_URI')):
            abort(503,'School Google sign-in is not configured. Contact the administrator.')
        uri=urlparse(app.config['GOOGLE_REDIRECT_URI'])
        if not uri.hostname or (uri.scheme!='https' and not (uri.scheme=='http' and uri.hostname in ('localhost','127.0.0.1'))) or uri.path!='/auth/google/callback' or uri.query or uri.fragment or uri.username:
            abort(503,'The Google callback URL must be HTTPS (or local development) and end in /auth/google/callback.')

    @app.get('/auth/google')
    def google_start():
        configured()
        # Authlib creates and validates OAuth state, OIDC nonce and PKCE verifier.
        return google.authorize_redirect(app.config['GOOGLE_REDIRECT_URI'],hd=DOMAIN,prompt='select_account')

    @app.get('/auth/google/callback')
    def google_callback():
        configured()
        try:
            # With openid scope, Authlib validates the signed ID token and its nonce,
            # issuer, audience and expiry, then returns its claims as userinfo.
            token=google.authorize_access_token()
            claims=token.get('userinfo',{}) if token.get('id_token') else {}
        except Exception:
            # Do not log authorization codes, ID tokens, or provider error payloads.
            abort(403,'Google sign-in could not be verified. Please start sign-in again.')
        if not isinstance(claims,dict): abort(403,'Google did not return a verified school identity.')
        email=claims.get('email','')
        subject=claims.get('sub')
        if not isinstance(email,str) or not isinstance(subject,str) or not subject:
            abort(403,'Google did not return a verified school identity.')
        email=email.strip().lower()
        if claims.get('email_verified') is not True or claims.get('hd')!=DOMAIN or email.rsplit('@',1)[-1]!=DOMAIN or email.count('@')!=1:
            abort(403,'Use your verified @delia.edu.hk Google Workspace account.')
        with connect(data) as db:
            db.execute('BEGIN IMMEDIATE')
            user=db.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()
            if not user or not user['enabled']:
                abort(403,'This account is not on the approved teacher list. Contact the administrator.')
            if user['google_sub'] and user['google_sub']!=subject:
                abort(403,'This teacher account is linked to a different Google identity. Contact the administrator.')
            try:
                db.execute('UPDATE users SET google_sub=? WHERE id=?',(subject,user['id']))
            except sqlite3.IntegrityError:
                abort(403,'This Google identity is already linked to another account.')
        # Retain no Google access, refresh, or ID tokens in cookies or the database.
        session.clear()
        session.update(user=user['id'],email=email,auth_method='google',csrf=secrets.token_urlsafe(32))
        session.permanent=True
        return redirect(url_for('index'))

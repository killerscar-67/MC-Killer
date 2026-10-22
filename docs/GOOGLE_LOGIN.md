# Delia Google Workspace login

The default production login is Google OpenID Connect, restricted to verified `@delia.edu.hk` Workspace identities **and an approved teacher list**. A matching email suffix alone does not grant access. Student accounts sharing the school domain are denied unless explicitly approved.

## Configure with school IT

1. Choose the backend URL. The current PR has no hosted backend URL or cloud database.
2. In a school-controlled Google Cloud project, configure Google Auth Platform / the OAuth consent screen for the school. Use the organization's internal audience when available and follow the school's administrator approval process.
3. Create an OAuth client of type **Web application**. Register the exact authorized redirect URI: `https://YOUR-HOST/auth/google/callback`. For development only, `http://127.0.0.1:8000/auth/google/callback` or the matching localhost URI is supported.
4. Put the client ID and client secret into server environment variables `MCK_GOOGLE_CLIENT_ID` and `MCK_GOOGLE_CLIENT_SECRET`; set `MCK_GOOGLE_REDIRECT_URI` to that exact registered URI. Keep `MCK_AUTH_MODE=google`. Never place the client secret in browser code, GitHub files, or chat. See `.env.example` for variable names.
5. Set a stable `MCK_SECRET_KEY`, serve through HTTPS, and set `MCK_HTTPS=1`. Use `MCK_HTTPS=0` only for localhost HTTP development.
6. Approve teachers on the server, using the same `--data` directory as the service:

```sh
python -m mcmark.web authorize-teacher --data /data --email teacher@delia.edu.hk
python -m mcmark.web serve --data /data --host 0.0.0.0 --port 8000
```

To revoke access:

```sh
python -m mcmark.web revoke-teacher --data /data --email teacher@delia.edu.hk
```

Revocation is checked on protected requests, including active browser sessions. Teacher accounts are bound to Google's stable subject identifier after their first successful sign-in. A changed identity cannot silently take over an existing account. Existing database files are migrated in place to add the identity and enabled-state columns; back up the data directory before upgrades.

## What the application checks

Authlib handles the authorization-code flow with state, nonce, PKCE and validation of the Google-signed ID token. The application additionally requires `email_verified=true`, `hd=delia.edu.hk`, the exact school email domain, and an enabled approved-teacher record. The `hd` authorization request parameter is a Google account-picker hint, not the access-control check.

Only `openid email profile` scopes are requested. The app does not request Gmail, Drive, or Contacts access, and retains no Google access/refresh/ID tokens in browser sessions or the database. It stores the teacher email and stable Google subject. Provider error details and tokens are not logged by the login routes.

Local password login remains available only when explicitly selecting `MCK_AUTH_MODE=password` for development. It is disabled in Google mode, including direct POST attempts. Do not enable password mode for the school's Google-only deployment.

The automated tests use simulated provider responses to check application policy and exercise Authlib's missing-state rejection. A live round trip with a real registered client and school account remains required after deployment.

References: [Google ID-token verification](https://developers.google.com/identity/gsi/web/guides/verify-google-id-token), [Authlib Flask OIDC](https://docs.authlib.org/en/latest/oauth2/client/web/flask.html).

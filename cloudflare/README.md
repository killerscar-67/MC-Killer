# Cloudflare Pages gateway

Deploy `pages/` using Pages Direct Upload with advanced-mode `_worker.js` support (Wrangler or the deployment API). Dashboard upload also supports this advanced-mode `_worker.js`; upload the folder or a ZIP containing `_worker.js` and `index.html` at its root.

The fixed upstream is the Northflank MC-Killer service. Request and response bodies stream through; responses are never cached. Same-origin absolute redirects are rewritten to the public Pages host. Google redirects remain external. Cookies remain host-only on the Pages address.

Set Northflank `MCK_GOOGLE_REDIRECT_URI` and Google's authorized redirect URI to `https://ACTUAL-PROJECT.pages.dev/auth/google/callback`. Keep OAuth and database secrets exclusively in Northflank. No credentials belong in this gateway.

This gateway does not add persistent file storage or processing capacity. Confirm Google accepts the issued hostname, then verify login and review end to end before live use.

Public gateway: https://mc-killer.pages.dev

OAuth callback: https://mc-killer.pages.dev/auth/google/callback

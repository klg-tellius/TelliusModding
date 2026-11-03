# Tellius Archive Decap OAuth worker

This Cloudflare Worker is the GitHub OAuth bridge required by the static Decap CMS.
It stores no content and logs no tokens. OAuth state is short-lived, HMAC-signed,
bound to the exact archive origin, and checked against a secure HTTP-only cookie.

## Deploy

1. Create a GitHub OAuth App. Use the Worker URL as its homepage and
   `<worker-url>/callback?provider=github` as its callback URL.
2. Install dependencies with `npm install` in this directory.
3. Add encrypted secrets, entering each value only at Wrangler's prompt:

   ```text
   npx wrangler secret put GITHUB_OAUTH_ID
   npx wrangler secret put GITHUB_OAUTH_SECRET
   npx wrangler secret put OAUTH_STATE_SECRET
   ```

   Generate `OAUTH_STATE_SECRET` with at least 32 random bytes. Never store these
   values in the repository or in `.dev.vars` committed to Git.
4. Run `npm run deploy`. The production Worker URL for this repository is
   `https://tellius-archive-oauth.klgtellius.workers.dev`.
5. Set `backend.base_url` in `wiki/admin/config.yml` to that URL. Register the same
   URL in the GitHub OAuth App, then rebuild the wiki.
6. Confirm `/healthz`, trusted-editor publication, and outsider Open Authoring.

If the archive moves to a custom domain, change `ALLOWED_ORIGIN`, redeploy, and
update the OAuth App. Rotate the client secret and state secret immediately after
suspected disclosure; existing five-minute state values then become invalid.

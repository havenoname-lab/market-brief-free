# Market Brief — free cloud newsroom

A Chinese-language public-news reader with source links, topic filters, a seven-day history view and expandable sector signal modules. Headlines and abstracts are source statements; financial mechanisms are conditional inferences. Live price data is not connected.

## Runtime

- Cloudflare Workers serves the UI and an authenticated, indexed D1 API.
- GitHub Actions runs the Python collectors at minutes 7 and 37 of every hour. Schedules may be delayed or skipped by GitHub; freshness and source gaps remain visible.
- Workers AI uses the free-tier-compatible Mistral Small 3.1 model. The application caps calls at 100 per UTC day; Cloudflare's account-wide free quota also applies. Quota failure pauses analysis while collection continues. No paid plan or paid fallback is configured.
- News snapshots are precomputed in the collection job. Larger snapshots are gzip-compressed before storage, so the Worker does not compute financial analysis on page requests.

## Access and credentials

All reader pages and APIs require a generated shared reading account. Write/sync endpoints require a separate random application token. The GitHub workflow receives only this application token, not a Cloudflare account token or account password. Public source code contains no database, model weights, personal email settings or credentials.

Cloudflare secrets: `READER_PASSWORD`, `SYNC_TOKEN`. Optional reader name: `READER_USERNAME` (defaults to `reader`). GitHub Actions secret: `SYNC_TOKEN`; repository variable: `CLOUD_BASE_URL`. The collection job stays disabled until the URL variable is configured.

## Setup

1. Authorize the official Cloudflare Wrangler and GitHub CLI tools; verify the Cloudflare account email.
2. Create the free D1 database and apply `worker/schema.sql`.
3. Run `python scripts/build_public.py`, then deploy with Wrangler. Add the two generated secrets with Wrangler's secret storage.
4. Privately migrate existing records with `python -m scripts.seed_sql SOURCE_DB PRIVATE_OUTPUT.sql` and Wrangler D1 import. Never commit the migration file.
5. Configure the GitHub repository secret and URL variable, then manually run `Collect public news` and verify a successful sync.

## Development checks

`python -m pytest tests -q`

`node --test tests/worker.test.mjs`

The original localhost application is not modified by this separate deployment. Public feed and sitemap coverage is partial; none of the source adapters guarantees all historical articles. D1/storage/AI free quotas and provider availability can interrupt service. GitHub may disable scheduled workflows in a public repository after 60 days without repository activity; the repository owner should check scheduled operation periodically.

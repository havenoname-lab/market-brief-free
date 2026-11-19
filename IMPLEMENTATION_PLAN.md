# Free cloud implementation plan

Goal: Share the existing newsroom from a free Cloudflare URL and continue collecting while the Windows computer is off.

Architecture: Workers serves static assets and a small authenticated D1-backed API. GitHub Actions runs the existing Python collectors every 30 minutes and uploads changed records through a scoped application sync secret. No Cloudflare account token is stored in GitHub. AI uses only a free-tier-compatible Workers AI model with an application daily cap; quota failures pause analysis without pausing collection.

1. Implement indexed D1 article/snapshot schema and bounded Worker read/sync endpoints. Test login, size limits, pagination, update validation and fail-closed defaults.
2. Implement Python state download, existing collector reuse, local SQLite reconstruction and incremental upload. Preserve source IDs, publication times, existing Chinese payloads and diagnostics. Precompute sector/coverage snapshots outside Worker CPU limits.
3. Adapt frontend refresh and runtime status text to scheduled cloud collection. Preserve module layout, source links and pagination.
4. Add a public-repository workflow, narrowly scoped permissions, non-overlapping collection and daily history supplementation. Keep personal data, database files and credentials out of source control.
5. After official account authorization, verify the account is on Workers Free, create D1, deploy, migrate existing records privately and configure generated reader/sync secrets.
6. Verify the public HTTPS URL, authenticated APIs, migrated counts, a completed GitHub workflow and subsequent freshness. Do not claim AI works before a real validated response. Free limits, delayed scheduling and unsupported sources remain visible.

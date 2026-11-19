# Free cloud edition

Deployment in progress. The public reader is not live yet.

Planned runtime: Cloudflare Workers + D1; collection: GitHub Actions; AI: free quota only.
Workers API, D1 schema, collector-state sync, scheduled workflow and frontend adaptation are implemented. D1 has been created and the actual import succeeded: 4,356 deduplicated articles plus 11 precomputed snapshots, about 10MB total. Reader and sync secrets have been configured separately in Cloudflare secret storage; the sync secret is configured in GitHub Actions.

The Worker code and assets uploaded successfully, but activation of the public workers.dev route is still blocked by Cloudflare error 10034: account email verification required. The URL currently does not serve the application. The repository URL variable is deliberately unset, so the scheduled job does not attempt to sync to an inactive endpoint.

The free AI provider returned a schema-validated Chinese assessment and a valid conditional mechanism chain in a bounded live readiness probe. The deployed Worker AI route, gzip snapshots over public HTTPS and a full GitHub collection job still require end-to-end verification after the account restriction is cleared. Do not describe the cloud application as live until these checks pass.

Local checks passed: 5 Python tests, 6 Node tests and JavaScript syntax validation. Read-only code review found no remaining blocking code defect after correcting the 75-minute cloud gap threshold, keyset pagination and compressed overview snapshots.
No database, account passwords, API tokens, model weights, or personal email configuration is included.

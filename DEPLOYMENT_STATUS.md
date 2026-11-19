# Free cloud edition

Live free cloud deployment, verified on 2026-11-19 (Asia/Shanghai).

Public URL: https://market-brief-free.arket-rief-free-cloud.workers.dev

All reading routes require the separate generated reader account. Reading credentials are held in a local ignored file, not in this repository.

Planned runtime: Cloudflare Workers + D1; collection: GitHub Actions; AI: free quota only.
Workers API, D1 schema, collector-state sync, scheduled workflow and frontend adaptation are implemented. D1 has been created and the actual import succeeded: 4,356 deduplicated articles plus 11 precomputed snapshots, about 10MB total. Reader and sync secrets have been configured separately in Cloudflare secret storage; the sync secret is configured in GitHub Actions.

Account verification propagated successfully and the public workers.dev route is active. The repository URL variable and sync secret are configured. The first actual GitHub Actions run completed successfully: https://github.com/havenoname-lab/market-brief-free/actions/runs/44558905745 . It restored 4,356 article states and synchronized 106 changed articles plus 11 snapshots. The configured schedule is minute 7 and 37 of each hour; GitHub scheduling may be delayed or skipped.

The free AI provider returned schema-validated Chinese content and a valid conditional mechanism chain. The actual cloud collection job then performed two deployed AI attempts successfully and updated the analysis success timestamp. Free daily quota enforcement and validation remain active.

Live HTTP checks passed: public health returns 200; unauthenticated reader access returns 401; the authenticated homepage, versioned assets, articles, sources, all tested summaries, coverage, analysis status, UI version and continuity return 200 with valid JSON where applicable; the reading account is denied administrative sync access. The precompressed overview now uses Workers' manual body encoding to prevent double compression. Browser screenshot/layout checks and regional network reachability were not verified.

Local checks passed: 5 Python tests, 6 Node tests and JavaScript syntax validation. Read-only code review found no remaining blocking code defect after correcting the 75-minute cloud gap threshold, keyset pagination and compressed overview snapshots.
No database, account passwords, API tokens, model weights, or personal email configuration is included.

# Validation and release limits

This records evidence from the current cloud build. It is not a claim of Windows deployment, live bank settlement, payroll-provider approval, or tax compliance.

## Verified

- The current update passes **73 Python accounting tests**, **12 Node source-update/desktop-origin tests**, **4 Node Firebase snapshot tests**, and **3 Android company-origin unit tests**. The added HTTP test simulates Host forwarding from a TLS terminator; it does not test a live TLS deployment.
- Main 8.2.2 and Vendor 4.1.2 complete connected Windows editions were packaged and NSIS installers generated. Profile-copy fixtures verify that original bytes remain unchanged and running/ambiguous/unsafe profiles are rejected. These are fixture checks, not real Windows upgrades.
- All three Android debug APKs compiled and passed `apksigner verify`; package identities, versions and SHA-256 hashes are recorded in `android-apks/manifest.json`. They have not been run on a physical device or emulator. Business Accounting signs into Firebase and discovers its HTTPS service without asking for a URL; no shared accounting server has been deployed. Firebase snapshot upload/import and company discovery are implemented with controlled-response tests; live deployment and rule enforcement remain unverified.

The earlier application validation also established:

- **63 automated tests passed.** Coverage includes combined retail/wholesale accounting, balanced journals, integer-cent rounding, idempotent imports, source revisions and reversals, duplicate payment copies, stale snapshots, closed periods, reconciled postings, retained attachments, supplier payments, credential redaction, owner setup, password hashing, lockouts, session invalidation, viewer restrictions, and rejected malformed imports.
- Asset tests cover full-month straight-line depreciation, every-cent allocation, salvage limits, repeat-post prevention, future-month rejection, equipment disposal, and duplicate acquisition links.
- Payroll tests cover wage/tax accruals, net-wage payments after closing an earlier period, duplicate/overlapping periods, provider calculation review, explicit approval, changed-calculation rejection, uncertain-outcome retention, duplicate-submission blocking, and demo/production accounting separation.
- Payroll API transport tests use test doubles against methods and paths inspected in the official Gusto SDK. **They are not live provider integration tests.** No bank payments, tax remittances, tax filings, or payroll submissions were made.
- Tax-source tests verify first-fetch baselines, changed-page review queues, source citations, failed-source status, review notes/effective dates, and that a source change never rewrites accounting or tax formulas. The registry includes all 50 states and DC. This does not establish that every state URL is currently reachable or that every local law is covered.
- Chromium browser smoke checks passed for first-time owner creation, login/logout, direct expense entry, saved production recipes, channel pricing, stock planning, vendor import preview/commit, supporting attachments, equipment registration and depreciation, external payroll records, journals, reconciliation, and financial reports. No page-script errors occurred.
- The browser created actual printable PDF artifacts for a payroll earnings statement and profit-and-loss report. Desktop and mobile layout screenshots were captured with fictitious test records in a disposable database. Those company data files are not shipped in the installer.
- Both connected source-app archives were extracted with per-file integrity verification and compared byte-for-byte to their built source copies. JavaScript syntax checks passed. Connector-hook checks verified owner gating, mirrored-record filtering, source-data preservation and the financial snapshot shape. All files in the original uploaded main-app ZIP still match their extracted originals byte-for-byte.
- The Windows application directory includes a pinned Electron runtime and a checksum-verified Windows Python runtime. The NSIS compiler generated a Windows installer and its file manifest / SHA-256 companion. Installer generation does not require Wine; the uninstaller is created on the target Windows computer. Uninstall instructions remove only files from the packaged manifest and preserve company data outside the installation directory.

## Not verified / prerequisites

- **Windows installation, launch, upgrade, printing to a physical printer and uninstall were not executed on Windows.** Test these on a separate Windows user profile before using live company data. The installer is unsigned because no code-signing certificate was supplied.
- A Linux Electron launch using a headless Ozone backend crashed in this cloud runtime. Actual web workflows were instead validated in Chromium. This is not evidence that Windows launch works or fails.
- Source-app logins, real Firebase permissions, existing live data, source-app upgrade compatibility and cross-computer transfers have not been validated. The provided packages contain compiled app assets rather than the original React development projects. A separate installation directory alone does not isolate existing Electron user data; use a separate Windows user or the documented disposable-profile override.
- **Live all-50-state payroll and direct deposit remain blocked on an approved payroll-provider application/company, authorized credentials, employer/state setup, employee onboarding, and bank verification.** Gusto integration code is present, but it must be exercised with the actual approved account in its demo environment before production activation.
- Provider-hosted workflows and current provider responses need end-to-end testing. Unsupported accounting components, imputed-pay allocations, deferred taxes, reversals, and totals that do not reconcile remain in an explicit accounting-review state.
- Official IRS access was denied by the current cloud network policy when tested. A draft with the required official-state/provider domains and reusable startup instructions was saved. Draft persistence does not apply or publish the network policy. Review/save/publish it in environment settings before expecting those cloud requests to work. The installed Windows application uses the PC's own Internet access.
- Official-source monitoring is not an autonomous legal-research or certification service. The provider supplies maintained tax calculations; source-page differences require review. Checks stop when the process or computer is off unless a hosted service is separately deployed.
- Bank feeds, ACH settlement reconciliation, tax filing and provider subscription/partner onboarding require the appropriate external services. This build does not fabricate any of those capabilities.
- No real business backups were provided. Import totals and account mappings must be checked against actual source-app control totals before relying on company financial statements.

## Release artifacts

The Windows installer, its SHA-256 file, installed-file manifest, source-app connection package, source ZIP and quick-start instructions are under `dist/`. File hashes are computed from the generated artifacts, not placeholders. The release source includes reproducible build scripts and the desktop dependency lockfile.

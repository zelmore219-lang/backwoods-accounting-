# Backwoods Brew 8.2.0 — Windows Test Release Candidate

This is a **Windows installer source package**, NOT a completed Windows EXE or production-ready app. It is based on recovered packaged Electron files rather than original React source.

## Improvements in this release
- Consistent purchase source IDs across wholesale accounting journal and inventory movements.
- Rollback of partially mutated in-memory wholesale data when order status or form actions throw errors.
- Additional packaging preflight checks; Windows batch build script.
- Existing wholesale customer, product, raw-material, batch, order, packing, delivery, route, returns, reporting, backup and journal interfaces are retained.

## Build and test on Windows
1. **Back up your existing Backwoods Brew data** and do not overwrite the working installation.
2. Install Node.js 22 or later.
3. Extract this ZIP and run `BUILD-ON-WINDOWS.cmd` with an internet connection.
4. If it succeeds, inspect `dist/` for the NSIS Windows installer.
5. Install into a test environment and verify startup, login, retail screens, wholesale, and backup export. Use fictitious business records only.
6. If it fails, save the complete command window output. Do not assume the installer exists.

## Known incomplete items (do not use for live business transactions)
- **No automatic wholesale postings into the main retail/company general ledger.** Local wholesale journal is independent.
- **No live wholesale Firebase writes** or verified employee synchronization.
- **No verified Windows GUI launch** or install/upgrade test. This environment cannot run a Windows NSIS installer.
- **No full production-grade** tax, multi-line invoices, driver proof of delivery, refunds, granular local permissions, or end-to-end accounting integration.
- Original compiled retail application is not editable React source; there is additional integration risk.

Passing static tests does not establish business correctness or readiness for production.

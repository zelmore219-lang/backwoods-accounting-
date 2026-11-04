# Central Accounting — implemented scope and remaining work

## Delivered in this build
- Central Accounting screen inside the recovered Backwoods Brew Electron application.
- Offline wholesale journal normalization and double-entry validation.
- Optional import of **journalEntries** from a main-app JSON backup, without modifying the main app's records.
- Consolidated journal account balances grouped by division and CSV export.
- Duplicate source ID, unbalanced entry, malformed line and missing journal validation.
- Automated tests for consolidation, division reporting, CSV export, duplicate entries, and invalid imports.

## Not complete / not production ready
- **No automatic posting into the main application's existing ledger.** The recovered compiled retail application derives its general ledger from multiple record types (sales, bills, payroll, inventory, journal entries). A simple journalEntries import is not a complete company accounting ledger.
- Retail entries must be imported manually and are not persisted by this module.
- No Firebase ledger synchronization, cloud transaction safety, or reconciliation against the live main app.
- No accounting period close, tax treatment, payment settlement, or bank reconciliation integration.
- No Windows installation or runtime verification.

This build is a meaningful, tested offline consolidation *viewer*, not the complete central accounting integration requested. Do not rely on it as a sole source of company financial statements.

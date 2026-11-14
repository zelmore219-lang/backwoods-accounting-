# Coordinated application repair and payroll preparation

Work requested November 14, 2026. This is implementation work, including the
owner's second payroll-management request. This document is a progress record,
not a certification that the entire suite is deployed or accepted.

## Existing architecture and implementation order

1. Main 8.2.9 and Vendor 4.1.8 are the connected Electron/Capacitor programs in
   `source-app-updates` and `android-apps`. Their approved Firebase project is
   `backwoodsbrew-e3584-d52a3`. Main retains username sign-in and its existing
   saved retail records. Vendor uses UID-keyed `vendorUsers` and separate
   wholesale collections. Do not put wholesale customers into retail stores.
2. Employee 0.4.5 has a private Windows owner service, an encrypted Firestore
   mailbox, one verified Firebase UID per employee, and canonical shared clock
   records. Reuse this service for Vendor. The new clock uses server timestamps,
   exact existing Wholesale jobs, retained request IDs and the existing shared
   active-shift transaction. Vendor clients cannot write official timecards.
3. Business Accounting 1.0.7 maintains the existing company ledger and private
   shared-ledger namespace. Main/Vendor financial transfers and Employee approved
   time imports already exist. Preserve document IDs, revisions, division/source
   metadata, balanced postings, closed-period protection and duplicate detection.
4. Implement Payroll Management in Accounting, with manual preparation and
   approved Employee time, rate snapshots, review/approval, payroll CSV/Excel,
   provider mappings and receipt references, final-result reconciliation and
   actual payment records. Gross estimates and exports must never imply taxes
   were calculated, a provider received a submission, or a bank paid staff.
5. Verify the actual browser workflows, shared Firebase emulators, regressions,
   package contents and compatible native builds before publishing any update.
   Preserve installed identities, data paths and Android signing keys.

## Production source blocker

The connected GitHub inventory contains no Production source repository or
published Production package. The existing system audit identifies an unshipped,
locally modified prototype based on Accounting commit 79c8ca8; those prototype
files are absent from all available workspaces and repository branches. The
owner does not know its location. Do not invent its database, SKU mapping, stock
ownership, authentication or an already-working connection. Production stock
transfers, manufacturing/COGS lifecycle and its central Employee access remain
pending recovery and review of the actual source. Do not enable new manufactured
inventory writes against the older Vendor stock writer.

## Verified implementation before native packaging

- Main: removed requested tabs/routes/exclusive components while preserving
  historical data and unrelated auth/business logic. Actual Chromium login,
  sale, inventory, receipt/cancel/reprint and balanced Accounting export pass.
- Vendor: real UID/password login, server clock through the existing encrypted
  owner protocol, shared active-state/overlap guard, lost-response recovery,
  offline retry and actual Employee source/department visibility pass. Browser
  acceptance covers desktop/tablet/phone. The emulator browser uses authenticated
  REST only for profile-read transport because this environment cannot negotiate
  emulator WebChannel; real Auth, rules, encrypted mailbox and backend are used.
- Employee: private finance roster/feed, Accounting roles and the existing
  central UID/password. Ordinary suite: 135 cases, 112 passed and 23 emulator-only
  cases skipped. Eight real shared-clock emulator cases passed; the additional
  Finance integration passed separately after its assertions were corrected to
  preserve the approved-workweek freeze and expected validation response.
- Accounting: Payroll Management has domain storage/calculations, manual and
  approved-source wages, salary/OT/additions, rate history, departmental totals,
  review/owner approval, immutable reviewed CSV/Excel and verified provider
  templates, actual receipt/final results, actual bank settlement/reconciliation.
  The complete UI workflow passed on desktop/tablet/phone; viewer APIs are denied.
- Actual Vendor -> Employee timesheet approval -> protected finance feed -> same
  Accounting ledger was tested with real Auth/Firestore emulators. Staff used
  the same password/UID without replacing the company's native owner connection.
  Revocation blocked an open finance session; Main access remained active.
  A synthetic administrative withdrawal was freshly retrieved and blocked
  cached payroll review. Normal approved-workweek corrections remain frozen.
- Additive tables contain no SQL triggers/views; the existing shared-ledger
  executable-schema rejection remains. Ledger posting and payroll state commit
  atomically. Current approved-source eligibility is tracked separately from
  preserved history, and one Accounting profile binds one actual legal company.
- Native CI builds exact packages, verifies Android identity/signature, then
  installs/reinstalls those exact Windows bytes before publishing the update
  feed. Source/workflow completion does not itself imply a published release.

Full owner instructions: [COORDINATED-OWNER-GUIDE.md](COORDINATED-OWNER-GUIDE.md).

## External prerequisites

No ADP or other new provider API credentials, sandbox, or verified import schema
have been supplied. General payroll review exports can be implemented and tested;
provider-specific compatibility requires its actual approved import specification.
The owner's existing HR.my workflow must remain usable without Gusto enrollment.
No live payroll submission, tax filing, money transfer, employee activation or
manufacturing transaction is authorized as a software test.

# Backwoods Business Accounting

A standalone company ledger for Backwoods Brew retail activity, Vendor Ordering wholesale deliveries, and transactions entered directly in this app. The original apps retain their own accounting.

## Windows installation

Use `Backwoods-Business-Accounting-Setup-1.0.2.exe` from the release package. It bundles the desktop shell and Python runtime: a separate Python installation is not required. Install for your Windows user, launch Business Accounting, and create the first owner account. There is no default username or password. Use a passphrase of at least 12 characters.

The application stores your database in `%LOCALAPPDATA%\BackwoodsBusinessAccounting`. Uninstalling the application preserves this data. Back it up before upgrading. Closing the window keeps the app in the system tray when supported, so enabled local feeds and tax-source checks can continue. Use the tray menu's Exit command to stop it. A computer that is off cannot run the monitor.

The installer is unsigned unless built with your organization's signing setup. A generated Windows installer is not evidence of successful Windows installation or bank/payroll operation; see `VALIDATION.md` for exactly what was tested.

## What the app does

- Maintains one integer-cent, double-entry company ledger, original accounting records, import history, revision reversals, and supporting attachments.
- Supports previewed imports and one-way local automatic feeds from connected copies of the supplied Main 8.2.0 and Vendor Ordering 4.1.0 apps.
- Records independent invoices, bills, expenses, payments, tax payments, journals, opening balances, and corrections.
- Shows profit and loss, balance sheet, closing trial balance, the general ledger, current receivable/payable aging, and bank reconciliation.
- Saves production recipes with ingredients, packaging, labor burden, overhead, waste and yield, plus retail, wholesale and distributor pricing scenarios.
- Shows source inventory separately, with case packs, reorder targets, lead times and expiry notes. Shared physical stock is not added together automatically.
- Registers equipment, straight-line full-month book depreciation, and equipment disposal gains/losses. This is not a tax MACRS, Section 179 or bonus-depreciation calculation.
- Supports an approved Gusto Embedded Payroll connection for provider workflows, calculations, owner-approved submissions, payroll status and accounting sync. Provider onboarding, account approval, scopes and verified bank funding are external prerequisites. All-50-state tax coverage and direct deposit are supplied by the provider, not a homemade withholding table.
- Keeps externally calculated payroll records, employees, net-wage accruals/payments, employer taxes, and printable payroll records. Direct entry records amounts; it does not move money or file a return.
- Provides printable documents and PDF saving through the normal Windows print dialog.
- Requires login, hashes passwords with scrypt, expires sessions, locks out repeated failed sign-ins, and restricts user management, payroll-provider authorization and database backups to the owner. Accountant and financial-viewer roles are available.

## Source-app connections

Complete connected editions of **both** supplied source apps are now in [source-app-updates](source-app-updates/README.md). Extract the whole repository and run `BUILD-APP-UPDATES-WINDOWS.cmd` to build Main 8.2.3 and Vendor 4.1.3 installers. Node.js 22+ is required; these two builds do not require Python. These replace the earlier manual ASAR replacement instructions.

Back up and close the originals first. Connected editions install alongside them with separate profiles. On first launch, the helper copies a detected original profile without modifying it; ambiguous or unsafe profile choices stop with an explanation. Check your records before using the connected edition for future entries. The preserved original profile is not a second synchronized local copy. For isolated tests, use a separate Windows user for all three applications; `BACKWOODS_TEST_DATA_DIR` isolates only a source profile.

Sign in to each source app as the same Firebase owner. Financial snapshots send automatically while the apps are open, and Business Accounting imports them into one shared Firestore ledger. The accounting engine runs inside the Windows app and Android APK. **No external host, transfer URL, Firebase Functions or Blaze upgrade is required.** Complete the one-time [Spark setup](firebase/SETUP.md) and review the merged permissions first. Live rules have not been published by this build. The same-PC Windows file route also remains automatic, with the same import IDs.

The vendor connected copy additionally captures historical-at-event unit costs for future delivery and return movements. Existing movements without captured unit costs appear in a review queue. Enter actual historical costs from supporting records; current catalog costs are not assumed to be historical costs.

The main app's preferred connection exports its own general ledger, including its payroll and roasting rules. Plain backup imports support core retail records but reject unsupported components. **Choose the main-ledger connection before importing plain main-app backups.** The two formats use different source IDs, so changing formats in a populated company requires a reviewed migration and is blocked rather than double-posted.

Vendor customer payments duplicated in both an invoice and the payment list are counted once. Approved credits already included on an invoice are not posted a second time. Inventory purchase receipts accrue inventory and accounts payable; their companion stock movements do not also accrue the purchase. Supplier invoice formats not implemented in the supplied build are rejected for review. Hard-deleted source transactions are never silently deleted from posted books.

## All three Android APKs

Installable **test** APKs for Main, Vendor and Business Accounting are in [android-apks](android-apks/README.md), with hashes and version metadata. They are debug signed and have not been tested on a physical Android device. Accounting requires Android 7+ on ARM64/x86-64; source apps require Android 6+. Original APK signing keys and Android projects were not supplied, so the two source editions install alongside existing apps.

The source APKs upload authenticated financial copies after owner sign-in. Business Accounting now bundles the full engine and syncs one shared ledger directly through Firestore, instead of asking for a hosted service address. One-time Firebase rules/account linking is required; no host or billing upgrade is needed. Source owner apps must be open for the current sender. Android Accounting needs API 24+ on ARM64/x86-64; main/vendor keep API 23+ targets. Spark quotas and documented supported sizes apply. See [Spark setup](firebase/SETUP.md).

`BUILD-APK-WINDOWS.cmd` rebuilds all three APKs. Complete Android projects and prerequisites are in [android-apps](android-apps/README.md).

## Connected payroll setup

An owner needs an approved Gusto Embedded Payroll application and company authorization. Enter its company UUID, environment and company access token in the Windows app's payroll connection form. Refresh-token settings are optional only when the selected authorization does not need renewal; expired authorization blocks service access. Access and refresh secrets are encrypted with Windows DPAPI for the current Windows user and are not included in the database backup. Reconnect after moving to another Windows account or computer.

For development, use secure environment bindings named `GUSTO_COMPANY_ID`, `GUSTO_ACCESS_TOKEN`, optionally `GUSTO_REFRESH_TOKEN`, `GUSTO_CLIENT_ID`, `GUSTO_CLIENT_SECRET`, and `GUSTO_ENVIRONMENT` (`demo` or `production`). Do not put values into the repository or chat. Linux development does not save plaintext payroll credentials; Windows encrypted storage or environment bindings are required.

Demo payroll is never posted to the company ledger. A production submission requires a fresh provider calculation, the owner password, and approval of that specific pay date. Submission is asynchronous: acceptance, processing and deposit settlement are distinct. An uncertain submission cannot be retried automatically. Refresh its provider status and resolve it with the provider first.

Provider accounting sync posts validated accruals to payroll clearing accounts and retains the provider's tax totals. Actual bank and tax settlements still require reconciliation. Unsupported/irreconcilable components are flagged, not forced to balance. Imputed pay, owner draws, deferred taxes and payroll reversals require a reviewed allocation. Provider processing can continue while an accounting allocation needs review. The official provider workflow supplies legal pay stubs and filing documents; the local external-payroll statement is not a substitute for those provider documents.

API contract reference: official `@gusto/embedded-api` 0.16.3, API version `2025-06-15`, https://github.com/Gusto/gusto-typescript-client and https://docs.gusto.com/embedded-payroll/ . No live provider requests or payroll payments were authorized or executed during this build.

## State tax-source monitoring

Select the actual states of operation. The registry contains all 50 states and DC. Federal and selected state official pages are checked daily while the app runs; a manual check is also available. The first successful fetch is a baseline. Later text changes enter a review queue with the source URL and detected differences. An owner can document applicability, a confirmed effective date, and provider follow-up.

This is source-page monitoring, not a guarantee that every law, regulation or local tax was discovered. A page change never rewrites payroll formulas. The connected provider supplies maintained payroll tax calculations. Failed, moved, blocked and stale sources remain visible as monitoring problems. Checks run in an open installed accounting app. Firebase stores the results; it does not execute website research while all installed apps are closed.

## Backups, printing and closed periods

Use Settings to download a complete SQLite backup, including records, files, recipes, registers, users and audit history. Keep a copy off this computer. Payroll connection credentials are stored separately and must be reconnected after restoration on another Windows account. Protect backups as confidential business records.

Use Print Center, record print links, payroll-record statements, recipe printouts and depreciation schedules. Windows' print dialog can save PDFs. Opening a print view is audited; the app does not claim a physical printer completed a job.

Close periods only after resolving historical costs, reviewing accounts, and completing reconciliation. Posted corrections affecting closed dates are rejected. Payments in a later open period against an older invoice are allowed. Reconciled postings and registered-equipment purchase records cannot be silently rewritten.

To restore from source, first close the app (including the tray), then run:

```sh
python run.py --restore "path/to/backwoods-accounting-backup.sqlite3"
```

The existing database is preserved before restoration. A process lock prevents restoration over a running company. Restored login sessions are invalidated.

## Development and verification

Python 3.12+ is the only backend runtime dependency. Node is needed to package the desktop application and to validate the copied source-app scripts. Each cloud task already has an isolated checkout; use the existing checkout and do not create a Git worktree unless explicitly requested.

```sh
python -m unittest discover -s tests -v
python run.py --data-dir .data --no-browser
```

For browser smoke testing, use a disposable, empty data directory and installed Playwright/Chromium. Test data must never be entered into your real company database.

```sh
python scripts/browser_smoke.py
```

Build connected copies from the supplied versions:

```sh
python scripts/build_connected_apps.py --main-dir PATH_TO_EXTRACTED_MAIN_8_2 --vendor-asar PATH_TO_VENDOR_4_1_ASAR --out NEW_OUTPUT_DIRECTORY
```

Build the Windows installer with the checked-in desktop configuration and a checksum-verified `cpython-3.12.15-windows-x86_64-none` runtime placed at `.build-resources/python`. The installer build includes only application sources, web assets and that runtime; no company data or payroll credentials are included.

### Build it yourself on Windows

1. Download this repository as a ZIP and **extract the whole folder**.
2. Install **Node.js 22 or later** and **Python 3.12 or later** (including the Python launcher).
3. Double-click `BUILD-INSTALLER-WINDOWS.cmd` in the extracted folder.
4. It installs pinned build tools into isolated folders, downloads the verified portable runtime, runs the tests, and invokes the native Windows installer builder.
5. The output is `dist\windows\Backwoods-Business-Accounting-Setup-1.0.2.exe`.

The build needs Internet access and about 2 GB of free disk space. It does not need payroll credentials and does not publish anything. The installed app includes its runtime, so people installing the finished EXE do not need Python or Node.js. This Windows batch workflow has been reviewed but has not been executed on a Windows machine in this cloud session; failures remain visible in its command window.

The runtime-copy step uses Windows Robocopy, including support for long paths, and treats its documented success codes (0–7) correctly. If an older copy of the build script stops with an XCopy “File creation error,” replace `BUILD-INSTALLER-WINDOWS.cmd` with the current version in this repository and run it again in the same folder. The previously downloaded runtime and build environment are reused.

If `npm ci` says the lockfile is missing, make sure you extracted the **entire ZIP**. Running the CMD from inside a ZIP causes Windows to put only that file into a temporary directory; the required `desktop/package-lock.json` and application folders are then absent. The build script now checks the full project before installing tools. Do not generate a replacement lockfile to work around incomplete extraction.

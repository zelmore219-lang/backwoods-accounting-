# Connected updates for both source apps

This folder contains complete installer-ready connected app copies, not just replacement ASAR files.

| App | Uploaded base | Connected edition | Desktop shortcut |
| --- | --- | --- | --- |
| Main retail app | 8.2.0 | 8.2.1 | Backwoods Brew Connected |
| Vendor / wholesale app | 4.1.0 | 4.1.1 | Backwoods Vendor Ordering Connected |

The versions are based on the packages supplied for this task. Compatibility with other installed source versions has not been established.

## Build the Windows updates

Extract the complete repository ZIP. Install Node.js 22+, then double-click `BUILD-APP-UPDATES-WINDOWS.cmd` in the repository root. Python is not required for these two source-app installers; their prepared renderer assets are included.

The outputs are:

- `dist\source-app-updates\main\Backwoods-Brew-Connected-Setup-8.2.1.exe`
- `dist\source-app-updates\vendor\Backwoods-Vendor-Ordering-Connected-Setup-4.1.1.exe`

## First launch and existing records

1. Export backups from both original apps. Do not uninstall or delete their profiles.
2. Close the original main and vendor apps before launching a connected edition.
3. Install the connected editions. Their app identities, shortcuts and local profiles are separate from the original installations.
4. On the first connected launch, the app copies the detected previous local profile **before** Chromium opens its new profile. It does not modify or delete the original profile. Cache/lock files are omitted; business storage, offline queues and authentication state are retained in the copy where supported.
5. If more than one plausible previous profile exists, startup stops for an explicit source selection; it does not choose one silently. Advanced users can set `BACKWOODS_SOURCE_PROFILE` to the intended source folder before launching.
6. If no previous profile is found, a visible message explains that the connected edition starts fresh. Sign in to the normal account or restore a backup using the source app before enabling transfers.
7. Check your customers, inventory, transactions and balances against the original backups before making live entries.

The connected edition is the app to use for future entries. The original profile is a preserved pre-migration copy, not a second automatically synchronized local profile. Do not keep entering records in both editions. Existing Firebase synchronization continues under the source app's own rules; the connector itself does not write to Firebase.

## Feed the one company ledger

Open Business Accounting on the **same Windows user and computer**. In each connected source app, sign in as owner and enable **Business Accounting connection → Send to Business Accounting** in the lower-left corner.

The main app retains its accounting screens. It sends a copy of its own ledger and supporting records. Vendor Ordering sends invoices, payments, approved credits, purchase receipts and captured inventory costs. The receiver validates and deduplicates them into the same company ledger.

Test a retail sale and a delivered wholesale invoice first. Draft wholesale orders are not revenue. Review the App connections status, control totals and any cost warnings. Repeating an unchanged snapshot must not duplicate postings.

For a fully isolated test, use a separate Windows user for **all three apps**. `BACKWOODS_TEST_DATA_DIR` isolates a source profile only; it does not by itself isolate the receiving Business Accounting database.

Windows installation and real profile migration still require testing on the intended PC. The cloud checks use disposable fixtures, syntax checks, archive integrity verification and transfer tests; they do not establish compatibility with every existing installation.

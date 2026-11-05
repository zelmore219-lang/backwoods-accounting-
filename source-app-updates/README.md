# Connected updates for both source apps

This folder contains complete installer-ready connected app copies, not just replacement ASAR files.

| App | Uploaded base | Connected edition | Desktop shortcut |
| --- | --- | --- | --- |
| Main retail app | 8.2.0 | 8.2.4 | Backwoods Brew Connected |
| Vendor / wholesale app | 4.1.0 | 4.1.4 | Backwoods Vendor Ordering Connected |

The versions are based on the packages supplied for this task. Compatibility with other installed source versions has not been established.

## Build the Windows updates

Extract the complete repository ZIP. Install Node.js 22+, then double-click `BUILD-APP-UPDATES-WINDOWS.cmd` in the repository root. Python is not required for these two source-app installers; their prepared renderer assets are included.

The outputs are:

- `dist\source-app-updates\main\Backwoods-Brew-Connected-Setup-8.2.4.exe`
- `dist\source-app-updates\vendor\Backwoods-Vendor-Ordering-Connected-Setup-4.1.4.exe`

## First launch and existing records

1. Export backups from both original apps. Do not uninstall or delete their profiles.
2. Close the original main and vendor apps before launching a connected edition.
3. Install the connected editions. Their app identities, shortcuts and local profiles are separate from the original installations.
4. On the first connected launch, the app copies the detected previous local profile **before** Chromium opens its new profile. It does not modify or delete the original profile. Cache/lock files are omitted; business storage, offline queues and authentication state are retained in the copy where supported.
5. If more than one plausible previous profile exists, startup stops for an explicit source selection; it does not choose one silently. Advanced users can set `BACKWOODS_SOURCE_PROFILE` to the intended source folder before launching.
6. If no previous profile is found, a visible message explains that the connected edition starts fresh. Sign in to the normal account or restore a backup using the source app before enabling transfers.
7. Check your customers, inventory, transactions and balances against the original backups before making live entries.

The connected edition is the app to use for future entries. The original profile is a preserved pre-migration copy, not a second automatically synchronized local profile. Do not keep entering records in both editions. Existing Firebase synchronization continues under the source app's own rules; the new accounting connector writes only private accounting snapshots, never rewrites source collections.

## Feed the one company ledger

After the one-time [Firebase company setup](../firebase/SETUP.md), open each connected source app and sign in as the Firebase owner. Accounting copies send automatically to that owner's private namespace. The accounting service imports retail and wholesale records into the same ledger while running. No transfer link or opt-in button is required.

The main app retains its own accounting and exports its ledger/supporting records. Vendor exports invoices, payments, approved credits, receipts and captured costs after its source sync finishes. Windows also retains an automatic local-file feed under the same Windows user. Both routes use the existing receiver's import IDs and validation. Cloud use requires the reviewed Firebase rules once. The full accounting engine runs in the installed app and shares its ledger through Firestore; no external host or Blaze upgrade is needed. Live rules have not been published here.

Test a retail sale and a delivered wholesale invoice first. Draft wholesale orders are not revenue. Review the App connections status, control totals and any cost warnings. Repeating an unchanged snapshot must not duplicate postings.

For a fully isolated test, use a separate Windows user for **all three apps**. `BACKWOODS_TEST_DATA_DIR` isolates a source profile only; it does not by itself isolate the receiving Business Accounting database.

Windows installation and real profile migration still require testing on the intended PC. The cloud checks use disposable fixtures, syntax checks, archive integrity verification and transfer tests; they do not establish compatibility with every existing installation.

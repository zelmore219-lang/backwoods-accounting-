# All three Android apps — automatic accounting test build

| App | Version | Android application ID |
| --- | --- | --- |
| Backwoods Brew Connected | 8.2.2 | `com.backwoodsbrew.main.connected` |
| Backwoods Vendor Connected | 4.1.2 | `com.backwoodsbrew.vendor.connected` |
| Backwoods Business Accounting | 1.0.1 | `com.backwoodsbrew.accounting` |

Main and vendor keep their supplied compiled apps and Firebase behavior, and now automatically send authenticated accounting snapshots while the owner is signed in and the app is open. Accounting has a native Firebase email/password sign-in and company-service discovery screen. Users do not enter a server URL. Source staff roles do not gain access to consolidated accounting or payroll.

**One-time administrator setup is still required:** merge/review the Firestore rules, link the Firebase owner to the existing ledger, and deploy a persistent HTTPS company accounting service. See [Firebase setup](../firebase/SETUP.md) and [shared hosting](SHARED-ACCOUNTING.md). Missing deployment produces a clear setup error; these APKs cannot deploy a server merely by being installed. Live company sync/rules have not been verified.

Download [all APKs and Windows installers](https://github.com/zelmore219-lang/backwoods-accounting-/releases/tag/automatic-accounting-test-1). They are test builds, not production-certified releases. Original APK identities/signing keys were not provided; connected source apps install alongside originals. They cannot read another app's private device data. Sync/export and verify records before changing apps, retaining originals and backups.

## Rebuild on Windows

Install Node.js 22+ and Android Studio with Java 21, Android API 35 and Build Tools 35.0.0. Extract the complete repository and run `BUILD-APK-WINDOWS.cmd`. It produces all three debug-signed test APKs. Main/vendor use pinned Capacitor 7 dependencies; the accounting client is a native Gradle project with company-origin tests.

Use the original signing key to update an installed APK; a different debug/release key cannot update it in place. Production releases need your own securely retained release key. No private signing keys, local SDK paths or business databases are committed. Back up records before any signing-identity change or uninstall.

APK signatures/versions/hashes are verified. Physical Android camera, location, printing, login and live Firebase reconciliation still need testing. The native accounting Print button opens Android's printer/PDF service; physical printing requires an Android print service.

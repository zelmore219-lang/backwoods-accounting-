# All three Android apps — Firebase Spark

| App | Version | Android application ID |
| --- | --- | --- |
| Backwoods Brew Connected | 8.2.3 | `com.backwoodsbrew.main.connected` |
| Backwoods Vendor Connected | 4.1.3 | `com.backwoodsbrew.vendor.connected` |
| Backwoods Business Accounting | 1.0.2 | `com.backwoodsbrew.accounting` |

Main/vendor keep the supplied compiled apps and add automatic authenticated financial copies. Accounting now bundles the **full Python accounting engine**, its professional web interface, SQLite and direct Firestore shared-ledger sync. It is no longer a thin client for an external accounting server. No transfer URL, Firebase Functions, Hosting provider or Blaze upgrade is required. [One-time Spark rules/setup](../firebase/SETUP.md) is still necessary; it has not been published to the live project by this build.

Accounting targets Android 7+ (API 24), ARM64 and x86-64. Its private UI runs only on device loopback; other apps do not receive its bootstrap secret. Firebase/provider traffic remains verified HTTPS. Credentials use Android Keystore; cloud auto-backup is disabled. Native Print opens Android printing/Save as PDF, and receipt/import files use the system picker.

## Rebuild

Install Node.js 22+, Python 3.12, Android Studio with Java 21, Android API 35 and Build Tools 35.0.0. Extract the whole repository and run `BUILD-APK-WINDOWS.cmd`. Accounting's pinned Chaquopy 16.1.0 toolchain packages Python 3.12; phone users do not install Python. `scripts/prepare_accounting_android.py` copies only program files, not business databases or credentials.

[All downloads](https://github.com/zelmore219-lang/backwoods-accounting-/releases/tag/firebase-spark-test-1) include test APKs and Windows installers. APK signatures/package versions/hashes are checked. Physical Android camera/location, actual printing, live Firebase rules and business reconciliation require testing. These are debug-signed review builds, not production-signed releases. Original Android signing identities were not supplied, so connected source editions remain separate from unknown older APKs. Preserve originals and backups; changing signing keys requires a deliberate migration.

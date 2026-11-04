# Backwoods Android downloads

Installable, debug-signed **test APKs** for Android 6+. Download a file on your Android device, open it, and allow installation from your browser when Android asks. Test with non-production records first.

| App | Download | Required setup |
| --- | --- | --- |
| Main retail, 8.2.1 | [Backwoods Brew APK](https://github.com/zelmore219-lang/backwoods-accounting-/raw/refs/heads/main/android-apks/Backwoods-Brew-Connected-8.2.1-test.apk) | Existing main-app login and Firebase access |
| Vendor wholesale, 4.1.1 | [Backwoods Vendor APK](https://github.com/zelmore219-lang/backwoods-accounting-/raw/refs/heads/main/android-apks/Backwoods-Vendor-Connected-4.1.1-test.apk) | Existing vendor-app login and Firebase access |
| Business Accounting, 1.0.0 | [Business Accounting APK](https://github.com/zelmore219-lang/backwoods-accounting-/raw/refs/heads/main/android-apks/Backwoods-Business-Accounting-1.0.0-test.apk) | Shared HTTPS accounting service and accounting login; **service not deployed** |

The source editions install alongside older Android apps. Original signing keys and application identities were not supplied; these cannot access another app's private device storage. Sync/export old records and keep backups and old apps until records and balances have been checked.

Current transfer: source APK → existing Firebase sync → connected Windows source app → local file feed → Business Accounting. This needs the Windows apps running and depends on existing Firebase rules and source sync. It has not been tested against live company data. **Direct Firebase accounting integration is unfinished.** The accounting APK needs a shared server; entering a Firebase console/project address will not set one up.

All three APKs passed signature verification and package/version inspection. [SHA256SUMS.txt](SHA256SUMS.txt) and [manifest.json](manifest.json) record hashes, sizes, application IDs and signing-certificate fingerprints. Login, camera, location, physical printing and live syncing still require device testing.

Production distribution requires your own securely retained release signing key. Rebuilding with a different debug key cannot update these APKs in place; preserve/export records before changing signing identities. No private signing key is committed.

See [Android projects](../android-apps/README.md), [shared accounting setup](../android-apps/SHARED-ACCOUNTING.md), and [Windows source updates](../source-app-updates/README.md).

# Revised Android downloads

These installable **debug-signed test APKs** replace the earlier manual-connection builds. Android 6+ is required.

- [Main retail 8.2.2 APK](https://github.com/zelmore219-lang/backwoods-accounting-/releases/download/automatic-accounting-test-1/Backwoods-Brew-Connected-8.2.2-test.apk)
- [Vendor wholesale 4.1.2 APK](https://github.com/zelmore219-lang/backwoods-accounting-/releases/download/automatic-accounting-test-1/Backwoods-Vendor-Connected-4.1.2-test.apk)
- [Business Accounting 1.0.1 APK](https://github.com/zelmore219-lang/backwoods-accounting-/releases/download/automatic-accounting-test-1/Backwoods-Business-Accounting-1.0.1-test.apk)
- [Windows installers and all downloads](https://github.com/zelmore219-lang/backwoods-accounting-/releases/tag/automatic-accounting-test-1)

Sign in normally to the source apps as the Firebase owner. Their accounting copies send automatically while the apps are open. Business Accounting uses Firebase sign-in and company discovery; **no transfer URL entry** is required.

**Not activated yet:** one-time Firestore rules, company ledger linking and shared HTTPS service deployment. See [setup](../firebase/SETUP.md). Installing the APKs alone does not deploy those pieces. Cloud tests used controlled Firebase responses; no live company or physical-device test has been completed.

[SHA256SUMS.txt](SHA256SUMS.txt) and [manifest.json](manifest.json) record each built artifact's hash, size, version and signing certificate. Keep old apps and backups until records match. Source editions have separate Android identities from unknown originals. Different signing keys cannot update these test APKs in place; never uninstall without verifying backups/sync. No private signing key is committed.

# Firebase Spark app downloads

- [Main retail 8.2.4 APK](https://github.com/zelmore219-lang/backwoods-accounting-/raw/refs/heads/main/android-apks/Backwoods-Brew-Connected-8.2.4-test.apk)
- [Vendor wholesale 4.1.4 APK](https://github.com/zelmore219-lang/backwoods-accounting-/raw/refs/heads/main/android-apks/Backwoods-Vendor-Connected-4.1.4-test.apk)
- [Business Accounting 1.0.2 APK](https://github.com/zelmore219-lang/backwoods-accounting-/raw/refs/heads/main/android-apks/Backwoods-Business-Accounting-1.0.2-test.apk)
- [Windows installers and release checksums](https://github.com/zelmore219-lang/backwoods-accounting-/releases/tag/firebase-spark-test-2)

The accounting APK now contains the full engine and shares books through Firestore. It does not ask for a server/transfer URL. No host or Blaze upgrade is required. Publish the reviewed [merged Firebase rules](../firebase/firestore.rules) once, then follow [Spark setup](../firebase/SETUP.md). Live company operation has not been verified by this build.

Accounting requires Android 7+ with ARM64/x86-64. Main/vendor target Android 6+. These are debug-signed test builds; the signing identity matches the earlier connected test APKs, allowing an in-place update of those matching identities. Unknown original APKs use separate profiles. Keep originals and backups until records and source totals match. Never uninstall to resolve a signing conflict without first preserving data.

[manifest.json](manifest.json) and [SHA256SUMS.txt](SHA256SUMS.txt) record the actual built files. Physical-device testing, live Firebase reconciliation and real printing remain necessary.

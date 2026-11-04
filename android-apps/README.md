# All three Android apps

Capacitor 7 projects for **Main retail** and **Vendor Ordering** retain the supplied compiled apps and native filesystem, sharing, browser, app and geolocation plugins. Camera permission supports existing camera/barcode workflows. **Business Accounting** is a native Java Android HTTPS client with company connection setup, web login, printing, file picking and downloads.

| APK | Version | Android application ID |
| --- | --- | --- |
| Backwoods Brew Connected | 8.2.1 | `com.backwoodsbrew.main.connected` |
| Backwoods Vendor Connected | 4.1.1 | `com.backwoodsbrew.vendor.connected` |
| Backwoods Business Accounting | 1.0.0 | `com.backwoodsbrew.accounting` |

These IDs are deliberately separate from unknown existing APK identities. They install alongside existing apps and cannot read another Android app's private local data. Sync/export existing records and sign in with the usual source-app account. No prior Android signing keystore or original Android project was supplied, so these are not claimed to be in-place upgrades of an existing APK.

## How the accounting transfer works on Android

The Windows file connector is not used inside Android's sandbox. The mobile app keeps the source app's existing Firebase synchronization. A connected desktop instance signed into the same source account must receive those cloud records, then forwards its validated snapshot to Business Accounting on that Windows computer/user.

This relay depends on the original Firebase authentication, data model, security rules and existing sync behavior. It has not been verified against live company credentials. Records that are device-local and not part of the original source sync do not become cross-device automatically. No new public or unauthenticated accounting API is enabled by these APKs.

The Business Accounting APK asks for the shared server's HTTPS origin. No service is preconfigured or deployed. It cannot read a PC's loopback-only service from the phone. See [shared service setup and remaining Firebase work](SHARED-ACCOUNTING.md). Direct Firebase accounting integration is unfinished.

## Build or install

Installable debug-signed test APKs are under `android-apks` when built. Use them on a test device/profile first. Device login, live Firebase transfer, barcode/camera, location and physical printing still require actual device tests. A compiled APK and valid signature do not establish those behaviors.

For a Windows rebuild, install Node.js 22+ and Android Studio with Java 21, Android 15 / API 35 and Android Build Tools 35.0.0. Extract the entire repository and run `BUILD-APK-WINDOWS.cmd` to build all three APKs. You can also open each app's `android` folder in Android Studio and build it there. The accounting client has no npm dependency; its Gradle project includes origin-boundary unit tests.

For a production release, use Android Studio's Generate Signed Bundle / APK workflow and your own securely backed-up release keystore. Do not commit signing keys, passwords, `local.properties`, service-account keys or private company data. Updating an older APK requires its original application ID and signing key, which cannot be reconstructed from the supplied web/Electron packages.

The Gradle distribution is pinned to 8.11.1 with Google's generated project settings and its official SHA-256 checksum. Android system TLS verification and cleartext defaults remain in place; no certificate checks are disabled. Android cloud auto-backup is disabled for the new app profiles. Original in-app backup/export remains available where supported.

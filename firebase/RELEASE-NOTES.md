Retail and wholesale accounting copies send automatically through authenticated Firebase while the owner app is open. Business Accounting signs in to Firebase and discovers its company service; users do not enter transfer URLs. Original source accounting remains intact.

Downloads include three Android test APKs, three Windows installers, SHA-256 hashes, merged Firestore rules and setup instructions. Versions: Main 8.2.2, Vendor 4.1.2, Business Accounting 1.0.1.

**Required before live syncing:** publish the reviewed merged Firebase rules, link the Firebase owner to the existing ledger, and configure a persistent HTTPS accounting service. These have not been deployed against the company project by this build. APK installation does not deploy them. See Firebase-Accounting-Setup.md.

The merged rules retain the owner-supplied retail/vendor permission baseline and add private active-owner accounting paths. They have not yet been tested in the live Firebase project/emulator. The accounting sender runs in an open owner app; it is not a server-side trigger watching all staff writes.

Validation: 73 Python tests, 12 source/desktop Node tests, four Firebase transport Node tests and three Android origin unit tests in the cloud build. Firebase tests use controlled responses. APK signatures, package versions and Windows package contents verified. Android uses the same debug signing identity as the prior test builds. Physical Android/Windows behavior and live company reconciliation remain unverified. APKs are debug signed; Windows installers are unsigned. Back up and retain existing apps/data before testing.

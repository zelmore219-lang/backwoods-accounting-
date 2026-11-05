# Shared accounting on Firebase Spark

The earlier server-discovery design has been replaced. The accounting engine now runs inside each installed Windows app/Android APK, and Firestore holds the shared authoritative ledger. No external host, hosted URL, always-on PC, Functions deployment or Blaze upgrade is required.

Follow [Firebase Spark setup](../firebase/SETUP.md). Publish the reviewed merged rules once, then sign into all three apps with the same Firebase owner login. A device joining an existing company retrieves its books. New users create the Business Accounting owner/password once for that ledger. Automatic imports and shared postings run while the apps are open and online; Android background suspension can delay sync.

Windows retains its local-file connector as an automatic same-PC fallback, with the same import IDs. The normal shared route is Firebase. Do not follow the older `--public-origin`, reverse-proxy or `BACKWOODS_ACCOUNTING_SERVER_URL` setup for these Spark builds.

Spark quota and supported database-size limits apply. Shared financial writes are acknowledged after a complete Firestore generation is confirmed. Source records, business-entered transactions and source-record revisions stay in the books. Login sessions and encrypted provider/Firebase credentials remain device-private.

# Firestore integration — implementation gate

**Not deployed or connected.** Existing wholesale records remain device-local. Do not turn on a cloud writer until the current Firestore rules, authentication claims, and central accounting document structure are reviewed.

## Proposed division-scoped collections
- `wholesaleCustomers/{id}`: name, contact, address, terms, createdAt
- `wholesaleProducts/{id}`: SKU, sellPriceCents, onHand, reserved, avgCostCents
- `wholesaleMaterials/{id}`: SKU, onHand, avgCostCents
- `wholesaleOrders/{id}`: customerId, lines, status, totalCents, paidCents, version
- `wholesaleBatches/{id}`: inputs, outputs, costs, operator, timestamp
- `wholesaleMovements/{id}`: sourceId, itemId, signedQuantity, costCents
- `accountingEntries/{id}`: immutable balanced posting, division=wholesale, sourceId

## Critical implementation rules
1. Authenticate each employee and authorize their wholesale role on the server. Never trust a client-selected role.
2. Use Firestore transactions or trusted backend operations for order transitions, stock reservations, delivery, and accounting postings.
3. Use deterministic posting IDs to prevent duplicate delivery/payment journal entries on retry.
4. Reject unbalanced entries and invalid inventory movements server-side.
5. Use cents (integers) for financial amounts and track audit timestamps.
6. Read existing accounting schema before writing wholesale entries; do not create a second company ledger.
7. Migrate local wholesale data only after review, deduplication and a backup.

## Required before activation
- Current Firestore security rules (redact sensitive identifiers).
- Sanitized sample documents from the existing central accounting collection and employee role collection.
- Confirmation of Firebase Auth login method and current access model.

Do not send service-account private keys or passwords.

# Phase 7 security review — DO NOT DEPLOY AS-IS

Your supplied Cloud Firestore rules currently permit any active vendor user to create/update `vendorOrders` and `vendorCustomers`, regardless of job role. A client-side role check is **not** a security boundary. Before allowing production cloud writes, revise and test server-enforced rules for the order lifecycle and immutable financial fields.

Suggested role mapping:
- Sales: create draft/submitted orders, cannot change packed/delivered orders or financial totals after submission.
- Warehouse/packer: packing records and status transition only.
- Driver: delivery confirmation only.
- Accountant: invoice/payment creation and reconciliation only.
- Manager: administrative overrides with audit logs.

Firestore security rules cannot safely validate complex multi-document accounting and inventory transitions alone. Use a trusted server (Cloud Functions) for authoritative totals, product pricing, idempotent posting, and stock consumption. Do not activate automatic ledger posting from client code.

`appData/main` is a shared snapshot with broad employee write permissions. Avoid adding wholesale financial postings to that document until its writer and concurrency model are redesigned.

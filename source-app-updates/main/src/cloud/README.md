# Wholesale Firestore workflow module — integration source

This is **actual Firestore SDK source** for customer/product reads, order submission, packing, and delivery. It is NOT yet wired to the recovered compiled Electron UI, and it does not change live Firebase data unless a developer explicitly imports/calls it from an authenticated app.

Requirements: `firebase` npm dependency, initialized Firestore instance, Firebase Auth user, deployed rules permitting the respective role and document fields. Functions use Firestore transactions to reject duplicate IDs and invalid state transitions. They do not deduct stock or post central accounting because the source of truth for stock/cost and the ledger schema have not yet been established. The existing Firestore rules currently permit broad vendorOrders writes; enforce role/state/field restrictions and test in the emulator before production use.

Example: `await submitOrder(db, auth.currentUser, {orderId:'ord-1001', customerId:'cust-1', items:[{productId:'coffee-12oz',qty:2,unitPriceCents:1499}]})`.

**Security warning:** These functions are not an authorization boundary. Firestore rules and/or a trusted backend must independently enforce the same invariants. Never deploy permissive catch-all rules. Do not import the module directly into the compiled 8.2.0 bundle without a proper build.

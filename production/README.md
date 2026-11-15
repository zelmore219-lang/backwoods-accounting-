# Backwoods Production — connected edition

The recovered Production app now connects to the existing Employee/Employer owner service, Vendor Ordering and Business Accounting. Existing recipes, lots, event IDs and local database are preserved.

For the installed Windows app, extract the entire connection update ZIP, close Production and run **UPDATE-PRODUCTION.cmd**. The update locates the normal installed Application folder automatically; it asks for a folder only for a custom location. The update backs up the old application files and copies the new ones; it does not replace the database, executable or runtime. The included Windows cryptography dependencies match the supplied 64-bit Python 3.14 runtime.

After installing the matching Employee, Vendor and Accounting updates and reviewed Firestore stock protections, open **Manager tools → Connections**. Verify the actual Employee owner, choose the existing company ledger, review opening balances and match each finished SKU/package size to Vendor. Production access is then managed in Employee/Employer. Released, unreserved packages transfer to Vendor automatically and cannot be sold locally a second time. Business Accounting receives the production journals and original supporting records.

Automatic transfers require Production signed in as a manager, Employee Owner service online, and Business Accounting open. Connections distinguishes a saved transfer from an actual Vendor receipt and a sent accounting snapshot from its subsequent import status.

The first connection requires reconciliation of existing opening stock and payables against the company books. No historical sale, bank payment or tax amount is inferred. The detailed setup, accounting mappings, retries, supported limits and verification boundaries are in **PRODUCTION-CONNECTIONS.md** beside the update package.

To run source directly, install Python 3.12+, install `requirements.txt`, run `python server.py` and open http://127.0.0.1:8080. By default records remain in `backwoods.db`; the retained desktop executable supplies its existing database path. The server continues to listen only on loopback by default. No public host, Firebase billing upgrade or new employee password database is required.

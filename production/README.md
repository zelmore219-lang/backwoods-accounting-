# Backwoods Production

Use the existing Production app as before: receive materials, make the batch, package it, inspect it and release it for sale. The background connection then removes those packages from Production's available stock and receives the exact SKU/lot/count into Vendor. Vendor tracks available inventory and subsequent sales. Production keeps the completed batch history; Business Accounting receives costs, supplier records and journals; Employee/Employer controls access.

The existing layout, navigation, production forms and Windows launcher are retained. The existing Connections and Integration queue pages report recording/transfer status; they are not a new setup workflow.

For Windows, close Production, extract the entire update ZIP and run **UPDATE-PRODUCTION.cmd**. It finds the normal existing installation, backs up application files and preserves the database, launcher and Python runtime. After installing the matching Employee, Vendor and Accounting updates and reviewing the Firebase stock protections, reopen Production and run **CONNECT-EXISTING-APPS.cmd** from the extracted folder once to link your existing company. Opening balances and existing Vendor stock must be reconciled before activation.

New released lots match a unique exact Vendor SKU automatically. Unfinished batches, bulk stock, held stock, expired lots and mismatched package sizes do not transfer. Lost responses retry using retained transfer IDs, preventing duplicate stock. The setup command can also review opening stock or an unmapped SKU. Keep Production signed in as a manager, the Employee Owner service online and Business Accounting open for automatic recording.

See **PRODUCTION-CONNECTIONS.md** beside the update for account mappings, setup, retries and test evidence. No live company data or rules are changed by downloading the update.

To run the source, install Python 3.12+, install `requirements.txt`, run `python server.py` and open http://127.0.0.1:8080. Existing records remain in `backwoods.db` or the database path supplied by the retained desktop launcher.

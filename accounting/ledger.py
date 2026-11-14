"""Transactional, integer-cent company ledger. No third-party runtime dependencies."""
import base64
import hashlib
import json
import re
import sqlite3
import uuid
from contextvars import ContextVar
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


class AccountingError(ValueError):
    pass

ACTOR=ContextVar('accounting_actor',default='system / automatic feed')


def now():
    return datetime.now(timezone.utc).isoformat()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def cents(value):
    if isinstance(value, bool) or value is None:
        raise AccountingError("A monetary amount must be a number")
    try:
        n = Decimal(str(value))
        if not n.is_finite() or abs(n) > Decimal("1000000000"):
            raise AccountingError("Amount outside supported range")
        return int((n * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise AccountingError("Invalid monetary amount") from exc


def day(value):
    try:
        value = str(value)[:10]
        return date.fromisoformat(value).isoformat()
    except (ValueError, TypeError) as exc:
        raise AccountingError("A valid transaction date (YYYY-MM-DD) is required") from exc


ACCOUNTS = [
    ("1010", "Cash on Hand", "asset"), ("1020", "Bank Account", "asset"),
    ("1030", "Undeposited Funds", "asset"), ("1100", "Accounts Receivable", "asset"),
    ("1200", "Inventory Asset", "asset"), ("1210", "Green Coffee Inventory", "asset"),
    ("1220", "Roasted Coffee Inventory", "asset"), ("1500", "Fixed Assets", "asset"),
    ("1590", "Accumulated Depreciation", "asset"), ("2000", "Accounts Payable", "liability"),
    ("2100", "Sales Tax Payable", "liability"), ("2151", "Federal Withholding Payable", "liability"),
    ("2152", "State Withholding Payable", "liability"), ("2153", "Social Security Payable", "liability"),
    ("2154", "Medicare Payable", "liability"), ("2155", "Deductions Payable", "liability"),
    ("2156", "Unemployment Payable", "liability"), ("2500", "Loans Payable", "liability"),
    ("2200", "Net Wages Payable", "liability"),
    ("2160", "Payroll Provider Tax Clearing", "liability"), ("2250", "Payroll Provider Net Pay Clearing", "liability"),
    ("2260", "Tips Payable", "liability"),
    ("3000", "Owner Equity", "equity"), ("3100", "Opening Balance Equity", "equity"),
    ("4000", "Sales Revenue", "income"), ("4010", "Discounts Given", "income"),
    ("4020", "Sales Returns and Credits", "income"), ("5000", "Cost of Goods Sold", "expense"),
    ("4800", "Gain on Asset Disposal", "income"), ("6200", "Loss on Asset Disposal", "expense"),
    ("5100", "Operating Expenses", "expense"), ("5200", "Wages", "expense"),
    ("5210", "Employer Payroll Taxes", "expense"), ("5900", "Rounding Adjustment", "expense"),
    ("5220", "Employer Benefits", "expense"),
    ("5300", "Rent", "expense"), ("5400", "Utilities", "expense"),
    ("5500", "Advertising", "expense"), ("5600", "Repairs and Maintenance", "expense"),
    ("5700", "Insurance", "expense"), ("5800", "Bank and Merchant Fees", "expense"),
    ("6010", "Roast Loss / Waste", "expense"), ("6100", "Depreciation Expense", "expense"),
]

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS accounts(code TEXT PRIMARY KEY,name TEXT NOT NULL,type TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS batches(id TEXT PRIMARY KEY,source TEXT NOT NULL,created_at TEXT NOT NULL,
 snapshot_at TEXT,filename TEXT NOT NULL,payload TEXT NOT NULL,added INTEGER,changed INTEGER,duplicates INTEGER);
CREATE TABLE IF NOT EXISTS documents(source TEXT NOT NULL,source_id TEXT NOT NULL,hash TEXT NOT NULL,
 revision INTEGER NOT NULL,date TEXT NOT NULL,kind TEXT NOT NULL,reference TEXT NOT NULL,
 party TEXT NOT NULL,amount INTEGER NOT NULL,balance INTEGER NOT NULL,payload TEXT NOT NULL,
 batch_id TEXT NOT NULL, PRIMARY KEY(source,source_id),FOREIGN KEY(batch_id) REFERENCES batches(id));
CREATE TABLE IF NOT EXISTS entries(id INTEGER PRIMARY KEY,source TEXT NOT NULL,source_id TEXT NOT NULL,
 revision INTEGER NOT NULL,date TEXT NOT NULL,memo TEXT NOT NULL,batch_id TEXT NOT NULL,
 reversal_of INTEGER REFERENCES entries(id),FOREIGN KEY(batch_id) REFERENCES batches(id));
CREATE TABLE IF NOT EXISTS lines(id INTEGER PRIMARY KEY,entry_id INTEGER NOT NULL REFERENCES entries(id),
 account TEXT NOT NULL REFERENCES accounts(code),debit INTEGER NOT NULL CHECK(debit>=0),
 credit INTEGER NOT NULL CHECK(credit>=0),CHECK(NOT(debit>0 AND credit>0)));
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,at TEXT NOT NULL,action TEXT NOT NULL,detail TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS processed_feeds(source TEXT NOT NULL,fingerprint TEXT NOT NULL,PRIMARY KEY(source,fingerprint));
CREATE TABLE IF NOT EXISTS document_history(source TEXT NOT NULL,source_id TEXT NOT NULL,revision INTEGER NOT NULL,
 payload TEXT NOT NULL,batch_id TEXT NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(source,source_id,revision));
CREATE TABLE IF NOT EXISTS attachments(id TEXT PRIMARY KEY,source TEXT NOT NULL,source_id TEXT NOT NULL,
 name TEXT NOT NULL,mime TEXT NOT NULL,content BLOB NOT NULL,created_at TEXT NOT NULL,
 FOREIGN KEY(source,source_id) REFERENCES documents(source,source_id));
CREATE TABLE IF NOT EXISTS reconciliations(id TEXT PRIMARY KEY,account TEXT NOT NULL REFERENCES accounts(code),
 date TEXT NOT NULL,starting INTEGER NOT NULL,ending INTEGER NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS reconciliation_lines(line_id INTEGER PRIMARY KEY REFERENCES lines(id),
 reconciliation_id TEXT NOT NULL REFERENCES reconciliations(id));
CREATE TABLE IF NOT EXISTS cost_overrides(source_id TEXT PRIMARY KEY,unit_cost TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS recipes(id TEXT PRIMARY KEY,name TEXT NOT NULL,payload TEXT NOT NULL,result TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS catalog(source TEXT NOT NULL,source_id TEXT NOT NULL,payload TEXT NOT NULL,updated_at TEXT NOT NULL,PRIMARY KEY(source,source_id));
CREATE TABLE IF NOT EXISTS item_plans(source TEXT NOT NULL,source_id TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(source,source_id));
CREATE TABLE IF NOT EXISTS pricing(id TEXT PRIMARY KEY,name TEXT NOT NULL,payload TEXT NOT NULL,result TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS assets(id TEXT PRIMARY KEY,payload TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS employees(id TEXT PRIMARY KEY,name TEXT NOT NULL,payload TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS entries_date ON entries(date);
CREATE INDEX IF NOT EXISTS entries_source ON entries(source,source_id);
"""


class Ledger:
    def __init__(self, path):
        self.path = str(path)
        self.db = sqlite3.connect(self.path, timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        from .auth import SCHEMA as AUTH_SCHEMA
        self.db.executescript(AUTH_SCHEMA)
        from .payroll_provider import SCHEMA as PROVIDER_SCHEMA
        self.db.executescript(PROVIDER_SCHEMA)
        from .tax_watch import SCHEMA as TAX_SCHEMA
        self.db.executescript(TAX_SCHEMA)
        self.db.executemany("INSERT OR IGNORE INTO accounts VALUES(?,?,?)", ACCOUNTS)
        self.db.execute("INSERT OR IGNORE INTO settings VALUES('company','Backwoods Brew')")
        self.db.execute("INSERT OR IGNORE INTO settings VALUES('schema_version','1')")
        self.db.commit()

    def close(self):
        self.db.close()

    def audit(self, action, detail):
        self.db.execute("INSERT INTO audit(at,action,detail) VALUES(?,?,?)", (now(), action, canonical({**detail,'actor':ACTOR.get()})))

    def settings(self):
        return dict(self.db.execute("SELECT key,value FROM settings"))

    def set_settings(self, values):
        with self.db:
            for k, v in values.items():
                if k not in {"company", "company_address", "company_phone", "closed_through"}:
                    raise AccountingError("Unknown setting")
                if k == "closed_through":
                    v = day(v)
                    if self.db.execute("SELECT 1 FROM documents WHERE kind='needs-cost' AND date<=?",(v,)).fetchone():
                        raise AccountingError('Resolve historical inventory costs before closing this period')
                    if v < self.settings().get(k, ""):
                        raise AccountingError("Closed periods cannot be reopened here")
                elif k=='company' and not str(v).strip():
                    raise AccountingError("Company name cannot be empty")
                self.db.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (k, str(v)[:200]))
            self.audit("settings", values)

    def account_code(self, value):
        m = re.match(r"^(\d{4,6})(?:\s.*)?$", str(value).strip())
        if not m:
            raise AccountingError(f"Account needs a chart code: {value}")
        return m.group(1)

    def validate(self, documents, account_rows=()):
        known = {r[0] for r in self.db.execute("SELECT code FROM accounts")}
        for a in account_rows:
            if a[2] not in {"asset", "liability", "equity", "income", "expense"}:
                raise AccountingError("Invalid account type")
            if not re.fullmatch(r"\d{4,6}", a[0]):
                raise AccountingError("Invalid account code")
            existing = self.db.execute("SELECT type FROM accounts WHERE code=?", (a[0],)).fetchone()
            if existing and existing[0] != a[2]:
                raise AccountingError(f"Account {a[0]} has a conflicting account type")
            known.add(a[0])
        ids = set()
        for doc in documents:
            sid = str(doc.get("id", "")).strip()
            if not sid or sid in ids:
                raise AccountingError(f"Missing or duplicate source record: {sid}")
            ids.add(sid)
            day(doc["date"])
            lines = doc["lines"]
            if not isinstance(lines, list):
                raise AccountingError("Journal lines must be a list")
            debit = credit = 0
            for line in lines:
                if line["account"] not in known:
                    raise AccountingError(f"Unknown account {line['account']}; add it to the chart first")
                d, c = line["debit"], line["credit"]
                if type(d) is not int or type(c) is not int or min(d, c) < 0 or max(d, c) > 100_000_000_000 or (d and c):
                    raise AccountingError(f"Invalid journal line in {sid}")
                debit += d
                credit += c
            if debit != credit:
                raise AccountingError(f"Unbalanced entry {sid}: debits {debit}, credits {credit}")
            if lines and not debit:
                raise AccountingError(f"Zero-value journal entry {sid}")

    def import_documents(self, source, documents, payload, filename="import.json", snapshot_at=None, accounts=(), preview=False, overrides=(), catalog=(), assets=()):
        if source not in {"main", "vendor", "manual", "provider", "employees"}:
            raise AccountingError("Unrecognized source app")
        self.validate(documents, accounts)
        if snapshot_at:
            try:
                stamp = datetime.fromisoformat(str(snapshot_at).replace("Z", "+00:00"))
                if stamp.tzinfo is None:
                    raise ValueError()
                snapshot_at = stamp.astimezone(timezone.utc).isoformat()
            except ValueError as exc:
                raise AccountingError("Export timestamp must include timezone") from exc
        # BEGIN IMMEDIATE serializes duplicate detection with commit, including concurrent feeds.
        self.db.execute("BEGIN IMMEDIATE")
        try:
            previous = self.db.execute("SELECT MAX(snapshot_at) FROM batches WHERE source=?", (source,)).fetchone()[0]
            if snapshot_at and previous and snapshot_at < previous:
                raise AccountingError("This backup is older than the last imported snapshot; use a current export")
            if snapshot_at and snapshot_at > datetime.now(timezone.utc).isoformat():
                from datetime import timedelta
                if datetime.fromisoformat(snapshot_at)>datetime.now(timezone.utc)+timedelta(minutes=5):
                    raise AccountingError('Export timestamp is in the future; correct the source computer clock')
            counts = {"added": 0, "changed": 0, "duplicates": 0, "records": len(documents)}
            if source=='employees':
                existing=[json.loads(row[0]) for row in self.db.execute("SELECT payload FROM documents WHERE source='employees'")]
                combined={doc['id']:doc for doc in existing}
                for doc in documents:
                    old=combined.get(doc['id'])
                    if old and (old['original']['company']['id']!=doc['original']['company']['id'] or old['original']['record']['employeeId']!=doc['original']['record']['employeeId']):
                        raise AccountingError('An existing Employee record ID belongs to another company or employee')
                combined.update({doc['id']:doc for doc in documents})
                companies={doc['original']['company']['id'] for doc in combined.values()}
                if len(companies)>1:raise AccountingError('Employee records belong to different companies. Use the correct separate Accounting company profile.')
                sheets=[doc['original']['record'] for doc in combined.values() if doc['kind']=='employee-timesheet']
                for index,sheet in enumerate(sheets):
                    if any(other['employeeId']==sheet['employeeId'] and other['start']<sheet['endExclusive'] and other['endExclusive']>sheet['start'] for other in sheets[index+1:]):
                        raise AccountingError('An approved Employee timesheet overlaps an already imported period. Review the original records before importing.')
            pending = []
            closed = self.settings().get("closed_through", "")
            for doc in documents:
                content = canonical(doc)
                digest = hashlib.sha256(content.encode()).hexdigest()
                old = self.db.execute("SELECT * FROM documents WHERE source=? AND source_id=?", (source, doc["id"])).fetchone()
                if old and old["hash"] == digest:
                    counts["duplicates"] += 1
                    continue
                old_payload=json.loads(old["payload"]) if old else None
                financial_change=not old or old_payload["lines"]!=doc["lines"] or old["date"]!=doc["date"]
                if financial_change and closed and (doc["date"] <= closed or (old and old["date"] <= closed)):
                    raise AccountingError(f"Record {doc['id']} affects a closed accounting period")
                if old and financial_change and self.db.execute("SELECT 1 FROM reconciliation_lines r JOIN lines l ON l.id=r.line_id JOIN entries e ON e.id=l.entry_id WHERE e.source=? AND e.source_id=?", (source, doc["id"])).fetchone():
                    raise AccountingError(f"Record {doc['id']} is reconciled; review a correcting journal instead")
                if old and financial_change:
                    for asset_row in self.db.execute('SELECT payload FROM assets'):
                        asset=json.loads(asset_row[0])
                        if asset.get('linkedSource')==source and asset.get('linkedId')==doc['id']:
                            raise AccountingError(f"Record {doc['id']} is linked to registered equipment; use a reviewed correcting entry")
                counts["changed" if old else "added"] += 1
                pending.append((doc, digest, old, financial_change))
            if preview:
                self.db.rollback()
                return counts
            batch = str(uuid.uuid4())
            stored=payload
            if isinstance(payload,dict) and payload.get('type')=='business-accounting-feed':
                data=payload.get('data',payload)
                # Preserve the financial record versions, not another entire
                # cumulative app backup for every sale. This bounds Spark usage
                # without discarding posting/reversal or source-record history.
                stored={'type':payload['type'],'schemaVersion':payload.get('schemaVersion',1),'app':payload.get('app',''),
                        'exportedAt':payload.get('exportedAt'),'storage':'financial-record-history-v1',
                        'snapshotSha256':hashlib.sha256(canonical(payload).encode()).hexdigest(),'records':len(documents),
                        'changedRecords':[doc['id'] for doc,_,_,_ in pending],
                        'data':{'generalLedger':[]} if 'generalLedger' in data else {}}
            self.db.execute("INSERT INTO batches VALUES(?,?,?,?,?,?,?,?,?)", (batch, source, now(), snapshot_at, str(filename)[:200], canonical(stored), counts["added"], counts["changed"], counts["duplicates"]))
            for account in accounts:
                self.db.execute("INSERT OR IGNORE INTO accounts VALUES(?,?,?)", account)
            for sid,cost in overrides:
                self.db.execute("INSERT OR REPLACE INTO cost_overrides VALUES(?,?)",(sid,cost))
                self.audit("cost-override",{"id":sid,"unitCost":cost})
            for item in catalog:
                self.db.execute("INSERT INTO catalog VALUES(?,?,?,?) ON CONFLICT(source,source_id) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at",(source,item["id"],canonical(item),now()))
            for asset in assets:
                self.db.execute('INSERT INTO assets VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at',(asset['id'],canonical(asset),now()))
            for doc, digest, old, financial_change in pending:
                revision = old["revision"] + 1 if old else 1
                if old:self.db.execute('INSERT OR IGNORE INTO document_history VALUES(?,?,?,?,?,?)',(source,doc['id'],old['revision'],old['payload'],old['batch_id'],now()))
                self.db.execute('INSERT INTO document_history VALUES(?,?,?,?,?,?)',(source,doc['id'],revision,canonical(doc),batch,now()))
                if old and financial_change:
                    prior = self.db.execute("SELECT e.id,e.date FROM entries e WHERE e.source=? AND e.source_id=? AND e.reversal_of IS NULL AND NOT EXISTS(SELECT 1 FROM entries reversal WHERE reversal.reversal_of=e.id)", (source, doc["id"])).fetchall()
                    for entry in prior:
                        lines = self.db.execute("SELECT account,debit,credit FROM lines WHERE entry_id=?", (entry["id"],)).fetchall()
                        self.post(source, doc["id"], revision, entry["date"], "Reversal for source revision", batch,
                                  [{"account": l["account"], "debit": l["credit"], "credit": l["debit"]} for l in lines], entry["id"])
                if doc["lines"] and financial_change:
                    self.post(source, doc["id"], revision, doc["date"], doc.get("memo", ""), batch, doc["lines"])
                self.db.execute("INSERT OR REPLACE INTO documents VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (
                    source, doc["id"], digest, revision, doc["date"], doc.get("kind", "journal"),
                    doc.get("reference", doc["id"]), doc.get("party", ""), doc.get("amount", 0),
                    doc.get("balance", 0), canonical(doc), batch))
            self.audit("import", {"batch": batch, "source": source, **counts})
            self.db.commit()
            return {"batch": batch, **counts}
        except Exception:
            self.db.rollback()
            raise

    def post(self, source, sid, revision, date_, memo, batch, lines, reversal=None):
        eid = self.db.execute("INSERT INTO entries(source,source_id,revision,date,memo,batch_id,reversal_of) VALUES(?,?,?,?,?,?,?)",
                              (source, sid, revision, date_, str(memo)[:1000], batch, reversal)).lastrowid
        self.db.executemany("INSERT INTO lines(entry_id,account,debit,credit) VALUES(?,?,?,?)",
                            [(eid, l["account"], l["debit"], l["credit"]) for l in lines])

    def rows(self, start=None, end=None, source=None, account=None):
        conditions, args = ["1=1"], []
        for column, op, value in [("e.date", ">=", start), ("e.date", "<=", end), ("e.source", "=", source), ("l.account", "=", account)]:
            if value:
                conditions.append(f"{column}{op}?")
                args.append(day(value) if column == "e.date" else value)
        return [dict(r) for r in self.db.execute("SELECT l.id,l.entry_id,e.source,e.source_id,e.revision,e.date,e.memo,e.reversal_of,l.account,a.name,a.type,l.debit,l.credit,r.reconciliation_id FROM lines l JOIN entries e ON e.id=l.entry_id JOIN accounts a ON a.code=l.account LEFT JOIN reconciliation_lines r ON r.line_id=l.id WHERE " + " AND ".join(conditions) + " ORDER BY e.date,e.id,l.id", args)]

    def report(self, start=None, end=None):
        period = self.rows(start, end)
        all_rows = self.rows(end=end)
        def aggregate(rows):
            result = {}
            for r in rows:
                a = result.setdefault(r["account"], {"code": r["account"], "name": r["name"], "type": r["type"], "debit": 0, "credit": 0})
                a["debit"] += r["debit"]
                a["credit"] += r["credit"]
            for a in result.values():
                a["balance"] = a["debit"] - a["credit"]
                a['closingDebit']=max(a['balance'],0)
                a['closingCredit']=max(-a['balance'],0)
            return sorted(result.values(), key=lambda a: a["code"])
        trial = aggregate(all_rows)
        pnl = aggregate(period)
        income = -sum(a["balance"] for a in pnl if a["type"] == "income")
        expense = sum(a["balance"] for a in pnl if a["type"] == "expense")
        assets = sum(a["balance"] for a in trial if a["type"] == "asset")
        liabilities = -sum(a["balance"] for a in trial if a["type"] == "liability")
        equity = -sum(a["balance"] for a in trial if a["type"] == "equity")
        retained = -sum(a["balance"] for a in trial if a["type"] in {"income", "expense"})
        return {"income": income, "expense": expense, "profit": income-expense, "assets": assets,
                "liabilities": liabilities, "equity": equity, "earnings": retained,
                "balanceDifference": assets-liabilities-equity-retained,
                "debits": sum(a["debit"] for a in trial), "credits": sum(a["credit"] for a in trial),
                'trialDebits':sum(a['closingDebit'] for a in trial),'trialCredits':sum(a['closingCredit'] for a in trial),
                "trial": trial, "profitLoss": [a for a in pnl if a["type"] in {"income", "expense"}],
                "balanceSheet": [a for a in trial if a["type"] in {"asset", "liability", "equity"}]}

    def summary(self, start=None, end=None):
        report = self.report(start, end)
        documents=[dict(r) for r in self.db.execute("SELECT source,source_id,revision,date,kind,reference,party,amount,balance FROM documents ORDER BY date DESC,source_id")]
        allocations=self.allocations()
        for d in documents:
            d['balance']-=allocations.get((d['source'],d['source_id']),0)
        return {"settings": self.settings(), "report": report,
                "documents": documents,
                "accounts": [dict(r) for r in self.db.execute("SELECT * FROM accounts ORDER BY code")],
                "batches": [dict(r) for r in self.db.execute("SELECT id,source,created_at,snapshot_at,filename,added,changed,duplicates FROM batches ORDER BY created_at DESC LIMIT 50")],
                "audit": [dict(r) for r in self.db.execute("SELECT * FROM audit ORDER BY id DESC LIMIT 100")],
                "reconciliations": [dict(r) for r in self.db.execute("SELECT * FROM reconciliations ORDER BY date DESC")],
                "attachments": [dict(r) for r in self.db.execute("SELECT id,source,source_id,name,mime,created_at FROM attachments ORDER BY created_at DESC")]}

    def allocations(self):
        result={}
        for r in self.db.execute("SELECT payload FROM documents WHERE source='manual' AND kind='payment'"):
            doc=json.loads(r[0]);applied=doc.get('appliedTo')
            if applied:
                key=(applied['source'],applied['id'])
                result[key]=result.get(key,0)+doc['amount']
        return result

    def reconcile(self, value):
        account, date_ = self.account_code(value["account"]), day(value["date"])
        ids = value.get("lineIds", [])
        if not isinstance(ids, list) or len(ids) != len(set(ids)) or any(type(i) is not int for i in ids):
            raise AccountingError("Choose each bank journal line once")
        starting, ending = cents(value["starting"]), cents(value["ending"])
        with self.db:
            previous = self.db.execute("SELECT date,ending FROM reconciliations WHERE account=? ORDER BY date DESC LIMIT 1", (account,)).fetchone()
            if previous and (date_ <= previous["date"] or starting != previous["ending"]):
                raise AccountingError("Start with the last statement's ending balance and a later statement date")
            if self.settings().get("closed_through", "") >= date_:
                raise AccountingError("Statement date is in a closed period")
            rows = {r["id"]: r for r in self.rows(end=date_, account=account)}
            if account not in {"1010", "1020", "1030"}:
                raise AccountingError("Choose a cash or bank account")
            if not previous and starting != 0:
                raise AccountingError("First reconciliation starts at zero; select the opening balance journal too")
            if any(i not in rows or rows[i]["reconciliation_id"] for i in ids):
                raise AccountingError("Selected line is missing, after the statement date, or already reconciled")
            actual = starting + sum(rows[i]["debit"]-rows[i]["credit"] for i in ids)
            if actual != ending:
                raise AccountingError(f"Statement difference is {(ending-actual)/100:.2f}; resolve it before finishing")
            rid = str(uuid.uuid4())
            self.db.execute("INSERT INTO reconciliations VALUES(?,?,?,?,?,?)", (rid, account, date_, starting, ending, now()))
            self.db.executemany("INSERT INTO reconciliation_lines VALUES(?,?)", [(i, rid) for i in ids])
            self.audit("reconciliation", {"id": rid, "lineIds": ids})
            if value.get('statement'):
                self.audit('bank-statement',{'reconciliation':rid,'rows':value['statement']})
            return {"id": rid}

    def attach(self, value):
        try:
            data = base64.b64decode(value["content"], validate=True)
        except (ValueError, KeyError) as exc:
            raise AccountingError("Invalid attachment") from exc
        if not data or len(data) > 10*1024*1024:
            raise AccountingError("Attachments must be between 1 byte and 10 MB")
        aid = str(uuid.uuid4())
        with self.db:
            if not self.db.execute("SELECT 1 FROM documents WHERE source=? AND source_id=?", (value["source"], value["sourceId"])).fetchone():
                raise AccountingError("Choose an existing transaction")
            self.db.execute("INSERT INTO attachments VALUES(?,?,?,?,?,?,?)", (aid, value["source"], value["sourceId"], str(value["name"])[:200], "application/octet-stream", data, now()))
            self.audit("attachment", {"id": aid, "source": value["source"], "sourceId": value["sourceId"]})
        return {"id": aid}

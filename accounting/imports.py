"""Adapters for the supplied Backwoods Brew 8.2 and Vendor Ordering 4.1 packages.

No inferred payroll, tax rates, or historical inventory costs. Unknown financial
records fail explicitly, rather than producing apparently complete statements.
"""
from collections import defaultdict
from decimal import Decimal
import re
from .ledger import AccountingError, cents, day


def line(account, debit=0, credit=0):
    return {"account": str(account), "debit": debit, "credit": credit}


def pair(debit, credit, amount):
    if not amount:
        return []
    if amount < 0:
        return pair(credit, debit, -amount)
    return [line(debit, amount), line(credit, credit=amount)]


def identifier(row):
    value = row.get("id")
    if value is None or not str(value).strip():
        raise AccountingError("Every source record needs its original stable ID")
    return str(value)


def record(kind, row, lines, *, amount=0, balance=0, party="", date_=None, reference=None):
    return {"id": f"{kind}:{identifier(row)}", "kind": kind,
            "date": day(date_ or row.get("date") or row.get("createdAt")),
            "reference": str(reference or row.get("invoiceNumber") or row.get("invoiceNo") or row.get("reference") or row["id"]),
            "party": str(party or ""), "memo": str(row.get("memo") or row.get("notes") or row.get("note") or kind),
            "amount": amount, "balance": balance, "lines": lines, "original": row}


def money(row, key, default=0):
    return cents(row.get(key, default))


def nonnegative(value):
    if value < 0:
        raise AccountingError("Negative invoice/payment amount requires a credit or reversal")
    return value


def account_code(value, default):
    value = str(value or default).strip()
    m = re.match(r"^(\d{4,6})(?:\s.*)?$", value)
    if not m:
        raise AccountingError(f"Map account '{value}' to a chart code first")
    return m.group(1)


def unwrap(payload):
    if not isinstance(payload, dict):
        raise AccountingError("Import must be a JSON object")
    for key in ["data", "appData", "state"]:
        if isinstance(payload.get(key), dict):
            return payload[key]
    return payload


def sanitize_payload(payload,source):
    data=unwrap(payload)
    financial={'accounts','generalLedger','orders','invoices','bills','expenses','journalEntries','payrollRuns','salesTaxPayments','payrollTaxPayments','wasteLogs','greenCoffeeLots','roastBatches','voids','refunds','receiptAttachments','payments','inventory','products','stores','depreciationRuns','businessLoans','fixedAssets','bankImports','bankReconciliations','customers','suppliers','purchaseOrders','purchaseReceipts','supplierInvoices','credits','inventoryMovements','driverSettlements'}
    forbidden={'password','passwordhash','passwordsalt','accesstoken','refreshtoken','clientsecret','privatekey','ssn','socialsecuritynumber','routingnumber','bankaccountnumber','apikey'}
    def clean(value):
        if isinstance(value,dict):return {k:clean(v) for k,v in value.items() if re.sub(r'[^a-z]','',k.lower()) not in forbidden}
        if isinstance(value,list):return [clean(v) for v in value]
        return value
    if source=='employees':
        return {key:clean(value) for key,value in payload.items() if key in {'schemaVersion','source','type','company','start','endExclusive','exportId','timesheets','timeOff','departments'}}
    result={key:clean(value) for key,value in data.items() if key in financial}
    if isinstance(data.get('company'),dict):result['company']={'name':str(data['company'].get('name',''))}
    return {**{k:v for k,v in payload.items() if k in {'schemaVersion','app','type','exportedAt'}},'data':result}


def cancelled(row):
    return bool(row.get("voided") or row.get("deleted")) or str(row.get("status", "")).strip().lower() in {"void", "voided", "cancelled", "canceled", "deleted"}


def mirrored(row):
    return str(row.get("sourceSystem") or row.get("sourceApp") or "").lower() in {"vendor-ordering", "vendor", "backwoods vendor ordering"}


def main_import(payload):
    data = unwrap(payload)
    docs, warnings, accounts = [], [], []
    types = {"asset": "asset", "assets": "asset", "liability": "liability", "liabilities": "liability",
             "equity": "equity", "income": "income", "revenue": "income", "expense": "expense", "expenses": "expense", "cost of goods sold": "expense"}
    for a in data.get("accounts", []):
        code = account_code(a.get("code"), "")
        type_ = types.get(str(a.get("type", "")).lower())
        if not type_:
            raise AccountingError(f"Unknown account type for {code}")
        accounts.append((code, str(a.get("name") or code), type_))
    # Preferred route: the main app's own general ledger, including payroll/roasting.
    if "generalLedger" in data:
        if not isinstance(data["generalLedger"], list):
            raise AccountingError("generalLedger must be an array")
        void_invoices={str(r.get("invoiceNo") or r["id"]) for r in data.get("invoices",[]) if cancelled(r) and not mirrored(r)}
        grouped = defaultdict(list)
        for r in data["generalLedger"]:
            if mirrored(r):
                continue
            source_id = str(r.get("source", "")).strip()
            if not source_id:
                raise AccountingError("General ledger line has no source reference")
            if any(source_id=="Invoice Payment "+ref for ref in void_invoices):
                raise AccountingError("Voided invoice has a payment; record a refund or reviewed correction in the source app")
            if any(source_id=="Invoice "+ref for ref in void_invoices):
                continue
            # Source labels in the recovered main app are stable across exports.
            grouped[source_id].append(r)
        for sid, rows in grouped.items():
            dates = {day(r.get("date")) for r in rows}
            if len(dates) != 1:
                raise AccountingError(f"Main ledger source '{sid}' has multiple dates; original IDs must be disambiguated")
            lines = [line(account_code(r.get("account"), ""), money(r, "debit"), money(r, "credit")) for r in rows if money(r, "debit") or money(r, "credit")]
            docs.append(record("ledger", {"id": sid, "date": next(iter(dates)), "memo": "; ".join(dict.fromkeys(str(r.get("memo") or "") for r in rows))}, lines, amount=sum(l["debit"] for l in lines), reference=sid))
        # Documents/receipts are retained as supporting records, without posting a second time.
        for collection in ["orders", "invoices", "bills", "expenses", "payrollRuns", "receiptAttachments", "payments"]:
            for r in data.get(collection, []):
                if not mirrored(r):
                    doc = record("support-"+collection, r, [], date_=r.get("date") or r.get("createdAt") or payload.get("exportedAt"))
                    if collection in {"invoices","bills"}:
                        doc["party"]=str(r.get("customer") or r.get("vendor") or "")
                        doc["amount"]=money(r,"total",r.get("amount",0))
                        doc["balance"]=0 if str(r.get("status","")).lower()=="paid" else doc["amount"]
                        doc["reference"]=str(r.get("invoiceNo") or r.get("reference") or r["id"])
                    if collection=="invoices" and cancelled(r):
                        doc.update(amount=0,balance=0,kind="voided-support-invoices")
                    docs.append(doc)
        warnings.append("Main-app totals follow its existing ledger rules. Review the source app's bank, payroll, and rounding classifications.")
        return docs, accounts, warnings
    # Plain backup route supports explicit journals and core retail records. More
    # complex components require the connector, so they are never silently lost.
    for key in ["payrollRuns", "greenCoffeeLots", "roastBatches", "depreciationRuns", "businessLoans", "fixedAssets", "payments"]:
        if data.get(key):
            raise AccountingError(f"This main-app backup includes {key}. Use the main-app connector's general-ledger export to preserve its accounting rules.")
    if not any(k in data for k in ["orders", "invoices", "bills", "expenses", "journalEntries"]):
        raise AccountingError("Not a recognized main-app accounting backup")
    orders = {identifier(r): r for r in data.get("orders", [])}
    for r in data.get("orders", []):
        if mirrored(r):
            continue
        gross, discount, tax, total = (money(r, k) for k in ["subtotal", "discountAmount", "tax", "total"])
        if total != gross-discount+tax:
            raise AccountingError(f"Sale {r['id']} totals do not match; use the main-app ledger export for rounding details")
        bank = "1010" if str(r.get("paymentType", "")).lower() == "cash" else "1020"
        lines = [line(bank, total), line("4000", credit=gross)]
        if discount: lines.append(line("4010", discount))
        if tax: lines.append(line("2100", credit=tax))
        cost = sum(money(x, "cost") for x in r.get("depletionLog", []))
        lines += pair("5000", "1200", cost)
        docs.append(record("sale", r, [l for l in lines if l["debit"] or l["credit"]], amount=total))
    # Voids reverse the original sale. Explicit void record wins over flag.
    voids = {str(v.get("orderId")): v for v in data.get("voids", [])}
    for oid, r in orders.items():
        if r.get("voided") or oid in voids:
            original = next((d for d in docs if d["id"] == "sale:"+oid), None)
            if not original: continue
            v = voids.get(oid, {"date": r.get("voidedAt") or r.get("date")})
            rows = [line(l["account"], l["credit"], l["debit"]) for l in original["lines"]]
            docs.append(record("void", {**v, "id": oid}, rows, date_=v.get("date") or v.get("createdAt") or r.get("date"), amount=-original["amount"]))
    for r in data.get("refunds", []):
        if not all(k in r for k in ["amount", "tax", "subtotal"]):
            raise AccountingError("Refund requires explicit subtotal/tax, or the main-app ledger connector")
        subtotal, tax, total = money(r,"subtotal"), money(r,"tax"), money(r,"amount")
        if subtotal+tax != total:
            raise AccountingError("Refund total does not match subtotal and tax")
        bank = "1010" if str(r.get("paymentType", "")).lower() == "cash" else "1020"
        docs.append(record("refund", r, [line("4020",subtotal),line("2100",tax),line(bank,credit=total)], amount=-total))
    for key, kind in [("expenses", "expense"), ("bills", "bill"), ("invoices", "invoice")]:
        for r in data.get(key, []):
            if mirrored(r): continue
            if kind == "invoice" and cancelled(r):
                docs.append(record("voided-invoice", r, [], party=r.get("customer", "")))
                docs[-1]["id"] = "invoice:"+identifier(r)
                continue
            paid = str(r.get("status", "")).lower() == "paid"
            if kind == "invoice":
                subtotal = money(r, "subtotal", r.get("amount", 0))
                tax = money(r, "tax")
                total = money(r, "total", Decimal(subtotal+tax)/100)
                if subtotal+tax != total: raise AccountingError("Invoice totals do not match")
                lines = pair("1100", account_code(r.get("account"), "4000"), subtotal)
                lines += pair("1100", "2100", tax)
                party = r.get("customer", "")
                payment_lines = pair("1020", "1100", total)
            else:
                total = money(r, "amount")
                lines = pair(account_code(r.get("account"), "5100"), "2000" if kind == "bill" else "1020", total)
                party = r.get("vendor", "")
                payment_lines = pair("2000", "1020", total)
            nonnegative(total)
            docs.append(record(kind,r,lines,amount=total,balance=0 if paid or kind=="expense" else total,party=party))
            if paid and kind != "expense":
                docs.append(record(kind+"-payment", r, payment_lines, amount=total, party=party, date_=r.get("paidDate") or r.get("date")))
    for r in data.get("journalEntries", []):
        if mirrored(r): continue
        if r.get("payrollRunId"):
            raise AccountingError("Payroll-linked journal requires main-app ledger export")
        lines = [line(account_code(l.get("account"), ""), money(l,"debit"),money(l,"credit")) for l in r.get("lines",[])]
        if not lines: raise AccountingError("Empty journal")
        docs.append(record("journal",r,lines,amount=sum(l["debit"] for l in lines)))
    for key, debit in [("salesTaxPayments","2100"),("payrollTaxPayments",None),("wasteLogs","5000")]:
        for r in data.get(key,[]):
            amount=money(r,"cost" if key=="wasteLogs" else "amount")
            docs.append(record(key,r,pair(debit or account_code(r.get("account"),"2151"),"1200" if key=="wasteLogs" else "1020",amount),amount=amount))
    return docs, accounts, warnings


def quantity(value):
    try:
        n=Decimal(str(value))
        if not n.is_finite() or abs(n)>1_000_000_000: raise ValueError()
        return n
    except Exception as exc:
        raise AccountingError("Invalid inventory quantity") from exc


def vendor_import(payload):
    data=unwrap(payload)
    if not isinstance(data.get("orders"),list) or not isinstance(data.get("products"),list):
        raise AccountingError("Not a Vendor Ordering backup (orders and products are required)")
    docs,warnings=[],[]
    customers={str(r["id"]):r.get("name","") for r in data.get("customers",[])}
    suppliers={str(r["id"]):r.get("name","") for r in data.get("suppliers",[])}
    orders={identifier(r):r for r in data["orders"]}
    if len(orders)!=len(data["orders"]): raise AccountingError("Duplicate vendor order ID")
    payments={}
    def add_payment(r, oid=None):
        pid=identifier(r)
        obj={**r,"orderId":str(r.get("orderId") or oid or "")}
        if pid in payments and any(payments[pid].get(k)!=obj.get(k) for k in ["orderId","amount","method"]):
            raise AccountingError(f"Conflicting payment copies: {pid}")
        payments[pid]=obj
    for r in data.get("payments",[]):add_payment(r)
    for r in data["orders"]:
        for p in r.get("payments",[]): add_payment(p,identifier(r))
    active=set()
    for r in data["orders"]:
        oid=identifier(r)
        status=str(r.get("status","")).lower()
        recognized={"delivered","payment_pending","completed"}
        is_cancelled=cancelled(r)
        draft=status in {"draft","submitted","approved","packing","packed","out_for_delivery","ready","scheduled"}
        if not (status in recognized or is_cancelled or draft):
            raise AccountingError(f"Unknown vendor order status '{status}' for {oid}")
        if draft:
            if r.get("payments"): raise AccountingError(f"Undelivered order {oid} has payments; deposit accounting needs review")
            continue
        if is_cancelled:
            if any(p["orderId"]==oid for p in payments.values()): raise AccountingError(f"Cancelled order {oid} has payments; record the refund explicitly")
            docs.append(record("voided-invoice",r,[],date_=r.get("deliveredAt") or r.get("createdAt"),party=customers.get(str(r.get("customerId")),"")))
            docs[-1]["id"]="invoice:"+oid
            continue
        active.add(oid)
        gross=returns=0
        for item in r.get("items",[]):
            q=quantity(item.get("invoiceQty",item.get("deliveredQty",item.get("qty",0))))
            rq=quantity(item.get("returnQty",0))
            price=quantity(item.get("price",0))
            rp=quantity(item.get("returnPrice",item.get("price",0)))
            percent=quantity(item.get("returnCreditPercent",100))
            if min(q,rq,price,rp,percent)<0 or percent>100:raise AccountingError("Invalid invoice quantity, price or return percentage")
            gross+=cents(q*price)
            returns+=cents(rq*rp*percent/100)
        tax=nonnegative(money(r,"tax"))
        credits=sum(nonnegative(money(c,"amount")) for c in r.get("credits",[]))
        total=gross-returns-credits+tax
        if total<0:raise AccountingError(f"Credits exceed invoice {oid}; customer credit balance requires review")
        paid=sum(nonnegative(money(p,"amount")) for p in payments.values() if p["orderId"]==oid)
        if paid>total:raise AccountingError(f"Payments exceed invoice {oid}; customer deposit requires review")
        lines=[line("1100",total),line("4000",credit=gross)]
        if returns+credits:lines.append(line("4020",returns+credits))
        if tax:lines.append(line("2100",credit=tax))
        docs.append(record("invoice",r,[l for l in lines if l["debit"] or l["credit"]],amount=total,balance=total-paid,party=customers.get(str(r.get("customerId")),r.get("customerName","")),date_=r.get("deliveredAt") or r.get("date") or r.get("createdAt")))
    for p in payments.values():
        if p["orderId"] not in active:
            raise AccountingError(f"Payment {p['id']} has no delivered invoice; review before posting")
        amount=nonnegative(money(p,"amount"))
        # Driver cash/check/card collections stay undeposited until a deposit is recorded.
        bank="1020" if str(p.get("method","")).lower() in {"ach","bank","bank transfer"} else "1030"
        docs.append(record("payment",p,pair(bank,"1100",amount),amount=amount,party=customers.get(str(orders[p["orderId"]].get("customerId")),"")))
    # Approved credits are already included in their invoice, never posted again.
    for credit in data.get("credits",[]):
        if str(credit.get("status","")).lower() in {"approved","picked_up"}:
            order=orders.get(str(credit.get("orderId")))
            if not order or not any(str(c.get("id"))==identifier(credit) for c in order.get("credits",[])):
                raise AccountingError(f"Approved credit {credit.get('id')} is absent from its invoice")
    receipts={identifier(r):r for r in data.get("purchaseReceipts",[])}
    for r in receipts.values():
        if "landedCostTotal" not in r: raise AccountingError(f"Receipt {r['id']} has no captured landed cost")
        amount=nonnegative(money(r,"landedCostTotal"))
        docs.append(record("purchase-receipt",r,pair("1200","2000",amount),amount=amount,balance=amount,party=suppliers.get(str(r.get("supplierId")),"")))
    if data.get("supplierInvoices"):
        raise AccountingError("Supplier invoice schema is not present in the supplied app build; review its fields before posting to avoid counting received goods twice")
    for r in data.get("inventoryMovements",[]):
        type_=r.get("type")
        if type_=="purchase_receipt":
            if str(r.get("referenceId")) not in receipts:raise AccountingError("Purchase movement has no corresponding receipt")
            continue
        q=quantity(r.get("quantity",0))
        if not q:continue
        if "unitCost" not in r:
            # A missing historical cost is represented explicitly in the review queue.
            doc=record("needs-cost",r,[])
            doc["id"]="inventory:"+identifier(r)
            docs.append(doc)
            warnings.append(f"Inventory movement {r['id']} ({type_}) needs its historical unit cost; no cost posting was made.")
            continue
        amount=cents(q*quantity(r["unitCost"]))
        if type_ in {"opening_balance","bulk_opening_balance"}:
            lines=pair("1200","3100",amount)
        elif type_ in {"delivery","credit_return","return","return_sellable","sellable_return","adjustment","damaged","expired","waste"}:
            lines=pair("1200","5000",amount)
        elif type_ in {"return_damaged","return_expired","return_quarantine"}:
            lines=[]
            warnings.append(f"Non-sellable return {r['id']} has no inventory recovery value posted. Review any salvage value or quarantine release separately.")
        else:raise AccountingError(f"Unknown inventory movement type: {type_}")
        docs.append(record("inventory",r,lines,amount=amount))
    for settlement in data.get("driverSettlements",[]):
        docs.append(record("support-settlement",settlement,[]))
    warnings.append("Driver settlements are supporting records. Record actual bank deposits as transfers from Undeposited Funds; a settlement is not proof of a deposit.")
    return docs,[],warnings


def employee_time_import(payload):
    if payload.get('schemaVersion')!=1 or payload.get('source')!='employees' or payload.get('type')!='backwoods-employee-time':
        raise AccountingError('Choose business-accounting-time.json from an Employee Employer approved-time download')
    company=payload.get('company') or {}
    if not isinstance(company,dict) or not company.get('id') or not company.get('name'):raise AccountingError('The Employee company identity is missing')
    start=day(payload.get('start'));end=day(payload.get('endExclusive'))
    if not start<end:raise AccountingError('Invalid Employee time report period')
    sheets=payload.get('timesheets');leave=payload.get('timeOff')
    if not isinstance(sheets,list) or not isinstance(leave,list) or not sheets and not leave:raise AccountingError('No approved Employee time records were supplied')
    docs=[];ids=set()
    def minutes(value):
        from decimal import InvalidOperation
        try:
            number=Decimal(str(value))
            if not number.is_finite() or not 0<=number<=150000:raise ValueError()
            return number
        except (InvalidOperation,ValueError,TypeError):raise AccountingError('Invalid approved time minutes')
    for kind,records in [('employee-timesheet',sheets),('employee-time-off',leave)]:
        for item in records:
            if not isinstance(item,dict) or not isinstance(item.get('id'),str) or not item['id'] or not item.get('employeeId') or item.get('status')!='approved' or not item.get('approvedBy'):raise AccountingError('Each Employee time record needs its stable ID, employee and approval')
            key=(kind,item['id'])
            if key in ids:raise AccountingError('Duplicate Employee time record in the file')
            ids.add(key)
            if kind=='employee-timesheet':
                if not re.fullmatch('[a-f0-9]{64}',str(item.get('sourceHash') or '')) or not item.get('approvedAt'):raise AccountingError('Approved timesheet evidence is missing')
                if not start<=day(item.get('start'))<day(item.get('endExclusive'))<=end:raise AccountingError('Timesheet falls outside the complete export period')
                if not isinstance(item.get('assignments'),list):raise AccountingError('Approved job allocations are missing')
                for job in item['assignments']:
                    if not isinstance(job,dict) or not job.get('assignmentId') or not job.get('departmentId') or job.get('payType') not in {'hourly','salary'}:raise AccountingError('Approved job and department mapping is missing')
                    minutes(job.get('regularMinutes'));minutes(job.get('overtimeMinutes'))
                    if type(job.get('rateCents')) is not int or not 0<=job['rateCents']<=100000000:raise AccountingError('Invalid reviewed job rate')
                    if job['payType']=='hourly' and (any(type(job.get(key)) is not int or job[key]<0 for key in ['regularCents','overtimeCents','estimatedGrossCents']) or job['regularCents']+job['overtimeCents']!=job['estimatedGrossCents']):raise AccountingError('Estimated gross wages do not reconcile')
            else:
                paid=minutes(item.get('paidMinutes'))
                if item.get('kind') not in {'vacation','sick','personal','unpaid'} or item['kind']=='unpaid' and paid:raise AccountingError('Invalid approved time-off type')
                if paid and (not item.get('assignmentId') or not item.get('departmentId')):raise AccountingError('Paid leave needs a reviewed job and department')
                if day(item.get('start'))<start or day(item.get('start'))>=end or day(item.get('end'))>end:raise AccountingError('Time off falls outside the export period')
            original={'id':item['id'],'date':item['start'],'memo':'Approved hours / estimated gross pay; payroll review in Business Accounting','record':item,'company':company}
            docs.append(record(kind,original,[],party=item.get('employee',''),reference=item.get('employeeNumber') or item['employeeId']))
    return docs,[],['Approved time and PTO only: no payroll, tax liability or payment is posted by this import. Estimated gross wages are before deductions; process payroll in Business Accounting using the actual payroll results.']

def prepare(payload, source):
    if source=='employees':return employee_time_import(payload)
    if source=="vendor":return vendor_import(payload)
    if source=="main":return main_import(payload)
    raise AccountingError("Select the main app, vendor app or Employee Employer app as import source")


def catalog_items(payload,source):
    data=unwrap(payload)
    products={str(p.get('id')):p for p in data.get('products',[]) if p.get('id') is not None}
    rows=data.get('inventory',[]) if source=='main' else data.get('products',[])
    result=[]
    for r in rows:
        pid=identifier(r)
        p=products.get(str(r.get('productId') or r.get('id')),{})
        result.append({'id':pid,'sku':str(r.get('sku') or p.get('sku') or ''),'name':str(r.get('name') or r.get('item') or p.get('name') or pid),
            'location':str(r.get('storeId') or r.get('location') or 'Warehouse' if source=='vendor' else r.get('storeId') or r.get('location') or 'Retail'),
            'onHand':float(quantity(r.get('onHand',r.get('qty',0)))),'reserved':float(quantity(r.get('reserved',0))),
            'unitCost':str(r.get('cost',p.get('cost',0))),'unit':str(r.get('unit',p.get('unit','each'))),
            'caseQty':float(quantity(r.get('caseQty',p.get('caseQty',1)))),'reorderLevel':float(quantity(r.get('reorderLevel',0))),
            'price':str(r.get('price',p.get('price',0)))})
    return result

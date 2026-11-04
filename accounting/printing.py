"""Escaped, authenticated print documents. No UI controls appear on paper."""
from html import escape
import json
from .ledger import AccountingError
from .business import asset_state


def e(value):return escape(str(value if value is not None else ''),quote=True)
def money(value):return f'${value/100:,.2f}'
def table(heads,rows):return '<table><thead><tr>'+''.join('<th>'+e(h)+'</th>' for h in heads)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+e(v)+'</td>' for v in row)+'</tr>' for row in rows)+'</tbody></table>'
def total(label,value):return '<div class="total"><span>'+e(label)+'</span><strong>'+e(money(value))+'</strong></div>'


def render(ledger,args,user):
    type_=args.get('type','ledger');title='';body='';subtitle=''
    report=ledger.report(args.get('start'),args.get('end'))
    documents=ledger.summary()['documents']
    if user['role']=='viewer' and type_ in {'payroll','paystub','provider-payroll'}:raise AccountingError('Payroll printing is restricted to authorized users')
    if type_=='ledger':
        title='Company general ledger';subtitle='Accrual basis · USD'
        body=table(['Date','Account','Source','Reference','Debit','Credit'],[[r['date'],r['account']+' '+r['name'],r['source'],r['source_id'],money(r['debit']),money(r['credit'])] for r in ledger.rows(args.get('start'),args.get('end'))])
    elif type_=='profit-loss':
        title='Profit & loss';subtitle=f"{args.get('start') or 'Beginning'} through {args.get('end') or 'latest imported date'} · Accrual basis"
        body=table(['Account','Amount'],[[a['code']+' '+a['name'],money(-a['balance'] if a['type']=='income' else a['balance'])] for a in report['profitLoss']])+total('Net revenue',report['income'])+total('Expenses & cost of sales',report['expense'])+total('Net profit',report['profit'])
    elif type_=='balance-sheet':
        title='Balance sheet';subtitle='As of '+(args.get('end') or 'latest imported date')
        body=table(['Type','Account','Balance'],[[a['type'].title(),a['code']+' '+a['name'],money(a['balance'] if a['type']=='asset' else -a['balance'])] for a in report['balanceSheet']])+total('Assets',report['assets'])+total('Liabilities',report['liabilities'])+total('Equity before earnings',report['equity'])+total('Cumulative earnings',report['earnings'])+total('Balance difference',report['balanceDifference'])
    elif type_=='trial-balance':
        title='Trial balance';subtitle='As of '+(args.get('end') or 'latest imported date')
        body=table(['Account','Debit balance','Credit balance'],[[a['code']+' '+a['name'],money(a['closingDebit']),money(a['closingCredit'])] for a in report['trial']])+total('Total debit balances',report['trialDebits'])+total('Total credit balances',report['trialCredits'])
    elif type_=='record':
        source=args.get('source');sid=args.get('id')
        r=ledger.db.execute('SELECT payload FROM documents WHERE source=? AND source_id=?',(source,sid)).fetchone()
        if not r:raise AccountingError('Record not found')
        d=json.loads(r[0]);original=d.get('original',{})
        if user['role']=='viewer' and 'payroll' in d['kind'].lower():raise AccountingError('Payroll printing requires authorized access')
        title=d['kind'].removeprefix('support-').replace('-',' ').title()
        subtitle=d['reference']
        body='<div class="info"><p><strong>Date:</strong> '+e(d['date'])+'</p><p><strong>Customer / supplier:</strong> '+e(d['party'] or '—')+'</p><p><strong>Source:</strong> '+e(source)+'</p>'
        if original.get('dueDate'):body+='<p><strong>Due date:</strong> '+e(original['dueDate'])+'</p>'
        body+='</div>'
        items=original.get('items',[])
        if items:
            body+=table(['Description','Quantity','Unit price','Returns'],[[i.get('name') or i.get('description') or i.get('productId',''),i.get('invoiceQty',i.get('deliveredQty',i.get('qty',''))),i.get('price',''),i.get('returnQty',0)] for i in items])
        elif d.get('memo'):body+='<p>'+e(d['memo'])+'</p>'
        body+=total('Record amount',d['amount'])
        display=next((x for x in documents if x['source']==source and x['source_id']==sid),None)
        if d['kind'] in {'invoice','bill','purchase-receipt','support-invoices','support-bills'}:body+=total('Current outstanding balance',display['balance'] if display else d['balance'])
        if d['lines']:body+='<h2>Accounting detail</h2>'+table(['Account','Debit','Credit'],[[l['account'],money(l['debit']),money(l['credit'])] for l in d['lines']])
        files=ledger.db.execute('SELECT name FROM attachments WHERE source=? AND source_id=?',(source,sid)).fetchall()
        if files:body+='<h2>Supporting attachments</h2><ul>'+''.join('<li>'+e(f['name'])+'</li>' for f in files)+'</ul><p class="note">Download the supporting files from the record to print their contents separately.</p>'
    elif type_=='payroll':
        title='Business payroll register';subtitle='Externally calculated payroll recorded directly in Business Accounting · not a tax filing'
        payroll=[]
        for r in ledger.db.execute("SELECT payload FROM documents WHERE source='manual' AND kind='payroll' ORDER BY date"):
            d=json.loads(r[0]);c=d['original']['calculation']
            payroll.append([d['date'],d['party'],d['original']['periodStart']+' to '+d['original']['periodEnd'],money(c['gross']),money(c['withheld']),money(c['net']),money(c['employerTaxes'])])
        body=table(['Pay date','Employee','Pay period','Gross','Withheld','Net','Employer taxes'],payroll)
    elif type_=='paystub':
        r=ledger.db.execute("SELECT payload FROM documents WHERE source='manual' AND source_id=? AND kind='payroll'",(args.get('id'),)).fetchone()
        if not r:raise AccountingError('Payroll record not found')
        d=json.loads(r[0]);o=d['original'];c=o['calculation'];title='Payroll earnings statement';subtitle=d['party']
        body='<div class="info"><p><strong>Pay date:</strong> '+e(d['date'])+'</p><p><strong>Pay period:</strong> '+e(o['periodStart'])+' through '+e(o['periodEnd'])+'</p><p><strong>Reference:</strong> '+e(d['reference'])+'</p></div>'+table(['Earnings / deduction','Amount'],[['Gross wages',money(c['gross'])]]+[[name,money(c['amounts'][key])] for key,name in [('federal','Federal withholding'),('state','State / local withholding'),('socialSecurity','Employee Social Security'),('medicare','Employee Medicare'),('deductions','Other employee deductions')]])+total('Net pay',c['net'])+total('Unpaid net wages in these books',d['balance'])
        body+='<p class="note">Prepared from externally calculated payroll figures entered in Business Accounting. It is not a direct-deposit confirmation or a tax form. For provider-run payroll, use the provider’s official pay stub.</p>'
    elif type_ in {'assets','asset'}:
        assets=asset_state(ledger)
        if type_=='assets':
            title='Equipment & fixed-asset register';subtitle='Book values · straight-line depreciation'
            body=table(['Equipment','Purchase date','Cost','Accumulated depreciation','Net book value','Status'],[[a['name'],a['purchaseDate'],money(a['cost']),money(a['accumulated']),money(a['bookValue']),'Disposed '+a['disposedAt'] if a.get('disposedAt') else 'Active'] for a in assets])
        else:
            a=next((a for a in assets if a['id']==args.get('id')),None)
            if not a:raise AccountingError('Equipment not found')
            title='Equipment depreciation schedule';subtitle=a['name']
            body=total('Cost',a['cost'])+total('Residual value',a['salvage'])+table(['Month','Depreciation','Status'],[[r['month'],money(r['amount']),'Posted' if r['posted'] else 'Scheduled'] for r in a['schedule']])
        body+='<p class="note">Full-month book depreciation. This schedule does not determine tax depreciation, Section 179 or bonus depreciation.</p>'
    elif type_=='tax-liabilities':
        title='Tax & payroll liability summary';subtitle='Posted accounting balances · not a filing or remittance confirmation'
        body=table(['Account','Liability balance'],[[a['code']+' '+a['name'],money(-a['balance'])] for a in report['trial'] if a['type']=='liability' and a['code'].startswith(('21','22'))])
    elif type_=='inventory':
        title='Inventory & replenishment planning';subtitle='Source stock shown separately; overlapping stock is not consolidated'
        items=[(r['source'],json.loads(r['payload'])) for r in ledger.db.execute('SELECT * FROM catalog ORDER BY source,source_id')]
        body=table(['Source','Item','SKU','Location','On hand','Reserved','Case size'],[[s,p['name'],p['sku'],p['location'],p['onHand'],p['reserved'],p['caseQty']] for s,p in items])
    elif type_ in {'recipe','pricing'}:
        table_= 'recipes' if type_=='recipe' else 'pricing'
        r=ledger.db.execute('SELECT * FROM '+table_+' WHERE id=?',(args.get('id'),)).fetchone()
        if not r:raise AccountingError('Saved cost or pricing plan not found')
        result=json.loads(r['result']);title='Production cost sheet' if type_=='recipe' else 'Retail & wholesale price plan';subtitle=r['name']
        if type_=='recipe':
            body=table(['Component','Type','Quantity','Unit','Unit cost ($)','Total'],[[m['name'],m['kind'],m['quantity'],m['unit'],m['unitCost'],money(m['total'])] for m in result['materials']])+table(['Batch cost','Amount'],[[k.title(),money(result[k])] for k in ['ingredients','packaging','labor','overhead','other']])+total('Total batch cost',result['total'])+total('Cost per sellable unit',result['unitCost'])+total('Suggested selling price',result['suggestedPrice'])+'<p>Sellable units: '+e(result['sellableUnits'])+' · Target margin: '+e(result['targetMargin'])+'%</p>'
        else:body=table(['Channel','Unit price','Cost incl. fees','Unit profit','Margin','Case revenue'],[[c['name'],money(c['price']),money(c['cost']),money(c['profit']),f"{c['margin']:.2f}%" if c['margin'] is not None else '—',money(c['caseRevenue'])] for c in result['channels']])
        body+='<p class="note">Planning estimate. This document does not post an accounting entry or change source-app prices.</p>'
    else:raise AccountingError('Unknown print document type')
    if ledger.db.execute("SELECT 1 FROM documents WHERE kind='needs-cost'").fetchone() and type_ in {'profit-loss','balance-sheet','trial-balance'}:
        body='<p class="warning">Historical inventory costs remain unresolved. These statements exclude those missing cost postings.</p>'+body
    company=ledger.settings()
    header='<div class="print-brand">BACKWOODS <span>BUSINESS ACCOUNTING</span></div><h1>'+e(title)+'</h1><p class="subtitle">'+e(subtitle)+'</p><div class="company"><strong>'+e(company['company'])+'</strong><p>'+e(company.get('company_address',''))+'</p><p>'+e(company.get('company_phone',''))+'</p></div>'
    with ledger.db:ledger.audit('print-view-opened',{'type':type_,'id':args.get('id'),'source':args.get('source')})
    return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+e(title)+' · '+e(company['company'])+'</title><link rel="stylesheet" href="/print.css"><script defer src="/print.js"></script></head><body><div class="toolbar"><button id="print-button">Print / Save PDF</button><span>Use your printer or select Save as PDF in the print dialog.</span></div><article>'+header+'<section>'+body+'</section><footer>Backwoods Business Accounting · '+e(company['company'])+' · Accrual basis · USD</footer></article></body></html>'

"""Explicit fixed-asset schedules and payroll records, without tax-rate guesses."""
import calendar
import json
import uuid
from datetime import date
from .ledger import AccountingError,cents,day
from .imports import record,pair,line


def positive_amount(value,label,zero=False):
    amount=cents(value)
    if amount<0 or (not zero and not amount):raise AccountingError(label+' must be '+('nonnegative' if zero else 'positive'))
    return amount


def add_month(month,offset):
    y,m=map(int,month.split('-'))
    absolute=y*12+m-1+offset
    return f'{absolute//12:04d}-{absolute%12+1:02d}'


def schedule(asset):
    depreciable=asset['cost']-asset['salvage']
    base,remainder=divmod(depreciable,asset['lifeMonths'])
    result=[]
    for index in range(asset['lifeMonths']):
        month=add_month(asset['startMonth'],index)
        y,m=map(int,month.split('-'))
        result.append({'month':month,'date':f'{month}-{calendar.monthrange(y,m)[1]}','amount':base+(1 if index<remainder else 0)})
    return result


def register_asset(ledger,value):
    name=str(value.get('name','')).strip()
    if not name:raise AccountingError('Equipment name required')
    cost=positive_amount(value.get('cost'),'Asset cost')
    salvage=positive_amount(value.get('salvage',0),'Salvage value',True)
    life=int(value.get('lifeMonths',0))
    if life<1 or life>600 or salvage>cost:raise AccountingError('Useful life must be 1–600 months and salvage cannot exceed cost')
    purchase=day(value.get('purchaseDate'))
    start=day(str(value.get('startMonth'))+'-01')[:7]
    if start<purchase[:7]:raise AccountingError('Depreciation cannot begin before purchase')
    aid=str(uuid.uuid4())
    asset={'id':aid,'name':name,'cost':cost,'salvage':salvage,'lifeMonths':life,'purchaseDate':purchase,'startMonth':start,
           'serialNumber':str(value.get('serialNumber','')),'location':str(value.get('location','')),'notes':str(value.get('notes','')),
           'assetAccount':'1500','accumulatedAccount':'1590','expenseAccount':'6100'}
    if value.get('postPurchase'):
        credit=str(value.get('fundingAccount','1020'))
        if credit not in {'1010','1020','2000','2500','3000'}:raise AccountingError('Choose bank, cash, accounts payable, loan or owner funding')
        doc=record('bill' if credit=='2000' else 'asset-purchase',{'id':aid,'date':purchase,'memo':'Equipment acquisition: '+name},pair('1500',credit,cost),amount=cost,balance=cost if credit=='2000' else 0,party=value.get('supplier',''),reference=value.get('reference') or aid)
        asset['linkedSource']='manual';asset['linkedId']=doc['id']
        return ledger.import_documents('manual',[doc],value,'Equipment acquisition',assets=[asset])
    source=str(value.get('linkedSource','manual'));sid=str(value.get('linkedId',''))
    r=ledger.db.execute('SELECT payload FROM documents WHERE source=? AND source_id=?',(source,sid)).fetchone()
    if not r:raise AccountingError('Link the asset to an existing equipment purchase, or choose Record purchase')
    existing=json.loads(r[0]);available=sum(l['debit']-l['credit'] for l in existing['lines'] if l['account']=='1500')
    registered=sum(json.loads(r[0])['cost'] for r in ledger.db.execute('SELECT payload FROM assets') if json.loads(r[0]).get('linkedSource')==source and json.loads(r[0]).get('linkedId')==sid)
    if available-registered<cost:raise AccountingError('Linked transaction does not contain enough unregistered 1500 Fixed Assets cost')
    asset['linkedSource']=source;asset['linkedId']=sid
    return ledger.import_documents('manual',[],value,'Register existing equipment',assets=[asset])


def asset_state(ledger):
    assets=[]
    for r in ledger.db.execute('SELECT payload FROM assets'):
        asset=json.loads(r[0])
        postings={d['source_id']:json.loads(d['payload']) for d in ledger.db.execute("SELECT source_id,payload FROM documents WHERE source='manual' AND kind='depreciation'")}
        asset['schedule']=schedule(asset)
        for row in asset['schedule']:row['posted']=f"depreciation:{asset['id']}:{row['month']}" in postings
        asset['accumulated']=sum(row['amount'] for row in asset['schedule'] if row['posted'])
        asset['bookValue']=asset['cost']-asset['accumulated']
        assets.append(asset)
    return assets


def depreciate(ledger,value):
    asset=next((a for a in asset_state(ledger) if a['id']==value.get('id')),None)
    if not asset:raise AccountingError('Asset not found')
    if asset.get('disposedAt'):raise AccountingError('Asset is already disposed')
    through=day(str(value.get('throughMonth'))+'-01')[:7]
    docs=[]
    for row in asset['schedule']:
        if row['month']>through or row['posted'] or not row['amount']:continue
        if row['date']>date.today().isoformat():raise AccountingError('Future depreciation months cannot be posted')
        docs.append(record('depreciation',{'id':asset['id']+':'+row['month'],'date':row['date'],'memo':'Straight-line depreciation: '+asset['name']},pair('6100','1590',row['amount']),amount=row['amount'],reference=asset['name']+' '+row['month']))
    if not docs:raise AccountingError('No unposted depreciation is due through this month')
    return ledger.import_documents('manual',docs,value,'Monthly equipment depreciation')


def dispose_asset(ledger,value):
    asset=next((a for a in asset_state(ledger) if a['id']==value.get('id')),None)
    if not asset or asset.get('disposedAt'):raise AccountingError('Choose an active registered asset')
    date_=day(value.get('date'));proceeds=positive_amount(value.get('proceeds',0),'Sale proceeds',True)
    if date_<asset['purchaseDate'] or any(row['posted'] and row['date']>date_ for row in asset['schedule']):raise AccountingError('Disposal date is before the purchase or an existing depreciation posting')
    rows=[line('1500',credit=asset['cost'])]
    if asset['accumulated']:rows.append(line('1590',asset['accumulated']))
    if proceeds:rows.append(line('1020',proceeds))
    difference=proceeds-asset['bookValue']
    if difference>0:rows.append(line('4800',credit=difference))
    elif difference<0:rows.append(line('6200',-difference))
    doc=record('asset-disposal',{'id':asset['id'],'date':date_,'memo':'Equipment disposal: '+asset['name']},rows,amount=proceeds)
    persisted={k:v for k,v in asset.items() if k not in {'schedule','accumulated','bookValue'}}
    persisted['disposedAt']=date_
    return ledger.import_documents('manual',[doc],value,'Equipment disposal',assets=[persisted])


PAYROLL_FIELDS={
    'federal':'2151','state':'2152','socialSecurity':'2153','medicare':'2154','deductions':'2155',
    'employerSocialSecurity':'2153','employerMedicare':'2154','employerUnemployment':'2156',
}


def payroll_preview(value):
    gross=positive_amount(value.get('gross'),'Gross wages')
    amounts={k:positive_amount(value.get(k,0),k,True) for k in PAYROLL_FIELDS}
    withheld=sum(amounts[k] for k in ['federal','state','socialSecurity','medicare','deductions'])
    employer=sum(amounts[k] for k in ['employerSocialSecurity','employerMedicare','employerUnemployment'])
    if withheld>gross:raise AccountingError('Employee deductions exceed gross pay')
    net=gross-withheld
    paid=value.get('paid') is True
    rows=pair('5200','1020' if paid else '2200',net)
    if withheld:rows.append(line('5200',withheld))
    if employer:rows.append(line('5210',employer))
    for k,account in PAYROLL_FIELDS.items():
        if amounts[k]:rows.append(line(account,credit=amounts[k]))
    return {'gross':gross,'withheld':withheld,'net':net,'employerTaxes':employer,'totalEmployerCost':gross+employer,'amounts':amounts,'lines':rows}


def post_payroll(ledger,value):
    employee=ledger.db.execute('SELECT id,name FROM employees WHERE id=?',(value.get('employeeId'),)).fetchone()
    if not employee:raise AccountingError('Choose a registered employee')
    start=day(value.get('periodStart'));end=day(value.get('periodEnd'));date_=day(value.get('date'))
    if start>end:raise AccountingError('Payroll period ends before it begins')
    for r in ledger.db.execute("SELECT payload FROM documents WHERE source='manual' AND kind='payroll'"):
        original=json.loads(r[0])['original']
        if original['employeeId']==employee['id'] and not (end<original['periodStart'] or start>original['periodEnd']):
            raise AccountingError('This employee already has payroll overlapping this period')
    result=payroll_preview(value)
    original={**value,'id':str(uuid.uuid4()),'date':date_,'employeeName':employee['name'],'calculation':result}
    doc=record('payroll',original,result['lines'],amount=result['gross'],balance=0 if value.get('paid') is True else result['net'],party=employee['name'],reference=str(value.get('reference') or f'{employee["name"]} {start} — {end}'))
    return ledger.import_documents('manual',[doc],value,'Business payroll record')


def pay_payroll(ledger,value):
    r=ledger.db.execute("SELECT payload FROM documents WHERE source='manual' AND source_id=? AND kind='payroll'",(value.get('id'),)).fetchone()
    if not r:raise AccountingError('Payroll record not found')
    doc=json.loads(r[0]);amount=doc['balance']
    if amount<=0:raise AccountingError('This payroll has no unpaid net wages')
    doc['balance']=0;doc['original']['paidAt']=day(value.get('date'))
    payment=record('payroll-payment',{'id':str(uuid.uuid4()),'date':value.get('date'),'memo':'Net payroll payment: '+doc['party']},pair('2200','1020',amount),amount=amount,party=doc['party'])
    return ledger.import_documents('manual',[doc,payment],value,'Payroll payment record')

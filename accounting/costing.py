"""Production estimates. Intentionally never posts to the general ledger."""
from decimal import Decimal, ROUND_HALF_UP
from .ledger import AccountingError, cents


def number(value,name,positive=False):
    try:
        n=Decimal(str(value))
        if not n.is_finite() or n<0 or n>1_000_000_000 or (positive and not n):raise ValueError()
        return n
    except Exception as exc:
        raise AccountingError(f"{name} must be {'positive' if positive else 'nonnegative'} and finite") from exc


def calculate(value):
    if not str(value.get("name","")).strip():raise AccountingError("Give this product or recipe a name")
    yield_=number(value.get("yieldUnits"),"Batch yield",True)
    waste=number(value.get("wastePercent",0),"Waste percentage")
    margin=number(value.get("targetMargin",40),"Target margin")
    if waste>=100 or margin>=100:raise AccountingError("Waste and margin percentages must be below 100")
    sellable=yield_*(1-waste/100)
    materials=[]
    if not isinstance(value.get("materials"),list) or not value["materials"]:raise AccountingError("Add at least one ingredient or packaging component")
    if len(value["materials"])>200:raise AccountingError("A recipe supports up to 200 components")
    total_materials=0
    packaging=0
    for row in value["materials"]:
        if not str(row.get("name","")).strip():raise AccountingError("Every component needs a name")
        qty=number(row.get("quantity",0),"Component quantity")
        cost=number(row.get("unitCost",0),"Component unit cost")
        total=cents(qty*cost)
        is_packaging=row.get("kind")=="packaging"
        if is_packaging:packaging+=total
        else:total_materials+=total
        materials.append({"name":str(row["name"]),"kind":"packaging" if is_packaging else "ingredient","unit":str(row.get("unit", "")),"quantity":float(qty),"unitCost":float(cost),"total":total})
    labor_hours=number(value.get("laborHours",0),"Labor hours")
    rate=number(value.get("laborRate",0),"Hourly labor cost")
    burden=number(value.get("laborBurdenPercent",0),"Payroll burden percentage")
    labor=cents(labor_hours*rate*(1+burden/100))
    overhead=cents(number(value.get("overhead",0),"Batch overhead"))
    other=cents(number(value.get("otherCost",0),"Other batch cost"))
    total=total_materials+packaging+labor+overhead+other
    unit=Decimal(total)/sellable # fractional cents retained for pricing math
    price=number(value.get("sellingPrice",0),"Selling price")
    price_cents=price*100
    # Round suggested prices UP to avoid recommending below the target margin.
    suggested=int((unit/(1-margin/100)).to_integral_value(rounding='ROUND_CEILING'))
    unit_rounded=int(unit.quantize(Decimal(1),rounding=ROUND_HALF_UP))
    unit_profit=price_cents-unit
    return {"name":str(value["name"]).strip(),"materials":materials,"ingredients":total_materials,"packaging":packaging,"labor":labor,
            "overhead":overhead,"other":other,"total":total,"sellableUnits":float(sellable),"yieldUnits":float(yield_),
            "unitCost":unit_rounded,"unitCostPrecise":float(unit/100),"suggestedPrice":suggested,
            "sellingPrice":cents(price),"unitProfit":int(unit_profit.quantize(Decimal(1),rounding=ROUND_HALF_UP)),
            "grossMargin":float(unit_profit/price_cents*100) if price_cents else None,
            "markup":float(unit_profit/unit*100) if unit else None,"targetMargin":float(margin),
            "estimatedBatchRevenue":cents(price*sellable),"estimatedBatchProfit":cents(price*sellable)-total}


def price_channels(value):
    if not str(value.get('name','')).strip():raise AccountingError('Product name required')
    unit=number(value.get('unitCost'),'Production / landed unit cost')
    case=number(value.get('caseQty',1),'Units per case',True)
    retail=number(value.get('retailPrice',0),'Retail price')
    wholesale=number(value.get('wholesalePrice',0),'Wholesale unit price')
    distributor=number(value.get('distributorPrice',0),'Distributor unit price')
    fee=number(value.get('retailFeePercent',0),'Retail selling fee')
    delivery=number(value.get('deliveryPerCase',0),'Delivery cost per case')
    wholesale_fee=number(value.get('wholesaleFeePercent',0),'Wholesale selling fee')
    target=number(value.get('targetMargin',35),'Target margin')
    if max(fee,wholesale_fee,target)>=100:raise AccountingError('Fee and margin percentages must be below 100')
    channels=[]
    for name,price,fees,freight in [('Retail',retail,fee,Decimal(0)),('Wholesale',wholesale,wholesale_fee,delivery/case),('Distributor',distributor,wholesale_fee,delivery/case)]:
        costs=unit+freight+price*fees/100
        profit=price-costs
        denominator=1-(target+fees)/100
        suggested=cents((unit+freight)/denominator) if denominator>0 else None
        channels.append({'name':name,'price':cents(price),'cost':cents(costs),'profit':cents(profit),
            'margin':float(profit/price*100) if price else None,'caseRevenue':cents(price*case),'caseProfit':cents(profit*case),
            'suggestedPrice':suggested,'belowCost':price<costs})
    return {'name':str(value['name']).strip(),'caseQty':float(case),'caseCost':cents(unit*case),'channels':channels,
        'retailerMargin':float((retail-wholesale)/retail*100) if retail else None}

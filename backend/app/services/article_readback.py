"""Fresh SQL comparison of all mapped article fields after an authorized SAVE."""
from decimal import Decimal,InvalidOperation
from app.services import chat_tools

MAPPING={'ITM0_1.DES1AXX':['ITMDES1_0'],'ITM0_1.TCLCOD':['TCLCOD_0'],'ITM0_1.ITMSTA':['ITMSTA_0'],
 'ITM3_1.STU':['STU_0'],'ITM3_1.PUU':['PUU_0'],'ITM3_1.SAU':['SAU_0'],
 'ITM3_1.PUUSTUCOE':['PUUSTUCOE_0'],'ITM3_1.SAUSTUCOE':['SAUSTUCOE_0'],
 'ITM5_1.ACCCOD':['ACCCOD_0'],'ITM5_1.VACITM':['VACITM_0','VACITM_1','VACITM_2'],
 'ITM2_1.STOMGTCOD':['STOMGTCOD_0'],'ITM2_3.LOTMGTCOD':['LOTMGTCOD_0']}


def compare(operation,article):
    code=article['code_article'];calls=[{'id':'record','tool':'get_article_record','args':{'Code':code}}]
    supplier=article.get('code_fournisseur')
    if supplier:calls.append({'id':'supplier','tool':'get_supplier_article_references','args':{'Code':code,'Supplier':supplier}})
    try:reads=chat_tools.run(calls)
    except Exception:reads={}
    record=reads.get('record',{});rows=record.get('rows',[])
    valid=record.get('ok') is True and record.get('source')=='SQL TEST' and len(rows)==1
    row=rows[0] if valid else {};comparison={};errors=[]
    comparison['ITMREF_0']=row.get('ITMREF_0')==code
    for field in operation.get('payload',{}).get('fields',[]):
        path=field['group']+'.'+field['name'];value=field['value']
        if path=='ITP_1.BPSNUM':
            comparison['supplier_link']=reads.get('supplier',{}).get('ok') is True and any(str(r.get('BPSNUM_0','')).strip()==value and str(r.get('ITMREF_0','')).strip()==code for r in reads.get('supplier',{}).get('rows',[]));continue
        columns=MAPPING.get(path)
        if not columns:errors.append('unverified_sql_mapping:'+path);continue
        expected=value if isinstance(value,list) else [value]
        if len(expected)!=len(columns):errors.append('unverified_sql_dimension:'+path);continue
        for column,want in zip(columns,expected):
            got=row.get(column)
            if path.endswith('COE'):
                try:ok=got is not None and Decimal(str(got))==Decimal(want)
                except (InvalidOperation,ValueError):ok=False
            else:ok=got is not None and str(got).strip()==want.strip()
            comparison[column]=ok
    if not valid:errors.append('article_sql_readback_unavailable')
    confirmed=(operation.get('status')=='succeeded' and operation.get('result',{}).get('status')==1
        and operation.get('after_record',{}).get('exists') is True and valid and bool(comparison) and all(comparison.values()) and not errors)
    return {'confirmed':confirmed,'comparisons':comparison,'errors':errors,'sql_readback':{'ok':valid,'folder':'TEST','article':rows if valid else [],'supplier':reads.get('supplier',{})},
            'site_creation_executed':False,'retry_allowed':False}

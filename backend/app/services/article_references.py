"""Read-only business choices; accounting codes and tax levels stay distinct."""
import re
from decimal import Decimal,InvalidOperation
from app.services.chat_turns import norm

def text(value):return str(value or '').strip()

def accounting(schema,query=''):
    query=norm(query).strip(' .')
    found={}
    for row in schema.get('accounting',[]):
        code=text(row.get('ACCCOD_0'));label=text(row.get('DES_0'))
        accounts=sorted({text(value) for key,value in row.items() if re.fullmatch(r'ACC_\d+',key) and text(value)})
        if query and not (norm(code).startswith(query) or query in norm(label) or any(norm(account).startswith(query) for account in accounts)):continue
        if code:found[(code,text(row.get('COA_0'))) ]={'code':code,'label':label,'plan':text(row.get('COA_0')),'accounts':accounts,'requires_selection':True}
    return sorted(found.values(),key=lambda item:(item['code'],item['plan']))

def taxes(schema,rate=None):
    wanted=None
    if rate is not None:
        try:wanted=Decimal(str(rate).strip().rstrip('%').replace(',','.'))
        except InvalidOperation:return []
    levels={text(row.get('VACITM_0')):row for row in schema.get('tax_levels',[]) if row.get('ENAFLG_0',2)==2}
    values={}
    for tax in schema.get('taxes',[]):
        try:tax_rate=Decimal(str(tax.get('VATRAT_0')))
        except InvalidOperation:continue
        if wanted is not None and tax_rate!=wanted:continue
        vat=text(tax.get('VAT_0'))
        for rule in schema.get('tax_determinations',[]):
            code=text(rule.get('VACITM_0'))
            if text(rule.get('VAT_0'))!=vat or code not in levels or rule.get('ENAFLG_0',2)!=2:continue
            expression=text(rule.get('EXPTST_0'))
            simple='[F:TLK]VACBPR="'+text(rule.get('VACBPR_0'))+'" & [F:TLK]VACITM="'+code+'"'
            item={'code':code,'label':text(levels[code].get('DESAXX_0') or levels[code].get('DES_0') or rule.get('VACDES_0')),
                  'tax_code':vat,'rate':str(tax_rate),'regime':text(rule.get('VACBPR_0')),
                  'conditional':any(text(rule.get(key)) for key in ('EXP1_0','EXP2_0')) or expression not in ('',simple),'requires_selection':True}
            values[(code,vat,item['regime'],item['rate'])]=item
    if wanted is None:
        for code,row in levels.items():
            if not any(key[0]==code for key in values):values[(code,'','','')]={'code':code,'label':text(row.get('DESAXX_0') or row.get('DES_0')),'tax_code':None,'rate':None,'regime':None,'conditional':True,'requires_selection':True}
    return sorted(values.values(),key=lambda item:(item['code'],item.get('regime') or '',item.get('tax_code') or ''))

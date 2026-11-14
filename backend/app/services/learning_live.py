"""Fresh TEST reads, never persisted as knowledge or training examples."""
import json,subprocess,re
from datetime import date
from decimal import Decimal
from app.services import supplier_sql,learning,sage_crud as crud

def read(kind,code,site='',company='',ledger='',date_from='',date_to=''):
    if kind not in ('stock','balance','code') or not code or any(len(v)>30 for v in (code,site,company,ledger)):raise crud.CrudError('Précisez les codes à consulter.',422)
    if kind=='stock' and not site:raise crud.CrudError('Précisez le site pour consulter le stock.',422)
    if kind=='balance':
        if not company or not ledger:raise crud.CrudError('Précisez la société et le référentiel comptable.',422)
        try:
            if date.fromisoformat(date_from)>date.fromisoformat(date_to):raise ValueError()
        except ValueError:raise crud.CrudError('Période comptable invalide.',422) from None
    request={'folder':'TEST','kind':kind,'code':code,'site':site,'company':company,'ledger':ledger,'date_from':date_from,'date_to':date_to}
    try:
        p=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-File',str(learning.ROOT/'TEST/learning_live_worker.ps1')],
            input=json.dumps(request),capture_output=True,text=True,encoding='utf-8',timeout=25,env=supplier_sql.connection_env(),creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        result=json.loads(p.stdout.lstrip('\ufeff'))
        if result.get('ok') is not True:raise ValueError()
    except (OSError,ValueError,subprocess.TimeoutExpired):raise crud.CrudError('Consultation actuelle indisponible ou droits insuffisants. Aucune ancienne valeur ne sera utilisée.',503) from None
    if kind=='balance':
        totals={}
        for row in result['rows']:
            if row['Sens'] not in (-1,1):raise crud.CrudError('Sens comptable non reconnu : solde non calculé.',409)
            currency=row['Devise'];totals[currency]=totals.get(currency,Decimal(0))+Decimal(row['Montant'])*row['Sens']
        result['totals']=[{'Devise':currency,'Solde_signe':str(total)} for currency,total in totals.items()]
        result['definition']='Somme des montants du référentiel multipliés par leur sens, sur la période et le compte demandés ; devises séparées.'
    if kind=='stock':result['definition']='Quantités en unité de stock, par statut. Les réservations ne sont pas déduites pour produire un stock disponible.'
    return result

def answer(text):
    from app.services.chat_turns import norm
    n=norm(text)
    if not re.match(r'^(?:quel|quels|quelle|quelles|donne|affiche|consulte|stock\b|solde\b|le code\b)',n.strip()):return None
    def code(label):
        m=re.search(r'\b'+label+r'\s*[:=]?\s*([a-z0-9_.-]+)',n,re.I)
        return m[1].upper() if m else ''
    if re.search(r'\bstocks?\b',n):
        article=code('article');site=code('site')
        if not article or not site:return 'Pour consulter le stock actuel, indiquez le code article et le site, par exemple « Affiche le stock article CODE site SITE ». '
        result=read('stock',article,site=site)
    elif re.search(r'\bsolde\b',n):
        account=code('compte');company=code('societe');ledger=code('referentiel');dates=re.findall(r'\b\d{4}-\d{2}-\d{2}\b',text)
        if not account or not company or not ledger or len(dates)!=2:return 'Pour consulter le solde actuel, indiquez le compte, la société, le référentiel et les deux dates de la période (AAAA-MM-JJ).'
        result=read('balance',account,company=company,ledger=ledger,date_from=dates[0],date_to=dates[1])
    elif re.search(r'\bcode\b',n) and re.search(r'\b(disponible|libre|existe|utilise)\b',n):
        m=re.search(r'\bf[0-9]{1,14}\b',n)
        if not m:return 'Indiquez le code fournisseur exact à vérifier.'
        result=read('code',m[0].upper())
    else:return None
    rows=result.get('totals') or result.get('rows') or []
    return 'Consultation actuelle dans TEST ('+result['checked_at']+') :\n\n'+('\n'.join(' · '.join(str(k).replace('_',' ')+': '+str(v) for k,v in row.items()) for row in rows) if rows else 'Aucune ligne trouvée pour ces critères.')+'\n\n'+result.get('definition','Un code absent n’est pas réservé.')

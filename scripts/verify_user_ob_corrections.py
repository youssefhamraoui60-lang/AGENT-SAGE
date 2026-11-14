"""Verify workbook claims with fixed SELECT snapshots; workbook cells are data."""
import json,subprocess,concurrent.futures,collections,re
from pathlib import Path
from datetime import datetime
from openpyxl import load_workbook
from openpyxl.styles import Font,PatternFill,Alignment
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'runtime/sob-corrections-check-20261113';OUT.mkdir(exist_ok=True)
SOURCE=Path(r'C:\Users\youssef\Desktop\SOB-MESSAGES-AVEC-CORRECTIONS-OB.xlsx')
def read(kind):
    r=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-File',str(ROOT/'telegram-test/audit-read.ps1')],input=json.dumps({'kind':kind,'start':'2026-11-09','end':'2026-11-14'}),capture_output=True,encoding='utf-8',timeout=90)
    data=json.loads(r.stdout.lstrip('\ufeff'))
    if not data.get('ok'):raise RuntimeError('SQL read failed: '+kind)
    (OUT/(kind+'.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    return kind,data['rows']
def pieces(v):return [p.strip() for p in str(v or '').split(';')]
def number(v):return float(str(v).replace(',','.').replace(' ',''))
def tuples(rows):return sorted((r['ITMREF_0'].strip(),round(float(r['QTY_0']),6),r['SAU_0'].strip(),round(float(r['NETPRIATI_0']),6)) for r in rows)
def main():
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        data=dict(pool.map(read,['orders','test_orders_audit','customers','articles','test_customer_catalog','test_article_catalog']))
    ob=collections.defaultdict(list);test=collections.defaultdict(list)
    for r in data['orders']:ob[r['SOHNUM_0']].append(r)
    for r in data['test_orders_audit']:test[r['SOHNUM_0']].append(r)
    clients={r['BPCNUM_0'].strip():r for r in data['customers']};articles={r['ITMREF_0'].strip():r for r in data['articles']}
    tc={r['BPCNUM_0'].strip():r for r in data['test_customer_catalog']};ta={r['ITMREF_0'].strip():r for r in data['test_article_catalog']}
    wb=load_workbook(SOURCE);ws=wb.worksheets[0];original=list(ws.values);report=[]
    cols=['Vérification directe OB 13/11','Nom officiel client OB','Écarts fichier / OB','Lignes réelles OB (code | qté | unité | prix)','Référentiels TEST vérifiés','Commandes TEST candidates (même client)','Limites / conclusion vérifiée']
    for j,h in enumerate(cols,19):ws.cell(1,j,h)
    for idx,row in enumerate(original[1:],2):
        ids,code,order=str(row[0]),str(row[8] or '').strip(),str(row[9] or '').strip()
        codes=[c for c in pieces(row[10]) if c];issues=[];details=[]
        official=clients.get(code,{}).get('BPCNAM_0','');actual=ob.get(order,[])
        if order:
            if not actual:status='Commande non retrouvée dans la fenêtre';issues.append('OB du 09 au 13/11, société 20 uniquement')
            else:
                if actual[0]['BPCORD_0'].strip()!=code:issues.append('Client différent : '+actual[0]['BPCORD_0'])
                try:
                    qs,us,ps=pieces(row[12]),pieces(row[13]),pieces(row[14])
                    if len({len(codes),len(qs),len(us),len(ps)})!=1:issues.append('Liste de lignes incomplète dans le fichier')
                    else:
                        expected=sorted((c,round(number(q),6),u,round(number(p),6)) for c,q,u,p in zip(codes,qs,us,ps))
                        if expected!=tuples(actual):issues.append('Articles/quantités/unités/prix du fichier différents de la commande OB')
                except ValueError:issues.append('Valeurs chiffrées non comparables')
                status='Conforme aux lignes OB' if not issues else 'Écart avec OB'
                details=[' | '.join(map(str,t)) for t in tuples(actual)]
        else:status='Aucune commande OB indiquée'
        checks=[]
        if code:checks.append('Client TEST : '+('présent' if code in tc else 'ABSENT'))
        for c in codes:
            if c not in articles:checks.append(c+' : ABSENT OB');continue
            if c not in ta:checks.append(c+' : ABSENT TEST');continue
            dif=[k for k in ['ITMDES1_0','SAU_0','STU_0','SAUSTUCOE_0'] if str(articles[c].get(k,'')).strip()!=str(ta[c].get(k,'')).strip()]
            checks.append(c+' : '+('diffère OB/TEST ('+', '.join(dif)+')' if dif else 'fiche OB/TEST concordante')+(' ; site 201 ABSENT' if not ta[c].get('SITE_OK') else ''))
        candidates=[{'number':n,'same_lines':tuples(rr)==tuples(actual) if actual else False,'lines':tuples(rr)} for n,rr in test.items() if code and rr[0]['BPCORD_0'].strip()==code]
        limit='L’existence des lignes dans OB ne prouve ni la règle générale de conversion ni l’absence de commande TEST. Vérifier le lien au message source.'
        if not order and codes:limit='Références contrôlées dans le catalogue ; aucune commande précise ni client confirmés par cette ligne.'
        if not order and not codes:limit='Pas de correction exploitable dans cette ligne. Les pièces originales restent disponibles dans l’audit précédent.'
        if ids=='5222':limit='Écart source : 36 tonnes, contre 805 sacs dans OB. CPJ55 et CPJ55_PP sont des codes distincts ; ne pas assimiler sans contrôle.'
        if ids=='5315, 5316, 5317':limit='Le lien OB concerne seulement Moncif (5315). Travemac (5316/5317) est un autre client : séparer les commandes.'
        if ids=='5214, 5215, 5216, 5217':limit='Les quantités sont aussi visibles sur la photo originale. Prix OB du T6 : 9,80, alors que le complément indique 9,50 sans exception explicite.'
        if ids=='5242':limit='OB contient bien CPJ45 et transport 50 ; le message ne précise pas le grade CPJ ni les 50 de transport. Ne pas transformer ces ajouts OB en valeurs source.'
        if ids=='5354':limit='Source : 25 m³ ; référence proposée conditionnée en 30 m³. Ne pas substituer automatiquement.'
        values=[status,official,' ; '.join(issues),'\n'.join(details),'\n'.join(checks),json.dumps(candidates,ensure_ascii=False),limit]
        for j,v in enumerate(values,19):ws.cell(idx,j,v)
        report.append({'row':idx,'ids':ids,'order':order,'client':code,'official_name':official,'status':status,'issues':issues,'catalog_checks':checks,'test_candidates':candidates,'limit':limit})
    summary=wb.create_sheet('Vérification directe OB')
    counters=collections.Counter(r['status'] for r in report)
    for row in [('Contrôle','Résultat'),('Vérifié le',datetime.now().isoformat(timespec='seconds')),('Périmètre SQL','09–13/11/2026 inclus ; société 20 ; SELECT uniquement'),('Lignes du fichier',len(report)),*counters.items(),('Attention','Aucune donnée métier ni règle active modifiée. Conforme OB signifie égalité avec la saisie OB ; pas validation de toutes les interprétations.'),('Référentiels','Même code dans TEST ne suffit pas : désignation, unité, coefficient et site sont comparés.'),('Documents','Les pièces jointes sont déjà disponibles dans runtime/sob-quality-audit-20261112/attachments ; la remarque du fichier disant qu’elles sont indisponibles ne s’applique pas à notre environnement.')]:summary.append(row)
    summary.column_dimensions['A'].width=43;summary.column_dimensions['B'].width=125
    wb.active=wb.index(summary)
    for s in wb:
        s.freeze_panes='C2' if s==ws else 'A2';s.auto_filter.ref=s.dimensions
        for c in s[1]:c.font=Font(color='FFFFFF',bold=True);c.fill=PatternFill('solid',fgColor='17365D')
        for row in s.iter_rows(min_row=2):
            s.row_dimensions[row[0].row].height=90
            for cell in row:
                cell.alignment=Alignment(wrap_text=True,vertical='top')
                if isinstance(cell.value,str):cell.data_type='s';cell.value=cell.value[:32760]
    for j in range(19,26):ws.column_dimensions[ws.cell(1,j).column_letter].width=60 if j!=25 else 100
    dest=ROOT/'TEST/SOB-CORRECTIONS-VERIFIEES-OB-2026-11-13.xlsx';wb.save(dest)
    (OUT/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    check=load_workbook(dest);assert check.worksheets[0].max_row==63
    print(json.dumps({'file':str(dest),'counts':dict(counters),'claims':sum(bool(r['order']) for r in report),'differences':[r for r in report if r['issues']]},ensure_ascii=True))
if __name__=='__main__':main()

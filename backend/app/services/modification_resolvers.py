"""Resolvers use current TEST references; no remembered supplier values or write authority."""
import re,unicodedata
from difflib import SequenceMatcher
from decimal import Decimal,InvalidOperation
from app.services.modification_policy import block

def norm(value):return re.sub(r'[^a-z0-9]+',' ',''.join(c for c in unicodedata.normalize('NFKD',str(value)) if not unicodedata.combining(c)).casefold()).strip()
def clean(value):return str(value or '').strip()

class CategoryResolver:
    SYNONYMS={'negose':'negoce','marchndise':'negoce','marchondise':'negoce','marchndises':'negoce','marchandize':'negoce','negouse':'negoce','negos':'negoce','negosse':'negoce','marchandise':'negoce','marchandises':'negoce','negotse':'negoce'}
    def search(self,query,rows,profile=None,rejected=(),limit=3,confirmed_examples=(),include_incompatible=False):
        q=norm(query);q=' '.join(self.SYNONYMS.get(w,w) for w in q.split())
        if not q:return []
        # Only validated, authorized retrieval results may contribute general aliases.
        for example in confirmed_examples:
            if example.get('status')=='validated' and norm(example.get('from',''))==q:q=norm(example['to'])
        candidates=[]
        for row in rows:
            code=clean(row.get('TCLCOD_0'));label=clean(row.get('TCLDES_0'))
            if not code or clean(row.get('STOFCY_0')) or code in rejected or row.get('ENAFLG_0',2)!=2:continue
            conflicts=[k for k,v in (profile or {}).items() if clean(row.get(k)).casefold()!=clean(v).casefold()]
            if conflicts and not include_incompatible:continue
            score=1 if norm(code)==q else .99 if norm(label)==q else max(SequenceMatcher(None,q,norm(label)).ratio(),max((SequenceMatcher(None,q,w).ratio() for w in norm(label).split()),default=0)*.9)
            if score>=.45:candidates.append({'code':code,'label':label,'score':round(score,3),'compatible':not conflicts,'conflicts':conflicts,'parameters':{k:row[k] for k in ('STOMGTCOD_0','PURFLG_0','SALFLG_0','STU_0','ACCCOD_0','VACITM_0') if k in row},'source':'TEST.ITMCATEG','requires_selection':True})
        return sorted(candidates,key=lambda r:(-r['score'],r['code']))[:min(limit,5)]

class UnitResolver:
    def search(self,query,rows,limit=10):
        q=norm(query).replace('metres','metre').replace('carres','carre')
        choices={}
        for row in rows:
            code=clean(row.get('UOM_0'));label=clean(row.get('label') or row.get('TEXTE_0') or row.get('UOMSYM_0') or code)
            if not code:continue
            texts=[norm(code),norm(label),norm(row.get('UOMSYM_0',''))]
            score=1 if q in texts else .95 if q and any(q in t for t in texts) else max((SequenceMatcher(None,q,t).ratio() for t in texts if t),default=0)
            if (not q or score>=.5) and (code not in choices or score>choices[code]['score']):choices[code]={'code':code,'label':label,'score':round(score,3),'requires_selection':q not in texts,'source':'TABUNIT / ATEXTRA'}
        return sorted(choices.values(),key=lambda r:(-r['score'],r['code']))[:limit]
    def find(self,code,snapshot):
        rows=[r for r in snapshot.get('units',[]) if clean(r.get('UOM_0'))==code]
        if len(rows)!=1:block('Unité '+code+' absente ou ambiguë. Réutilisez une unité existante ou préparez sa création séparément.')
        return rows[0]
    def coefficient(self,source,target,snapshot,declared=None):
        self.find(source,snapshot);self.find(target,snapshot)
        if source==target:value=Decimal(1)
        else:
            rows=[r for r in snapshot.get('conversions',[]) if clean(r.get('UOM1_0'))==source and clean(r.get('UOM2_0'))==target]
            inverse=[r for r in snapshot.get('conversions',[]) if clean(r.get('UOM1_0'))==target and clean(r.get('UOM2_0'))==source]
            if len(rows)!=1 or len(inverse)!=1:block('Conversion '+source+' → '+target+' ou conversion inverse absente/ambiguë. Aucun coefficient ne sera inventé.')
            value=Decimal(str(rows[0]['COEUOM_0']));back=Decimal(str(inverse[0]['COEUOM_0']))
            if value<=0 or back<=0 or abs(value*back-1)>Decimal('.0000001'):block('Coefficients de conversion incohérents.')
        if declared is not None:
            if type(declared) is float:block('Indiquez le coefficient sous forme de texte décimal exact, pour éviter un arrondi JSON.')
            try:requested=Decimal(str(declared))
            except InvalidOperation:block('Coefficient illisible ; indiquez une valeur numérique exacte.')
            if not requested.is_finite():block('Coefficient non fini interdit.')
            if requested!=value:block('Le coefficient demandé diffère du coefficient enregistré. La conversion existante ne sera pas modifiée automatiquement.')
        return format(value,'f')

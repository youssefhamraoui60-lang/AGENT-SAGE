"""Read-only OB reference snapshot for large replay tests; no execution authority."""
import json
import re
from pathlib import Path
from understanding import normalized,choose_reference


class ReferenceSnapshot:
    def __init__(self,root):
        self.root=Path(root)
        self.customers=self.load('customers')
        if (self.root/'ob-customer_identities.json').exists():
            identities={r['BPCNUM_0']:r for r in self.load('customer_identities')}
            self.customers=[{**r,**identities.get(r['BPCNUM_0'],{})} for r in self.customers]
        self.articles=self.load('articles')
        self.representatives=self.load('representatives')
        self.orders=self.load('orders')
        self.sites={r['ITMREF_0'] for r in self.load('article_sites')}
        self.last_prices={}
        for row in self.orders:
            key=(row['BPCORD_0'],row['ITMREF_0'])
            old=self.last_prices.get(key)
            rank=(str(row['ORDDAT_0']),str(row['CREDATTIM_0']),row['SOHNUM_0'],row['SOPLIN_0'])
            if old is None or rank>old[0]:self.last_prices[key]=(rank,row)

    def load(self,kind):
        data=json.loads((self.root/f'ob-{kind}.json').read_text(encoding='utf-8'))
        if not data['ok']:raise ValueError('Reference export failed: '+kind)
        return data['rows']

    @staticmethod
    def matches(query,name):
        terms=[normalized(w) for w in re.split(r'[\s._-]+',query) if normalized(w)]
        target=normalized(name)
        def ordered(words):
            start=0
            for word in words:
                at=target.find(word,start)
                if at<0:return False
                start=at+len(word)
            return True
        return ordered(terms) or ordered(list(reversed(terms)))

    def __call__(self,kind,code,client=None,*,folder='OB',_fallback=True,representative=None):
        if folder!='OB':raise ValueError('Snapshot is OB read-only')
        from prepare import canonical_article
        if kind=='client_by_ice':
            return [r for r in self.customers if str(r.get('XICE_0','')).strip()==code]
        if kind=='representative':
            import learning_memory
            alias=learning_memory.policy('contact_representatives',{}).get(normalized(code))
            if alias:code=alias
        if kind=='last_price':
            value=self.last_prices.get((client,code))
            if value is None:return []
            r=value[1]
            return [{'PRICE_TTC':r['NETPRIATI_0'],'SOHNUM_0':r['SOHNUM_0']}]
        if kind=='client':
            import learning_memory
            learned=learning_memory.client_alias(code,representative)
            if learned:code=learned
            codes=re.findall(r'\bC\d{4,8}\b',code,re.I)
            if len(set(c.upper() for c in codes))==1:code=codes[0].upper()
            pool,key,label=self.customers,'BPCNUM_0','BPCNAM_0'
        elif kind=='representative':pool,key,label=self.representatives,'REPNUM_0','REPNAM_0'
        elif kind=='article':
            code=canonical_article(code)
            pool,key,label=self.articles,'ITMREF_0','ITMDES1_0'
        else:raise ValueError('Unsupported snapshot tool')
        exact=[r for r in pool if normalized(r[key])==normalized(code)]
        if exact:rows=exact
        else:
            rows=[r for r in pool if self.matches(code,r[label])]
            if kind=='client' and representative:
                same=[r for r in rows if r['REP_0']==representative]
                if same:rows=same
            rows=sorted(rows,key=lambda r:r[key])[:25]
            if not rows and _fallback and kind in ('client','representative'):
                candidates={}
                for term in [w for w in re.findall(r'[A-Za-zÀ-ÿ0-9]+',code) if len(w)>=4][:3]:
                    for r in self(kind,term,client,folder=folder,_fallback=False,representative=representative):candidates[r[key]]=r
                rows=list(candidates.values())
            rows=choose_reference(kind,code,rows,{'REPNUM_0':representative} if representative else None)
        if kind=='article':
            rows=[{**r,'SITE_OK':int(r['ITMREF_0'] in self.sites)} for r in rows]
        return rows

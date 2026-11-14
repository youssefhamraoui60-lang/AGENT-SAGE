"""Execute the bounded SELECT registry against real TEST data, without writes."""
import sys,json
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.services import chat_tools as t
p=t.Plan()
t.search_articles(p,'XPS')
t.get_recent_articles(p,'NEG')
t.check_article_duplicate(p,'CPJ35')
t.get_article_categories(p,'NEG')
t.get_units(p,'UN','SAC')
p.add('get_unit_conversions',Unit='UN',Unit2='SAC')
t.get_sites(p,'201')
t.search_suppliers(p,'','F234')
t.get_supplier_article_references(p,'F234')
t.get_accounting_categories(p,code='CPJ35')
t.get_tax_rules(p,'20')
p.add('get_article_site',Code='CPJ35',Site='201')
results=t.run(p.calls)
category=next((r for r in results.values() if r['tool']=='get_article_categories'),{})
levels={r.get('VACITM_0','').strip() for r in category.get('rows',[]) if r.get('VACITM_0','').strip()}
offset=len(p.calls)
for level in sorted(levels)[:2]:p.add('get_tax_determination',Level=level)
results.update(t.run(p.calls[offset:]))
covered={r['tool'] for r in results.values()}
proof={'checked_at':datetime.now(timezone.utc).isoformat(),'database':'x3v12','schema':'TEST','writes':0,
       'calls':p.calls,'results':results,'tools_covered':sorted(covered),
       'status':'PASS' if covered==t.TOOLS and all(r['ok'] for r in results.values()) else 'INCOMPLETE',
       'note':'A successful SELECT with zero rows does not validate the requested business value.'}
(ROOT/'logs/chat-sql-tools-live.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
print(json.dumps({'status':proof['status'],'writes':0,'tools_covered':len(covered),'queries':len(results),
                  'results':[{'tool':r['tool'],'ok':r['ok'],'row_count':len(r['rows'])} for r in results.values()]}))

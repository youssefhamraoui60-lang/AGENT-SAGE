"""Read-only unit labels and provenance; never supplies conversion factors."""
import re
from app.services import chat_tools
from app.services.modification_resolvers import UnitResolver,norm

def search(query,folder):
    result=chat_tools.run([{'id':'unit_search','tool':'search_units','args':{'Label':query,'Folder':folder}}]).get('unit_search',{})
    if not result.get('ok') or result.get('folder',folder)!=folder:
        return {'ok':False,'folder':folder,'choices':[],'message':'Référentiel des unités indisponible ; aucune unité inventée.'}
    # The catalogue is small and bounded; retry full labels for spelling errors.
    rows=result.get('rows',[])
    if query and not rows:
        result=chat_tools.run([{'id':'unit_search','tool':'search_units','args':{'Label':'','Folder':folder}}]).get('unit_search',{})
        if not result.get('ok') or result.get('folder',folder)!=folder:return {'ok':False,'folder':folder,'choices':[]}
        rows=result.get('rows',[])
    return {'ok':True,'folder':folder,'query':query,'choices':UnitResolver().search(query,rows,limit=100),'sage_writes':0}

def proof(value,evidence,state,folder):
    result=state.get('unit_choices') or {}
    if not result.get('ok') or result.get('folder')!=folder:return None
    choices=result.get('choices',[])
    if not choices:return None
    chosen=next((row for row in choices if row['code']==value),None)
    if not chosen:return None
    q=norm(result.get('query',''))
    if not q or not re.search(r'(?<!\w)'+re.escape(q)+r'(?!\w)',norm(evidence)):return None
    # Approximate labels only resolve a strong, unambiguous candidate.
    competing=max((row['score'] for row in choices if row['code']!=value),default=0)
    exact=chosen['score']==1 and competing<1
    if not exact and (chosen['score']<.75 or chosen['score']-competing<.15):return None
    return {'source':'verified_unit_label','value':value,'reference_label':chosen['label'],'declared_label':result['query'],'folder':folder}

"""Technical diagnostics without raw prompts, SQL parameters, tokens or credentials."""
import json,logging,traceback
from uuid import uuid4

def record(exc,stage,conversation=None,job=None):
    identifier=uuid4().hex[:12]
    detail={'event':'chat_diagnostic','diagnostic_id':identifier,'stage':stage,'error_type':type(exc).__name__,'sqlstate':getattr(exc,'sqlstate',None),'conversation_id':str(conversation) if conversation else None,'job_id':str(job) if job else None,
            'frames':[{'file':f.filename.replace('\\','/').split('/')[-1],'function':f.name,'line':f.lineno} for f in traceback.extract_tb(exc.__traceback__)[-8:]]}
    if str(exc) in ('invalid_partner_target','partner_name_required','partner_name_not_grounded','incomplete_model_output','incomplete_article_list','ungrounded_semantic_fact','contradictory_semantic_facts','semantic_clause_in_field','known_unknown_conflict'):detail['reason']=str(exc)
    if hasattr(exc,'errors'):
        try:detail['validation']=[{'location':list(e['loc']),'type':e['type']} for e in exc.errors(include_input=False,include_context=False)][:12]
        except Exception:pass
    logging.getLogger('agent_sage.chat').warning(json.dumps(detail,separators=(',',':')))
    return identifier

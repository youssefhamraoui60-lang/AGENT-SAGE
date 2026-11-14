import asyncio
import json
import hashlib
from pathlib import Path
import re
import httpx
from pydantic import ValidationError
from app.core.config import settings
from app.schemas.business import Proposal
from app.services.business_rules import normalize

PROMPT_VERSION='business-v2'

class InvalidModelOutput(Exception): pass

def check_grounding(proposal,text):
    for item in proposal.articles:
        for field in ('designation','fournisseur'):
            value=getattr(item,field)
            if value and value.casefold() not in text.casefold():
                raise InvalidModelOutput('technical_text_not_preserved')
        for field in ('code_article','code_fournisseur','site'):
            value=getattr(item,field)
            if value and not re.search(r'(?<!\w)'+re.escape(normalize(value))+r'(?!\w)',normalize(text)):
                raise InvalidModelOutput('ungrounded_identifier')
    for supplier in proposal.fournisseurs:
        if supplier.nom and supplier.nom.casefold() not in text.casefold():
            raise InvalidModelOutput('supplier_name_not_grounded')
        if any(value.casefold() not in text.casefold() for value in supplier.informations.values()):
            raise InvalidModelOutput('supplier_information_not_grounded')
        if supplier.code_fournisseur and not re.search(r'(?<!\w)'+re.escape(normalize(supplier.code_fournisseur))+r'(?!\w)',normalize(text)):
            raise InvalidModelOutput('ungrounded_supplier_code')

async def analyze(text,rag,examples=None):
    examples=[row for row in (examples or []) if len(json.dumps(row,ensure_ascii=False))<=2000][:2]
    schema=Proposal.model_json_schema()
    prompt=(Path(__file__).resolve().parents[1]/f'prompts/{PROMPT_VERSION}.txt').read_text(encoding='utf-8')
    example={'intention':'create_article','articles':[{'designation':'vis de démonstration',
        'unite':None,'categorie':'FG','famille':None,'fournisseur':'Société fictive',
        'code_fournisseur':None,'code_article':None,'site':None}],
        'fournisseurs':[],'ambigu':False,'questions':[]}
    messages=[{'role':'system','content':prompt+'\nSCHEMA: '+json.dumps(schema,ensure_ascii=False)},
        {'role':'user','content':'Créer une vis de démonstration, unité, catégorie FG, fournisseur Société fictive.'},
        {'role':'assistant','content':json.dumps(example,ensure_ascii=False)},
        {'role':'user','content':'Créer les fournisseurs SOCIETE FICTIVE A et SOCIETE FICTIVE B.'},
        {'role':'assistant','content':json.dumps({'intention':'create_supplier','articles':[],
            'fournisseurs':[{'nom':'SOCIETE FICTIVE A','code_fournisseur':None,'informations':{}},
                {'nom':'SOCIETE FICTIVE B','code_fournisseur':None,'informations':{}}],
            'ambigu':False,'questions':[]},ensure_ascii=False)},
        {'role':'user','content':json.dumps({'demande':text,'contexte_local_non_fiable':rag['passages'],
            'exemples_humains_non_executables':examples or []},ensure_ascii=False)}]
    last=None
    async with httpx.AsyncClient(timeout=settings.business_ai_timeout,trust_env=False) as client:
        tags=await client.get(settings.ollama_url+'/api/tags')
        tags.raise_for_status()
        model=next((m for m in tags.json()['models'] if m['name']==settings.ollama_model),None)
        if model is None: raise InvalidModelOutput('configured_model_missing')
        version_response=await client.get(settings.ollama_url+'/api/version')
        version_response.raise_for_status()
        for attempt in range(1,settings.business_ai_attempts+1):
            try:
                response=await client.post(settings.ollama_url+'/api/chat',json={
                    'model':settings.ollama_model,'messages':messages,'format':schema,'stream':False,
                    'options':{'temperature':0,'num_ctx':8192,'num_predict':2500}})
                response.raise_for_status()
                body=response.json()
                if not body.get('done') or body.get('done_reason')=='length': raise InvalidModelOutput('incomplete_response')
                proposal=Proposal.model_validate_json(body['message']['content'])
                check_grounding(proposal,text)
                return proposal,{'prompt_version':PROMPT_VERSION,'model':settings.ollama_model,
                    'model_digest':model.get('digest'),'ollama_version':version_response.json().get('version'),
                    'attempts':attempt,'temperature':0,'retrieval':rag,'training_performed':False,
                    'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),
                    'schema_sha256':hashlib.sha256(json.dumps(schema,sort_keys=True).encode()).hexdigest(),
                    'example_request_ids':[row['request_id'] for row in (examples or [])]}
            except (ValidationError,InvalidModelOutput,KeyError,ValueError) as exc:
                last=exc
                messages.append({'role':'system','content':'La réponse précédente a été rejetée. Respecte TOUS les champs du schéma, les codes explicites et le littéral null sans guillemets. Chaque objet doit représenter une entité citée, jamais un objet entièrement vide.'})
            except httpx.HTTPError as exc:
                last=exc
                if attempt==settings.business_ai_attempts: raise
            if attempt<settings.business_ai_attempts: await asyncio.sleep(0.1)
    raise InvalidModelOutput(type(last).__name__) from None

"""Keep grounded data when both inference paths fail; never prepare or execute SQL."""
import copy
from app.services import article_sql_dialogue,article_sql

def recover(text,state):
    changed=copy.deepcopy(state)
    if changed.get('articles'):
        article_sql_dialogue.enrich(changed,text,state)
        for article in changed['articles']:
            if (article.get('operation') or {}).get('status') not in article_sql.TERMINAL:
                article['approved']=False
                article['operation']={'status':'blocked','transport':'direct_sql_article','message':'La compréhension doit être confirmée avant une nouvelle vérification.'}
        return changed,'Les services IA ne permettent pas de terminer cette analyse. Votre fiche et les informations reconnues sont conservées. Précisez uniquement le champ à corriger, par exemple « unité UN ».'
    return changed,'Les services IA sont momentanément indisponibles. Votre demande est conservée. Vous pouvez préciser le nom et les informations connues dans le chat, sans répéter toute la demande.'

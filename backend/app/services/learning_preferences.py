"""Only explicit personal preferences auto-validate; business facts need review."""
import re
from app.services.chat_turns import norm
from app.services import business_store as db

def personal(content):
    n=norm(content)
    return bool(re.match(r'(?:je prefere|je souhaite|je veux|reponds[- ]moi|mes reponses)',n) and not re.search(r'\b(?:fournisseur|frs|ice|stock|solde|creation|production|autorisation)\b',n))

def topic(content):
    n=norm(content)
    if re.search(r'francais|darija|anglais|arabe|langue',n):return 'language'
    if re.search(r'courte?s?|longue?s?|detaille|concis',n):return 'length'
    if re.search(r'tableau|liste|paragraphe',n):return 'format'
    return 'unspecified'

def conflicts(owner,content):
    with db.connection() as conn:
        rows=conn.execute("SELECT * FROM learning_items WHERE owner_id=%s AND kind='preference' AND status='validated'",(owner,)).fetchall()
    return [r for r in rows if topic(r['content'])==topic(content) and norm(r['content'])!=norm(content)]

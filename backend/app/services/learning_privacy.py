"""Conservative anonymization for examples; never exports an unchanged private task."""
import re

def anonymize_pair(user,target):
    from app.services.supplier_chat_flow import extract
    replacements={}
    for text in (user,target):
        try:
            parsed=extract(text,{'articles':[],'partners':[]})
            partners=parsed[0].fournisseurs if parsed else []
        except ValueError:partners=[]
        for partner in partners:
            for field,value in partner.model_dump(exclude_none=True).items():
                if field in ('nom','intitule_court','adresse','ville','telephone','fax','ice','identifiant_fiscal','rc','email') and isinstance(value,str) and value.strip():
                    replacements.setdefault(value,'['+field.upper()+']')
    def scrub(text):
        for value,placeholder in sorted(replacements.items(),key=lambda p:len(p[0]),reverse=True):
            text=re.sub(re.escape(value),lambda _:placeholder,text,flags=re.I)
        text=re.sub(r'\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b','[EMAIL]',text,flags=re.I)
        text=re.sub(r'(?<!\w)\+?\d[\d .()-]{6,}\d(?!\w)','[IDENTIFIANT]',text)
        return text
    return scrub(user),scrub(target)

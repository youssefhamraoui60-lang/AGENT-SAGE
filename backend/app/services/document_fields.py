"""Document contents supply literal candidates, never instructions or approvals."""
import re
from app.services import learning
from app.services.chat_turns import norm

LABELS={'nom du fournisseur':'nom','nom fournisseur':'nom','raison sociale':'nom','fournisseur':'nom','nom':'nom',
 'identifiant fiscal':'identifiant_fiscal','if':'identifiant_fiscal','ice':'ice','registre de commerce':'rc','rc':'rc',
 'adresse':'adresse','ville':'ville','telephone':'telephone','tel':'telephone','email':'email','e-mail':'email',
 'conditions de paiement':'conditions_paiement','condition de paiement':'conditions_paiement','paiement':'conditions_paiement'}
TITLES={'nom':'Nom du fournisseur','ice':'ICE','identifiant_fiscal':'IF','rc':'RC','adresse':'Adresse','ville':'Ville','telephone':'Téléphone','email':'Email','conditions_paiement':'Paiement'}
PATTERN=re.compile(r'(?<!\w)('+ '|'.join(re.escape(k) for k in sorted(LABELS,key=len,reverse=True))+r')\s*[:=]\s*',re.I)

# Printed tax forms use bilingual labels, often without punctuation. Match only
# these explicit labels; never infer a company from the filename or a tax date.
FORM_LABELS=[
 ('nom',r'^nom,?\s*(?:et\s+)?prenom\(s\)\s+ou\s+raison(?:\s+sociale)?'),
 ('identifiant_fiscal',r'^(?:n[°ºo]\s*(?:de\s+)?)?d[’\x27]identification\s+fiscale'),
 ('ice',r'^identifiant\s+commun\s+de\s+l[’\x27]entreprise\s*[«\"]?\s*ice\s*[»\"]?'),
 ('rc',r'^(?:n[°ºo]\s*du\s+)?registre\s+de\s+commerce'),
 ('adresse',r'^domicile\s+fiscal\s+ou\s+siege\s+social'),
]

def form_pairs(lines,index):
    # Remove only the parallel Arabic label, not Latin identifiers or leading 0s.
    clean=lambda s:re.sub(r'[\u0600-\u06ff\u0750-\u077f\ufb50-\ufdff\ufe70-\ufeff]+',' ',s).strip()
    line=clean(lines[index]); normalized=norm(line)
    for field,pattern in FORM_LABELS:
        match=re.match(pattern,normalized,re.I)
        if not match:continue
        value=line[match.end():].strip(' :;')
        if not value and index+1<len(lines):
            following=clean(lines[index+1])
            if following and not re.match(r'^(?:n[°ºo]|nom|activite|domicile|identifiant)\b',norm(following)):
                value=following
        if field in ('ice','identifiant_fiscal','rc'):
            numeric=re.fullmatch(r'\s*(\d+)\s*',value)
            if not numeric:return []
            value=numeric[1]
        return [(field,value)] if value else []
    return []

def parse(report,filename,file_id):
    candidates=[];warnings=[]
    for page in report.get('pages',[]):
        number=page['page'];lines=page['text'].splitlines()
        if 'text_truncated' in page.get('warnings',[]):warnings.append({'page':number,'reason':'Page très longue : seule la première partie a été analysée.'})
        if not page['text'].strip():warnings.append({'page':number,'reason':'Aucun texte lisible.'})
        if learning.INJECTION.search(page['text']):warnings.append({'page':number,'reason':'Consignes présentes dans le document ignorées.'})
        for index,line in enumerate(lines):
            matches=list(PATTERN.finditer(norm(line)))
            if not matches:
                label=norm(line.strip().strip(':'))
                if label in LABELS and index+1<len(lines) and not PATTERN.search(norm(lines[index+1])) and norm(lines[index+1].strip().strip(':')) not in LABELS:
                    pairs=[(LABELS[label],lines[index+1].strip())]
                else:
                    pairs=form_pairs(lines,index)
                    if not pairs:continue
            else:pairs=[(LABELS[m[1].lower()],line[m.end():matches[i+1].start() if i+1<len(matches) else len(line)].strip(' ;/')) for i,m in enumerate(matches)]
            for field,value in pairs:
                if not value and index+1<len(lines) and not PATTERN.search(norm(lines[index+1])) and norm(lines[index+1].strip().strip(':')) not in LABELS:
                    value=lines[index+1].strip()
                if not value or len(value)>500:continue
                if learning.SECRET.search(value) or learning.INJECTION.search(value):
                    warnings.append({'page':number,'reason':'Valeur sensible ou instruction ignorée.'});continue
                if field in ('ice','identifiant_fiscal','rc'):value=re.sub(r'^(?:N\s*[°ºo]|num[eé]ro)\s*','',value,flags=re.I).rstrip(' .')
                candidates.append({'field':field,'value':value,'source':{'file_id':str(file_id),'filename':filename,'page':number,'method':page['method']},
                    'uncertain':bool(page['uncertain']),'warnings':page.get('warnings',[])})
    # Values remain strings, including fiscal leading zeroes and unreadable OCR characters.
    return {'candidates':candidates,'warnings':warnings}

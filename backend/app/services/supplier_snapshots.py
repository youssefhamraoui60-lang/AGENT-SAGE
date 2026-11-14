"""Read-only, immutable display projection. No operation tokens or write authority."""
FIELDS=[('Statut','Statut fournisseur','statut'),('Nom','Nom du fournisseur','nom'),('NomCourt','Nom court','intitule_court'),('ICE','ICE','ice'),('IF','Identifiant fiscal','identifiant_fiscal'),('RC','Registre de commerce','rc'),('Adresse','Adresse','adresse'),('Ville','Ville','ville'),('Pays','Pays','pays'),('Telephone','Téléphone','telephone'),('Fax','Fax','fax'),('Email','Email','email'),('Paiement','Conditions de paiement','conditions_paiement'),('Devise','Devise','devise'),('TypeLibelle','Prix','type_montant'),('Categorie','Catégorie fournisseur','categorie_fournisseur'),('CodeComptable','Code comptable','code_comptable'),('RegimeTaxe','Régime fiscal','regime_taxe'),('DateRegularite','Date de régularité','date_regularite')]

def capture(state):
    snapshots=[]
    for partner in state.get('partners',[]):
        if partner.get('kind')!='supplier':continue
        op=partner.get('operation') or {};parameters={} if op.get('status')=='invalidated' else op.get('parameters') or {}
        rows=[]
        for parameter,label,field in FIELDS:
            value=partner.get(field) if partner.get(field) is not None else parameters.get(parameter)
            empty=value in (None,'') or parameter=='DateRegularite' and value=='1753-01-01'
            row={'key':parameter,'label':label,'value':None if empty else value,'origin':'missing' if empty else 'default' if parameter in op.get('defaulted_fields',[]) else 'declared'}
            source=partner.get('document_sources',{}).get(field)
            if source:row.update(origin='document',source=source)
            if parameter=='Adresse' and (parameters.get('Adresse2') or parameters.get('Adresse3')):
                for key,title in [('Adresse','Adresse — ligne 1'),('Adresse2','Adresse — ligne 2'),('Adresse3','Adresse — ligne 3')]:
                    if parameters.get(key):rows.append({**row,'key':key,'label':title,'value':parameters[key]})
                continue
            rows.append(row)
        if partner.get('forme_juridique'):
            rows.insert(2,{'key':'FormeJuridique','label':'Forme juridique','value':partner['forme_juridique'],'origin':'declared'})
        snapshots.append({'supplier_id':partner['id'],'name':partner.get('nom'),'stage':op.get('status','draft'),'rows':rows})
    return snapshots

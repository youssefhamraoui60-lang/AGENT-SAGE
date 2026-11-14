"""Record original-document visual readings; no Sage writes or inferred codes."""
import hashlib
import json
from pathlib import Path
import learning_memory as memory
from psycopg.types.json import Jsonb

OUT=Path(__file__).resolve().parents[1]/'runtime/sob-week-20261102'
REVIEWS={
    4065:{'text':'TILDI BATIMENT\nClient : S.O.B\n02/11/2026\nFer 08 | 6000 KG | 9,10\nFer 10 | 2000 KG | 9,10\nFer 12 | 12000 KG | 9,10\nFer 14 | 4000 KG | 9,10\nFer 16 | 2000 KG | 9,10',
          'issues':['Client OB du motif de quantités = PROFIL DES TRAVAUX DE CONSTRUCTION ; lien avec TILDI BATIMENT à confirmer.','Totaux manuscrits à vérifier sur original.']},
    4104:{'text':"BEN ZAKANI\nDestinataire : OULD BOUAZZA\nBon de commande 41-2026\n02/11/2026\nChantier AIN CHOCK\nFer à béton 14 | KG | 800 | 9,50\nFer à béton 10 | KG | 600 | 9,50\nFer à béton 12 | KG | 800 | 9,50\nFer à béton 6 | KG | 300 | 9,80\nFIL D'ATTACHE | KG | 25 | 14,50\nTOTAL TTC 24202,50",
          'issues':["Référence exacte du fil d’attache à confirmer ; PF-FR130 figure dans l’OB correspondant, mais son diamètre n’est pas écrit sur le document."]},
    4084:{'text':'SOCIETE AL MOTTAHIDA LIL BINA\n02/11/2026\nA BOUSKOURA\n01 Ciment 45\nContacter ABDELLAH\n0655-43-95-56\nICE 001620857000060',
          'issues':['Unité de la quantité 01 non écrite : voyage, tonne ou autre à confirmer.']},
    4083:{'text':'Première page examinée : NISSICIR IMMO, STATUTS, objet social, siège social. Aucune ligne article/quantité sur cette page.',
          'issues':['Pièce administrative ; préciser à quelle demande/client elle se rattache. Les pages non examinées ne sont pas transcrites.']},
}

def main():
    path=OUT/'messages-visual.json'
    source=json.loads(path.read_text(encoding='utf-8'))
    by_id={r['id']:r for r in source}
    with memory.db.connection() as conn:
        for mid,review in REVIEWS.items():
            row=by_id[mid]
            digest=hashlib.sha256((OUT/row['file']).read_bytes()).hexdigest()
            row['visual_review_20261109']={'method':'assistant_visual_read_of_original_first_page','file_sha256':digest,'uncertain':True,'issues':review['issues'],'transcription':review['text']}
            conn.execute('''INSERT INTO sob_learning_examples(source_key,input_data,expected,observed,status) VALUES(%s,%s,%s,%s,%s)
                ON CONFLICT(source_key) DO UPDATE SET observed=EXCLUDED.observed,status=EXCLUDED.status''',
                ('sob-visual-review-'+str(mid),Jsonb({'message_id':mid,'date':row['date'],'file':row['file'],'sha256':digest}),Jsonb({'transcription':review['text']}),Jsonb({'issues':review['issues']}),'needs_user_review'))
    path.write_text(json.dumps(source,ensure_ascii=False,indent=2),encoding='utf-8')
    print('4 visual reviews preserved; no Sage writes')

if __name__=='__main__':main()

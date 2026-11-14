"""Incident replay: real local extractor and PG; recorded TEST categories, no ERP writes."""
import asyncio
import argparse
import json
from pathlib import Path
import evaluate_human_conversations as evaluation


class RecordedCategories(evaluation.FakeSQL):
    def __call__(self,calls):
        output=super().__call__(calls)
        path=Path(__file__).resolve().parents[1]/'tests/ai-evaluation/reports/modern-foam-real-categories.json'
        catalogue=json.loads(path.read_text(encoding='utf-8-sig'))['results'][0]
        if not catalogue.get('ok'):raise RuntimeError('Verified category snapshot required')
        for call in calls:
            if call['tool']=='get_article_categories':
                code=call['args'].get('Category','')
                output[call['id']]['rows']=[r for r in catalogue['rows'] if not code or r['TCLCOD_0'].strip()==code]
                output[call['id']]['source']='RECORDED_REAL_TEST_CATEGORY_SELECT'
        return output


def scenarios():
    step=evaluation.step
    return [{'id':'modern-foam-priority','persona':'conversation fournie et corrections successives',
        'cardinality':2,'path':'incident', 'turns':[
        step('Bonjour, j’ai besoin de la création de ces deux articles : Modern foam boards A XPS 4 CM et Modern foam boards B XPS 4 CM. Unité M2, fournisseur Modern for Foam and Plastic, catégorie AR.',article_count=2,articles={'categorie':'AR','unite':'M2'}),
        step('sur le site 201 ET POUR LE FORNISEUR JE VEUX PAS DE FORNISEUR',article_count=2,articles={'site':'201','unite':'M2','supplier_intent':'none'}),
        step('DONNER LES NOM DES CHQGE CATIGORIER',unchanged=True),
        step('lisert les nom des de chque cztigorier pour mois je peux dire q uille code catigorier',unchanged=True),
        step('AGEN',articles={'categorie':'AGEN','site':'201','unite':'M2','supplier_intent':'none'}),
        step('AGEN',unchanged=True),
        step('site 202',articles={'site':'202','categorie':'AGEN','unite':'M2'}),
        step('unité UN',articles={'site':'202','categorie':'AGEN','unite':'UN'}),
        step('code fournisseur F234',articles={'code_fournisseur':'F234','site':'202'}),
        step('sans fournisseur',articles={'supplier_intent':'none','site':'202'}),
        step('catégorie NEG',articles={'categorie':'NEG','site':'202','unite':'UN'}),
        step('site 201',articles={'site':'201','categorie':'NEG','unite':'UN'}),
        step('unité M2',articles={'site':'201','categorie':'NEG','unite':'M2','supplier_intent':'none'}),
        step('oui',no_approval=True)]}]


if __name__=='__main__':
    evaluation.FakeSQL=RecordedCategories
    evaluation.scenarios=scenarios
    raise SystemExit(asyncio.run(evaluation.run(argparse.Namespace(only='',limit=1))))

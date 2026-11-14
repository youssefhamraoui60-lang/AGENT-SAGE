"""Export the executed case catalogue and consolidate identical-input retests."""
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
import argparse,hashlib,json,xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'tests/ai-evaluation'


def write(relative,value):
    file=BASE/relative;file.parent.mkdir(parents=True,exist_ok=True)
    file.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf8')


def main(junit='all-isolated-cycle-03.xml'):
    source=BASE/junit;cases=[]
    for node in ET.parse(source).getroot().iter('testcase'):
        props={p.get('name'):p.get('value') for p in node.findall('./properties/property')}
        if 'scenario' not in props:continue
        scenario=json.loads(props['scenario'])
        assert node.find('failure') is None and node.find('error') is None
        cases.append({'scenario':scenario,'actual':json.loads(props['actual']),
                      'status':'passed','seconds':float(node.get('time','0'))})
    assert len(cases)==1000 and len({c['scenario']['id'] for c in cases})==1000
    write('scenarios/scenarios-1000.json',[c['scenario'] for c in cases])
    write('results/contracts-executed.json',{'source':source.name,'count':len(cases),'results':cases})
    records=[]
    for file in sorted((BASE/'conversations').glob('*/run_manifest.json')):
        manifest=json.loads(file.read_text(encoding='utf8'))
        if manifest.get('finished_at') and len(manifest.get('conversations',[]))==100:records.append((file,manifest))
    assert records,'No completed 100-conversation cycle'
    file,full=records[-1]
    original={c['id']:c for c in full['conversations']}
    inputs={c['id']:c for c in json.loads((file.parent/'scenario-inputs.json').read_text(encoding='utf8'))}
    final={key:{**value,'source':str(file.parent.relative_to(BASE))} for key,value in original.items()}
    retests=[]
    for other in sorted((BASE/'conversations').glob('*/run_manifest.json')):
        if other.parent.name<=file.parent.name:continue
        replay=json.loads(other.read_text(encoding='utf8'))
        if not replay.get('finished_at') or replay.get('status')=='cancelled_superseded':continue
        if replay.get('model_digest')!=full.get('model_digest'):continue
        replay_inputs={c['id']:c for c in json.loads((other.parent/'scenario-inputs.json').read_text(encoding='utf8'))}
        for item in replay['conversations']:
            if item['id'] not in inputs:continue
            assert inputs[item['id']]['turns']==replay_inputs[item['id']]['turns'],'Retest changed the expected conversation'
            final[item['id']]={**item,'source':str(other.parent.relative_to(BASE))}
            retests.append({'id':item['id'],'passed':item['passed'],'source':str(other.parent.relative_to(BASE)),'identical_inputs_and_expectations':True})
    known=BASE/'failures/existing-site-mismatch-simulation.json'
    known_failure=json.loads(known.read_text(encoding='utf-8-sig')) if known.exists() else None
    manifest={'at':datetime.now(timezone.utc).isoformat(),'goal_complete':False,
              'contract_scenarios':{'executed':1000,'passed':1000,'domains':dict(Counter(c['scenario']['domain'] for c in cases)),'junit':source.name},
              'conversations':{'distinct':len(final),'initial_passed':sum(c['passed'] for c in original.values()),
                  'final_passed':sum(c['passed'] for c in final.values()),'primary_cycle':str(file.parent.relative_to(BASE)),
                  'primary_turns':sum(c['turns'] for c in original.values()),'retests':retests,
                  'human_language_review_complete':False,'latest_per_id':final},
              'model':{'name':full['model'],'digest':full['model_digest']},
              'real20':{'prepared':20,'created':0,'article_sites_created':0,'approval':'user_requested_corrections'},
              'known_open_sensitive_defects':[{'id':'existing_site_readback_mismatch','reproduced':bool(known_failure and known_failure.get('DefectReproduced')),'fix_applied':False}],
              'code_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'backend/app').rglob('*.py')}}
    write('run_manifest.json',manifest)
    print(json.dumps({'scenarios':1000,'conversations':len(final),'initial_passed':manifest['conversations']['initial_passed'],
                      'final_passed':manifest['conversations']['final_passed'],'identical_input_retests':len(retests),'goal_complete':False}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--junit',default='all-isolated-cycle-03.xml')
    main(parser.parse_args().junit)

import asyncio
import audit_replays as module
import prepare
import creation


def test_authorized_replay_is_idempotent_and_never_creates(monkeypatch,tmp_path):
    monkeypatch.setattr(module,'DB',tmp_path/'audit.sqlite3')
    from datetime import date
    original_build=creation.build_payload
    monkeypatch.setattr(creation,'build_payload',lambda details:original_build(details,reference_date=date(2026,11,10)))
    async def analyze(*args,**kwargs):
        return {'client':{'BPCNUM_0':'C01401','CUR_0':'MAD'},'missing':[],'missing_fields':[],
                'delivery':'2026-11-10','lines':[{'article':'CPJ45','quantity':20,'price':81}]}
    calls=[]
    def sql(script,payload):
        assert script=='sob-execute.ps1' and payload['mode']=='preview'
        calls.append(payload)
        return {'ok':True,'rows':[]}
    monkeypatch.setattr(prepare,'prepare',analyze)
    monkeypatch.setattr(creation,'run_script',sql)
    monkeypatch.setattr(creation,'confirm',lambda *a,**k:(_ for _ in ()).throw(AssertionError('No creation')))
    token=module.register(1,2,'test',[{'id':100,'text':'20 sacs cpj45 C01401'}])
    result=asyncio.run(module.run(token))
    assert result['status']=='sql_preview_passed'
    assert asyncio.run(module.run(token))==result
    assert len(calls)==1

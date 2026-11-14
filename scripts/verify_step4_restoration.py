"""Compare stage-4 local tables against the isolated restored backup, without changing originals."""
import hashlib,json
from pathlib import Path
import psycopg
from psycopg import sql
import native_stack as stack
ROOT=stack.ROOT
backup=json.loads((ROOT/'logs/native-backup-tests.json').read_text())
assert backup['restore']=='PASS'
target=Path(backup['restore_directory']);cluster=target/'postgres';env=stack.environment()
def snapshot(conn,table):
    rows=conn.execute(sql.SQL('SELECT row_to_json(t)::text FROM sage_ai.{} t ORDER BY row_to_json(t)::text').format(sql.Identifier(table))).fetchall()
    return {'rows':len(rows),'sha256':hashlib.sha256(json.dumps(rows,ensure_ascii=False).encode()).hexdigest()}
stack.pg_run('pg_ctl.exe','-D',str(cluster),'-l',str(target/'postgres.log'),'-w','start')
try:
    with stack.connect() as original,psycopg.connect(host='127.0.0.1',port=55433,user='sage_admin',password=env['NATIVE_PG_ADMIN_PASSWORD'],dbname=env['POSTGRES_DB']) as restored:
        compared={}
        for table in ['soap_article_preparations','soap_article_observations']:
            before=snapshot(original,table);after=snapshot(restored,table)
            assert before==after,table
            compared[table]=before
finally:stack.pg_run('pg_ctl.exe','-D',str(cluster),'-m','fast','-w','stop')
proof={'status':'PASS','backup':backup['backup'],'restored_tables':compared,'original_data_replaced':False}
(ROOT/'logs/step4-form-backup-tests.json').write_text(json.dumps(proof,indent=2),encoding='utf-8')
print(json.dumps(proof,indent=2))

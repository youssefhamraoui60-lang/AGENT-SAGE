"""Read-only comparison of the stage-2 schema in the already restored clone."""
import hashlib
import json
from pathlib import Path
import psycopg
from psycopg import sql
import native_stack as stack

ROOT=stack.ROOT
proof=json.loads((ROOT/'logs/native-backup-tests.json').read_text())
assert proof['restore']=='PASS'
target=Path(proof['restore_directory'])
cluster=target/'postgres'
env=stack.environment()
tables=['schema_migrations','reference_entries','knowledge_documents','knowledge_passages','requests','request_events']
def snapshot(conn,table):
    rows=conn.execute(sql.SQL('SELECT row_to_json(t)::text FROM sage_ai.{} t ORDER BY row_to_json(t)::text').format(sql.Identifier(table))).fetchall()
    return {'rows':len(rows),'sha256':hashlib.sha256(json.dumps(rows,ensure_ascii=False).encode()).hexdigest()}
stack.pg_run('pg_ctl.exe','-D',str(cluster),'-l',str(target/'postgres.log'),'-w','start')
try:
    with stack.connect() as original, psycopg.connect(host='127.0.0.1',port=55433,user='sage_admin',password=env['NATIVE_PG_ADMIN_PASSWORD'],dbname=env['POSTGRES_DB']) as restored:
        compared={}
        for table in tables:
            source=snapshot(original,table);clone=snapshot(restored,table)
            assert source==clone,table
            compared[table]=source
finally:
    stack.pg_run('pg_ctl.exe','-D',str(cluster),'-m','fast','-w','stop')
result={'status':'PASS','backup':proof['backup'],'restored_tables':compared,'original_data_replaced':False}
(ROOT/'logs/step2-backup-tests.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))

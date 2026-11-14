"""Read-only verification of all three CRUD tables in an isolated restored clone."""
import hashlib,json
from pathlib import Path
import psycopg
from psycopg import sql
import native_stack as stack
ROOT=stack.ROOT
backup=json.loads((ROOT/'logs/native-backup-tests.json').read_text());assert backup['restore']=='PASS'
folder=Path(backup['restore_directory']);env=stack.environment()
def snapshot(conn,table):
    rows=conn.execute(sql.SQL('SELECT row_to_json(t)::text FROM sage_ai.{} t ORDER BY row_to_json(t)::text').format(sql.Identifier(table))).fetchall()
    return {'rows':len(rows),'sha256':hashlib.sha256(json.dumps(rows,ensure_ascii=False).encode()).hexdigest()}
stack.pg_run('pg_ctl.exe','-D',str(folder/'postgres'),'-l',str(folder/'postgres.log'),'-w','start')
try:
    with stack.connect() as original,psycopg.connect(host='127.0.0.1',port=55433,user='sage_admin',password=env['NATIVE_PG_ADMIN_PASSWORD'],dbname=env['POSTGRES_DB']) as restored:
        tables={}
        for table in ['soap_operations','soap_operation_events','soap_operation_approvals']:
            actual=snapshot(original,table);copy=snapshot(restored,table)
            assert actual==copy,table
            tables[table]=actual
finally:stack.pg_run('pg_ctl.exe','-D',str(folder/'postgres'),'-m','fast','-w','stop')
proof={'status':'PASS','backup':backup['backup'],'restored_tables':tables,'original_data_replaced':False}
(ROOT/'logs/step4-crud-backup-tests.json').write_text(json.dumps(proof,indent=2),encoding='utf-8');print(json.dumps(proof,indent=2))

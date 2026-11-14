"""Activate supplier emails for future INBOX requests after checking the target."""
import argparse,json,subprocess,sys
from contextlib import closing
from pathlib import Path
from uuid import UUID
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from dotenv import set_key
from app.core.config import settings
from app.services import supplier_mail as mail,supplier_sql
ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--folder',choices=('TEST','OB'),required=True);args=parser.parse_args()
    UUID(settings.supplier_mail_owner_id)
    security=supplier_sql.security(force=True,folder=args.folder)
    if security.get('ready') is not True:
        print(json.dumps({'activated':False,'folder':args.folder,'blockers':security.get('blockers',[])}));raise SystemExit(1)
    client=mail.connect()
    stopped=False
    try:
        status,_=client.select('INBOX',readonly=True)
        if status!='OK':raise ValueError('inbox_unavailable')
        with closing(mail.ledger()) as conn:
            # Hold the same database write lock used by claim(): no new request
            # can enter execution between the idle check and stopping the worker.
            conn.execute('BEGIN IMMEDIATE')
            previous=conn.execute('SELECT mailbox,uidvalidity,min_uid FROM activations WHERE folder=?',(args.folder,)).fetchone()
            if settings.supplier_mail_folder==args.folder and previous:
                cutoff=mail.activation_cutoff(conn,client,args.folder)
                conn.rollback()
                print(json.dumps({'activated':True,'already_active':True,'folder':args.folder,'minimum_uid':cutoff}))
                starter=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-File',str(ROOT/'scripts/start-supplier-mail.ps1')],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=20)
                print('Supplier mail worker running')
                if starter.returncode:raise RuntimeError('mail_worker_start_failed')
                return
            active=conn.execute("SELECT folder,status FROM messages WHERE status IN ('processing','claimed')").fetchall()
            if active:raise RuntimeError('mail_request_in_progress_wait_before_activation')
            command="Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -like '*supplier_mail_worker.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -ErrorAction SilentlyContinue }"
            process=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',command],capture_output=True,text=True,timeout=15)
            if process.returncode:raise RuntimeError('mail_worker_stop_failed')
            stopped=True
            status,_=client.select('INBOX',readonly=True)
            if status!='OK':raise ValueError('inbox_unavailable')
            _, validity=client.response('UIDVALIDITY');_, next_uid=client.response('UIDNEXT')
            validity=validity[-1].decode('ascii') if validity and validity[0] else ''
            next_uid=next_uid[-1].decode('ascii') if next_uid and next_uid[0] else ''
            if not validity.isdecimal() or not next_uid.isdecimal() or int(next_uid)<1:raise ValueError('mailbox_activation_metadata_missing')
            conn.execute('''INSERT INTO activations(folder,mailbox,uidvalidity,min_uid) VALUES(?,?,?,?)
                ON CONFLICT(folder) DO UPDATE SET mailbox=excluded.mailbox,uidvalidity=excluded.uidvalidity,
                    min_uid=excluded.min_uid,activated_at=CURRENT_TIMESTAMP''',
                (args.folder,settings.gmail_user.lower(),validity,int(next_uid)))
            conn.commit()
            set_key(ROOT/'.env','SUPPLIER_MAIL_FOLDER',args.folder)
            result={'activated':True,'folder':args.folder,'minimum_uid':int(next_uid),'uidvalidity':validity,'old_messages_replayed':False,'sql_permissions_ready':True}
            (ROOT/'TEST/supplier-mail-active-target.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
            print(json.dumps(result))
    finally:
        client.logout()
        if stopped:
            process=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-File',str(ROOT/'scripts/start-supplier-mail.ps1')],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=20)
            print('Supplier mail worker restarted')
            if process.returncode:raise RuntimeError('mail_worker_start_failed')

if __name__=='__main__':main()

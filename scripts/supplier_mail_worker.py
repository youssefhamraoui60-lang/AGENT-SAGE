"""Run with backend/.venv/Scripts/python.exe scripts/supplier_mail_worker.py."""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.core.config import settings
from app.services import supplier_mail


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true', help='Read-only IMAP connectivity check')
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--folder', choices=('TEST', 'OB'))
    args = parser.parse_args()
    if args.check:
        print(json.dumps(supplier_mail.check_connection())); return
    while True:
        try:
            print(json.dumps(supplier_mail.poll(args.folder)), flush=True)
        except Exception as exc:
            print(json.dumps({'status': 'failed', 'error_type': type(exc).__name__}), flush=True)
            if args.once: raise SystemExit(1) from None
        if args.once: return
        time.sleep(settings.supplier_mail_poll_seconds)


if __name__ == '__main__': main()

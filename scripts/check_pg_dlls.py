from pathlib import Path
import re
root=Path(__file__).resolve().parents[1]
for name in ['icuin67.dll','icuuc67.dll','libintl-9.dll','libxml2.dll','libzstd.dll']:
    print(name, sorted({m.decode() for m in re.findall(rb'[A-Za-z0-9_.-]+\.dll', (root/'.tools/postgresql-17/pgsql/bin'/name).read_bytes())}))

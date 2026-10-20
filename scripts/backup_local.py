"""Consistent SQLite backup before upgrading; never copy tokens or log record data."""
import os
import sys
import sqlite3
from datetime import datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from config.env import load_env
load_env()
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
from django.conf import settings
config=settings.DATABASES['default']
if config['ENGINE']!='django.db.backends.sqlite3':
    raise SystemExit('Database PostgreSQL: lakukan backup dengan pg_dump dan prosedur produksi, lalu jalankan pembaruan manual sesuai README.')
source=Path(config['NAME'])
if source.exists():
    directory=ROOT/'backups'; directory.mkdir(exist_ok=True)
    target=directory/f'db-before-update-{datetime.now():%Y%m%d-%H%M%S-%f}.sqlite3'
    with sqlite3.connect(str(source)) as src,sqlite3.connect(str(target)) as dst:
        src.backup(dst)
    print('Backup SQLite dibuat di folder backups. Simpan folder ini secara privat.')
else:
    print('Belum ada database lokal; tidak ada data lama yang perlu dibackup.')

import os,subprocess,tempfile
from pathlib import Path
import pgserver
ROOT=Path(__file__).resolve().parents[1]
path=Path(tempfile.mkdtemp(prefix='salam-manis-postgres-'))
server=pgserver.get_server(path,cleanup_mode='delete')
try:
    env=os.environ.copy()
    env.update(DATABASE_URL=server.get_uri(),DB_SSLMODE='disable',DJANGO_DEBUG='true',DJANGO_SECRET_KEY='ephemeral-postgres-test-key')
    print('Ephemeral PostgreSQL started; executing migrations and full test suite.',flush=True)
    for args in [['migrate','--noinput'],['test','--verbosity','1']]:
        result=subprocess.run([str(ROOT/'.venv/bin/python'),'manage.py',*args],cwd=ROOT,env=env)
        if result.returncode: raise SystemExit(result.returncode)
finally:
    server.cleanup()

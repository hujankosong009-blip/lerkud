"""Exercise an actual 0003 -> 0004 upgrade on an isolated legacy database."""
import os
import secrets
import subprocess
import tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='salam-upgrade-') as temp:
    env=os.environ.copy()
    env.pop('DATABASE_URL',None)
    env.update(DJANGO_DEBUG='true',DJANGO_SECRET_KEY=secrets.token_hex(48),DJANGO_SQLITE_PATH=str(Path(temp)/'legacy.sqlite3'))
    def run(*args):
        return subprocess.run([str(ROOT/'.venv/bin/python'),'manage.py',*args],cwd=ROOT,env=env,check=True)
    run('migrate','auth','--noinput')
    run('migrate','service','0003','--noinput')
    run('shell','-c', '''
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
apps=MigrationExecutor(connection).loader.project_state([('service','0003_screeningdraft')]).apps
User=apps.get_model('auth','User'); Officer=apps.get_model('service','Officer'); Assignment=apps.get_model('service','OfficerAssignment'); Location=apps.get_model('service','Location'); Telegram=apps.get_model('service','TelegramUser'); Consent=apps.get_model('service','Consent'); Terms=apps.get_model('service','Terms'); Profile=apps.get_model('service','Profile'); App=apps.get_model('service','Application'); Code=apps.get_model('service','ActivationCode')
from django.utils import timezone
from datetime import timedelta
location=Location.objects.create(name='Lokasi Lama Sintetis',category='IPWL',active=True)
for name,roles in [('legacy-manager',['SYSTEM','COORD']),('legacy-coord',['COORD']),('legacy-local',['LOCAL']),('revoked-manager',['SYSTEM'])]:
 user=User.objects.create(username=name,is_staff=True,is_superuser=True)
 officer=Officer.objects.create(web_user=user,verified=True)
 for role in roles: Assignment.objects.create(officer=officer,location=location,role=role,active=name!='revoked-manager')
u=Telegram.objects.create(telegram_id=999001,bot_notifications=True)
p=Profile.objects.create(user=u,data={'name':'Sintetis'})
c=Consent.objects.create(user=u,terms=Terms.objects.get(active=True))
App.objects.create(number='SM-LEGACY-TEST',applicant=p,identity={'name':'Sintetis'},consent=c,status='MENUNGGU_VERIFIKASI')
Code.objects.create(digest='legacy-hash',location=location,role='COORD',expires_at=timezone.now()+timedelta(days=1))
''')
    run('migrate','--noinput')
    run('shell','-c', '''
from service.models import *
from service.access import officer_active
manager=Officer.objects.get(web_user__username='legacy-manager')
assert manager.role=='SUPERADMIN' and manager.assignments.count()==1
coord=Officer.objects.get(web_user__username='legacy-coord')
assert coord.role=='PELAKSANA' and coord.all_locations
assert not coord.web_user.is_superuser and not coord.web_user.is_staff
local=Officer.objects.get(web_user__username='legacy-local')
assert local.role=='PELAKSANA' and not local.all_locations
assert not officer_active(Officer.objects.get(web_user__username='revoked-manager'))
assert Application.objects.get(number='SM-LEGACY-TEST').legacy_submission
assert ActivationCode.objects.get(digest='legacy-hash').revoked
assert TelegramUser.objects.get(telegram_id=999001).notification_decided
print('Legacy upgrade passed: two roles, deduplicated scope, permissions, revoked invites, preserved applications.')
''')

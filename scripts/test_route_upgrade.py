"""Upgrade existing evidence from 0004 while preserving already routed cases."""
import os, secrets, subprocess, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='salam-route-upgrade-') as temp:
    env=os.environ.copy(); env.pop('DATABASE_URL',None)
    env.update(DJANGO_DEBUG='true',DJANGO_SECRET_KEY=secrets.token_hex(48),DJANGO_SQLITE_PATH=str(Path(temp)/'old.sqlite3'))
    def run(*args):
        subprocess.run([str(ROOT/'.venv/bin/python'),'manage.py',*args],cwd=ROOT,env=env,check=True)
    run('migrate','auth','--noinput')
    run('migrate','service','0004','--noinput')
    run('shell','-c', '''
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
apps=MigrationExecutor(connection).loader.project_state([('service','0004_assessmentevidence_siteconfiguration_and_more')]).apps
User=apps.get_model('auth','User'); Officer=apps.get_model('service','Officer'); Assignment=apps.get_model('service','OfficerAssignment'); Location=apps.get_model('service','Location'); Telegram=apps.get_model('service','TelegramUser'); Consent=apps.get_model('service','Consent'); Terms=apps.get_model('service','Terms'); Profile=apps.get_model('service','Profile'); App=apps.get_model('service','Application'); Evidence=apps.get_model('service','AssessmentEvidence')
location=Location.objects.create(name='Titik Lama Uji',category='IPWL',active=True)
web=User.objects.create(username='old-operator')
o=Officer.objects.create(web_user=web,verified=True,role='PELAKSANA',all_locations=True)
Assignment.objects.create(officer=o,location=location)
for i in range(2):
 u=Telegram.objects.create(telegram_id=990010+i)
 p=Profile.objects.create(user=u,data={'name':'Sintetis'})
 c=Consent.objects.create(user=u,terms=Terms.objects.get(active=True))
 app=App.objects.create(number=f'ROUTE-UPGRADE-{i}',applicant=p,identity={'name':'Sintetis'},consent=c,status='MENUNGGU_VERIFIKASI',location=location if i==0 else None)
 Evidence.objects.create(application=app,image=b'synthetic-legacy-image',mime='image/jpeg',checksum=f'hash-{i}',source_url='https://example.org/test')
''')
    run('migrate','--noinput')
    run('shell','-c', '''
from service.models import *
from service.access import cases_for
old=Application.objects.get(number='ROUTE-UPGRADE-0'); pending=Application.objects.get(number='ROUTE-UPGRADE-1')
assert old.routed_at and not old.location_selected_at and old.status=='MENUNGGU_VERIFIKASI'
assert pending.status=='MENUNGGU_TITIK_AKSES' and not pending.routed_at and pending.evidence.count()==1
operator=Officer.objects.get(web_user__username='old-operator')
assert not operator.all_locations
assert cases_for(operator).filter(pk=old.pk).exists()
assert not cases_for(operator).filter(pk=pending.pk).exists()
assert SiteConfiguration.objects.get(pk=1).self_assessment_url=='https://selfassessment.bnn.go.id/Transactions/Assist'
print('Route upgrade passed: existing routed case preserved, unassigned evidence waits for owner selection, location scope enforced.')
''')

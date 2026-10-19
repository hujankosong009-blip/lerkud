"""Isolated synthetic browser smoke test; no real bot calls or persistent users."""
import os
import secrets
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='salam-browser-') as temp:
    env=os.environ.copy()
    env.pop('DATABASE_URL',None)
    env.update(DJANGO_DEBUG='true',DJANGO_SECRET_KEY=secrets.token_hex(48),DJANGO_SQLITE_PATH=str(Path(temp)/'browser.sqlite3'),NOTIFICATION_MODE='simulation')
    password=secrets.token_urlsafe(24)
    def django(*args,**kwargs):
        return subprocess.run([str(ROOT/'.venv/bin/python'),'manage.py',*args],cwd=ROOT,env=env,check=True,**kwargs)
    django('migrate','--noinput',stdout=subprocess.DEVNULL)
    setup='''
import os
from django.contrib.auth import get_user_model
from service.models import *
from service.services import *
web=get_user_model().objects.create_user(username='petugas-uji',password=os.environ['BROWSER_TEST_PASSWORD'])
location=Location.objects.create(name='Lokasi Sintetis · Uji Antarmuka',category=Category.IPWL,active=True)
o=Officer.objects.create(web_user=web,verified=True)
OfficerAssignment.objects.create(officer=o,location=location,role=Role.COORD)
for i in range(4):
 u=TelegramUser.objects.create(telegram_id=70000+i)
 Consent.objects.create(user=u,terms=Terms.objects.get(active=True))
 RegistrationDraft.objects.create(user=u,data=dict(nik=f'{i:016}',name=f'Pemohon Sintetis {i+1}',phone='081234567890',address='Alamat Sintetis',city='Kota Uji',district='Kecamatan Uji',village='Kelurahan Uji',rt='001',rw='002'))
 app,_=submit_registration(u)
 if i:
  submit_screening(u,app,'Uraian sintetis untuk pengujian.')
  app.refresh_from_db()
  assign_application(o,app,location,'Penugasan sintetis',o)
 if i>1: app=update_progress(o,app,Status.REVIEW,'Tinjauan sintetis')
 if i>2: update_progress(o,app,Status.FOLLOWUP,'Tindak lanjut sintetis')
'''
    env['BROWSER_TEST_PASSWORD']=password
    django('shell','-c',setup,stdout=subprocess.DEVNULL)
    env.pop('BROWSER_TEST_PASSWORD')
    # Local requests only. Choose an isolated test port.
    server=subprocess.Popen([str(ROOT/'.venv/bin/python'),'manage.py','runserver','127.0.0.1:8765','--noreload'],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                with urlopen('http://127.0.0.1:8765/health/',timeout=1) as r:
                    if r.status==200: break
            except OSError: time.sleep(.1)
        else: raise RuntimeError('Browser test server failed to start')
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=os.getenv('CHROMIUM_PATH','/usr/bin/chromium'),args=['--no-sandbox'])
            page=browser.new_page(viewport={'width':1440,'height':1100},device_scale_factor=1)
            errors=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto('http://127.0.0.1:8765/login/')
            page.locator('[name=username]').fill('petugas-uji')
            page.locator('[name=password]').fill(password)
            page.get_by_role('button',name='Masuk ke dashboard').click()
            page.wait_for_url('http://127.0.0.1:8765/')
            assert page.get_by_role('heading',name='Ringkasan permohonan').is_visible()
            assert page.get_by_text('Notifikasi: SIMULASI').is_visible()
            page.screenshot(path=str(ROOT/'docs/dashboard-desktop.png'),full_page=True)
            page.get_by_role('link',name='Daftar pemohon',exact=False).first.click()
            assert page.locator('table tbody tr').count()==4
            page.locator('table tbody a').first.click()
            assert page.get_by_role('heading',name='Skrining naratif').is_visible()
            page.locator('[name=status]').select_option('PERLU_KELENGKAPAN')
            page.locator('[name=reason]').fill('Alasan sintetis untuk pengujian UI')
            page.locator('[name=public_text]').fill('Mohon melengkapi uraian sintetis.')
            page.get_by_role('button',name='Simpan progres').click()
            assert page.get_by_text('Progres disimpan. Notifikasi masuk antrean.').is_visible()
            page.goto('http://127.0.0.1:8765/')
            page.set_viewport_size({'width':390,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.screenshot(path=str(ROOT/'docs/dashboard-mobile.png'),full_page=True)
            page.get_by_role('link',name='Daftar pemohon',exact=False).first.click()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert page.get_by_role('button',name='Keluar',exact=True).is_visible()
            page.get_by_role('button',name='Keluar',exact=True).click()
            page.wait_for_url('**/login/')
            assert not errors, errors
            browser.close()
        print('Browser smoke passed: login, overview, list, detail, progress save, 1440px/390px layout; synthetic DB removed.')
    finally:
        server.terminate()
        server.wait(timeout=10)

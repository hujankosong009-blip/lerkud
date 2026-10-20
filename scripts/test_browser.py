"""Isolated browser smoke; all accounts, places and uploads are synthetic."""
import os
import secrets
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen
from playwright.sync_api import sync_playwright
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='salam-browser-') as temp:
    env=os.environ.copy(); env.pop('DATABASE_URL',None)
    env.update(DJANGO_DEBUG='true',DJANGO_SECRET_KEY=secrets.token_hex(48),DJANGO_SQLITE_PATH=str(Path(temp)/'browser.sqlite3'),NOTIFICATION_MODE='simulation')
    password=secrets.token_urlsafe(24)
    def django(*args,**kwargs):
        return subprocess.run([str(ROOT/'.venv/bin/python'),'manage.py',*args],cwd=ROOT,env=env,check=True,**kwargs)
    django('migrate','--noinput',stdout=subprocess.DEVNULL)
    setup='''
import os
from io import BytesIO
from PIL import Image
from django.contrib.auth import get_user_model
from service.models import *
from service.services import *
web=get_user_model().objects.create_user(username='superadmin-uji',password=os.environ['BROWSER_TEST_PASSWORD'],is_staff=True)
location=Location.objects.create(name='Lokasi Sintetis · Uji Antarmuka',category=Category.IPWL,active=True)
o=Officer.objects.create(web_user=web,verified=True,role=Role.SUPERADMIN)
OfficerAssignment.objects.create(officer=o,location=location)
config=site_config(); config.self_assessment_url='https://example.org/asesmen-uji'; config.save()
image=BytesIO(); Image.new('RGB',(140,100),'#4e7965').save(image,'PNG')
for i in range(4):
 u=TelegramUser.objects.create(telegram_id=70000+i)
 Consent.objects.create(user=u,terms=Terms.objects.get(active=True))
 RegistrationDraft.objects.create(user=u,data=dict(nik=f'{i:016}',name=f'Pemohon Sintetis {i+1}',phone='081234567890',address='Alamat Sintetis',city='Kota Uji',district='Kecamatan Uji',village='Kelurahan Uji',rt='001',rw='002'))
 app,_=submit_registration(u)
 submit_screening(u,app,f'Kendala Sintetis {i+1} untuk pengujian.')
 begin_assessment(u,app)
 if i:
  submit_evidence(u,app,image.getvalue())
  send_to_location(u,app,location)
 if i>1: app=verify_application(o,app,True,'Bukti sintetis sesuai')
 if i>2: update_progress(o,app,Status.FOLLOWUP,'Tindak lanjut sintetis')
'''
    env['BROWSER_TEST_PASSWORD']=password
    django('shell','-c',setup,stdout=subprocess.DEVNULL)
    env.pop('BROWSER_TEST_PASSWORD')
    image=Path(temp)/'proof.png'; Image.new('RGB',(120,80),'#668a71').save(image)
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
            errors=[]; page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto('http://127.0.0.1:8765/login/')
            page.locator('[name=username]').fill('superadmin-uji'); page.locator('[name=password]').fill(password)
            page.get_by_role('button',name='Masuk ke dashboard').click()
            page.wait_for_url('**/permohonan/')
            assert page.get_by_role('heading',name='Data Pemohon').is_visible()
            page.get_by_text('Telegram simulasi',exact=False).wait_for()
            assert page.locator('#data-table tbody tr').count()==4
            page.screenshot(path=str(ROOT/'docs/dashboard-desktop.png'),full_page=True)
            page.set_viewport_size({'width':390,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.screenshot(path=str(ROOT/'docs/dashboard-mobile.png'),full_page=True)
            page.set_viewport_size({'width':1440,'height':1100})
            # The page notices an external database update without any user click.
            django('shell','-c',"from service.models import Application; from django.utils import timezone; a=Application.objects.first(); a.updated_at=timezone.now(); a.save(update_fields=['updated_at'])",stdout=subprocess.DEVNULL)
            page.locator('#live-notice').wait_for(state='visible',timeout=15000)
            page.locator('[name=q]').fill('Kendala Sintetis 2'); page.get_by_role('button',name='Cari',exact=True).click()
            assert page.locator('#data-table tbody tr').count()==1
            page.locator('#data-table tbody a').first.click()
            assert page.get_by_role('heading',name='Bukti pengisian BOSS BNN').is_visible()
            page.locator('[name=verify-decision]').select_option('accept')
            page.locator('[name=verify-note]').fill('Bukti sesuai pada uji browser')
            page.get_by_role('button',name='Simpan verifikasi',exact=True).click()
            assert page.get_by_text('Verifikasi disimpan.',exact=False).is_visible()
            page.goto('http://127.0.0.1:8765/permohonan/?q=Pemohon+Sintetis+1')
            page.locator('#data-table a[title="Lihat berkas"]').click()
            page.get_by_role('link',name='Unggah bukti',exact=True).click()
            page.locator('[name=screenshot]').set_input_files(str(image)); page.locator('[name=confirm]').check()
            page.get_by_role('button',name='Simpan',exact=True).click()
            assert page.get_by_text('Bukti tersimpan. Jika lokasi belum dipilih',exact=False).is_visible()
            assert page.locator('img.proof-image').count()==1
            page.get_by_role('link',name='Edit data',exact=True).click()
            page.locator('[name=name]').fill('Pemohon Sintetis Koreksi')
            page.locator('[name=reason]').fill('Koreksi sintetis')
            page.get_by_role('button',name='Simpan',exact=True).click()
            assert page.get_by_role('heading',name='Pemohon Sintetis Koreksi',exact=True).is_visible()
            page.goto('http://127.0.0.1:8765/tampilan/')
            page.locator('[name=subtitle]').fill('Mudah diakses, cepat ditindaklanjuti.')
            page.locator('[name=logo_upload]').set_input_files(str(image))
            page.get_by_role('button',name='Simpan',exact=True).click()
            assert page.locator('img.brand-logo').count()==1
            page.goto('http://127.0.0.1:8765/akun/')
            page.locator('[name=username]').fill('pelaksana-browser')
            page.locator('[name=password1]').fill('Synthetic-browser-password-8972')
            page.locator('[name=password2]').fill('Synthetic-browser-password-8972')
            page.locator('[name=location]').select_option(label='Lokasi Sintetis · Uji Antarmuka')
            page.get_by_role('button',name='Tambah akun',exact=True).click()
            assert page.get_by_text('Akun dibuat.',exact=False).is_visible()
            page.goto('http://127.0.0.1:8765/permohonan/')
            page.set_viewport_size({'width':390,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.get_by_role('button',name='Keluar',exact=True).click(); page.wait_for_url('**/login/')
            assert page.locator('img.login-logo').is_visible()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert not errors,errors
            browser.close()
        print('Browser passed: login, unified table/search, live notice, verification, image upload, edit, branding/logo, account creation, mobile layout/logout. Synthetic DB removed.')
    finally:
        server.terminate(); server.wait(timeout=10)

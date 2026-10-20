from datetime import timedelta, datetime, timezone as dt_timezone
from io import BytesIO, StringIO
from unittest.mock import patch
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings, Client
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from service.models import *
from service.services import *
from service.access import cases_for, has_role, officer_active
from service.bot import handle_update, directory
from service.notifications import process_one, enqueue_reminders
from service.telegram_api import DeliveryError, keyboard, bot_call
from service.uploads import clean_image

DATA=dict(nik='0000000000000001',name='Pemohon Sintetis',phone='081234567890',address='Alamat Uji',city='Kota Uji',district='Kecamatan Uji',village='Kelurahan Uji',rt='001',rw='002')

def picture(color='green'):
    output=BytesIO()
    Image.new('RGB',(64,48),color).save(output,'PNG')
    return output.getvalue()

class WorkflowTests(TestCase):
    def setUp(self):
        self.user=TelegramUser.objects.create(telegram_id=100001,notification_decided=True,bot_notifications=True)
        self.other=TelegramUser.objects.create(telegram_id=100002)
        self.terms=Terms.objects.get(active=True)
        self.sequence=0
        self.a=Location.objects.create(name='Lokasi Sintetis A',category=Category.IPWL,active=True)
        self.b=Location.objects.create(name='Lokasi Sintetis B',category=Category.LRKM,active=True)
        self.manager=self.officer('superadmin',self.a,Role.SUPERADMIN)
        self.local=self.officer('pelaksana-a',self.a,Role.PELAKSANA)
        self.local_b=self.officer('pelaksana-b',self.b,Role.PELAKSANA)
        self.staff_user=TelegramUser.objects.create(telegram_id=100003,bot_notifications=True,notification_decided=True)
        self.local.telegram=self.staff_user; self.local.save()
        config=site_config(); config.self_assessment_url='https://example.org/asesmen-uji'; config.save()
    def officer(self,name,location,role):
        web=get_user_model().objects.create_user(username=name,password='synthetic-test-password',is_staff=role==Role.SUPERADMIN)
        o=Officer.objects.create(web_user=web,role=role,verified=True)
        OfficerAssignment.objects.create(officer=o,location=location)
        return o
    def bot(self,action='',text='',user=None,photo=None,update_id=None):
        self.sequence+=1
        return handle_update(update_id or self.sequence,(user or self.user).telegram_id,action=action,text=text,photo=photo)
    def register(self,user=None):
        user=user or self.user
        Consent.objects.get_or_create(user=user,terms=self.terms)
        RegistrationDraft.objects.create(user=user,data=DATA.copy(),step=9)
        return submit_registration(user)[0]
    def with_screen(self):
        app=self.register()
        submit_screening(self.user,app,'Kendala sintetis untuk pengujian.')
        app.refresh_from_db()
        return app
    def ready(self):
        app=self.with_screen()
        begin_assessment(self.user,app)
        submit_evidence(self.user,app,picture())
        app.refresh_from_db()
        send_to_location(self.user,app,self.a)
        app.refresh_from_db()
        assign_application(self.manager,app,self.a,'Penugasan uji',self.local)
        app.refresh_from_db()
        return app
    def test_start_two_choices_and_registration_draft_survives(self):
        self.bot(action='register'); self.bot(text=DATA['nik'])
        response=self.bot(text='/start')[0]
        self.assertEqual([b[1] for b in response['buttons']],['public','admin'])
        self.assertEqual(RegistrationDraft.objects.get(user=self.user).data['nik'],DATA['nik'])
        response=self.bot(action='public')
        self.assertEqual(len(response[0]['buttons']),7)
        self.assertEqual(response[1]['buttons'][0][1],'resume')
    def test_private_only(self):
        handle_update(900,123,text='/start',private=False,photo=picture())
        self.assertFalse(TelegramUser.objects.filter(telegram_id=123).exists())
    def test_consent_prompt_explicit_not_silently_enabled(self):
        response=self.bot(action='register',user=self.other)[0]
        self.assertIn('notify_register',[x[1] for x in response['buttons']])
        self.other.refresh_from_db(); self.assertFalse(self.other.bot_notifications)
        self.bot(action='notify_register',user=self.other)
        self.other.refresh_from_db(); self.assertTrue(self.other.bot_notifications)
        self.assertIsNotNone(self.other.notification_consent_at)
        self.bot(action='notify_off',user=self.other)
        self.other.refresh_from_db(); self.assertFalse(self.other.bot_notifications)
    def test_registration_edit_mask_exact_success_and_auto_screen(self):
        self.bot(action='register')
        for key,_ in FIELDS: response=self.bot(text=DATA[key])
        self.assertNotIn(DATA['nik'],response[0]['text'])
        self.bot(action='field:rt'); self.bot(text='007')
        self.bot(action=f'agree:{self.terms.pk}')
        response=self.bot(action='submit')
        self.assertEqual(response[0]['text'],SUCCESS)
        self.user.refresh_from_db(); self.assertEqual(self.user.state['mode'],'screening')
        app=Application.objects.get()
        self.assertEqual(app.identity['rt'],'007'); self.assertEqual(app.identity['phone'],'+6281234567890')
        self.bot(action='submit'); self.assertEqual(Application.objects.count(),1)
    def test_registration_server_idempotence_and_constraint(self):
        app=self.register(); again,created=submit_registration(self.user)
        self.assertFalse(created); self.assertEqual(app.pk,again.pk)
        with self.assertRaises(IntegrityError),transaction.atomic():
            Application.objects.create(number='DUPLICATE-TEST',applicant=app.applicant,identity=DATA,consent=app.consent)
    def test_validations(self):
        for key,val in [('nik','123'),('nik','١'*16),('phone','no'),('name',' '),('address',' '),('city',''),('rt','A1'),('rw','-1')]:
            with self.subTest(key=key),self.assertRaises(ValidationError): validate_field(key,val)
        self.assertEqual(validate_field('rt','001'),'001')
    def test_consent_required_and_current_terms(self):
        RegistrationDraft.objects.create(user=self.user,data=DATA)
        with self.assertRaises(ValidationError): submit_registration(self.user)
        Consent.objects.create(user=self.user,terms=self.terms)
        self.terms.active=False; self.terms.save()
        Terms.objects.create(version='2',body='Ketentuan sintetis baru',active=True)
        with self.assertRaises(ValidationError): submit_registration(self.user)
    def test_cancel_draft_does_not_remove_application(self):
        app=self.register(); self.bot(action='confirm_cancel')
        self.assertTrue(Application.objects.filter(pk=app.pk).exists())
    def test_duplicate_nik_no_cross_owner_disclosure(self):
        first=self.register(); second=self.register(self.other)
        self.assertTrue(second.duplicate_review)
        with self.assertRaises(PermissionDenied): public_progress(self.other,first)
        self.assertNotIn(first.number,self.bot(action=f'my:{first.pk}',user=self.other)[0]['text'])
    def test_bot_seamless_screen_to_external_link(self):
        self.register(); self.bot(action='screen'); self.bot(text='Uraian sintetis')
        response=self.bot(action='screen_send')
        self.assertTrue(any(any(b[1].startswith('url:https://example.org') for b in r['buttons']) for r in response))
        self.assertEqual(Application.objects.get().status,Status.WAIT_PROOF)
        self.assertEqual(AssessmentResponse.objects.count(),0)
    def test_draft_screen_survives_menu_and_start(self):
        app=self.register(); self.bot(action='screen'); self.bot(text='Draft sintetis')
        self.bot(text='/start'); self.bot(action='public'); self.bot(action='directory')
        self.assertIn('Draft sintetis',self.bot(action='screen')[0]['text'])
        self.bot(action='screen_send'); self.assertEqual(app.screenings.get().text,'Draft sintetis')
    def test_self_and_screen_prerequisites(self):
        response=self.bot(action='screen',user=self.other)[0]
        self.assertEqual(response['buttons'][0][1],'register')
        app=self.register()
        self.assertIn('Sampaikan kendala',self.bot(action='self')[0]['text'])
        with self.assertRaises(ValidationError): begin_assessment(self.user,app)
    def test_missing_external_url_blocks_no_invented_link_or_result(self):
        app=self.with_screen(); config=site_config(); config.self_assessment_url=''; config.save()
        response=self.bot(action='self')[0]
        self.assertIn('sedang disiapkan',response['text'])
        self.assertFalse(any(a.startswith('url:') for _,a in response['buttons']))
        self.assertEqual(AssessmentResponse.objects.count(),0)
        with self.assertRaises(ValidationError): begin_assessment(self.user,app)
    def test_bukti_consent_and_upload_complete_dossier(self):
        app=self.with_screen(); self.bot(action='self'); self.bot(action='evidence_begin')
        self.assertFalse(app.evidence.exists())
        self.bot(action='evidence_consent')
        response=self.bot(photo=picture())
        self.assertIn('Bukti pengisian sudah tersimpan',response[0]['text'])
        app.refresh_from_db(); self.assertEqual(app.status,Status.WAIT_LOCATION)
        self.assertFalse(app.notifications.filter(event='dossier_ready',recipient=self.staff_user).exists())
        self.bot(action=f'loc_pick:{self.a.pk}')
        self.bot(action=f'loc_send:{self.a.pk}')
        app.refresh_from_db(); self.assertEqual(app.status,Status.WAIT_VERIFY)
        item=app.evidence.get(); self.assertIsNone(item.verified_at)
        self.assertTrue(app.notifications.filter(event='dossier_ready',recipient=self.staff_user).exists())
    def test_no_staff_notification_before_all_three_parts(self):
        app=self.with_screen()
        self.assertFalse(Notification.objects.filter(recipient=self.staff_user).exists())
        begin_assessment(self.user,app); submit_evidence(self.user,app,picture())
        self.assertFalse(Notification.objects.filter(recipient=self.staff_user).exists())
        send_to_location(self.user,app,self.a)
        self.assertEqual(Notification.objects.filter(recipient=self.staff_user,event='dossier_ready').count(),1)
    def test_evidence_server_gate_and_owner(self):
        app=self.register()
        with self.assertRaises(ValidationError): submit_evidence(self.user,app,picture())
        app=self.with_screen_after_existing(app)
        with self.assertRaises(PermissionDenied): submit_evidence(self.other,app,picture())
    def with_screen_after_existing(self,app):
        submit_screening(self.user,app,'Kendala uji'); begin_assessment(self.user,app); app.refresh_from_db(); return app
    def test_evidence_repeat_dedupes(self):
        app=self.with_screen(); begin_assessment(self.user,app)
        first=submit_evidence(self.user,app,picture()); second=submit_evidence(self.user,app,picture())
        self.assertEqual(first.pk,second.pk); self.assertEqual(app.evidence.count(),1)
    def test_invalid_oversize_svg_images_rejected(self):
        for data in [b'<svg><script>bad</script></svg>',b'',b'x'*(5*1024*1024+1)]:
            with self.subTest(size=len(data)),self.assertRaises(ValidationError): clean_image(data)
        image,mime,_=clean_image(picture()); self.assertEqual(mime,'image/jpeg'); self.assertTrue(image.startswith(b'\xff\xd8'))
    def test_image_private_and_revoked_scope(self):
        app=self.ready(); evidence=app.evidence.get(); url=f'/bukti/{evidence.pk}/'
        self.assertEqual(self.client.get(url).status_code,302)
        self.client.force_login(self.local_b.web_user); self.assertEqual(self.client.get(url).status_code,404)
        self.client.force_login(self.local.web_user); response=self.client.get(url)
        self.assertEqual(response.status_code,200); self.assertIn('no-store',response['Cache-Control'])
        self.local.verified=False; self.local.save(); self.assertEqual(self.client.get(url).status_code,403)
    def test_two_roles_only_and_scope(self):
        self.assertEqual(Role.values,['SUPERADMIN','PELAKSANA'])
        app=self.ready()
        self.assertTrue(cases_for(self.local).filter(pk=app.pk).exists())
        self.assertFalse(cases_for(self.local_b).filter(pk=app.pk).exists())
        self.assertTrue(cases_for(self.manager).filter(pk=app.pk).exists())
        with self.assertRaises(PermissionDenied): assign_application(self.local,app,self.b,'Niet')
    def test_web_account_disabled_also_revokes_bot(self):
        self.local.web_user.is_active=False; self.local.web_user.save()
        self.assertFalse(officer_active(self.local))
        self.assertFalse(cases_for(self.local).exists())
    def test_verification_required_before_review(self):
        app=self.ready()
        with self.assertRaises(ValidationError): update_progress(self.local,app,Status.REVIEW,'Melompati verifikasi')
        app=verify_application(self.local,app,True,'Bukti dan identitas sesuai','Berkas Anda terverifikasi.')
        self.assertEqual(app.status,Status.REVIEW)
        self.assertIsNotNone(app.evidence.get().verified_at)
    def test_reject_reupload_preserves_versions(self):
        app=self.ready(); app=verify_application(self.local,app,False,'Gambar belum jelas','Mohon kirim ulang bukti yang jelas.')
        self.assertEqual(app.status,Status.NEED_INFO)
        begin_assessment(self.user,app); submit_evidence(self.user,app,picture('blue'))
        app.refresh_from_db(); self.assertEqual(app.evidence.count(),2)
        self.assertEqual(app.status,Status.WAIT_VERIFY)
    def test_bot_executor_verification(self):
        app=self.ready()
        self.bot(action=f'admin_verify:{app.pk}',user=self.staff_user)
        self.bot(text='Berkas sesuai',user=self.staff_user)
        app.refresh_from_db(); self.assertEqual(app.status,Status.REVIEW)
    def test_status_rules_internal_hidden_audited(self):
        app=self.ready()
        with self.assertRaises(ValidationError): update_progress(self.local,app,Status.DONE,'Tidak sah')
        app=verify_application(self.local,app,True,'Catatan verifikasi internal','Berkas diterima.')
        app=update_progress(self.local,app,Status.FOLLOWUP,'Alasan internal','Petugas menindaklanjuti.','Catatan sangat rahasia')
        text=public_progress(self.user,app)
        self.assertIn('Petugas menindaklanjuti.',text); self.assertNotIn('Catatan sangat rahasia',text); self.assertNotIn('Alasan internal',text)
        self.assertTrue(Audit.objects.filter(action='progress.updated').exists())
    def test_stale_update_rejected(self):
        app=self.ready(); verify_application(self.local,app,True,'Sesuai')
        with self.assertRaises(ValidationError): update_progress(self.local,app,Status.CANCELLED,'Lama',expected_status=Status.WAIT_VERIFY)
    def test_closed_reopen_superadmin_only(self):
        app=self.ready(); app=update_progress(self.local,app,Status.CANCELLED,'Alasan sah')
        with self.assertRaises(PermissionDenied): update_progress(self.local,app,Status.REVIEW,'Buka',reopen=True)
        app=update_progress(self.manager,app,Status.REVIEW,'Buka kembali',reopen=True)
        self.assertEqual(app.status,Status.REVIEW)
    def test_activation_bound_existing_account_no_duplicate(self):
        raw,code=create_activation(self.b,Role.PELAKSANA,officer=self.local_b)
        self.assertNotEqual(raw,code.digest)
        self.assertTrue(activate(self.other,raw)); self.assertFalse(activate(self.user,raw))
        self.local_b.refresh_from_db(); self.assertEqual(self.local_b.telegram,self.other)
        self.assertEqual(Officer.objects.count(),3)
    def test_wrong_expired_code_and_rate_limit(self):
        raw,code=create_activation(self.a,Role.PELAKSANA)
        code.expires_at=timezone.now()-timedelta(seconds=1); code.save()
        self.assertFalse(activate(self.other,raw))
        for _ in range(4): self.assertFalse(activate(self.other,'wrong'))
        valid,_=create_activation(self.a,Role.PELAKSANA)
        self.assertFalse(activate(self.other,valid))
        self.assertEqual(ActivationAttempt.objects.filter(user=self.other).count(),5)
    def test_empty_directory_and_inactive_locations(self):
        Location.objects.all().update(active=False)
        self.assertEqual(len(self.bot(action='directory')[0]['buttons']),7)
        self.assertIn('sedang disiapkan',directory(Category.IPWL)['text'])
    def test_duplicate_update_and_callback_size(self):
        self.bot(action='register',update_id=500); self.bot(text=DATA['nik'],update_id=501); self.bot(text=DATA['nik'],update_id=501)
        self.assertEqual(RegistrationDraft.objects.get(user=self.user).step,1)
        RegistrationDraft.objects.filter(user=self.user).delete()
        app=self.ready()
        for r in self.bot(action=f'admin_case:{app.pk}',user=self.staff_user):
            for _,action in r['buttons']: self.assertLessEqual(len(action.encode()),64)
    @override_settings(NOTIFICATION_MODE='simulation')
    def test_simulation_never_sends(self):
        app=self.register()
        with patch('service.notifications.bot_call') as send: process_one(); send.assert_not_called()
        n=app.notifications.get(); self.assertEqual(n.status,'simulated'); self.assertIsNone(n.sent_at)
    @override_settings(NOTIFICATION_MODE='live')
    def test_live_notif_automatic_payload_safe_with_action_button(self):
        app=self.ready()
        with patch('service.notifications.bot_call',return_value={'message_id':77}) as send:
            while process_one(): pass
        n=Notification.objects.get(recipient=self.staff_user,event='dossier_ready')
        self.assertEqual(n.status,'sent')
        for call in send.call_args_list:
            payload=call.args[1]
            self.assertNotIn(DATA['nik'],str(payload)); self.assertNotIn(DATA['name'],str(payload))
            self.assertIn('reply_markup',payload)
    @override_settings(NOTIFICATION_MODE='live')
    def test_failure_not_loss_and_retry_after(self):
        app=self.register(); before=timezone.now()
        with patch('service.notifications.bot_call',side_effect=DeliveryError('telegram_rate_limit',3600)): process_one()
        n=app.notifications.get(); self.assertEqual(n.status,'failed'); self.assertIsNone(n.sent_at)
        self.assertGreaterEqual(n.next_attempt_at,before+timedelta(seconds=3600)); self.assertFalse(process_one())
        self.assertTrue(Application.objects.filter(pk=app.pk).exists())
    @override_settings(NOTIFICATION_MODE='live')
    def test_consent_and_revocation_at_delivery(self):
        self.user.bot_notifications=False; self.user.save()
        app=self.ready(); self.local.verified=False; self.local.save()
        with patch('service.notifications.bot_call') as send:
            while process_one(): pass
            send.assert_not_called()
        self.assertTrue(Notification.objects.filter(error='recipient_not_consented').exists())
        self.assertTrue(Notification.objects.filter(error='recipient_access_revoked').exists())
    def test_recipient_link_identity_once_and_expired(self):
        raw=create_recipient_link(self.user)
        self.assertFalse(verify_recipient_link(raw,self.other.telegram_id)); self.assertTrue(verify_recipient_link(raw,self.user.telegram_id)); self.assertFalse(verify_recipient_link(raw,self.user.telegram_id))
        raw=create_recipient_link(self.other); RecipientLink.objects.filter(user=self.other).update(expires_at=timezone.now()-timedelta(seconds=1))
        self.assertFalse(verify_recipient_link(raw,self.other.telegram_id))
    def test_archive_restore_and_no_unauthorized_delete(self):
        app=self.ready()
        with self.assertRaises(PermissionDenied): archive_application(self.local,app,'Tidak boleh')
        archive_application(self.manager,app,'Data uji')
        self.assertFalse(cases_for(self.manager).filter(pk=app.pk).exists())
        app.refresh_from_db()
        with self.assertRaises(PermissionDenied): public_progress(self.user,app)
        self.assertTrue(app.evidence.exists())
        restore_application(self.manager,app)
        self.assertTrue(cases_for(self.manager).filter(pk=app.pk).exists())
    def test_crud_edits_versioned_and_stale_rejected(self):
        app=self.ready(); changed=dict(app.identity,name='Nama Koreksi Sintetis')
        app=edit_application(self.local,app,changed,'Koreksi','Kendala baru',app.updated_at.isoformat())
        self.assertEqual(app.identity['name'],'Nama Koreksi Sintetis'); self.assertEqual(app.screenings.count(),2)
        with self.assertRaises(ValidationError): edit_application(self.local,app,changed,'Lama',expected_updated='old')
    def test_web_tabs_search_each_table_and_access(self):
        app=self.ready(); self.client.force_login(self.local.web_user)
        for tab,q in [('applicant','Pemohon'),('screening','Kendala'),('proof','Pemohon')]:
            response=self.client.get('/permohonan/',{'tab':tab,'q':q})
            self.assertEqual(response.status_code,200); self.assertContains(response,app.number)
        self.assertNotContains(self.client.get('/permohonan/',{'q':'unknown'}),app.number)
        self.assertEqual(self.client.get('/akun/').status_code,403)
        self.assertEqual(self.client.get('/tampilan/').status_code,403)
        self.client.force_login(self.local_b.web_user)
        self.assertNotContains(self.client.get('/permohonan/',{'location':self.a.pk,'from':'2026-99-99'}),app.number)
    def test_web_verification_and_csrf(self):
        app=self.ready(); self.client.force_login(self.local.web_user)
        response=self.client.post(f'/permohonan/{app.pk}/',{'action':'verify','verify-decision':'accept','verify-note':'Sesuai','verify-public_text':'Berkas diterima'})
        self.assertEqual(response.status_code,302)
        app.refresh_from_db(); self.assertEqual(app.status,Status.REVIEW)
        secure=Client(enforce_csrf_checks=True); secure.force_login(self.local.web_user)
        self.assertEqual(secure.post(f'/permohonan/{app.pk}/',{}).status_code,403)
    def test_form_create_requires_owner_terms_and_no_duplicates(self):
        Consent.objects.create(user=self.other,terms=self.terms)
        self.client.force_login(self.manager.web_user)
        data={**DATA,'telegram':self.other.pk,'reason':'Dibantu petugas','screening':'Kendala uji'}
        self.assertEqual(self.client.post('/permohonan/tambah/',data).status_code,302)
        self.assertEqual(Application.objects.filter(applicant__user=self.other).count(),1)
        self.assertEqual(self.client.post('/permohonan/tambah/',data).status_code,200)
        self.assertEqual(Application.objects.filter(applicant__user=self.other).count(),1)
    def test_branding_logo_and_https_link(self):
        self.client.force_login(self.manager.web_user)
        response=self.client.post('/tampilan/',{'title':'LAYANAN UJI','subtitle':'Judul uji','description':'Deskripsi uji','self_assessment_url':'https://example.org/assessment','logo_upload':SimpleUploadedFile('logo.png',picture(),'image/png')})
        self.assertEqual(response.status_code,302); self.assertEqual(site_config().title,'LAYANAN UJI')
        self.assertEqual(self.client.get('/logo/').status_code,200)
        self.assertContains(self.client.get('/permohonan/'),'LAYANAN UJI')
        response=self.client.post('/tampilan/',{'title':'Test','subtitle':'Test','description':'Test','self_assessment_url':'http://example.org'})
        self.assertEqual(response.status_code,200); self.assertContains(response,'HTTPS')
    def test_accounts_create_edit_disable_and_role_choices(self):
        self.client.force_login(self.manager.web_user)
        response=self.client.post('/akun/',{'username':'baru','password1':'Strong-example-password-7823','password2':'Strong-example-password-7823','role':Role.PELAKSANA,'location':self.a.pk})
        self.assertEqual(response.status_code,302)
        officer=Officer.objects.get(web_user__username='baru')
        self.assertEqual(officer.role,Role.PELAKSANA); self.assertFalse(officer.web_user.is_superuser)
        response=self.client.post(f'/akun/{officer.pk}/',{'username':'baru','role':Role.PELAKSANA,'location':self.a.pk})
        self.assertEqual(response.status_code,302); officer.refresh_from_db(); self.assertFalse(officer.verified)
    def test_last_manager_and_own_disable_protected(self):
        self.client.force_login(self.manager.web_user)
        response=self.client.post(f'/akun/{self.manager.pk}/',{'username':'superadmin','role':Role.PELAKSANA,'location':self.a.pk,'active':'on'})
        self.assertEqual(response.status_code,200); self.assertContains(response,'Minimal satu Superadmin')
        self.manager.refresh_from_db(); self.assertEqual(self.manager.role,Role.SUPERADMIN)
        response=self.client.post(f'/akun/{self.manager.pk}/',{'username':'superadmin','role':Role.SUPERADMIN})
        self.assertContains(response,'menonaktifkan akun sendiri')
    def test_live_events_only_metadata_and_scope(self):
        app=self.ready(); self.client.force_login(self.local.web_user)
        data=self.client.get('/pembaruan/').json()
        self.assertEqual(data['waiting'],1); self.assertNotIn(DATA['nik'],str(data)); self.assertNotIn('Pemohon',str(data))
        self.client.force_login(self.local_b.web_user); self.assertEqual(self.client.get('/pembaruan/').json()['total'],0)
    def test_utc_to_jakarta(self):
        app=self.register(); Application.objects.filter(pk=app.pk).update(updated_at=datetime(2026,1,2,23,30,tzinfo=dt_timezone.utc)); app.refresh_from_db()
        self.assertIn('03/01/2026 06:30 WIB',public_progress(self.user,app))
    def test_login_rate_limit(self):
        for _ in range(10): self.client.post('/login/',{'username':'no','password':'bad'})
        self.assertEqual(self.client.post('/login/',{}).status_code,429)
    def test_reminders_idempotent(self):
        app=self.ready(); Application.objects.filter(pk=app.pk).update(updated_at=timezone.now()-timedelta(days=10))
        enqueue_reminders(); enqueue_reminders()
        self.assertEqual(Notification.objects.filter(event='reminder',recipient=self.staff_user).count(),1)
    def test_bogus_callbacks_safe_and_no_role_escalation(self):
        for action in ['my:bad','agree:bad','field:bad','screen_send','evidence_consent',f'admin_verify:bad']:
            self.assertTrue(self.bot(action=action,user=self.other))
        self.assertFalse(Officer.objects.filter(telegram=self.other).exists())
    def test_url_keyboard_and_token_error_sanitization(self):
        self.assertIn('url',keyboard([('Buka','url:https://example.org')])['inline_keyboard'][0][0])
        with self.assertRaises(DeliveryError): keyboard([('Unsafe','url:http://example.org')])
        with override_settings(TELEGRAM_BOT_TOKEN='invalid token value'):
            with self.assertRaises(DeliveryError) as error: bot_call('getUpdates',{})
            self.assertNotIn('invalid token value',str(error.exception))
    def test_bot_starts_embedded_notification_worker_by_default(self):
        from django.core.management import call_command
        with override_settings(TELEGRAM_BOT_TOKEN='1:'+'x'*35),patch('service.management.commands.run_bot.threading.Thread') as thread,patch('service.management.commands.run_bot.bot_call',side_effect=KeyboardInterrupt),patch('service.management.commands.run_bot.close_old_connections'):
            call_command('run_bot',stdout=StringIO())
            thread.return_value.start.assert_called_once()
            thread.return_value.join.assert_called_once()
    def test_terms_body_cannot_silently_change(self):
        from service.admin import TermsForm
        form=TermsForm(data={'version':self.terms.version,'body':'Changed','active':True,'published_at':self.terms.published_at},instance=self.terms)
        self.assertFalse(form.is_valid())
    def test_domicile_rule_does_not_override_applicant_location_choice(self):
        RoutingRule.objects.create(city=DATA['city'],district=DATA['district'],village=DATA['village'],location=self.b)
        app=self.with_screen()
        self.assertIsNone(app.location_id)
        begin_assessment(self.user,app); submit_evidence(self.user,app,picture())
        send_to_location(self.user,app,self.b)
        app.refresh_from_db()
        self.assertEqual(app.location_id,self.b.pk)
        self.assertEqual(app.assignment_history.count(),1)
        self.assertFalse(cases_for(self.local).filter(pk=app.pk).exists())
        self.assertTrue(cases_for(self.local_b).filter(pk=app.pk).exists())
    @override_settings(NOTIFICATION_MODE='live',NOTIFICATION_CHANNEL='mtproto')
    def test_unlinked_mtproto_does_not_send(self):
        self.register()
        with patch('service.notifications.mtproto_send') as send:
            process_one(); send.assert_not_called()
        self.assertEqual(Notification.objects.get().error,'recipient_not_verified_or_consented')
    def test_executor_cannot_post_accounts_or_branding(self):
        self.client.force_login(self.local.web_user)
        count=get_user_model().objects.count()
        self.assertEqual(self.client.post('/akun/',{'username':'unauthorized','role':Role.SUPERADMIN}).status_code,403)
        self.assertEqual(self.client.post('/tampilan/',{'title':'Unauthorized'}).status_code,403)
        self.assertEqual(get_user_model().objects.count(),count)
        self.assertNotEqual(site_config().title,'Unauthorized')
    def test_rejected_same_image_does_not_claim_complete(self):
        app=self.ready(); verify_application(self.local,app,False,'Bukti perlu diperbaiki')
        begin_assessment(self.user,app)
        with self.assertRaises(ValidationError): submit_evidence(self.user,app,picture())
        app.refresh_from_db(); self.assertEqual(app.status,Status.NEED_INFO)
        self.assertEqual(app.evidence.count(),1)
    def test_private_evidence_view_in_bot_and_scope(self):
        app=self.ready()
        result=self.bot(action=f'admin_proof:{app.pk}',user=self.staff_user)[0]
        self.assertEqual(result['evidence_id'],app.evidence.get().pk)
        rejected=self.bot(action=f'admin_proof:{app.pk}',user=self.other)[0]
        self.assertNotIn('evidence_id',rejected)
    def test_sending_proof_rechecks_access_and_normalized_image(self):
        from unittest.mock import MagicMock
        from service.telegram_api import send_reply
        app=self.ready(); result=self.bot(action=f'admin_proof:{app.pk}',user=self.staff_user)[0]
        context=MagicMock(); context.__enter__.return_value.read.return_value=b'{"ok":true,"result":{"message_id":10}}'
        with override_settings(TELEGRAM_BOT_TOKEN='1:'+'x'*35),patch('service.telegram_api.urlopen',return_value=context) as transport:
            send_reply(self.staff_user.telegram_id,result)
            self.assertIn(b'Content-Type: image/jpeg',transport.call_args.args[0].data)
            self.assertIn(b'protect_content',transport.call_args.args[0].data)
        self.local.verified=False; self.local.save()
        with patch('service.telegram_api.urlopen') as transport:
            with self.assertRaises(DeliveryError): send_reply(self.staff_user.telegram_id,result)
            transport.assert_not_called()
    def test_location_selection_required_before_operator_access(self):
        app=self.with_screen(); begin_assessment(self.user,app); submit_evidence(self.user,app,picture())
        app.refresh_from_db()
        self.assertEqual(app.status,Status.WAIT_LOCATION)
        self.assertIsNone(app.routed_at)
        self.assertFalse(cases_for(self.local).filter(pk=app.pk).exists())
        self.assertFalse(cases_for(self.local_b).filter(pk=app.pk).exists())
        with self.assertRaises(PermissionDenied): require_case(self.local,app)
        with self.assertRaises(ValidationError): assign_application(self.manager,app,self.a,'Belum dikonfirmasi pemohon')
        send_to_location(self.user,app,self.a)
        self.assertTrue(cases_for(self.local).filter(pk=app.pk).exists())
        self.assertFalse(cases_for(self.local_b).filter(pk=app.pk).exists())
    @override_settings(NOTIFICATION_MODE='live')
    def test_direct_admin_notification_only_to_selected_location(self):
        tg_b=TelegramUser.objects.create(telegram_id=100004,bot_notifications=True)
        self.local_b.telegram=tg_b; self.local_b.all_locations=True; self.local_b.save()
        app=self.with_screen(); begin_assessment(self.user,app); submit_evidence(self.user,app,picture())
        send_to_location(self.user,app,self.b)
        self.assertFalse(app.notifications.filter(recipient=self.staff_user).exists())
        self.assertEqual(app.notifications.filter(recipient=tg_b,event='dossier_ready').count(),1)
        with patch('service.notifications.bot_call',return_value={'message_id':77}) as transport:
            while process_one(): pass
        chat_ids=[call.args[1]['chat_id'] for call in transport.call_args_list]
        self.assertIn(tg_b.telegram_id,chat_ids)
        self.assertNotIn(self.staff_user.telegram_id,chat_ids)
        self.assertEqual(app.notifications.get(recipient=tg_b,event='dossier_ready').status,'sent')
        app.refresh_from_db(); self.assertFalse(cases_for(self.local).filter(pk=app.pk).exists())
    def test_location_send_idempotence_and_forbidden_switch(self):
        app=self.with_screen(); begin_assessment(self.user,app); submit_evidence(self.user,app,picture())
        with self.assertRaises(PermissionDenied): send_to_location(self.other,app,self.a)
        first,created=send_to_location(self.user,app,self.a)
        self.assertTrue(created)
        count=first.notifications.count()
        _,created=send_to_location(self.user,app,self.a)
        self.assertFalse(created); self.assertEqual(first.notifications.count(),count)
        with self.assertRaises(ValidationError): send_to_location(self.user,app,self.b)
        app.refresh_from_db(); self.assertEqual(app.location,self.a)
    def test_inactive_coordinator_or_premature_location_rejected(self):
        app=self.register()
        with self.assertRaises(ValidationError): send_to_location(self.user,app,self.a)
        submit_screening(self.user,app,'Kendala'); begin_assessment(self.user,app); submit_evidence(self.user,app,picture())
        self.a.active=False; self.a.save()
        with self.assertRaises(ValidationError): send_to_location(self.user,app,self.a)
        coord=Location.objects.create(name='Koordinator Uji',category=Category.COORD,active=True)
        with self.assertRaises(ValidationError): send_to_location(self.user,app,coord)
    def test_empty_location_choices_keep_evidence(self):
        app=self.with_screen(); self.bot(action='self'); self.bot(action='evidence_consent'); self.bot(photo=picture())
        Location.objects.all().update(active=False)
        response=self.bot(action='loc_category:0')[0]
        self.assertIn('Belum ada titik akses aktif',response['text'])
        app.refresh_from_db(); self.assertEqual(app.status,Status.WAIT_LOCATION)
        self.assertEqual(app.evidence.count(),1)
    def test_legacy_all_locations_does_not_bypass_location_scope(self):
        app=self.ready()
        self.local_b.all_locations=True; self.local_b.save()
        self.assertFalse(cases_for(self.local_b).filter(pk=app.pk).exists())
        OfficerAssignment.objects.create(officer=self.local_b,location=self.a)
        self.assertFalse(officer_active(self.local_b))
    @override_settings(NOTIFICATION_MODE='live')
    def test_admin_can_request_notification_test_and_delivery(self):
        self.client.force_login(self.manager.web_user)
        url=f'/notifikasi/uji/{self.local.pk}/'
        self.assertEqual(self.client.post(url).status_code,302)
        n=Notification.objects.get(event='test_staff',recipient=self.staff_user)
        with patch('service.notifications.bot_call',return_value={'message_id':99}) as transport: process_one()
        n.refresh_from_db(); self.assertEqual(n.status,'sent')
        self.assertEqual(transport.call_args.args[1]['chat_id'],self.staff_user.telegram_id)
        self.client.post(url)
        self.assertEqual(Notification.objects.filter(event='test_staff').count(),1)
        self.client.force_login(self.local_b.web_user)
        self.assertEqual(self.client.post(url).status_code,403)
    def test_notification_test_requires_link_and_consent(self):
        self.client.force_login(self.manager.web_user)
        self.staff_user.bot_notifications=False; self.staff_user.save()
        self.client.post(f'/notifikasi/uji/{self.local.pk}/')
        self.assertFalse(Notification.objects.filter(event='test_staff').exists())
        self.client.post(f'/notifikasi/uji/{self.local_b.pk}/')
        self.assertFalse(Notification.objects.filter(event='test_staff').exists())
    def test_unified_table_search_and_logo_on_login_home(self):
        app=self.ready(); self.client.force_login(self.manager.web_user)
        response=self.client.get('/permohonan/',{'q':'Kendala sintetis'})
        self.assertContains(response,app.number)
        self.assertContains(response,'Teks permasalahan')
        self.assertNotContains(response,'class="tabs"')
        self.assertEqual(response.content.count(b'<table '),1)
        config=site_config(); config.logo,config.logo_mime,_=clean_image(picture()); config.save()
        response=self.client.get('/permohonan/')
        self.assertContains(response,'class="home-logo"')
        self.client.logout(); response=self.client.get('/login/')
        self.assertContains(response,'class="login-logo"')
    @override_settings(NOTIFICATION_MODE='live')
    def test_reassignment_notifies_only_new_location(self):
        app=self.ready()
        tg_b=TelegramUser.objects.create(telegram_id=100005,bot_notifications=True)
        self.local_b.telegram=tg_b; self.local_b.save()
        app=assign_application(self.manager,app,self.b,'Pemindahan resmi',self.local_b)
        self.assertIsNone(app.location_selected_at)
        self.assertIn(self.b.name,public_progress(self.user,app))
        self.assertFalse(cases_for(self.local).filter(pk=app.pk).exists())
        with patch('service.notifications.bot_call',return_value={'message_id':88}) as send:
            while process_one(): pass
        destinations=[call.args[1]['chat_id'] for call in send.call_args_list]
        self.assertIn(tg_b.telegram_id,destinations)
        self.assertNotIn(self.staff_user.telegram_id,destinations)
    def test_legacy_telegram_only_profile_can_link_to_location_account(self):
        legacy=Officer.objects.create(telegram=self.other,role=Role.PELAKSANA,verified=True)
        OfficerAssignment.objects.create(officer=legacy,location=self.a)
        raw,_=create_activation(self.b,Role.PELAKSANA,officer=self.local_b)
        self.local_b.verified=False; self.local_b.save()
        self.assertFalse(activate(self.other,raw))
        legacy.refresh_from_db(); self.assertTrue(legacy.verified); self.assertEqual(legacy.telegram,self.other)
        self.local_b.verified=True; self.local_b.save()
        self.assertTrue(activate(self.other,raw))
        legacy.refresh_from_db(); self.local_b.refresh_from_db()
        self.assertFalse(legacy.verified); self.assertIsNone(legacy.telegram)
        self.assertFalse(legacy.assignments.filter(active=True).exists())
        self.assertEqual(self.local_b.telegram,self.other)
        self.assertTrue(officer_active(self.local_b))
        self.assertTrue(Audit.objects.filter(action='legacy_telegram.relinked').exists())

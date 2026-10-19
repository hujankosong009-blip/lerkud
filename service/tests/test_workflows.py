from datetime import timedelta
from unittest.mock import patch
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied,ValidationError
from django.db import IntegrityError,transaction
from django.test import TestCase,override_settings
from django.utils import timezone
from service.models import *
from service.services import *
from service.access import cases_for
from service.bot import handle_update,WELCOME,PUBLIC,directory
from service.notifications import process_one,enqueue_reminders
from service.telegram_api import DeliveryError,send_reply

# Entirely synthetic; never live Telegram or actual personal records.
DATA=dict(nik='0000000000000001',name='Pemohon Sintetis',phone='081234567890',address='Alamat Uji',city='Kota Uji',district='Kecamatan Uji',village='Kelurahan Uji',rt='001',rw='002')
class WorkflowTests(TestCase):
    def setUp(self):
        self.user=TelegramUser.objects.create(telegram_id=100001)
        self.other=TelegramUser.objects.create(telegram_id=100002)
        self.terms=Terms.objects.get(active=True)
        self.sequence=0
        self.a=Location.objects.create(name='Lokasi Sintetis A',category=Category.IPWL,active=True)
        self.b=Location.objects.create(name='Lokasi Sintetis B',category=Category.LRKM,active=True)
        self.local=self.officer('lokal',self.a,Role.LOCAL)
        self.coord=self.officer('koordinator',self.a,Role.COORD)
        self.manager=self.officer('pengelola',self.a,Role.SYSTEM)
    def officer(self,name,location,role):
        web=get_user_model().objects.create_user(username=name,password='synthetic-test-password')
        o=Officer.objects.create(web_user=web,verified=True)
        OfficerAssignment.objects.create(officer=o,location=location,role=role)
        return o
    def bot(self,action='',text='',user=None,update_id=None):
        self.sequence+=1
        return handle_update(update_id or self.sequence,(user or self.user).telegram_id,action=action,text=text)
    def register(self,user=None):
        user=user or self.user
        Consent.objects.get_or_create(user=user,terms=self.terms)
        RegistrationDraft.objects.create(user=user,data=DATA.copy(),step=9)
        return submit_registration(user)[0]
    def ready(self):
        app=self.register()
        submit_screening(self.user,app,'Permasalahan sintetis untuk pengujian.')
        app.refresh_from_db()
        assign_application(self.coord,app,self.a,'Penugasan uji',self.local)
        app.refresh_from_db()
        return app
    def test_start_two_options_and_draft_survives(self):
        self.bot(action='register'); self.bot(text=DATA['nik'])
        response=self.bot(text='/start')[0]
        self.assertEqual(response['text'],WELCOME)
        self.assertEqual([b[0] for b in response['buttons']],['Masyarakat','Admin'])
        self.assertEqual(RegistrationDraft.objects.get(user=self.user).data['nik'],DATA['nik'])
        response=self.bot(action='public')
        self.assertEqual(len(response[0]['buttons']),7)
        self.assertEqual(response[1]['buttons'][0][1],'resume')
    def test_private_chat_only(self):
        handle_update(900,123,text='/start',private=False)
        self.assertFalse(TelegramUser.objects.filter(telegram_id=123).exists())
    def test_registration_resume_edit_mask_and_exact_success(self):
        self.bot(action='register')
        for key,_ in FIELDS:
            response=self.bot(text=DATA[key])
        self.assertNotIn(DATA['nik'],response[0]['text'])
        self.assertIn('************0001',response[0]['text'])
        self.bot(action='save'); self.bot(text='/start'); self.bot(action='resume')
        self.bot(action='field:rt'); self.bot(text='007')
        self.assertEqual(RegistrationDraft.objects.get(user=self.user).data['rt'],'007')
        self.bot(action=f'agree:{self.terms.pk}')
        response=self.bot(action='submit')
        self.assertEqual(response[0]['text'],SUCCESS)
        self.assertTrue(response[1]['text'].startswith('Nomor permohonan: SM-'))
        self.assertEqual(Application.objects.get().status,Status.WAIT_SCREEN)
        self.assertEqual(Application.objects.get().identity['phone'],'+6281234567890')
        self.bot(action='submit')
        self.assertEqual(Application.objects.count(),1)
    def test_submit_idempotent_and_database_constraint(self):
        app=self.register()
        again,created=submit_registration(self.user)
        self.assertFalse(created); self.assertEqual(app.pk,again.pk)
        with self.assertRaises(IntegrityError),transaction.atomic():
            Application.objects.create(number='DUPLICATE-TEST',applicant=app.applicant,identity=DATA,consent=app.consent)
    def test_each_field_validation_and_manual_address(self):
        for key,val in [('nik','123'),('nik','١'*16),('phone','no'),('name',' '),('address','\n '),('city',''),('rt','A1'),('rw','-1')]:
            with self.subTest(key=key,val=val),self.assertRaises(ValidationError): validate_field(key,val)
        app=self.register()
        self.assertFalse(app.applicant.address_verified)
        self.assertEqual(app.identity['rt'],'001')
    def test_consent_required_and_terms_version_changes(self):
        RegistrationDraft.objects.create(user=self.user,data=DATA)
        with self.assertRaises(ValidationError): submit_registration(self.user)
        Consent.objects.create(user=self.user,terms=self.terms)
        self.terms.active=False; self.terms.save()
        Terms.objects.create(version='2',body='Ketentuan sintetis baru',active=True)
        with self.assertRaises(ValidationError): submit_registration(self.user)
        self.assertEqual(Application.objects.count(),0)
    def test_cancel_draft_preserves_valid_application(self):
        app=self.register()
        self.bot(action='confirm_cancel')
        self.assertTrue(Application.objects.filter(pk=app.pk).exists())
        self.assertEqual(RegistrationDraft.objects.get(user=self.user).form_status,'REGISTRASI_TERKIRIM')
    def test_duplicate_nik_never_exposes_other_profile(self):
        self.register()
        second=self.register(self.other)
        self.assertTrue(second.duplicate_review)
        self.assertEqual(cases_for(self.manager).count(),0)
        self.assertEqual(Application.objects.filter(applicant__user=self.other).count(),1)
    def test_screening_prerequisite_and_version_history(self):
        response=self.bot(action='screen')[0]
        self.assertEqual(response['buttons'][0][1],'register')
        app=self.ready()
        self.assertEqual(app.status,Status.WAIT_VERIFY)
        update_progress(self.local,app,Status.REVIEW,'Ditinjau')
        app=update_progress(self.local,app,Status.NEED_INFO,'Kelengkapan','Mohon melengkapi uraian.')
        submit_screening(self.user,app,'Kelengkapan sintetis.')
        app.refresh_from_db()
        self.assertEqual(app.status,Status.WAIT_VERIFY)
        self.assertEqual(list(app.screenings.values_list('version',flat=True)),[1,2])
    def test_bot_screening_review_and_repeat_submission(self):
        app=self.register()
        self.bot(action='screen'); self.bot(text='Uraian uji')
        response=self.bot(action='screen_send')
        self.assertEqual(response[0]['text'],SCREEN_THANKS)
        self.bot(action='screen_send')
        self.assertEqual(app.screenings.count(),1)
    def test_empty_directory_seven_categories_only_active(self):
        Location.objects.all().update(active=False)
        choices=self.bot(action='directory')[0]['buttons']
        self.assertEqual(len(choices),7)
        for key,_ in Category.choices:
            if key==Category.COORD: continue
            self.assertEqual(directory(key)['text'],f'Data titik akses kategori {key} sedang disiapkan. Silakan periksa kembali secara berkala.')
        self.a.active=True; self.a.save()
        self.assertIn(self.a.name,directory(Category.IPWL)['text'])
        self.assertNotIn(self.b.name,directory(Category.IPWL)['text'])
    def test_self_assessment_inactive(self):
        self.assertEqual(self.bot(action='self')[0]['text'],SELF_MESSAGE)
        self.assertEqual(AssessmentResponse.objects.count(),0)
    def test_invalid_expired_and_rate_limited_activation(self):
        self.assertFalse(activate(self.user,'invalid'))
        raw,code=create_activation(self.a,Role.LOCAL)
        code.expires_at=timezone.now()-timedelta(seconds=1); code.save()
        self.assertFalse(activate(self.user,raw))
        for _ in range(4): activate(self.user,'bad')
        raw,_=create_activation(self.a,Role.LOCAL)
        self.assertFalse(activate(self.user,raw))
        self.assertEqual(ActivationAttempt.objects.filter(user=self.user).count(),5)
        self.assertFalse(Officer.objects.filter(telegram=self.user).exists())
    def test_activation_single_use_hash_and_revoke(self):
        raw,code=create_activation(self.a,Role.LOCAL)
        self.assertNotEqual(raw,code.digest)
        self.assertTrue(activate(self.user,raw))
        self.assertFalse(activate(self.other,raw))
        officer=Officer.objects.get(telegram=self.user)
        self.assertEqual(assignments(officer).count(),1)
        officer.assignments.update(active=False)
        self.assertEqual(cases_for(officer).count(),0)
        self.assertIn('Silakan masukkan kode',self.bot(action='admin')[0]['text'])
    def test_location_scope_and_ownership(self):
        app=self.ready()
        self.assertEqual(cases_for(self.local).count(),1)
        with self.assertRaises(PermissionDenied): public_progress(self.other,app)
        with self.assertRaises(PermissionDenied): submit_screening(self.other,app,'Tidak boleh')
        assign_application(self.coord,app,self.b,'Dipindahkan')
        app.refresh_from_db()
        self.assertEqual(cases_for(self.local).count(),0)
        with self.assertRaises(PermissionDenied): update_progress(self.local,app,Status.REVIEW,'Ditolak')
        self.assertEqual(cases_for(self.coord).count(),1)
    def test_progress_audit_and_internal_hidden(self):
        app=self.ready()
        app=update_progress(self.local,app,Status.REVIEW,'Alasan rahasia','Mohon menunggu.','Catatan sangat rahasia')
        output=public_progress(self.user,app)
        self.assertIn('Mohon menunggu.',output)
        self.assertNotIn('Alasan rahasia',output)
        self.assertNotIn('Catatan sangat rahasia',output)
        self.assertTrue(Audit.objects.filter(action='progress.updated',object_id=str(app.pk)).exists())
        self.assertEqual(app.notes.count(),1)
    def test_illegal_transition_and_reopen_rules(self):
        app=self.ready()
        with self.assertRaises(ValidationError): update_progress(self.local,app,Status.DONE,'Lompatan')
        app=update_progress(self.local,app,Status.REVIEW,'Mulai')
        with self.assertRaises(ValidationError): update_progress(self.local,app,Status.CANCELLED,' ')
        app=update_progress(self.local,app,Status.CANCELLED,'Alasan sah')
        with self.assertRaises(PermissionDenied): update_progress(self.local,app,Status.REVIEW,'Buka kembali',reopen=True)
        app=update_progress(self.coord,app,Status.REVIEW,'Buka kembali beralasan',reopen=True)
        self.assertEqual(app.status,Status.REVIEW)
    def test_stale_update_rejected(self):
        app=self.ready()
        update_progress(self.local,app,Status.REVIEW,'Tinjau')
        with self.assertRaises(ValidationError): update_progress(self.local,app,Status.CANCELLED,'Lama',expected_status=Status.WAIT_VERIFY)
    def test_routing_exact_manual_reference(self):
        RoutingRule.objects.create(city=DATA['city'],district=DATA['district'],village=DATA['village'],location=self.b)
        app=self.register(); submit_screening(self.user,app,'Uraian')
        app.refresh_from_db()
        self.assertEqual(app.location,self.b)
        self.assertEqual(app.assignment_history.count(),1)
    def test_assignment_permissions_and_responsible_validation(self):
        app=self.register()
        with self.assertRaises(PermissionDenied): assign_application(self.local,app,self.a,'Dilarang')
        with self.assertRaises(ValidationError): assign_application(self.coord,app,self.b,'Petugas salah',self.local)
    def test_bot_duplicate_update_no_side_effect_and_callback_size(self):
        self.bot(action='register',update_id=500)
        self.bot(text=DATA['nik'],update_id=501)
        self.bot(text=DATA['nik'],update_id=501)
        self.assertEqual(RegistrationDraft.objects.get(user=self.user).step,1)
        app=self.ready_without_draft()
        self.local.telegram=self.user; self.local.save()
        responses=self.bot(action=f'admin_case:{app.pk}')
        for r in responses:
            for _,action in r['buttons']: self.assertLessEqual(len(action.encode()),64)
    def ready_without_draft(self):
        RegistrationDraft.objects.filter(user=self.user).delete()
        return self.ready()
    @override_settings(NOTIFICATION_MODE='simulation')
    def test_simulation_never_sent(self):
        app=self.register()
        with patch('service.notifications.bot_call') as send:
            self.assertTrue(process_one())
            send.assert_not_called()
        n=Notification.objects.get(application=app,recipient=self.user)
        self.assertEqual(n.status,'simulated'); self.assertIsNone(n.sent_at)
    @override_settings(NOTIFICATION_MODE='live')
    def test_notification_failure_does_not_remove_application(self):
        self.user.bot_notifications=True; self.user.save()
        app=self.register()
        with patch('service.notifications.bot_call',side_effect=DeliveryError('telegram_connection_failed')): process_one()
        app.refresh_from_db()
        n=app.notifications.get()
        self.assertEqual(n.status,'failed'); self.assertEqual(n.attempts,1); self.assertIsNone(n.sent_at)
        self.assertEqual(app.status,Status.WAIT_SCREEN)
    @override_settings(NOTIFICATION_MODE='live')
    def test_bot_requires_consent_and_notification_text_is_safe(self):
        app=self.register()
        with patch('service.notifications.bot_call') as send:
            process_one(); send.assert_not_called()
        n=app.notifications.get(); self.assertEqual(n.error,'recipient_not_consented')
        self.user.bot_notifications=True; self.user.save()
        n.next_attempt_at=timezone.now(); n.save()
        with patch('service.notifications.bot_call',return_value={'message_id':77}) as send:
            process_one()
            payload=send.call_args.args[1]
            self.assertNotIn(DATA['nik'],str(payload)); self.assertNotIn(DATA['name'],str(payload))
        n.refresh_from_db(); self.assertEqual(n.status,'sent'); self.assertEqual(n.message_id,'77')
    def test_mtproto_pairing_checks_sender_expiry_once_and_consent(self):
        raw=create_recipient_link(self.user)
        self.assertFalse(verify_recipient_link(raw,self.other.telegram_id))
        self.assertTrue(verify_recipient_link(raw,self.user.telegram_id))
        self.assertFalse(verify_recipient_link(raw,self.user.telegram_id))
        self.assertTrue(NotificationRecipient.objects.get(user=self.user).active)
        self.bot(action='notify_off')
        self.assertFalse(NotificationRecipient.objects.get(user=self.user).active)
    @override_settings(NOTIFICATION_MODE='live',NOTIFICATION_CHANNEL='mtproto')
    def test_mtproto_unlinked_never_attempted(self):
        self.register()
        with patch('service.notifications.mtproto_send') as send:
            process_one(); send.assert_not_called()
        self.assertEqual(Notification.objects.get().error,'recipient_not_verified_or_consented')
    def test_reminders_idempotent(self):
        app=self.register(); Application.objects.filter(pk=app.pk).update(updated_at=timezone.now()-timedelta(days=10))
        enqueue_reminders(); enqueue_reminders()
        self.assertEqual(Notification.objects.filter(event='reminder').count(),1)
    def test_web_login_scope_csrf_and_timezone(self):
        app=self.ready()
        self.assertEqual(self.client.get('/').status_code,302)
        self.client.force_login(self.local.web_user)
        for url in ['/', '/permohonan/', f'/permohonan/{app.pk}/','/notifikasi/']:
            response=self.client.get(url)
            self.assertEqual(response.status_code,200,url)
            self.assertIn('no-store',response['Cache-Control'])
        response=self.client.get(f'/permohonan/{app.pk}/')
        self.assertContains(response,'WIB')
        self.assertEqual(settings.TIME_ZONE,'Asia/Jakarta')
        self.assertTrue(timezone.is_aware(app.submitted_at))
        self.assertEqual(self.client.get('/pengelolaan/').status_code,403)
        assign_application(self.coord,app,self.b,'Pindah')
        self.assertEqual(self.client.get(f'/permohonan/{app.pk}/').status_code,404)
        self.assertNotContains(self.client.get('/permohonan/'),app.number)
        self.client.force_login(self.manager.web_user)
        self.assertEqual(self.client.get('/pengelolaan/').status_code,200)
        self.assertNotContains(self.client.get('/'),app.number)
        from django.test import Client
        secure=Client(enforce_csrf_checks=True); secure.force_login(self.local.web_user)
        self.assertEqual(secure.post(f'/permohonan/{app.pk}/',{'status':Status.DONE}).status_code,403)
    def test_dashboard_assignment_and_progress_post(self):
        app=self.register(); submit_screening(self.user,app,'Uraian'); app.refresh_from_db()
        self.client.force_login(self.coord.web_user)
        response=self.client.post(f'/permohonan/{app.pk}/',{'action':'assign','assignment-location':self.a.pk,'assignment-responsible':self.local.pk,'assignment-reason':'Penugasan'})
        self.assertEqual(response.status_code,302)
        self.client.force_login(self.local.web_user)
        response=self.client.post(f'/permohonan/{app.pk}/',{'status':Status.REVIEW,'expected_status':Status.WAIT_VERIFY,'reason':'Tinjau','public_text':'Sedang ditinjau','internal_text':'Internal'})
        self.assertEqual(response.status_code,302)
        app.refresh_from_db(); self.assertEqual(app.status,Status.REVIEW)
    def test_login_throttle(self):
        for _ in range(10): self.client.post('/login/',{'username':'invalid','password':'bad'})
        self.assertEqual(self.client.post('/login/',{}).status_code,429)
    def test_bot_invalid_callbacks_fail_safely(self):
        for action in ['my:bad','admin_status:bad:bad','agree:bad','screen_send','field:bad']:
            response=self.bot(action=action)
            self.assertTrue(response)
    def test_screening_draft_survives_start_and_menu_changes(self):
        app=self.register()
        self.bot(action='screen'); self.bot(text='Draft uraian sintetis.')
        self.bot(text='/start'); self.bot(action='public'); self.bot(action='directory')
        response=self.bot(action='screen')
        self.assertIn('Draft uraian sintetis.',response[0]['text'])
        self.bot(action='screen_send')
        self.assertEqual(app.screenings.get().text,'Draft uraian sintetis.')
        self.assertFalse(ScreeningDraft.objects.filter(application=app).exists())
    @override_settings(NOTIFICATION_MODE='live')
    def test_notification_rechecks_revoked_assignment(self):
        app=self.ready()
        admin_user=TelegramUser.objects.create(telegram_id=100003,bot_notifications=True)
        self.local.telegram=admin_user; self.local.save()
        n=Notification.objects.create(application=app,recipient=admin_user,event='progress',channel='bot',dedupe_key='revocation-test')
        self.local.assignments.update(active=False)
        with patch('service.notifications.bot_call') as send:
            while process_one(): pass
            send.assert_not_called()
        n.refresh_from_db(); self.assertEqual(n.error,'recipient_access_revoked')
    def test_forged_bot_update_cannot_switch_case_scope(self):
        app=self.ready()
        self.assertNotIn(app.number,self.bot(action=f'my:{app.pk}',user=self.other)[0]['text'])
        self.assertNotIn(app.number,self.bot(action=f'admin_case:{app.pk}',user=self.other)[0]['text'])
    def test_terms_cannot_change_published_content(self):
        from service.admin import TermsForm
        f=TermsForm(data={'version':self.terms.version,'body':'Changed','active':True,'published_at':self.terms.published_at},instance=self.terms)
        self.assertFalse(f.is_valid())
    @override_settings(NOTIFICATION_MODE='live')
    def test_rate_limit_retry_respects_telegram_wait(self):
        self.user.bot_notifications=True; self.user.save()
        app=self.register()
        before=timezone.now()
        with patch('service.notifications.bot_call',side_effect=DeliveryError('telegram_rate_limit',3600)):
            process_one()
        n=app.notifications.get()
        self.assertGreaterEqual(n.next_attempt_at,before+timedelta(seconds=3600))
        self.assertEqual(n.status,'failed')
        self.assertFalse(process_one())
    @override_settings(NOTIFICATION_MODE='live',NOTIFICATION_CHANNEL='mtproto')
    def test_verified_mtproto_adapter_success(self):
        app=self.register()
        raw=create_recipient_link(self.user)
        verify_recipient_link(raw,self.user.telegram_id)
        async def fake_send(sender_id):
            self.assertEqual(sender_id,self.user.telegram_id)
            return 'fake-message-1'
        with patch('service.notifications.mtproto_send',side_effect=fake_send): process_one()
        n=app.notifications.get()
        self.assertEqual(n.status,'sent'); self.assertEqual(n.message_id,'fake-message-1')
    def test_expired_link_rejected(self):
        raw=create_recipient_link(self.user)
        RecipientLink.objects.filter(user=self.user).update(expires_at=timezone.now()-timedelta(seconds=1))
        self.assertFalse(verify_recipient_link(raw,self.user.telegram_id))
    def test_direct_filters_do_not_expand_location_scope(self):
        app=self.ready()
        other_local=self.officer('lokal-b',self.b,Role.LOCAL)
        self.client.force_login(other_local.web_user)
        response=self.client.get('/permohonan/',{'location':self.a.pk,'status':app.status,'from':'2026-99-99'})
        self.assertEqual(response.status_code,200)
        self.assertNotContains(response,app.number)
    def test_public_timestamp_converts_utc_to_jakarta(self):
        from datetime import datetime,timezone as dt_timezone
        app=self.register()
        timestamp=datetime(2026,1,2,23,30,tzinfo=dt_timezone.utc)
        Application.objects.filter(pk=app.pk).update(updated_at=timestamp)
        app.refresh_from_db()
        self.assertIn('03/01/2026 06:30 WIB',public_progress(self.user,app))

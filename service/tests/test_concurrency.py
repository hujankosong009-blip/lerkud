from concurrent.futures import ThreadPoolExecutor
from unittest import skipUnless
from django.db import connection,close_old_connections,connections
from django.test import TransactionTestCase
from service.models import TelegramUser,Terms,Consent,RegistrationDraft,Application,Location,Role,OfficerAssignment
from service.services import submit_registration,create_activation,activate
from .test_workflows import DATA

@skipUnless(connection.vendor=='postgresql','Row-lock concurrency check requires PostgreSQL')
class PostgreSQLConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.user=TelegramUser.objects.create(telegram_id=200001)
        self.other=TelegramUser.objects.create(telegram_id=200002)
        terms=Terms.objects.create(version='concurrency',body='Synthetic terms',active=True) if not Terms.objects.filter(active=True).exists() else Terms.objects.get(active=True)
        Consent.objects.create(user=self.user,terms=terms)
        RegistrationDraft.objects.create(user=self.user,data=DATA,step=9)
    def test_simultaneous_registration_submits(self):
        def submit(_):
            close_old_connections()
            try: return submit_registration(TelegramUser.objects.get(pk=self.user.pk))[0].pk
            finally: connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool: ids=list(pool.map(submit,range(2)))
        self.assertEqual(ids[0],ids[1]); self.assertEqual(Application.objects.count(),1)
    def test_simultaneous_activation_single_winner(self):
        location=Location.objects.create(name='Synthetic Concurrency Location',category='IPWL',active=True)
        raw,_=create_activation(location,Role.PELAKSANA)
        def run(pk):
            close_old_connections()
            try: return activate(TelegramUser.objects.get(pk=pk),raw)
            finally: connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(run,[self.user.pk,self.other.pk]))
        self.assertEqual(sum(results),1); self.assertEqual(OfficerAssignment.objects.count(),1)
    def test_concurrent_demotion_preserves_last_superadmin(self):
        from django.contrib.auth import get_user_model
        from django.core.exceptions import ValidationError
        from service.models import Officer
        from service.services import save_account
        point=Location.objects.create(name='Concurrent Test Point',category='IPWL',active=True)
        actors=[]
        for name in ['parallel-manager-a','parallel-manager-b']:
            web=get_user_model().objects.create_user(username=name,is_staff=True)
            actors.append(Officer.objects.create(web_user=web,verified=True,role=Role.SUPERADMIN))
        def demote(pk):
            close_old_connections()
            try:
                officer=Officer.objects.select_related('web_user').get(pk=pk)
                data={'username':officer.web_user.username,'first_name':'','last_name':'','email':'','role':Role.PELAKSANA,'active':True,'location':point}
                try:
                    save_account(officer,data,officer=officer)
                    return True
                except ValidationError:
                    return False
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(demote,[o.pk for o in actors]))
        self.assertEqual(sum(results),1)
        self.assertEqual(Officer.objects.filter(role=Role.SUPERADMIN,verified=True).count(),1)
    def test_concurrent_location_confirmation_has_one_destination(self):
        from service.models import Application, Status
        from service.services import submit_screening, begin_assessment, submit_evidence, send_to_location, site_config
        from .test_workflows import picture
        from django.core.exceptions import ValidationError
        app,_=submit_registration(self.user)
        submit_screening(self.user,app,'Kendala uji konkurensi')
        config=site_config(); config.self_assessment_url='https://example.org/test'; config.save()
        begin_assessment(self.user,app); submit_evidence(self.user,app,picture())
        points=[Location.objects.create(name=f'Concurrent Point {n}',category='IPWL',active=True) for n in range(2)]
        def send(pk):
            close_old_connections()
            try:
                try:
                    _,created=send_to_location(TelegramUser.objects.get(pk=self.user.pk),Application.objects.get(pk=app.pk),Location.objects.get(pk=pk))
                    return created
                except ValidationError:
                    return False
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(send,[point.pk for point in points]))
        self.assertEqual(sum(results),1)
        app.refresh_from_db(); self.assertEqual(app.status,Status.WAIT_VERIFY)
        self.assertEqual(app.assignment_history.count(),1)
        self.assertEqual(app.notifications.filter(event='dossier_ready').count(),1)

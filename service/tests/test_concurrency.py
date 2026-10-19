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
        raw,_=create_activation(location,Role.LOCAL)
        def run(pk):
            close_old_connections()
            try: return activate(TelegramUser.objects.get(pk=pk),raw)
            finally: connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(run,[self.user.pk,self.other.pk]))
        self.assertEqual(sum(results),1); self.assertEqual(OfficerAssignment.objects.count(),1)

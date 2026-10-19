from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand,CommandError
from service.models import Officer,OfficerAssignment,Location,Category,Role
from service.services import audit
class Command(BaseCommand):
    help='Tautkan akun superuser yang sudah dibuat ke peran pengelola sistem (tanpa kewenangan kasus).'
    def add_arguments(self,parser): parser.add_argument('username')
    def handle(self,*args,**options):
        user=get_user_model().objects.filter(username=options['username'],is_superuser=True,is_staff=True,is_active=True).first()
        if not user: raise CommandError('Buat superuser aktif terlebih dahulu dengan createsuperuser.')
        location,_=Location.objects.get_or_create(name='BNN Kota Surabaya',category=Category.COORD,defaults={'active':True})
        officer,_=Officer.objects.get_or_create(web_user=user)
        officer.verified=True; officer.save()
        OfficerAssignment.objects.get_or_create(officer=officer,location=location,role=Role.SYSTEM,defaults={'active':True})
        audit(f'web:{user.pk}','manager.bootstrapped',officer.pk)
        self.stdout.write('Peran pengelola sistem siap. Peran koordinator harus ditetapkan secara terpisah bila berwenang.')

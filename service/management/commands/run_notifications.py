import time
from django.core.management.base import BaseCommand
from django.db import close_old_connections
from service.notifications import process_one, enqueue_reminders
class Command(BaseCommand):
    help='Proses antrean dan pengingat; default simulasi, tanpa pesan nyata.'
    def add_arguments(self,parser):
        parser.add_argument('--once',action='store_true')
        parser.add_argument('--reminders',action='store_true')
    def handle(self,*args,**options):
        last_reminder=float('-inf')
        count=0
        while True:
            close_old_connections()
            if options['reminders'] and time.monotonic()-last_reminder>3600:
                enqueue_reminders(); last_reminder=time.monotonic()
            processed=process_one()
            if processed: count+=1
            elif options['once']: break
            else: time.sleep(2)
        self.stdout.write(f'{count} notifikasi diproses. Periksa status pada dashboard; simulasi bukan pengiriman nyata.')

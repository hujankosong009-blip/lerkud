import time
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections
from service.models import RuntimeCursor
from service.bot import handle_update
from service.telegram_api import bot_call,send_reply,DeliveryError
class Command(BaseCommand):
    help='Jalankan satu konsumen long-polling bot. Tidak menghapus webhook secara otomatis.'
    def handle(self,*args,**options):
        if not settings.TELEGRAM_BOT_TOKEN: raise CommandError('TELEGRAM_BOT_TOKEN belum dikonfigurasi.')
        cursor,_=RuntimeCursor.objects.get_or_create(name='bot_offset')
        self.stdout.write('Bot aktif. Isi update dan kredensial tidak dicatat.')
        while True:
            close_old_connections()
            try:
                updates=bot_call('getUpdates',{'offset':cursor.value,'timeout':25,'allowed_updates':['message','callback_query']})
                for update in updates:
                    callback=update.get('callback_query')
                    message=callback.get('message',{}) if callback else update.get('message',{})
                    sender=callback.get('from',{}) if callback else message.get('from',{})
                    chat=message.get('chat',{})
                    if chat and sender and not sender.get('is_bot'):
                        responses=handle_update(update['update_id'],sender['id'],text=message.get('text','') if not callback else '',action=callback.get('data','') if callback else '',private=chat.get('type')=='private')
                        if callback: bot_call('answerCallbackQuery',{'callback_query_id':callback['id']})
                        for response in responses: send_reply(chat['id'],response)
                    cursor.value=update['update_id']+1
                    cursor.save(update_fields=['value'])
            except DeliveryError as exc:
                self.stderr.write(f'Bot: {exc.reason}; akan mencoba kembali.')
                time.sleep(max(5,int(exc.retry_after or 0)))

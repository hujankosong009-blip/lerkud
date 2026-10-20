import time
import threading
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections, connections, OperationalError
from service.models import RuntimeCursor, TelegramUser
from service.bot import handle_update
from service.telegram_api import bot_call, send_reply, DeliveryError, download_photo, token
from service.notifications import process_one

class Command(BaseCommand):
    help = 'Bot Telegram dan pekerja notifikasi otomatis dalam satu perintah.'
    def add_arguments(self, parser):
        parser.add_argument('--no-notifications', action='store_true', help='Gunakan worker notifikasi terpisah.')
    def handle(self, *args, **options):
        try:
            token()
        except DeliveryError:
            raise CommandError('Token bot belum valid. Periksa .env tanpa membagikan isinya.') from None
        cursor, _ = RuntimeCursor.objects.get_or_create(name='bot_offset')
        stop = threading.Event()
        def pump():
            while not stop.is_set():
                try:
                    close_old_connections()
                    if not process_one():
                        stop.wait(1)
                except OperationalError:
                    stop.wait(2)
                except Exception:
                    self.stderr.write('Worker notifikasi mengalami gangguan; mencoba kembali tanpa mencatat data sensitif.')
                    stop.wait(5)
            connections.close_all()
        worker = None
        if not options['no_notifications']:
            worker = threading.Thread(target=pump, daemon=True)
            worker.start()
        self.stdout.write(f'Bot aktif. Notifikasi otomatis: {settings.NOTIFICATION_MODE}. Isi update dan kredensial tidak dicatat.')
        try:
            while True:
                close_old_connections()
                try:
                    updates = bot_call('getUpdates',{'offset':cursor.value,'timeout':20,'allowed_updates':['message','callback_query']})
                    for update in updates:
                        callback = update.get('callback_query')
                        message = callback.get('message',{}) if callback else update.get('message',{})
                        sender = callback.get('from',{}) if callback else message.get('from',{})
                        chat = message.get('chat',{})
                        photo = None
                        if chat and sender and not sender.get('is_bot'):
                            if message.get('photo') and chat.get('type') == 'private':
                                user = TelegramUser.objects.filter(telegram_id=sender['id']).first()
                                if user and user.state.get('mode') == 'evidence':
                                    try:
                                        photo = download_photo(message['photo'][-1]['file_id'])
                                    except DeliveryError:
                                        send_reply(chat['id'],{'text':'Bukti belum tersimpan. Kirim ulang gambar JPEG/PNG maksimal 5 MB.','buttons':[]})
                                        cursor.value = update['update_id'] + 1
                                        cursor.save(update_fields=['value'])
                                        continue
                            responses = handle_update(update['update_id'],sender['id'],text=message.get('text','') if not callback else '',action=callback.get('data','') if callback else '',private=chat.get('type')=='private',photo=photo)
                            if callback:
                                try:
                                    bot_call('answerCallbackQuery',{'callback_query_id':callback['id']})
                                except DeliveryError:
                                    pass  # Expired UI acknowledgment must not block a committed form.
                            for response in responses:
                                try:
                                    send_reply(chat['id'],response)
                                except DeliveryError as exc:
                                    if exc.reason in ('recipient_access_revoked','telegram_http_403'):
                                        self.stderr.write('Respons dilewati: akses berubah atau penerima tidak dapat dihubungi.')
                                        break
                                    raise
                        cursor.value = update['update_id'] + 1
                        cursor.save(update_fields=['value'])
                except DeliveryError as exc:
                    self.stderr.write(f'Bot: {exc.reason}; akan mencoba kembali.')
                    stop.wait(max(5,int(exc.retry_after or 0)))
                except OperationalError:
                    self.stderr.write('Database sibuk; mencoba kembali.')
                    stop.wait(2)
        except KeyboardInterrupt:
            self.stdout.write('Bot dihentikan.')
        finally:
            stop.set()
            if worker:
                worker.join(timeout=45)

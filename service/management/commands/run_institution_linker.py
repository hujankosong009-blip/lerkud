import asyncio
from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.management.base import BaseCommand,CommandError
from service.services import verify_recipient_link
class Command(BaseCommand):
    help='Verifikasi kode pengaitan melalui akun institusi MTProto; membutuhkan sesi yang telah disiapkan secara aman.'
    def handle(self,*args,**options):
        if settings.NOTIFICATION_MODE!='live' or not all([settings.TELEGRAM_API_ID,settings.TELEGRAM_API_HASH,settings.TELEGRAM_SESSION]):
            raise CommandError('Mode live dan kredensial/sesi institusi diperlukan untuk koneksi nyata.')
        asyncio.run(self.run())
    async def run(self):
        from telethon import TelegramClient,events
        from telethon.sessions import StringSession
        client=TelegramClient(StringSession(settings.TELEGRAM_SESSION),int(settings.TELEGRAM_API_ID),settings.TELEGRAM_API_HASH,flood_sleep_threshold=0)
        @client.on(events.NewMessage(incoming=True,pattern=r'^/kaitkan ([A-Za-z0-9_-]+)$'))
        async def link(event):
            if not event.is_private: return
            sender=await event.get_sender()
            if not sender or sender.bot: return
            valid=await sync_to_async(verify_recipient_link)(event.pattern_match.group(1),sender.id)
            await event.reply('Pengaitan dan persetujuan notifikasi dicatat.' if valid else 'Kode tidak dapat digunakan. Buat kode baru melalui bot layanan.')
        try:
            await client.connect()
            if not await client.is_user_authorized(): raise CommandError('Sesi institusi belum terotorisasi; siapkan secara aman di luar aplikasi.')
            self.stdout.write('Pengaitan akun institusi aktif; isi pesan tidak dicatat.')
            await client.run_until_disconnected()
        finally: await client.disconnect()

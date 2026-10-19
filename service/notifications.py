import asyncio
from datetime import timedelta
from django.conf import settings
from django.db import transaction, connection
from django.db.models import Q
from django.utils import timezone
from .models import Notification, NotificationRecipient, Application, Status, CLOSED
from .services import queue_event
from .access import cases_for
from .telegram_api import bot_call, DeliveryError

SAFE_MESSAGE = 'Ada pembaruan permohonan SALAM MANIS. Buka bot layanan dan pilih Progres Permohonan Saya atau Menu Admin sesuai akses Anda.'

async def mtproto_send(sender_id):
    if not all([settings.TELEGRAM_API_ID,settings.TELEGRAM_API_HASH,settings.TELEGRAM_SESSION]): raise DeliveryError('mtproto_not_configured')
    from telethon import TelegramClient, errors
    from telethon.sessions import StringSession
    client=TelegramClient(StringSession(settings.TELEGRAM_SESSION),int(settings.TELEGRAM_API_ID),settings.TELEGRAM_API_HASH,flood_sleep_threshold=0)
    try:
        await client.connect()
        if not await client.is_user_authorized(): raise DeliveryError('mtproto_session_unauthorized')
        # Require an existing dialog to obtain the real entity/access hash.
        entity=None
        async for dialog in client.iter_dialogs():
            if dialog.id==sender_id:
                entity=dialog.entity
                break
        if entity is None: raise DeliveryError('mtproto_recipient_not_connected')
        msg=await client.send_message(entity,SAFE_MESSAGE)
        return str(msg.id)
    except errors.FloodWaitError as exc: raise DeliveryError('telegram_rate_limit',exc.seconds) from None
    except DeliveryError: raise
    except Exception: raise DeliveryError('mtproto_delivery_failed') from None
    finally: await client.disconnect()

def deliver(notification):
    if settings.NOTIFICATION_MODE=='simulation': return 'simulated',''
    if settings.NOTIFICATION_MODE!='live': raise DeliveryError('invalid_notification_mode')
    # Authorization is rechecked at delivery, including revocations and reassignment.
    if notification.application_id:
        app=notification.application
        if app.applicant.user_id!=notification.recipient_id:
            officer=getattr(notification.recipient,'officer',None)
            if not officer or not cases_for(officer).filter(pk=app.pk).exists(): raise DeliveryError('recipient_access_revoked')
    if notification.channel=='bot':
        if not notification.recipient.bot_notifications: raise DeliveryError('recipient_not_consented')
        result=bot_call('sendMessage',{'chat_id':notification.recipient.telegram_id,'text':SAFE_MESSAGE})
        return 'sent',str(result['message_id'])
    if notification.channel=='mtproto':
        recipient=NotificationRecipient.objects.filter(user=notification.recipient,active=True).first()
        if not recipient: raise DeliveryError('recipient_not_verified_or_consented')
        return 'sent',asyncio.run(mtproto_send(recipient.mtproto_id))
    raise DeliveryError('unsupported_channel')

def process_one():
    now=timezone.now()
    with transaction.atomic():
        # Recover a crashed worker lease. Telegram delivery is at least once.
        Notification.objects.filter(status='processing',locked_at__lt=now-timedelta(minutes=5)).update(status='failed',error='worker_lease_expired',locked_at=None)
        qs=Notification.objects.filter(status__in=['queued','failed'],attempts__lt=5,next_attempt_at__lte=now).order_by('queued_at')
        n=qs.select_for_update(skip_locked=connection.features.has_select_for_update_skip_locked).first()
        if not n: return False
        n.status='processing'; n.locked_at=now; n.attempts+=1
        n.save(update_fields=['status','locked_at','attempts'])
    try:
        status,message_id=deliver(n)
    except Exception as exc:
        # Never persist external exception strings (can contain credentials/text).
        error=exc.reason if isinstance(exc,DeliveryError) else 'delivery_failed'
        delay=max(2**n.attempts*30,int(exc.retry_after or 0)) if isinstance(exc,DeliveryError) else 300
        Notification.objects.filter(pk=n.pk,status='processing',locked_at=now).update(status='failed',error=error,next_attempt_at=timezone.now()+timedelta(seconds=delay),locked_at=None)
    else:
        Notification.objects.filter(pk=n.pk,status='processing',locked_at=now).update(status=status,message_id=message_id,sent_at=timezone.now() if status=='sent' else None,error='',locked_at=None)
    return True

def enqueue_reminders():
    date=timezone.localdate().isoformat()
    stale=Application.objects.exclude(status__in=CLOSED).filter(updated_at__lt=timezone.now()-timedelta(days=settings.STALE_DAYS))
    for app in stale.iterator(): queue_event(app,'reminder',f'reminder:{date}:{app.pk}')

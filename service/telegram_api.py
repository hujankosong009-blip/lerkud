"""Bot transport: all network errors are sanitized, including malformed-token URLs."""
import json
import re
import http.client
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from django.conf import settings
from .uploads import MAX_UPLOAD

class DeliveryError(Exception):
    def __init__(self, reason='transport_failed', retry_after=None):
        self.reason = reason
        self.retry_after = retry_after
        super().__init__(reason)


def token():
    value = settings.TELEGRAM_BOT_TOKEN.strip()
    if not re.fullmatch(r'[0-9]+:[A-Za-z0-9_-]{20,}', value):
        raise DeliveryError('bot_token_invalid_or_missing')
    return value


def bot_call(method, payload):
    credential = token()
    try:
        req = Request(f'https://api.telegram.org/bot{credential}/{method}',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
        with urlopen(req, timeout=40) as response:
            data = json.load(response)
    except HTTPError as exc:
        retry = None
        if exc.code == 429:
            try:
                retry = int(json.loads(exc.read()).get('parameters',{}).get('retry_after',60))
            except (ValueError, TypeError):
                retry = 60
        raise DeliveryError('telegram_rate_limit' if exc.code == 429 else f'telegram_http_{exc.code}', retry) from None
    except (URLError, TimeoutError, OSError, ValueError, http.client.HTTPException):
        raise DeliveryError('telegram_connection_failed') from None
    if not isinstance(data, dict) or not data.get('ok'):
        raise DeliveryError('telegram_rejected')
    return data['result']


def download_photo(file_id):
    info = bot_call('getFile', {'file_id':file_id})
    path = info.get('file_path', '')
    if info.get('file_size', 0) > MAX_UPLOAD or not re.fullmatch(r'[A-Za-z0-9_/-]+\.(jpg|jpeg|png|webp)',path,re.I) or '..' in path:
        raise DeliveryError('photo_invalid_or_too_large')
    try:
        with urlopen(f'https://api.telegram.org/file/bot{token()}/{path}',timeout=30) as response:
            data = response.read(MAX_UPLOAD + 1)
    except (URLError, TimeoutError, OSError, ValueError, http.client.HTTPException):
        raise DeliveryError('photo_download_failed') from None
    if len(data) > MAX_UPLOAD:
        raise DeliveryError('photo_invalid_or_too_large')
    return data


def keyboard(buttons):
    rows = []
    for label, action in buttons:
        if action.startswith('url:'):
            url = action[4:]
            if not url.startswith('https://'):
                raise DeliveryError('invalid_button_url')
            button = {'text':label, 'url':url}
        else:
            if len(action.encode()) > 64:
                raise DeliveryError('callback_too_long')
            button = {'text':label, 'callback_data':action}
        rows.append([button])
    return {'inline_keyboard':rows}


def send_reply(chat_id, response):
    if response.get('evidence_id'):
        return send_evidence_photo(chat_id,response)
    text = response['text']
    for offset in range(0, len(text), 3500):
        payload = {'chat_id':chat_id,'text':text[offset:offset+3500]}
        if offset+3500 >= len(text) and response.get('buttons'):
            payload['reply_markup'] = keyboard(response['buttons'])
        bot_call('sendMessage', payload)



def send_evidence_photo(chat_id, response):
    import secrets
    from .models import TelegramUser, Officer, AssessmentEvidence
    from .access import cases_for
    user=TelegramUser.objects.filter(telegram_id=chat_id).first()
    officer=Officer.objects.filter(telegram=user,verified=True).first() if user else None
    evidence=AssessmentEvidence.objects.filter(pk=response['evidence_id'],application__in=cases_for(officer)).first()
    if not evidence:
        raise DeliveryError('recipient_access_revoked')
    boundary='salam-'+secrets.token_hex(16)
    payload={'chat_id':str(chat_id),'caption':response['text'][:900],'protect_content':'true','reply_markup':json.dumps(keyboard(response.get('buttons',[])))}
    parts=[]
    for name,value in payload.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="photo"; filename="bukti.jpg"\r\nContent-Type: image/jpeg\r\n\r\n'.encode()+bytes(evidence.image)+b'\r\n')
    parts.append(f'--{boundary}--\r\n'.encode())
    credential=token()
    try:
        req=Request(f'https://api.telegram.org/bot{credential}/sendPhoto',data=b''.join(parts),headers={'Content-Type':f'multipart/form-data; boundary={boundary}'})
        with urlopen(req,timeout=40) as result:
            data=json.load(result)
    except HTTPError as exc:
        retry=None
        if exc.code==429:
            try: retry=int(json.loads(exc.read()).get('parameters',{}).get('retry_after',60))
            except (ValueError,TypeError): retry=60
        raise DeliveryError('telegram_rate_limit' if exc.code==429 else f'telegram_http_{exc.code}',retry) from None
    except (URLError,TimeoutError,OSError,ValueError,http.client.HTTPException):
        raise DeliveryError('telegram_photo_send_failed') from None
    if not isinstance(data,dict) or not data.get('ok'):
        raise DeliveryError('telegram_rejected')
    return data['result']

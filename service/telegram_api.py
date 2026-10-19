"""Small Bot API client. Exceptions never include token-bearing URLs or payloads."""
import json
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from django.conf import settings

class DeliveryError(Exception):
    def __init__(self,reason='transport_failed',retry_after=None):
        self.reason=reason
        self.retry_after=retry_after
        super().__init__(reason)

def bot_call(method,payload):
    if not settings.TELEGRAM_BOT_TOKEN: raise DeliveryError('bot_not_configured')
    req=Request(f'https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/{method}',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
    try:
        with urlopen(req,timeout=45) as response: data=json.load(response)
    except HTTPError as exc:
        retry=None
        if exc.code==429:
            try: retry=json.loads(exc.read()).get('parameters',{}).get('retry_after',60)
            except (ValueError,TypeError): retry=60
        raise DeliveryError('telegram_rate_limit' if exc.code==429 else f'telegram_http_{exc.code}',retry) from None
    except (URLError,TimeoutError,OSError,ValueError): raise DeliveryError('telegram_connection_failed') from None
    if not data.get('ok'): raise DeliveryError('telegram_rejected')
    return data['result']

def send_reply(chat_id,response):
    # Telegram's 4096-character limit; plain text avoids markup interpretation.
    text=response['text']
    for offset in range(0,len(text),3500):
        payload={'chat_id':chat_id,'text':text[offset:offset+3500]}
        if offset+3500>=len(text) and response.get('buttons'):
            keyboard=[]
            for label,action in response['buttons']:
                if len(action.encode())>64: raise DeliveryError('callback_too_long')
                keyboard.append([{'text':label,'callback_data':action}])
            payload['reply_markup']={'inline_keyboard':keyboard}
        bot_call('sendMessage',payload)

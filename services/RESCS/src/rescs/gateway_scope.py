"""Short-lived, method/path-bound scope assertions from the trusted CORE gateway."""
import contextvars
import hashlib
import hmac
import re
import time

from starlette.responses import JSONResponse
from rescs.mounts import check_mount

current_owner = contextvars.ContextVar('rescs_owner', default='')


def signed_headers(key, owner, method, path, expires=None):
    expires = int(time.time()) + 30 if expires is None else expires
    message = f'{owner}\n{expires}\n{method.upper()}\n{path}'
    signature = hmac.new(key.encode(), message.encode(), hashlib.sha256).hexdigest()
    return {'X-RESCS-Owner': owner, 'X-RESCS-Expires': str(expires), 'X-RESCS-Signature': signature}


class ScopeMiddleware:
    def __init__(self, app, settings):
        self.app, self.settings = app, settings

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        try:
            check_mount(self.settings)
        except (OSError, ValueError):
            return await JSONResponse({'error': {'code': 'storage_unavailable', 'message': 'Required storage mount unavailable'}}, status_code=503)(scope, receive, send)
        token = None
        if self.settings.require_signed_owner and scope['path'].startswith('/api/v1/'):
            headers = dict(scope['headers'])
            try:
                owner = headers.get(b'x-rescs-owner', b'').decode()
                expiry = int(headers.get(b'x-rescs-expires', b'0'))
                if not re.fullmatch(r'core\.profile\.[a-f0-9]{32}', owner):
                    raise ValueError()
                if not int(time.time()) <= expiry <= int(time.time()) + 60:
                    raise ValueError()
                expected = signed_headers(self.settings.api_key, owner, scope['method'], scope['path'], expiry)['X-RESCS-Signature']
                if not hmac.compare_digest(expected, headers.get(b'x-rescs-signature', b'').decode()):
                    raise ValueError()
            except (ValueError, UnicodeError):
                return await JSONResponse({'error': {'code': 'unauthorized', 'message': 'Valid gateway scope required'}}, status_code=401)(scope, receive, send)
            # Never allow a profile assertion to invoke global cleanup.
            if scope['path'] == '/api/v1/admin/cleanup':
                return await JSONResponse({'error': {'code': 'forbidden', 'message': 'Global maintenance is offline operator-only in signed mode'}}, status_code=403)(scope, receive, send)
            scope.setdefault('state', {})['scoped_settings'] = self.settings.model_copy(update={'api_key_owner': owner})
            token = current_owner.set(owner)
        try:
            return await self.app(scope, receive, send)
        finally:
            if token is not None:
                current_owner.reset(token)

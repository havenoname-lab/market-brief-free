"""Optional shared-reader login for HTTPS cloud hosting."""
import base64
import binascii
import os
import secrets

from starlette.responses import Response


def configure_access(app):
    password = os.getenv('NEWS_ACCESS_PASSWORD', '')
    username = os.getenv('NEWS_ACCESS_USERNAME', 'reader')
    if os.getenv('NEWS_CLOUD') == '1' and len(password) < 16:
        raise ValueError('NEWS_ACCESS_PASSWORD must contain at least 16 characters in cloud mode')
    if not password:
        return

    @app.middleware('http')
    async def authenticate(request, call_next):
        if request.url.path == '/healthz':
            return await call_next(request)
        try:
            scheme, token = request.headers.get('authorization', '').split(' ', 1)
            decoded = base64.b64decode(token, validate=True).decode('utf-8')
            user, supplied = decoded.split(':', 1)
            valid_user = secrets.compare_digest(user.encode(), username.encode())
            valid_password = secrets.compare_digest(supplied.encode(), password.encode())
            valid = scheme.lower() == 'basic' and valid_user and valid_password
        except (ValueError, UnicodeError, binascii.Error):
            valid = False
        if not valid:
            return Response('Login required', status_code=401,
                            headers={'WWW-Authenticate': 'Basic realm="Market Brief", charset="UTF-8"',
                                     'Cache-Control': 'no-store'})
        response = await call_next(request)
        response.headers['Cache-Control'] = 'private, no-store'
        return response

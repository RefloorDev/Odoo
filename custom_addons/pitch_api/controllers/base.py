import os
import json
import logging
from functools import wraps
from datetime import date, datetime

from odoo import fields
from odoo.http import request, Response

_logger = logging.getLogger(__name__)


def json_serial(obj):
    """JSON serializer for objects not serializable by default json code."""
    if isinstance(obj, (datetime, date)):
        return fields.Datetime.to_string(obj)
    if isinstance(obj, bytes):
        return obj.decode()
    if hasattr(obj, '__dict__'):
        return obj.__dict__
    raise TypeError(f"Type {type(obj)} not serializable")


def mask_token(token: str) -> str:
    """Return a masked version of a token to avoid logging full secrets.

    Examples:
        abcdefghijkl -> abcdef...ijkl
        short -> short
    """
    try:
        if not token:
            return ''
        if len(token) <= 12:
            return token
        return f"{token[:6]}...{token[-6:]}"
    except Exception:
        return ''


def json_response(f):
    """Decorator that parses JSON body into kwargs and returns JSON responses."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            json_data = request.httprequest.get_data().decode('utf-8')
            if json_data:
                data = json.loads(json_data)
                if isinstance(data, dict):
                    kwargs.update(data)
        except Exception as e:
            _logger.debug("Failed to parse JSON body: %s", e)
            params = request.params.copy() if hasattr(request, 'params') else {}
            if params:
                try:
                    params = dict(params)
                    kwargs.update(params)
                except Exception:
                    pass

        result = f(*args, **kwargs)

        # If the view returned an odoo Response, pass it through
        if isinstance(result, Response):
            return result

        # Support returning (body, status) or (body, status, headers)
        status = 200
        extra_headers = None
        body = result

        if isinstance(result, tuple) and len(result) >= 2:
            body, status = result[0], result[1]
            if len(result) >= 3:
                extra_headers = result[2]

        # Only JSON-serialize dicts/lists; allow plain strings as-is
        if isinstance(body, (dict, list)):
            body_text = json.dumps(body, default=json_serial)
            headers = [('Content-Type', 'application/json'), ('Content-Length', str(len(body_text)))]
            if extra_headers:
                # merge/append headers
                headers.extend(list(extra_headers.items()) if isinstance(extra_headers, dict) else list(extra_headers))
            return Response(body_text, status=int(status), headers=headers)

        if isinstance(body, str):
            headers = [('Content-Type', 'text/plain; charset=utf-8'), ('Content-Length', str(len(body)))]
            if extra_headers:
                headers.extend(list(extra_headers.items()) if isinstance(extra_headers, dict) else list(extra_headers))
            return Response(body, status=int(status), headers=headers)

        # Fallback: return original result unchanged
        return result

    return wrapper


def _ensure_secret(env):
    """Ensure a server-wide JWT secret exists in ir.config_parameter.

    The secret is created on-first-use and stored under the key
    `pitch_api.jwt_secret`.
    """
    params = env["ir.config_parameter"].sudo()
    key = params.get_param("pitch_api.jwt_secret")
    if not key:
        key = os.urandom(32).hex()
        params.set_param("pitch_api.jwt_secret", key)
    return key

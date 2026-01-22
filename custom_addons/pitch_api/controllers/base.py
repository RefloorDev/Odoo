# -*- coding: utf-8 -*-
"""Base utilities for Pitch API controllers.

This module provides common utilities used across all API controllers:
- JSON serialization helpers
- Response decorator for consistent API responses
- Security utilities for token management
"""

import json
import logging
from functools import wraps
from datetime import date, datetime

from odoo import fields
from odoo.http import request, Response

_logger = logging.getLogger(__name__)

# =============================================================================
# Imports from Models (Single Source of Truth)
# =============================================================================

from ..models.refresh_token import JWT_SECRET_PARAM_KEY, get_jwt_secret


# =============================================================================
# Serialization Utilities
# =============================================================================

def json_serial(obj):
    """JSON serializer for objects not serializable by default.

    Handles:
        - datetime/date objects: converts to Odoo format string
        - bytes: decodes to UTF-8 string
        - objects with __dict__: returns dict representation

    Args:
        obj: Object to serialize.

    Returns:
        Serializable representation of the object.

    Raises:
        TypeError: If object type is not supported.
    """
    if isinstance(obj, (datetime, date)):
        return fields.Datetime.to_string(obj)
    if isinstance(obj, bytes):
        return obj.decode('utf-8')
    if hasattr(obj, '__dict__'):
        return obj.__dict__
    raise TypeError(f"Type {type(obj)} not serializable")


# =============================================================================
# Security Utilities
# =============================================================================

def mask_token(token: str) -> str:
    """Return a masked version of a token for safe logging.

    Masks the middle portion of tokens longer than 12 characters
    to prevent full secrets from appearing in logs.

    Args:
        token: The token string to mask.

    Returns:
        Masked token string (e.g., 'abcdef...ijklmn').

    Examples:
        >>> mask_token('abcdefghijklmnop')
        'abcdef...mnop'
        >>> mask_token('short')
        'short'
    """
    if not token:
        return ''
    if len(token) <= 12:
        return token
    return f"{token[:6]}...{token[-6:]}"


def ensure_jwt_secret(env):
    """Ensure a server-wide JWT secret exists in ir.config_parameter.

    The secret is created on first use and stored persistently.
    Uses cryptographically secure random bytes for key generation.

    Delegates to get_jwt_secret from models.refresh_token for
    single source of truth.

    Args:
        env: Odoo environment object.

    Returns:
        str: The JWT secret key (64-character hex string).
    """
    return get_jwt_secret(env)


# Legacy alias for backward compatibility
_ensure_secret = ensure_jwt_secret


# =============================================================================
# Response Decorator
# =============================================================================

def json_response(func):
    """Decorator for consistent JSON API responses.

    This decorator:
    1. Parses JSON body from request and adds to kwargs
    2. Handles response formatting based on return type
    3. Supports multiple return formats:
       - (body, status) tuple
       - (body, status, headers) tuple
       - Plain dict/list (defaults to 200)
       - Odoo Response object (passed through)

    Args:
        func: Controller method to wrap.

    Returns:
        Wrapped function with JSON handling.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Parse JSON body into kwargs
        try:
            raw_data = request.httprequest.get_data().decode('utf-8')
            if raw_data:
                parsed = json.loads(raw_data)
                if isinstance(parsed, dict):
                    kwargs.update(parsed)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            _logger.debug("Failed to parse JSON body: %s", e)
            # Fallback: try request params
            if hasattr(request, 'params') and request.params:
                try:
                    kwargs.update(dict(request.params))
                except (TypeError, ValueError) as e:
                    _logger.debug("Failed to update kwargs from params: %s", e)

        # Execute controller method
        result = func(*args, **kwargs)

        # Pass through Odoo Response objects unchanged
        if isinstance(result, Response):
            return result

        # Parse return value
        body = result
        status = 200
        extra_headers = None

        if isinstance(result, tuple):
            if len(result) >= 2:
                body, status = result[0], result[1]
            if len(result) >= 3:
                extra_headers = result[2]

        # Build response
        if isinstance(body, (dict, list)):
            body_text = json.dumps(body, default=json_serial)
            headers = [
                ('Content-Type', 'application/json'),
                ('Content-Length', str(len(body_text)))
            ]
            if extra_headers:
                headers.extend(
                    list(extra_headers.items()) if isinstance(extra_headers, dict)
                    else list(extra_headers)
                )
            return Response(body_text, status=int(status), headers=headers)

        if isinstance(body, str):
            headers = [
                ('Content-Type', 'text/plain; charset=utf-8'),
                ('Content-Length', str(len(body)))
            ]
            if extra_headers:
                headers.extend(
                    list(extra_headers.items()) if isinstance(extra_headers, dict)
                    else list(extra_headers)
                )
            return Response(body, status=int(status), headers=headers)

        # Fallback: return unchanged
        return result

    return wrapper

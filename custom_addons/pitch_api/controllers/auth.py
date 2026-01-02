# -*- coding: utf-8 -*-
"""Authentication API Controller.

Provides REST API endpoints for JWT-based authentication:
    POST /api/auth/login      - Exchange credentials for access + refresh tokens
    POST /api/auth/refresh    - Rotate refresh token for new access token
    POST /api/auth/logout     - Revoke tokens (single device or all devices)
    POST /api/auth/introspect - Validate token and return claims
    GET  /api/auth/me         - Get current user profile
    GET  /api/auth/devices    - List active login devices
    POST /api/auth/revoke_refresh - Revoke a specific refresh token

Security Features:
    - JWT access tokens with HMAC-SHA256 signatures
    - Rotating refresh tokens with device binding
    - Token revocation tracking
    - Multi-device session management
    - Rate limiting per device
"""

import os
import time
import uuid
import json
import hmac
import base64
import hashlib
import logging
from datetime import datetime, timezone

from odoo.service import common as odoo_common
from odoo import http, fields
from odoo.http import request

from .base import json_response, ensure_jwt_secret, mask_token
from ..models.refresh_token import verify_token_hash, PBKDF2_ITERATIONS

try:
    import jwt
except ImportError:
    jwt = None

_logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

DEFAULT_ACCESS_TOKEN_EXPIRY = 3600  # 1 hour
DEFAULT_REFRESH_TOKEN_EXPIRY = 60 * 60 * 24 * 30  # 30 days
TOKEN_ISSUER = 'refloor_v18'
TOKEN_AUDIENCE = 'pitch_api_users'

# Standardized expired token response (OAuth 2.0 / RFC 6750 compliant)
# Clients should check for error="token_expired" to trigger refresh flow
EXPIRED_TOKEN_RESPONSE = {
    "error": "token_expired",
    "error_description": "The access token has expired. Use refresh token to obtain a new access token.",
    "error_code": "TOKEN_EXPIRED"
}
EXPIRED_TOKEN_STATUS = 401

# Standardized expired refresh token response
# Clients should check for error="refresh_token_expired" to force re-login
EXPIRED_REFRESH_TOKEN_RESPONSE = {
    "error": "refresh_token_expired",
    "error_description": "The refresh token has expired. Please login again.",
    "error_code": "REFRESH_TOKEN_EXPIRED"
}
EXPIRED_REFRESH_TOKEN_STATUS = 401


class AuthController(http.Controller):
    """REST API controller for authentication endpoints.

    All endpoints use auth='none' to allow external systems to
    authenticate without existing Odoo sessions.
    """

    # =========================================================================
    # Device Info Helpers
    # =========================================================================

    def _get_device_info(self):
        """Extract device information from request headers.

        Required Headers:
            X-Device-ID: Unique device identifier

        Optional Headers:
            X-Device-Name: Human-readable device name
            X-App-Version: Client application version
            User-Agent: Browser/client user agent

        Returns:
            dict: Device information.

        Raises:
            ValueError: If X-Device-ID header is missing.
        """
        headers = request.httprequest.headers
        device_id = headers.get('X-Device-ID')

        if not device_id:
            raise ValueError("X-Device-ID header is required")

        return {
            'device_id': device_id,
            'device_name': headers.get('X-Device-Name', 'Unknown Device'),
            'user_agent': headers.get('User-Agent', 'Unknown'),
            'app_version': headers.get('X-App-Version', 'Unknown'),
            'ip_address': request.httprequest.remote_addr,
        }

    def _extract_bearer_token(self):
        """Extract Bearer token from Authorization header.

        Returns:
            tuple: (token, None) on success or (None, error_response) on failure.
        """
        auth_header = (
            request.httprequest.headers.get('Authorization') or
            request.httprequest.headers.get('authorization')
        )

        if not auth_header:
            return None, ({
                "error": "invalid_request",
                "error_description": "Authorization header with bearer token required"
            }, 400)

        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != 'bearer':
            return None, ({
                "error": "invalid_request",
                "error_description": "Authorization header must be 'Bearer <token>'"
            }, 400)

        return parts[1], None

    # =========================================================================
    # JWT Generation Helpers
    # =========================================================================

    def _generate_access_token(self, user, device_info, secret, expires_in):
        """Generate a signed JWT access token.

        Args:
            user: res.users record.
            device_info: Device information dict.
            secret: JWT signing secret.
            expires_in: Token lifetime in seconds.

        Returns:
            tuple: (token_string, jti) or (None, error_response).
        """
        now = int(time.time())
        jti = uuid.uuid4().hex

        header = {
            "typ": "JWT",
            "alg": "HS256",
            "kid": hashlib.sha256(secret.encode()).hexdigest()[:8]
        }

        payload = {
            "iss": TOKEN_ISSUER,
            "sub": str(user.id),
            "aud": TOKEN_AUDIENCE,
            "iat": now,
            "exp": now + expires_in,
            "jti": jti,
            "uid": user.id,
            "login": user.login,
            "device_id": device_info.get('device_id'),
            "device_name": device_info.get('device_name'),
            "scope": "api:access"
        }

        try:
            # Manual encoding for consistent format
            header_b64 = base64.urlsafe_b64encode(
                json.dumps(header).encode()
            ).rstrip(b'=').decode()

            payload_b64 = base64.urlsafe_b64encode(
                json.dumps(payload).encode()
            ).rstrip(b'=').decode()

            signature_input = f"{header_b64}.{payload_b64}".encode()
            signature = hmac.new(
                secret.encode(),
                signature_input,
                hashlib.sha256
            ).digest()
            signature_b64 = base64.urlsafe_b64encode(signature).rstrip(b'=').decode()

            token = f"{header_b64}.{payload_b64}.{signature_b64}"
            return token, jti

        except Exception as e:
            _logger.exception("JWT generation failed: %s", e)
            return None, ({
                "error": "server_error",
                "error_description": "Failed to generate access token"
            }, 500)

    def _decode_access_token(self, token, secret, verify_exp=True, verify_claims=True):
        """Decode and validate a JWT access token.

        Args:
            token: JWT token string.
            secret: JWT signing secret.
            verify_exp: Whether to verify expiration.
            verify_claims: Whether to verify issuer and audience claims.

        Returns:
            dict or None: Token payload if valid.
        """
        try:
            parts = token.split('.')
            if len(parts) != 3:
                return None

            header_b64, payload_b64, signature = parts

            # Verify signature
            signature_input = f"{header_b64}.{payload_b64}".encode()
            expected_sig = base64.urlsafe_b64encode(
                hmac.new(secret.encode(), signature_input, hashlib.sha256).digest()
            ).rstrip(b'=').decode()

            if not hmac.compare_digest(signature, expected_sig):
                return None

            # Decode payload
            padding = '=' * (-len(payload_b64) % 4)
            payload_json = base64.urlsafe_b64decode(payload_b64 + padding)
            payload = json.loads(payload_json)

            # Verify issuer and audience claims
            if verify_claims:
                if payload.get('iss') != TOKEN_ISSUER:
                    _logger.warning("Token issuer mismatch: expected=%s got=%s", TOKEN_ISSUER, payload.get('iss'))
                    return None
                if payload.get('aud') != TOKEN_AUDIENCE:
                    _logger.warning("Token audience mismatch: expected=%s got=%s", TOKEN_AUDIENCE, payload.get('aud'))
                    return None

            # Check expiration
            if verify_exp:
                now = int(time.time())
                if payload.get('exp', 0) < now:
                    return None

            return payload

        except (ValueError, KeyError, json.JSONDecodeError) as e:
            _logger.debug("Token decode failed: %s", e)
            return None
        except Exception as e:
            _logger.debug("Unexpected error decoding token: %s", e)
            return None

    # =========================================================================
    # Token Introspection
    # =========================================================================

    def _introspect_access_token(self, token):
        """Introspect an access token.

        Returns:
            dict: Introspection result with 'active' key.
        """
        try:
            secret = ensure_jwt_secret(request.env)
            payload = self._decode_access_token(token, secret, verify_exp=True, verify_claims=True)

            if not payload:
                # Try without exp check to get reason
                payload_no_exp = self._decode_access_token(token, secret, verify_exp=False, verify_claims=False)
                if payload_no_exp:
                    # Check what failed
                    if payload_no_exp.get('iss') != TOKEN_ISSUER:
                        return {"active": False, "reason": "invalid_issuer"}
                    if payload_no_exp.get('aud') != TOKEN_AUDIENCE:
                        return {"active": False, "reason": "invalid_audience"}
                    # Must be expired
                    return {"active": False, "reason": "expired"}
                return {"active": False, "reason": "invalid_signature"}

            # Check revocation
            jti = payload.get('jti')
            if jti and request.env['auth.revoked.token'].sudo().is_revoked(jti):
                return {"active": False, "reason": "revoked"}

            return {
                "active": True,
                "token_type": "access_token",
                "token_use": "access",
            }

        except Exception as e:
            _logger.debug("Access token introspection failed: %s", e)
            return {"active": False, "reason": "invalid_format"}

    def _introspect_refresh_token(self, token):
        """Introspect a refresh token.

        Returns:
            dict: Introspection result with 'active' key.
        """
        try:
            rt_model = request.env['auth.refresh.token'].sudo()

            # Try to get device_id from headers
            device_id = None
            try:
                device_info = self._get_device_info()
                device_id = device_info.get('device_id')
            except ValueError:
                # X-Device-ID header missing - expected in some cases
                pass
            except Exception as e:
                _logger.debug("Failed to get device info: %s", e)

            # Verify token - requires device_id for secure lookup
            token_record = None
            if device_id:
                try:
                    token_record, _ = rt_model.verify_token(token, device_id)
                except Exception as e:
                    _logger.debug("Refresh token verification failed: %s", e)

            # NOTE: Removed slow fallback _find_refresh_token_by_hash
            # The fallback scanned 2000 tokens with PBKDF2 (200k iterations each)
            # which caused 15-20 second response times.
            # Refresh tokens MUST be verified with device_id for performance.

            if not token_record:
                if not device_id:
                    return {"active": False, "reason": "missing_device_id"}
                return {"active": False, "reason": "not_found"}

            # Check expiration
            try:
                expires_dt = fields.Datetime.from_string(token_record.expires_on)
                now_dt = fields.Datetime.from_string(fields.Datetime.now())
                if expires_dt < now_dt:
                    return {"active": False, "reason": "expired"}
            except (ValueError, TypeError) as e:
                _logger.debug("Invalid token expiry format: %s", e)
                return {"active": False, "reason": "invalid_expiry"}

            return {
                "active": True,
                "token_type": "refresh_token",
                "token_use": "refresh",
                "user_id": token_record.user_id.id,
                "device_id": token_record.device_id,
                "expires_at": fields.Datetime.to_string(token_record.expires_on),
                "created_at": fields.Datetime.to_string(token_record.created_on)
            }

        except Exception as e:
            _logger.debug("Refresh token introspection failed: %s", e)
            return {"active": False, "reason": "invalid_format"}

    def _find_refresh_token_by_hash(self, token_plain, rt_model):
        """Find a refresh token record by comparing hashes.

        NOTE: This method is deprecated and slow. Only kept for legacy support.
        New code should use token_id lookup.

        Args:
            token_plain: Plaintext token.
            rt_model: auth.refresh.token model.

        Returns:
            Record or None.
        """
        try:
            candidates = rt_model.search([('revoked', '=', False)], limit=2000)
            for cand in candidates:
                if verify_token_hash(cand.token_hash, token_plain):
                    return cand
        except Exception as e:
            _logger.debug("Error searching refresh tokens: %s", e)

        return None

    def _find_expired_refresh_token(self, token_plain, device_id, rt_model):
        """Check if a refresh token exists but is expired.

        Args:
            token_plain: Plaintext refresh token.
            device_id: Device ID to match.
            rt_model: auth.refresh.token model.

        Returns:
            Record if token exists and is expired, None otherwise.
        """
        try:
            now = fields.Datetime.now()
            # Search for expired (but not revoked) tokens for this device
            candidates = rt_model.search([
                ('device_id', '=', device_id),
                ('revoked', '=', False),
                ('expires_on', '<=', now)
            ], limit=100)

            for cand in candidates:
                if verify_token_hash(cand.token_hash, token_plain):
                    return cand
        except Exception as e:
            _logger.debug("Error searching expired tokens by hash: %s", e)

        return None

    # =========================================================================
    # Login Endpoint
    # =========================================================================

    @http.route("/api/auth/login", auth="none", methods=["POST"], csrf=False)
    @json_response
    def login(self, **post):
        """Exchange username/password for access and refresh tokens.

        Request JSON:
            {
                "username": "...",
                "password": "...",
                "device_name": "Optional device name"
            }

        Required Headers:
            X-Device-ID: Unique device identifier

        Returns:
            {
                "access_token": "...",
                "token_type": "bearer",
                "expires_in": <configured_value>,
                "refresh_token": "...",
                "user_id": 123,
                "improveit_user_id": "..."
            }
        """
        if jwt is None:
            return ({
                "error": "server_error",
                "error_description": "PyJWT is not installed on the server"
            }, 500)

        # Validate device headers
        try:
            device_info = self._get_device_info()
        except ValueError as e:
            return ({"error": "invalid_request", "error_description": str(e)}, 400)

        # Parse credentials
        username = post.get("username") or post.get("login")
        password = post.get("password")

        _logger.info(
            "Auth.login: attempt username=%s device=%s ip=%s",
            username, device_info['device_id'], device_info['ip_address']
        )

        if not username or password is None:
            return ({
                "error": "invalid_request",
                "error_description": "username and password required"
            }, 400)

        # Authenticate with Odoo
        db = request.env.cr.dbname
        uid = odoo_common.exp_authenticate(db, username, password, {})

        if not uid:
            _logger.warning(
                "Auth.login: failed username=%s device=%s ip=%s",
                username, device_info['device_id'], device_info['ip_address']
            )
            return ({"error": "invalid_grant", "error_description": "invalid credentials"}, 401)

        user = request.env['res.users'].sudo().browse(uid)

        # Get configuration
        secret = ensure_jwt_secret(request.env)
        params = request.env['ir.config_parameter'].sudo()
        expires_in = int(params.get_param('pitch_api.jwt_expiration', DEFAULT_ACCESS_TOKEN_EXPIRY))
        refresh_expires = int(params.get_param('pitch_api.refresh_token_expiration', DEFAULT_REFRESH_TOKEN_EXPIRY))

        # Override device name if provided
        if post.get('device_name'):
            device_info['device_name'] = post['device_name']

        # Revoke existing session for this device
        rt_model = request.env['auth.refresh.token'].sudo()
        existing = rt_model.search([
            ('user_id', '=', user.id),
            ('device_id', '=', device_info['device_id']),
            ('revoked', '=', False)
        ], limit=1)

        if existing:
            existing.revoke(reason='new_login')

        # Generate tokens
        access_token, jti = self._generate_access_token(user, device_info, secret, expires_in)
        if not access_token:
            return jti  # Error response

        rec, refresh_token = rt_model.create_for_user(
            user=user,
            device_id=device_info['device_id'],
            device_name=device_info['device_name'],
            client_info=device_info['user_agent'],
            ip_address=device_info['ip_address'],
            expires_seconds=refresh_expires
        )

        _logger.info(
            "Auth.login: success user_id=%s device=%s jti=%s",
            user.id, device_info['device_id'], jti
        )

        return ({
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": expires_in,
            "refresh_token": refresh_token,
            "user_id": user.id,
            "improveit_user_id": getattr(user, 'improveit_user_id', None),
        }, 200)

    # =========================================================================
    # Refresh Endpoint
    # =========================================================================

    @http.route("/api/auth/refresh", auth="none", methods=["POST"], csrf=False)
    @json_response
    def refresh(self, **post):
        """Exchange refresh token for new access token (with rotation).

        Request JSON:
            {"refresh_token": "..."}

        Required Headers:
            X-Device-ID: Device identifier (must match original)

        Returns:
            {
                "access_token": "...",
                "token_type": "bearer",
                "expires_in": <configured_value>,
                "refresh_token": "..." (new rotated token)
            }
        """
        if jwt is None:
            return ({
                "error": "server_error",
                "error_description": "PyJWT is not installed on the server"
            }, 500)

        try:
            device_info = self._get_device_info()
        except ValueError as e:
            return ({"error": "invalid_request", "error_description": str(e)}, 400)

        _logger.info(
            "Auth.refresh: attempt device=%s ip=%s",
            device_info['device_id'], device_info['ip_address']
        )

        refresh_token = post.get("refresh_token")
        if not refresh_token:
            return ({
                "error": "invalid_request",
                "error_description": "refresh_token required"
            }, 400)

        # Verify refresh token
        rt_model = request.env['auth.refresh.token'].sudo()
        token_rec, valid = rt_model.verify_token(refresh_token, device_info['device_id'])

        if not token_rec:
            # Check if token exists but is expired
            expired_token = self._find_expired_refresh_token(refresh_token, device_info['device_id'], rt_model)
            if expired_token:
                _logger.warning(
                    "Auth.refresh: expired token device=%s token=%s",
                    device_info['device_id'], mask_token(refresh_token)
                )
                return (EXPIRED_REFRESH_TOKEN_RESPONSE, EXPIRED_REFRESH_TOKEN_STATUS)
            
            _logger.warning(
                "Auth.refresh: invalid token device=%s token=%s",
                device_info['device_id'], mask_token(refresh_token)
            )
            return ({"error": "invalid_grant", "error_description": "invalid refresh token"}, 401)

        # Revoke old token (rotation)
        try:
            if valid and hasattr(token_rec, 'revoke'):
                token_rec.revoke()
        except Exception:
            _logger.exception("Failed to revoke old refresh token")

        user = token_rec.user_id.sudo()

        # Get configuration
        secret = ensure_jwt_secret(request.env)
        params = request.env['ir.config_parameter'].sudo()
        expires_in = int(params.get_param('pitch_api.jwt_expiration', DEFAULT_ACCESS_TOKEN_EXPIRY))
        refresh_expires = int(params.get_param('pitch_api.refresh_token_expiration', DEFAULT_REFRESH_TOKEN_EXPIRY))

        # Generate new tokens
        payload = {
            "iss": TOKEN_ISSUER,
            "sub": str(user.id),
            "aud": TOKEN_AUDIENCE,
            "iat": int(time.time()),
            "exp": int(time.time()) + expires_in,
            "jti": uuid.uuid4().hex,
            "uid": user.id,
            "login": user.login,
        }

        try:
            access_token = jwt.encode(payload, secret, algorithm="HS256")
        except Exception as e:
            _logger.exception("JWT generation failed: %s", e)
            return ({"error": "server_error", "error_description": str(e)}, 500)

        # Issue new refresh token
        rec, new_refresh_token = rt_model.create_for_user(
            user,
            device_id=device_info['device_id'],
            expires_seconds=refresh_expires
        )

        _logger.info(
            "Auth.refresh: success user_id=%s device=%s",
            user.id, device_info['device_id']
        )

        return ({
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": expires_in,
            "refresh_token": new_refresh_token
        }, 200)

    # =========================================================================
    # Logout Endpoint
    # =========================================================================

    @http.route("/api/auth/logout", auth="none", methods=["POST"], csrf=False)
    @json_response
    def logout(self, **post):
        """Logout and revoke tokens.

        Request JSON (optional):
            {"logout_all": true}  - Logout from all devices

        Required Headers:
            Authorization: Bearer <token>
            X-Device-ID: Device identifier

        Returns:
            {"revoked": true, ...}
        """
        try:
            device_info = self._get_device_info()
        except ValueError as e:
            return ({"error": "invalid_request", "error_description": str(e)}, 400)

        logout_all = post.get("logout_all", False)

        _logger.info(
            "Auth.logout: attempt logout_all=%s device=%s ip=%s",
            logout_all, device_info['device_id'], device_info['ip_address']
        )

        # Extract token from header
        token, err = self._extract_bearer_token()
        if err:
            return err

        rt_model = request.env['auth.refresh.token'].sudo()
        secret = ensure_jwt_secret(request.env)

        # Determine token type
        is_access = token.count('.') == 2
        access_data = None

        if is_access:
            access_data = self._decode_access_token(token, secret, verify_exp=False)

        # Handle logout_all
        if logout_all:
            user_id = None
            if is_access and access_data:
                user_id = access_data.get('uid')
            else:
                token_rec, _ = rt_model.verify_token(token, device_info['device_id'])
                if token_rec:
                    user_id = token_rec.user_id.id

            if not user_id:
                return ({
                    "error": "invalid_request",
                    "error_description": "user not identified for logout_all"
                }, 400)

            # Revoke all refresh tokens
            active_tokens = rt_model.search([
                ('user_id', '=', user_id),
                ('revoked', '=', False)
            ])
            for rt in active_tokens:
                rt.revoke(reason='user_logout')

            # Revoke access token
            if access_data and access_data.get('jti'):
                self._revoke_access_token(access_data)

            _logger.info(
                "Auth.logout: logout_all revoked %s tokens for user_id=%s",
                len(active_tokens), user_id
            )

            return ({
                "revoked": True,
                "all_devices": True,
                "device_count": len(active_tokens)
            }, 200)

        # Single device logout
        if not is_access:
            token_rec, _ = rt_model.verify_token(token, device_info['device_id'])
            if token_rec:
                token_rec.revoke(reason='user_logout')
        else:
            if access_data and access_data.get('jti'):
                self._revoke_access_token(access_data)

        _logger.info("Auth.logout: success device=%s", device_info['device_id'])

        return ({"revoked": True, "device_id": device_info['device_id']}, 200)

    def _revoke_access_token(self, access_data):
        """Revoke an access token by its JTI."""
        jti = access_data.get('jti')
        if not jti:
            return

        user_id = access_data.get('uid') or access_data.get('sub')
        if not user_id:
            return

        exp = access_data.get('exp')
        expires_at = None
        try:
            if exp:
                # Use timezone-aware datetime, then strip tzinfo for Odoo compatibility
                expires_at = datetime.fromtimestamp(int(exp), tz=timezone.utc).replace(tzinfo=None)
        except (ValueError, TypeError, OSError) as e:
            _logger.debug("Failed to parse token expiry: %s", e)
            expires_at = datetime.now(tz=timezone.utc).replace(tzinfo=None)

        request.env['auth.revoked.token'].sudo().revoke_token(
            jti=jti,
            user_id=int(user_id),
            expires_at=expires_at,
            reason='logout'
        )

    # =========================================================================
    # Introspect Endpoint
    # =========================================================================

    @http.route("/api/auth/introspect", auth="none", methods=["POST"], csrf=False)
    @json_response
    def introspect(self, **post):
        """Validate a token and return its status (RFC 7662).

        Request JSON:
            {
                "access_token": "..." or "refresh_token": "...",
                "token_type_hint": "access_token|refresh_token" (optional)
            }

        Or via Authorization header:
            Authorization: Bearer <token>

        Returns:
            {
                "active": true|false,
                "token_type": "access_token|refresh_token",
                "reason": "..." (if inactive)
            }
        """
        # Determine token source
        token = None
        token_type = None

        if post.get("access_token"):
            token = post["access_token"]
            token_type = "access_token"
        elif post.get("refresh_token"):
            token = post["refresh_token"]
            token_type = "refresh_token"

        # Fallback to Authorization header
        if not token:
            header_token, _ = self._extract_bearer_token()
            if header_token:
                token = header_token

        if not token:
            return ({"active": False, "reason": "missing_token"}, 400)

        # Auto-detect token type
        if not token_type:
            token_type = "access_token" if token.count('.') == 2 else "refresh_token"

        _logger.info(
            "Auth.introspect: type=%s token=%s",
            token_type, mask_token(token)
        )

        if token_type == "access_token":
            result = self._introspect_access_token(token)
        else:
            result = self._introspect_refresh_token(token)

        _logger.info(
            "Auth.introspect: result active=%s reason=%s",
            result.get('active'), result.get('reason')
        )

        return (result, 200)

    # =========================================================================
    # Me Endpoint
    # =========================================================================

    @http.route("/api/auth/me", auth="none", methods=["GET"], csrf=False)
    @json_response
    def me(self, **kwargs):
        """Get current user profile.

        Accepts token via:
            - Authorization: Bearer <access_token>
            - Query param: ?token=<token>

        Returns:
            {
                "user": {
                    "id": 123,
                    "name": "...",
                    "login": "...",
                    "email": "...",
                    "tz": "...",
                    "active": true
                }
            }
        """
        # Try Authorization header first
        token, _ = self._extract_bearer_token()

        if not token:
            token = kwargs.get('token') or request.params.get('token')

        if not token:
            return ({
                "error": "invalid_request",
                "error_description": "token required"
            }, 400)

        # Only accept access tokens (JWTs) - refresh tokens not allowed
        # This is fast: decode JWT + check jti in revoked table (O(1))
        if token.count('.') != 2:
            return ({
                "error": "invalid_token",
                "error_description": "access token required, refresh tokens not accepted"
            }, 400)

        # Validate access token (checks signature, expiry, and revocation via jti)
        introspection = self._introspect_access_token(token)
        if not introspection.get('active'):
            if introspection.get('reason') == 'expired':
                return (EXPIRED_TOKEN_RESPONSE, EXPIRED_TOKEN_STATUS)
            return ({
                "error": "invalid_token",
                "error_description": introspection.get('reason', 'invalid')
            }, 401)

        # Extract user_id from token
        secret = ensure_jwt_secret(request.env)
        payload = self._decode_access_token(token, secret, verify_exp=False)
        user_id = payload.get('uid') or payload.get('sub') if payload else None

        if not user_id:
            return ({
                "error": "invalid_request",
                "error_description": "could not determine user from token"
            }, 400)

        try:
            user = request.env['res.users'].sudo().browse(int(user_id))
            if not user.exists():
                return ({"error": "not_found", "error_description": "user not found"}, 404)

            profile = {
                'id': user.id,
                'name': getattr(user, 'name', None),
                'login': getattr(user, 'login', None),
                'email': getattr(user, 'email', None) or (
                    getattr(user.partner_id, 'email', None) if user.partner_id else None
                ),
                'tz': getattr(user, 'tz', None),
                'active': bool(getattr(user, 'active', True)),
            }

            _logger.info("Auth.me: success user_id=%s", user.id)
            return ({'user': profile}, 200)

        except Exception as e:
            _logger.exception("Auth.me: failed to load user: %s", e)
            return ({"error": "server_error", "error_description": "failed to load user"}, 500)

    # =========================================================================
    # Devices Endpoint
    # =========================================================================

    @http.route("/api/auth/devices", auth="none", methods=["GET"], csrf=False)
    @json_response
    def devices(self, **post):
        """List active login devices for current user.

        Requires Authorization header with Bearer token.

        Returns:
            {
                "user_id": 123,
                "device_count": 2,
                "devices": [...]
            }
        """
        # Get token from Authorization header only
        token, _ = self._extract_bearer_token()

        if not token:
            return ({
                "error": "invalid_request",
                "error_description": "Authorization header with bearer token required"
            }, 400)

        # Only accept access tokens (JWTs) - refresh tokens not allowed
        # This is fast: decode JWT + check jti in revoked table (O(1))
        if token.count('.') != 2:
            return ({
                "error": "invalid_token",
                "error_description": "access token required, refresh tokens not accepted"
            }, 400)

        # Validate access token (checks signature, expiry, and revocation via jti)
        introspection = self._introspect_access_token(token)
        if not introspection.get('active'):
            if introspection.get('reason') == 'expired':
                return (EXPIRED_TOKEN_RESPONSE, EXPIRED_TOKEN_STATUS)
            return ({
                "error": "invalid_token",
                "error_description": introspection.get('reason', 'invalid')
            }, 401)

        # Extract user_id from token
        secret = ensure_jwt_secret(request.env)
        payload = self._decode_access_token(token, secret, verify_exp=False)
        user_id = payload.get('uid') or payload.get('sub') if payload else None

        if not user_id:
            return ({
                "error": "invalid_request",
                "error_description": "could not determine user from token"
            }, 400)

        # Get active devices
        rt_model = request.env['auth.refresh.token'].sudo()
        tokens = rt_model.search([
            ('user_id', '=', user_id),
            ('revoked', '=', False)
        ])

        devices = []
        for t in tokens:
            devices.append({
                'id': t.id,
                'device_id': t.device_id,
                'device_name': t.device_name,
                'created_on': fields.Datetime.to_string(t.created_on) if t.created_on else None,
                'expires_on': fields.Datetime.to_string(t.expires_on) if t.expires_on else None,
                'last_used': fields.Datetime.to_string(t.last_used) if t.last_used else None,
                'ip_address': t.ip_address,
                'token_family': t.token_family,
                'use_count': t.use_count,
            })

        _logger.info("Auth.devices: user_id=%s count=%s", user_id, len(devices))

        return ({
            "user_id": user_id,
            "device_count": len(devices),
            "devices": devices
        }, 200)

    # =========================================================================
    # Revoke Refresh Endpoint
    # =========================================================================

    @http.route("/api/auth/revoke_refresh", auth="none", methods=["POST"], csrf=False)
    @json_response
    def revoke_refresh(self, **post):
        """Revoke a specific refresh token.

        Request JSON:
            {"refresh_token": "..."}

        Or via Authorization header.

        Returns:
            {"revoked": true, "device_id": "...", "user_id": 123}
        """
        # Extract token
        token = post.get('refresh_token')

        if not token:
            header_token, _ = self._extract_bearer_token()
            if header_token:
                token = header_token

        if not token:
            return ({
                "error": "invalid_request",
                "error_description": "refresh_token required"
            }, 400)

        rt_model = request.env['auth.refresh.token'].sudo()

        # Try device-bound verification first (fast lookup)
        device_id = None
        try:
            device_info = self._get_device_info()
            device_id = device_info.get('device_id')
        except ValueError:
            # X-Device-ID header missing - will be handled below
            pass
        except Exception as e:
            _logger.debug("Failed to get device info: %s", e)

        token_rec = None
        if device_id:
            try:
                token_rec, _ = rt_model.verify_token(token, device_id)
            except Exception as e:
                _logger.debug("Token verification failed: %s", e)

        # NOTE: Removed slow fallback _find_refresh_token_by_hash
        # The fallback scanned 2000 tokens with PBKDF2 (200k iterations each)
        # which caused 15-20 second response times.
        # Refresh tokens MUST include X-Device-ID header for revocation.

        if not token_rec:
            if not device_id:
                return ({
                    "error": "invalid_request",
                    "error_description": "X-Device-ID header required for refresh token verification"
                }, 400)
            return ({
                "error": "invalid_token",
                "error_description": "refresh token not found or invalid for this device"
            }, 404)

        try:
            token_rec.revoke(reason='client_revoke')
            _logger.info(
                "Auth.revoke_refresh: success user_id=%s device=%s",
                token_rec.user_id.id, token_rec.device_id
            )
        except Exception:
            _logger.exception("Failed to revoke refresh token")

        return ({
            "revoked": True,
            "device_id": token_rec.device_id,
            "user_id": token_rec.user_id.id
        }, 200)

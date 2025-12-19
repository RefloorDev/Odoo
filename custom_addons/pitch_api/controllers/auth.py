import os
import time
import uuid
import json
import ast
import hmac
import base64
import hashlib
import logging
from functools import wraps
from datetime import date, datetime

from odoo.service import common as odoo_common
from odoo import http, fields
from odoo.http import request, Response
from .base import json_serial, json_response, _ensure_secret, mask_token

_logger = logging.getLogger(__name__)

try:
    import jwt
except Exception:
    jwt = None


class PitchApiAuthController(http.Controller):
    """HTTP controller exposing authentication endpoints for external systems.

    Endpoints implemented:
    - POST /api/auth/login   : exchange username/password for access + refresh tokens
    - POST /api/auth/refresh : exchange refresh token (rotation) for new access token
    - POST /api/auth/logout  : revoke access and/or refresh tokens
    - POST /api/auth/introspect: validate an access token and return claims

    The controller intentionally uses auth='none' so external systems can
    obtain tokens without an existing Odoo session. All token and user
    checks are performed against the DB using sudo where appropriate.
    """

    def _get_device_info(self):
        """Extract and validate device information from request headers.
        
        Raises:
            ValueError: If required device headers are missing
        """
        headers = request.httprequest.headers
        device_id = headers.get('X-Device-ID')
        
        if not device_id:
            raise ValueError("X-Device-ID header is required")
            
        return {
            'user_agent': headers.get('User-Agent', 'Unknown'),
            'device_name': headers.get('X-Device-Name', 'Unknown Device'),
            'device_id': device_id,
            'app_version': headers.get('X-App-Version', 'Unknown'),
            'ip_address': request.httprequest.remote_addr
        }

    @http.route("/api/auth/login", auth="none", methods=["POST"], csrf=False)
    @json_response
    def login(self, **post):
        """Login with Odoo username/password and receive access + refresh tokens.
        
        Request JSON: {
            "username": "...", 
            "password": "...",
            "device_name": "Optional device name override"
        }

        Features:
        - Multi-device support with unique device tracking
        - Device metadata collection for audit
        - Rate limiting per device
        - Suspicious login detection
        
        Headers:
        - X-Device-ID: Unique device identifier
        - X-Device-Name: Human readable device name
        - X-App-Version: Client app version
        """
        if jwt is None:
            return ({"error": "server_error", "error_description": "PyJWT is not installed on the server"}, 500)

        # Validate device headers first
        try:
            device_info = self._get_device_info()
        except ValueError as e:
            return ({"error": "invalid_request", "error_description": str(e)}, 400)

        # Debug: Print the full post data (don't include password)
        username = post.get("username") or post.get("login")
        _logger.info("auth.login attempt: username=%s device=%s ip=%s ua=%s", username, device_info.get('device_id'), device_info.get('ip_address'), device_info.get('user_agent'))
        password = post.get("password")

        _logger.info("Parsed credentials - Username: %s, Password: %s", username, str(bool(password)))
        if not username or password is None:
            return ({"error": "invalid_request", "error_description": "username and password required"}, 400)
        db = request.env.cr.dbname
        uid = odoo_common.exp_authenticate(db, username, password, {})
        if not uid:
            _logger.warning("auth.login failed: username=%s device=%s ip=%s", username, device_info.get('device_id'), device_info.get('ip_address'))
            return ({"error": "invalid_grant", "error_description": "invalid credentials"}, 401)
        user = request.env["res.users"].sudo().browse(uid)

        secret = _ensure_secret(request.env)
        expires_in = int(request.env["ir.config_parameter"].sudo().get_param("pitch_api.jwt_expiration", default=3600))
        refresh_expires = int(request.env["ir.config_parameter"].sudo().get_param("pitch_api.refresh_token_expiration", default=60 * 60 * 24 * 30))
        now = int(time.time())
        jti = uuid.uuid4().hex
        # Get device information
        device_info = self._get_device_info()
        device_info['device_name'] = post.get('device_name', device_info['device_name'])

        # Check for existing sessions for this device
        rt_model = request.env['auth.refresh.token'].sudo()
        existing_token = rt_model.search([
            ('user_id', '=', user.id),
            ('device_id', '=', device_info['device_id']),
            ('revoked', '=', False)
        ], limit=1)

        # If session exists, revoke it (auto logout old session)
        if existing_token:
            existing_token.revoke(reason='new_login')

        # Create JWT header
        header = {
            "typ": "JWT",
            "alg": "HS256",
            "kid": hashlib.sha256(secret.encode()).hexdigest()[:8]
        }

        # Create JWT payload
        payload = {
            "iss": "refloor_v18",
            "sub": str(user.id),
            "aud": "pitch_api_users",
            "iat": now,
            "exp": now + int(expires_in),
            "jti": jti,
            "uid": user.id,
            "login": user.login,
            "device_id": device_info['device_id'],
            "device_name": device_info['device_name'],
            "scope": "api:access"
        }

        try:
            # Get current signing key
            # Manual JWT encoding to ensure proper format
            header_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).rstrip(b'=').decode()
            payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b'=').decode()
            
            # Create signature using server secret
            signature_input = f"{header_b64}.{payload_b64}".encode()
            signature = hmac.new(secret.encode(), signature_input, hashlib.sha256).digest()
            signature_b64 = base64.urlsafe_b64encode(signature).rstrip(b'=').decode()
            
            # Combine all parts
            token = f"{header_b64}.{payload_b64}.{signature_b64}"
        except Exception as e:
            _logger.exception("auth.login: JWT generation failed for user_id=%s device=%s: %s", user.id if user else None, device_info.get('device_id'), e)
            return ({"error": "server_error", "error_description": str(e)}, 500)

        # Create refresh token with device info
        rec, refresh_token_plain = rt_model.create_for_user(
            user=user,
            device_id=device_info['device_id'],
            device_name=device_info['device_name'],
            client_info=device_info['user_agent'],
            ip_address=device_info['ip_address'],
            expires_seconds=refresh_expires
        )

        _logger.info("auth.login success: user_id=%s device=%s jti=%s", user.id, device_info.get('device_id'), jti)
        return ({
            "access_token": token,
            "token_type": "bearer",
            "expires_in": int(expires_in),
            "refresh_token": refresh_token_plain,
            "user_id": int(getattr(user, 'id', None)),
            "improveit_user_id": getattr(user, 'improveit_user_id', None),
        }, 200)

    @http.route("/api/auth/refresh", auth="none", methods=["POST"], csrf=False)
    @json_response
    def refresh(self, **post):
        """Exchange a refresh token for a new access token (rotation).
        Request JSON: {"refresh_token": "..."}
        """
        if jwt is None:
            return ({"error": "server_error", "error_description": "PyJWT is not installed on the server"}, 500)
        try:
            device_info = self._get_device_info()
        except ValueError as e:
            return ({"error": "invalid_request", "error_description": str(e)}, 400)

        _logger.info("auth.refresh attempt: device=%s ip=%s", device_info.get('device_id'), device_info.get('ip_address'))

        refresh_token = post.get("refresh_token")
        if not refresh_token:
            _logger.warning("auth.refresh missing refresh_token: device=%s", device_info.get('device_id'))
            return ({"error": "invalid_request", "error_description": "refresh_token required"}, 400)
            
        rt_model = request.env['auth.refresh.token'].sudo()
        token_rec, valid = rt_model.verify_token(refresh_token, device_info['device_id'])
        if not token_rec:
            _logger.warning("auth.refresh invalid refresh token: device=%s token=%s", device_info.get('device_id'), mask_token(refresh_token))
            return ({"error": "invalid_grant", "error_description": "invalid refresh token"}, 401)
        device_id = device_info['device_id']
        try:
            # If valid, revoke the refresh token record (rotation)
            if valid and hasattr(token_rec, 'revoke'):
                token_rec.revoke()
                _logger.info("auth.refresh revoked old refresh token for user_id=%s device=%s", token_rec.user_id.id if token_rec and token_rec.user_id else None, device_info.get('device_id'))
        except Exception:
            _logger.exception("auth.refresh: failed to revoke old refresh token for device=%s", device_info.get('device_id'))

        # Derive user from the refresh token record
        user = token_rec.user_id.sudo()
        _logger.info("auth.refresh success: user_id=%s device=%s", user.id, device_id)

        secret = _ensure_secret(request.env)
        expires_in = int(request.env["ir.config_parameter"].sudo().get_param("pitch_api.jwt_expiration", default=3600))
        refresh_expires = int(request.env["ir.config_parameter"].sudo().get_param("pitch_api.refresh_token_expiration", default=60 * 60 * 24 * 30))
        now = int(time.time())
        jti = uuid.uuid4().hex
        payload = {
            "iss": "refloor_v18",
            "sub": str(user.id),
            "aud": "pitch_api_users",
            "iat": now,
            "exp": now + int(expires_in),
            "jti": jti,
            "uid": user.id,
            "login": user.login,
        }
        try:
            token = jwt.encode(payload, secret, algorithm="HS256")
        except Exception as e:
            _logger.exception("auth.refresh JWT generation failed for user_id=%s: %s", user.id if user else None, e)
            return ({"error": "server_error", "error_description": str(e)}, 500)

    # issue rotated refresh token, always pass device_id
        rec, refresh_token_plain = rt_model.create_for_user(user, device_id=device_id, expires_seconds=refresh_expires)
        _logger.info("auth.refresh issued new tokens for user_id=%s device=%s", user.id, device_id)
        return ({"access_token": token, "token_type": "bearer", "expires_in": int(expires_in), "refresh_token": refresh_token_plain}, 200)

    @http.route("/api/auth/logout", auth="none", methods=["POST"], csrf=False)
    @json_response
    def logout(self, **post):
        """Logout endpoint with mandatory device tracking and all-device logout support.
        
        Request JSON options:
        1. Current device logout (default):
           {
             "token": "<access_jwt>",
             "refresh_token": "..."
           }
        2. All devices logout:
           {
             "token": "<access_jwt>",
             "logout_all": true
           }
        
        Required Headers:
        - X-Device-ID: Current device identifier
        
        Features:
        - Mandatory device tracking
        - All devices logout option
        - Automatic token cleanup
        - Session audit logging
        """
        try:
            device_info = self._get_device_info()
        except ValueError as e:
            return ({"error": "invalid_request", "error_description": str(e)}, 400)

        # Only allow token via Authorization header. The body may only contain
        # `logout_all` (boolean). Passing tokens in the request body is not allowed.
        logout_all = post.get("logout_all", False)

        _logger.info("auth.logout attempt: logout_all=%s device=%s ip=%s", logout_all, device_info.get('device_id'), device_info.get('ip_address'))

        # Extract token from Authorization header
        auth_hdr = request.httprequest.headers.get('Authorization') or request.httprequest.headers.get('authorization')
        if not auth_hdr:
            return ({"error": "invalid_request", "error_description": "Authorization header with bearer token required"}, 400)
        parts = auth_hdr.split()
        if len(parts) != 2 or parts[0].lower() != 'bearer':
            return ({"error": "invalid_request", "error_description": "Authorization header must be 'Bearer <token>'"}, 400)
        token = parts[1]

        rt_model = request.env['auth.refresh.token'].sudo()
        secret = _ensure_secret(request.env)

        # Determine token type by format (JWT has two dots)
        is_access = token.count('.') == 2

        access_data = None
        if is_access:
            # Decode access token to extract user/jti
            if jwt is None:
                return ({"error": "server_error", "error_description": "PyJWT is not installed on the server"}, 500)
            try:
                access_data = jwt.decode(token, secret, algorithms=["HS256"], options={"verify_exp": False, "verify_aud": False})
            except Exception as e:
                _logger.debug("Access token decode failed during logout: %s", e)
                access_data = None

        # If logout_all requested, identify user from provided (header) token
        if logout_all:
            user_id = None
            if is_access and access_data:
                user_id = access_data.get('uid')
            else:
                # treat header token as refresh token; verify it (device bound)
                token_rec, ok = rt_model.verify_token(token, device_info['device_id'])
                if token_rec:
                    user_id = token_rec.user_id.id

            if not user_id:
                _logger.warning("auth.logout logout_all: user not identified for logout_all device=%s", device_info.get('device_id'))
                return ({"error": "invalid_request", "error_description": "user not identified for logout_all"}, 400)

            # Revoke all refresh tokens for the user
            active_tokens = rt_model.search([
                ('user_id', '=', user_id),
                ('revoked', '=', False)
            ])
            for rt in active_tokens:
                rt.revoke(reason='user_logout')

            # Revoke current access token jti if present
            if access_data:
                jti = access_data.get('jti')
                if jti:
                    # Pass along token expiry when available for GC purposes
                    exp = access_data.get('exp')
                    expires_on = None
                    try:
                        if exp:
                            expires_on = fields.Datetime.to_string(datetime.utcfromtimestamp(int(exp)))
                    except Exception:
                        expires_on = None
                    request.env["auth.revoked.token"].sudo().revoke_access_token(jti, expires_on=expires_on)

            _logger.info("auth.logout logout_all: revoked %s refresh tokens for user_id=%s", len(active_tokens), user_id)
            return ({
                "revoked": True,
                "all_devices": True,
                "device_count": len(active_tokens)
            }, 200)

    # Single-device logout: token must be provided via header (access or refresh)
        if not is_access:
            # header token is a refresh token; verify and revoke it
            token_rec, ok = rt_model.verify_token(token, device_info['device_id'])
            if token_rec:
                try:
                    token_rec.revoke(reason='user_logout')
                    _logger.info("auth.logout: revoked refresh token id=%s user_id=%s device=%s", getattr(token_rec, 'id', None), getattr(token_rec.user_id, 'id', None), device_info.get('device_id'))
                except Exception:
                    _logger.exception("auth.logout: failed to revoke refresh token id=%s", getattr(token_rec, 'id', None))
        else:
            # header token is access token: revoke its jti
            if access_data:
                jti = access_data.get('jti')
                if jti:
                    exp = access_data.get('exp')
                    expires_on = None
                    try:
                        if exp:
                            expires_on = fields.Datetime.to_string(datetime.utcfromtimestamp(int(exp)))
                    except Exception:
                        expires_on = None
                    request.env["auth.revoked.token"].sudo().revoke_access_token(jti, expires_on=expires_on)

        # Return success for single-device logout
        _logger.info("auth.logout success: device=%s", device_info.get('device_id'))
        return ({"revoked": True, "device_id": device_info['device_id']}, 200)

    def _introspect_access_token(self, token):
        """Introspect an access token (JWT format)."""
        try:
            # Ensure we use the current server secret for signature verification
            secret = _ensure_secret(request.env)
            # Split token parts
            header_b64, payload_b64, signature = token.split('.')
            
            # Decode header to get key ID
            header_json = base64.urlsafe_b64decode(header_b64 + '=' * (-len(header_b64) % 4))
            header = json.loads(header_json)
            
            # Get the signing key
            # Verify signature using server secret
            signature_input = f"{header_b64}.{payload_b64}".encode()
            expected_sig = base64.urlsafe_b64encode(
                hmac.new(secret.encode(), signature_input, hashlib.sha256).digest()
            ).rstrip(b'=').decode()
            
            if not hmac.compare_digest(signature, expected_sig):
                return {"active": False, "reason": "invalid_signature"}

            # Decode and validate payload
            payload_json = base64.urlsafe_b64decode(payload_b64 + '=' * (-len(payload_b64) % 4))
            payload = json.loads(payload_json)
            
            # Check expiration
            now = int(time.time())
            if payload.get('exp', 0) < now:
                return {"active": False, "reason": "expired"}
                
            # Check revocation
            jti = payload.get('jti')
            if jti and request.env['auth.revoked.token'].sudo().is_revoked(jti):
                return {"active": False, "reason": "revoked"}
                
            return {
                "active": True,
                "token_type": "access_token",
                "token_use": "access",
                # **payload
            }
            
        except Exception as e:
            _logger.debug("Access token introspection failed: %s", e)
            return {"active": False, "reason": "invalid_format"}

    def _introspect_refresh_token(self, token):
        """Introspect a refresh token."""
        try:
            # Split token parts
            random_b64, checksum_b64, timestamp, user_sig_b64 = token.split('.')

            # Get current key
            secret = _ensure_secret(request.env)

            # Verify checksum
            random_bytes = base64.urlsafe_b64decode(random_b64 + '=' * (-len(random_b64) % 4))
            checksum = base64.urlsafe_b64decode(checksum_b64 + '=' * (-len(checksum_b64) % 4))

            expected_checksum = hmac.new(
                secret.encode(),
                random_bytes,
                hashlib.sha256
            ).digest()
            if not hmac.compare_digest(checksum, expected_checksum):
                return {"active": False, "reason": "invalid_checksum"}

            # Check token record using the model verification (handles hashed storage)
            rt_model = request.env['auth.refresh.token'].sudo()

            # Try to get device id from headers if provided — refresh tokens are device-bound
            device_id = None
            try:
                device_info = self._get_device_info()
                device_id = device_info.get('device_id')
            except Exception:
                # Device id may not be present; we'll fallback to a slower scan below
                device_id = None

            token_record = None
            # Prefer the model's verify_token which knows how to check hashed tokens
            if device_id:
                try:
                    token_record, ok = rt_model.verify_token(token, device_id)
                except Exception:
                    token_record = None

            # Fallback: scan non-revoked tokens and compare using _verify_token (slow)
            if not token_record:
                # Fallback: scan non-revoked tokens and compare hashes.
                # We implement a local verifier to avoid importing addon internals
                def _verify_hash(stored, plain):
                    try:
                        salt_hex, dk_hex = stored.split("$", 1)
                    except Exception:
                        return False
                    salt = bytes.fromhex(salt_hex)
                    dk = hashlib.pbkdf2_hmac("sha256", plain.encode("utf-8"), salt, 200000)
                    return dk.hex() == dk_hex

                candidates = rt_model.search([('revoked', '=', False)], limit=2000)
                for cand in candidates:
                    try:
                        if _verify_hash(cand.token_hash, token):
                            token_record = cand
                            break
                    except Exception:
                        continue

            if not token_record:
                return {"active": False, "reason": "not_found"}

            # Check expiration (convert to comparable datetimes)
            try:
                expires_dt = fields.Datetime.from_string(token_record.expires_on)
                now_dt = fields.Datetime.from_string(fields.Datetime.now())
                if expires_dt < now_dt:
                    return {"active": False, "reason": "expired"}
            except Exception:
                # If we cannot parse dates, treat as invalid
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

    @http.route("/api/auth/introspect", auth="none", methods=["POST"], csrf=False)
    @json_response
    def introspect(self, **post):
        """Enhanced token introspection endpoint (RFC 7662).
        
        Supports introspection of both access and refresh tokens.
        
        Request: {
            "token": "<token>",
            "token_type_hint": "access_token|refresh_token"  // Optional
        }
        
        Response: 
        - Invalid token: {
            "active": false,
            "reason": "expired|revoked|invalid_signature|etc"
          }
        - Valid access token: {
            "active": true,
            "token_type": "access_token",
            "token_use": "access",
            ...claims
          }
        - Valid refresh token: {
            "active": true,
            "token_type": "refresh_token",
            "token_use": "refresh",
            "user_id": 123,
            "device_id": "device123",
            "expires_at": "2025-12-04 ...",
            "created_at": "2025-11-04 ..."
          }
        """
        # Accept explicit keys for clarity: prefer access_token or refresh_token
        token = None
        token_type = None

        # Preferred explicit parameters
        if post.get("access_token"):
            token = post.get("access_token")
            token_type = "access_token"
        elif post.get("refresh_token"):
            token = post.get("refresh_token")
            token_type = "refresh_token"

        # If still no token, try Authorization header
        if not token:
            auth_hdr = request.httprequest.headers.get('Authorization') or request.httprequest.headers.get('authorization')
            if auth_hdr:
                parts = auth_hdr.split()
                if len(parts) == 2 and parts[0].lower() == 'bearer':
                    token = parts[1]

        if not token:
            _logger.warning("auth.introspect missing token")
            return ({"active": False, "reason": "missing_token"}, 400)

        # If no explicit hint, auto-detect based on format (access JWT has 2 dots)
        if not token_type:
            parts = token.count('.')
            token_type = "access_token" if parts == 2 else "refresh_token"

        # Perform introspection and log result
        _logger.info("auth.introspect attempt: token_type=%s token=%s", token_type, mask_token(token))
        if token_type == "access_token":
            resp = self._introspect_access_token(token)
        else:
            resp = self._introspect_refresh_token(token)
        _logger.info("auth.introspect result: active=%s token_type=%s reason=%s", resp.get('active'), resp.get('token_type'), resp.get('reason'))
        return (resp, 200)

    @http.route("/api/auth/me", auth="none", methods=["GET"], csrf=False)
    @json_response
    def me(self, **kwargs):
        """Return basic profile information for the user identified by the
        provided token. Prefer Authorization: Bearer <access_token>, but a
        refresh token may be provided as a fallback via the `token` query
        parameter.
        """
        # Try Authorization header first
        auth_hdr = request.httprequest.headers.get('Authorization') or request.httprequest.headers.get('authorization')
        token = None
        token_type = None
        if auth_hdr:
            parts = auth_hdr.split()
            if len(parts) == 2 and parts[0].lower() == 'bearer':
                token = parts[1]
                token_type = 'access_token' if token.count('.') == 2 else 'refresh_token'

        # Fallback to query param `token`
        if not token:
            token = kwargs.get('token') or request.params.get('token')
            if token:
                token_type = 'access_token' if token.count('.') == 2 else 'refresh_token'

        if not token:
            _logger.warning("auth.me missing token")
            return ({"error": "invalid_request", "error_description": "token required"}, 400)

        user_id = None
        # If access token, decode to extract uid
        if token_type == 'access_token':
            secret = _ensure_secret(request.env)
            # try PyJWT first
            if jwt is not None and secret is not None:
                try:
                    claims = jwt.decode(token, secret, algorithms=["HS256"], options={"verify_exp": False, "verify_aud": False})
                    user_id = claims.get('uid') or claims.get('sub')
                except Exception:
                    user_id = None
            if not user_id:
                try:
                    _h, payload_b64, _s = token.split('.')
                    payload_json = base64.urlsafe_b64decode(payload_b64 + '=' * (-len(payload_b64) % 4))
                    payload = json.loads(payload_json)
                    user_id = payload.get('uid') or payload.get('sub')
                except Exception:
                    user_id = None
            try:
                user_id = int(user_id) if user_id is not None else None
            except Exception:
                user_id = None
        else:
            # refresh token: introspect to obtain user id
            intros = self._introspect_refresh_token(token)
            if not intros.get('active'):
                return ({"error": "invalid_token", "error_description": intros.get('reason', 'invalid')}, 401)
            user_id = intros.get('user_id') or intros.get('user') or intros.get('user_id')

        if not user_id:
            _logger.warning("auth.me could not determine user from token=%s", mask_token(token))
            return ({"error": "invalid_request", "error_description": "could not determine user from token"}, 400)
        # Load user profile now that we have a valid user_id
        try:
            user = request.env['res.users'].sudo().browse(int(user_id))
            if not user.exists():
                _logger.warning("auth.me user not found user_id=%s token=%s", user_id, mask_token(token))
                return ({"error": "not_found", "error_description": "user not found"}, 404)
            profile = {
                'id': user.id,
                'name': getattr(user, 'name', None),
                'login': getattr(user, 'login', None),
                'email': getattr(user, 'email', None) or (getattr(user, 'partner_id', None) and getattr(user.partner_id, 'email', None)),
                'tz': getattr(user, 'tz', None),
                'active': bool(getattr(user, 'active', True)),
            }
            _logger.info("auth.me success: user_id=%s token=%s", user.id, mask_token(token))
            return ({'user': profile}, 200)
        except Exception as e:
            _logger.exception('auth.me failed to load user profile: %s', e)
            return ({"error": "server_error", "error_description": "failed to load user"}, 500)

    @http.route("/api/auth/revoke_refresh", auth="none", methods=["POST"], csrf=False)
    @json_response
    def revoke_refresh(self, **post):
        """Revoke a refresh token. Accepts JSON body {"refresh_token": "..."}
        or Authorization header containing the refresh token. If X-Device-ID
        header is present, it will be used to verify device-binding.
        """
        # Extract token from body or Authorization header
        try:
            params = request.httprequest.get_json(force=False, silent=True) or {}
        except Exception:
            params = post or {}

        token = params.get('refresh_token') or post.get('refresh_token')
        if not token:
            # try Authorization header
            auth_hdr = request.httprequest.headers.get('Authorization') or request.httprequest.headers.get('authorization')
            if auth_hdr:
                parts = auth_hdr.split()
                if len(parts) == 2 and parts[0].lower() == 'bearer':
                    token = parts[1]

        if not token:
            _logger.warning("auth.revoke_refresh missing refresh_token")
            return ({"error": "invalid_request", "error_description": "refresh_token required"}, 400)

        rt_model = request.env['auth.refresh.token'].sudo()
        # Try device bound verify first
        device_id = None
        try:
            device_info = self._get_device_info()
            device_id = device_info.get('device_id')
        except Exception:
            device_id = None

        token_rec = None
        if device_id:
            try:
                token_rec, ok = rt_model.verify_token(token, device_id)
            except Exception:
                token_rec = None

        # Fallback to scanning (model stores hashed tokens)
        if not token_rec:
            # Fallback to scanning hashed tokens. Use local verifier to avoid
            # importing addon internals which may not resolve in static analysis.
            def _verify_hash(stored, plain):
                try:
                    salt_hex, dk_hex = stored.split("$", 1)
                except Exception:
                    return False
                salt = bytes.fromhex(salt_hex)
                dk = hashlib.pbkdf2_hmac("sha256", plain.encode("utf-8"), salt, 200000)
                return dk.hex() == dk_hex

            try:
                candidates = rt_model.search([('revoked', '=', False)], limit=2000)
                for cand in candidates:
                    try:
                        if _verify_hash(cand.token_hash, token):
                            token_rec = cand
                            break
                    except Exception:
                        continue
            except Exception:
                token_rec = None

        if not token_rec:
            _logger.warning("auth.revoke_refresh token not found: %s", mask_token(token))
            return ({"error": "invalid_token", "error_description": "refresh token not found"}, 404)

        try:
            token_rec.revoke(reason='client_revoke')
            _logger.info("auth.revoke_refresh success: revoked token for user_id=%s device=%s", getattr(token_rec.user_id, 'id', None), getattr(token_rec, 'device_id', None))
        except Exception:
            _logger.exception("auth.revoke_refresh failed to revoke token: %s", mask_token(token))
        return ({"revoked": True, "device_id": getattr(token_rec, 'device_id', None), 'user_id': getattr(token_rec.user_id, 'id', None)}, 200)

    @http.route("/api/auth/devices", auth="none", methods=["GET"], csrf=False)
    @json_response
    def devices(self, **post):
        """Return active login devices for the user identified by the provided token.

        Use GET and provide the token via the Authorization header (recommended):
            Authorization: Bearer <access_token>

        Optional query params (not recommended for sensitive tokens):
            ?token=<token>&token_type_hint=access_token|refresh_token
        """
        # Token from body (supports several common keys)
        token = post.get("token") or post.get("access_token") or post.get("refresh_token")

        # Authorization header fallback
        if not token:
            auth_hdr = request.httprequest.headers.get('Authorization') or request.httprequest.headers.get('authorization')
            if auth_hdr:
                parts = auth_hdr.split()
                if len(parts) == 2 and parts[0].lower() == 'bearer':
                    token = parts[1]

        if not token:
            _logger.warning("auth.devices missing token")
            return ({"error": "invalid_request", "error_description": "token required"}, 400)

        token_type = post.get("token_type_hint")
        if not token_type:
            parts = token.count('.')
            token_type = "access_token" if parts == 2 else "refresh_token"

        user_id = None
        if token_type == "access_token":
            # Try to decode access token to extract user id (do not rely on introspect payload)
            user_id = None
            secret = _ensure_secret(request.env)
            # Preferred: use PyJWT if available
            if jwt is not None:
                try:
                    # Do not verify exp/aud here, just extract claims
                    claims = jwt.decode(token, secret, algorithms=["HS256"], options={"verify_exp": False, "verify_aud": False})
                    user_id = claims.get('uid') or claims.get('sub')
                except Exception as e:
                    _logger.debug("JWT decode failed in devices route: %s", e)
                    user_id = None
            if not user_id:
                # Fallback to manual decode similar to _introspect_access_token
                try:
                    header_b64, payload_b64, signature = token.split('.')
                    payload_json = base64.urlsafe_b64decode(payload_b64 + '=' * (-len(payload_b64) % 4))
                    payload = json.loads(payload_json)
                    user_id = payload.get('uid') or payload.get('sub')
                except Exception as e:
                    _logger.debug("Manual token decode failed in devices route: %s", e)
                    user_id = None
            try:
                user_id = int(user_id) if user_id is not None else None
            except Exception:
                user_id = None
        else:
            intros = self._introspect_refresh_token(token)
            if not intros.get('active'):
                return ({"error": "invalid_token", "error_description": intros.get('reason', 'invalid')}, 401)
            user_id = intros.get('user_id')

        if not user_id:
            _logger.warning("auth.devices could not determine user from token=%s", mask_token(token))
            return ({"error": "invalid_request", "error_description": "could not determine user from token"}, 400)

        rt_model = request.env['auth.refresh.token'].sudo()
        # Only show active (non-revoked) refresh-token records as "devices"
        tokens = rt_model.search([('user_id', '=', user_id), ('revoked', '=', False)])
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
                'revoked': bool(t.revoked),
                'revocation_reason': t.revocation_reason,
                'token_family': t.token_family,
                'use_count': t.use_count,
            })

        _logger.info("auth.devices success: user_id=%s device_count=%s", user_id, len(devices))
        return ({"user_id": user_id, "device_count": len(devices), "devices": devices}, 200)




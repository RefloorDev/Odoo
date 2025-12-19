import base64
import json
import logging

from odoo import http, fields
from odoo.http import request

from .base import json_response, _ensure_secret, mask_token
from .auth import PitchApiAuthController

try:
    import jwt
except Exception:
    jwt = None

_logger = logging.getLogger(__name__)


class PitchApiUsersController(http.Controller):
    """Users API endpoints (admin-only)."""

    # --- Helpers ---------------------------------------------------------
    def _extract_bearer_token(self):
        auth_hdr = request.httprequest.headers.get('Authorization') or request.httprequest.headers.get('authorization')
        if not auth_hdr:
            _logger.warning("users._extract_bearer_token: missing Authorization header from %s", request.httprequest.remote_addr)
            return None, ({"error": "invalid_request", "error_description": "Authorization header with bearer token required"}, 400)
        parts = auth_hdr.split()
        if len(parts) != 2 or parts[0].lower() != 'bearer':
            _logger.warning("users._extract_bearer_token: malformed Authorization header from %s: %s", request.httprequest.remote_addr, auth_hdr)
            return None, ({"error": "invalid_request", "error_description": "Authorization header must be 'Bearer <token>'"}, 400)
        try:
            _logger.debug("users._extract_bearer_token: token provided from %s token=%s", request.httprequest.remote_addr, mask_token(parts[1]))
        except Exception:
            pass
        return parts[1], None

    def _resolve_user_from_access_token(self, token):
        if not token or token.count('.') != 2:
            _logger.warning("users._resolve_user_from_access_token: invalid token format from %s", request.httprequest.remote_addr)
            return None, ({"error": "invalid_request", "error_description": "access token (JWT) required in Authorization header"}, 400)

        auth_ctrl = PitchApiAuthController()
        intros = auth_ctrl._introspect_access_token(token)
        if not intros.get('active'):
            _logger.warning("users._resolve_user_from_access_token: introspect failed reason=%s from %s", intros.get('reason', 'invalid'), request.httprequest.remote_addr)
            return None, ({"error": "invalid_token", "error_description": intros.get('reason', 'invalid')}, 401)

        try:
            secret = _ensure_secret(request.env)
        except Exception:
            secret = None

        uid = None
        if jwt is not None and secret is not None:
            try:
                claims = jwt.decode(token, secret, algorithms=["HS256"], options={"verify_exp": False, "verify_aud": False})
                uid = claims.get('uid') or claims.get('sub')
            except Exception:
                uid = None

        if uid is None:
            try:
                _h, payload_b64, _s = token.split('.')
                payload_json = base64.urlsafe_b64decode(payload_b64 + '=' * (-len(payload_b64) % 4))
                payload = json.loads(payload_json)
                uid = payload.get('uid') or payload.get('sub')
            except Exception:
                uid = None

        try:
            uid = int(uid) if uid is not None else None
        except Exception:
            uid = None

        if not uid:
            _logger.warning("users._resolve_user_from_access_token: could not determine uid from token from %s", request.httprequest.remote_addr)
            return None, ({"error": "invalid_request", "error_description": "could not determine user from token"}, 400)
        return uid, None

    def _fmt_datetime(self, dt):
        try:
            return fields.Datetime.to_string(dt) if dt else None
        except Exception:
            return str(dt) if dt else None

    def _serialize_user(self, user):
        try:
            company_id = getattr(user.company_id, 'id', None) if getattr(user, 'company_id', None) else None
            company_name = getattr(user.company_id, 'name', None) if getattr(user, 'company_id', None) else None
        except Exception:
            company_id = None
            company_name = None

        return {
            'id': user.id,
            'name': getattr(user, 'name', None),
            'login': getattr(user, 'login', None),
            'active': bool(getattr(user, 'active', True)),
            'tz': getattr(user, 'tz', None),
            'company_id': company_id,
            'company_name': company_name,
            'login_date': self._fmt_datetime(getattr(user, 'login_date', None)),
            'is_pitch_admin': bool(getattr(user, 'is_pitch_admin', False)),
            'improveit_user_id': getattr(user, 'improveit_user_id', None),
        }

    def _serialize_user_groups(self, user):
        """Serialize user groups with detailed info."""
        groups_out = []
        try:
            groups = getattr(user, 'groups_id', []) or []
            xml_map = {}
            try:
                xml_map = groups.get_external_id()
            except Exception:
                xml_map = {}
            for g in groups:
                try:
                    groups_out.append({
                        'id': getattr(g, 'id', None),
                        'name': getattr(g, 'name', None),
                        'xml_id': xml_map.get(g.id),
                        'category_id': getattr(g.category_id, 'id', None) if getattr(g, 'category_id', None) else None,
                        'category_name': getattr(g.category_id, 'name', None) if getattr(g, 'category_id', None) else None,
                    })
                except Exception:
                    continue
        except Exception:
            groups_out = []
        return groups_out

    # --- Routes ----------------------------------------------------------
    @http.route("/api/users", auth="none", methods=["GET"], csrf=False)
    @json_response
    def list_users(self, **kwargs):
        """List all users (admin-only).

        Security:
        - Requires a valid Bearer access token in Authorization header.
        - The requesting user must be a Pitch API Admin (is_pitch_admin=True).

        Query params (optional):
        - active: 'true'|'false'|'all' (default 'all')
          - 'true': only active users
          - 'false': only inactive users
          - 'all': both active and inactive users
        """
        token, err = self._extract_bearer_token()
        if err:
            return err
        uid, err = self._resolve_user_from_access_token(token)
        if err:
            return err

        admin_user = request.env['res.users'].sudo().browse(uid)
        if not getattr(admin_user, 'is_pitch_admin', False):
            _logger.warning("users.list_users: forbidden for user_id=%s (not pitch admin)", uid)
            return ({"error": "forbidden", "error_description": "Pitch API admin required"}, 403)

        active_param = kwargs.get('active') or request.params.get('active')
        
        user_model = request.env['res.users'].sudo()
        domain = []
        
        if active_param is not None:
            active_param = active_param.strip().lower()
            if active_param in ('true', '1', 'yes'):
                domain.append(('active', '=', True))
            elif active_param in ('false', '0', 'no'):
                domain.append(('active', '=', False))
            else:
                # If active param provided but not true/false, get both
                user_model = user_model.with_context(active_test=False)
        else:
            # No active param provided - get all users (active and inactive)
            user_model = user_model.with_context(active_test=False)
        
        users = user_model.search(domain, order='id asc')
        data = [self._serialize_user(u) for u in users]

        return ({
            'admin_user_id': uid,
            'count': len(data),
            'active_filter': active_param if active_param else 'all',
            'users': data,
        }, 200)

    @http.route("/api/users/<int:user_id>", auth="none", methods=["GET"], csrf=False)
    @json_response
    def get_user_by_id(self, user_id, **kwargs):
        """Get a single user's info by id (admin-only)."""
        token, err = self._extract_bearer_token()
        if err:
            return err
        uid, err = self._resolve_user_from_access_token(token)
        if err:
            return err

        admin_user = request.env['res.users'].sudo().browse(uid)
        if not getattr(admin_user, 'is_pitch_admin', False):
            return ({"error": "forbidden", "error_description": "Pitch API admin required"}, 403)

        user = request.env['res.users'].sudo().browse(user_id)
        if not user.exists():
            return ({"error": "not_found", "error_description": "user not found"}, 404)
        return (self._serialize_user(user), 200)

    @http.route("/api/users/lookup", auth="none", methods=["GET"], csrf=False)
    @json_response
    def lookup_user(self, **kwargs):
        """Lookup a user by id or login (admin-only).

        Query params: user_id=<int> or login=<string>
        """
        token, err = self._extract_bearer_token()
        if err:
            return err
        uid, err = self._resolve_user_from_access_token(token)
        if err:
            return err

        admin_user = request.env['res.users'].sudo().browse(uid)
        if not getattr(admin_user, 'is_pitch_admin', False):
            return ({"error": "forbidden", "error_description": "Pitch API admin required"}, 403)

        user = None
        user_id_param = kwargs.get('user_id') or request.params.get('user_id')
        login_param = kwargs.get('login') or request.params.get('login')

        if user_id_param:
            try:
                user_id_val = int(user_id_param)
                usr = request.env['res.users'].sudo().browse(user_id_val)
                user = usr if usr.exists() else None
            except Exception:
                user = None
        elif login_param:
            user = request.env['res.users'].sudo().search([('login', '=', login_param)], limit=1)

        if not user:
            return ({"error": "not_found", "error_description": "user not found"}, 404)
        return (self._serialize_user(user), 200)

    @http.route("/api/users/exists", auth="none", methods=["GET"], csrf=False)
    @json_response
    def user_exists(self, **kwargs):
        """Check if a user exists (admin-only).

        Query params: user_id=<int> or login=<string>
        Returns: { exists: true|false }
        """
        token, err = self._extract_bearer_token()
        if err:
            return err
        uid, err = self._resolve_user_from_access_token(token)
        if err:
            return err

        admin_user = request.env['res.users'].sudo().browse(uid)
        if not getattr(admin_user, 'is_pitch_admin', False):
            return ({"error": "forbidden", "error_description": "Pitch API admin required"}, 403)

        user_id_param = kwargs.get('user_id') or request.params.get('user_id')
        login_param = kwargs.get('login') or request.params.get('login')

        exists = False
        if user_id_param:
            try:
                user_id_val = int(user_id_param)
                exists = request.env['res.users'].sudo().search_count([('id', '=', user_id_val)]) > 0
            except Exception:
                exists = False
        elif login_param:
            exists = request.env['res.users'].sudo().search_count([('login', '=', login_param)]) > 0
        else:
            return ({"error": "invalid_request", "error_description": "provide user_id or login"}, 400)

        return ({'exists': bool(exists)}, 200)

    @http.route("/api/users/<int:user_id>/groups", auth="none", methods=["GET"], csrf=False)
    @json_response
    def get_user_groups(self, user_id, **kwargs):
        """Get groups for a single user (admin-only).
        
        Returns detailed group information including XML IDs and categories.
        """
        token, err = self._extract_bearer_token()
        if err:
            return err
        uid, err = self._resolve_user_from_access_token(token)
        if err:
            return err

        admin_user = request.env['res.users'].sudo().browse(uid)
        if not getattr(admin_user, 'is_pitch_admin', False):
            return ({"error": "forbidden", "error_description": "Pitch API admin required"}, 403)

        user = request.env['res.users'].sudo().browse(user_id)
        if not user.exists():
            return ({"error": "not_found", "error_description": "user not found"}, 404)

        groups = self._serialize_user_groups(user)
        return ({
            'user_id': user.id,
            'user_login': user.login,
            'user_name': user.name,
            'groups_count': len(groups),
            'groups': groups,
        }, 200)

    @http.route("/api/users/groups", auth="none", methods=["GET"], csrf=False)
    @json_response
    def get_multiple_users_groups(self, **kwargs):
        """Get groups for multiple users (admin-only).
        
        Query params:
        - user_ids: comma-separated user IDs (e.g., "1,2,3")
        
        Returns groups information for each requested user.
        """
        token, err = self._extract_bearer_token()
        if err:
            return err
        uid, err = self._resolve_user_from_access_token(token)
        if err:
            return err

        admin_user = request.env['res.users'].sudo().browse(uid)
        if not getattr(admin_user, 'is_pitch_admin', False):
            return ({"error": "forbidden", "error_description": "Pitch API admin required"}, 403)

        user_ids_param = kwargs.get('user_ids') or request.params.get('user_ids')
        if not user_ids_param:
            return ({"error": "invalid_request", "error_description": "user_ids parameter required (comma-separated)"}, 400)

        try:
            user_ids = [int(uid_str.strip()) for uid_str in user_ids_param.split(',') if uid_str.strip()]
        except Exception:
            return ({"error": "invalid_request", "error_description": "user_ids must be comma-separated integers"}, 400)

        if not user_ids:
            return ({"error": "invalid_request", "error_description": "at least one user_id required"}, 400)

        users = request.env['res.users'].sudo().browse(user_ids)
        result = []
        for user in users:
            if user.exists():
                groups = self._serialize_user_groups(user)
                result.append({
                    'user_id': user.id,
                    'user_login': user.login,
                    'user_name': user.name,
                    'groups_count': len(groups),
                    'groups': groups,
                })

        return ({
            'count': len(result),
            'users': result,
        }, 200)

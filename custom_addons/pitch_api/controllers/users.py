# -*- coding: utf-8 -*-
"""Users API Controller.

Provides REST API endpoints for user management (admin-only).

Endpoints:
    GET /api/users                      - List all users
    GET /api/users/<id>                 - Get user by ID
    GET /api/users/lookup               - Lookup user by ID or login
    GET /api/users/exists               - Check if user exists
    GET /api/users/<id>/groups          - Get groups for a user
    GET /api/users/groups               - Get groups for multiple users
"""

import logging

from odoo import http, fields
from odoo.http import request

from .base import json_response
from .mixins import AuthenticationMixin

_logger = logging.getLogger(__name__)


class UsersController(http.Controller, AuthenticationMixin):
    """REST API controller for user management endpoints.

    All endpoints require a valid Bearer token (JWT) in the Authorization header
    and the authenticated user must have `is_pitch_admin=True`.
    """

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _format_datetime(self, dt):
        """Format datetime to string."""
        try:
            return fields.Datetime.to_string(dt) if dt else None
        except (TypeError, ValueError) as e:
            _logger.debug("Failed to format datetime: %s", e)
            return str(dt) if dt else None

    def _serialize_user(self, user):
        """Serialize a user record to a dictionary."""
        try:
            company_id = getattr(user.company_id, 'id', None) if getattr(user, 'company_id', None) else None
            company_name = getattr(user.company_id, 'name', None) if getattr(user, 'company_id', None) else None
        except (AttributeError, TypeError) as e:
            _logger.debug("Failed to serialize user company: %s", e)
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
            'login_date': self._format_datetime(getattr(user, 'login_date', None)),
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
            except AttributeError:
                xml_map = {}
            except Exception as e:
                _logger.debug("Failed to get external IDs for groups: %s", e)
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
                except (AttributeError, TypeError) as e:
                    _logger.debug("Failed to serialize group %s: %s", getattr(g, 'id', 'unknown'), e)
                    continue
        except Exception as e:
            _logger.debug("Failed to serialize user groups: %s", e)
            groups_out = []
        return groups_out

    # =========================================================================
    # List Users
    # =========================================================================

    @http.route("/api/users", auth="none", methods=["GET"], csrf=False)
    @json_response
    def list_users(self, **kwargs):
        """List all users (admin-only).

        Query params (optional):
            active: 'true'|'false'|'all' (default: 'all')
                - 'true': only active users
                - 'false': only inactive users
                - 'all': both active and inactive users
        """
        _logger.info("Users.list: from=%s", request.httprequest.remote_addr)

        # Authenticate admin
        admin_user_id, err = self._authenticate_admin()
        if err:
            return err

        # Parse active filter
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
                user_model = user_model.with_context(active_test=False)
        else:
            user_model = user_model.with_context(active_test=False)

        # Query users
        users = user_model.search(domain, order='id asc')
        data = [self._serialize_user(u) for u in users]

        _logger.info("Users.list: count=%s admin_user_id=%s", len(data), admin_user_id)

        return ({
            'admin_user_id': admin_user_id,
            'count': len(data),
            'active_filter': active_param if active_param else 'all',
            'users': data,
        }, 200)

    # =========================================================================
    # Get User by ID
    # =========================================================================

    @http.route("/api/users/<int:user_id>", auth="none", methods=["GET"], csrf=False)
    @json_response
    def get_user(self, user_id, **kwargs):
        """Get a single user by ID (admin-only)."""
        _logger.info("Users.get: user_id=%s from=%s", user_id, request.httprequest.remote_addr)

        # Authenticate admin
        admin_user_id, err = self._authenticate_admin()
        if err:
            return err

        # Load user
        user = request.env['res.users'].sudo().browse(user_id)
        if not user.exists():
            _logger.warning("Users.get: Not found user_id=%s admin_user_id=%s", user_id, admin_user_id)
            return ({"error": "not_found", "error_description": "user not found"}, 404)

        _logger.info("Users.get: Success user_id=%s admin_user_id=%s", user_id, admin_user_id)
        return (self._serialize_user(user), 200)

    # =========================================================================
    # Lookup User
    # =========================================================================

    @http.route("/api/users/lookup", auth="none", methods=["GET"], csrf=False)
    @json_response
    def lookup_user(self, **kwargs):
        """Lookup a user by ID or login (admin-only).

        Query params: user_id=<int> or login=<string>
        """
        _logger.info("Users.lookup: from=%s", request.httprequest.remote_addr)

        # Authenticate admin
        admin_user_id, err = self._authenticate_admin()
        if err:
            return err

        # Parse lookup parameters
        user_id_param = kwargs.get('user_id') or request.params.get('user_id')
        login_param = kwargs.get('login') or request.params.get('login')

        user = None
        if user_id_param:
            try:
                user_id_val = int(user_id_param)
                usr = request.env['res.users'].sudo().browse(user_id_val)
                user = usr if usr.exists() else None
            except (ValueError, TypeError) as e:
                _logger.debug("Invalid user_id parameter: %s", e)
                user = None
        elif login_param:
            user = request.env['res.users'].sudo().search([('login', '=', login_param)], limit=1)

        if not user:
            _logger.warning("Users.lookup: Not found admin_user_id=%s", admin_user_id)
            return ({"error": "not_found", "error_description": "user not found"}, 404)

        _logger.info("Users.lookup: Found user_id=%s admin_user_id=%s", user.id, admin_user_id)
        return (self._serialize_user(user), 200)

    # =========================================================================
    # Check User Exists
    # =========================================================================

    @http.route("/api/users/exists", auth="none", methods=["GET"], csrf=False)
    @json_response
    def user_exists(self, **kwargs):
        """Check if a user exists (admin-only).

        Query params: user_id=<int> or login=<string>
        Returns: { exists: true|false }
        """
        _logger.info("Users.exists: from=%s", request.httprequest.remote_addr)

        # Authenticate admin
        admin_user_id, err = self._authenticate_admin()
        if err:
            return err

        # Parse lookup parameters
        user_id_param = kwargs.get('user_id') or request.params.get('user_id')
        login_param = kwargs.get('login') or request.params.get('login')

        if not user_id_param and not login_param:
            return ({"error": "invalid_request", "error_description": "provide user_id or login"}, 400)

        exists = False
        if user_id_param:
            try:
                user_id_val = int(user_id_param)
                exists = request.env['res.users'].sudo().search_count([('id', '=', user_id_val)]) > 0
            except (ValueError, TypeError) as e:
                _logger.debug("Invalid user_id for exists check: %s", e)
                exists = False
        elif login_param:
            exists = request.env['res.users'].sudo().search_count([('login', '=', login_param)]) > 0

        _logger.info("Users.exists: exists=%s admin_user_id=%s", exists, admin_user_id)
        return ({'exists': bool(exists)}, 200)

    # =========================================================================
    # User Groups
    # =========================================================================

    @http.route("/api/users/<int:user_id>/groups", auth="none", methods=["GET"], csrf=False)
    @json_response
    def get_user_groups(self, user_id, **kwargs):
        """Get groups for a single user (admin-only).

        Returns detailed group information including XML IDs and categories.
        """
        _logger.info("Users.groups: user_id=%s from=%s", user_id, request.httprequest.remote_addr)

        # Authenticate admin
        admin_user_id, err = self._authenticate_admin()
        if err:
            return err

        # Load user
        user = request.env['res.users'].sudo().browse(user_id)
        if not user.exists():
            _logger.warning("Users.groups: Not found user_id=%s admin_user_id=%s", user_id, admin_user_id)
            return ({"error": "not_found", "error_description": "user not found"}, 404)

        groups = self._serialize_user_groups(user)

        _logger.info("Users.groups: user_id=%s groups=%s admin_user_id=%s", user_id, len(groups), admin_user_id)
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
            user_ids: comma-separated user IDs (e.g., "1,2,3")

        Returns groups information for each requested user.
        """
        _logger.info("Users.groups_multi: from=%s", request.httprequest.remote_addr)

        # Authenticate admin
        admin_user_id, err = self._authenticate_admin()
        if err:
            return err

        # Parse user_ids parameter
        user_ids_param = kwargs.get('user_ids') or request.params.get('user_ids')
        if not user_ids_param:
            return ({"error": "invalid_request", "error_description": "user_ids parameter required (comma-separated)"}, 400)

        try:
            user_ids = [int(uid_str.strip()) for uid_str in user_ids_param.split(',') if uid_str.strip()]
        except (ValueError, TypeError) as e:
            _logger.debug("Failed to parse user_ids: %s", e)
            return ({"error": "invalid_request", "error_description": "user_ids must be comma-separated integers"}, 400)

        if not user_ids:
            return ({"error": "invalid_request", "error_description": "at least one user_id required"}, 400)

        # Query users and serialize groups
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

        _logger.info("Users.groups_multi: count=%s admin_user_id=%s", len(result), admin_user_id)
        return ({
            'count': len(result),
            'users': result,
        }, 200)

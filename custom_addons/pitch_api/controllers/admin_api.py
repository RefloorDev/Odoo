# -*- coding: utf-8 -*-
"""Admin API controller for Pitch API.

Provides admin-only endpoints for fetching appointments and related data.
These routes are restricted to users with `is_pitch_admin=True`.
"""

import logging
from datetime import datetime, time, timezone

from odoo import http, fields
from odoo.http import request

from .base import json_response, _ensure_secret, mask_token
from .auth import PitchApiAuthController
from .api import PitchApiController

try:
    import jwt
except Exception:
    jwt = None

try:
    import pytz
except Exception:
    pytz = None

_logger = logging.getLogger(__name__)


class PitchAdminApiController(http.Controller):
    """Admin API controller for Pitch API endpoints.

    All endpoints require a valid access token (Bearer token) and the
    authenticated user must have `is_pitch_admin=True`.

    Routes:
    - GET /api/admin/appointments - List all appointments with filters
    - GET /api/admin/appointments/today - Today's appointments
    - GET /api/admin/appointments/<id> - Single appointment by ID
    - GET /api/admin/market-segments - List all distinct market segments
    """

    # --- Helpers ---------------------------------------------------------

    def _get_base_controller(self):
        """Return an instance of the base PitchApiController for reusing methods."""
        return PitchApiController()

    def _extract_bearer_token(self):
        """Return (token, None) or (None, error_dict)."""
        return self._get_base_controller()._extract_bearer_token()

    def _resolve_user_from_access_token(self, token):
        """Verify access token and extract user id (int).

        Returns (uid, None) on success or (None, error_dict) on failure.
        """
        return self._get_base_controller()._resolve_user_from_access_token(token)

    def _serialize_appointment(self, appt):
        """Serialize an appointment record to a dict."""
        return self._get_base_controller()._serialize_appointment(appt)

    def _fmt_datetime(self, dt):
        """Format datetime to string."""
        return self._get_base_controller()._fmt_datetime(dt)

    def _verify_admin(self, user_id):
        """Verify that the user is a pitch admin.

        Returns (True, None) if admin, (False, error_response) otherwise.
        """
        try:
            user = request.env['res.users'].sudo().browse(user_id)
            if not user.exists():
                _logger.warning("admin_api._verify_admin: user not found user_id=%s", user_id)
                return False, ({"error": "invalid_token", "error_description": "user not found"}, 401)

            if not user.is_pitch_admin:
                _logger.warning("admin_api._verify_admin: user is not admin user_id=%s", user_id)
                return False, ({"error": "forbidden", "error_description": "admin access required"}, 403)

            return True, None
        except Exception as e:
            _logger.exception("admin_api._verify_admin: error checking admin status user_id=%s", user_id)
            return False, ({"error": "server_error", "error_description": str(e)}, 500)

    def _authenticate_admin(self):
        """Extract token, resolve user, and verify admin status.

        Returns (user_id, None) on success or (None, error_response) on failure.
        """
        token, err = self._extract_bearer_token()
        if err:
            return None, err

        user_id, err = self._resolve_user_from_access_token(token)
        if err:
            return None, err

        is_admin, err = self._verify_admin(user_id)
        if not is_admin:
            return None, err

        return user_id, None

    def _parse_filters(self, kwargs):
        """Parse filter parameters from request.

        Returns a dict with parsed filter values.
        """
        filters = {}

        # Timezone filter (for date conversions)
        tz_name = kwargs.get('tz') or request.params.get('tz') or 'UTC'
        filters['tz'] = tz_name

        # Market segment filter (text, comma-separated for multiple)
        market_segment = kwargs.get('market_segment') or request.params.get('market_segment')
        if market_segment:
            # Split by comma and strip whitespace
            segments = [s.strip() for s in market_segment.split(',') if s.strip()]
            filters['market_segment'] = segments if len(segments) > 1 else segments[0] if segments else None
            _logger.info("admin_api._parse_filters: market_segment input=%s, parsed=%s, type=%s", 
                        market_segment, filters.get('market_segment'), type(filters.get('market_segment')))

        # User ID / Salesperson filter (integer)
        user_id_param = kwargs.get('user_id') or request.params.get('user_id')
        if user_id_param:
            try:
                filters['user_id'] = int(user_id_param)
            except (ValueError, TypeError):
                pass

        # Date filters - store as date or datetime objects, will be converted to UTC in _build_domain
        # Accepts: YYYY-MM-DD or YYYY-MM-DD HH:MM:SS
        date_from = kwargs.get('date_from') or request.params.get('date_from')
        if date_from:
            try:
                # Try datetime format first (YYYY-MM-DD HH:MM:SS)
                filters['date_from'] = datetime.strptime(date_from, '%Y-%m-%d %H:%M:%S')
                filters['date_from_is_datetime'] = True
            except (ValueError, TypeError):
                try:
                    # Fallback to date format (YYYY-MM-DD)
                    filters['date_from'] = datetime.strptime(date_from, '%Y-%m-%d').date()
                    filters['date_from_is_datetime'] = False
                except (ValueError, TypeError):
                    pass

        date_to = kwargs.get('date_to') or request.params.get('date_to')
        if date_to:
            try:
                # Try datetime format first (YYYY-MM-DD HH:MM:SS)
                filters['date_to'] = datetime.strptime(date_to, '%Y-%m-%d %H:%M:%S')
                filters['date_to_is_datetime'] = True
            except (ValueError, TypeError):
                try:
                    # Fallback to date format (YYYY-MM-DD)
                    filters['date_to'] = datetime.strptime(date_to, '%Y-%m-%d').date()
                    filters['date_to_is_datetime'] = False
                except (ValueError, TypeError):
                    pass

        # Filter logic (and/or)
        filter_logic = kwargs.get('filter_logic') or request.params.get('filter_logic') or 'and'
        filters['filter_logic'] = filter_logic.lower() if filter_logic in ('and', 'or', 'AND', 'OR') else 'and'

        return filters

    def _convert_local_datetime_to_utc(self, local_dt_or_date, tz_name, start_of_day=True, is_datetime=False):
        """Convert a local date or datetime to UTC datetime string.

        Args:
            local_dt_or_date: date or datetime object in local timezone
            tz_name: IANA timezone string (e.g. 'America/Chicago')
            start_of_day: If True and input is date, use start of day (00:00:00), else end of day (23:59:59)
            is_datetime: If True, input is a datetime (use exact time); if False, input is a date

        Returns:
            UTC datetime string suitable for Odoo domain
        """
        try:
            if pytz is not None:
                tz = pytz.timezone(tz_name)
                if is_datetime:
                    # Input is datetime - use exact time, localize to timezone
                    local_dt = tz.localize(local_dt_or_date)
                else:
                    # Input is date - use start or end of day
                    if start_of_day:
                        local_dt = datetime.combine(local_dt_or_date, time.min)
                    else:
                        local_dt = datetime.combine(local_dt_or_date, time.max)
                    local_dt = tz.localize(local_dt)
                utc_dt = local_dt.astimezone(pytz.UTC)
            else:
                # Fallback: assume UTC
                if is_datetime:
                    utc_dt = local_dt_or_date.replace(tzinfo=timezone.utc)
                else:
                    if start_of_day:
                        utc_dt = datetime.combine(local_dt_or_date, time.min).replace(tzinfo=timezone.utc)
                    else:
                        utc_dt = datetime.combine(local_dt_or_date, time.max).replace(tzinfo=timezone.utc)
        except Exception:
            # On error, fallback to UTC
            if is_datetime:
                utc_dt = local_dt_or_date.replace(tzinfo=timezone.utc) if hasattr(local_dt_or_date, 'hour') else datetime.combine(local_dt_or_date, time.min).replace(tzinfo=timezone.utc)
            else:
                if start_of_day:
                    utc_dt = datetime.combine(local_dt_or_date, time.min).replace(tzinfo=timezone.utc)
                else:
                    utc_dt = datetime.combine(local_dt_or_date, time.max).replace(tzinfo=timezone.utc)

        return fields.Datetime.to_string(utc_dt)

    def _build_domain(self, filters):
        """Build Odoo domain from parsed filters.

        Returns a domain list based on filter_logic (AND or OR).
        Dates/datetimes are converted from local timezone to UTC for comparison.
        """
        conditions = []
        tz_name = filters.get('tz', 'UTC')

        if filters.get('market_segment'):
            market_seg = filters['market_segment']
            if isinstance(market_seg, list):
                # Multiple market segments - create case-insensitive IN condition
                # Normalize to proper case by getting all segments and matching
                _logger.info("admin_api._build_domain: multiple market_segments filter=%s", market_seg)
                # Get all possible market segments and find case-insensitive matches
                appt_model = request.env['team.customer.appointment'].sudo()
                all_segments_records = appt_model.read_group(
                    domain=[('market_segment', '!=', False)],
                    fields=['market_segment'],
                    groupby=['market_segment'],
                )
                all_segments = {g['market_segment'].lower(): g['market_segment'] 
                               for g in all_segments_records if g.get('market_segment')}
                
                # Match input segments (case-insensitive) to actual DB values
                matched_segments = []
                for seg in market_seg:
                    seg_lower = seg.lower()
                    if seg_lower in all_segments:
                        matched_segments.append(all_segments[seg_lower])
               
                if matched_segments:
                    if len(matched_segments) == 1:
                        conditions.append(('market_segment', '=', matched_segments[0]))
                    else:
                        segment_conditions = [('market_segment', '=', seg) for seg in matched_segments]
                        conditions.append(('_market_segments_or', segment_conditions))
                else:
                    # No valid segments found - add impossible condition to return 0 results
                    _logger.warning("admin_api._build_domain: no valid market_segments found in %s", market_seg)
                    conditions.append(('market_segment', '=', '__INVALID_SEGMENT_NO_MATCH__'))
            else:
                # Single market segment - case-insensitive exact match
                _logger.info("admin_api._build_domain: single market_segment filter=%s", market_seg)
                # Get all market segments and find case-insensitive match
                appt_model = request.env['team.customer.appointment'].sudo()
                all_segments_records = appt_model.read_group(
                    domain=[('market_segment', '!=', False)],
                    fields=['market_segment'],
                    groupby=['market_segment'],
                )
                all_segments = {g['market_segment'].lower(): g['market_segment'] 
                               for g in all_segments_records if g.get('market_segment')}
                
                seg_lower = market_seg.lower()
                if seg_lower in all_segments:
                    conditions.append(('market_segment', '=', all_segments[seg_lower]))
                else:
                    # Invalid segment - add impossible condition to return 0 results
                    _logger.warning("admin_api._build_domain: invalid market_segment=%s not found", market_seg)
                    conditions.append(('market_segment', '=', '__INVALID_SEGMENT_NO_MATCH__'))

        if filters.get('user_id'):
            conditions.append(('user_id', '=', filters['user_id']))

        if filters.get('date_from'):
            # Convert local date/datetime to UTC
            is_datetime = filters.get('date_from_is_datetime', False)
            date_from_utc = self._convert_local_datetime_to_utc(
                filters['date_from'], tz_name, start_of_day=True, is_datetime=is_datetime
            )
            conditions.append(('appointment_date', '>=', date_from_utc))

        if filters.get('date_to'):
            # Convert local date/datetime to UTC
            is_datetime = filters.get('date_to_is_datetime', False)
            date_to_utc = self._convert_local_datetime_to_utc(
                filters['date_to'], tz_name, start_of_day=False, is_datetime=is_datetime
            )
            conditions.append(('appointment_date', '<=', date_to_utc))

        if not conditions:
            return []

        # Build domain based on filter logic
        # First, handle special market_segments OR condition if present
        final_conditions = []
        market_seg_or = None
        
        for cond in conditions:
            if isinstance(cond, tuple) and cond[0] == '_market_segments_or':
                market_seg_or = cond[1]  # Extract the OR conditions
            else:
                final_conditions.append(cond)
        
        # If we have market segment OR conditions, we need to structure the domain carefully
        if market_seg_or:
            # Build OR domain for market segments
            if len(market_seg_or) == 1:
                final_conditions.insert(0, market_seg_or[0])
            else:
                market_seg_domain = ['|'] * (len(market_seg_or) - 1) + market_seg_or
                # If filter_logic is AND and we have other conditions
                if filters.get('filter_logic') == 'and' and final_conditions:
                    # All conditions must be met: (market_seg1 OR market_seg2 OR ...) AND other_conditions
                    # We need to flatten: ['&', market_seg_domain..., other_condition]
                    # For each additional condition, we need an '&'
                    result_domain = []
                    # Add '&' operators: we need (len(final_conditions) - 1) + 1 = len(final_conditions)
                    # because we're ANDing market_seg_domain with all final_conditions
                    result_domain.extend(['&'] * len(final_conditions))
                    result_domain.extend(market_seg_domain)
                    result_domain.extend(final_conditions)
                    return result_domain
                elif filters.get('filter_logic') == 'or' and final_conditions:
                    # Any condition can be met: combine everything with OR
                    all_conditions = market_seg_or + final_conditions
                    return ['|'] * (len(all_conditions) - 1) + all_conditions
                else:
                    # Only market segment conditions
                    return market_seg_domain
        
        if not final_conditions:
            return []
        
        # Build domain based on filter logic
        if filters.get('filter_logic') == 'or' and len(final_conditions) > 1:
            # OR logic: use | operator
            domain = ['|'] * (len(final_conditions) - 1) + final_conditions
        else:
            # AND logic (default): just concatenate conditions
            domain = final_conditions

        return domain

    def _parse_pagination(self, kwargs):
        """Parse pagination parameters.

        Returns (page, per_page) if pagination requested, (None, None) otherwise.
        """
        page_param = kwargs.get('page') or request.params.get('page')
        per_page_param = kwargs.get('per_page') or request.params.get('per_page')

        # If neither page nor per_page provided, no pagination
        if page_param is None and per_page_param is None:
            return None, None

        try:
            page = int(page_param) if page_param else 1
        except (ValueError, TypeError):
            page = 1
        if page < 1:
            page = 1

        try:
            per_page = int(per_page_param) if per_page_param else 100
        except (ValueError, TypeError):
            per_page = 100
        if per_page < 1:
            per_page = 100

        return page, per_page

    def _build_filters_response(self, filters):
        """Build filters metadata for response."""
        result = {}
        if filters.get('tz'):
            result['tz'] = filters['tz']
        if filters.get('market_segment'):
            market_seg = filters['market_segment']
            result['market_segment'] = market_seg if isinstance(market_seg, list) else market_seg
        if filters.get('user_id'):
            result['user_id'] = filters['user_id']
        if filters.get('date_from'):
            result['date_from'] = str(filters['date_from'])
        if filters.get('date_to'):
            result['date_to'] = str(filters['date_to'])
        if filters.get('filter_logic'):
            result['filter_logic'] = filters['filter_logic']
        return result

    # --- Routes -----------------------------------------------------------

    @http.route("/api/admin/appointments", auth="none", methods=["GET"], csrf=False)
    @json_response
    def admin_list_appointments(self, **kwargs):
        """List all appointments with optional filters.

        Admin-only endpoint. Returns all appointments matching filters.
        If pagination params (page, per_page) are provided, returns paginated results.

        Query params:
        - tz: IANA timezone string (e.g. 'America/Chicago'). Used for date/datetime conversions. Defaults to UTC.
        - market_segment: Filter by market segment (text, case-insensitive)
        - user_id: Filter by salesperson/user ID (integer)
        - date_from: Filter appointments from this date/datetime. Formats accepted:
            - YYYY-MM-DD (uses start of day 00:00:00 in specified tz)
            - YYYY-MM-DD HH:MM:SS (uses exact time in specified tz)
        - date_to: Filter appointments until this date/datetime. Formats accepted:
            - YYYY-MM-DD (uses end of day 23:59:59 in specified tz)
            - YYYY-MM-DD HH:MM:SS (uses exact time in specified tz)
        - filter_logic: 'and' (default) or 'or' for combining filters
        - page: Page number (1-based) for pagination
        - per_page: Items per page (default 100)
        """
        _logger.info("admin_api.admin_list_appointments called from=%s", request.httprequest.remote_addr)

        # Authenticate admin
        admin_user_id, err = self._authenticate_admin()
        if err:
            return err

        # Parse filters
        filters = self._parse_filters(kwargs)
        domain = self._build_domain(filters)

        # Parse pagination
        page, per_page = self._parse_pagination(kwargs)

        appt_model = request.env['team.customer.appointment'].sudo()

        if page is not None:
            # Paginated mode
            offset = (page - 1) * per_page
            total = appt_model.search_count(domain)
            recs = appt_model.search(domain, limit=per_page, offset=offset, order='appointment_date desc')
            data = [self._serialize_appointment(r) for r in recs]

            _logger.info("admin_api.admin_list_appointments: returning page %s (%s of %s) for admin_user_id=%s",
                         page, len(data), total, admin_user_id)

            return ({
                'admin_user_id': admin_user_id,
                'page': page,
                'per_page': per_page,
                'total': total,
                'count': len(data),
                'filters': self._build_filters_response(filters),
                'appointments': data,
            }, 200)
        else:
            # All results (no limit)
            recs = appt_model.search(domain, order='appointment_date desc')
            data = [self._serialize_appointment(r) for r in recs]

            _logger.info("admin_api.admin_list_appointments: returning %s appointments for admin_user_id=%s",
                         len(data), admin_user_id)

            return ({
                'admin_user_id': admin_user_id,
                'count': len(data),
                'filters': self._build_filters_response(filters),
                'appointments': data,
            }, 200)

    @http.route("/api/admin/appointments/today", auth="none", methods=["GET"], csrf=False)
    @json_response
    def admin_list_todays_appointments(self, **kwargs):
        """List today's appointments with optional filters.

        Admin-only endpoint. Returns appointments whose `appointment_date`
        falls within 'today' in the specified timezone.

        Query params:
        - tz: IANA timezone string (e.g. 'America/Chicago'). Used to determine 'today' and for date conversions. Defaults to UTC.
        - market_segment: Filter by market segment (text)
        - user_id: Filter by salesperson/user ID (integer)
        - filter_logic: 'and' (default) or 'or' for combining filters
        - page: Page number for pagination
        - per_page: Items per page
        """
        _logger.info("admin_api.admin_list_todays_appointments called from=%s", request.httprequest.remote_addr)

        # Authenticate admin
        admin_user_id, err = self._authenticate_admin()
        if err:
            return err

        # Determine timezone
        tz_name = kwargs.get('tz') or request.params.get('tz') or 'UTC'

        # Compute day start/end in UTC from local tz
        try:
            if pytz is not None:
                tz = pytz.timezone(tz_name)
                now_local = datetime.now(tz)
                local_date = now_local.date()
                start_local = datetime.combine(local_date, time.min).replace(tzinfo=tz)
                end_local = datetime.combine(local_date, time.max).replace(tzinfo=tz)
                start_utc = start_local.astimezone(pytz.UTC)
                end_utc = end_local.astimezone(pytz.UTC)
            else:
                now_utc = datetime.now(tz=timezone.utc)
                local_date = now_utc.date()
                start_utc = datetime.combine(local_date, time.min).replace(tzinfo=timezone.utc)
                end_utc = datetime.combine(local_date, time.max).replace(tzinfo=timezone.utc)
        except Exception:
            now_utc = datetime.now(tz=timezone.utc)
            local_date = now_utc.date()
            start_utc = datetime.combine(local_date, time.min).replace(tzinfo=timezone.utc)
            end_utc = datetime.combine(local_date, time.max).replace(tzinfo=timezone.utc)
            tz_name = 'UTC'

        start_str = fields.Datetime.to_string(start_utc)
        end_str = fields.Datetime.to_string(end_utc)

        # Parse additional filters (excluding date_from/date_to as we use today)
        filters = self._parse_filters(kwargs)
        # Remove date filters as we're using today's date
        filters.pop('date_from', None)
        filters.pop('date_to', None)

        # Build base domain for today
        date_domain = [('appointment_date', '>=', start_str), ('appointment_date', '<=', end_str)]

        # Build additional filter domain
        additional_domain = self._build_domain(filters)

        # Combine domains
        if filters.get('filter_logic') == 'or' and additional_domain:
            # For OR logic, we still need date constraint as AND with OR of other filters
            # (date is required, other filters are optional)
            domain = date_domain + additional_domain
        else:
            domain = date_domain + additional_domain

        # Parse pagination
        page, per_page = self._parse_pagination(kwargs)

        appt_model = request.env['team.customer.appointment'].sudo()

        if page is not None:
            offset = (page - 1) * per_page
            total = appt_model.search_count(domain)
            recs = appt_model.search(domain, limit=per_page, offset=offset, order='appointment_date asc')
            data = [self._serialize_appointment(r) for r in recs]

            _logger.info("admin_api.admin_list_todays_appointments: returning page %s (%s of %s) for admin_user_id=%s",
                         page, len(data), total, admin_user_id)

            return ({
                'admin_user_id': admin_user_id,
                'tz': tz_name,
                'date': str(local_date),
                'page': page,
                'per_page': per_page,
                'total': total,
                'count': len(data),
                'filters': self._build_filters_response(filters),
                'appointments': data,
            }, 200)
        else:
            recs = appt_model.search(domain, order='appointment_date asc')
            data = [self._serialize_appointment(r) for r in recs]

            _logger.info("admin_api.admin_list_todays_appointments: returning %s appointments for admin_user_id=%s",
                         len(data), admin_user_id)

            return ({
                'admin_user_id': admin_user_id,
                'tz': tz_name,
                'date': str(local_date),
                'count': len(data),
                'filters': self._build_filters_response(filters),
                'appointments': data,
            }, 200)

    @http.route("/api/admin/appointments/<int:appointment_id>", auth="none", methods=["GET"], csrf=False)
    @json_response
    def admin_get_appointment(self, appointment_id, **kwargs):
        """Get a single appointment by ID.

        Admin-only endpoint. Returns any appointment regardless of ownership.
        """
        _logger.info("admin_api.admin_get_appointment called: appointment_id=%s from=%s",
                     appointment_id, request.httprequest.remote_addr)

        # Authenticate admin
        admin_user_id, err = self._authenticate_admin()
        if err:
            return err

        # Load the appointment
        appt_model = request.env['team.customer.appointment'].sudo()
        appt = appt_model.browse(appointment_id)

        if not appt.exists():
            _logger.warning("admin_api.admin_get_appointment: appointment not found id=%s admin_user_id=%s",
                            appointment_id, admin_user_id)
            return ({"error": "not_found", "error_description": "appointment not found"}, 404)

        _logger.info("admin_api.admin_get_appointment: success appointment_id=%s admin_user_id=%s",
                     appointment_id, admin_user_id)

        return ({
            'admin_user_id': admin_user_id,
            'appointment': self._serialize_appointment(appt),
        }, 200)

    @http.route("/api/admin/appointments/<int:appointment_id>/app_screen_logs", auth="none", methods=["GET"], csrf=False)
    @json_response
    def admin_get_appointment_app_screen_logs(self, appointment_id, **kwargs):
        """Return the app screen log lines for a given appointment.

        Admin-only endpoint. Returns app screen logs for any appointment
        regardless of ownership.
        """
        _logger.info("admin_api.admin_get_appointment_app_screen_logs called: appointment_id=%s from=%s",
                     appointment_id, request.httprequest.remote_addr)

        # Authenticate admin
        admin_user_id, err = self._authenticate_admin()
        if err:
            return err

        # Load the appointment
        appt_model = request.env['team.customer.appointment'].sudo()
        appt = appt_model.browse(appointment_id)

        if not appt.exists():
            _logger.warning("admin_api.admin_get_appointment_app_screen_logs: appointment not found id=%s admin_user_id=%s",
                            appointment_id, admin_user_id)
            return ({"error": "not_found", "error_description": "appointment not found"}, 404)

        # Gather app screen logs
        logs = getattr(appt, 'app_screen_log_line', []) or []
        out = []
        for log in logs:
            try:
                out.append({
                    'id': getattr(log, 'id', None),
                    'name': getattr(log, 'name', None),
                    'completion_date': self._fmt_datetime(getattr(log, 'completion_date', None)),
                    'user_id': getattr(log.user_id, 'id', None) if hasattr(log, 'user_id') else None,
                })
            except Exception:
                # best-effort: skip malformed entries
                continue

        _logger.info("admin_api.admin_get_appointment_app_screen_logs: success appointment_id=%s admin_user_id=%s logs_count=%s",
                     appointment_id, admin_user_id, len(out))

        return ({
            'admin_user_id': admin_user_id,
            'appointment_id': appointment_id,
            'count': len(out),
            'app_screen_logs': out,
        }, 200)

    @http.route("/api/admin/appointments/<int:appointment_id>/app_live_screen_logs", auth="none", methods=["GET"], csrf=False)
    @json_response
    def admin_get_appointment_app_live_screen_logs(self, appointment_id, **kwargs):
        """Return the app live screen log lines for a given appointment.

        Admin-only endpoint. Returns app live screen logs for any appointment
        regardless of ownership.
        """
        _logger.info("admin_api.admin_get_appointment_app_live_screen_logs called: appointment_id=%s from=%s",
                     appointment_id, request.httprequest.remote_addr)

        # Authenticate admin
        admin_user_id, err = self._authenticate_admin()
        if err:
            return err

        # Load the appointment
        appt_model = request.env['team.customer.appointment'].sudo()
        appt = appt_model.browse(appointment_id)

        if not appt.exists():
            _logger.warning("admin_api.admin_get_appointment_app_live_screen_logs: appointment not found id=%s admin_user_id=%s",
                            appointment_id, admin_user_id)
            return ({"error": "not_found", "error_description": "appointment not found"}, 404)

        # Gather app live screen logs
        logs = getattr(appt, 'app_live_screen_log_line', []) or []
        out = []
        for log in logs:
            try:
                out.append({
                    'id': getattr(log, 'id', None),
                    'name': getattr(log, 'name', None),
                    'screen_entry_date': self._fmt_datetime(getattr(log, 'screen_entry_date', None)),
                    'user_id': getattr(log.user_id, 'id', None) if hasattr(log, 'user_id') else None,
                })
            except Exception:
                # best-effort: skip malformed entries
                continue

        _logger.info("admin_api.admin_get_appointment_app_live_screen_logs: success appointment_id=%s admin_user_id=%s logs_count=%s",
                     appointment_id, admin_user_id, len(out))

        return ({
            'admin_user_id': admin_user_id,
            'appointment_id': appointment_id,
            'count': len(out),
            'app_live_screen_logs': out,
        }, 200)

    @http.route("/api/admin/market-segments", auth="none", methods=["GET"], csrf=False)
    @json_response
    def admin_list_market_segments(self, **kwargs):
        """List all distinct market segment values.

        Admin-only endpoint. Returns unique market segment values from all appointments.
        
        Query params:
        - user_id: (optional) Filter market segments by salesperson/user ID (integer)
                   When provided, returns only market segments that have appointments assigned to this user
        """
        _logger.info("admin_api.admin_list_market_segments called from=%s", request.httprequest.remote_addr)

        # Authenticate admin
        admin_user_id, err = self._authenticate_admin()
        if err:
            return err

        # Parse optional user_id filter
        user_id_param = kwargs.get('user_id') or request.params.get('user_id')
        filter_user_id = None
        if user_id_param:
            try:
                filter_user_id = int(user_id_param)
                _logger.info("admin_api.admin_list_market_segments: filtering by user_id=%s", filter_user_id)
            except (ValueError, TypeError):
                _logger.warning("admin_api.admin_list_market_segments: invalid user_id format: %s", user_id_param)

        # Query distinct market segments
        appt_model = request.env['team.customer.appointment'].sudo()

        # Build domain with optional user_id filter
        domain = [('market_segment', '!=', False)]
        if filter_user_id:
            domain.append(('user_id', '=', filter_user_id))

        # Use read_group to get distinct values efficiently
        try:
            groups = appt_model.read_group(
                domain=domain,
                fields=['market_segment'],
                groupby=['market_segment'],
            )
            segments = [g['market_segment'] for g in groups if g.get('market_segment')]
            # Sort alphabetically
            segments.sort()
        except Exception as e:
            _logger.exception("admin_api.admin_list_market_segments: error querying market segments")
            # Fallback: fetch all and dedupe in Python
            try:
                all_appts = appt_model.search(domain)
                segments = list(set(appt.market_segment for appt in all_appts if appt.market_segment))
                segments.sort()
            except Exception:
                segments = []

        _logger.info("admin_api.admin_list_market_segments: returning %s segments for admin_user_id=%s, filter_user_id=%s",
                     len(segments), admin_user_id, filter_user_id)

        # Build response
        response_data = {}
        
        # Include user_id filter in response if provided
        if filter_user_id:
            response_data['user_id'] = filter_user_id
        
        response_data['count'] = len(segments)
        response_data['market_segments'] = segments

        return (response_data, 200)

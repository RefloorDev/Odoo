# -*- coding: utf-8 -*-
"""Admin Appointments API Controller.

Provides REST API endpoints for appointments accessible only to admin users.
Admins can access all appointments regardless of ownership.

Endpoints:
    GET /api/admin/appointments                              - List all appointments with filters
    GET /api/admin/appointments/today                        - Today's appointments
    GET /api/admin/appointments/<id>                         - Single appointment by ID
    GET /api/admin/appointments/<id>/app_screen_logs         - Screen logs for appointment
    GET /api/admin/appointments/<id>/app_live_screen_logs    - Live screen logs for appointment
    GET /api/admin/market-segments                           - List all distinct market segments
"""

import logging
from datetime import datetime, time, timezone

from odoo import http, fields
from odoo.http import request

from .base import json_response
from .mixins import (
    AuthenticationMixin,
    AppointmentSerializerMixin,
    PaginationMixin,
    FilterMixin,
    VALID_APPOINTMENT_STATUSES,
    VALID_ORDER_OPTIONS,
    DEFAULT_ORDER,
    DEFAULT_PER_PAGE,
    MAX_PER_PAGE,
)

try:
    import pytz
except ImportError:
    pytz = None

_logger = logging.getLogger(__name__)


class AdminAppointmentsController(
    http.Controller,
    AuthenticationMixin,
    AppointmentSerializerMixin,
    PaginationMixin,
    FilterMixin
):
    """REST API controller for admin appointment endpoints.

    All endpoints require a valid Bearer token (JWT) in the Authorization header
    and the authenticated user must have `is_pitch_admin=True`.

    Admins can access all appointments regardless of ownership.
    """

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _parse_admin_filters(self, kwargs):
        """Parse all filter parameters for admin endpoints.

        Returns a dict with parsed filter values.
        """
        filters = {}

        # Timezone
        filters['tz'] = kwargs.get('tz') or request.params.get('tz') or 'UTC'

        # Market segment (comma-separated for multiple)
        market_segment = kwargs.get('market_segment') or request.params.get('market_segment')
        if market_segment:
            segments = [s.strip() for s in market_segment.split(',') if s.strip()]
            filters['market_segment'] = segments if len(segments) > 1 else (segments[0] if segments else None)
            _logger.debug("AdminAppointments: market_segment=%s", filters.get('market_segment'))

        # User ID filter
        user_id_param = kwargs.get('user_id') or request.params.get('user_id')
        if user_id_param:
            try:
                filters['user_id'] = int(user_id_param)
            except (ValueError, TypeError):
                pass

        # Improveit User ID filter (Salesforce ID) - only used if user_id not provided
        if not filters.get('user_id'):
            improveit_user_id_param = kwargs.get('improveit_user_id') or request.params.get('improveit_user_id')
            if improveit_user_id_param:
                filters['improveit_user_id'] = improveit_user_id_param.strip()
                _logger.debug("AdminAppointments: improveit_user_id=%s", filters.get('improveit_user_id'))

        # Date filters
        date_from = kwargs.get('date_from') or request.params.get('date_from')
        if date_from:
            try:
                filters['date_from'] = datetime.strptime(date_from, '%Y-%m-%d %H:%M:%S')
                filters['date_from_is_datetime'] = True
            except (ValueError, TypeError):
                try:
                    filters['date_from'] = datetime.strptime(date_from, '%Y-%m-%d').date()
                    filters['date_from_is_datetime'] = False
                except (ValueError, TypeError):
                    pass

        date_to = kwargs.get('date_to') or request.params.get('date_to')
        if date_to:
            try:
                filters['date_to'] = datetime.strptime(date_to, '%Y-%m-%d %H:%M:%S')
                filters['date_to_is_datetime'] = True
            except (ValueError, TypeError):
                try:
                    filters['date_to'] = datetime.strptime(date_to, '%Y-%m-%d').date()
                    filters['date_to_is_datetime'] = False
                except (ValueError, TypeError):
                    pass

        # Status filter
        status_param = kwargs.get('status') or request.params.get('status')
        if status_param is not None:
            status_param = status_param.strip() if status_param else ''
            if status_param:
                status_lower = status_param.lower()
                if status_lower in VALID_APPOINTMENT_STATUSES:
                    filters['status'] = status_lower
                else:
                    filters['status_invalid'] = status_param

        # Order filter
        order_param = kwargs.get('order') or request.params.get('order')
        if order_param:
            order_param = order_param.strip().lower()
            if order_param in VALID_ORDER_OPTIONS:
                filters['order'] = order_param
                filters['order_clause'] = VALID_ORDER_OPTIONS[order_param]
            else:
                filters['order_invalid'] = order_param
        else:
            filters['order'] = 'id_desc'
            filters['order_clause'] = DEFAULT_ORDER

        # Filter logic
        filter_logic = kwargs.get('filter_logic') or request.params.get('filter_logic') or 'and'
        filters['filter_logic'] = filter_logic.lower() if filter_logic in ('and', 'or', 'AND', 'OR') else 'and'

        return filters

    def _convert_local_to_utc(self, local_dt_or_date, tz_name, start_of_day=True, is_datetime=False):
        """Convert local date/datetime to UTC string for Odoo domain.

        Args:
            local_dt_or_date: date or datetime object in local timezone
            tz_name: IANA timezone string
            start_of_day: If True and date input, use 00:00:00; else 23:59:59
            is_datetime: If True, input is datetime with exact time

        Returns:
            str: UTC datetime string for Odoo domain
        """
        try:
            if pytz is not None:
                tz = pytz.timezone(tz_name)
                if is_datetime:
                    local_dt = tz.localize(local_dt_or_date)
                else:
                    time_val = time.min if start_of_day else time.max
                    local_dt = tz.localize(datetime.combine(local_dt_or_date, time_val))
                utc_dt = local_dt.astimezone(pytz.UTC)
            else:
                if is_datetime:
                    utc_dt = local_dt_or_date.replace(tzinfo=timezone.utc)
                else:
                    time_val = time.min if start_of_day else time.max
                    utc_dt = datetime.combine(local_dt_or_date, time_val).replace(tzinfo=timezone.utc)
        except Exception as e:
            _logger.debug("Failed to convert timezone %s: %s", tz_name, e)
            if is_datetime:
                utc_dt = local_dt_or_date.replace(tzinfo=timezone.utc) if hasattr(local_dt_or_date, 'hour') else \
                    datetime.combine(local_dt_or_date, time.min).replace(tzinfo=timezone.utc)
            else:
                time_val = time.min if start_of_day else time.max
                utc_dt = datetime.combine(local_dt_or_date, time_val).replace(tzinfo=timezone.utc)

        return fields.Datetime.to_string(utc_dt)

    def _build_domain(self, filters):
        """Build Odoo domain from parsed filters.

        Returns a domain list based on filter_logic (AND or OR).
        """
        conditions = []
        tz_name = filters.get('tz', 'UTC')

        # Market segment filter
        if filters.get('market_segment'):
            market_seg = filters['market_segment']
            if isinstance(market_seg, list):
                conditions.extend(self._build_market_segment_conditions(market_seg))
            else:
                conditions.extend(self._build_market_segment_conditions([market_seg]))

        # User ID filter
        if filters.get('user_id'):
            conditions.append(('user_id', '=', filters['user_id']))

        # Status filter
        if filters.get('status'):
            conditions.append(('state', '=', filters['status']))

        # Date from filter
        if filters.get('date_from'):
            date_from_utc = self._convert_local_to_utc(
                filters['date_from'], tz_name,
                start_of_day=True,
                is_datetime=filters.get('date_from_is_datetime', False)
            )
            conditions.append(('appointment_date', '>=', date_from_utc))

        # Date to filter
        if filters.get('date_to'):
            date_to_utc = self._convert_local_to_utc(
                filters['date_to'], tz_name,
                start_of_day=False,
                is_datetime=filters.get('date_to_is_datetime', False)
            )
            conditions.append(('appointment_date', '<=', date_to_utc))

        if not conditions:
            return []

        # Handle OR logic if needed
        return self._apply_filter_logic(conditions, filters.get('filter_logic', 'and'))

    def _build_market_segment_conditions(self, segments):
        """Build domain conditions for market segment filter.

        Performs case-insensitive matching against database values.
        """
        appt_model = request.env['team.customer.appointment'].sudo()

        # Get all market segments from DB for case-insensitive matching
        try:
            groups = appt_model.read_group(
                domain=[('market_segment', '!=', False)],
                fields=['market_segment'],
                groupby=['market_segment'],
            )
            all_segments = {g['market_segment'].lower(): g['market_segment']
                           for g in groups if g.get('market_segment')}
        except Exception as e:
            _logger.debug("Failed to load market segments: %s", e)
            all_segments = {}

        # Match input segments to actual DB values
        matched = []
        for seg in segments:
            seg_lower = seg.lower()
            if seg_lower in all_segments:
                matched.append(all_segments[seg_lower])

        if not matched:
            _logger.warning("AdminAppointments: No valid market segments in %s", segments)
            return [('market_segment', '=', '__INVALID_SEGMENT_NO_MATCH__')]

        if len(matched) == 1:
            return [('market_segment', '=', matched[0])]

        # Multiple segments - use OR
        return [('_market_segments_or', [(('market_segment', '=', seg)) for seg in matched])]

    def _apply_filter_logic(self, conditions, logic):
        """Apply AND/OR logic to domain conditions."""
        if not conditions:
            return []

        # Handle market segments OR separately
        final_conditions = []
        market_seg_or = None

        for cond in conditions:
            if isinstance(cond, tuple) and cond[0] == '_market_segments_or':
                market_seg_or = cond[1]
            else:
                final_conditions.append(cond)

        if market_seg_or:
            # Build OR domain for market segments
            if len(market_seg_or) == 1:
                market_domain = [market_seg_or[0]]
            else:
                market_domain = ['|'] * (len(market_seg_or) - 1) + list(market_seg_or)

            if logic == 'and' and final_conditions:
                result = ['&'] * len(final_conditions)
                result.extend(market_domain)
                result.extend(final_conditions)
                return result
            elif logic == 'or' and final_conditions:
                all_conds = list(market_seg_or) + final_conditions
                return ['|'] * (len(all_conds) - 1) + all_conds
            else:
                return market_domain

        if logic == 'or' and len(final_conditions) > 1:
            return ['|'] * (len(final_conditions) - 1) + final_conditions

        return final_conditions

    def _build_filters_response(self, filters):
        """Build filters metadata for response."""
        result = {}
        if filters.get('tz'):
            result['tz'] = filters['tz']
        if filters.get('market_segment'):
            result['market_segment'] = filters['market_segment']
        if filters.get('user_id'):
            result['user_id'] = filters['user_id']
        if filters.get('resolved_improveit_user_id'):
            result['improveit_user_id'] = filters['resolved_improveit_user_id']
        if filters.get('date_from'):
            result['date_from'] = str(filters['date_from'])
        if filters.get('date_to'):
            result['date_to'] = str(filters['date_to'])
        if filters.get('status'):
            result['status'] = filters['status']
        if filters.get('filter_logic'):
            result['filter_logic'] = filters['filter_logic']
        if filters.get('order'):
            result['order'] = filters['order']
        return result

    def _validate_filters(self, filters, admin_user_id, endpoint_name):
        """Validate parsed filters for invalid values.

        Returns None on success, or error response tuple on failure.
        """
        if filters.get('status_invalid'):
            _logger.warning(
                "%s: Invalid status '%s' from admin_user_id=%s",
                endpoint_name, filters['status_invalid'], admin_user_id
            )
            return ({
                "error": "invalid_request",
                "error_description": f"Invalid status value '{filters['status_invalid']}'. Allowed values: draft, scheduled, canceled, done"
            }, 400)

        if filters.get('order_invalid'):
            _logger.warning(
                "%s: Invalid order '%s' from admin_user_id=%s",
                endpoint_name, filters['order_invalid'], admin_user_id
            )
            return ({
                "error": "invalid_request",
                "error_description": f"Invalid order value '{filters['order_invalid']}'. Allowed values: id_desc, id_asc, date_desc, date_asc"
            }, 400)

        # Resolve improveit_user_id to user_id
        if filters.get('improveit_user_id'):
            improveit_id = filters['improveit_user_id']
            user = request.env['res.users'].sudo().search(
                [('improveit_user_id', '=', improveit_id)],
                limit=1
            )
            if not user:
                _logger.warning(
                    "%s: No user found with improveit_user_id='%s' from admin_user_id=%s",
                    endpoint_name, improveit_id, admin_user_id
                )
                return ({
                    "error": "user_not_found",
                    "error_description": f"No user found with improveit_user_id: {improveit_id}"
                }, 404)
            # Set user_id from resolved improveit_user_id
            filters['user_id'] = user.id
            filters['resolved_improveit_user_id'] = improveit_id
            _logger.debug(
                "%s: Resolved improveit_user_id='%s' to user_id=%s",
                endpoint_name, improveit_id, user.id
            )

        return None

    # =========================================================================
    # List Appointments
    # =========================================================================

    @http.route("/api/admin/appointments", auth="none", methods=["GET"], csrf=False)
    @json_response
    def list_appointments(self, **kwargs):
        """List all appointments with optional filters.

        Admin-only endpoint. Returns all appointments matching filters.

        Query params:
            tz: IANA timezone string (default: UTC)
            market_segment: Filter by market segment (comma-separated for multiple)
            user_id: Filter by salesperson/user ID (Odoo user ID)
            improveit_user_id: Filter by Salesforce user ID (used if user_id not provided)
            status: Filter by status (draft, scheduled, canceled, done)
            date_from: Filter from date (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)
            date_to: Filter to date (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)
            filter_logic: 'and' (default) or 'or'
            page: Page number (default: 1)
            per_page: Items per page (default: 200, max: 2000)
            order: Sort order (id_desc, id_asc, date_desc, date_asc)
        """
        _logger.info(
            "AdminAppointments.list: from=%s",
            request.httprequest.remote_addr
        )

        # Authenticate admin
        admin_user_id, err = self._authenticate_admin()
        if err:
            return err

        # Parse and validate filters
        filters = self._parse_admin_filters(kwargs)
        err = self._validate_filters(filters, admin_user_id, "AdminAppointments.list")
        if err:
            return err

        # Build domain and order
        domain = self._build_domain(filters)
        order_clause = filters.get('order_clause', DEFAULT_ORDER)

        # Parse pagination
        page, per_page, err = self._parse_pagination(kwargs)
        if err:
            return err

        # Query appointments
        appt_model = request.env['team.customer.appointment'].sudo()
        offset = self._calculate_offset(page, per_page)
        total = appt_model.search_count(domain)
        records = appt_model.search(domain, limit=per_page, offset=offset, order=order_clause)
        data = [self._serialize_appointment(rec) for rec in records]

        _logger.info(
            "AdminAppointments.list: page=%s count=%s/%s admin_user_id=%s",
            page, len(data), total, admin_user_id
        )

        return ({
            'admin_user_id': admin_user_id,
            'total': total,
            'count': len(data),
            'page': page,
            'per_page': per_page,
            'order': filters.get('order', 'id_desc'),
            'filters': self._build_filters_response(filters),
            'appointments': data,
        }, 200)

    # =========================================================================
    # Today's Appointments
    # =========================================================================

    @http.route("/api/admin/appointments/today", auth="none", methods=["GET"], csrf=False)
    @json_response
    def list_today_appointments(self, **kwargs):
        """List today's appointments with optional filters.

        Admin-only endpoint. Returns appointments for today in specified timezone.

        Query params:
            tz: IANA timezone string (default: UTC)
            market_segment: Filter by market segment (comma-separated for multiple)
            user_id: Filter by salesperson/user ID (Odoo user ID)
            improveit_user_id: Filter by Salesforce user ID (used if user_id not provided)
            status: Filter by status (draft, scheduled, canceled, done)
            filter_logic: 'and' (default) or 'or'
            page: Page number (default: 1)
            per_page: Items per page (default: 200, max: 2000)
            order: Sort order (id_desc, id_asc, date_desc, date_asc)
        """
        _logger.info(
            "AdminAppointments.today: from=%s",
            request.httprequest.remote_addr
        )

        # Authenticate admin
        admin_user_id, err = self._authenticate_admin()
        if err:
            return err

        # Parse and validate filters
        filters = self._parse_admin_filters(kwargs)
        err = self._validate_filters(filters, admin_user_id, "AdminAppointments.today")
        if err:
            return err

        order_clause = filters.get('order_clause', DEFAULT_ORDER)
        tz_name = filters.get('tz', 'UTC')

        # Get today's range in UTC
        start_str, end_str, local_date, tz_name = self._get_today_range_utc(tz_name)

        # Remove date filters (we use today's date)
        filters.pop('date_from', None)
        filters.pop('date_to', None)

        # Build domains
        date_domain = [('appointment_date', '>=', start_str), ('appointment_date', '<=', end_str)]
        additional_domain = self._build_domain(filters)
        domain = date_domain + additional_domain

        # Parse pagination
        page, per_page, err = self._parse_pagination(kwargs)
        if err:
            return err

        # Query appointments
        appt_model = request.env['team.customer.appointment'].sudo()
        offset = self._calculate_offset(page, per_page)
        total = appt_model.search_count(domain)
        records = appt_model.search(domain, limit=per_page, offset=offset, order=order_clause)
        data = [self._serialize_appointment(rec) for rec in records]

        _logger.info(
            "AdminAppointments.today: page=%s count=%s/%s admin_user_id=%s",
            page, len(data), total, admin_user_id
        )

        return ({
            'admin_user_id': admin_user_id,
            'tz': tz_name,
            'date': str(local_date),
            'total': total,
            'count': len(data),
            'page': page,
            'per_page': per_page,
            'order': filters.get('order', 'id_desc'),
            'filters': self._build_filters_response(filters),
            'appointments': data,
        }, 200)

    # =========================================================================
    # Single Appointment
    # =========================================================================

    @http.route("/api/admin/appointments/<int:appointment_id>", auth="none", methods=["GET"], csrf=False)
    @json_response
    def get_appointment(self, appointment_id, **kwargs):
        """Get a single appointment by ID.

        Admin-only endpoint. Returns any appointment regardless of ownership.
        """
        _logger.info(
            "AdminAppointments.get: id=%s from=%s",
            appointment_id, request.httprequest.remote_addr
        )

        # Authenticate admin
        admin_user_id, err = self._authenticate_admin()
        if err:
            return err

        # Load appointment
        appointment = request.env['team.customer.appointment'].sudo().browse(appointment_id)
        if not appointment.exists():
            _logger.warning(
                "AdminAppointments.get: Not found id=%s admin_user_id=%s",
                appointment_id, admin_user_id
            )
            return ({"error": "not_found", "error_description": "appointment not found"}, 404)

        _logger.info(
            "AdminAppointments.get: Success id=%s admin_user_id=%s",
            appointment_id, admin_user_id
        )

        return ({
            'admin_user_id': admin_user_id,
            'appointment': self._serialize_appointment(appointment),
        }, 200)

    # =========================================================================
    # Screen Logs
    # =========================================================================

    @http.route("/api/admin/appointments/<int:appointment_id>/app_screen_logs", auth="none", methods=["GET"], csrf=False)
    @json_response
    def get_screen_logs(self, appointment_id, **kwargs):
        """Get app screen logs for an appointment.

        Admin-only endpoint. Returns logs for any appointment.
        """
        _logger.info(
            "AdminAppointments.screen_logs: id=%s from=%s",
            appointment_id, request.httprequest.remote_addr
        )

        # Authenticate admin
        admin_user_id, err = self._authenticate_admin()
        if err:
            return err

        # Load appointment
        appointment = request.env['team.customer.appointment'].sudo().browse(appointment_id)
        if not appointment.exists():
            _logger.warning(
                "AdminAppointments.screen_logs: Not found id=%s admin_user_id=%s",
                appointment_id, admin_user_id
            )
            return ({"error": "not_found", "error_description": "appointment not found"}, 404)

        # Serialize logs
        logs = getattr(appointment, 'app_screen_log_line', []) or []
        data = []
        for log in logs:
            try:
                data.append(self._serialize_screen_log(log))
            except (AttributeError, TypeError) as e:
                _logger.debug("Failed to serialize screen log: %s", e)
                continue

        _logger.info(
            "AdminAppointments.screen_logs: Success id=%s admin_user_id=%s count=%s",
            appointment_id, admin_user_id, len(data)
        )

        return ({
            'admin_user_id': admin_user_id,
            'appointment_id': appointment_id,
            'count': len(data),
            'app_screen_logs': data,
        }, 200)

    @http.route("/api/admin/appointments/<int:appointment_id>/app_live_screen_logs", auth="none", methods=["GET"], csrf=False)
    @json_response
    def get_live_screen_logs(self, appointment_id, **kwargs):
        """Get app live screen logs for an appointment.

        Admin-only endpoint. Returns logs for any appointment.
        """
        _logger.info(
            "AdminAppointments.live_logs: id=%s from=%s",
            appointment_id, request.httprequest.remote_addr
        )

        # Authenticate admin
        admin_user_id, err = self._authenticate_admin()
        if err:
            return err

        # Load appointment
        appointment = request.env['team.customer.appointment'].sudo().browse(appointment_id)
        if not appointment.exists():
            _logger.warning(
                "AdminAppointments.live_logs: Not found id=%s admin_user_id=%s",
                appointment_id, admin_user_id
            )
            return ({"error": "not_found", "error_description": "appointment not found"}, 404)

        # Serialize logs
        logs = getattr(appointment, 'app_live_screen_log_line', []) or []
        data = []
        for log in logs:
            try:
                data.append(self._serialize_live_screen_log(log))
            except (AttributeError, TypeError) as e:
                _logger.debug("Failed to serialize live screen log: %s", e)
                continue

        _logger.info(
            "AdminAppointments.live_logs: Success id=%s admin_user_id=%s count=%s",
            appointment_id, admin_user_id, len(data)
        )

        return ({
            'admin_user_id': admin_user_id,
            'appointment_id': appointment_id,
            'count': len(data),
            'app_live_screen_logs': data,
        }, 200)

    # =========================================================================
    # Market Segments
    # =========================================================================

    @http.route("/api/admin/market-segments", auth="none", methods=["GET"], csrf=False)
    @json_response
    def list_market_segments(self, **kwargs):
        """List all distinct market segment values.

        Admin-only endpoint. Returns unique market segments from all appointments.

        Query params:
            user_id: (optional) Filter by salesperson/user ID
        """
        _logger.info(
            "AdminAppointments.market_segments: from=%s",
            request.httprequest.remote_addr
        )

        # Authenticate admin
        admin_user_id, err = self._authenticate_admin()
        if err:
            return err

        # Parse optional user_id filter
        filter_user_id = None
        user_id_param = kwargs.get('user_id') or request.params.get('user_id')
        if user_id_param:
            try:
                filter_user_id = int(user_id_param)
            except (ValueError, TypeError):
                _logger.warning(
                    "AdminAppointments.market_segments: Invalid user_id=%s",
                    user_id_param
                )

        # Build domain
        domain = [('market_segment', '!=', False)]
        if filter_user_id:
            domain.append(('user_id', '=', filter_user_id))

        # Query distinct market segments
        appt_model = request.env['team.customer.appointment'].sudo()
        try:
            groups = appt_model.read_group(
                domain=domain,
                fields=['market_segment'],
                groupby=['market_segment'],
            )
            segments = sorted([g['market_segment'] for g in groups if g.get('market_segment')])
        except Exception as e:
            _logger.debug("read_group failed for market_segments: %s", e)
            try:
                appointments = appt_model.search(domain)
                segments = sorted(set(a.market_segment for a in appointments if a.market_segment))
            except Exception as e2:
                _logger.debug("search fallback failed for market_segments: %s", e2)
                segments = []

        _logger.info(
            "AdminAppointments.market_segments: count=%s admin_user_id=%s filter_user_id=%s",
            len(segments), admin_user_id, filter_user_id
        )

        response = {'count': len(segments), 'market_segments': segments}
        if filter_user_id:
            response['user_id'] = filter_user_id

        return (response, 200)

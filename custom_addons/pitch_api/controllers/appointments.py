# -*- coding: utf-8 -*-
"""User Appointments API Controller.

Provides REST API endpoints for appointments accessible to authenticated users.
Users can only access their own appointments.

Endpoints:
    GET /api/appointments                              - List appointments with filters
    GET /api/appointments/today                        - Today's appointments
    GET /api/appointments/<id>                         - Single appointment by ID
    GET /api/appointments/<id>/app_screen_logs         - Screen logs for appointment
    GET /api/appointments/<id>/app_live_screen_logs    - Live screen logs for appointment
"""

import logging

from odoo import http
from odoo.http import request

from .base import json_response
from .mixins import (
    AuthenticationMixin,
    AppointmentSerializerMixin,
    PaginationMixin,
    FilterMixin,
    AppointmentAuthorizationMixin,
)

_logger = logging.getLogger(__name__)


class AppointmentsController(
    http.Controller,
    AuthenticationMixin,
    AppointmentSerializerMixin,
    PaginationMixin,
    FilterMixin,
    AppointmentAuthorizationMixin
):
    """REST API controller for user appointment endpoints.

    All endpoints require a valid Bearer token (JWT) in the Authorization header.
    Users can only access appointments where they are the owner or attendee.
    """

    # =========================================================================
    # Single Appointment
    # =========================================================================

    @http.route("/api/appointments/<int:appointment_id>", auth="none", methods=["GET"], csrf=False)
    @json_response
    def get_appointment(self, appointment_id, **kwargs):
        """Get a single appointment by ID.

        Args:
            appointment_id: ID of the appointment to retrieve.

        Returns:
            JSON response with appointment data or error.
        """
        _logger.info(
            "AppointmentsController.get: appointment_id=%s from=%s",
            appointment_id, request.httprequest.remote_addr
        )

        # Authenticate
        user_id, err = self._authenticate_user()
        if err:
            return err

        # Load appointment
        appointment = request.env['team.customer.appointment'].sudo().browse(appointment_id)
        if not appointment.exists():
            _logger.warning(
                "AppointmentsController.get: Not found id=%s user_id=%s",
                appointment_id, user_id
            )
            return ({"error": "not_found", "error_description": "appointment not found"}, 404)

        # Authorize
        if not self._user_can_access_appointment(user_id, appointment):
            _logger.warning(
                "AppointmentsController.get: Forbidden id=%s user_id=%s",
                appointment_id, user_id
            )
            return ({"error": "forbidden", "error_description": "user not authorized to view this appointment"}, 403)

        _logger.info(
            "AppointmentsController.get: Success id=%s user_id=%s",
            appointment_id, user_id
        )
        return (self._serialize_appointment(appointment), 200)

    # =========================================================================
    # List Appointments
    # =========================================================================

    @http.route("/api/appointments", auth="none", methods=["GET"], csrf=False)
    @json_response
    def list_appointments(self, **kwargs):
        """List appointments with filtering and pagination.

        Query Parameters:
            status: Filter by status (draft, scheduled, canceled, done)
            date_from: Filter from date (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)
            date_to: Filter to date (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)
            tz: Timezone for date conversion (default: user's tz or UTC)
            page: Page number (default: 1)
            per_page: Items per page (default: 200, max: 2000)
            order: Sort order (id_desc, id_asc, date_desc, date_asc)

        Returns:
            JSON response with paginated appointments or error.
        """
        _logger.info(
            "AppointmentsController.list: from=%s",
            request.httprequest.remote_addr
        )

        # Authenticate
        user_id, err = self._authenticate_user()
        if err:
            return err

        # Parse filters
        status_filter, err = self._parse_status_filter(kwargs, user_id)
        if err:
            return err

        order_key, order_clause, err = self._parse_order_filter(kwargs, user_id)
        if err:
            return err

        tz_name = self._parse_timezone(kwargs, user_id)

        # Parse date filters
        date_from_param = kwargs.get('date_from') or request.params.get('date_from')
        date_to_param = kwargs.get('date_to') or request.params.get('date_to')

        date_from_utc, err = self._parse_date_filter(
            date_from_param, tz_name, is_end_of_day=False,
            user_id=user_id, param_name='date_from'
        )
        if err:
            return err

        date_to_utc, err = self._parse_date_filter(
            date_to_param, tz_name, is_end_of_day=True,
            user_id=user_id, param_name='date_to'
        )
        if err:
            return err

        # Parse pagination
        page, per_page, err = self._parse_pagination(kwargs)
        if err:
            return err

        offset = self._calculate_offset(page, per_page)

        # Build domain
        domain = [('user_id', '=', user_id)]

        if status_filter:
            domain.append(('state', '=', status_filter))
        if date_from_utc:
            domain.append(('appointment_date', '>=', date_from_utc))
        if date_to_utc:
            domain.append(('appointment_date', '<=', date_to_utc))

        # Execute query
        appointment_model = request.env['team.customer.appointment'].sudo()

        try:
            total = appointment_model.search_count(domain)
            records = appointment_model.search(
                domain, limit=per_page, offset=offset, order=order_clause
            )
            appointments = [self._serialize_appointment(r) for r in records]
        except Exception as e:
            _logger.exception(
                "AppointmentsController.list: Database error user_id=%s: %s",
                user_id, e
            )
            return ({
                "error": "server_error",
                "error_description": "An error occurred while fetching appointments"
            }, 500)

        _logger.info(
            "AppointmentsController.list: Returning %s/%s for user_id=%s",
            len(appointments), total, user_id
        )

        # Build response
        response = {
            'user_id': user_id,
            'total': total,
            'count': len(appointments),
            'page': page,
            'per_page': per_page,
            'order': order_key,
        }

        # Add active filters
        filters = {}
        if status_filter:
            filters['status'] = status_filter
        if date_from_param:
            filters['date_from'] = date_from_param
        if date_to_param:
            filters['date_to'] = date_to_param
        if tz_name != 'UTC':
            filters['tz'] = tz_name
        if filters:
            response['filters'] = filters

        response['appointments'] = appointments
        return (response, 200)

    # =========================================================================
    # Today's Appointments
    # =========================================================================

    @http.route("/api/appointments/today", auth="none", methods=["GET"], csrf=False)
    @json_response
    def list_today_appointments(self, **kwargs):
        """List today's appointments with filtering and pagination.

        Query Parameters:
            status: Filter by status (draft, scheduled, canceled, done)
            tz: Timezone for determining 'today' (default: user's tz or UTC)
            page: Page number (default: 1)
            per_page: Items per page (default: 200, max: 2000)
            order: Sort order (id_desc, id_asc, date_desc, date_asc)

        Returns:
            JSON response with today's appointments or error.
        """
        _logger.info(
            "AppointmentsController.list_today: from=%s",
            request.httprequest.remote_addr
        )

        # Authenticate
        user_id, err = self._authenticate_user()
        if err:
            return err

        # Parse filters
        status_filter, err = self._parse_status_filter(kwargs, user_id)
        if err:
            return err

        order_key, order_clause, err = self._parse_order_filter(kwargs, user_id)
        if err:
            return err

        tz_name = self._parse_timezone(kwargs, user_id)

        # Parse pagination
        page, per_page, err = self._parse_pagination(kwargs)
        if err:
            return err

        offset = self._calculate_offset(page, per_page)

        # Get today's range
        start_utc, end_utc, local_date, tz_name = self._get_today_range_utc(tz_name)

        # Build domain
        domain = [
            ('user_id', '=', user_id),
            ('appointment_date', '>=', start_utc),
            ('appointment_date', '<=', end_utc),
        ]

        if status_filter:
            domain.append(('state', '=', status_filter))

        # Execute query
        appointment_model = request.env['team.customer.appointment'].sudo()

        try:
            total = appointment_model.search_count(domain)
            records = appointment_model.search(
                domain, limit=per_page, offset=offset, order=order_clause
            )
            appointments = [self._serialize_appointment(r) for r in records]
        except Exception as e:
            _logger.exception(
                "AppointmentsController.list_today: Database error user_id=%s: %s",
                user_id, e
            )
            return ({
                "error": "server_error",
                "error_description": "An error occurred while fetching appointments"
            }, 500)

        _logger.info(
            "AppointmentsController.list_today: Returning %s/%s for user_id=%s",
            len(appointments), total, user_id
        )

        # Build response
        response = {
            'user_id': user_id,
            'tz': tz_name,
            'date': str(local_date),
            'total': total,
            'count': len(appointments),
            'page': page,
            'per_page': per_page,
            'order': order_key,
        }

        # Add active filters
        if status_filter:
            response['filters'] = {'status': status_filter}

        response['appointments'] = appointments
        return (response, 200)

    # =========================================================================
    # Screen Logs
    # =========================================================================

    @http.route("/api/appointments/<int:appointment_id>/app_screen_logs", auth="none", methods=["GET"], csrf=False)
    @json_response
    def get_screen_logs(self, appointment_id, **kwargs):
        """Get screen logs for an appointment.

        Args:
            appointment_id: ID of the appointment.

        Returns:
            JSON response with screen logs or error.
        """
        _logger.info(
            "AppointmentsController.get_screen_logs: appointment_id=%s from=%s",
            appointment_id, request.httprequest.remote_addr
        )

        # Authenticate
        user_id, err = self._authenticate_user()
        if err:
            return err

        # Load appointment
        appointment = request.env['team.customer.appointment'].sudo().browse(appointment_id)
        if not appointment.exists():
            return ({"error": "not_found", "error_description": "appointment not found"}, 404)

        # Authorize
        if not self._user_can_access_appointment(user_id, appointment):
            return ({"error": "forbidden", "error_description": "user not authorized to view this appointment"}, 403)

        # Gather logs
        logs = getattr(appointment, 'app_screen_log_line', []) or []
        screen_logs = []

        for log in logs:
            try:
                screen_logs.append(self._serialize_screen_log(log))
            except (AttributeError, TypeError) as e:
                _logger.debug("Failed to serialize screen log: %s", e)
                continue

        return ({
            'appointment_id': appointment_id,
            'count': len(screen_logs),
            'app_screen_logs': screen_logs
        }, 200)

    @http.route("/api/appointments/<int:appointment_id>/app_live_screen_logs", auth="none", methods=["GET"], csrf=False)
    @json_response
    def get_live_screen_logs(self, appointment_id, **kwargs):
        """Get live screen logs for an appointment.

        Args:
            appointment_id: ID of the appointment.

        Returns:
            JSON response with live screen logs or error.
        """
        _logger.info(
            "AppointmentsController.get_live_screen_logs: appointment_id=%s from=%s",
            appointment_id, request.httprequest.remote_addr
        )

        # Authenticate
        user_id, err = self._authenticate_user()
        if err:
            return err

        # Load appointment
        appointment = request.env['team.customer.appointment'].sudo().browse(appointment_id)
        if not appointment.exists():
            return ({"error": "not_found", "error_description": "appointment not found"}, 404)

        # Authorize
        if not self._user_can_access_appointment(user_id, appointment):
            return ({"error": "forbidden", "error_description": "user not authorized to view this appointment"}, 403)

        # Gather logs
        logs = getattr(appointment, 'app_live_screen_log_line', []) or []
        live_logs = []

        for log in logs:
            try:
                live_logs.append(self._serialize_live_screen_log(log))
            except (AttributeError, TypeError) as e:
                _logger.debug("Failed to serialize live screen log: %s", e)
                continue

        return ({
            'appointment_id': appointment_id,
            'count': len(live_logs),
            'app_live_screen_logs': live_logs
        }, 200)

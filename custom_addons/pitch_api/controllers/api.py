import base64
import json
import logging
from datetime import datetime, time, timezone

from odoo import http, fields
from odoo.http import request

from .base import json_response, _ensure_secret, mask_token
from .auth import PitchApiAuthController

try:
    import jwt
except Exception:
    jwt = None

try:
    import pytz
except Exception:
    pytz = None

_logger = logging.getLogger(__name__)


class PitchApiController(http.Controller):
    """Generic API controller for Pitch API endpoints.

    Provides both single-resource and list endpoints for
    `team.customer.appointment`. Endpoints require a valid access token
    (Bearer token) presented in the Authorization header.
    """

    # --- Helpers ---------------------------------------------------------
    def _extract_bearer_token(self):
        """Return (token, None) or (None, error_dict)."""
        auth_hdr = request.httprequest.headers.get('Authorization') or request.httprequest.headers.get('authorization')
        if not auth_hdr:
            _logger.warning("api._extract_bearer_token: missing Authorization header from %s", request.httprequest.remote_addr)
            return None, ({"error": "invalid_request", "error_description": "Authorization header with bearer token required"}, 400)
        parts = auth_hdr.split()
        if len(parts) != 2 or parts[0].lower() != 'bearer':
            _logger.warning("api._extract_bearer_token: malformed Authorization header from %s: %s", request.httprequest.remote_addr, auth_hdr)
            return None, ({"error": "invalid_request", "error_description": "Authorization header must be 'Bearer <token>'"}, 400)
        # mask token when logging
        try:
            _logger.debug("api._extract_bearer_token: token provided from %s token=%s", request.httprequest.remote_addr, mask_token(parts[1]))
        except Exception:
            pass
        return parts[1], None

    def _resolve_user_from_access_token(self, token):
        """Verify access token and extract user id (int).

        Returns (uid, None) on success or (None, error_dict) on failure.
        """
        if not token or token.count('.') != 2:
            _logger.warning("api._resolve_user_from_access_token: invalid token format from %s", request.httprequest.remote_addr)
            return None, ({"error": "invalid_request", "error_description": "access token (JWT) required in Authorization header"}, 400)

        # verify signature/expiry/revocation using auth controller
        auth_ctrl = PitchApiAuthController()
        intros = auth_ctrl._introspect_access_token(token)
        if not intros.get('active'):
            _logger.warning("api._resolve_user_from_access_token: introspect failed reason=%s from %s", intros.get('reason', 'invalid'), request.httprequest.remote_addr)
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
            _logger.warning("api._resolve_user_from_access_token: could not determine uid from token from %s", request.httprequest.remote_addr)
            return None, ({"error": "invalid_request", "error_description": "could not determine user from token"}, 400)
        return uid, None

    def _user_is_authorized_for_appointment(self, user_id, appt):
        """Return True if user is owner or partner/attendee of the appointment."""
        try:
            if getattr(appt, 'user_id', False) and appt.user_id.id == user_id:
                return True
        except Exception:
            pass

        try:
            user = request.env['res.users'].sudo().browse(user_id)
            partner = getattr(user, 'partner_id', None)
            partners = getattr(appt, 'partner_ids', None) or getattr(appt, 'attendee_ids', None) or getattr(appt, 'partner_id', None)
            if not partners:
                return False
            partner_ids = [p.id for p in partners] if hasattr(partners, '__iter__') else ([partners.id] if partners else [])
            if partner and partner.id in partner_ids:
                return True
        except Exception:
            return False
        return False

    def _fmt_datetime(self, dt):
        try:
            return fields.Datetime.to_string(dt) if dt else None
        except Exception:
            return str(dt) if dt else None

    def _serialize_appointment(self, appt):
        """Serialize an appointment record to a dict (stable shape)."""

        return {
            'id': appt.id,
            'improveit_appointment_id': getattr(appt, 'improveit_appointment_id', None),
            'name': getattr(appt, 'name', None),
            'state': getattr(appt, 'state', None),
            'partner_id': appt.partner_id.id if getattr(appt, 'partner_id', None) else None,
            'customer_name': getattr(appt, 'customer_name', None),
            'applicant_data': {
                'applicant_first_name': getattr(appt, 'applicant_first_name', None),
                'applicant_middle_name': getattr(appt, 'applicant_middle_name', None),
                'applicant_last_name': getattr(appt, 'applicant_last_name', None),
                'applicant_address': {
                    'street': getattr(appt, 'street', None),
                    'street2': getattr(appt, 'street2', None),
                    'city': getattr(appt, 'city', None),
                    'state_id': getattr(appt.state_id, 'id', None) if getattr(appt, 'state_id', None) else None,
                    'state_code': getattr(appt.state_id, 'code', None) if getattr(appt, 'state_id', None) else None,
                    'state_name': getattr(appt.state_id, 'name', None) if getattr(appt, 'state_id', None) else None,
                    'country_id': getattr(appt.country_id, 'id', None) if getattr(appt, 'country_id', None) else None,
                    'country_code': getattr(appt.country_id, 'code', None) if getattr(appt, 'country_id', None) else None,
                    'country_name': getattr(appt.country_id, 'name', None) if getattr(appt, 'country_id', None) else None,
                    'zip': getattr(appt, 'zip', None),
                },
                'phone': getattr(appt, 'phone', None),
                'mobile': getattr(appt, 'mobile', None),
                'email': getattr(appt, 'email', None),
            },
            'co_applicant_data': {
                'co_applicant': getattr(appt, 'co_applicant', None),
                'co_applicant_first_name': getattr(appt, 'co_applicant_first_name', None),
                'co_applicant_middle_name': getattr(appt, 'co_applicant_middle_name', None),
                'co_applicant_last_name': getattr(appt, 'co_applicant_last_name', None),
                'co_applicant_address': {
                    'co_applicant_address': getattr(appt, 'co_applicant_address', None),
                    'co_applicant_city': getattr(appt, 'co_applicant_city', None),
                    'co_applicant_state_id': getattr(appt.co_applicant_state, 'id', None) if getattr(appt, 'co_applicant_state', None) else None,
                    'co_applicant_state_code': getattr(appt.co_applicant_state, 'code', None) if getattr(appt, 'co_applicant_state', None) else None,
                    'co_applicant_state_name': getattr(appt.co_applicant_state, 'name', None) if getattr(appt, 'co_applicant_state', None) else None,
                    'co_applicant_country_id': getattr(appt.co_applicant_country_id, 'id', None) if getattr(appt, 'co_applicant_country_id', None) else None,
                    'co_applicant_country_code': getattr(appt.co_applicant_country_id, 'code', None) if getattr(appt, 'co_applicant_country_id', None) else None,
                    'co_applicant_country_name': getattr(appt.co_applicant_country_id, 'name', None) if getattr(appt, 'co_applicant_country_id', None) else None,
                    'co_applicant_zip': getattr(appt, 'co_applicant_zip', None),
                    'co_applicant_state_code_2': getattr(appt, 'co_applicant_state_code', None),
                },
                'co_applicant_phone': getattr(appt, 'co_applicant_phone', None),
                'co_applicant_secondary_phone': getattr(appt, 'co_applicant_secondary_phone', None),
                'co_applicant_email': getattr(appt, 'co_applicant_email', None),
            },
            'appointment_date': self._fmt_datetime(getattr(appt, 'appointment_date', None)),
            'what_happened_notes': getattr(appt, 'what_happened_notes', None),
            'appointment_result': getattr(appt, 'appointment_result', None),
            'office_location_id': getattr(appt.office_location_id, 'id', None) if getattr(appt, 'office_location_id', None) else None,
            'office_location_name': getattr(appt.office_location_id, 'name', None) if getattr(appt, 'office_location_id', None) else None,
            'app_data': {
                'id': getattr(appt.app_version_id, 'id', None) if getattr(appt, 'app_version_id', None) else None,
                'app_version': getattr(appt.app_version_id, 'name', None) if getattr(appt, 'app_version_id', None) else None,
                'app_release_date': getattr(appt.app_version_id, 'date', None) if getattr(appt, 'app_version_id', None) else None,
            },
            'credit_application_url': getattr(appt, 'credit_application_url', None),
            'appointment_result_details': {
                'id': getattr(appt.resulting_reason_id, 'id', None) if getattr(appt, 'resulting_reason_id', None) else None,
                'reason': getattr(appt.resulting_reason_id, 'reason', None) if getattr(appt, 'resulting_reason_id', None) else None,
                'tags': getattr(appt.resulting_reason_id, 'appointment_result_ids', None).mapped('result') if getattr(appt, 'resulting_reason_id', None) and getattr(appt.resulting_reason_id, 'appointment_result_ids', None) else None,
            },
            'user_id': getattr(appt.user_id, 'id', None) if getattr(appt, 'user_id', None) else None,
            'user_data': {
                'id': getattr(appt.user_id, 'id', None) if getattr(appt, 'user_id', None) else None,
                'name': getattr(appt.user_id, 'name', None) if getattr(appt, 'user_id', None) else None,
                'login': getattr(appt.user_id, 'login', None) if getattr(appt, 'user_id', None) else None,
            },
            'measurement_exist': bool(getattr(appt, 'measurement_exist', False)),
            'send_physical_document': bool(getattr(appt, 'send_physical_document', False)),
            'flexible_installation': bool(getattr(appt, 'flexible_installation', False)),
            'whats_next_notes': getattr(appt, 'whats_next_notes', None),
            'last_price_quoted_value': getattr(appt, 'last_price_quoted_value', None),
            'market_segment': getattr(appt, 'market_segment', None),
            'both_parties_present': bool(getattr(appt, 'both_parties_present', False)),
            'sent_review_link': bool(getattr(appt, 'sent_review_link', False)),
            'make_payment_failure': bool(getattr(appt, 'make_payment_failure', False)),
            'destination_selection_id': getattr(appt.destination_selection_id, 'id', None) if getattr(appt, 'destination_selection_id', None) else None,
            'destination_selection_name': getattr(appt.destination_selection_id, 'name', None) if getattr(appt, 'destination_selection_id', None) else None,
            'additional_comments': getattr(appt, 'additional_comments', None),
            'geolocation_data': {
                'date_localization': self._fmt_datetime(getattr(appt, 'date_localization', None)),
                'partner_latitude': getattr(appt, 'partner_latitude', None),
                'partner_longitude': getattr(appt, 'partner_longitude', None),
            },
            'arrival_date': self._fmt_datetime(getattr(appt, 'arrival_date', None)),
            'departure_date': self._fmt_datetime(getattr(appt, 'departure_date', None)),
            'manual_arrival_date': self._fmt_datetime(getattr(appt, 'manual_arrival_date', None)),
            'app_screen_logs': [{'completion_date': getattr(log, 'completion_date', None), 'name': getattr(log, 'name', None)} for log in getattr(appt, 'app_screen_log_line', [])],
        }

    # --- Routes -----------------------------------------------------------
    @http.route("/api/appointments/<int:appointment_id>", auth="none", methods=["GET"], csrf=False)
    @json_response
    def get_appointment(self, appointment_id, **kwargs):
        """Return a single `team.customer.appointment` record if the requesting
        user (from the bearer token) is authorized to view it.

        Response: JSON with appointment fields or an error object.
        """
        _logger.info("api.get_appointment called: appointment_id=%s from=%s", appointment_id, request.httprequest.remote_addr)
        # Extract bearer token
        token, err = self._extract_bearer_token()
        if err:
            return err

        # Resolve user id from token and validate token
        user_id, err = self._resolve_user_from_access_token(token)
        if err:
            return err

        # Load the appointment from the requested model
        team_customer_appointment_obj = request.env['team.customer.appointment'].sudo()
        appt = team_customer_appointment_obj.browse(appointment_id)
        if not appt.exists():
            _logger.warning("api.get_appointment: appointment not found id=%s user_id=%s", appointment_id, user_id)
            return ({"error": "not_found", "error_description": "appointment not found"}, 404)

        # Authorization
        if not self._user_is_authorized_for_appointment(user_id, appt):
            _logger.warning("api.get_appointment: unauthorized access attempt appointment_id=%s user_id=%s", appointment_id, user_id)
            return ({"error": "forbidden", "error_description": "user not authorized to view this appointment"}, 403)

        _logger.info("api.get_appointment: success appointment_id=%s user_id=%s", appointment_id, user_id)
        return (self._serialize_appointment(appt), 200)

    @http.route("/api/appointments", auth="none", methods=["GET"], csrf=False)
    @json_response
    def list_appointments(self, **kwargs):
        """Return all appointments relevant to the authenticated user.

        Supports optional `limit` query param (default 100).
        """
        _logger.info("api.list_appointments called from=%s", request.httprequest.remote_addr)
        token, err = self._extract_bearer_token()
        if err:
            return err
        user_id, err = self._resolve_user_from_access_token(token)
        if err:
            return err

        try:
            limit = int(kwargs.get('limit') or request.params.get('limit') or 100)
            if limit <= 0:
                limit = 100
        except Exception:
            limit = 100

        appt_model = request.env['team.customer.appointment'].sudo()
        domain = [('user_id', '=', user_id)]

        recs = appt_model.search(domain, limit=limit, order='id desc')
        data = [self._serialize_appointment(r) for r in recs]
        _logger.info("api.list_appointments: returning %s appointments for user_id=%s", len(data), user_id)
        return ({'user_id': user_id, 'count': len(data), 'appointments': data}, 200)

    @http.route("/api/appointments/paginated", auth="none", methods=["GET"], csrf=False)
    @json_response
    def list_appointments_paginated(self, **kwargs):
        """Return appointments for the authenticated user with pagination.

        Query params:
        - page: 1-based page number (defaults to 1)
        - per_page: items per page (defaults to 50, capped to MAX_PER_PAGE)
        """
        token, err = self._extract_bearer_token()
        if err:
            return err

        user_id, err = self._resolve_user_from_access_token(token)
        if err:
            return err

        # parse pagination params
        try:
            page = int(kwargs.get('page') or request.params.get('page') or 1)
        except Exception:
            page = 1
        if page < 1:
            page = 1

        try:
            per_page = int(kwargs.get('per_page') or request.params.get('per_page') or 50)
        except Exception:
            per_page = 50
        if per_page < 1:
            per_page = 50

        MAX_PER_PAGE = 1000
        if per_page > MAX_PER_PAGE:
            per_page = MAX_PER_PAGE

        offset = (page - 1) * per_page

        appt_model = request.env['team.customer.appointment'].sudo()

        # build domain: same scoping as list_appointments (user or partner membership)
        domain = [('user_id', '=', user_id)]

        total = appt_model.search_count(domain)
        recs = appt_model.search(domain, limit=per_page, offset=offset, order='appointment_date asc')
        data = [self._serialize_appointment(r) for r in recs]

        return ({
            'user_id': user_id,
            'page': page,
            'per_page': per_page,
            'total': total,
            'count': len(data),
            'appointments': data,
        }, 200)


    @http.route("/api/appointments/<int:appointment_id>/app_screen_logs", auth="none", methods=["GET"], csrf=False)
    @json_response
    def get_appointment_app_screen_logs(self, appointment_id, **kwargs):
        """Return the app screen log lines for a given appointment.

        Requires a valid Bearer access token in Authorization header and the
        requesting user must be authorized to view the appointment (same rules
        as `get_appointment`).
        """
        # Extract bearer token
        token, err = self._extract_bearer_token()
        if err:
            return err

        # Resolve user id from token and validate token
        user_id, err = self._resolve_user_from_access_token(token)
        if err:
            return err

        # Load the appointment
        team_customer_appointment_obj = request.env['team.customer.appointment'].sudo()
        appt = team_customer_appointment_obj.browse(appointment_id)
        if not appt.exists():
            return ({"error": "not_found", "error_description": "appointment not found"}, 404)

        # Authorization
        if not self._user_is_authorized_for_appointment(user_id, appt):
            return ({"error": "forbidden", "error_description": "user not authorized to view this appointment"}, 403)

        # Gather app screen logs
        logs = getattr(appt, 'app_screen_log_line', []) or []
        out = []
        for log in logs:
            try:
                out.append({
                    'id': getattr(log, 'id', None),
                    'name': getattr(log, 'name', None),
                    'completion_date': self._fmt_datetime(getattr(log, 'completion_date', None)),
                    # include any additional data fields if present
                    'user_id': getattr(log.user_id, 'id', None) if hasattr(log, 'user_id') else None,
                })
            except Exception:
                # best-effort: skip malformed entries
                continue

        return ({'appointment_id': appointment_id, 'count': len(out), 'app_screen_logs': out}, 200)

    @http.route("/api/appointments/today", auth="none", methods=["GET"], csrf=False)
    @json_response
    def list_todays_appointments(self, **kwargs):
        """Return appointments whose `appointment_date` falls within 'today'
        in the specified timezone.

        Query params:
        - tz: optional IANA timezone string (e.g. 'America/Chicago'). If not
          provided, the requesting user's timezone is used; fallback is UTC.
        - limit: optional integer limit (default 100)
        """
        token, err = self._extract_bearer_token()
        if err:
            return err

        user_id, err = self._resolve_user_from_access_token(token)
        if err:
            return err

        # determine timezone
        tz_name = (kwargs.get('tz') or request.params.get('tz') or None)
        user_tz = None
        try:
            user = request.env['res.users'].sudo().browse(user_id)
            user_tz = getattr(user, 'tz', None)
        except Exception:
            user_tz = None

        if not tz_name:
            tz_name = user_tz or 'UTC'

        # compute day start/end in UTC from local tz
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
                # fallback: assume server UTC (timezone-aware)
                now_utc = datetime.now(tz=timezone.utc)
                local_date = now_utc.date()
                start_utc = datetime.combine(local_date, time.min).replace(tzinfo=timezone.utc)
                end_utc = datetime.combine(local_date, time.max).replace(tzinfo=timezone.utc)
        except Exception:
            # On error, fallback to UTC today (timezone-aware)
            now_utc = datetime.now(tz=timezone.utc)
            local_date = now_utc.date()
            start_utc = datetime.combine(local_date, time.min).replace(tzinfo=timezone.utc)
            end_utc = datetime.combine(local_date, time.max).replace(tzinfo=timezone.utc)

        start_str = fields.Datetime.to_string(start_utc)
        end_str = fields.Datetime.to_string(end_utc)

        # limit (optional): apply only if caller provided one
        limit_param = kwargs.get('limit') or request.params.get('limit')
        limit = None
        if limit_param is not None:
            try:
                limit_val = int(limit_param)
                if limit_val > 0:
                    limit = limit_val
                else:
                    limit = None
            except Exception:
                limit = None

        appt_model = request.env['team.customer.appointment'].sudo()

        # base domain: appointment_date within utc window
        date_domain = [('appointment_date', '>=', start_str), ('appointment_date', '<=', end_str)]

        # user scoping: user or partner membership
        domain = date_domain + [('user_id', '=', user_id)]

        if limit:
            recs = appt_model.search(domain, limit=limit, order='appointment_date asc')
        else:
            recs = appt_model.search(domain, order='appointment_date asc')
        data = [self._serialize_appointment(r) for r in recs]
        return ({'user_id': user_id, 'tz': tz_name, 'date': str(local_date), 'count': len(data), 'appointments': data}, 200)







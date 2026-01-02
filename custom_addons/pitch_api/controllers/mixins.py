# -*- coding: utf-8 -*-
"""Shared mixins and utilities for Pitch API controllers.

This module provides reusable functionality for authentication,
serialization, pagination, and filter validation used across
different API endpoints.

Mixins:
    - AuthenticationMixin: JWT token extraction and user authentication
    - AppointmentSerializerMixin: Appointment data serialization
    - PaginationMixin: Pagination parameter parsing
    - FilterMixin: Query filter parsing and validation
    - AppointmentAuthorizationMixin: Appointment access authorization
"""

import base64
import json
import logging
from datetime import datetime, time, timezone

from odoo import fields
from odoo.http import request

from .base import ensure_jwt_secret, mask_token

# Import standardized expired token response from auth module
# These will be imported lazily in _resolve_user_from_token to avoid circular imports

# Legacy alias for backward compatibility
_ensure_secret = ensure_jwt_secret

try:
    import jwt
except ImportError:
    jwt = None

try:
    import pytz
except ImportError:
    pytz = None

_logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================

VALID_APPOINTMENT_STATUSES = ('draft', 'scheduled', 'canceled', 'done')

VALID_ORDER_OPTIONS = {
    'id_desc': 'id desc',
    'id_asc': 'id asc',
    'date_desc': 'appointment_date desc',
    'date_asc': 'appointment_date asc',
}

DEFAULT_ORDER = 'id desc'
DEFAULT_PER_PAGE = 200
MAX_PER_PAGE = 2000


# =============================================================================
# Authentication Mixin
# =============================================================================

class AuthenticationMixin:
    """Mixin providing JWT authentication methods."""

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
            _logger.warning(
                "AuthMixin: Missing Authorization header from %s",
                request.httprequest.remote_addr
            )
            return None, ({
                "error": "invalid_request",
                "error_description": "Authorization header with bearer token required"
            }, 400)

        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != 'bearer':
            _logger.warning(
                "AuthMixin: Malformed Authorization header from %s",
                request.httprequest.remote_addr
            )
            return None, ({
                "error": "invalid_request",
                "error_description": "Authorization header must be 'Bearer <token>'"
            }, 400)

        try:
            _logger.debug(
                "AuthMixin: Token provided from %s token=%s",
                request.httprequest.remote_addr,
                mask_token(parts[1])
            )
        except Exception as e:
            _logger.debug("Failed to log token info: %s", e)

        return parts[1], None

    def _resolve_user_from_token(self, token):
        """Verify access token and extract user ID.

        Args:
            token: JWT access token string.

        Returns:
            tuple: (user_id, None) on success or (None, error_response) on failure.
        """
        if not token or token.count('.') != 2:
            _logger.warning(
                "AuthMixin: Invalid token format from %s",
                request.httprequest.remote_addr
            )
            return None, ({
                "error": "invalid_request",
                "error_description": "access token (JWT) required in Authorization header"
            }, 400)

        # Verify signature/expiry/revocation
        from .auth import AuthController, EXPIRED_TOKEN_RESPONSE, EXPIRED_TOKEN_STATUS
        auth_ctrl = AuthController()
        introspection = auth_ctrl._introspect_access_token(token)

        if not introspection.get('active'):
            reason = introspection.get('reason', 'invalid')
            _logger.warning(
                "AuthMixin: Token introspection failed reason=%s from %s",
                reason,
                request.httprequest.remote_addr
            )
            # Return standardized expired token response for refresh flow
            if reason == 'expired':
                return None, (EXPIRED_TOKEN_RESPONSE, EXPIRED_TOKEN_STATUS)
            return None, ({
                "error": "invalid_token",
                "error_description": reason
            }, 401)

        # Extract user ID from token
        user_id = self._extract_user_id_from_token(token)

        if not user_id:
            _logger.warning(
                "AuthMixin: Could not determine user from token from %s",
                request.httprequest.remote_addr
            )
            return None, ({
                "error": "invalid_request",
                "error_description": "could not determine user from token"
            }, 400)

        return user_id, None

    def _extract_user_id_from_token(self, token):
        """Extract user ID from JWT token payload.

        Args:
            token: JWT token string.

        Returns:
            int or None: User ID if found, None otherwise.
        """
        try:
            secret = _ensure_secret(request.env)
        except Exception as e:
            _logger.debug("Failed to get JWT secret: %s", e)
            secret = None

        user_id = None

        # Try JWT library first
        if jwt is not None and secret is not None:
            try:
                claims = jwt.decode(
                    token, secret,
                    algorithms=["HS256"],
                    options={"verify_exp": False, "verify_aud": False}
                )
                user_id = claims.get('uid') or claims.get('sub')
            except jwt.exceptions.InvalidTokenError as e:
                _logger.debug("JWT decode failed: %s", e)
            except Exception as e:
                _logger.debug("Unexpected error decoding JWT: %s", e)

        # Fallback: manual base64 decode
        if user_id is None:
            try:
                _, payload_b64, _ = token.split('.')
                padding = '=' * (-len(payload_b64) % 4)
                payload_json = base64.urlsafe_b64decode(payload_b64 + padding)
                payload = json.loads(payload_json)
                user_id = payload.get('uid') or payload.get('sub')
            except (ValueError, json.JSONDecodeError) as e:
                _logger.debug("Manual token decode failed: %s", e)
            except Exception as e:
                _logger.debug("Unexpected error in manual token decode: %s", e)

        # Convert to int
        try:
            return int(user_id) if user_id is not None else None
        except (ValueError, TypeError):
            return None

    def _verify_admin_access(self, user_id):
        """Verify that the user has admin privileges.

        Args:
            user_id: ID of the user to verify.

        Returns:
            tuple: (True, None) if admin, (False, error_response) otherwise.
        """
        try:
            user = request.env['res.users'].sudo().browse(user_id)
            if not user.exists():
                _logger.warning("AuthMixin: User not found user_id=%s", user_id)
                return False, ({
                    "error": "forbidden",
                    "error_description": "user not found"
                }, 403)

            is_admin = getattr(user, 'is_pitch_admin', False)
            if not is_admin:
                _logger.warning(
                    "AuthMixin: Non-admin access attempt user_id=%s",
                    user_id
                )
                return False, ({
                    "error": "forbidden",
                    "error_description": "admin access required"
                }, 403)

            return True, None

        except Exception as e:
            _logger.exception("AuthMixin: Error verifying admin access: %s", e)
            return False, ({
                "error": "server_error",
                "error_description": "error verifying access"
            }, 500)

    def _authenticate_user(self):
        """Authenticate user from bearer token.

        Returns:
            tuple: (user_id, None) on success or (None, error_response) on failure.
        """
        token, err = self._extract_bearer_token()
        if err:
            return None, err

        return self._resolve_user_from_token(token)

    def _authenticate_admin(self):
        """Authenticate admin user from bearer token.

        Returns:
            tuple: (user_id, None) on success or (None, error_response) on failure.
        """
        user_id, err = self._authenticate_user()
        if err:
            return None, err

        is_admin, err = self._verify_admin_access(user_id)
        if err:
            return None, err

        return user_id, None


# =============================================================================
# Serialization Mixin
# =============================================================================

class AppointmentSerializerMixin:
    """Mixin providing appointment serialization methods."""

    def _format_datetime(self, dt):
        """Format datetime to string.

        Args:
            dt: datetime object or None.

        Returns:
            str or None: Formatted datetime string.
        """
        try:
            return fields.Datetime.to_string(dt) if dt else None
        except (TypeError, ValueError) as e:
            _logger.debug("Failed to format datetime: %s", e)
            return str(dt) if dt else None

    def _serialize_appointment(self, appointment):
        """Serialize an appointment record to a dictionary.

        Args:
            appointment: team.customer.appointment record.

        Returns:
            dict: Serialized appointment data.
        """
        appt = appointment

        return {
            'id': appt.id,
            'improveit_appointment_id': getattr(appt, 'improveit_appointment_id', None),
            'name': getattr(appt, 'name', None),
            'state': getattr(appt, 'state', None),
            'partner_id': appt.partner_id.id if getattr(appt, 'partner_id', None) else None,
            'customer_name': getattr(appt, 'customer_name', None),
            'applicant_data': self._serialize_applicant_data(appt),
            'co_applicant_data': self._serialize_co_applicant_data(appt),
            'appointment_date': self._format_datetime(getattr(appt, 'appointment_date', None)),
            'what_happened_notes': getattr(appt, 'what_happened_notes', None),
            'appointment_result': getattr(appt, 'appointment_result', None),
            'office_location_id': getattr(appt.office_location_id, 'id', None) if getattr(appt, 'office_location_id', None) else None,
            'office_location_name': getattr(appt.office_location_id, 'name', None) if getattr(appt, 'office_location_id', None) else None,
            'app_data': self._serialize_app_data(appt),
            'credit_application_url': getattr(appt, 'credit_application_url', None),
            'appointment_result_details': self._serialize_result_details(appt),
            'user_id': getattr(appt.user_id, 'id', None) if getattr(appt, 'user_id', None) else None,
            'user_data': self._serialize_user_data(appt),
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
            'geolocation_data': self._serialize_geolocation_data(appt),
            'arrival_date': self._format_datetime(getattr(appt, 'arrival_date', None)),
            'departure_date': self._format_datetime(getattr(appt, 'departure_date', None)),
            'manual_arrival_date': self._format_datetime(getattr(appt, 'manual_arrival_date', None)),
        }

    def _serialize_applicant_data(self, appt):
        """Serialize applicant information."""
        return {
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
        }

    def _serialize_co_applicant_data(self, appt):
        """Serialize co-applicant information."""
        return {
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
        }

    def _serialize_app_data(self, appt):
        """Serialize app version information."""
        return {
            'id': getattr(appt.app_version_id, 'id', None) if getattr(appt, 'app_version_id', None) else None,
            'app_version': getattr(appt.app_version_id, 'name', None) if getattr(appt, 'app_version_id', None) else None,
            'app_release_date': getattr(appt.app_version_id, 'date', None) if getattr(appt, 'app_version_id', None) else None,
        }

    def _serialize_result_details(self, appt):
        """Serialize appointment result details."""
        result_id = getattr(appt, 'resulting_reason_id', None)
        if not result_id:
            return {'id': None, 'reason': None, 'tags': None}

        tags = None
        if getattr(result_id, 'appointment_result_ids', None):
            tags = result_id.appointment_result_ids.mapped('result')

        return {
            'id': getattr(result_id, 'id', None),
            'reason': getattr(result_id, 'reason', None),
            'tags': tags,
        }

    def _serialize_user_data(self, appt):
        """Serialize user information."""
        user = getattr(appt, 'user_id', None)
        if not user:
            return {'id': None, 'name': None, 'login': None}

        return {
            'id': getattr(user, 'id', None),
            'name': getattr(user, 'name', None),
            'login': getattr(user, 'login', None),
        }

    def _serialize_geolocation_data(self, appt):
        """Serialize geolocation information."""
        return {
            'date_localization': self._format_datetime(getattr(appt, 'date_localization', None)),
            'partner_latitude': getattr(appt, 'partner_latitude', None),
            'partner_longitude': getattr(appt, 'partner_longitude', None),
        }

    def _serialize_screen_log(self, log):
        """Serialize a screen log entry."""
        return {
            'id': getattr(log, 'id', None),
            'name': getattr(log, 'name', None),
            'completion_date': self._format_datetime(getattr(log, 'completion_date', None)),
            'user_id': getattr(log.user_id, 'id', None) if hasattr(log, 'user_id') and log.user_id else None,
        }

    def _serialize_live_screen_log(self, log):
        """Serialize a live screen log entry."""
        return {
            'id': getattr(log, 'id', None),
            'name': getattr(log, 'name', None),
            'screen_entry_date': self._format_datetime(getattr(log, 'screen_entry_date', None)),
            'user_id': getattr(log.user_id, 'id', None) if hasattr(log, 'user_id') and log.user_id else None,
        }


# =============================================================================
# Pagination Mixin
# =============================================================================

class PaginationMixin:
    """Mixin providing pagination parsing and validation."""

    def _parse_pagination(self, kwargs, default_per_page=DEFAULT_PER_PAGE, max_per_page=MAX_PER_PAGE):
        """Parse and validate pagination parameters.

        Args:
            kwargs: Request keyword arguments.
            default_per_page: Default items per page.
            max_per_page: Maximum allowed items per page.

        Returns:
            tuple: (page, per_page, None) on success or (None, None, error_response) on failure.
        """
        page_param = kwargs.get('page') or request.params.get('page')
        per_page_param = kwargs.get('per_page') or request.params.get('per_page')

        # Parse page (default: 1)
        try:
            page = int(page_param) if page_param else 1
        except (ValueError, TypeError):
            page = 1
        if page < 1:
            page = 1

        # Parse per_page
        try:
            per_page = int(per_page_param) if per_page_param else default_per_page
        except (ValueError, TypeError):
            per_page = default_per_page
        if per_page < 1:
            per_page = default_per_page

        # Validate per_page limit
        if per_page > max_per_page:
            return None, None, ({
                "error": "invalid_request",
                "error_description": f"per_page cannot exceed {max_per_page}. Requested: {per_page}"
            }, 400)

        return page, per_page, None

    def _calculate_offset(self, page, per_page):
        """Calculate database offset from page and per_page.

        Args:
            page: Page number (1-based).
            per_page: Items per page.

        Returns:
            int: Database offset.
        """
        return (page - 1) * per_page


# =============================================================================
# Filter Mixin
# =============================================================================

class FilterMixin:
    """Mixin providing filter parsing and validation."""

    def _parse_status_filter(self, kwargs, user_id=None):
        """Parse and validate status filter parameter.

        Args:
            kwargs: Request keyword arguments.
            user_id: User ID for logging (optional).

        Returns:
            tuple: (status_value, None) on success or (None, error_response) on invalid.
        """
        status_param = kwargs.get('status') or request.params.get('status')

        if status_param is None:
            return None, None

        status_param = status_param.strip() if status_param else ''
        if not status_param:
            return None, None

        status_lower = status_param.lower()
        if status_lower in VALID_APPOINTMENT_STATUSES:
            return status_lower, None

        _logger.warning(
            "FilterMixin: Invalid status '%s' from user_id=%s",
            status_param, user_id
        )
        return None, ({
            "error": "invalid_request",
            "error_description": f"Invalid status value '{status_param}'. Allowed values: draft, scheduled, canceled, done"
        }, 400)

    def _parse_order_filter(self, kwargs, user_id=None):
        """Parse and validate order filter parameter.

        Args:
            kwargs: Request keyword arguments.
            user_id: User ID for logging (optional).

        Returns:
            tuple: (order_key, order_clause, None) on success or (None, None, error_response) on invalid.
        """
        order_param = kwargs.get('order') or request.params.get('order')

        if not order_param:
            return 'id_desc', DEFAULT_ORDER, None

        order_param = order_param.strip().lower()
        if order_param in VALID_ORDER_OPTIONS:
            return order_param, VALID_ORDER_OPTIONS[order_param], None

        _logger.warning(
            "FilterMixin: Invalid order '%s' from user_id=%s",
            order_param, user_id
        )
        return None, None, ({
            "error": "invalid_request",
            "error_description": f"Invalid order value '{order_param}'. Allowed values: id_desc, id_asc, date_desc, date_asc"
        }, 400)

    def _parse_timezone(self, kwargs, user_id=None):
        """Parse timezone parameter or get user's default.

        Args:
            kwargs: Request keyword arguments.
            user_id: User ID for fallback timezone.

        Returns:
            str: Timezone name (IANA format).
        """
        tz_name = kwargs.get('tz') or request.params.get('tz')

        if tz_name:
            return tz_name

        if user_id:
            try:
                user = request.env['res.users'].sudo().browse(user_id)
                return getattr(user, 'tz', None) or 'UTC'
            except Exception as e:
                _logger.debug("Failed to get user timezone: %s", e)

        return 'UTC'

    def _parse_date_filter(self, date_param, tz_name, is_end_of_day=False, user_id=None, param_name='date'):
        """Parse and validate a date filter parameter.

        Args:
            date_param: Date string (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS).
            tz_name: Timezone for conversion.
            is_end_of_day: If True and date-only, use end of day; else start of day.
            user_id: User ID for logging.
            param_name: Parameter name for error messages.

        Returns:
            tuple: (utc_datetime_string, None) on success or (None, error_response) on invalid.
        """
        if not date_param:
            return None, None

        try:
            # Try datetime format first
            try:
                dt = datetime.strptime(date_param, '%Y-%m-%d %H:%M:%S')
                is_datetime = True
            except ValueError:
                dt = datetime.strptime(date_param, '%Y-%m-%d')
                is_datetime = False

            # Convert to UTC
            if pytz is not None:
                tz = pytz.timezone(tz_name)
                if is_datetime:
                    local_dt = tz.localize(dt)
                else:
                    time_val = time.max if is_end_of_day else time.min
                    local_dt = tz.localize(datetime.combine(dt.date(), time_val))
                utc_dt = local_dt.astimezone(pytz.UTC)
            else:
                if is_datetime:
                    utc_dt = dt.replace(tzinfo=timezone.utc)
                else:
                    time_val = time.max if is_end_of_day else time.min
                    utc_dt = datetime.combine(dt.date(), time_val).replace(tzinfo=timezone.utc)

            return fields.Datetime.to_string(utc_dt), None

        except (ValueError, TypeError) as e:
            _logger.warning(
                "FilterMixin: Invalid %s '%s' from user_id=%s: %s",
                param_name, date_param, user_id, e
            )
            return None, ({
                "error": "invalid_request",
                "error_description": f"Invalid {param_name} format '{date_param}'. Expected: YYYY-MM-DD or YYYY-MM-DD HH:MM:SS"
            }, 400)

    def _get_today_range_utc(self, tz_name):
        """Get today's date range in UTC.

        Args:
            tz_name: Timezone name for determining 'today'.

        Returns:
            tuple: (start_utc_string, end_utc_string, local_date, effective_tz_name)
        """
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
                tz_name = 'UTC'
        except Exception as e:
            _logger.debug("Failed to calculate today range for tz=%s: %s", tz_name, e)
            now_utc = datetime.now(tz=timezone.utc)
            local_date = now_utc.date()
            start_utc = datetime.combine(local_date, time.min).replace(tzinfo=timezone.utc)
            end_utc = datetime.combine(local_date, time.max).replace(tzinfo=timezone.utc)
            tz_name = 'UTC'

        return (
            fields.Datetime.to_string(start_utc),
            fields.Datetime.to_string(end_utc),
            local_date,
            tz_name
        )


# =============================================================================
# Authorization Mixin
# =============================================================================

class AppointmentAuthorizationMixin:
    """Mixin providing appointment authorization checks."""

    def _user_can_access_appointment(self, user_id, appointment):
        """Check if user is authorized to access an appointment.

        Args:
            user_id: ID of the user.
            appointment: Appointment record.

        Returns:
            bool: True if authorized, False otherwise.
        """
        # Check if user is the owner
        try:
            if getattr(appointment, 'user_id', False) and appointment.user_id.id == user_id:
                return True
        except (AttributeError, TypeError) as e:
            _logger.debug("Failed to check appointment owner: %s", e)

        # Check if user's partner is associated with the appointment
        try:
            user = request.env['res.users'].sudo().browse(user_id)
            partner = getattr(user, 'partner_id', None)

            partners = (
                getattr(appointment, 'partner_ids', None) or
                getattr(appointment, 'attendee_ids', None) or
                getattr(appointment, 'partner_id', None)
            )

            if not partners:
                return False

            if hasattr(partners, '__iter__'):
                partner_ids = [p.id for p in partners]
            else:
                partner_ids = [partners.id] if partners else []

            if partner and partner.id in partner_ids:
                return True

        except (AttributeError, TypeError) as e:
            _logger.debug("Failed to check partner access: %s", e)

        return False

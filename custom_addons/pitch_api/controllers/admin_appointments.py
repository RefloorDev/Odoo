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
    POST /api/admin/appointments/app_live_screen_logs        - Bulk live screen logs for multiple appointments
    GET /api/admin/appointments/analytics                    - Time analytics and metrics
    GET /api/admin/market-segments                           - List all distinct market segments
    GET /api/admin/salespersons                              - List salespersons by market segment

Filter Parameters (AND logic):
    market_segment     - Filter by market segment (comma-separated for multiple)
    user_id            - Filter by salesperson/user ID (Odoo user ID)
    improveit_user_id  - Filter by Salesforce user ID
    status             - Filter by status (draft, scheduled, canceled, done)
    date_from          - Filter from date in UTC (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)
    date_to            - Filter to date in UTC (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)

Search Parameters (AND logic with filters):
    customer      - Search in customer name fields (partial match, priority-based)
    co_applicant  - Search in co-applicant name fields (partial match, priority-based)
    name          - Search in appointment reference (partial match)
    id            - Search by appointment ID (exact match)

Pagination:
    page      - Page number (default: 1)
    per_page  - Items per page (default: 200, max: 2000)
    order     - Sort order (id_desc, id_asc, date_desc, date_asc)
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

        # Search parameters (direct field searches)
        customer = kwargs.get('customer') or request.params.get('customer')
        if customer:
            filters['customer'] = customer.strip()

        co_applicant = kwargs.get('co_applicant') or request.params.get('co_applicant')
        if co_applicant:
            filters['co_applicant'] = co_applicant.strip()

        name = kwargs.get('name') or request.params.get('name')
        if name:
            filters['name'] = name.strip()

        id_param = kwargs.get('id') or request.params.get('id')
        if id_param:
            try:
                filters['id'] = int(id_param)
            except (ValueError, TypeError):
                filters['id_invalid'] = id_param

        # Market segment (comma-separated for multiple)
        market_segment = kwargs.get('market_segment') or request.params.get('market_segment')
        if market_segment:
            segments = [s.strip() for s in market_segment.split(',') if s.strip()]
            filters['market_segment'] = segments if len(segments) > 1 else (segments[0] if segments else None)

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

        return filters

    def _build_customer_search_domain(self, search_term):
        """Build search domain for customer name fields with priority matching.

        Priority order:
        1. Exact match on customer_name
        2. Reversed format match ("john doe" -> "doe, john")
        3. first_name = first_word AND last_name = second_word
        4. first_name = second_word AND last_name = first_word (swapped)
        5. Partial match (ilike) on any field

        Returns a list of (domain, priority) tuples for prioritized searching.
        """
        if not search_term:
            return []

        search_term = search_term.strip()
        words = search_term.split()
        domains_with_priority = []

        # Fields to search
        name_field = 'customer_name'
        first_name_field = 'applicant_first_name'
        middle_name_field = 'applicant_middle_name'
        last_name_field = 'applicant_last_name'

        # Priority 1: Exact match on customer_name
        domains_with_priority.append((
            [(name_field, '=ilike', search_term)],
            1
        ))

        if len(words) >= 2:
            first_word = words[0]
            last_word = words[-1]
            middle_words = ' '.join(words[1:-1]) if len(words) > 2 else None

            # Priority 2: Reversed format ("john doe" -> "doe, john")
            reversed_format = f"{last_word}, {first_word}"
            domains_with_priority.append((
                [(name_field, '=ilike', reversed_format)],
                2
            ))

            # Also try with comma but no space
            reversed_format_no_space = f"{last_word},{first_word}"
            domains_with_priority.append((
                [(name_field, '=ilike', reversed_format_no_space)],
                2
            ))

            # Priority 3: first_name = first_word AND last_name = last_word
            domains_with_priority.append((
                ['&', (first_name_field, '=ilike', first_word), (last_name_field, '=ilike', last_word)],
                3
            ))

            # Priority 4: first_name = last_word AND last_name = first_word (swapped)
            domains_with_priority.append((
                ['&', (first_name_field, '=ilike', last_word), (last_name_field, '=ilike', first_word)],
                4
            ))

            # If there are middle words, also check middle_name
            if middle_words:
                domains_with_priority.append((
                    ['&', '&',
                     (first_name_field, '=ilike', first_word),
                     (middle_name_field, '=ilike', middle_words),
                     (last_name_field, '=ilike', last_word)],
                    3
                ))

        # Priority 5: Partial match on any field
        partial_pattern = f"%{search_term}%"
        partial_domain = [
            '|', '|', '|',
            (name_field, 'ilike', search_term),
            (first_name_field, 'ilike', search_term),
            (middle_name_field, 'ilike', search_term),
            (last_name_field, 'ilike', search_term),
        ]
        domains_with_priority.append((partial_domain, 5))

        # Also search each word individually for partial matches
        if len(words) >= 1:
            for word in words:
                if len(word) >= 2:  # Skip very short words
                    word_domain = [
                        '|', '|', '|',
                        (name_field, 'ilike', word),
                        (first_name_field, 'ilike', word),
                        (middle_name_field, 'ilike', word),
                        (last_name_field, 'ilike', word),
                    ]
                    domains_with_priority.append((word_domain, 6))

        return domains_with_priority

    def _build_co_applicant_search_domain(self, search_term):
        """Build search domain for co-applicant name fields with priority matching.

        Same priority logic as customer search but for co-applicant fields.
        """
        if not search_term:
            return []

        search_term = search_term.strip()
        words = search_term.split()
        domains_with_priority = []

        # Fields to search
        name_field = 'co_applicant'
        first_name_field = 'co_applicant_first_name'
        middle_name_field = 'co_applicant_middle_name'
        last_name_field = 'co_applicant_last_name'

        # Priority 1: Exact match on co_applicant
        domains_with_priority.append((
            [(name_field, '=ilike', search_term)],
            1
        ))

        if len(words) >= 2:
            first_word = words[0]
            last_word = words[-1]
            middle_words = ' '.join(words[1:-1]) if len(words) > 2 else None

            # Priority 2: Reversed format ("john doe" -> "doe, john")
            reversed_format = f"{last_word}, {first_word}"
            domains_with_priority.append((
                [(name_field, '=ilike', reversed_format)],
                2
            ))

            reversed_format_no_space = f"{last_word},{first_word}"
            domains_with_priority.append((
                [(name_field, '=ilike', reversed_format_no_space)],
                2
            ))

            # Priority 3: first_name = first_word AND last_name = last_word
            domains_with_priority.append((
                ['&', (first_name_field, '=ilike', first_word), (last_name_field, '=ilike', last_word)],
                3
            ))

            # Priority 4: first_name = last_word AND last_name = first_word (swapped)
            domains_with_priority.append((
                ['&', (first_name_field, '=ilike', last_word), (last_name_field, '=ilike', first_word)],
                4
            ))

            if middle_words:
                domains_with_priority.append((
                    ['&', '&',
                     (first_name_field, '=ilike', first_word),
                     (middle_name_field, '=ilike', middle_words),
                     (last_name_field, '=ilike', last_word)],
                    3
                ))

        # Priority 5: Partial match on any field
        partial_domain = [
            '|', '|', '|',
            (name_field, 'ilike', search_term),
            (first_name_field, 'ilike', search_term),
            (middle_name_field, 'ilike', search_term),
            (last_name_field, 'ilike', search_term),
        ]
        domains_with_priority.append((partial_domain, 5))

        # Also search each word individually
        if len(words) >= 1:
            for word in words:
                if len(word) >= 2:
                    word_domain = [
                        '|', '|', '|',
                        (name_field, 'ilike', word),
                        (first_name_field, 'ilike', word),
                        (middle_name_field, 'ilike', word),
                        (last_name_field, 'ilike', word),
                    ]
                    domains_with_priority.append((word_domain, 6))

        return domains_with_priority

    def _build_name_search_domain(self, search_term):
        """Build search domain for appointment name/reference field.

        Priority:
        1. Exact match
        2. Partial match (ilike)
        """
        if not search_term:
            return []

        search_term = search_term.strip()
        domains_with_priority = []

        # Priority 1: Exact match
        domains_with_priority.append((
            [('name', '=ilike', search_term)],
            1
        ))

        # Priority 2: Partial match
        domains_with_priority.append((
            [('name', 'ilike', search_term)],
            2
        ))

        return domains_with_priority

    def _execute_priority_search(self, base_domain, search_domains_with_priority, model, order_clause):
        """Execute search with priority-based domain matching.

        Tries domains in priority order and returns IDs from the first
        non-empty result set. If no priority match found, returns all IDs
        matching any of the search conditions.

        Args:
            base_domain: Base domain conditions (non-search filters)
            search_domains_with_priority: List of (domain, priority) tuples
            model: Odoo model to search
            order_clause: Order clause for sorting

        Returns:
            Recordset of matching appointments
        """
        if not search_domains_with_priority:
            return None

        # Sort by priority
        sorted_domains = sorted(search_domains_with_priority, key=lambda x: x[1])

        # Group by priority level
        priority_groups = {}
        for domain, priority in sorted_domains:
            if priority not in priority_groups:
                priority_groups[priority] = []
            priority_groups[priority].append(domain)

        # Try each priority level
        for priority in sorted(priority_groups.keys()):
            domains = priority_groups[priority]

            # Build OR domain for all conditions at this priority level
            if len(domains) == 1:
                combined_search_domain = domains[0]
            else:
                combined_search_domain = ['|'] * (len(domains) - 1)
                for d in domains:
                    combined_search_domain.extend(d)

            # Combine with base domain
            full_domain = base_domain + combined_search_domain

            # Check if any records match
            count = model.search_count(full_domain)
            if count > 0:
                _logger.debug(
                    "Priority search: Found %d records at priority %d",
                    count, priority
                )
                return full_domain

        # No matches at any priority level - return domain that matches nothing
        # But we should still return records if partial match exists
        # Combine all search domains with OR
        all_domains = [d for d, _ in sorted_domains]
        if len(all_domains) == 1:
            combined_domain = all_domains[0]
        else:
            combined_domain = ['|'] * (len(all_domains) - 1)
            for d in all_domains:
                combined_domain.extend(d)

        return base_domain + combined_domain

    def _build_domain(self, filters):
        """Build Odoo domain from parsed filters.

        Returns a domain list based on filter_logic (AND or OR).
        All date/datetime values are treated as UTC.
        """
        conditions = []

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

        # Date from filter (UTC)
        if filters.get('date_from'):
            date_from = filters['date_from']
            if filters.get('date_from_is_datetime'):
                # datetime - use as-is
                date_from_str = fields.Datetime.to_string(date_from)
            else:
                # date - use start of day (00:00:00 UTC)
                date_from_str = fields.Datetime.to_string(
                    datetime.combine(date_from, time.min)
                )
            conditions.append(('appointment_date', '>=', date_from_str))

        # Date to filter (UTC)
        if filters.get('date_to'):
            date_to = filters['date_to']
            if filters.get('date_to_is_datetime'):
                # datetime - use as-is
                date_to_str = fields.Datetime.to_string(date_to)
            else:
                # date - use end of day (23:59:59 UTC)
                date_to_str = fields.Datetime.to_string(
                    datetime.combine(date_to, time.max)
                )
            conditions.append(('appointment_date', '<=', date_to_str))

        if not conditions:
            return []

        return conditions

    def _build_search_domain(self, filters):
        """Build search-specific domain from parsed filters.

        Handles search parameters: customer, co_applicant, name, id.
        All search conditions are combined with AND logic.
        Priority-based matching is used for customer and co_applicant.

        Returns tuple: (search_conditions, all_priority_domains)
        - search_conditions: simple domain conditions (like id=X)
        - all_priority_domains: list of (domain, priority) tuples for priority search
        """
        search_conditions = []
        all_priority_domains = []

        # ID search (exact match)
        if filters.get('id'):
            search_conditions.append(('id', '=', filters['id']))

        # Name search (partial match)
        if filters.get('name'):
            name_domains = self._build_name_search_domain(filters['name'])
            all_priority_domains.extend(name_domains)

        # Customer search (priority-based partial match)
        if filters.get('customer'):
            customer_domains = self._build_customer_search_domain(filters['customer'])
            all_priority_domains.extend(customer_domains)

        # Co-applicant search (priority-based partial match)
        if filters.get('co_applicant'):
            co_applicant_domains = self._build_co_applicant_search_domain(filters['co_applicant'])
            all_priority_domains.extend(co_applicant_domains)

        return search_conditions, all_priority_domains

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

    def _apply_filter_logic(self, conditions):
        """Apply AND logic to domain conditions."""
        if not conditions:
            return []

        # Handle market segments OR separately (multiple values in same field)
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

            if final_conditions:
                result = ['&'] * len(final_conditions)
                result.extend(market_domain)
                result.extend(final_conditions)
                return result
            else:
                return market_domain

        return final_conditions

    def _build_filters_response(self, filters):
        """Build filters metadata for response."""
        result = {}
        # Filter parameters
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
        if filters.get('order'):
            result['order'] = filters['order']
        # Search parameters
        if filters.get('customer'):
            result['customer'] = filters['customer']
        if filters.get('co_applicant'):
            result['co_applicant'] = filters['co_applicant']
        if filters.get('name'):
            result['name'] = filters['name']
        if filters.get('id'):
            result['id'] = filters['id']
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

        # Validate id parameter
        if filters.get('id_invalid'):
            _logger.warning(
                "%s: Invalid id '%s' from admin_user_id=%s",
                endpoint_name, filters['id_invalid'], admin_user_id
            )
            return ({
                "error": "invalid_request",
                "error_description": f"Invalid id value '{filters['id_invalid']}'. Must be a valid integer."
            }, 400)

        return None

    # =========================================================================
    # List Appointments
    # =========================================================================

    @http.route("/api/admin/appointments", auth="none", methods=["GET"], csrf=False)
    @json_response
    def list_appointments(self, **kwargs):
        """List all appointments with optional filters.

        Admin-only endpoint. Returns all appointments matching filters.
        All filters are combined with AND logic.
        All date/datetime values are treated as UTC.

        Query params:
            Filters (AND logic):
                market_segment: Filter by market segment (comma-separated for multiple)
                user_id: Filter by salesperson/user ID (Odoo user ID)
                improveit_user_id: Filter by Salesforce user ID (used if user_id not provided)
                status: Filter by status (draft, scheduled, canceled, done)
                date_from: Filter from date in UTC (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)
                date_to: Filter to date in UTC (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)

            Search (AND logic with filters):
                customer: Search in customer name fields (partial match, priority-based)
                co_applicant: Search in co-applicant name fields (partial match, priority-based)
                name: Search in appointment reference (partial match)
                id: Search by appointment ID (exact match)

            Pagination:
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
        base_domain = self._build_domain(filters)
        order_clause = filters.get('order_clause', DEFAULT_ORDER)

        # Build search domain
        search_conditions, priority_domains = self._build_search_domain(filters)
        _logger.info(
            "AdminAppointments.list: search_conditions=%s, priority_domains_count=%s",
            search_conditions, len(priority_domains) if priority_domains else 0
        )

        # Parse pagination
        page, per_page, err = self._parse_pagination(kwargs)
        if err:
            return err

        # Query appointments
        appt_model = request.env['team.customer.appointment'].sudo()

        # Combine base domain with simple search conditions
        domain = base_domain + search_conditions

        # Handle priority-based searches (all domains are OR'd together)
        if priority_domains:
            result_domain = self._execute_priority_search(
                domain, priority_domains, appt_model, order_clause
            )
            if result_domain is not None:
                domain = result_domain
            _logger.info(
                "AdminAppointments.list: Applied priority search, domain=%s",
                domain
            )

        _logger.info("AdminAppointments.list: final domain=%s", domain)
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

        Admin-only endpoint. Returns appointments for today in UTC.
        All filters are combined with AND logic.

        Query params:
            Filters (AND logic):
                market_segment: Filter by market segment (comma-separated for multiple)
                user_id: Filter by salesperson/user ID (Odoo user ID)
                improveit_user_id: Filter by Salesforce user ID (used if user_id not provided)
                status: Filter by status (draft, scheduled, canceled, done)

            Search (AND logic with filters):
                customer: Search in customer name fields (partial match, priority-based)
                co_applicant: Search in co-applicant name fields (partial match, priority-based)
                name: Search in appointment reference (partial match)
                id: Search by appointment ID (exact match)

            Pagination:
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

        # Get today's date range in UTC
        today_utc = datetime.now(timezone.utc).date()
        start_str = fields.Datetime.to_string(datetime.combine(today_utc, time.min))
        end_str = fields.Datetime.to_string(datetime.combine(today_utc, time.max))

        # Remove date filters (we use today's date)
        filters.pop('date_from', None)
        filters.pop('date_to', None)

        # Build domains
        date_domain = [('appointment_date', '>=', start_str), ('appointment_date', '<=', end_str)]
        additional_domain = self._build_domain(filters)
        base_domain = date_domain + additional_domain

        # Build search domain
        search_conditions, priority_domains = self._build_search_domain(filters)
        _logger.info(
            "AdminAppointments.today: search_conditions=%s, priority_domains_count=%s",
            search_conditions, len(priority_domains) if priority_domains else 0
        )

        # Parse pagination
        page, per_page, err = self._parse_pagination(kwargs)
        if err:
            return err

        # Query appointments
        appt_model = request.env['team.customer.appointment'].sudo()

        # Combine base domain with simple search conditions
        domain = base_domain + search_conditions

        # Handle priority-based searches (all domains are OR'd together)
        if priority_domains:
            result_domain = self._execute_priority_search(
                domain, priority_domains, appt_model, order_clause
            )
            if result_domain is not None:
                domain = result_domain
            _logger.info(
                "AdminAppointments.today: Applied priority search, domain=%s",
                domain
            )

        _logger.info("AdminAppointments.today: final domain=%s", domain)
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
            'date': str(today_utc),
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

    @http.route("/api/admin/appointments/app_live_screen_logs", auth="none", methods=["POST"], csrf=False)
    @json_response
    def get_bulk_live_screen_logs(self, **kwargs):
        """Get app live screen logs for multiple appointments.

        Admin-only endpoint. Returns logs for multiple appointments at once.
        Supports pagination for the appointments list.

        Request body:
            appointment_ids: List of appointment IDs (required)
            page: Page number (default: 1)
            per_page: Items per page (default: 200, max: 2000)
        """
        _logger.info(
            "AdminAppointments.bulk_live_logs: from=%s",
            request.httprequest.remote_addr
        )

        # Authenticate admin
        admin_user_id, err = self._authenticate_admin()
        if err:
            return err

        # Parse JSON body
        try:
            body = request.get_json_data() if hasattr(request, 'get_json_data') else {}
            if not body:
                body = request.jsonrequest if hasattr(request, 'jsonrequest') else {}
        except Exception as e:
            _logger.debug("Failed to parse JSON body: %s", e)
            body = {}

        # Get appointment_ids from body
        appointment_ids = body.get('appointment_ids', [])
        if not appointment_ids:
            _logger.warning(
                "AdminAppointments.bulk_live_logs: Missing appointment_ids from admin_user_id=%s",
                admin_user_id
            )
            return (
                {
                    "error": "invalid_request",
                    "error_description": "appointment_ids is required and must be a non-empty list"
                },
                400
            )

        # Validate appointment_ids is a list of integers
        if not isinstance(appointment_ids, list):
            return (
                {
                    "error": "invalid_request",
                    "error_description": "appointment_ids must be a list"
                },
                400
            )

        try:
            appointment_ids = [int(aid) for aid in appointment_ids]
        except (ValueError, TypeError):
            return (
                {
                    "error": "invalid_request",
                    "error_description": "appointment_ids must contain only integers"
                },
                400
            )

        # Parse pagination from body
        page = body.get('page', 1)
        per_page = body.get('per_page', DEFAULT_PER_PAGE)
        try:
            page = max(1, int(page))
            per_page = min(max(1, int(per_page)), MAX_PER_PAGE)
        except (ValueError, TypeError):
            page = 1
            per_page = DEFAULT_PER_PAGE

        # Calculate pagination for appointment IDs
        total_appointments = len(appointment_ids)
        offset = (page - 1) * per_page
        paginated_ids = appointment_ids[offset:offset + per_page]

        # Load appointments
        appt_model = request.env['team.customer.appointment'].sudo()
        appointments = appt_model.browse(paginated_ids)

        # Build response for each appointment
        results = []
        total_logs = 0
        total_time_spent_seconds = 0
        appointments_with_time = 0
        
        for appt_id in paginated_ids:
            appointment = appointments.filtered(lambda a: a.id == appt_id)
            logs_data = []
            screen_entry_times = []
            
            if appointment.exists():
                logs = getattr(appointment, 'app_live_screen_log_line', []) or []
                for log in logs:
                    try:
                        logs_data.append(self._serialize_live_screen_log(log))
                        # Collect screen_entry_date for time calculation
                        entry_date = getattr(log, 'screen_entry_date', None)
                        if entry_date:
                            screen_entry_times.append(entry_date)
                    except (AttributeError, TypeError) as e:
                        _logger.debug("Failed to serialize live screen log: %s", e)
                        continue
            
            # Calculate time spent based on earliest and latest screen_entry_date
            time_spent_seconds = 0
            if len(screen_entry_times) >= 2:
                earliest = min(screen_entry_times)
                latest = max(screen_entry_times)
                time_diff = latest - earliest
                time_spent_seconds = int(time_diff.total_seconds())
                total_time_spent_seconds += time_spent_seconds
                appointments_with_time += 1
            
            total_logs += len(logs_data)
            results.append({
                'appointment_id': appt_id,
                'logs_count': len(logs_data),
                'time_spent_seconds': time_spent_seconds,
                'app_live_screen_logs': logs_data,
            })

        # Calculate average time spent (only for appointments that have time data)
        average_time_spent_seconds = 0
        if appointments_with_time > 0:
            average_time_spent_seconds = round(total_time_spent_seconds / appointments_with_time, 2)

        _logger.info(
            "AdminAppointments.bulk_live_logs: Success admin_user_id=%s total_appointments=%s page=%s per_page=%s appointments_returned=%s total_logs=%s total_time=%s avg_time=%s",
            admin_user_id, total_appointments, page, per_page, len(results), total_logs, total_time_spent_seconds, average_time_spent_seconds
        )

        return ({
            'admin_user_id': admin_user_id,
            'total_appointments': total_appointments,
            'count': len(results),
            'page': page,
            'per_page': per_page,
            'total_logs': total_logs,
            'total_time_spent_seconds': total_time_spent_seconds,
            'average_time_spent_seconds': average_time_spent_seconds,
            'appointments': results,
        }, 200)

    # =========================================================================
    # Analytics
    # =========================================================================

    @http.route("/api/admin/appointments/analytics", auth="none", methods=["GET"], csrf=False)
    @json_response
    def get_analytics(self, **kwargs):
        """Get time analytics for appointments.

        Admin-only endpoint. Returns aggregated time metrics for appointments
        based on optional filters.

        Query params:
            market_segment: (optional) Comma-separated list of market segments
            user_id: (optional) Comma-separated list of Odoo user IDs
            improveit_user_id: (optional) Comma-separated list of Salesforce user IDs
            date_from: (optional) Start date in UTC (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)
            date_to: (optional) End date in UTC (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)
        """
        _logger.info(
            "AdminAppointments.analytics: from=%s",
            request.httprequest.remote_addr
        )

        # Authenticate admin
        admin_user_id, err = self._authenticate_admin()
        if err:
            return err

        # Parse filters
        filters_applied = {}

        # Parse market_segment (comma-separated)
        market_segment_param = kwargs.get('market_segment') or request.params.get('market_segment')
        market_segments = None
        if market_segment_param:
            market_segments = [s.strip() for s in market_segment_param.split(',') if s.strip()]
            if market_segments:
                filters_applied['market_segments'] = market_segments

        # Parse user_id (comma-separated)
        user_id_param = kwargs.get('user_id') or request.params.get('user_id')
        user_ids = None
        if user_id_param:
            try:
                user_ids = [int(uid.strip()) for uid in user_id_param.split(',') if uid.strip()]
                if user_ids:
                    filters_applied['user_ids'] = user_ids
            except (ValueError, TypeError):
                _logger.warning("AdminAppointments.analytics: Invalid user_id format: %s", user_id_param)

        # Parse improveit_user_id (comma-separated) - resolve to Odoo user IDs
        improveit_user_id_param = kwargs.get('improveit_user_id') or request.params.get('improveit_user_id')
        if improveit_user_id_param and not user_ids:
            improveit_ids = [uid.strip() for uid in improveit_user_id_param.split(',') if uid.strip()]
            if improveit_ids:
                user_model = request.env['res.users'].sudo()
                resolved_users = user_model.search([('improveit_user_id', 'in', improveit_ids)])
                if resolved_users:
                    user_ids = resolved_users.ids
                    filters_applied['user_ids'] = user_ids
                    filters_applied['improveit_user_ids'] = improveit_ids
                else:
                    # No users found for given improveit_user_ids - return empty results
                    _logger.info(
                        "AdminAppointments.analytics: No users found for improveit_user_ids=%s",
                        improveit_ids
                    )
                    return ({
                        'admin_user_id': admin_user_id,
                        'filters': {'improveit_user_ids': improveit_ids},
                        'total_appointments': 0,
                        'appointments_with_logs': 0,
                        'appointments_without_logs': 0,
                        'total_time_spent_seconds': 0,
                        'average_time_spent_seconds': 0,
                        'min_time_spent_seconds': 0,
                        'max_time_spent_seconds': 0,
                    }, 200)

        # Parse date_from
        date_from_param = kwargs.get('date_from') or request.params.get('date_from')
        date_from = None
        if date_from_param:
            try:
                try:
                    date_from = datetime.strptime(date_from_param, '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    date_from = datetime.strptime(date_from_param, '%Y-%m-%d')
                    date_from = datetime.combine(date_from.date(), time.min)
                filters_applied['date_from'] = date_from_param
            except (ValueError, TypeError):
                _logger.warning("AdminAppointments.analytics: Invalid date_from format: %s", date_from_param)

        # Parse date_to
        date_to_param = kwargs.get('date_to') or request.params.get('date_to')
        date_to = None
        if date_to_param:
            try:
                try:
                    date_to = datetime.strptime(date_to_param, '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    date_to = datetime.strptime(date_to_param, '%Y-%m-%d')
                    date_to = datetime.combine(date_to.date(), time.max)
                filters_applied['date_to'] = date_to_param
            except (ValueError, TypeError):
                _logger.warning("AdminAppointments.analytics: Invalid date_to format: %s", date_to_param)

        # Build domain
        domain = []
        if market_segments:
            if len(market_segments) == 1:
                domain.append(('market_segment', '=', market_segments[0]))
            else:
                domain.append(('market_segment', 'in', market_segments))
        if user_ids:
            if len(user_ids) == 1:
                domain.append(('user_id', '=', user_ids[0]))
            else:
                domain.append(('user_id', 'in', user_ids))
        if date_from:
            domain.append(('appointment_date', '>=', fields.Datetime.to_string(date_from)))
        if date_to:
            domain.append(('appointment_date', '<=', fields.Datetime.to_string(date_to)))

        # Query appointments
        appt_model = request.env['team.customer.appointment'].sudo()
        appointments = appt_model.search(domain)

        # Calculate time metrics
        total_appointments = len(appointments)
        total_time_spent_seconds = 0
        appointments_with_logs = 0
        appointments_without_logs = 0
        time_spent_list = []

        for appointment in appointments:
            logs = getattr(appointment, 'app_live_screen_log_line', []) or []
            screen_entry_times = []
            
            for log in logs:
                entry_date = getattr(log, 'screen_entry_date', None)
                if entry_date:
                    screen_entry_times.append(entry_date)
            
            if len(screen_entry_times) >= 2:
                earliest = min(screen_entry_times)
                latest = max(screen_entry_times)
                time_diff = latest - earliest
                time_spent = int(time_diff.total_seconds())
                total_time_spent_seconds += time_spent
                time_spent_list.append(time_spent)
                appointments_with_logs += 1
            else:
                appointments_without_logs += 1

        # Calculate aggregates
        average_time_spent_seconds = 0
        min_time_spent_seconds = 0
        max_time_spent_seconds = 0
        
        if time_spent_list:
            average_time_spent_seconds = round(total_time_spent_seconds / len(time_spent_list), 2)
            min_time_spent_seconds = min(time_spent_list)
            max_time_spent_seconds = max(time_spent_list)

        _logger.info(
            "AdminAppointments.analytics: Success admin_user_id=%s total=%s with_logs=%s without_logs=%s total_time=%s avg_time=%s",
            admin_user_id, total_appointments, appointments_with_logs, appointments_without_logs,
            total_time_spent_seconds, average_time_spent_seconds
        )

        response = {
            'admin_user_id': admin_user_id,
            'total_appointments': total_appointments,
            'appointments_with_logs': appointments_with_logs,
            'appointments_without_logs': appointments_without_logs,
            'total_time_spent_seconds': total_time_spent_seconds,
            'average_time_spent_seconds': average_time_spent_seconds,
            'min_time_spent_seconds': min_time_spent_seconds,
            'max_time_spent_seconds': max_time_spent_seconds,
        }
        
        if filters_applied:
            response['filters'] = filters_applied

        return (response, 200)

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

        response = {'admin_user_id': admin_user_id, 'count': len(segments), 'market_segments': segments}
        if filter_user_id:
            response['user_id'] = filter_user_id

        return (response, 200)

    # =========================================================================
    # Salespersons
    # =========================================================================

    @http.route("/api/admin/salespersons", auth="none", methods=["GET"], csrf=False)
    @json_response
    def list_salespersons(self, **kwargs):
        """List salespersons filtered by market segment.

        Admin-only endpoint. Returns unique salespersons who have appointments
        in the specified market segment(s). If no market_segment is provided,
        returns all salespersons from all appointments.

        Query params:
            market_segment: (optional) Comma-separated list of market segments
        """
        _logger.info(
            "AdminAppointments.salespersons: from=%s",
            request.httprequest.remote_addr
        )

        # Authenticate admin
        admin_user_id, err = self._authenticate_admin()
        if err:
            return err

        # Parse market_segment parameter (optional)
        market_segment_param = kwargs.get('market_segment') or request.params.get('market_segment')
        market_segments = None
        if market_segment_param:
            market_segments = [s.strip() for s in market_segment_param.split(',') if s.strip()]
            if not market_segments:
                market_segments = None

        # Build domain for appointments with a user assigned
        domain = [('user_id', '!=', False)]
        if market_segments:
            if len(market_segments) == 1:
                domain.append(('market_segment', '=', market_segments[0]))
            else:
                domain.append(('market_segment', 'in', market_segments))

        # Query appointments and collect unique user IDs
        appt_model = request.env['team.customer.appointment'].sudo()
        try:
            # Use read_group to get distinct user_ids efficiently
            groups = appt_model.read_group(
                domain=domain,
                fields=['user_id'],
                groupby=['user_id'],
            )
            user_ids = [g['user_id'][0] for g in groups if g.get('user_id')]
        except Exception as e:
            _logger.debug("read_group failed for salespersons: %s, falling back to search", e)
            try:
                appointments = appt_model.search(domain)
                user_ids = list(set(a.user_id.id for a in appointments if a.user_id))
            except Exception as e2:
                _logger.error("AdminAppointments.salespersons: Failed to query appointments: %s", e2)
                user_ids = []

        # Fetch user details
        salespersons = []
        if user_ids:
            user_model = request.env['res.users'].sudo()
            users = user_model.browse(user_ids).exists()
            for user in users:
                salespersons.append({
                    'id': user.id,
                    'improveit_user_id': user.improveit_user_id or None,
                    'name': user.name or None,
                    'login': user.login or None,
                })
            # Sort by name for consistent ordering
            salespersons.sort(key=lambda x: (x.get('name') or '').lower())

        # If no market_segment filter, get all available market segments
        response_market_segments = market_segments
        if not market_segments:
            try:
                segment_groups = appt_model.read_group(
                    domain=[('market_segment', '!=', False)],
                    fields=['market_segment'],
                    groupby=['market_segment'],
                )
                response_market_segments = sorted([
                    g['market_segment'] for g in segment_groups if g.get('market_segment')
                ])
            except Exception as e:
                _logger.debug("read_group failed for all market_segments: %s", e)
                try:
                    all_appts = appt_model.search([('market_segment', '!=', False)])
                    response_market_segments = sorted(set(
                        a.market_segment for a in all_appts if a.market_segment
                    ))
                except Exception as e2:
                    _logger.debug("search fallback failed for all market_segments: %s", e2)
                    response_market_segments = []

        _logger.info(
            "AdminAppointments.salespersons: market_segments=%s count=%s admin_user_id=%s",
            market_segments, len(salespersons), admin_user_id
        )

        response = {
            'count': len(salespersons),
            'market_segments': response_market_segments,
            'salespersons': salespersons,
        }

        return (response, 200)

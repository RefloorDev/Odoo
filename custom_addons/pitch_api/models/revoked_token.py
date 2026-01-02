# -*- coding: utf-8 -*-
"""Revoked Token Model for Pitch API.

This module tracks revoked access tokens to prevent their reuse.
Access tokens are short-lived JWTs, but we need to track revoked ones
until their natural expiry to prevent use of leaked/stolen tokens.
"""

import datetime
import logging
from datetime import timezone

from odoo import models, fields, api

_logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================

GC_THRESHOLD_DAYS = 7  # Keep revoked tokens for 7 days max


# =============================================================================
# Revoked Token Model
# =============================================================================

class AuthRevokedToken(models.Model):
    """Track revoked access tokens.

    Access tokens (JWTs) are stateless by design, but we need to
    maintain a revocation list to handle:
    - User logout (invalidate current access token)
    - Password changes (invalidate all tokens)
    - Suspicious activity (emergency revocation)
    - Administrative actions (force logout)

    The jti (JWT ID) claim in each access token is checked against
    this table during authentication.
    """

    _name = "auth.revoked.token"
    _description = "Revoked API Access Token"
    _order = "revoked_at desc"

    # =========================================================================
    # Fields
    # =========================================================================

    jti = fields.Char(
        string="JWT ID",
        required=True,
        index=True,
        help="Unique identifier (jti claim) of the revoked JWT"
    )

    user_id = fields.Many2one(
        'res.users',
        string="User",
        required=True,
        ondelete='cascade',
        index=True,
        help="User who owned this token"
    )

    revoked_at = fields.Datetime(
        string="Revoked At",
        required=True,
        default=lambda self: fields.Datetime.now(),
        help="When the token was revoked"
    )

    expires_at = fields.Datetime(
        string="Original Expiry",
        required=True,
        help="When the token would have naturally expired"
    )

    reason = fields.Selection(
        selection=[
            ('logout', 'User Logout'),
            ('password_change', 'Password Changed'),
            ('admin_action', 'Administrative Action'),
            ('suspicious', 'Suspicious Activity'),
            ('session_expired', 'Session Expired'),
            ('new_login', 'New Login'),
        ],
        string="Revocation Reason",
        default='logout',
        help="Why the token was revoked"
    )

    ip_address = fields.Char(
        string="IP Address",
        help="IP address when token was revoked"
    )

    # =========================================================================
    # SQL Constraints
    # =========================================================================

    _sql_constraints = [
        ('jti_unique', 'UNIQUE(jti)', 'JWT ID must be unique'),
    ]

    # =========================================================================
    # Token Revocation
    # =========================================================================

    @api.model
    def revoke_token(self, jti, user_id, expires_at, reason='logout', ip_address=None):
        """Revoke an access token by its JWT ID.

        Args:
            jti: JWT ID claim from the access token.
            user_id: ID of the token owner.
            expires_at: When the token would naturally expire.
            reason: Why the token is being revoked.
            ip_address: IP address of the revocation request.

        Returns:
            record: Created or existing revocation record.
        """
        # Check if already revoked (idempotent operation)
        existing = self.sudo().search([('jti', '=', jti)], limit=1)
        if existing:
            _logger.debug(
                "Token already revoked: jti=%s user_id=%s",
                jti, user_id
            )
            return existing

        # Convert expires_at if string
        if isinstance(expires_at, str):
            expires_at = fields.Datetime.from_string(expires_at)
        elif isinstance(expires_at, (int, float)):
            # Use timezone-aware datetime (Python 3.12+ compatible)
            expires_at = datetime.datetime.fromtimestamp(expires_at, tz=timezone.utc).replace(tzinfo=None)

        record = self.sudo().create({
            'jti': jti,
            'user_id': user_id,
            'expires_at': expires_at,
            'reason': reason,
            'ip_address': ip_address,
        })

        _logger.info(
            "Revoked access token: jti=%s user_id=%s reason=%s",
            jti, user_id, reason
        )

        return record

    @api.model
    def is_revoked(self, jti):
        """Check if a JWT ID has been revoked.

        Args:
            jti: JWT ID claim to check.

        Returns:
            bool: True if token is revoked, False otherwise.
        """
        return bool(self.sudo().search_count([('jti', '=', jti)], limit=1))

    @api.model
    def revoke_all_for_user(self, user_id, reason='admin_action', ip_address=None):
        """Mark all tokens for a user as requiring revocation.

        Note: This records the intent - actual tokens must be
        tracked individually when issued.

        For immediate effect on existing tokens, the application
        should check user's password_write_date or a dedicated
        'tokens_revoked_at' field.

        Args:
            user_id: User ID to revoke tokens for.
            reason: Revocation reason.
            ip_address: IP address of request.

        Returns:
            bool: True on success.
        """
        _logger.info(
            "Bulk token revocation requested: user_id=%s reason=%s",
            user_id, reason
        )
        return True

    # =========================================================================
    # Garbage Collection
    # =========================================================================

    @api.autovacuum
    def _gc_revoked_tokens(self):
        """Garbage collect old revocation records.

        Removes records for tokens that:
        1. Have passed their original expiry time
        2. Are older than the GC threshold

        This prevents the revocation table from growing indefinitely.
        """
        now = fields.Datetime.now()
        threshold = fields.Datetime.to_string(
            fields.Datetime.from_string(now) -
            datetime.timedelta(days=GC_THRESHOLD_DAYS)
        )

        # Remove records where token would have expired anyway
        expired_records = self.search([
            '|',
            ('expires_at', '<', now),
            ('revoked_at', '<', threshold)
        ])

        if expired_records:
            count = len(expired_records)
            expired_records.unlink()
            _logger.info("Garbage collected %s expired revocation records", count)

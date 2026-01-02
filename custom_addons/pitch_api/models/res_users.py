# -*- coding: utf-8 -*-
"""User Extensions for Pitch API.

This module extends res.users to add Pitch API specific fields
and functionality.
"""

import logging

from odoo import models, fields, api
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    """Extend res.users with Pitch API admin flag.

    The is_pitch_admin field designates a user as the API administrator
    with elevated privileges for managing API configuration, monitoring,
    and administrative endpoints.

    Only one user can be the Pitch admin at any time.
    """

    _inherit = 'res.users'

    # =========================================================================
    # Fields
    # =========================================================================

    is_pitch_admin = fields.Boolean(
        string="Pitch API Admin",
        default=False,
        help="Designate this user as the Pitch API administrator. "
             "Only one user can have this role at a time."
    )

    # =========================================================================
    # Constraints
    # =========================================================================

    @api.constrains('is_pitch_admin')
    def _check_single_pitch_admin(self):
        """Ensure only one user can be the Pitch admin.

        Raises:
            ValidationError: If another user is already the admin.
        """
        for user in self:
            if user.is_pitch_admin:
                existing = self.sudo().search([
                    ('is_pitch_admin', '=', True),
                    ('id', '!=', user.id)
                ], limit=1)
                if existing:
                    raise ValidationError(
                        f"User '{existing.name}' is already designated as "
                        "the Pitch API Admin. Please remove their admin "
                        "status before assigning it to another user."
                    )

    # =========================================================================
    # Helper Methods
    # =========================================================================

    @api.model
    def get_pitch_admin(self):
        """Get the current Pitch API admin user.

        Returns:
            record: The admin user record, or empty recordset.
        """
        return self.sudo().search([
            ('is_pitch_admin', '=', True)
        ], limit=1)

    def is_current_user_pitch_admin(self):
        """Check if the current user is the Pitch admin.

        Returns:
            bool: True if current user is admin.
        """
        return self.env.user.is_pitch_admin

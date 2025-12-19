# -*- coding: utf-8 -*-
"""Extend res.users with Pitch API admin flag.

This extension adds a boolean field `is_pitch_admin` which designates
the single Pitch API administrator with elevated privileges.
"""

from odoo import models, fields, api
from odoo.exceptions import ValidationError


class ResUsers(models.Model):
    _inherit = 'res.users'

    is_pitch_admin = fields.Boolean(
        string='Pitch API Admin',
        default=False,
        help='Designates the single Pitch API administrator (at most one user can have this set)'
    )

    @api.model_create_multi
    def create(self, vals_list):
        # Pre-validation: block creation of a new admin if one already exists
        existing_admin_count = self.env['res.users'].sudo().search_count([('is_pitch_admin', '=', True)])
        # If any incoming record tries to set is_pitch_admin True while one exists, reject
        if existing_admin_count:
            for vals in vals_list:
                if vals.get('is_pitch_admin'):
                    raise ValidationError('A Pitch API Admin already exists. Unset the current admin before assigning a new one.')
        # Also prevent batch creation of multiple admins even if none existed yet
        proposed_admins = sum(1 for v in vals_list if v.get('is_pitch_admin'))
        if proposed_admins > 1:
            raise ValidationError('Only one user can be created as Pitch API Admin. Create one admin at a time.')
        return super().create(vals_list)

    def write(self, vals):
        # If attempting to set admin True, ensure no other admin exists
        if vals.get('is_pitch_admin'):
            # If setting to True
            if vals['is_pitch_admin']:
                for rec in self:
                    other_admins = self.env['res.users'].sudo().search([('id', '!=', rec.id), ('is_pitch_admin', '=', True)], limit=1)
                    if other_admins:
                        raise ValidationError('Cannot assign Pitch API Admin: another admin already exists. Remove the existing admin flag first.')
            # If setting to False we allow (may free slot for new admin)
        return super().write(vals)

    @api.constrains('is_pitch_admin')
    def _check_single_pitch_admin(self):
        # Defensive check for race conditions: ensure at most one admin
        admins = self.env['res.users'].sudo().search_count([('is_pitch_admin', '=', True)])
        if admins > 1:
            raise ValidationError('Only one user can be marked as Pitch API Admin at a time.')

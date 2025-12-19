# -*- coding: utf-8 -*-
"""Wizard for granting Pitch API access to selected users."""

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError


_LOGGER = logging.getLogger(__name__)


class PitchApiAccessWizard(models.TransientModel):
    _name = "pitch.api.access.wizard"
    _description = "Grant Pitch API Admin Access"

    user_ids = fields.Many2many('res.users', string='Users', domain=[('active','=',True), ('share','=',False), ('is_pitch_admin','=',False)])

    def action_grant_access(self):
        self.ensure_one()
        selected_lines = self.user_ids
        if not selected_lines:
            raise UserError(_("Please select at least one user to grant Pitch API admin access."))

        users_to_update = selected_lines.with_context(active_test=False).sudo()
        if not users_to_update:
            raise UserError(_("No eligible users were selected."))

        users_to_update.write({"is_pitch_admin": True})
        _LOGGER.info("Pitch API admin access granted to %s user(s): %s", len(users_to_update), ", ".join(users_to_update.mapped("name")))

        action = self.env.ref("pitch_api.action_pitch_api_users", raise_if_not_found=False)
        if action:
            return action.read()[0]
        return {"type": "ir.actions.act_window_close"}


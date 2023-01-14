# Copyright (C) 2019 Open Source Integrators
# <https://www.opensourceintegrators.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    def _get_default_tz(self):
        tz = self._context.get('tz')
        default_tz = self.env['ir.config_parameter'].sudo().get_param('otl_default_user_tz.default_tz')
        if default_tz:
            tz = default_tz
        return tz

    tz = fields.Selection(_default=_get_default_tz)


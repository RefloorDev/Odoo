# -*- coding: utf-8 -*-
import pytz
from odoo import api, fields, models

_tzs = [(tz, tz) for tz in sorted(pytz.all_timezones, key=lambda tz: tz if not tz.startswith('Etc/') else '_')]


class ResPartner(models.Model):
    _inherit = "res.partner"

    @api.model
    def _get_default_tz(self):
        tz = self._context.get('tz')
        default_tz = self.env['ir.config_parameter'].sudo().get_param('otl_default_user_tz.default_tz')
        return default_tz or tz or 'UTC'

    tz = fields.Selection(_tzs, string="Timezone", default=_get_default_tz)

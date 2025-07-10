# -*- coding: utf-8 -*-
from odoo import fields, models, api, _
import time
from odoo.exceptions import UserError
import pytz

_tzs = [(tz, tz) for tz in sorted(pytz.all_timezones, key=lambda tz: tz if not tz.startswith('Etc/') else '_')]
def _tz_get(self):
    return _tzs

class ResCompany(models.Model):
    _inherit = 'res.company'
    
    default_tz = fields.Selection(_tzs, 'Default Timezone')


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    default_tz = fields.Selection(selection=_tzs, string="Default Timezone", default=lambda self: self.company_id.default_tz, default_model='res.partner', config_parameter='otl_default_user_tz.default_tz')

# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models, api, _
import time
from odoo.exceptions import UserError
import pytz

_tzs = [(tz, tz) for tz in sorted(pytz.all_timezones, key=lambda tz: tz if not tz.startswith('Etc/') else '_')]
def _tz_get(self):
    return _tzs

class ResCompany(models.Model):
    _inherit = 'res.company'
    
    default_tz = fields.Selection(_tzs, 'Default Timezone', default_model='res.partner')



class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    default_tz = fields.Selection(_tzs, 'Default Timezone', default_model='res.partner', related='company_id.default_tz', readonly=False)




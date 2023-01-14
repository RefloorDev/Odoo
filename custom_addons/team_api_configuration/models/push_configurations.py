# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class PushConfiguration(models.Model):
    _name = 'push.configuration'
    _description = "Push Configurations"

    name = fields.Selection([('crm', 'CRM'),
                             ('leave', 'Leave'),
                             ('messaging', 'Messaging')], required=True, string="Category")
    is_activity = fields.Boolean('Activity Reminder')
    is_won = fields.Boolean('State to WON')
    leave_approve = fields.Boolean('Leave Approve')
    leave_reject = fields.Boolean('Leave Reject')
    active = fields.Boolean('Active', default=True)

    @api.constrains('name')
    def check_name(self):
        for record in self:
            if record.name:
                if self.search([('name', '=', record.name), ('id', '!=', record.id)]):
                    raise ValidationError("Entered Name is already existing. Please choose different name.")
        return True

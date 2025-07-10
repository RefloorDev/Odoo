# -*- coding: utf-8 -*-
from odoo import fields, models

class Users(models.Model):
    _inherit = 'res.users'

    improveit_user_id = fields.Char(string='i360 Salesperson ID')

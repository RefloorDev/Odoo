# -*- coding: utf-8 -*-
from odoo import fields, models

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    improveit_product_id = fields.Char(string='i360 ReferenceID')

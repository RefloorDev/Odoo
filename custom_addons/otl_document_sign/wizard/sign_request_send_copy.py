# -*- coding: utf-8 -*-

from odoo import api, fields, models

class SignRequestSendCopy(models.TransientModel):
    _name = 'otl_document_sign.request.send.copy'
    _description = 'Sign send request copy'

    @api.model
    def default_get(self, fields):
        res = super(SignRequestSendCopy, self).default_get(fields)
        res['request_id'] = self.env.context.get('active_id')
        return res

    request_id = fields.Many2one('otl_document_sign.request')
    partner_ids = fields.Many2many('res.partner', string="Contact")

    def send_a_copy(self):
        return self.env['otl_document_sign.request'].add_followers(self.request_id.id, self.partner_ids.ids)

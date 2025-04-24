# -*- coding: utf-8 -*-

from odoo import fields, models ,api
from odoo.exceptions import UserError


class Otl_Document_Sign_Wizard(models.TransientModel):
    _name = 'otl.document.otl_document_sign.wizard'
    _description = 'Create Sign Template'

    model_id = fields.Many2one('ir.model', string='Model')
    upload_data = fields.Binary('Upload File')
    file_name = fields.Char('File Name')

    def upload_template(self):
        for record in self:
            if record.upload_data:
                attachment = self.env['ir.attachment'].create({
                    'name': record.file_name,
                    'datas': record.upload_data,
                    'store_fname': record.file_name,
                })
                if attachment:
                    if attachment.mimetype not in ['application/pdf', 'application/x-pdf']:
                        raise UserError('Please upload a valid PDF file.')
                    sign_template = self.env['otl_document_sign.template'].create({
                        'name': record.file_name,
                        'attachment_id': attachment.id,
                        'model_id': record.model_id and record.model_id.id or False,
                    })
                    # Need to wrok on this
                    # if sign_template:
                    #     return sign_template.go_to_custom_template()
        return True


    # def set_model(self):
    #     template_model = self.env['otl.document.otl_document_sign.model'].search([],limit=1)
    #     template_model.model=self.model
    #     field_types=self.env['otl_document_sign.item.type'].search([])
    #     for fields in field_types:
    #         if fields.model.id == self.model.id or fields.item_type == 'signature':
    #             fields.show_in_template = True
    #         else:
    #             fields.show_in_template = False
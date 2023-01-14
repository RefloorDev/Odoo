# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields, api, _

import logging
_logger = logging.getLogger(__name__)


class IrAttachment(models.Model):
    _inherit = 'ir.attachment'

    @api.model
    def create_attachment(self, dict):
        attachment_id = False
        list = []
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        if dict.get('image', False):
            attachment = self.env['ir.attachment'].sudo().create({
                'name': dict.get('file_name', 'Attachment'),
                'datas': dict.get('image'),
                'store_fname': dict.get('file_name', 'Attachment'),
            })
            if attachment:
                attachment.generate_access_token()
                if attachment.access_token:
                    list.append({'id': attachment.id,
                                 'name': attachment.name,
                                 'url': base_url + '/web/image/' + str(attachment.id) + '?access_token=' + str(
                                     attachment.access_token)})

        return list

    @api.model
    def unlink_attachment_api(self, data):
        attachment_ids=data.get('attachment_ids',[])
        if not attachment_ids:
            _logger.info("------Attachment ID Empty------------")
            status = {
                'message': 'Attachment ID Empty',
                'result': 'Failed',
            }
        for attachment_id in attachment_ids:
            attachment = self.sudo().search([('id', '=', attachment_id)])
            if attachment:
                attachment.sudo().unlink()
                _logger.info("------Attachment Deleted------------")
                status = {
                    'message': 'Attachment Removed',
                    'result': 'Success',
                }
            else:
                _logger.info("------Attachment Not Found------------")
                status = {
                    'message': 'Attachment Not Found',
                    'result': 'Failed',
                }
        return status


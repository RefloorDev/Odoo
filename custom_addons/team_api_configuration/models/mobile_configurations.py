# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields, api
import logging
import pytz
from odoo.addons.team_api_configuration.pyfcm.fcm import FCMNotification


_logger = logging.getLogger(__name__)


class MobileNotifications(models.Model):

    _name = 'mobile.notifications'
    _order = 'create_date desc'
    _description = "Mobile Notifications"

    name = fields.Char("Description",required=True)
    title = fields.Char("Title")
    res_id = fields.Integer("Record id")
    user_id = fields.Many2one('res.users','Owner')
    res_model = fields.Char('Record Model')
    type = fields.Char('Type')
    active = fields.Boolean('active', default=True)
    attachment_id = fields.Many2one('ir.attachment',string='Image to displayed')
    status = fields.Selection([
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('failed', 'Failed')
    ], string="Status", copy=False, default='draft')

    @api.model
    def get_notify_list(self, values):
        tasks_count = 0
        approval_count = 0
        uid = values.get('user_id', False)
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        # date = values.get('date', False)
        # date = fields.Datetime.from_string(str(date))
        notification_list = self.search([('user_id', '=', int(uid)),
                     # ('create_date', '>', str(date)),
                     ('active', '=', True)], order='create_date desc')
        result = {}
        data = []
        tasks = self.env['mail.activity'].search([('res_model','=','crm.lead'),('user_id','=',int(uid)),('date_deadline','<=',fields.Date.today())])
        result.update({'pending':[{'tasks_pending':len(tasks),'approval_pending':approval_count}]})
        user = self.env['res.users'].search([('id', '=', int(uid))])
        for notification in notification_list:
            if notification.res_model == 'hr.leave':
                if self.env['hr.leave'].search([('id','=',notification.res_id)]):
                    dict = {}
                    if user.tz:
                        tz = pytz.timezone(user.tz) or pytz.utc
                        create_date = pytz.utc.localize(notification.create_date).astimezone(tz)
                    else:
                        create_date = notification.create_date
                    dict['title'] = str(notification.title)
                    dict['name'] = str(notification.name)
                    dict['create_date'] = create_date
                    dict['record_id'] = str(notification.res_id)
                    dict['user_id'] = str(notification.user_id.id)
                    dict['record_model'] = str(notification.res_model)
                    dict['type'] = str(notification.type)
                    url = ''
                    if notification.attachment_id:
                        if not notification.attachment_id.access_token:
                            notification.attachment_id.sudo().generate_access_token()
                        url = base_url + '/web/image/' + str(notification.attachment_id.id) + '?access_token=' + str(notification.attachment_id.access_token)
                        dict['image'] = str(url)
                    else:
                        url = ''
                        dict['image'] = str(url)
                    data.append(dict)
        result.update({'datas':data})
        
        return result

    def push_pyfcm_single(self, company, device_id, message_title, message_body, extra_data=False, device_type=False):
        """
            Send push
        """
        api_key = company.sudo().push_api_key_id
        result = False
        if api_key:
            push_service = FCMNotification(api_key=api_key)
            try:
                result = push_service.notify_single_device(registration_id=device_id, message_title=message_title,
                                                           message_body=message_body, extra_data=extra_data,
                                                           device_type=device_type)
                _logger.info("Push Sent Successfully===="+str(result))
            except:
                self.status = 'failed'
                _logger.info("Push Sent Failed====" + str(result))
        return result





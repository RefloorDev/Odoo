# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging
import pytz

from google.oauth2 import service_account
import google.auth.transport.requests
import json
import requests

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

    def _get_access_token(self, service_account_file):
        """
        Generates access token from credentials.
        If token expires then new access token is generated.
        Returns:
             str: Access token
        """
        token = ''
        # get OAuth 2.0 access token
        try:
            if service_account_file:
                credentials = service_account.Credentials.from_service_account_file(
                    service_account_file,
                    scopes=["https://www.googleapis.com/auth/firebase.messaging"],
                )
            request = google.auth.transport.requests.Request()
            credentials.refresh(request)
            token = credentials.token
        except Exception as e:
            _logger.error('Error while generating push access token: %s' %e)
        return token

    def push_pyfcm_single(self, company, device_id, message_title, message_body, extra_data={}):
        """
            Send push
        """
        api_auth_file_path = company.sudo().get_push_api_auth_file_path()
        push_project_id = company.sudo().push_project_id
        result = False
        if api_auth_file_path and push_project_id:

            push_url = 'https://fcm.googleapis.com/v1/projects/%s/messages:send'%(push_project_id)
            push_access_token = self._get_access_token(api_auth_file_path)
            headers = {
                'Authorization': "Bearer %s"%push_access_token,
                'Content-Type': 'application/json'
            }

            payload = {
                "message": {
                    "token": device_id,
                    "data": extra_data,
                    "apns": {
                        "headers": {
                            "apns-priority": "10"
                        },
                        "payload": {
                            "aps": {
                                "alert": {
                                    "title": message_title,
                                    "body": message_body
                                },
                                "sound": "default"
                            }
                        }
                    }
                }
            }
            try:
                _logger.info('Push Payload--------%s'%(payload))
                response = requests.post(push_url, headers=headers, data=json.dumps(payload))
                result = {
                    'success': True,
                    'result': str(response.text)
                }
                _logger.info("Push Sent Successfully====" + str(result))
            except:
                self.status = 'failed'
                _logger.info("Push Sent Failed====" + str(result))
        return result





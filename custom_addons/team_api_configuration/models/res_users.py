# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
import json
import base64
from odoo.exceptions import UserError

import logging

_logger = logging.getLogger(__name__)


class ChangePasswordUser(models.TransientModel):
    """ A model to configure users in the change password wizard. """
    _inherit = 'change.password.user'

    token_name = fields.Char('Token')

    def change_password_button(self):
        for line in self:
            if not line.new_passwd:
                raise UserError(_("Before clicking on 'Change Password', you have to write a new password."))
            line.user_id.write({'token_name': '', 'password': line.new_passwd})
        # don't keep temporary passwords in the database longer than necessary
        self.write({'token_name': '', 'new_passwd': False})


class ResUsers(models.Model):
    _inherit = 'res.users'

    token_name = fields.Char('Token')
    device_reg_id = fields.Char('Device registered Id')
    can_view_phone_number = fields.Boolean('Can View Phone Number?', default=True)
    enable_force_sync = fields.Boolean("Enable Force Sync", default=False)

    @api.model
    def get_user_roles(self, values):
        uid = values['uid']
        user_roles = []
        category = values['category']
        user = self.env['res.users'].sudo().search([('id', '=', int(uid))])
        if user:
            if category == 'epic':
                if user.has_group('hr_holidays_custom.group_leave_superior_access') or user.has_group(
                        'hr_holidays_custom.group_leave_second_level'):
                    user_roles.append({'leave': 'sla'})
                elif user.has_group('hr_holidays_custom.group_leave_first_level'):
                    user_roles.append({'leave': 'fla'})
                else:
                    user_roles.append({'leave': 'user'})

                if user.has_group('asset_management.group_asset_manager'):
                    user_roles.append({'asset': 'manager'})
                elif user.has_group('asset_management.group_asset_dept_head'):
                    user_roles.append({'asset': 'department_head'})
                else:
                    user_roles.append({'asset': 'user'})
            elif category == 'store':
                pass
        return user_roles

    @api.model
    def verify_api_token(self, values):
        """ retrieve the user corresponding to login (login or email),
            and reset their password
        """
        _logger.info("------------inside verify api token-------------")
        _logger.info("------------Values :" + str(values))
        token = values.get('token' or '')
        id = values.get('id' or '')
        user = False
        result = {
            'user_exists': False,
            'token_status': 'different'

        }
        try:
            user = self.sudo().search([('id', '=', int(id))])
            if user:
                result.update({'id': user.id, 'user_exists': True})
                if user.token_name == token:
                    result.update({'token_status': 'same'})
                elif not user.token_name:
                    result.update({'token_status': 'empty'})
        except:
            user = False
        _logger.info("------------Result :" + str(result))
        return result

    @api.model
    def log_out(self, values):
        """ retrieve the user corresponding to login (login or email),
            and reset their password
        """
        result = []
        password = values.get('password' or '')
        uid = values.get('uid' or '')
        users = self.search([('id', '=', int(uid))])
        if not users:
            return json.dumps({'result': 'Failed', 'message': 'Invalid user'})

        else:
            res = users.write({'device_reg_id': ''})
            result = [{'id': uid}]
        return result

    @api.model
    def change_password_api(self, values):
        """ retrieve the user corresponding to login (login or email),
            and reset their password
        """
        result = []
        new_password = values.get('new_password' or '')
        uid = values.get('uid' or '')
        users = self.search([('id', '=', int(uid))])
        if not users:
            return json.dumps({'result': 'Failed', 'message': 'Invalid user'})

        else:
            res = users.write({'password': new_password, 'token_name': ''})
            result = [{'id': uid}]
        return result

    @api.model
    def forget_password_api(self, values):
        """ retrieve the user corresponding to login (login or email),
            and reset their password
        """
        result = []
        login = values.get('login' or '')
        users = self.search([('login', '=', login)])
        if not users:
            users = self.search([('email', '=', login)])
        if len(users) != 1:
            return {'result': 'Failed', 'message': 'This Email ID is not registered in the system'}
        else:
            res = self.reset_password(login)
            return {
                'result': 'Success',
                'values': '',
                'message': 'Please check your mailbox for password reset instructions.'}

    @api.model
    def update_device_id(self, values):
        login = values.pop('login', False)
        registered_id = values.get('device_reg_id', False)
        user = self.search([('login', '=ilike', login)
                            ])
        users_with_same_device_id = self.search([('device_reg_id', '=', registered_id)
                                                 ])
        for same_id_user in users_with_same_device_id:
            same_id_user.write({'device_reg_id': ''})
        if user:
            res = user.write(values)
            return res

    @api.model
    def get_user_image(self, uid):
        user = self.env['res.users'].search([('id', '=', uid)])
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        url = ''
        if user:
            user_image = self.env['ir.attachment'].search([('res_model', '=', 'res.users'),
                                                           ('res_id', '=', user.id)], limit=1)
            if not user_image:
                user_image = self.env['ir.attachment'].sudo().create({
                    'res_id': user.id,
                    'res_model': 'res.users',
                    'datas': user.image,
                    'name': user.name
                })
            user_image.sudo().write({'datas': user.image})
            if not user_image.access_token:
                user_image.sudo().generate_access_token()
            url = _('%s/web/image/%s?access_token=%s' % (base_url, user_image.id, user_image.access_token))
        _logger.info("------------returning user image-------------")
        _logger.info(str(url))
        return url

    @api.model
    def get_user_name(self, uid):
        return self.env['res.users'].search([('id', '=', uid)]).name

    @api.model
    def get_user_details(self, uid):
        user = self.env['res.users'].search([('id', '=', uid)])
        sales_app_attachment_id = user.company_id.sales_app_attachment_id or False
        contract_logo_attachment_id = user.company_id.contract_logo_attachment_id or False
        login_logo_attachment_id = user.company_id.login_logo_attachment_id or False
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        company_logo_url = ''
        contract_logo_url = ''
        login_logo_url = ''
        company_logo_data = ''
        if sales_app_attachment_id:
            if not sales_app_attachment_id.access_token:
                sales_app_attachment_id.sudo().generate_access_token()
            company_logo_url = _('%s/web/image/%s?access_token=%s' % (base_url, sales_app_attachment_id.id, sales_app_attachment_id.access_token))
            decoded_image = base64.decodebytes(sales_app_attachment_id.datas)

            company_logo_data = base64.b64encode(decoded_image).decode('utf-8')
        if contract_logo_attachment_id:
            if not contract_logo_attachment_id.access_token:
                contract_logo_attachment_id.sudo().generate_access_token()
            contract_logo_url = _('%s/web/image/%s?access_token=%s' % (base_url, contract_logo_attachment_id.id, contract_logo_attachment_id.access_token))
        if login_logo_attachment_id:
            if not login_logo_attachment_id.access_token:
                login_logo_attachment_id.sudo().generate_access_token()
            login_logo_url = _('%s/web/image/%s?access_token=%s' % (base_url, login_logo_attachment_id.id, login_logo_attachment_id.access_token))
        return {
            'user_name': user.name,
            'can_view_phone_number': user.can_view_phone_number and 1 or 0,
            'company_logo_url': company_logo_url,
            'contract_logo_url': contract_logo_url,
            'login_logo_url': login_logo_url,
            'company_logo_data': company_logo_data
        }

    @api.model
    def is_active_user(self, uid):
        user = self.env['res.users'].search([('id', '=', uid), ('active', '=', False)])
        if user:
            return True
        return False

    @api.model
    def get_currency_symbol(self, uid):
        list = []
        user = self.env['res.users'].search([('id', '=', uid)])
        if user:
            list.append({'name': user.company_id.currency_id.name,
                         'symbol': user.company_id.currency_id.symbol,
                         'symbol_position': user.company_id.currency_id.position})
        return list

    @api.model
    def get_current_partner(self, uid):
        user = self.search([('id', '=', uid)])
        if user:
            return user.partner_id.id
        else:
            return ''


class ResCompany(models.Model):
    _inherit = 'res.company'

    push_api_key_id = fields.Char(string='Firebase API key')
    push_api_auth_attachment_id = fields.Many2one('ir.attachment', string='Push API Auth File')
    push_project_id = fields.Char('Push Project ID')


    def get_push_api_auth_file_path(self):
        file_path = ''
        for record in self:
          if record.push_api_auth_attachment_id:
              attachment = record.push_api_auth_attachment_id
              if attachment.store_fname:
                file_path = attachment._full_path(attachment.store_fname)
        return file_path



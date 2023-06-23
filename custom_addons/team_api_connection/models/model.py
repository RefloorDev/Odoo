# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
# import xml.etree.ElementTree as ET
from xml.etree.ElementTree import fromstring, ElementTree
from odoo import models, fields, api, _
import json
from odoo.exceptions import UserError

from odoo.addons.team_api_configuration.controllers.configurations import URL, DB, API_USER_ID, API_USER_PASSWORD
from odoo.http import request
from odoo.addons.payment.controllers.portal import PaymentProcessing
from odoo.addons.payment_authorize.models.authorize_request import AuthorizeAPI
from datetime import datetime,timedelta
import logging
import requests
import pytz
TIMEOUT = 50
from dateutil.relativedelta import relativedelta
from datetime import datetime

from odoo.tools import DEFAULT_SERVER_DATE_FORMAT, DEFAULT_SERVER_DATETIME_FORMAT


def local_2_utc(str_date, tz):
    if str_date:
        timez = 'UTC'
        if tz:
            timez = tz
        local_tz = pytz.timezone(timez)
        datetime_without_tz = datetime.strptime(str_date,
                                                DEFAULT_SERVER_DATETIME_FORMAT)
        datetime_with_tz = local_tz.localize(datetime_without_tz,
                                             is_dst=None)  # No daylight saving time
        datetime_in_utc = datetime_with_tz.astimezone(pytz.utc)
    return datetime_in_utc

def get_week_date(day, tz):
    current_date = fields.Date.today()
    # Checked the first week
    start_date = current_date - relativedelta(days=day)
    end_date = start_date + relativedelta(days=1)
    str_start_date = start_date.strftime('%Y-%m-%d') + ' 00:00:00'
    str_end_date = end_date.strftime('%Y-%m-%d') + ' 00:00:00'
    start_date_utc = local_2_utc(str_start_date, tz)
    end_date_utc = local_2_utc(str_end_date, tz)
    start_date_utc = start_date_utc.strftime(DEFAULT_SERVER_DATETIME_FORMAT)
    end_date_utc = end_date_utc.strftime(DEFAULT_SERVER_DATETIME_FORMAT)
    start_date_utc = datetime.strptime(start_date_utc, DEFAULT_SERVER_DATETIME_FORMAT)
    end_date_utc = datetime.strptime(end_date_utc, DEFAULT_SERVER_DATETIME_FORMAT)
    return start_date_utc, end_date_utc

def utc_2_local(str_date, tz):
    if str_date:
        timez = 'UTC'
        if tz:
            timez = tz
        local_tz = pytz.timezone(timez)
        date_with_tz = pytz.utc.localize(str_date).astimezone(local_tz)
    return date_with_tz

_logger = logging.getLogger(__name__)



class ResUsers(models.Model):
    _inherit = 'res.users'

    def split_name(self,name):
        name = name.split(',')
        if len(name) == 2:
            last_name = name[0].strip()
            first_name = name[1].strip()
            name_dict ={'first_name':first_name,"middle_name":'',"last_name":last_name}
            return name_dict
        if len(name) > 2:
            last_name = name[0].strip()
            middle_name = name[1].strip()
            first_name = name[2].strip()
            name_dict = {'first_name': first_name, "middle_name": middle_name, "last_name": last_name}
            return name_dict
        if len(name) == 1:
            first_name = name[0].strip()
            name_dict = {'first_name': first_name, "middle_name": '', "last_name": ''}
            return name_dict

    def get_sales_appointment_api(self,user_id):
        configurations = self.env['team.improveit.configuration'].search([('api_type', '=', 'boomi')])
        for record in configurations:
            end_point_url = record.token_url
            client_token = record.client_token
            update_existing_record = record.update_existing_record
            if end_point_url and client_token:
                url = end_point_url + 'GetSalesAppointments' + client_token
                headers = {"Content-type": 'application/json'}
                if user_id:
                    data = {
                        "SalespersonID": user_id
                    }

                    req = requests.post(url, data=json.dumps(data), headers=headers, timeout=TIMEOUT, verify=configurations.enable_ssl)
                    req.raise_for_status()
                    content = req.json()
                    res_user = self.env['res.users'].search([('improveit_user_id', '=', user_id)], limit=1)
                    tz = res_user.tz or self._context.get('tz') or 'UTC'
                    first_start_date_utc, first_end_date_utc = get_week_date(0, tz)
                    improveit_appointment_ids = []
                    if res_user:
                        _logger.info("-----Start Processing Appointments----------")
                        count = 0
                        for appointment in content:
                            _logger.info('----appointment data: %s'%(appointment))
                            improveit_appointment_ids.append(appointment['AppointmentID'])
                            date = appointment['AppointmentDate'].split()
                            appointment_date_str = '%s %s' % (date[0], date[1])
                            date_obj = datetime.strptime(date[0], '%Y%m%d')
                            partner = self.env['res.partner'].search(
                                [('name', '=', appointment.get('ProspectName','')), ('email', '=', appointment.get('ProspectEmail', ''))], limit=1)
                            applicant_name_split = self.split_name(appointment['ProspectName'])
                            str1 = appointment.get('AppointmentTime', '0:00 AM')
                            str1_list = str1.split(' ')
                            time = str1_list[0]
                            am_pm = str1_list[1]
                            hour, minute = time.split(':')
                            if hour == '12':
                                hour = '00'
                            if am_pm == 'PM':
                                hour = str(int(hour) + 12)
                            appointment_date = date_obj.replace(hour=int(hour), minute=int(minute))
                            user = self.env.user
                            tz = user.tz and pytz.timezone(user.tz) or pytz.utc
                            appointment_date = tz.localize(appointment_date).astimezone(pytz.utc).strftime(
                                '%Y-%m-%d %H:%M:%S')
                            state = self.env['res.country.state'].search(
                                [('country_id', '=', 233), ('code', '=', appointment.get('ProspectState',''))],limit=1)
                            appointments = self.env['team.customer.appointment'].search(
                                [('improveit_appointment_id', '=', appointment['AppointmentID'])], limit=1, order='id desc')
                            if appointments and appointments.sale_order_ids:
                                if appointments.sale_order_ids.filtered(lambda x: x.state in ['sale', 'done']):
                                    appointments = False
                            _logger.info('Existing Appointment: %s'%(appointments))
                            market_segment = appointment.get('MarketSegment', '')
                            office_location_id = False
                            if market_segment:
                                office_location_id = self.env['otl.office.location'].search(
                                    [('name', '=', market_segment)], limit=1)
                            if not appointments:
                                appointment_values = {
                                    'improveit_appointment_id': appointment['AppointmentID'],
                                    'partner_id': partner.id if partner else False,
                                    'user_id': res_user and res_user.id or False,
                                    'customer_name': appointment.get('ProspectName',''),
                                    'street': appointment.get('ProspectAddress',''),
                                    'city': appointment.get('ProspectCity',''),
                                    'zip': appointment.get('ProspectPostalCode',''),
                                    'phone': appointment.get('ProspectPhone',''),
                                    'appointment_date': appointment_date,
                                    'state': 'scheduled',
                                    'email': appointment.get('ProspectEmail', ''),
                                    'mobile': appointment.get('ProspectSecondaryPhone', ''),
                                    'state_id': state.id if state else False,
                                    'applicant_first_name': applicant_name_split['first_name'] or False,
                                    'applicant_middle_name': applicant_name_split['middle_name'] or False,
                                    'applicant_last_name': applicant_name_split['last_name'] or False,
                                    'market_segment': market_segment,
                                    'office_location_id': office_location_id and office_location_id.id or False,

                                }
                                appointment_obj = self.env['team.customer.appointment'].create(appointment_values)
                                if market_segment and not office_location_id:
                                    appointment_obj.message_post(body='Office Location is not found for Market Segment %s'%(market_segment))
                            elif appointments and update_existing_record:
                                appointment_values = {
                                    'improveit_appointment_id': appointment['AppointmentID'],
                                    'partner_id': partner.id if partner else False,
                                    'user_id': res_user and res_user.id or False,
                                    'customer_name': appointment.get('ProspectName', ''),
                                    'street': appointment.get('ProspectAddress', ''),
                                    'city': appointment.get('ProspectCity', ''),
                                    'zip': appointment.get('ProspectPostalCode',''),
                                    'phone': appointment.get('ProspectPhone',''),
                                    'appointment_date': appointment_date,
                                    'state': 'scheduled',
                                    'email': appointment.get('ProspectEmail', ''),
                                    'mobile': appointment.get('ProspectSecondaryPhone', ''),
                                    'state_id': state.id if state else False,
                                    'applicant_first_name': applicant_name_split['first_name'] or False,
                                    'applicant_middle_name': applicant_name_split['middle_name'] or False,
                                    'applicant_last_name': applicant_name_split['last_name'] or False,
                                    'market_segment': market_segment,
                                    'office_location_id': office_location_id and office_location_id.id or False,
                                    # 'attachment_ids': [(6, 0, [])],
                                }
                                appointments.write(appointment_values)
                                if market_segment and not office_location_id:
                                    appointments.message_post(body='Office Location is not found for Market Segment %s'%(market_segment))
                    # if improveit_appointment_ids:
                    appointments = self.env['team.customer.appointment'].search([
                        ('improveit_appointment_id', 'not in', improveit_appointment_ids),
                        # ('appointment_date', '>=', first_start_date_utc),
                        # ('appointment_date', '<', first_end_date_utc),
                        ('state', '=', 'scheduled'),
                    ])
                    if appointments:
                        for appointment in appointments:
                            appointment.write({'state': 'canceled'})
        return True

    @api.model
    def authenticate_salesperson_user(self,data):
        username = data.get('username',0)
        password = data.get('password',0)
        configurations = self.env['team.improveit.configuration'].search([('api_type', '=', 'boomi')], limit=1)
        if configurations:
            end_point_url = configurations.token_url
            client_token = configurations.client_token
            if end_point_url and client_token:
                url = end_point_url + 'AuthenticateSalesUser' + client_token
            headers = {"Content-type": "application/json"}
            data = {"LoginID": username, "Password": password}
            try:
                req = requests.post(url, data=json.dumps(data), headers=headers, timeout=TIMEOUT, verify=configurations.enable_ssl)
                req.raise_for_status()
                content = req.json()
                user_existed = True
                if content.get('SalespersonID', '') or content.get('InstallerID', ''):
                    users = self.env['res.users'].search([('login', '=ilike', username)], limit=1)
                    salesperson_name = content.get('SalespersonName', username)
                    can_view_phone_number = True
                    if not eval(content.get('ShowCustomerPhone', 'False')):
                        can_view_phone_number = False
                    if not users:
                        users = self.env['res.users'].sudo().create({
                            'login': username,
                            'name': salesperson_name,
                            'email': username,
                            'password': password,
                            'can_view_phone_number': can_view_phone_number,
                            'groups_id': [(6, 0, [self.env.ref('sales_team.group_sale_salesman').id,
                                          self.env.ref('base.group_partner_manager').id,self.env.ref('account.group_account_invoice').id])],
                            'improveit_user_id': content.get('SalespersonID', '') or content.get('InstallerID', '') or ''
                        })
                        self.env.cr.commit()
                        user_existed = False
                    if users:
                        if user_existed:
                            vals = {
                                'password': password,
                                'can_view_phone_number': can_view_phone_number,
                            }
                            if content.get('SalespersonID', ''):
                                vals.update({'improveit_user_id': content.get('SalespersonID', '')})
                            if content.get('SalespersonName', ''):
                                vals.update({'name': content.get('SalespersonName', '')})

                            if content.get('InstallerID', ''):
                                vals.update({'improveit_user_id': content.get('InstallerID', '')})
                                # self.get_sales_appointment_api(content.get('InstallerID', ''))
                            if vals:
                                users.sudo().write(vals)
                        status = {'message': 'Authenticating SalesPerson Api Successful', 'result': 'Success',
                                  'content': content}
                        return status
                    else:
                        _logger.info("------Authenticating User Failed-------------")
                        status = {'message': 'Authenticating User Failed', 'result': 'Failed'}
                        return status
                else:
                    _logger.info("------Authenticating User Failed-------------")
                    status = {'message': 'Authenticating User Failed', 'result': 'Failed'}
                    return status

            except requests.HTTPError:
                _logger.info("------Authenticating User Failed-------------")
                status = {'message': 'Authentication API Failed.', 'result': 'Failed'}
                return status
        else:
            status = {'message': 'Url Endpoint Not Configured', 'result': 'Failed'}
            return status

    def action_clear_token(self):
        for record in self:
            if record.token_name:
                vals = {
                    'user_id': record.id,
                    'action': 'logout',
                    'token': record.token_name,
                    'action_done': 'admin',
                }
                record.write({'token_name': ''})
                log = self.env['otl.user.authentication.log'].sudo().create(vals)
                _logger.info("Authentication log created successfully----. Vals: %s, Record: %s" % (vals, log.id))
        return True

    @api.model
    def cron_clear_user_tokens(self):
        for company in self.env['res.company'].search([('enable_auto_logout', '=', True)]):
            logged_in_users = self.search([('token_name', '!=', ''), ('company_id', '=', company.id)])
            users_with_pending_sync = []
            for user in logged_in_users:
                pending_appointments = self.env['team.customer.appointment'].search(
                    [('state', '=', 'scheduled'), ('user_id', '=', user.id)])
                if pending_appointments:
                    users_with_pending_sync.append(user.id)
                else:
                    vals = {
                        'user_id': user.id,
                        'action': 'logout',
                        'token': user.token_name,
                        'action_done': 'automated',
                    }
                    user.write({'token_name': ''})
                    log = self.env['otl.user.authentication.log'].sudo().create(vals)
                    _logger.info("Authentication log created successfully----. Vals: %s, Record: %s" % (vals, log.id))
            if users_with_pending_sync:
                try:
                    # Get the template id corresponding to the email template
                    # template_id = ir_model_data.get_object_reference('hr_holidays_custom', 'email_template_leave_request')[1]
                    template_id = self.env.ref('team_api_connection.email_template_pending_users_logout')
                except ValueError:
                    template_id = False
                if template_id:
                    template_id.send_mail(company.id, force_send=True, raise_exception=False)
        return True


class ResCompany(models.Model):
    _inherit = 'res.company'

    def get_logged_in_notify_user_ids(self):
        email_to = ''
        for company in self:
            if company.logged_in_notify_user_ids:
                for user in company.logged_in_notify_user_ids:
                    email = user.email
                    if not email_to:
                        email_to = email
                    else:
                        email_to += ', ' + email
        return email_to

    def get_pending_logout_users_list(self):
        result = []
        for company in self:
            logged_in_users = self.env['res.users'].search([('token_name', '!=', ''), ('company_id', '=', company.id)])
            for user in logged_in_users:
                pending_appointments = self.env['team.customer.appointment'].search(
                    [('state', '=', 'scheduled'), ('user_id', '=', user.id)])
                appointments = []
                for appointment in pending_appointments:
                    appointments.append(appointment.name)
                result.append({
                    'name': user.name,
                    'login': user.login,
                    'appointments': appointments
                })
        return result




class TeamRoomRoom(models.Model):
    _inherit = 'team.room.room'

    # get image url
    def profile_image(self, name, model_name, image, res_id):
        url = ''
        Attachment = self.env['ir.attachment'].sudo().search([('res_model', '=', model_name), ('res_id', '=', res_id)],
                                                             limit=1)
        if Attachment:
            Attachment.sudo().write({'datas': image})
            if not Attachment.access_token:
                Attachment.generate_access_token()
            url = URL + '/web/image/' + str(Attachment.id) + '?access_token=' + str(Attachment.access_token)
        else:
            Attachment = self.env['ir.attachment'].sudo().create({
                'res_id': res_id,
                'res_model': model_name,
                'datas': image,
                'name': name

            })
            Attachment.generate_access_token()
            url = URL + '/web/image/' + str(Attachment.id) + '?access_token=' + str(Attachment.access_token)
        return url

    @api.model
    def get_rooms(self):

        list = []
        rooms = self.env['team.room.room'].search([('active', '=', True)])
        if rooms:
            for room in rooms:
                room_image_url = ''
                if room.image:
                    room_image_url = self.profile_image(room.name, 'team.room.room', room.image, room.id)

                vals = {

                    'id': room.id,
                    'name': room.name and room.name.upper() or '',
                    'note': room.note or '',
                    'company_id': room.company_id.id,
                    'image': room_image_url,
                    'room_category': room.product_category_id and room.product_category_id.name or ''

                }
                list.append(vals)

        return list

    @api.model
    def get_room_list(self,data):
        appointment_id = data.get('appointment_id', False)
        if not appointment_id:
            _logger.info("------Empty Appointment id-------------")
            status = {'message': 'Empty Appointment id', 'result': 'Success'}
            return status
        if not self.env['team.customer.appointment'].browse(int(appointment_id)).exists():
            _logger.info("------ Appointment Not Exist-------------")
            status = {'message': 'Appointment Not Exist', 'result': 'Success'}
            return status

        list = []
        rooms = self.env['team.room.room'].search([('active', '=', True)])
        if rooms:
            for room in rooms:
                room_image_url = ''
                if room.image:
                    room_image_url = self.profile_image(room.name, 'team.room.room', room.image, room.id)
                measurement_exist = 'False'
                custom_room_parent ='False'
                if room.is_custom:
                    custom_room_parent='True'
                contract_room_lines = self.env['team.contract.room.measurement.line'].search(
                    [('appointment_id', '=', int(appointment_id)), ('room_id', '=', room.id)])
                if contract_room_lines and not room.is_custom:
                    measurement_exist = 'True'

                vals = {

                    'id': room.id,
                    'name': room.name and room.name.upper() or '',
                    'note': room.note or '',
                    'company_id': room.company_id.id,
                    'image': room_image_url,
                    'measurement_exist':measurement_exist,
                    'is_custom_room':'False',
                    'custom_room_measurement_id':'False',
                    'custom_room_parent':custom_room_parent,
                    'room_category': room.product_category_id and room.product_category_id.name or '',

                }
                list.append(vals)
            room_lines = self.env['team.contract.room.measurement.line'].search(
                [('appointment_id', '=', int(appointment_id)), ('room_id.is_custom', '=',True)])
            if room_lines:
                for custom_room in room_lines:
                    room_image_url = ''
                    if custom_room.room_id.image:
                        room_image_url = self.profile_image(custom_room.room_id.name, 'team.room.room', custom_room.room_id.image, custom_room.room_id.id)
                    if custom_room.custom_room_measured:
                        measurement_exist = 'True'
                    else:
                        measurement_exist = 'False'

                    vals = {

                        'id': custom_room.room_id.id,
                        'name': custom_room.custom_room_name and custom_room.custom_room_name.upper() or '',
                        'note': custom_room.room_id.note or '',
                        'company_id': custom_room.room_id.company_id.id,
                        'image': room_image_url,
                        'measurement_exist': measurement_exist,
                        'is_custom_room':'True',
                        'custom_room_measurement_id':custom_room.id,
                        'custom_room_parent':'False',
                        'room_category': custom_room.room_id.product_category_id and custom_room.room_id.product_category_id.name or '',

                    }
                    list.append(vals)
        sorted_list = sorted(list, key=lambda k: k['name'])
        room_list = [x for x in sorted_list if not ('True' == x.get('custom_room_parent'))]
        others_list = [x for x in sorted_list if ('True' == x.get('custom_room_parent'))]
        room_list.extend(others_list)
        return room_list

    @api.model
    def add_custom_rooms(self, data):
        room_list=[]
        vals={}
        appointment_id = data.get('appointment_id', False)
        room_name = data.get('room_name', False)
        if not appointment_id:
            _logger.info("------Empty Appointment id-------------")
            status = {'message': 'Empty Appointment id', 'result': 'Success'}
            return status
        if not self.env['team.customer.appointment'].browse(int(appointment_id)).exists():
            _logger.info("------ Appointment Not Exist-------------")
            status = {'message': 'Appointment Not Exist', 'result': 'Success'}
            return status
        if not room_name:
            _logger.info("------Empty Room Name-------------")
            status = {'message': 'Empty Room Name', 'result': 'Success'}
            return status
        room_exists = self.env['team.contract.room.measurement.line'].search([('appointment_id','=',int(appointment_id)),('custom_room_name','=',room_name)])
        if room_exists:
            _logger.info("------Custom Room Already Exist-------------")
            status = {'message': 'Custom Room Already Exist', 'result': 'Success'}
            return status
        room_id = self.env['team.room.room'].search([('is_custom', '=',True)],limit=1)
        if not room_id:
            _logger.info("------Room Others Not Found-------------")
            status = {'message': 'Room Others Not Found', 'result': 'Success'}
            return status
        obj = self.env['team.contract.room.measurement.line']

        vals.update({
            'room_id':room_id.id,
            'appointment_id':appointment_id,
            'custom_room_name':room_name,

        })
        record=obj.create(vals)
        if record:
            status = {'message': 'Custom Room Created','custom_room_measurement_id':record.id, 'result': 'Success'}
        else:
            status = {'message': 'Custom Room Creation Failed', 'result': 'Success'}
        return status



class TeamCustomerAppointment(models.Model):
    _inherit = 'team.customer.appointment'

    @api.model
    def get_appointment_result(self,data):
        results = []
        appointment_results = self.env['appointment.result'].search([])
        for appointment_result in appointment_results:
            content_dict={
                'id':appointment_result.id,
                'result':appointment_result.result or ''
            }
            results.append(content_dict)

        return {'message': 'Get Appointment Result Success','appointment_result':results, 'result': 'Success'}

    def split_name(self,name):
        name = name.split(',')
        if len(name) == 2:
            last_name = name[0].strip()
            first_name = name[1].strip()
            name_dict ={'first_name':first_name,"middle_name":'',"last_name":last_name}
            return name_dict
        if len(name) > 2:
            last_name = name[0].strip()
            middle_name = name[1].strip()
            first_name = name[2].strip()
            name_dict = {'first_name': first_name, "middle_name": middle_name, "last_name": last_name}
            return name_dict
        if len(name) == 1:
            first_name = name[0].strip()
            name_dict = {'first_name': first_name, "middle_name": '', "last_name": ''}
            return name_dict

    def parse_error_response(self, result):
        message = ''
        if result and result.get('errors', []):
            for error in result.get('errors', []):
                if not message:
                    message = error.get('message', '')
                else:
                    message += ', ' + error.get('message', '')
        elif result.get('Message', ''):
            message = result.get('Message', '')
        return {'message': message, 'result': 'Failed'}

    @api.model
    def submit_appointment_result(self, data):
        result = data.get('result','')
        appointment_id = data.get('appointment_id','')
        sale_order = self.env['sale.order'].search([('appointment_id','=',int(appointment_id))],limit=1)
        if sale_order and result:
            try:
                completed_document = False
                model_id = self.env['ir.model'].search([('model', '=', 'sale.order')], limit=1)
                sign_request = self.env['otl_document_sign.request'].sudo().search(
                    [('model_id', '=', model_id.id), ('res_id', '=', sale_order.id)],limit=1)
                if sign_request:
                    if sign_request.completed_document:
                        completed_document = sign_request.document_image()
                response_result = sale_order.add_quote_sales_app(result)
                if response_result.get('success', '') == 'true':
                    _logger.info("------ Add Quote API is Success-------------")
                else:
                    _logger.info("------ Add Quote API is Failed-------------")
                    return self.parse_error_response(response_result)
                response_result = sale_order.add_quote_items_sales_app()
                if response_result.get('success', '') == 'true':
                    _logger.info("------ Add Quote Item API is Success-------------")
                else:
                    _logger.info("------ Add Quote Item API is Failed-------------")
                    return self.parse_error_response(response_result)
                sale_order.add_quote_id_file(completed_document)
                response_result = sale_order.set_appointment_result_api(status=result)
                if response_result.get('Result', '') == 'Success':
                    _logger.info("------ Set Appointment Result API is Success-------------")
                else:
                    _logger.info("------ Set Appointment Result API is Failed-------------")
                    return self.parse_error_response(response_result)
                return {'message': 'Submit Appointment Result Success', 'result': 'Success'}
            except IOError:
                return {'message': 'Something Went Wrong While Submitting Appointment Result', 'result': 'Success'}

        else:
            team_question_obj = self.env['team.contract.question.line'].search(
                [('appointment_id', '=', int(appointment_id))])
            team_room_obj = self.env['team.contract.room.measurement.line'].search(
                [('appointment_id', '=', int(appointment_id))])
            room_transition_obj = self.env['team.contract.transition.line'].search(
                [('appointment_id', '=', int(appointment_id))])
            sale_dict = {}
            sale_order_ref = self.env['sale.order'].search([('appointment_id', '=', int(appointment_id))], limit=1)
            appointment = self.env['team.customer.appointment'].browse(int(appointment_id))
            res_partner_obj = self.env['res.partner']
            sale_order_obj = self.env['sale.order']
            if appointment and not sale_order_ref:
                if appointment.partner_id:
                    sale_dict = {'partner_id': appointment.partner_id.id,
                                 'appointment_id': int(appointment_id)
                                 }
                else:
                    if appointment.customer_name:
                        partner_vals = {
                            'name': appointment.customer_name,
                            'phone': appointment.phone,
                            'mobile': appointment.mobile,
                            'street': appointment.street,
                            'street2': appointment.street2,
                            'city': appointment.city,
                            'state_id': appointment.state_id.id or False,
                            'zip': appointment.zip,
                            'country_id': appointment.country_id.id or False,
                            'email': appointment.email
                        }
                        if partner_vals:
                            customer = res_partner_obj.create(partner_vals)
                            if customer:
                                split_name = self.split_name(customer.name)
                                if split_name['first_name'] and split_name['last_name']:
                                    inititals = split_name['first_name'][0] + split_name['last_name'][0]
                                if split_name['first_name'] and not split_name['last_name']:
                                    inititals = split_name['first_name'][0]
                                if inititals:
                                    inititals = inititals.upper() or ''
                                sale_dict = {'partner_id': customer.id,
                                             'appointment_id': int(appointment_id),
                                             }
                if sale_dict:
                    sale_order_ref = sale_order_obj.create(sale_dict)

            if team_question_obj:
                team_question_obj.write({'order_id': sale_order_ref.id})
            if team_room_obj:
                team_room_obj.write({'order_id': sale_order_ref.id})
            if room_transition_obj:
                room_transition_obj.write({'order_id': sale_order_ref.id})
            try:
                completed_document = False
                model_id = self.env['ir.model'].search([('model', '=', 'sale.order')], limit=1)
                sign_request = self.env['otl_document_sign.request'].sudo().search(
                    [('model_id', '=', model_id.id), ('res_id', '=', sale_order_ref.id)], limit=1)
                if sign_request and sign_request.completed_document:
                    completed_document = sign_request.document_image()
                response_result = sale_order_ref.add_quote_sales_app(result)
                if response_result.get('success', '') == 'true':
                    _logger.info("------ Add Quote API is Success-------------")
                else:
                    _logger.info("------ Add Quote API is Failed-------------")
                    return self.parse_error_response(response_result)
                response_result = sale_order_ref.add_quote_items_sales_app()
                if response_result.get('success', '') == 'true':
                    _logger.info("------ Add Quote Item API is Success-------------")
                else:
                    _logger.info("------ Add Quote Item API is Failed-------------")
                    return self.parse_error_response(response_result)
                sale_order_ref.add_quote_id_file(completed_document)
                response_result = sale_order_ref.set_appointment_result_api(status=result)
                if response_result.get('Result', '') == 'Success':
                    _logger.info("------ Set Appointment Result API is Success-------------")
                else:
                    _logger.info("------ Set Appointment Result API is Failed-------------")
                    return self.parse_error_response(response_result)
                return {'message': 'Submit Appointment Result Success', 'result': 'Success'}
            except IOError:
                return {'message': 'Something Went Wrong While Submitting Appointment Result', 'result': 'Success'}

    @api.model
    def submit_appointment_result_without_upload(self, data):
        result = data.get('result','')
        what_happened_notes = data.get('what_happened_notes','')
        whats_next_notes = data.get('whats_next_notes','')
        appointment_id = data.get('appointment_id','')
        notes = {
            'whats_next_notes': whats_next_notes,
            'what_happened_notes': what_happened_notes,
        }
        sale_order = self.env['sale.order'].search([('appointment_id','=',int(appointment_id))],limit=1)
        if sale_order and result:
            try:
                completed_document = False
                model_id = self.env['ir.model'].search([('model', '=', 'sale.order')], limit=1)
                sign_request = self.env['otl_document_sign.request'].sudo().search(
                    [('model_id', '=', model_id.id), ('res_id', '=', sale_order.id)],limit=1)
                # if sign_request:
                #     if sign_request.completed_document:
                #         completed_document = sign_request.document_image()
                # response_result = sale_order.add_quote_sales_app(result)
                # if response_result.get('success', '') == 'true':
                #     _logger.info("------ Add Quote API is Success-------------")
                # else:
                #     _logger.info("------ Add Quote API is Failed-------------")
                #     return self.parse_error_response(response_result)
                # response_result = sale_order.add_quote_items_sales_app()
                # if response_result.get('success', '') == 'true':
                #     _logger.info("------ Add Quote Item API is Success-------------")
                # else:
                #     _logger.info("------ Add Quote Item API is Failed-------------")
                #     return self.parse_error_response(response_result)
                # sale_order.add_quote_id_file(completed_document)
                sale_order.appointment_id.write({
                    'appointment_result': result,
                    'state': 'done',
                    'what_happened_notes': what_happened_notes,
                    'whats_next_notes': whats_next_notes,
                })
                response_result = sale_order.set_appointment_result_api(status=result, notes= notes)
                _logger.info('-------i360 SetAppointmentResult Response: %s' % (response_result))
                # if response_result.get('Result', '') == 'Success':
                #     _logger.info("------ Set Appointment Result API is Success-------------")
                # else:
                #     _logger.info("------ Set Appointment Result API is Failed-------------")
                #     return self.parse_error_response(response_result)
                return {'message': 'Submit Appointment Result Success', 'result': 'Success'}
            except IOError:
                return {'message': 'Something Went Wrong While Submitting Appointment Result', 'result': 'Success'}

        else:
            team_question_obj = self.env['team.contract.question.line'].search(
                [('appointment_id', '=', int(appointment_id))])
            team_room_obj = self.env['team.contract.room.measurement.line'].search(
                [('appointment_id', '=', int(appointment_id))])
            room_transition_obj = self.env['team.contract.transition.line'].search(
                [('appointment_id', '=', int(appointment_id))])
            sale_dict = {}
            sale_order_ref = self.env['sale.order'].search([('appointment_id', '=', int(appointment_id))], limit=1)
            appointment = self.env['team.customer.appointment'].browse(int(appointment_id))
            res_partner_obj = self.env['res.partner']
            sale_order_obj = self.env['sale.order']
            if appointment and not sale_order_ref:
                if appointment.partner_id:
                    sale_dict = {'partner_id': appointment.partner_id.id,
                                 'appointment_id': int(appointment_id)
                                 }
                else:
                    if appointment.customer_name:
                        partner_vals = {
                            'name': appointment.customer_name,
                            'phone': appointment.phone,
                            'mobile': appointment.mobile,
                            'street': appointment.street,
                            'street2': appointment.street2,
                            'city': appointment.city,
                            'state_id': appointment.state_id.id or False,
                            'zip': appointment.zip,
                            'country_id': appointment.country_id.id or False,
                            'email': appointment.email
                        }
                        if partner_vals:
                            customer = res_partner_obj.create(partner_vals)
                            if customer:
                                split_name = self.split_name(customer.name)
                                if split_name['first_name'] and split_name['last_name']:
                                    inititals = split_name['first_name'][0] + split_name['last_name'][0]
                                if split_name['first_name'] and not split_name['last_name']:
                                    inititals = split_name['first_name'][0]
                                if inititals:
                                    inititals = inititals.upper() or ''
                                sale_dict = {'partner_id': customer.id,
                                             'appointment_id': int(appointment_id),
                                             }
                if sale_dict:
                    sale_order_ref = sale_order_obj.create(sale_dict)

            if team_question_obj:
                team_question_obj.write({'order_id': sale_order_ref.id})
            if team_room_obj:
                team_room_obj.write({'order_id': sale_order_ref.id})
            if room_transition_obj:
                room_transition_obj.write({'order_id': sale_order_ref.id})
            try:
                completed_document = False
                model_id = self.env['ir.model'].search([('model', '=', 'sale.order')], limit=1)
                sign_request = self.env['otl_document_sign.request'].sudo().search(
                    [('model_id', '=', model_id.id), ('res_id', '=', sale_order_ref.id)], limit=1)
                # if sign_request and sign_request.completed_document:
                #     completed_document = sign_request.document_image()
                # response_result = sale_order_ref.add_quote_sales_app(result)
                # if response_result.get('success', '') == 'true':
                #     _logger.info("------ Add Quote API is Success-------------")
                # else:
                #     _logger.info("------ Add Quote API is Failed-------------")
                #     return self.parse_error_response(response_result)
                # response_result = sale_order_ref.add_quote_items_sales_app()
                # if response_result.get('success', '') == 'true':
                #     _logger.info("------ Add Quote Item API is Success-------------")
                # else:
                #     _logger.info("------ Add Quote Item API is Failed-------------")
                #     return self.parse_error_response(response_result)
                # sale_order.add_quote_id_file(completed_document)
                sale_order.appointment_id.write({
                    'appointment_result': result,
                    'state': 'done',
                    'what_happened_notes': what_happened_notes,
                    'whats_next_notes': whats_next_notes,
                    'start_sync_to_i360': True,
                })
                response_result = sale_order_ref.set_appointment_result_api(status=result, notes=notes)
                _logger.info('-------i360 SetAppointmentResult Response: %s' % (response_result))
                # if response_result.get('Result', '') == 'Success':
                #     _logger.info("------ Set Appointment Result API is Success-------------")
                # else:
                #     _logger.info("------ Set Appointment Result API is Failed-------------")
                #     return self.parse_error_response(response_result)
                return {'message': 'Submit Appointment Result Success', 'result': 'Success'}
            except IOError:
                return {'message': 'Something Went Wrong While Submitting Appointment Result', 'result': 'Success'}

    @api.model
    def submit_appointment_file_upload(self, data):
        _logger.info('--------Inside submit_appointment_file_upload function')
        appointment_id = data.get('appointment_id', '')
        sale_order = self.env['sale.order'].search([('appointment_id', '=', int(appointment_id))], limit=1)
        sale_order_vals = {}
        if sale_order.appointment_id and sale_order.appointment_result and not sale_order.appointment_id.status_updated_to_i360:
            response_result = sale_order.set_appointment_result_api(sale_order.appointment_result)
            _logger.info('-------i360 SetAppointmentResult Response: %s' % (response_result))
        if sale_order and sale_order.appointment_result and not sale_order.is_data_upload_completed:
            if not sale_order.quote_id:
                response_result = sale_order.add_quote_sales_app(status=sale_order.appointment_result)
                _logger.info('-------i360 AddQuote Response: %s'%(response_result))
            response_result = sale_order.add_quote_items_sales_app()
            _logger.info('-------i360 AddQuoteItem Response: %s'%(response_result))
            if not sale_order.other_files_uploaded:
                if sale_order.state in ['sale', 'done'] or sale_order.appointment_result == 'Sold':
                    result = sale_order.add_sale_id_file()
                else:
                    result = sale_order.add_quote_id_file(document=False)
                if result.get('success') == "true":
                    sale_order_vals.update({'other_files_uploaded': True})
            sale_order.write(sale_order_vals)
            if sale_order.check_document_upload_completed():
                sale_order.write({'is_data_upload_completed': True})
        return {
            'result': 'success',
            'message': "Documents Uploaded successfully"
        }

    @api.model
    def add_applicant_signature(self,data):
        vals = {}
        if data.get('appointment_id', False):
            if  self.env['team.customer.appointment'].browse(int(data.get('appointment_id', False))).exists():
                appointment_id = data.get('appointment_id', False)
            else:
                return {'message': 'Wrong Appointment ID', 'result': 'Success'}
        else:
            return {'message': 'Appointment ID Empty', 'result': 'Success'}
        appointment = self.env['team.customer.appointment'].browse(int(appointment_id))
        # sale_order = self.env['sale.order'].search([('appointment_id','=',int(appointment.id))],limit=1)
        # if not sale_order:
        #     return {'message': 'Sale Order Not Created For this appointment', 'result': 'Success'}
        # sale_order.generate_link()
        # link = sale_order.link_to_share
        if not data.get('finance_application', False):
            return {'message': 'finance_application Parameter Empty', 'result': 'Success'}
        if not data.get('credit_card', False):
            return {'message': 'credit_card Parameter Empty', 'result': 'Success'}
        if not data.get('contract', False):
            return {'message': 'contract Parameter Empty', 'result': 'Success'}
        finance_application = data.get('finance_application', False)
        if finance_application == 'True':
            status_finance_application ='True'
            vals.update({'finance_application':True})
        else:
            status_finance_application = 'False'
            vals.update({'finance_application': False})
        credit_card = data.get('credit_card', False)
        if credit_card == 'True':
            status_credit_card = 'True'
            vals.update({'credit_card':True})
        else:
            status_credit_card = 'False'
            vals.update({'credit_card': False})
        contract = data.get('contract', False)
        if contract == 'True':
            status_contract = 'True'
            vals.update({'contract':True})
        else:
            status_contract ='False'
            vals.update({'contract': False})
        if data.get('applicant_signature_id', False):
            if appointment.applicant_signature_id:
                appointment.applicant_signature_id.sudo().unlink()
            vals.update({'applicant_signature_id':int(data.get('applicant_signature_id', False))})
        if data.get('co_applicant_signature_id', False):
            if appointment.co_applicant_signature_id:
                appointment.co_applicant_signature_id.sudo().unlink()
            vals.update({'co_applicant_signature_id':int(data.get('co_applicant_signature_id', False))})
        if data.get('applicant_initial_id', False):
            if appointment.applicant_initial_id:
                appointment.applicant_initial_id.sudo().unlink()
            vals.update({'applicant_initial_id':int(data.get('applicant_initial_id', False))})
        if data.get('co_applicant_initial_id', False):
            if appointment.co_applicant_initial_id:
                appointment.co_applicant_initial_id.sudo().unlink()
            vals.update({'co_applicant_initial_id':int(data.get('co_applicant_initial_id', False))})
        appointment.write(vals)
        applicant_signature_image = []
        if appointment.applicant_signature_id:
            if not appointment.applicant_signature_id.access_token:
                appointment.applicant_signature_id.generate_access_token()
            url = URL + '/web/image/' + str(
                appointment.applicant_signature_id.id) + '?access_token=' + str(
                appointment.applicant_signature_id.access_token)
            applicant_signature_image.append({
                'id': appointment.applicant_signature_id.id,
                'name': appointment.applicant_signature_id.name,
                'url': url,
            })
        co_applicant_signature_image = []
        if appointment.co_applicant_signature_id:
            if not appointment.co_applicant_signature_id.access_token:
                appointment.co_applicant_signature_id.generate_access_token()
            url = URL + '/web/image/' + str(
                appointment.co_applicant_signature_id.id) + '?access_token=' + str(
                appointment.co_applicant_signature_id.access_token)
            co_applicant_signature_image.append({
                'id': appointment.co_applicant_signature_id.id,
                'name': appointment.co_applicant_signature_id.name,
                'url': url,
            })

        applicant_initial_image =[]
        if appointment.applicant_initial_id:
            if not appointment.applicant_initial_id.access_token:
                appointment.applicant_initial_id.generate_access_token()
            url = URL + '/web/image/' + str(
                appointment.applicant_initial_id.id) + '?access_token=' + str(
                appointment.applicant_initial_id.access_token)
            applicant_initial_image.append({
                'id': appointment.applicant_initial_id.id,
                'name': appointment.applicant_initial_id.name,
                'url': url,
            })
        co_applicant_initial_image = []
        if appointment.co_applicant_initial_id:
            if not appointment.co_applicant_initial_id.access_token:
                appointment.co_applicant_initial_id.generate_access_token()
            url = URL + '/web/image/' + str(
                appointment.co_applicant_initial_id.id) + '?access_token=' + str(
                appointment.co_applicant_initial_id.access_token)
            co_applicant_initial_image.append({
                'id': appointment.co_applicant_initial_id.id,
                'name': appointment.co_applicant_initial_id.name,
                'url': url,
            })

        return {'message': 'Applicant Signature Updated','applicant_signature_image':applicant_signature_image,'co_applicant_signature_image':co_applicant_signature_image ,'applicant_initial_image':applicant_initial_image,'co_applicant_initial_image':co_applicant_initial_image,'Document':'','finance_application':status_finance_application,'credit_card':status_credit_card,'contract':status_contract,'result': 'Success'}

    def update_appointment_to_boomi(self):
        configurations = self.env['team.improveit.configuration'].search([('api_type', '=', 'boomi')])
        if configurations:
            end_point_url = configurations.token_url
            client_token = configurations.client_token
            if end_point_url and client_token:
                url = end_point_url + 'UpdateAppointmentProspect' + client_token
                headers = {"Content-type": "application/json"}
                for appointment in self:
                    update_prospects_vals = {
                        "AppointmentID": appointment.improveit_appointment_id or 'null',
                        "ProspectFirstName": appointment.applicant_first_name or '',
                        "ProspectLastName": appointment.applicant_last_name or '',
                        "ProspectAddress": appointment.street or '',
                        "ProspectCity": appointment.city or '',
                        "ProspectState": appointment.state_id and appointment.state_id.code or '',
                        "ProspectPostalCode": appointment.zip or '',
                        "ProspectEmail": appointment.email or '',
                        "ProspectPrimaryPhone": appointment.phone or '',
                        "ProspectSecondaryPhone": appointment.mobile or '',
                        "Customer2FirstName": appointment.co_applicant_first_name or '',
                        "Customer2LastName": appointment.co_applicant_last_name or '',
                        "Customer2Address": appointment.co_applicant_address or "",
                        "Customer2City": appointment.co_applicant_city or "",
                        "Customer2State": appointment.co_applicant_state and appointment.co_applicant_state.code or "",
                        "Customer2PostalCode": appointment.co_applicant_zip or "",
                        "Customer2Email": appointment.co_applicant_email or "",
                        "Customer2PrimaryPhone": appointment.co_applicant_phone or "",
                        "Customer2SecondaryPhone": appointment.co_applicant_secondary_phone or ""
                    }
                    try:
                        _logger.info('--------Starting UpdateAppointmentProspect API--------')
                        _logger.info(update_prospects_vals)
                        req = requests.post(url, data=json.dumps(update_prospects_vals), headers=headers,
                                            timeout=TIMEOUT, verify=configurations.enable_ssl)
                        _logger.error('UpdateAppointmentProspect API Response of Appointment %s : %s' %(appointment.id, str(req.content)))
                        req.raise_for_status()
                        try:
                            content = req.json()

                        except IOError:
                            if req.status_code == 200:
                                return {
                                    'success': 'false',
                                    'errors': [
                                        {
                                            'message': "Prospect's data successfully send to the system, but response is in wrong format."
                                        }
                                    ]
                                }
                            else:
                                return {
                                    'success': 'false',
                                    'errors': [
                                        {
                                            'message': "Wrong response format."
                                        }
                                    ]
                                }
                        _logger.info('UpdateAppointmentProspect API Response of Appointment %s :%s' %(appointment.id, content))
                        return content
                    except IOError:
                        status = {'message': 'Appointment Update API Error', 'result': False}
                        _logger.info(status)
                        return status
        return True

    @api.model
    def update_appointment(self, data):
        status = {}
        appointment_id = data.get('appointment_id', False)
        if appointment_id is False:
            _logger.info("------Empty Appointment id-------------")
            status = {'message': 'Empty Appointment id', 'result': False}
            return status
        appointment = self.env['team.customer.appointment'].search([('id', '=', int(appointment_id))], limit=1)
        vals = {}
        state=''
        co_applicant_state=''
        _logger.info(data)
        partner_vals = {}
        if appointment:
            partner = appointment.partner_id or False
            if data.get('customer_name', ''):
                vals.update({'customer_name': data.get('customer_name')})
                if partner and partner.name != data.get('customer_name', ''):
                    partner_vals.update({'name': data.get('customer_name', '')})
            if data.get('co_applicant', ''):
                vals.update({'co_applicant': data.get('co_applicant')})
            if data.get('co_applicant_phone', ''):
                vals.update({'co_applicant_phone': data.get('co_applicant_phone')})
            if data.get('co_applicant_email', ''):
                vals.update({'co_applicant_email': data.get('co_applicant_email')})
            if data.get('appointment_date'):
                vals.update({'appointment_date': data.get('appointment_date')})
            if data.get('street', ''):
                vals.update({'street': data.get('street')})
                partner_vals.update({'street': data.get('street')})
            if data.get('street2', ''):
                vals.update({'street2': data.get('street2')})
                partner_vals.update({'street2': data.get('street2')})
            if data.get('city', ''):
                vals.update({'city': data.get('city')})
                partner_vals.update({'city': data.get('city')})
            if data.get('state_id', False):
                state = self.env['res.country.state'].search(
                    [('country_id', '=', 233), ('code', '=', data.get('state_id', False))], limit=1)
                if state:
                    vals.update({'state_id': state.id})
                    partner_vals.update({'state_id': state.id})
                else:
                    return {'message': 'Wrong State Code', 'result': False}
            if data.get('co_applicant_state', False):
                co_applicant_state = self.env['res.country.state'].search(
                    [('country_id', '=', 233), ('code', '=', data.get('co_applicant_state', False))], limit=1)
                if co_applicant_state:
                    vals.update({'co_applicant_state': co_applicant_state.id})
                else:
                    return {'message': 'Wrong State Code', 'result': False}
            if data.get('country_id', False):
                if self.env['res.country'].browse(int(data.get('country_id', False))).exists():
                    vals.update({'country_id': int(data.get('country_id'))})
                    partner_vals.update({'country_id': int(data.get('country_id'))})
                else:
                    return {'message': 'Wrong Country ID', 'result': False}
            if data.get('zip', ''):
                vals.update({'zip': data.get('zip')})
                partner_vals.update({'zip': data.get('zip')})
            if data.get('phone', ''):
                vals.update({'phone': data.get('phone')})
                partner_vals.update({'phone': data.get('phone')})
            if data.get('mobile', ''):
                vals.update({'mobile': data.get('mobile')})
                partner_vals.update({'mobile': data.get('mobile')})
            if data.get('email', ''):
                vals.update({'email': data.get('email')})
                partner_vals.update({'email': data.get('email')})
            if data.get('partner_latitude', ''):
                vals.update({'partner_latitude': data.get('partner_latitude')})
            if data.get('partner_longitude', ''):
                vals.update({'partner_longitude': data.get('partner_longitude')})
            if data.get('applicant_first_name', ''):
                vals.update({'applicant_first_name': data.get('applicant_first_name')})
            if data.get('applicant_middle_name', ''):
                vals.update({'applicant_middle_name': data.get('applicant_middle_name')})
            if data.get('applicant_last_name', ''):
                vals.update({'applicant_last_name': data.get('applicant_last_name')})
            if data.get('co_applicant_first_name', ''):
                vals.update({'co_applicant_first_name': data.get('co_applicant_first_name')})
            if data.get('co_applicant_middle_name', ''):
                vals.update({'co_applicant_middle_name': data.get('co_applicant_middle_name')})
            if data.get('co_applicant_last_name', ''):
                vals.update({'co_applicant_last_name': data.get('co_applicant_last_name')})
            if data.get('co_applicant_address', ''):
                vals.update({'co_applicant_address': data.get('co_applicant_address')})
            if data.get('co_applicant_city', ''):
                vals.update({'co_applicant_city': data.get('co_applicant_city')})
            if data.get('co_applicant_zip', ''):
                vals.update({'co_applicant_zip': data.get('co_applicant_zip')})
            if data.get('co_applicant_secondary_phone', ''):
                vals.update({'co_applicant_secondary_phone': data.get('co_applicant_secondary_phone')})
            if data.get('co_applicant_last_name', '') or data.get('co_applicant_first_name', ''):
                vals.update(
                    ({'co_applicant': '%s, %s' % (data.get('co_applicant_last_name', ''), data.get('co_applicant_first_name', ''))}))
            if partner_vals and partner:
                partner.write(partner_vals)
            update = appointment.write(vals)
            if update:
                result = appointment.update_appointment_to_boomi()
                if result.get('success', '') == 'true':
                    _logger.info("------ UpdateAppointmentProspect Success-------------")
                    status = {'message': 'UpdateAppointmentProspect Success', 'result': 'Success'}
                    appointment.write({'prospect_info_updated': True})
                else:
                    _logger.info("------ UpdateAppointmentProspect Failed-------------")
                    if result and result.get('errors', []):
                        message = ''
                        for error in result.get('errors', []):
                            if not message:
                                message = error.get('message', '')
                            else:
                                message += ', ' + error.get('message', '')
                        if message:
                            message += '\n We are having issue with communicating our server . Please tap on Retry button to try again. If issue continues, please reach out to the support'
                        status = {'message': message, 'result': 'Failed'}
                    else:
                        status = {'message': 'UpdateAppointmentProspect Failed', 'result': 'Failed'}
        else:
            status = {'message': 'Appointment Not Exist', 'result': False}
        return status

    @api.model
    def get_appointment_data(self, user_id):

        list = []
        if user_id:
            user = self.env['res.users'].browse(int(user_id))
            if user and user.improveit_user_id:
                self.env['res.users'].get_sales_appointment_api(user.improveit_user_id)
        tz = user.tz or self._context.get('tz') or 'UTC'
        first_start_date_utc, first_end_date_utc = get_week_date(0, tz)
        appointment_data = self.env['team.customer.appointment'].search(
            [
                ('user_id', '=', int(user_id)),
                ('state', '=', 'scheduled'),
                # ('appointment_date', '>=', first_start_date_utc),
                # ('appointment_date', '<', first_end_date_utc),
            ], order='appointment_date asc')
        improveit_appointment_ids = []
        if appointment_data:
            for data in appointment_data:
                if data.improveit_appointment_id:
                    if data.improveit_appointment_id in improveit_appointment_ids:
                        continue
                    improveit_appointment_ids.append(data.improveit_appointment_id)
                appointment_date = data.appointment_date and utc_2_local(data.appointment_date, tz) or False
                appointment_datetime= ''
                if appointment_date:
                    appointment_datetime= appointment_date.strftime('%d %b %I:%M %p')
                vals = {
                    'id': data.id,
                    'name': data.name,
                    'customer_name': data.customer_name and data.customer_name.upper() or '',
                    'applicant_first_name': data.applicant_first_name or '',
                    'applicant_middle_name':data.applicant_middle_name or '' ,
                    'applicant_last_name': data.applicant_last_name or '',
                    'co_applicant_first_name': data.co_applicant_first_name or '',
                    'co_applicant_middle_name':data.co_applicant_middle_name or '',
                    'co_applicant_last_name': data.co_applicant_last_name or '',
                    'co_applicant_phone': data.co_applicant_phone or '',
                    'co_applicant_email': data.co_applicant_email or '',
                    'co_applicant_address':data.co_applicant_address or '',
                    'co_applicant_city':data.co_applicant_city or '',
                    'co_applicant_state_id':data.co_applicant_state.id or '',
                    'co_applicant_state_code': data.co_applicant_state.code or '',
                    'co_applicant_state_name': data.co_applicant_state.name or '',
                    'co_applicant_zip':data.co_applicant_zip or '',
                    'co_applicant_secondary_phone':data.co_applicant_secondary_phone or '',
                    'is_room_measurement_exist':data.measurement_exist,
                    'customer_id': data.partner_id.id or 0,
                    'co_applicant': data.co_applicant or '',
                    'appointment_date': appointment_date,
                    'appointment_datetime': appointment_datetime,
                    'street': data.street or '',
                    'street2': data.street2 or '',
                    'city': data.city or '',
                    'state_id': data.state_id.id or 0,
                    'state_code': data.state_id.code or '',
                    'state': data.state_id.name or '',
                    'country_id': data.country_id.id or 0,
                    'country': data.country_id.name or '',
                    'zip':data.zip or '',
                    'country_code': data.country_id.code or '',
                    'phone': data.phone or '',
                    'mobile': data.mobile,
                    'email': data.email or '',
                    'sales_person': data.user_id.name or '',
                    'salesperson_id': data.user_id.id or 0,
                    'partner_latitude': data.partner_latitude or 0,
                    'partner_longitude': data.partner_longitude or 0,

                }
                list.append(vals)

        return list

    @api.model
    def get_appointment_data_filter(self, data):

        list = []
        customer_name = data.get('customer_name', '')
        user_id = data.get('uid', False)
        user = self.env['res.users'].browse(user_id)
        tz = user.tz or self._context.get('tz') or 'UTC'
        appointment_data = self.env['team.customer.appointment'].search([
            ('customer_name', 'ilike', '%'+customer_name),
            ('state', '=', 'scheduled'),
            ('user_id', '=', user_id)
        ], order='appointment_date asc')
        if appointment_data:
            for data in appointment_data:
                appointment_date = data.appointment_date and utc_2_local(data.appointment_date, tz) or False
                appointment_datetime = ''
                if appointment_date:
                    appointment_datetime = appointment_date.strftime('%d %b %I:%M %p')
                vals = {

                    'id': data.id,
                    'name': data.name,
                    'customer_name': data.customer_name and data.customer_name.upper() or '',
                    'customer_id': data.partner_id.id or 0,
                    'co_applicant': data.co_applicant or '',
                    'appointment_date': appointment_date or '',
                    'appointment_datetime': appointment_datetime or '',
                    'street': data.street or '',
                    'street2': data.street2 or '',
                    'city': data.city or '',
                    'state_id': data.state_id.id or 0,
                    'state': data.state_id.name or '',
                    'state_code': data.state_id.code or '',
                    'country_id': data.country_id.id or 0,
                    'country': data.country_id.name or '',
                    'country_code': data.country_id.code or '',
                    'zip': data.zip or '',
                    'phone': data.phone or '',
                    'mobile': data.mobile,
                    'email': data.email or '',
                    'co_applicant_address': data.co_applicant_address or '',
                    'co_applicant_city': data.co_applicant_city or '',
                    'co_applicant_state_id': data.co_applicant_state.id or '',
                    'co_applicant_state_code': data.co_applicant_state.code or '',
                    'co_applicant_state_name': data.co_applicant_state.name or '',
                    'co_applicant_zip': data.co_applicant_zip or '',
                    'co_applicant_secondary_phone': data.co_applicant_secondary_phone or '',
                    'sales_person': data.user_id.name or '',
                    'salesperson_id': data.user_id.id or 0,
                    'partner_latitude': data.partner_latitude or 0,
                    'partner_longitude': data.partner_longitude or 0,

                }
                list.append(vals)
            result = {
                'result': 'Success',
                'appointment_data': list,
                'message': '',
            }
        else:
            result = {
                'result': 'Failed',
                'appointment_data': list,
                'message': 'No Details Found',
            }
        return result

    @api.model
    def add_screenshots(self, data):
        status = {}
        appointment_id = data.get('appointment_id', False)
        if not appointment_id:
            _logger.info("------Empty Appointment id-------------")
            status = {'message': 'Empty Appointment id', 'result': 'Failed'}
            return status
        attachment_id = data.get('attachment_id', False)
        if not attachment_id:
            _logger.info("------Empty attachment_id id-------------")
            status = {'message': 'Empty attachment_id id', 'result': 'Failed'}
            return status
        appointment = self.env['team.customer.appointment'].search([('id', '=', int(appointment_id))], limit=1)
        if appointment and attachment_id:
            appointment.write({'attachment_ids': [(4, attachment_id)]})
            status= {
                'message': 'Snapshot uploaded successfully',
                'result': 'Success',
                'attachment_id': attachment_id
            }
        else:
            status = {
                'message': 'Wrong Appointment ID value',
                'result': 'Failed',
            }
        return status

class Product(models.Model):
    _inherit = 'product.template'

    improveit_product_id = fields.Char(string='i360 ReferenceID')

    @api.model
    def get_payment_method(self, data):
        appointment_id = int(data.get('appointment_id', 0))
        plan_id = int(data.get('paymentplan_id', 0))
        total_area = 0
        if appointment_id:
            room_measurements_lines = self.env['team.contract.room.measurement.line'].search([('appointment_id', '=', int(appointment_id))])
            if room_measurements_lines:
                for room_measurements_line in room_measurements_lines:
                    if not room_measurements_line.exclude_from_calculation:
                        total_area = total_area + room_measurements_line.adjusted_area


        downpayment_percentages = self.env['team.payment.percentage'].search([])
        payment_percentage = []
        if downpayment_percentages:
            for downpayment_percentage in downpayment_percentages:
                payment_percentage_values = {
                    'id': downpayment_percentage.id or 0,
                    'name': downpayment_percentage.name or '',
                    'percentage': downpayment_percentage.percentage or ''
                }
                payment_percentage.append(payment_percentage_values)
        downpayment_methods = self.env['team.downpayment.method'].search([])
        payment_method = []
        if downpayment_methods:
            for downpayment_method in downpayment_methods:
                downpayment_method_values = {
                    'id': downpayment_method.id or 0,
                    'name': downpayment_method.name or '',
                }
                payment_method.append((downpayment_method_values))

        values = {

            'downpayment_percetages': payment_percentage,
            'downpayment_method': payment_method,

        }

        return [values]

    def get_payment_options(self):
        payment_list = []
        all_payment_options = self.env['team.downpayment.option'].search([],order='sequence asc')
        for payment_options in all_payment_options:
            payment_options_dict = {
                'id':payment_options.id or 0,
                'Name': payment_options.name or '',
                'Description__c':payment_options.description or '' ,
                'Down_Payment__c':payment_options.down_payment or '',
                'Final_Payment__c':payment_options.final_payment or '',
                'Payment_Factor__c':payment_options.payment_factor or '' ,
                'Balance_Due__c':payment_options.balance_due or '',
                'Payment_Info__c':payment_options.payment_info or '',
                'sequence': payment_options.sequence or 0,
            }
            payment_list.append(payment_options_dict)
        return payment_list

    def get_payment_options_api(self):
        configurations = self.env['team.improveit.configuration'].search([('api_type', '=', 'boomi')])
        if configurations:
            end_point_url = configurations.token_url
            client_token = configurations.client_token
            if end_point_url and client_token:
                url = end_point_url + 'GetFinanceOptions' + client_token
                req = requests.get(url)
                req.raise_for_status()
                tree = ElementTree(fromstring(req.content))
                root = tree.getroot()
                payment_list = []
                for child_of_root in root:
                    finance_dict = {}
                    for child in child_of_root:
                        finance_dict[child.tag] = child.text if child.text is not None else 'false'
                    payment_list.append(finance_dict)
                return payment_list

    def get_discount_coupons(self):
        discount_coupon_list = []
        all_discount_coupons = self.env['team.monthly.promo'].search([])
        for discount_coupon in all_discount_coupons:
            discount_coupon_dict = {
                'Code': discount_coupon.code or '',
                'Amount': discount_coupon.amount or '',
                'Type': discount_coupon.type or '',
            }
            discount_coupon_list.append(discount_coupon_dict)
        return discount_coupon_list

    def get_discount_coupons_api(self):
        configurations = self.env['team.improveit.configuration'].search([('api_type', '=', 'boomi')])
        if configurations:
            end_point_url = configurations.token_url
            client_token = configurations.client_token
            if end_point_url and client_token:
                url = end_point_url + 'GetDiscountCodes' + client_token
                discount_coupon_list = []
                req = requests.get(url)
                req.raise_for_status()
                content = req.json()
                for discount_codes in content:
                    discount_coupon_list.append(discount_codes)
                return discount_coupon_list

    @api.model
    def get_payment_plan(self,data):
        payment_plan_list = []
        additional_cost=0
        color_up_charge_total = 0
        discount_exclude_amount = 0
        appointment_id = int(data.get('appointment_id', 0))
        contract_questions = self.env['team.contract.question.line'].search(
            [('appointment_id', '=', int(appointment_id))])

        for questions in contract_questions.filtered(lambda x: x.question_id.code != 'StairCount' and x. room_measurement_id and not x.room_measurement_id.exclude_from_calculation):
            if questions.extra_price and questions.answer_data:
                additional_cost += questions.extra_price
        for questions in contract_questions.filtered(lambda x: x.question_id.exclude_from_discount and x. room_measurement_id and not x.room_measurement_id.exclude_from_calculation):
            if questions.extra_price and questions.answer_data:
                discount_exclude_amount += questions.extra_price
        room_measurement_lines = self.env['team.contract.room.measurement.line'].search(
            [('appointment_id', '=', int(appointment_id)), ('exclude_from_calculation', '=', False)])
        for room in room_measurement_lines:
            color_up_charge_total += room.color_up_charge_total or 0
        if color_up_charge_total:
            additional_cost += color_up_charge_total
        floor_type_data = self.env['product.template'].search([('type','=','product'),('product_variant_ids','!=',False), ('categ_id.name', 'not ilike', 'Stairs')], order='sequence asc')
        if floor_type_data:
            for data in floor_type_data:
                stair_product = self.env['product.template'].search([
                    ('type','=','product'),
                    ('product_variant_ids','!=',False),
                    ('categ_id.name', 'ilike', 'Stairs'),
                    ('grade', '=', data.grade)
                ], order='sequence asc', limit=1)
                warranty=dict(data._fields['warranty'].selection).get(data.warranty)
                vals = {
                    'id': data.id,
                    'plan_title': data.name or '',
                    'plan_subtitle': data.payment_plan or '',
                    'description': data.description or '',
                    'material_cost':data.list_price,
                    'warranty': warranty or '',
                    'sequence': data.sequence or '',
                    'company_id': data.company_id.id or 0,
                    'cost_per_sqft': data.msrp or 0,
                    'monthly_promo':data.monthly_promo or 0,
                    'additional_cost': additional_cost,
                    'discount_exclude_amount': discount_exclude_amount,
                    'warranty_info':data.warranty_info or '',
                    'eligible_for_discounts':data.eligible_for_discounts or '',
                    'unit_of_measure':data.unit_of_measure or '',
                    'grade': data.grade or '',
                    'stair_cost': stair_product and stair_product.list_price or 0

                }
                payment_plan_list.append(vals)

        # payment_options = self.env['team.downpayment.option'].search([('active', '=', True)])
        # list_payment_option = []
        # if payment_options:
        #
        #     for payment_option in payment_options:
        #         payment_option_values = {
        #             'id': payment_option.id or 0,
        #             'title': payment_option.name or '',
        #             'subtitle': payment_option.description or '',
        #             'interest_rate':payment_option.interest_rate or 0.0
        #         }
        #         list_payment_option.append(payment_option_values)

        # list = []
        # product_list = self.env['product.product'].search([('is_material', '=', True)])
        # if product_list:
        #     for product in product_list:
        #         material_image_url = ''
        #         if product.image_1920:
        #             material_image_url = product.profile_image('product.product')
        #         vals = {
        #             'material_id': product.id or 0,
        #             'name': product.name,
        #             'color': product.color or 'False',
        #             'material_image_url': material_image_url,
        #         }
        #         list.append(vals)

        # payment_option_list = self.get_payment_options_api()
        # discount_coupon_list = self.get_discount_coupons_api()

        payment_option_list = self.get_payment_options()
        discount_coupon_list = self.get_discount_coupons()

        values = {
            'payment_plans': payment_plan_list,
            'payment_options': payment_option_list,
            'monthly_promo':discount_coupon_list,
            # 'materials': list,
            'admin_fee' : float(self.env['ir.config_parameter'].sudo().get_param('admin_fee')) or 0.0,
            'min_sale_price': float(self.env['ir.config_parameter'].sudo().get_param('min_sale_price')) or 0.0
        }
        return [values]


class TeamQuoteQuestion(models.Model):
    _inherit = 'team.quote.question'


    def get_quote_label(self):
        list=[]
        if not self.constr_mandatory:
            list.append({
                'question_id': self.id,
                'value': '',
            })
        if self.labels_ids:
            for label in self.labels_ids:

                vals ={
                'question_id' : label.question_id.id or 0,
                'sequence' : label.sequence,
                'value' : label.value or '',
                'is_correct' : label.is_correct,
                'answer_score' : label.answer_score or 0,
                }

                list.append(vals)
        return list


    @api.model
    def get_question_data(self,data):
        type=data.get('type')
        room_id=data.get('room_id')
        list = []
        product_category_id = 0
        room_obj = self.env['team.room.room'].search([('id', '=', int(room_id))])
        if room_obj and room_obj.product_category_id:
            product_category_id = room_obj.product_category_id.id
        quote_question = self.env['team.quote.question'].search([
            ('active', '=', True),
            (type, '=', True),
            ('room_ids','in',[int(room_id)]),
            ('product_category_ids','in',[int(product_category_id)]),
        ])
        if quote_question:
            for data in quote_question:
                quote_label = data.get_quote_label()
                vals = {
                    'id': data.id,
                    'name': data.name or '',
                    'code': data.code or '',
                    'company_id': data.company_id.id,
                    'description': data.description or '',
                    'question_type': data.question_type or '',
                    'validation_required': data.validation_required,
                    'validation_email_required': data.validation_email,
                    'validation_error_msg': data.validation_error_msg or '',
                    'mandatory_answer': data.constr_mandatory or '',
                    'Error_message': data.constr_error_msg or '',
                    'Refelct_in_cost': data.reflect_cost,
                    'calculation_type': data.calculation_type,
                    'amount': data.amount or 0,
                    'default_answer': data.default_answer or '',
                    'quote_label': quote_label,
                    'exclude_from_discount': data.exclude_from_discount,
                }
                list.append(vals)

        return list


class TeamTransitionLine(models.Model):
    _inherit= 'team.contract.transition.line'

    @api.model
    def get_transition_data(self, vals):
        list = []
        appointment_id = vals.get('appointment_id', 0)
        room_id = vals.get('room_id', 0)
        room_measurement_id = vals.get('room_measurement_id', 0)
        custom_room = False
        if self.env['team.room.room'].browse(int(room_id)).is_custom:
            custom_room = True
            if not room_measurement_id:
                _logger.info("------Custom Room_id Empty-------------")
                status = {'message': 'room_measurement_id Empty', 'result': 'Success'}
                return status
            if not self.env['team.contract.room.measurement.line'].browse(int(room_measurement_id)).exists():
                _logger.info("------Custom Room Not Exist-------------")
                status = {'message': 'Custom Room Not Exist', 'result': 'Success'}
                return status
        if appointment_id and  room_id:
            if custom_room:
                domain = [('room_measurement_id','=',int(room_measurement_id)),('appointment_id', '=', int(appointment_id)),('room_id', '=', int(room_id))]
            else:
                domain = [('appointment_id', '=', int(appointment_id)),('room_id', '=', int(room_id))]
            transitions = self.env['team.contract.transition.line'].search(domain)
            if transitions:
                for transition in transitions:
                    attachments = []
                    for attachment in transition.attachment_ids:
                        if not attachment.access_token:
                            attachment.generate_access_token()
                        url = URL + '/web/image/' + str(attachment.id) + '?access_token=' + str(attachment.access_token)
                        attachments.append({
                            'id': attachment.id,
                            'name':attachment.name,
                            'url': url,
                        })

                    vals = {
                        'id': transition.id,
                        'name': transition.name or '',
                        'transition_width': transition.transition_width or 0,
                        'room_id': transition.room_id.id or 0,
                        'room_name': transition.room_measurement_id.custom_room_name if custom_room else transition.room_id.name or '',
                        'company_id': transition.company_id.id or 0,
                        'attachments':attachments,
                        'custom_room':custom_room,
                        'custom_room_id':transition.room_measurement_id.id if custom_room else ''
                    }
                    list.append(vals)

        return list

    @api.model
    def create_transitions(self, data):
        obj = self.env['team.contract.transition.line']
        status={}
        description = data.get('name', '')
        if not description:
            _logger.info("------Description Empty-------------")
            status = {'message': 'Description Empty', 'result': 'Success'}
            return status
        appointment_id = data.get('appointment_id', False)
        if not appointment_id:
            _logger.info("------Appointment Data Empty-------------")
            status = {'message': 'Appointment Data Empty', 'result': 'Success'}
            return status
        if not self.env['team.customer.appointment'].browse(int(appointment_id)).exists():
            _logger.info("------ Appointment ID Error-------------")
            status = {'message': 'Appointment ID Error', 'result': False}
            return status
        transition_width = data.get('transition_width',0)
        room_id = data.get('room_id',False)
        if not room_id:
            _logger.info("------ Room_id Empty-------------")
            status = {'message': 'Room_id Empty', 'result': 'Success'}
            return status
        if not self.env['team.room.room'].browse(int(room_id)).exists():
            _logger.info("------ Room not Exist-------------")
            status = {'message': 'Room not Exist', 'result': 'Success'}
            return status
        custom_room = False
        if self.env['team.room.room'].browse(int(room_id)).is_custom:
            room_measurement_id = data.get('room_measurement_id','')
            custom_room =True
            if not room_measurement_id:
                _logger.info("------Custom Room_id Empty-------------")
                status = {'message': 'room_measurement_id Empty', 'result': 'Success'}
                return status
            if not self.env['team.contract.room.measurement.line'].browse(int(room_measurement_id)).exists():
                _logger.info("------Custom Room Not Exist-------------")
                status = {'message': 'Custom Room Not Exist', 'result': 'Success'}
                return status
            measurement_line = self.env['team.contract.room.measurement.line'].search([('id','=',int(room_measurement_id)),('appointment_id','=',int(appointment_id))])
            if not measurement_line:
                _logger.info("------Wrong Measurement ID For custom Room-------------")
                status = {'message': 'Wrong Measurement ID For custom Room', 'result': 'Success'}
                return status
        attachment_ids = data.get('image_ids', [])
        vals = {
            "name":description,
            "transition_width": transition_width,
            "room_id": int(room_id),
            'appointment_id': int(appointment_id),
            'room_measurement_id': int(room_measurement_id) if custom_room else False,
        }
        if attachment_ids:
            vals.update({'attachment_ids': [(6, 0, attachment_ids)]})
        record=obj.create(vals)
        if record:
            for attachment in self.env['ir.attachment'].browse(attachment_ids):
                if attachment.exists():
                    attachment.write({
                        'res_model': 'team.contract.transition.line',
                        'res_id': record.id,
                    })
            _logger.info("------Transition created-------------")
            status={
                'message':'Transition created',
                'result': 'Success',
                'transition_id':record.id}

        else:
            _logger.info("------Transition creation Failed-------------")
            status = {
                'message': 'Transition Creation Failed',
                'result':'Success'
            }
        return status

    @api.model
    def transition_delete_api(self, data):
        transition_ids = data.get('transition_ids', [])
        if not transition_ids:
            _logger.info("------Transition ID Empty------------")
            status = {
                'message': 'Transition ID Empty',
                'result': 'Failed',
            }
        for transition_id in transition_ids:
            transition = self.sudo().search([('id', '=', transition_id)])
            if transition:
                attachment = transition.attachment_ids
                if attachment:
                    _logger.info("------Transition Deleted And Attachment Deleted------------")
                    attachment.sudo().unlink()
                    transition.sudo().unlink()
                    status = {
                        'message': 'Transition and Attachment Removed',
                        'result': 'Success',
                    }
                else:
                    transition.sudo().unlink()
                    _logger.info("------Transition Deleted But Attachment Not Found------------")
                    status = {
                        'message': 'Transition Removed But Attachment Not Found',
                        'result': 'Success',
                    }
            else:
                _logger.info("------Transition Not Found------------")
                status = {
                    'message': 'Transition Not Found',
                    'result': 'Failed',
                }
        return status

class TeamContractQuestions(models.Model):
    _inherit = 'team.contract.question.line'

    @api.model
    def create_contract_questions(self, data):
        obj = self.env['team.contract.question.line']
        status = {}
        records_created = {}
        question_data = data.get('questions', [])
        appointment_id = data.get('appointment_id', 0)
        room_id = data.get('room_id', 0)
        _logger.info("create_contract_questions data: %s"%(data))
        if not self.env['team.customer.appointment'].browse(int(appointment_id)).exists():
            _logger.info("------ Appointment ID Error-------------")
            status = {'message': 'Appointment ID Error', 'result': 'False'}
            return status
        if not self.env['team.room.room'].browse(int(room_id)).exists():
            _logger.info("------ Room ID Error-------------")
            status = {'message': 'Room ID Error', 'result': 'False'}
            return status
        custom_room = False
        room_measurement_id = data.get('room_measurement_id', '')
        if self.env['team.room.room'].browse(int(room_id)).is_custom:
            custom_room = True
            if not room_measurement_id:
                _logger.info("------Custom Room_id Empty-------------")
                status = {'message': 'room_measurement_id Empty', 'result': 'Success'}
                return status
            if not self.env['team.contract.room.measurement.line'].browse(int(room_measurement_id)).exists():
                _logger.info("------Custom Room Not Exist-------------")
                status = {'message': 'Custom Room Not Exist', 'result': 'Success'}
                return status
        if appointment_id:
            if custom_room:
                contract_questions = self.env['team.contract.question.line'].search(
                    [('appointment_id', '=', int(appointment_id)), ('room_measurement_id', '=', int(room_measurement_id))])
            else:
                contract_questions = self.env['team.contract.question.line'].search(
                [('appointment_id', '=', int(appointment_id)), ('room_id', '=', int(room_id))])
            if contract_questions:
                for answer_to_update in question_data:
                    quote_question_id = answer_to_update.get('question_id', False)
                    if custom_room:
                        contract_questions_filtered = self.env['team.contract.question.line'].search(
                            [('question_id', '=', quote_question_id), ('appointment_id', '=', int(appointment_id)),
                             ('room_measurement_id', '=', int(room_measurement_id))])
                    else:
                        contract_questions_filtered = self.env['team.contract.question.line'].search(
                        [('question_id','=',quote_question_id),('appointment_id', '=', int(appointment_id)), ('room_id', '=', int(room_id))])

                    for contract_question in contract_questions_filtered:
                        answer_obj = self.env['team.contract.answer.line']
                        for answer in contract_question.answers:
                            answer.sudo().unlink()

                        contract_question.write({'question_id': answer_to_update.get('question_id', False), 'room_measurement_id': room_measurement_id})
                        answers = answer_to_update.get('answer', [])
                        answer_exists = False
                        for answer in answers:
                            if answer:
                                answer_exists = True
                                values = {}
                                values.update({'question_id': contract_question.id})
                                values.update({'answer': answer})
                                answer_record = answer_obj.create(values)
                        if not answer_exists:
                            contract_question.unlink()
                _logger.info("------ Team contract Question Line Answers Updated  -------------")
                status = {'message': 'Team contract Question Line Answers Updated', 'result': 'Success'}
                return status
        for questions in question_data:
            vals = {}
            name = data.get('name', '')
            appointment_id = data.get('appointment_id', False)
            if not appointment_id:
                _logger.info("------Appointment Data Empty-------------")
                status = {'message': 'Appointment Data Empty', 'result': 'False'}
                return status
            room_id = data.get('room_id', False)
            if not room_id:
                _logger.info("------ Room_id Empty-------------")
                status = {'message': 'Room_id Empty', 'result': 'False'}
                return status
            if room_measurement_id:
                vals.update({'room_measurement_id': int(room_measurement_id)})
            question_id = questions.get('question_id', False)
            if not question_id:
                _logger.info("------ Question Data Empty-------------")
                status = {'message': 'Question Data Empty', 'result': 'False'}
                return status
            if self.env['team.room.room'].browse(int(room_id)).exists():
                vals.update({'room_id': int(room_id)})
            else:
                _logger.info("------ Room ID Error-------------")
                status = {'message': 'Room ID Error', 'result': 'False'}
                return status
            if self.env['team.quote.question'].browse(int(question_id)).exists():
                vals.update({'question_id': int(question_id)})
            else:
                _logger.info("------ Question ID Error-------------")
                status = {'message': 'Question ID Error', 'result': 'False'}
                return status
            if self.env['team.customer.appointment'].browse(int(appointment_id)).exists():
                vals.update({'appointment_id': int(appointment_id)})
            else:
                _logger.info("------ Appointment ID Error-------------")
                status = {'message': 'Appointment ID Error', 'result': 'False'}
                return status
            vals.update({'name': name})
            answers = questions.get('answer', [])
            answer_obj = self.env['team.contract.answer.line']
            answer_list = []
            answer_exists = False
            for answer in answers:
                if answer:
                    answer_exists = True
            if answer_exists:
                record = obj.create(vals)
                for answer in answers:
                    if answer:
                        values = {}
                        values.update({'question_id': record.id})
                        values.update({'answer': answer})
                        answer_record = answer_obj.create(values)
                        answer_list.append(answer_record.id)
                records_created.update({str(record.id): answer_list})

        _logger.info("------Contract Questions created-------------")
        status = {
                'message': 'Contract Question Created',
                'result': 'Success',
                'question_answer_ids': records_created
            }
        return status

    @api.model
    def list_contract_question_line(self, vals):
        list = []
        status={}
        appointment_id = vals.get('appointment_id', 0)
        room_id = vals.get('room_id', 0)
        if appointment_id:
            if self.env['team.room.room'].browse(int(room_id)).is_custom:
                room_measurement_id = vals.get('room_measurement_id', '')
                custom_room = True
                if not room_measurement_id:
                    _logger.info("------Custom Room_id Empty-------------")
                    status = {'message': 'room_measurement_id Empty', 'result': 'Success'}
                    return status
            if custom_room:
                contract_questions = self.env['team.contract.question.line'].search(
                    [('appointment_id', '=', int(appointment_id)), ('room_measurement_id', '=', int(room_measurement_id))])
            else:
                contract_questions = self.env['team.contract.question.line'].search(
                [('appointment_id', '=', int(appointment_id)), ('room_id', '=', int(room_id))])
            if contract_questions:
                for data in contract_questions:
                    if data.room_id.is_custom:
                        custom_room = 'True'
                    else:
                        custom_room = 'False'
                    list_answers = []
                    for answer in data.answers:
                        answer_vals = {
                            'id': answer.id,
                            'contract_question_line_id': answer.question_id.id,
                            'answer': answer.answer
                        }
                        list_answers.append(answer_vals)
                    vals = {
                        'contract_question_line_id': data.id,
                        'name': data.name or '',
                        'room_id': data.room_id.id or 0,
                        'room_name':data.room_measurement_id.custom_room_name if custom_room else data.room_id.name or '',
                        'company_id': data.company_id.id or 0,
                        'appointment_id': data.appointment_id.id or 0,
                        'question_id': data.question_id.id or 0,
                        'question':data.question_id.name,
                        'answers': list_answers,
                        'custom_room':custom_room
                    }
                    list.append(vals)
                status = {
                    'result': 'Success',
                    'values': list,
                    'message': '',
                }
            else:
                status = {
                    'result': 'Success',
                    'values': list,
                    'message': 'No contract_questions',
                }
        return status

    @api.model
    def remove_contract_question_line(self, data):
        question_line_ids = data.get('question_ids', [])
        if not question_line_ids:
            _logger.info("------Question Line ID Empty------------")
            status = {
                'message': 'Question Line ID Empty',
                'result': 'Failed',
            }
        for question_id in question_line_ids:
            question = self.sudo().search([('id', '=', question_id)])
            for answers in question.answers:
                answers.sudo().unlink()
            if question:
                question.sudo().unlink()
                _logger.info("------Question Line Deleted------------")
                status = {
                    'message': 'Question Line Removed',
                    'result': 'Success',
                }
            else:
                _logger.info("------Question Line Not Found------------")
                status = {
                    'message': 'Question Line Not Found',
                    'result': 'Failed',
                }
        return status

    @api.model
    def update_contract_question_line(self, data):
        appointment_id = data.get('appointment_id', 0)
        room_id = data.get('room_id', 0)
        if not self.env['team.room.room'].browse(int(room_id)).exists():
            _logger.info("------ Room ID Error-------------")
            status = {'message': 'Room ID Error', 'result': 'False'}
            return status
        if not appointment_id:
            _logger.info("------Empty Appointment id-------------")
            status = {'message': 'Empty Appointment id', 'result': 'Success'}
            return status
        if not self.env['team.customer.appointment'].browse(int(appointment_id)).exists():
            _logger.info("------ Appointment Not Exist-------------")
            status = {'message': 'Appointment Not Exist', 'result': 'Success'}
            return status
        if appointment_id:
            contract_questions = self.env['team.contract.question.line'].search(
                [('appointment_id', '=', int(appointment_id)), ('room_id', '=', int(room_id))])
            for contract_question in contract_questions:
                for answers in contract_question.answers:
                    answers.sudo().unlink()
                contract_question.sudo().unlink()
            create_questions = self.create_contract_questions(data)
            return create_questions

        # for contract_questions in data:
        #     question_id = contract_questions.get('contract_question_line_id', False)
        #     if not question_id:
        #         _logger.info("------Empty Contract Question Line ID-------------")
        #         status = {'message': 'Empty Contract Question Line ID', 'result': False}
        #         return status
        #     question = self.env['team.contract.question.line'].search([('id', '=', int(question_id))], limit=1)
        #     vals = {}
        #     if question:
        #         if contract_questions.get('name', ''):
        #             vals.update({'name': contract_questions.get('name')})
        #         if contract_questions.get('room_id', False):
        #             if self.env['team.room.room'].browse(int(contract_questions.get('room_id', False))).exists():
        #                 vals.update({'room_id': int(contract_questions.get('room_id'))})
        #             else:
        #                 return {'message': 'Wrong Room ID', 'result': False}
        #         if contract_questions.get('question_id', False):
        #             if self.env['team.quote.question'].browse(int(contract_questions.get('question_id', False))).exists():
        #                 vals.update({'question_id': int(contract_questions.get('question_id'))})
        #             else:
        #                 return {'message': 'Wrong Question ID', 'result': False}
        #         if contract_questions.get('appointment_id', False):
        #             if self.env['team.customer.appointment'].browse(int(contract_questions.get('appointment_id', False))).exists():
        #                 vals.update({'appointment_id': int(contract_questions.get('appointment_id'))})
        #             else:
        #                 return {'message': 'Wrong Appointment ID', 'result': False}
        #         if contract_questions.get('answers', []):
        #             answers = contract_questions.get('answers', [])
        #             for answer in answers:
        #                 if self.env['team.contract.answer.line'].browse(int(answer.get('id', False))).exists() and (
        #                         int(answer.get('contract_question_line_id', '')) == int(question_id)):
        #                     answer_line = self.env['team.contract.answer.line'].browse(int(answer.get('id', False)))
        #                     if answer_line.question_id.id == int(question_id):
        #                         if answer.get('answer', ''):
        #                             answer_line.write({'answer': answer.get('answer', '')})
        #                     else:
        #                         return {'message': 'Wrong  Contract Question_line ID  or Wrong Answer ID Provided',
        #                                 'result': False}
        #                 else:
        #                     return {
        #                         'message': 'Wrong Answer Data , Either Answer  Not Exist or Wrong Contract Question_line ID ',
        #                         'result': False}
        #
        #         update = question.write(vals)
        #         status = {'message': 'Contract Question Line Update Success', 'result': True}
        #     else:
        #         status = {'message': 'Contract Question Line not found', 'result': False}
        # return status


class TeamContractRoomMeasurement(models.Model):
    _inherit = 'team.contract.room.measurement.line'

    improveit_id = fields.Char('Improveit Reference ID')

    @api.model
    def Checkroomstatus(self,data):
        appointment_id = int(data.get('appointment_id', False))
        room_id = int(data.get('room_id', False))
        if appointment_id and room_id:
            contract_room_lines = self.env['team.contract.room.measurement.line'].search([('appointment_id', '=', appointment_id),('room_id', '=', room_id)])
            if contract_room_lines:
                status = {'result': 'True','message': 'Contract Room line  already exist for this appointment'}
                return status
            else:
                status = {'result': 'False','message': 'No Contract Room line Exist for this appointment  ' }
                return status
        else:
            status =  {'result': 'False','message': 'No Contract Room line Exist for this appointment  '}
            return status

    @api.model
    def create_stair_room_measurement(self, data):
        obj = self.env['team.contract.room.measurement.line']
        status = {}
        name = data.get('name', '')
        appointment_id = int(data.get('appointment_id', 0))
        if not appointment_id:
            _logger.info("------Appointment Data Empty-------------")
            status = {'message': 'Appointment Data Empty', 'result': False}
            return status
        room_id = int(data.get('room_id', 0))
        if not room_id:
            _logger.info("------ Room_id Empty-------------")
            status = {'message': 'Room_id Empty', 'result': False}
            return status
        vals = {}
        vals.update({'name': name})
        vals.update({'room_area': float(data.get('room_area', 0))})
        vals.update({'adjusted_area': float(data.get('room_area', 0))})
        if self.env['team.customer.appointment'].browse(int(appointment_id)).exists():
            vals.update({'appointment_id': int(appointment_id)})
        else:
            _logger.info("------ Appointment ID Error-------------")
            status = {'message': 'Appointment ID Error', 'result': False}
            return status
        if self.env['team.room.room'].browse(int(room_id)).exists():
            vals.update({'room_id': int(room_id)})
        else:
            _logger.info("------ Room ID Error-------------")
            status = {'message': 'Room ID Error', 'result': False}
            return status
        room_measurements_line = self.env['team.contract.room.measurement.line'].search(
            [('appointment_id', '=', int(appointment_id)), ('room_id', '=', int(room_id))], limit=1)

        if room_measurements_line:
            data.update({
                'contract_measurement_id': room_measurements_line.id,
                'room_id': room_id,
                'appointment_id': appointment_id,
            })
            return self.update_room_measurement(data)
        record = obj.create(vals)
        if record:
            _logger.info("------ created-------------")
            status = {
                'result': 'Success',
                'message': 'Contract Room Measurement Created',
                'contract_measurement_id': record.id,
            }
        else:
            _logger.info("-------Contract Room Measurement Creation Failed-----------")
            status = {
                'result': 'Failed',
                'message': 'Contract Room Measurement Creation Failed '
            }
        return status

    @api.model
    def create_room_measurement(self, data):
        obj = self.env['team.contract.room.measurement.line']
        status = {}
        name = data.get('name', '')
        shape_image_id = int(data.get('shape_image_id', 0))
        appointment_id = int(data.get('appointment_id', 0))
        if not appointment_id:
            _logger.info("------Appointment Data Empty-------------")
            status = {'message': 'Appointment Data Empty', 'result': False}
            return status
        room_id = int(data.get('room_id', 0))
        if not room_id:
            _logger.info("------ Room_id Empty-------------")
            status = {'message': 'Room_id Empty', 'result': False}
            return status
        if not shape_image_id:
            _logger.info("------Room Shape Drawing Image Empty-------------")
            status = {'message': 'Room Shape Drawing Empty', 'result': False}
            return status
        vals = {}
        vals.update({'name': name})
        vals.update({'room_area': float(data.get('room_area', 0))})
        vals.update({'adjusted_area': float(data.get('room_area', 0))})
        vals.update({'room_perimeter': float(data.get('room_perimeter', 0))})
        if self.env['ir.attachment'].browse(int(shape_image_id)).exists():
            vals.update({'shape_image_id': int(shape_image_id)})
        else:
            _logger.info("------Shape Drawing Image Id  Error-------------")
            status = {'message': 'Shape Drawing Image ID Error', 'result': False}
            return status
        if self.env['team.customer.appointment'].browse(int(appointment_id)).exists():
            vals.update({'appointment_id': int(appointment_id)})
        else:
            _logger.info("------ Appointment ID Error-------------")
            status = {'message': 'Appointment ID Error', 'result': False}
            return status
        custom_room = False
        custom_room_measured = False
        if self.env['team.room.room'].browse(int(room_id)).exists():
            vals.update({'room_id': int(room_id)})
            if self.env['team.room.room'].browse(int(room_id)).is_custom:
                data.update({'adjusted_area': float(data.get('room_area', 0))})
                custom_room = True
                room_measurement_id = int(data.get('room_measurement_id', 0))
                if not room_measurement_id:
                    _logger.info("------Custom Room id  Empty-------------")
                    status = {'message': 'Custom Room id  Empty', 'result': 'Success'}
                    return status
                room_measurements_line = self.env['team.contract.room.measurement.line'].search(
                    [('id', '=', int(room_measurement_id))])
                if not room_measurements_line:
                    _logger.info("------NO Room measurements line Exist for room_measurement_id -------------")
                    status = {'message': 'NO Room measurements line Exist for room_measurement_id', 'result': 'Success'}
                    return status
                if room_measurements_line and not room_measurements_line.custom_room_measured:
                    data.update({
                        'contract_measurement_id': room_measurements_line.id,
                        'image_id': shape_image_id,
                        'room_id': room_id,
                        'appointment_id': appointment_id,
                    })
                    return self.update_room_measurement(data)
                else:
                    custom_room_measured = True
                    data.update({
                        'contract_measurement_id': room_measurements_line.id,
                        'image_id': shape_image_id,
                        'room_id': room_id,
                        'appointment_id': appointment_id,
                    })
                    # transitions = self.env['team.contract.transition.line'].search(
                    #     [('appointment_id', '=', appointment_id),
                    #      ('room_measurement_id', '=', room_measurements_line.id)])
                    # for transition in transitions:
                    #     for attachment in transition.attachment_ids:
                    #         attachment.sudo().unlink()
                    #     transition.sudo().unlink()
                    # questionaires = self.env['team.contract.question.line'].search(
                    #     [('room_measurement_id', '=', room_measurements_line.id),
                    #      ('appointment_id', '=', appointment_id)])
                    # for questionaire in questionaires:
                    #     for answer in questionaire.answers:
                    #         answer.sudo().unlink()
                    #     questionaire.sudo().unlink()
                    return self.update_room_measurement(data)

        else:
            _logger.info("------ Room ID Error-------------")
            status = {'message': 'Room ID Error', 'result': False}
            return status
        if not custom_room:
            room_measurements_line = self.env['team.contract.room.measurement.line'].search(
                [('appointment_id', '=', int(appointment_id)), ('room_id', '=', int(room_id))], limit=1)

        if room_measurements_line:
            if room_measurements_line.transition_line_id:
                room_measurements_line.transition_line_id.unlink()
            data.update({
                'contract_measurement_id': room_measurements_line.id,
                'image_id': shape_image_id,
                'room_id': room_id,
                'appointment_id': appointment_id,
            })
            # transitions = self.env['team.contract.transition.line'].search(
            #     [('appointment_id', '=', appointment_id),
            #      ('room_id', '=', room_id)])
            # for transition in transitions:
            #     for attachment in transition.attachment_ids:
            #         attachment.sudo().unlink()
            #     transition.sudo().unlink()
            # questionaires = self.env['team.contract.question.line'].search(
            #     [('room_id', '=', room_id),
            #      ('appointment_id', '=', appointment_id)])
            # for questionaire in questionaires:
            #     for answer in questionaire.answers:
            #         answer.sudo().unlink()
            #     questionaire.sudo().unlink()
            return self.update_room_measurement(data)

        record = obj.create(vals)
        if record:
            for transition_data in data.get('transitions', []):
                self.env['team.contract.transition.line'].create({
                    'name': transition_data.get('transition_type', ''),
                    'transition_width': float(transition_data.get('transition_width', 0)),
                    'room_measurement_id': record.id,
                    'room_id': room_id,
                    'appointment_id': appointment_id,
                })
                _logger.info('Transition Created: %s'%(transition_data))

            _logger.info("------ Contract Room Measurement Created-------------")
            status = {
                'result': 'Success',
                'message': 'Contract Room Measurement Created',
                'contract_measurement_id': record.id,
            }
        else:
            _logger.info("-------Contract Room Measurement Creation Failed-----------")
            status = {
                'result': 'Failed',
                'message': 'Contract Room Measurement Creation Failed '
            }
        return status

    @api.model
    def update_material_details(self, data):
        measurement_id = int(data.get('measurement_id', 0))
        material_id = int(data.get('material_id', 0))
        comments = data.get('comments', '')
        status = {}
        if measurement_id and material_id:
            measurement_ref = self.env['team.contract.room.measurement.line'].search([('id', '=', measurement_id)])
            material = self.env['product.product'].browse(material_id)
            measurement_ref.write({
                'material_id': material_id,
                'material_comments':comments,
                'color_up_charge_price': material.color_up_charge_price or 0,
            })
            _logger.info("------Material created-------------")
            status = {
                'message': 'Material Updated',
                'result': 'Success', }
        else:
            _logger.info("------measurement_id or material_id Empty-------------")
            status = {'message': 'measurement_id or material_id Empty', 'result': 'False'}
        return status

    @api.model
    def update_material_details_room(self, data):
        measurement_id = int(data.get('measurement_id', 0))
        material_id = int(data.get('material_id', 0))
        comments = data.get('comments', '')
        status = {}
        if measurement_id and material_id:
            measurement_ref = self.env['team.contract.room.measurement.line'].search([('id', '=', measurement_id)])
            material = self.env['product.product'].browse(material_id)
            measurement_ref.write({
                'material_id': material_id,
                'material_comments': comments,
                'color_up_charge_price': material.color_up_charge_price or 0,
            })
            _logger.info("------Material created-------------")
            if measurement_ref.appointment_id:
                response =  self.env['team.contract.room.measurement.line'].list_contract_room_measurement_line({"appointment_id": measurement_ref.appointment_id.id})
                return response

            else:
                _logger.info("------Appointment id  Empty-------------")
                status = {'message': 'Appointment id  is not available in measurement line', 'result': 'False'}
            return status

        else:
            _logger.info("------measurement_id or material_id Empty-------------")
            status = {'message': 'measurement_id or material_id Empty', 'result': 'False'}
        return status

    @api.model
    def update_moulding(self, data):
        measurement_id = int(data.get('measurement_id', 0))
        moulding = data.get('moulding_type', '')
        status = {}
        if measurement_id and moulding:
            measurement_ref = self.env['team.contract.room.measurement.line'].search([('id', '=', measurement_id)])
            molding_type = self.env['team.floor.molding'].search([('name', '=', moulding)], limit=1)
            if molding_type:
                measurement_ref.write({'molding_type_id': molding_type.id})
            else:
                _logger.info('--------------Molding is not existing------------')
                return {
                    'result': 'False',
                    'message': 'Selected Molding is not existing in the system'
                }
            _logger.info("------Moulding created-------------")
            if measurement_ref.appointment_id:
                response = self.env['team.contract.room.measurement.line'].list_contract_room_measurement_line(
                    {"appointment_id": measurement_ref.appointment_id.id})
                return response
            else:
                _logger.info("------Appointment id  Empty-------------")
                status = {'message': 'Appointment id  is not available in measurement line', 'result': 'False'}
            return status

        else:
            _logger.info("------measurement_id or material_id Empty-------------")
            status = {'message': 'measurement_id or material_id Empty', 'result': 'False'}
        return status

    @api.model
    def list_overall_room_summary(self, vals):
        appointment_id = vals.get('appointment_id', 0)
        status={}
        room_list=[]
        room_values = {}
        if appointment_id:
            room_measurements_list = self.env['team.contract.room.measurement.line'].search(
                [('appointment_id', '=', int(appointment_id))])
            for room_measurements in room_measurements_list:
                shape_image_url = []
                if room_measurements.shape_image_id:
                    if not room_measurements.shape_image_id.access_token:
                        room_measurements.shape_image_id.generate_access_token()
                    url = URL + '/web/image/' + str(
                        room_measurements.shape_image_id.id) + '?access_token=' + str(
                        room_measurements.shape_image_id.access_token)
                    shape_image_url.append({
                        'id': room_measurements.shape_image_id.id,
                        'name': room_measurements.shape_image_id.name,
                        'url': url,
                    })
                room_ids = list(set([(data.room_id.id) for data in room_measurements]))
                material_image_url=''
                material = 0
                if room_measurements.material_id.id:
                    material_ref = self.env['product.product'].search([('id', '=', int(room_measurements.material_id.id))])
                    if material_ref and material_ref.is_material==True:
                        material=material_ref.id
                        if material_ref.image_1920:
                            material_image_url = material_ref.profile_image('product.product')

                stair_count = 0
                if room_measurements.room_id and room_measurements.room_id.product_category_id and room_measurements.room_id.product_category_id.name.upper() == 'VINYL STAIRS':
                    contract_questions = self.env['team.contract.question.line'].search([
                        ('room_id', '=', room_measurements.room_id.id),
                        ('appointment_id', '=', int(appointment_id)),
                        ('question_id.code', '=', 'StairCount')
                    ], limit=1)
                    if contract_questions:
                        for answer_obj in contract_questions.answers:
                            stair_count = answer_obj.answer
                room_values = {
                    'room_ids': room_ids,
                    'material_id':material,
                    'striked':'True' if room_measurements.exclude_from_calculation is True else 'False',
                    'material_image_url':material_image_url,
                    'shape_image_id':room_measurements.shape_image_id and room_measurements.shape_image_id.id or 0,
                    'stair_count': stair_count,
                }
                room_list.append(room_values)
            status = {
                    'result': 'Success',
                    'values': room_list,
                    'message': '',
                }
            return status

    @api.model
    def list_room_measurement(self,vals):
            list = []
            status={}
            appointment_id = vals.get('appointment_id', 0)
            room_id = vals.get('room_id', 0)
            if not self.env['team.room.room'].browse(int(room_id)).exists():
                _logger.info("------Room Not Exist-------------")
                status = {'message': 'Room Not Exist', 'result': 'Success'}
                return status
            custom_room = False
            if self.env['team.room.room'].browse(int(room_id)).is_custom:
                custom_room =True
                room_measurement_id = vals.get('room_measurement_id', 0)
                if not room_measurement_id:
                    _logger.info("------room_measurement_id empty-------------")
                    status = {'message': 'room_measurement_id empty', 'result': 'Success'}
                    return status
                if not self.env['team.contract.room.measurement.line'].browse(int(room_measurement_id)).exists():
                    _logger.info("------Custom Room Not Found-------------")
                    status = {'message': 'Custom Room Not Found', 'result': 'Success'}
                    return status
            if appointment_id:
                if custom_room:
                    room_measurements = self.env['team.contract.room.measurement.line'].search([('id', '=', int(room_measurement_id))])
                else:
                    room_measurements = self.env['team.contract.room.measurement.line'].search([('appointment_id', '=', int(appointment_id)),('room_id', '=', int(room_id))])
                if room_measurements:
                    for data in room_measurements:
                        if data.room_id.is_custom:
                            custom_room = 'True'
                        else:
                            custom_room = 'False'
                        material_image_url = ''
                        attachments = []
                        for attachment in data.attachment_ids:
                            if not attachment.access_token:
                                attachment.generate_access_token()
                            url = URL + '/web/image/' + str(attachment.id) + '?access_token=' + str(
                                attachment.access_token)
                            attachments.append({
                                'id': attachment.id,
                                'name': attachment.name,
                                'url': url,
                            })
                        shape_image_url = []
                        if data.shape_image_id:
                            if not data.shape_image_id.access_token:
                                data.shape_image_id.generate_access_token()
                            url = URL + '/web/image/' + str(
                                data.shape_image_id.id) + '?access_token=' + str(
                                data.shape_image_id.access_token)
                            shape_image_url.append({
                                'id': data.shape_image_id.id,
                                'name': data.shape_image_id.name,
                                'url': url,
                            })
                        material = 0
                        if data.material_id.is_material == True:
                            material = data.material_id.id
                            if data.material_id.image_1920:
                                material_image_url = data.material_id.profile_image('product.product')
                        stair_count = 0
                        if data.room_id and data.room_id.product_category_id and data.room_id.product_category_id.name.upper() == 'VINYL STAIRS':
                            contract_questions = self.env['team.contract.question.line'].search([
                                ('room_id', '=', data.get('room_id', 0)),
                                ('appointment_id', '=', data.get('appointment_id', 0)),
                                ('question_id.code', '=', 'StairCount')
                            ], limit=1)
                            if contract_questions:
                                for answer_obj in contract_questions.answers:
                                    stair_count = answer_obj.answer
                        vals = {
                            'contract_measurement_id': data.id,
                            'name': data.name or '',
                            'material_image_url':material_image_url,
                            'material_id':material,
                            'room_id': data.room_id.id or 0,
                            'striked': 'True' if data.exclude_from_calculation is True else 'False',
                            'room_name':data.room_id.name or '',
                            'drawing_attachment':shape_image_url,
                            'attachments':attachments,
                            'company_id': data.company_id.id or 0,
                            'appointment_id':data.appointment_id.id or 0,
                            'room_area':data.room_area or 0,
                            'adjusted_area':data.adjusted_area or 0,
                            'custom_room':custom_room,
                            'stair_count': stair_count,

                        }
                        list.append(vals)

                status = {
                    'result': 'Success',
                    'values': list,
                    'message': '',
                }

            return status

    @api.model
    def update_room_measurement(self, data):
        status = {}

        contract_measurement_id = int(data.get('contract_measurement_id', 0))
        image_id = data.get('image_id', False)
        if contract_measurement_id is False:
            _logger.info("------Empty Contract Measurement ID-------------")
            status = {'message': 'Empty Contract Measurement ID', 'result': 'False'}
            return status
        contract_measurement = self.env['team.contract.room.measurement.line'].search([('id', '=', int(contract_measurement_id))], limit=1)
        vals = {}
        if contract_measurement:
            if data.get('name', ''):
                vals.update({'name': data.get('name', '')})
            if data.get('comments', ''):
                vals.update({'comments': data.get('comments', '')})
            if data.get('adjusted_area', ''):
                vals.update({'adjusted_area': float(data.get('adjusted_area', 0))})
            if data.get('room_area', ''):
                vals.update({'room_area': float(data.get('room_area', 0))})
                vals.update({'adjusted_area': float(data.get('room_area', 0))})
            if data.get('image_id', ''):
                vals.update({'shape_image_id':image_id})
            if contract_measurement.room_id.is_custom:
                vals.update({'custom_room_measured' : True})
            contract_measurement.write(vals)
            if data.get('transitions', []):
                if contract_measurement.transition_line_id:
                    contract_measurement.transition_line_id.unlink()
                for transition_data in data.get('transitions', []):
                    self.env['team.contract.transition.line'].create({
                        'name': transition_data.get('transition_type', ''),
                        'transition_width': float(transition_data.get('transition_width', 0)),
                        'room_measurement_id': contract_measurement.id,
                        'room_id': contract_measurement.room_id.id,
                        'appointment_id': contract_measurement.appointment_id.id,
                    })
                    _logger.info('Transition Created: %s'%(transition_data))
            attachments = []
            shape_image_url = []
            questionaire_list = []
            contract_questions = self.env['team.contract.question.line'].search([
                ('room_id', '=', data.get('room_id', 0)),
                ('appointment_id', '=', data.get('appointment_id', 0)),
            ])
            if contract_questions:
                for questions in contract_questions:
                    list_answers = []
                    for answer in questions.answers:
                        answer_vals = {
                            'id': answer.id,
                            'contract_question_line_id': answer.question_id.id,
                            'answer': answer.answer
                        }
                        list_answers.append(answer_vals)
                    question_line_vals = {
                        'contract_question_line_id': questions.id,
                        'name': questions.name or '',
                        'question': questions.question_id.name or '',
                        'room_id': questions.room_id.id or 0,
                        'custom_room_measurement_id': questions.room_measurement_id.id or 0,
                        'room_name': questions.room_measurement_id.custom_room_name if questions.room_id.is_custom else questions.room_id.name or '',
                        'company_id': questions.company_id.id or 0,
                        'appointment_id': questions.appointment_id.id or 0,
                        'question_id': questions.question_id.id or 0,
                        'code': questions.question_id.code or '',
                        'description': questions.question_id.description or '',
                        'question_type': questions.question_id.question_type or '',
                        'validation_required': questions.question_id.validation_required and str(
                            questions.question_id.validation_required) or 'False',
                        'validation_email_required': questions.question_id.validation_email and str(
                            questions.question_id.validation_email) or 'False',
                        'validation_error_msg': questions.question_id.validation_error_msg or '',
                        'mandatory_answer': questions.question_id.constr_mandatory and str(
                            questions.question_id.constr_mandatory) or 'False',
                        'Error_message': questions.question_id.constr_error_msg or '',
                        'Refelct_in_cost': questions.question_id.reflect_cost and str(
                            questions.question_id.reflect_cost) or 0,
                        'calculation_type': questions.question_id.calculation_type or '',
                        'amount': questions.question_id.amount or 0,
                        'default_answer': questions.question_id.default_answer or '',
                        'answers': list_answers,
                    }
                    questionaire_list.append(question_line_vals)
            if contract_measurement.shape_image_id:
                if not contract_measurement.shape_image_id.access_token:
                    contract_measurement.shape_image_id.generate_access_token()
                url = URL + '/web/image/' + str(contract_measurement.shape_image_id.id) + '?access_token=' + str(
                    contract_measurement.shape_image_id.access_token)
                shape_image_url.append({
                    'id': contract_measurement.shape_image_id.id,
                    'name': contract_measurement.shape_image_id.name,
                    'url': url,
                })
            for attachment in contract_measurement.attachment_ids:
                if not attachment.access_token:
                    attachment.generate_access_token()
                url = URL + '/web/image/' + str(attachment.id) + '?access_token=' + str(
                    attachment.access_token)
                attachments.append({
                    'id': attachment.id,
                    'name': attachment.name,
                    'url': url,
                })
            stair_count = 0
            if contract_measurement.room_id and contract_measurement.room_id.product_category_id and contract_measurement.room_id.product_category_id.name.upper() == 'VINYL STAIRS':
                contract_questions = self.env['team.contract.question.line'].search([
                    ('room_id', '=', data.get('room_id', 0)),
                    ('appointment_id', '=', data.get('appointment_id', 0)),
                    ('question_id.code', '=', 'StairCount')
                ], limit=1)
                if contract_questions:
                    for answer_obj in contract_questions.answers:
                        stair_count = answer_obj.answer
            transitions = []
            for transition in contract_measurement.transition_line_id:
                transitions.append({
                    'transition_id': transition.id,
                    'transition_name': transition.name,
                    'transition_width': transition.transition_width or 0,
                })
            status = {
                'result': 'Success',
                'message': ' Contract Measurement Update Success',
                'contract_measurement_id':contract_measurement.id,
                'values': [{
                    'comments':contract_measurement.comments or '',
                    'attachments': attachments,
                    'attachment_comments':contract_measurement.image_comments or '',
                    'drawing_attachment': shape_image_url,
                    'questionaire':questionaire_list,
                    'contract_measurement_id': contract_measurement.id,
                    'stair_count': stair_count,
                    'transitions': transitions,
                }]
            }
        else:
            status = {'result': 'False','message': 'Contract Measurement  Not Exist',}
        return status

    @api.model
    def remove_contract_room_measurement_line(self, data):
        measurement_line_ids = data.get('contract_measurement_ids', [])
        if not measurement_line_ids:
            _logger.info("------Contract Room Measurement Line IDs Empty------------")
            status = {
                'message': 'Measurement Line IDS Empty',
                'result': 'Failed',
            }
        for contract_measurement_id in measurement_line_ids:
            contracts_measurements = self.sudo().search([('id', '=', contract_measurement_id)])
            if contracts_measurements:
                appointment_id=contracts_measurements.appointment_id.id
                room_id=contracts_measurements.room_id.id
                if contracts_measurements.room_id.is_custom:
                    room_measurement_id = contracts_measurements.id
                    transitions = self.env['team.contract.transition.line'].search(
                        [('appointment_id', '=', appointment_id),
                         ('room_measurement_id', '=', room_measurement_id)])
                else:
                    transitions = self.env['team.contract.transition.line'].search(
                        [('appointment_id', '=', appointment_id),
                         ('room_id', '=', room_id)])
                if transitions:
                    transitions.sudo().unlink()
                if contracts_measurements.room_id.is_custom:
                    room_measurement_id = contracts_measurements.id
                    contract_questions = self.env['team.contract.question.line'].search(
                    [('appointment_id', '=',appointment_id), ('room_measurement_id', '=',room_measurement_id)])
                else:
                    contract_questions = self.env['team.contract.question.line'].search([('appointment_id', '=', appointment_id), ('room_id', '=', room_id)])
                for answers in contract_questions.answers:
                    answers.sudo().unlink()
                if contract_questions:
                    contract_questions.sudo().unlink()
                if contracts_measurements.shape_image_id:
                    contracts_measurements.shape_image_id.sudo().unlink()
                for attachment in contracts_measurements.attachment_ids:
                    attachment.sudo().unlink()
                contracts_measurements.sudo().unlink()
                _logger.info("------Contract Room Measurement Line Deleted------------")
                status = {
                    'message': 'Contract Room Measurement Line Removed',
                    'result': 'Success',
                }
            else:
                _logger.info("------Contract Room Measurement Line Not Found------------")
                status = {
                    'message': 'Contract Room Measurement Line Not Found',
                    'result': 'Failed',
                }
        return status

    @api.model
    def edit_contract_room_measurement_line(self,data):
        status = {}
        measurement_line_id = data.get('contract_measurement_id', False)
        if not measurement_line_id:
            _logger.info("------Contract Room Measurement Line ID Empty------------")
            status = {
                'message': 'Measurement Line ID Empty',
                'result': 'Failed',
            }
        contracts_measurement = self.sudo().search([('id', '=', int(measurement_line_id))])
        vals = {}
        if contracts_measurement:
            if data.get('operation', '') == 'delete':
                if  contracts_measurement.room_id and contracts_measurement.appointment_id:
                    if contracts_measurement.room_id.is_custom:
                        room_measurement_id = contracts_measurement.id
                        transitions = self.env['team.contract.transition.line'].search(
                            [('room_measurement_id', '=',room_measurement_id ),
                             ('appointment_id', '=', contracts_measurement.appointment_id.id)])
                    else:
                        transitions = self.env['team.contract.transition.line'].search(
                            [('room_id', '=', contracts_measurement.room_id.id),
                             ('appointment_id', '=', contracts_measurement.appointment_id.id)])

                    for transition in transitions:
                        for attachment in transition.attachment_ids:
                            attachment.sudo().unlink()
                        transition.sudo().unlink()
                    if contracts_measurement.room_id.is_custom:
                        room_measurement_id = contracts_measurement.id
                        questionaires = self.env['team.contract.question.line'] .search([('room_measurement_id','=',room_measurement_id),('appointment_id','=',contracts_measurement.appointment_id.id)])
                    else:
                        questionaires = self.env['team.contract.question.line'] .search([('room_id','=',contracts_measurement.room_id.id),('appointment_id','=',contracts_measurement.appointment_id.id)])
                    for questionaire in questionaires:
                        for answer in questionaire.answers:
                            answer.sudo().unlink()
                        questionaire.sudo().unlink()
                if contracts_measurement.shape_image_id:
                    contracts_measurement.shape_image_id.sudo().unlink()
                for attachment in contracts_measurement.attachment_ids:
                    attachment.sudo().unlink()
                contracts_measurement.sudo().unlink()

                status = { 'result': 'True','message': ' Contract Measurement Room  Deletion Success'}
                return status
            if data.get('operation', '') == 'strike':
                if contracts_measurement.exclude_from_calculation:
                    vals.update({'exclude_from_calculation': False})
                    contracts_measurement.write(vals)
                    status = { 'result': 'True','message': 'Remove Strike on Contract Measurement Room Success',
                              'contract_measurement_id': contracts_measurement.id,'strike':'False'}
                else:
                    vals.update({'exclude_from_calculation': True})
                    contracts_measurement.write(vals)
                    status = { 'result': 'True','message': 'Strike on Contract Measurement Room Success',
                              'contract_measurement_id': contracts_measurement.id,'strike':'True'}
            else:
                status = { 'result': 'False','message': 'Invalid Parameter'}
                return status
        else:
            status = {'result': 'False','message': 'Contract Measurement  Not Exist'}
        return status

    def profile_image(self, name, model_name, image, res_id):
        url = ''
        Attachment = self.env['ir.attachment'].sudo().search([('res_model', '=', model_name), ('res_id', '=', res_id)],
                                                             limit=1)
        if Attachment:
            Attachment.sudo().write({'datas': image})
            if not Attachment.access_token:
                Attachment.generate_access_token()
            url = URL + '/web/image/' + str(Attachment.id) + '?access_token=' + str(Attachment.access_token)
        else:
            Attachment = self.env['ir.attachment'].sudo().create({
                'res_id': res_id,
                'res_model': model_name,
                'datas': image,
                'name': name

            })
            Attachment.generate_access_token()
            url = URL + '/web/image/' + str(Attachment.id) + '?access_token=' + str(Attachment.access_token)
        return url

    def get_molding_type(self):
        result = []
        molding_types = self.env['team.floor.molding'].search([])
        for molding in molding_types:
            result.append({
                'molding_id': molding.id,
                'name': molding.name,
            })
        return result

    @api.model
    def list_contract_room_measurement_line(self, vals):
        list = []
        appointment_id = vals.get('appointment_id', 0)
        if appointment_id:
            room_measurements_line_records = self.env['team.contract.room.measurement.line'].search(
                [('appointment_id', '=', int(appointment_id))])
            room_measurements_line=room_measurements_line_records.sorted(key=lambda r: r.room_id.sequence)
            if not room_measurements_line:
                return {'message': 'Contract Room Measurements Not Found', 'result': 'Success', 'values': []}
            total_area = 0
            total_stair_count = 0
            room_image_url = ''
            room_image_id = ''
            default_image_url = ''
            for measurement_line in room_measurements_line:
                if measurement_line.company_id.default_image:
                    default_image_url = self.profile_image("default_image", 'res.company', measurement_line.company_id.default_image, measurement_line.company_id.id) or ""
                material_image_url = ''
                shape_image_url = []
                if measurement_line.shape_image_id:
                    if not measurement_line.shape_image_id.access_token:
                        measurement_line.shape_image_id.generate_access_token()
                    url = URL + '/web/image/' + str(measurement_line.shape_image_id.id) + '?access_token=' + str(
                        measurement_line.shape_image_id.access_token)
                    shape_image_url.append({
                        'id': measurement_line.shape_image_id.id,
                        'name': measurement_line.shape_image_id.name,
                        'url': url,
                    })
                if measurement_line.attachment_ids:
                    if not measurement_line.attachment_ids[0].access_token:
                        measurement_line.attachment_ids[0].generate_access_token()
                    room_image_url = URL + '/web/image/' + str(measurement_line.attachment_ids[0].id) + '?access_token=' + str(
                        measurement_line.attachment_ids[0].access_token)
                    room_image_id = measurement_line.attachment_ids[0].id

                product_list = self.env['product.product'].search([('active', '=', True), ('is_material', '=', True)])
                materials_list = []
                if product_list:
                    for product in product_list:
                        if product.url and product.thumb_nail:
                            floor_color_url = product.url + product.thumb_nail
                        else:
                            floor_color_url = default_image_url

                        vals = {
                            'material_id': product.id or 0,
                            'name': product.name,
                            'color':  product.floor_color if product.floor_color else "Select Color",
                            'material_image_url': floor_color_url,
                        }
                        materials_list.append(vals)
                done = set()
                result = []
                for material in materials_list:
                    if material['color'] not in done:
                        done.add(material['color'])
                        result.append(material)
                sorted_material_list = sorted(result, key=lambda k: k['color'])
                if measurement_line.material_id and measurement_line.material_id.is_material == True:
                    if measurement_line.material_id.url and measurement_line.material_id.thumb_nail:
                        material_image_url = measurement_line.material_id.url + measurement_line.material_id.thumb_nail
                    else:
                        material_image_url = default_image_url
                if measurement_line.room_id.is_custom:
                    custom_room ='True'
                else:
                    custom_room ='False'
                molding_type_list = self.get_molding_type()
                stair_count = 0
                if measurement_line.room_id and measurement_line.room_id.product_category_id and measurement_line.room_id.product_category_id.name.upper() == 'VINYL STAIRS':
                    contract_questions = self.env['team.contract.question.line'].search([
                        ('room_id', '=', measurement_line.room_id.id),
                        ('appointment_id', '=', appointment_id),
                        ('question_id.code', '=', 'StairCount')
                    ], limit=1)
                    if contract_questions:
                        for answer_obj in contract_questions.answers:
                            stair_count = int(answer_obj.answer)
                vals = {
                    'contract_measurement_id': measurement_line.id,
                    'name': measurement_line.name or '',
                    'material_id': measurement_line.material_id.id or 0,
                    'material_image_url': material_image_url or default_image_url,
                    'color':  measurement_line.material_id.floor_color if measurement_line.material_id.floor_color else "Select Color",
                    'material_name':measurement_line.material_id.name or '',
                    'room_image_url':room_image_url if room_image_url else '',
                    'room_image_id':room_image_id if room_image_id else '',
                    # 'floor_colors':floor_color_list,
                    'material_colors':sorted_material_list,
                    'molding_type': molding_type_list,
                    'moulding': measurement_line.molding_type_id and measurement_line.molding_type_id.name or "",
                    'moulding_id': measurement_line.molding_type_id and measurement_line.molding_type_id.id or 0,
                    'striked': 'True' if measurement_line.exclude_from_calculation is True else 'False',
                    'room_id': measurement_line.room_id.id or 0,
                    'room_name': measurement_line.custom_room_name if measurement_line.room_id.is_custom else measurement_line.room_id.name or '',
                    'appointment_id': measurement_line.appointment_id.id or 0,
                    'room_area': measurement_line.room_area or 0,
                    'adjusted_area':measurement_line.adjusted_area or 0,
                    'drawing_attachment': shape_image_url or '',
                    'custom_room':custom_room,
                    'stair_count': stair_count,
                }
                list.append(vals)
                # list.append({'material_colors':materials_list})

                if not measurement_line.exclude_from_calculation:
                    total_area = total_area + measurement_line.adjusted_area
                    total_stair_count += stair_count
            area = {
                'total_area': total_area,
                'total_stair_count': total_stair_count,
            }
            list.append(area)
        status = {'result': 'Success', 'values': list,'message': 'Success'}
        return status


    @api.model
    def summary_contract_room_measurement_line(self, data):
        list = []
        measurement_line_id = data.get('contract_room_id', False)
        if not measurement_line_id:
            _logger.info("------Contract Room Measurement Line ID Empty------------")
            status = {
                'message': 'Measurement Line ID Empty',
                'result': 'Failed',
            }
        if measurement_line_id:
            room_measurements_line = self.env['team.contract.room.measurement.line'].search(
                [('id', '=', int(measurement_line_id))],limit=1)
            if not room_measurements_line:
                return {'message': 'Contract Room Measurements Not Found', 'result': 'False'}
            appointment_id = room_measurements_line.appointment_id.id or 0
            room_id = room_measurements_line.room_id.id or 0
            transition_list=[]
            if room_measurements_line.room_id.is_custom:
                custom_room = True
            else:
                custom_room = False
            if custom_room:
                domain = [('room_measurement_id', '=', int(measurement_line_id)),
                          ('appointment_id', '=', int(appointment_id)), ('room_id', '=', int(room_id))]
            else:
                domain = [('appointment_id', '=', int(appointment_id)), ('room_id', '=', int(room_id))]
            if appointment_id and room_id:
                transitions = self.env['team.contract.transition.line'].search(domain)
                if transitions:
                    for transition in transitions:
                        attachments = []
                        for attachment in transition.attachment_ids:
                            if not attachment.access_token:
                                attachment.generate_access_token()
                            url = URL + '/web/image/' + str(attachment.id) + '?access_token=' + str(
                                attachment.access_token)
                            attachments.append({
                                'id': attachment.id,
                                'name': attachment.name,
                                'url': url,
                            })
                        vals = {
                            'id': transition.id,
                            'name': transition.name or '',
                            'transition_width': transition.transition_width or 0,
                            'room_id': transition.room_id.id or 0,
                            'room_measurement_id': transition.room_measurement_id.id or 0,
                            'room_name':transition.room_measurement_id.custom_room_name or '' if transition.room_id.is_custom else transition.room_id.name or '',
                            'company_id': transition.company_id.id or 0,
                            'attachments': attachments,

                        }
                        transition_list.append(vals)
            questionaire_list = []
            if appointment_id and room_id:
                contract_questions = self.env['team.contract.question.line'].search(domain)
                if contract_questions:
                    for questions in contract_questions:
                        list_answers = []
                        for answer in questions.answers:
                            if answer.answer:
                                answer_vals = {
                                    'id': answer.id,
                                    'contract_question_line_id': answer.question_id.id,
                                    'answer': answer.answer
                                }
                                list_answers.append(answer_vals)
                        if list_answers:
                            question_line_vals = {
                                'contract_question_line_id': questions.id,
                                'name': questions.name or '',
                                'question': questions.question_id.name or '',
                                'room_id': questions.room_id.id or 0,
                                'custom_room_measurement_id':questions.room_measurement_id.id or 0,
                                'room_name':questions.room_measurement_id.custom_room_name if  questions.room_id.is_custom else questions.room_id.name or '',
                                'company_id': questions.company_id.id or 0,
                                'appointment_id': questions.appointment_id.id or 0,
                                'question_id': questions.question_id.id or 0,
                                'code': questions.question_id.code or '',
                                'description': questions.question_id.description or '',
                                'question_type': questions.question_id.question_type or '',
                                'validation_required': questions.question_id.validation_required and str(questions.question_id.validation_required) or 'False',
                                'validation_email_required': questions.question_id.validation_email and str(questions.question_id.validation_email) or 'False',
                                'validation_error_msg': questions.question_id.validation_error_msg or '',
                                'mandatory_answer': questions.question_id.constr_mandatory and str(questions.question_id.constr_mandatory) or 'False',
                                'Error_message': questions.question_id.constr_error_msg or '',
                                'Refelct_in_cost': questions.question_id.reflect_cost and str(questions.question_id.reflect_cost) or 0,
                                'calculation_type': questions.question_id.calculation_type or '',
                                'amount': questions.question_id.amount or 0,
                                'default_answer': questions.question_id.default_answer or '',
                                'answers': list_answers,
                            }
                            questionaire_list.append(question_line_vals)

            for measurement_line in room_measurements_line:
                material_image_url=''
                if measurement_line.material_id and measurement_line.material_id.is_material == True:
                    if measurement_line.material_id.image_1920:
                        material_image_url=measurement_line.material_id.profile_image('product.product')
                shape_image_url = []
                if measurement_line.shape_image_id:
                    if not measurement_line.shape_image_id.access_token :
                        measurement_line.shape_image_id.generate_access_token()
                    url = URL + '/web/image/' + str(measurement_line.shape_image_id.id) + '?access_token=' + str(
                        measurement_line.shape_image_id.access_token)
                    shape_image_url.append({
                        'id': measurement_line.shape_image_id.id,
                        'name': measurement_line.shape_image_id.name,
                        'url': url,
                    })
                attachments = []
                for attachment in measurement_line.attachment_ids:
                    if not attachment.access_token:
                        attachment.generate_access_token()
                    url = URL + '/web/image/' + str(attachment.id) + '?access_token=' + str(
                        attachment.access_token)
                    attachments.append({
                        'id': attachment.id,
                        'name': attachment.name,
                        'url': url,
                    })
                stair_count = 0
                if measurement_line.room_id and measurement_line.room_id.product_category_id and measurement_line.room_id.product_category_id.name.upper() == 'VINYL STAIRS':
                    contract_questions = self.env['team.contract.question.line'].search([
                        ('room_id', '=', measurement_line.room_id.id),
                        ('appointment_id', '=', appointment_id),
                        ('question_id.code', '=', 'StairCount')
                    ], limit=1)
                    if contract_questions:
                        for answer_obj in contract_questions.answers:
                            stair_count = answer_obj.answer
                measurement_line_vals = {
                    'contract_measurement_id': measurement_line.id,
                    'name': measurement_line.name or '',
                    'material_id':measurement_line.material_id.id or 0,
                    'material_image_url':material_image_url,
                    'material_comments':measurement_line.material_comments or '',
                    'room_id': measurement_line.room_id.id or 0,
                    'room_name': measurement_line.custom_room_name if measurement_line.room_id.is_custom else measurement_line.room_id.name or '',
                    'appointment_id': measurement_line.appointment_id.id or 0,
                    'room_area': measurement_line.room_area or 0,
                    'adjusted_area':measurement_line.adjusted_area or 0,
                    'comments':measurement_line.comments or '',
                    'attachments': attachments,
                    'attachment_comments':measurement_line.image_comments or '',
                    'drawing_attachment': shape_image_url,
                    'striked':'True' if measurement_line.exclude_from_calculation is True else 'False',
                    'transition':transition_list,
                    'questionaire':questionaire_list,
                    'custom_room':'True' if  measurement_line.room_id.is_custom else 'False',
                    'stair_count': stair_count,
                }
                list.append(measurement_line_vals)
            status = {'result':'Success','values': list,'message': 'Success'}
        return status

    @api.model
    def update_summary_contract_room_measurement(self, data):
        status = {}
        measurement_line_id = data.get('contract_measurement_id', False)
        if not measurement_line_id:
            _logger.info("------Contract Room Measurement Line ID Empty------------")
            status = {
                'message': 'Measurement Line ID Empty',
                'result': 'Failed',
            }
        contracts_measurement = self.sudo().search([('id', '=', int(measurement_line_id))])
        if contracts_measurement:
            if data.get('comments', ''):
                contracts_measurement.write({'image_comments':data.get('comments', '')})
            if data.get('image_ids', []):
                attachment_ids = data.get('image_ids', [])
                for room_image_id in attachment_ids:
                    if not self.env['ir.attachment'].browse(int(room_image_id)).exists():
                        _logger.info("------Image Attachment Not Exist-------------")
                        status = {'message': 'Image Attachment Not Exist', 'result': 'Success'}
                        return status
                for attachment_id in attachment_ids:
                    contracts_measurement.write({'attachment_ids':  [(4, attachment_id)]})
            values = {
                'contract_measurement_id': contracts_measurement.id,
                'room_id': contracts_measurement.room_id and contracts_measurement.room_id.id or False,
                'appointment_id': contracts_measurement.appointment_id and contracts_measurement.appointment_id.id  or False,
            }
            result = self.update_room_measurement(values)
            status = {
                'message': 'Update Images,Comment on Room Successful',
                'contract_room_measurement_id':contracts_measurement.id,
                'result': 'True',
                'values': result.get('values', [])
            }
            return status
        else:
            status = {'message': 'Contract Measurement  Not Exist', 'result': 'False'}
        return status


class SaleOrder(models.Model):
    _inherit = 'sale.order'
    
    def check_document_upload_completed(self):
        is_data_upload_completed = True
        for record in self:
            if record.appointment_id and not record.appointment_id.status_updated_to_i360:
                is_data_upload_completed = False
            if not record.quote_id:
                is_data_upload_completed = False
            if record.appointment_result == 'Sold' and not record.contract_document_uploaded:
                is_data_upload_completed = False
            if not record.other_files_uploaded:
                is_data_upload_completed = False
            for room_measurement in record.room_measurement_line.filtered(lambda x: not x.exclude_from_calculation):
                if not room_measurement.improveit_id:
                    is_data_upload_completed = False
            if record.required_file_upload:
                is_data_upload_completed = False
        return is_data_upload_completed

    authorize_transaction_id = fields.Char('Transaction ID', copy=False)
    required_file_upload = fields.Boolean('Required Document Upload to i360', default=False)
    is_data_upload_completed = fields.Boolean('Data Upload to i360 Completed', default=False)

    @api.model
    def verify_parameters(self, data):
        if not self.env['sale.order'].browse(int(data.get('order_id', 0))).exists():
            return False
        # if not data.get('total_amount', 0):
        #     return False
        # if not data.get('downpayment_percentage', 0):
        #     return False
        # if not data.get('down_payment_amount', 0):
        #     return False
        # if not data.get('amount_balance', 0):
        #     return False
        # if not data.get('balance_payment_option', ''):
        #     return False
        # if not data.get('balance_payment_method', ''):
        #     return False
        return True

    @api.model
    def list_applicant_signature(self, data):
        appointment_id = (data.get('appointment_id', 0))
        if not appointment_id:
            _logger.info("------Empty Appointment id-------------")
            status = {'message': 'Empty Appointment id', 'result': 'Success'}
            return status
        if not self.env['team.customer.appointment'].browse(int(appointment_id)).exists():
            _logger.info("------ Appointment Not Exist-------------")
            status = {'message': 'Appointment Not Exist', 'result': 'Success'}
            return status
        appointment = self.env['team.customer.appointment'].browse(int(appointment_id))
        applicant_signature_image = []
        if appointment.applicant_signature_id:
            if not appointment.applicant_signature_id.access_token:
                appointment.applicant_signature_id.generate_access_token()
            url = URL + '/web/image/' + str(
                appointment.applicant_signature_id.id) + '?access_token=' + str(
                appointment.applicant_signature_id.access_token)
            applicant_signature_image.append({
                'id': appointment.applicant_signature_id.id,
                'name': appointment.applicant_signature_id.name,
                'url': url,
            })
        co_applicant_signature_image = []
        if appointment.co_applicant_signature_id:
            if not appointment.co_applicant_signature_id.access_token:
                appointment.co_applicant_signature_id.generate_access_token()
            url = URL + '/web/image/' + str(
                appointment.co_applicant_signature_id.id) + '?access_token=' + str(
                appointment.co_applicant_signature_id.access_token)
            co_applicant_signature_image.append({
                'id': appointment.co_applicant_signature_id.id,
                'name': appointment.co_applicant_signature_id.name,
                'url': url,
            })

        list = []
        vals = {"appointment_id": appointment.id or '',
                "applicant_signature":applicant_signature_image,
                "co_applicant_signature":co_applicant_signature_image,
                }
        list.append(vals)
        status = {'result': 'Success', 'values': list, 'message': 'Listing  Applicant Signature  Success'}
        return status

    @api.model
    def generate_credit_application(self, data):
        appointment_id = (data.get('appointment_id', 0))
        if not appointment_id:
            _logger.info("------Empty Appointment id-------------")
            status = {'message': 'Empty Appointment id', 'result': 'Success'}
            return status
        if not self.env['team.customer.appointment'].browse(int(appointment_id)).exists():
            _logger.info("------ Appointment Not Exist-------------")
            status = {'message': 'Appointment Not Exist', 'result': 'Success'}
            return status
        sale_order = self.env['sale.order'].search([('appointment_id', '=', int(appointment_id))], limit=1)
        if not sale_order:
            return {'message': 'Sale Order Not Created For this appointment', 'result': 'Success'}
        model_id = self.env['ir.model'].search([('model', '=', 'sale.order')], limit=1)
        sign_requests = self.env['otl_document_sign.request'].sudo().search(
            [('model_id', '=', model_id.id), ('res_id', '=', sale_order.id)], order='create_date desc')
        if sign_requests:
            for sign_request in sign_requests:
                sign_logs = self.env['otl_document_sign.log'].search([('sign_request_id','=',sign_request.id)])
                if sign_logs:
                    for sign_log in sign_logs:
                        sign_log.sudo().with_context(delete_log=True).unlink()
                sign_request.sudo().unlink()
        sale_order.generate_link()
        contract_document_url = sale_order.link_to_share
        team_credit_application = self.env['team.credit.application'].search(
            [('appointment_id', '=', int(appointment_id))], limit=1)
        share_url =''
        if  team_credit_application:
            share_url = team_credit_application.generate_link(sale_order)
        sale_order.recision_date = self.env.user.company_id.recision_date
        # configurations = self.env['team.improveit.configuration'].search([('api_type', '=', 'boomi')])
        # if configurations:
        #     end_point_url = configurations.token_url
        #     client_token = configurations.client_token
        #     if end_point_url and client_token:
        #         url = end_point_url + 'GetRecisionDate' + client_token
        #         req = requests.get(url)
        #         req.raise_for_status()
        #         content = req.json()
        #         if content.get('RecisionDate',False):
        #             recesion_date = datetime.strptime(content.get('RecisionDate',False), '%m/%d/%Y').strftime('%Y-%m-%d')
        #             sale_order.recision_date = recesion_date
        status = {'message': 'Credit Application Document , Contract Document Generated', 'result': 'Success','document':contract_document_url,'credit_document':share_url}
        _logger.info('generate_credit_application Status: %s', status)
        return status


    @api.model
    def list_credit_application(self,data):
        appointment_id = (data.get('appointment_id', 0))
        if not appointment_id:
            _logger.info("------Empty Appointment id-------------")
            status = {'message': 'Empty Appointment id', 'result': 'Success'}
            return status
        if not self.env['team.customer.appointment'].browse(int(appointment_id)).exists():
            _logger.info("------ Appointment Not Exist-------------")
            status = {'message': 'Appointment Not Exist', 'result': 'Success'}
            return status
        appointment =  self.env['team.customer.appointment'].browse(int(appointment_id))
        applicant_signature_image =[]
        if appointment.applicant_signature_id:
            if not appointment.applicant_signature_id.access_token:
                appointment.applicant_signature_id.generate_access_token()
            url = URL + '/web/image/' + str(
                appointment.applicant_signature_id.id) + '?access_token=' + str(
                appointment.applicant_signature_id.access_token)
            applicant_signature_image.append({
                'id': appointment.applicant_signature_id.id,
                'name': appointment.applicant_signature_id.name,
                'url': url,
            })
        co_applicant_signature_image = []
        if appointment.co_applicant_signature_id:
            if not appointment.co_applicant_signature_id.access_token:
                appointment.co_applicant_signature_id.generate_access_token()
            url = URL + '/web/image/' + str(
                appointment.co_applicant_signature_id.id) + '?access_token=' + str(
                appointment.co_applicant_signature_id.access_token)
            co_applicant_signature_image.append({
                'id': appointment.co_applicant_signature_id.id,
                'name': appointment.co_applicant_signature_id.name,
                'url': url,
            })
        credit_application = self.env['team.credit.application'].search([('appointment_id','=',int(appointment_id))],limit=1)
        if not credit_application:
            _logger.info("------Credit Application Not Exist-------------")
            status = {'message': 'Credit Application Not Exist for this Appointment', 'result': 'Success'}
            return status
        list=[]
        vals ={ "appointment_id": credit_application.appointment_id.id or '',
                "total_price":credit_application.total_price or '',
                "downpayment":credit_application.downpayment or '',
                "amount_financed":credit_application.amount_financed or '',
                "type_of_loan":credit_application.type_of_loan or '',
                "type_of_property":credit_application.type_of_property    or '',
                "work_to_be_done":credit_application.work_to_be_done    or '',
                "owners":credit_application.owners    or '',
                "owners_if_different":credit_application.owners_if_different or '',
                "address_of_property":credit_application.address_of_property    or '',
                "street":credit_application.street    or '',
                "street2":credit_application.street2    or '',
                "city":credit_application.city    or '',
                "state":credit_application.state    or '',
                "zip":credit_application.zip    or '',
                "same_property_address":credit_application.same_property_address or '',
                "applicant_first_name":credit_application.applicant_first_name    or '',
                "applicant_middle_name":credit_application.applicant_middle_name    or '',
                "applicant_last_name":credit_application.applicant_last_name    or '',
                "drivers_license":credit_application.drivers_license    or '',
                "drivers_license_exp_date":credit_application.drivers_license_exp_date    or '',
                "date_of_birth":credit_application.date_of_birth    or '',
                "social_security_number":credit_application.social_security_number  or '',
                "address_of_applicant_street":credit_application.address_of_applicant_street    or '',
                "address_of_applicant_street2":credit_application.address_of_applicant_street    or '',
                "address_of_applicant_city":credit_application.address_of_applicant_city    or '',
                "address_of_applicant_state":credit_application.address_of_applicant_state    or '',
                "address_of_applicant_zip":credit_application.address_of_applicant_zip    or '',
                "previous_address_of_applicant":credit_application.previous_address_of_applicant    or '',
                "previous_address_of_applicant_street":credit_application.previous_address_of_applicant_street    or '',
                "previous_address_of_applicant_street2":credit_application.previous_address_of_applicant_street2    or '',
                "previous_address_of_applicant_city":credit_application.previous_address_of_applicant_city    or '',
                "previous_address_of_applicant_state":credit_application.previous_address_of_applicant_state    or '',
                "previous_address_of_applicant_zip":credit_application.previous_address_of_applicant_zip    or '',
                "cell_phone":credit_application.cell_phone    or '',
                "home_phone":credit_application.home_phone    or '',
                "how_long":credit_application.how_long    or '',
                "previous_address_how_long":credit_application.previous_address_how_long    or '',
                "present_employer":credit_application.present_employer    or '',
                "years_on_job":credit_application.years_on_job    or '',
                "occupation":credit_application.occupation    or '',
                "present_employers_address":credit_application.present_employers_address    or '',
                "present_employers_address_street":credit_application.present_employers_address_street    or '',
                "present_employers_address_street2":credit_application.present_employers_address_street2    or '',
                "present_employers_address_city":credit_application.present_employers_address_city    or '',
                "present_employers_address_state":credit_application.present_employers_address_state    or '',
                "present_employers_address_zip":credit_application.present_employers_address_zip    or '',
                "earnings_from_employment":credit_application.earnings_from_employment    or '',
                "supervisor_or_department":credit_application.supervisor_or_department   or '',
                "employers_phone_number":credit_application.employers_phone_number    or '',
                "previous_employers_address":credit_application.previous_employers_address,
                "previous_employers_address_street":credit_application.previous_employers_address_street    or '',
                "previous_employers_address_street2":credit_application.previous_employers_address_street2    or '',
                "previous_employers_address_city":credit_application.previous_employers_address_city    or '',
                "previous_employers_address_state":credit_application.previous_employers_address_state    or '',
                "previous_employers_address_zip":credit_application.previous_employers_address_zip    or '',
                "earnings_per_month":credit_application.earnings_per_month    or '',
                "years_on_job_previous_employer":credit_application.years_on_job_previous_employer or '',
                "occupation_previous_employer":credit_application.occupation_previous_employer    or '',
                "previous_employers_phone_number":credit_application.previous_employers_phone_number    or '',
                "co_applicant_first_name":credit_application.co_applicant_first_name    or '',
                "co_applicant_middle_name":credit_application.co_applicant_middle_name    or '',
                "co_applicant_last_name":credit_application.co_applicant_last_name    or '',
                "co_applicant_drivers_license":credit_application.co_applicant_drivers_license    or '',
                "co_applicant_drivers_license_exp_date":credit_application.co_applicant_drivers_license_exp_date    or '',
                "co_applicant_date_of_birth":credit_application.co_applicant_date_of_birth    or '',
                "co_applicant_social_security_number":credit_application.co_applicant_social_security_number    or '',
                "co_applicant_address_of_applicant":credit_application.co_applicant_address_of_applicant    or '',
                "co_applicant_street":credit_application.co_applicant_street    or '',
                "co_applicant_street2":credit_application.co_applicant_street2    or '',
                "co_applicant_city":credit_application.co_applicant_city    or '',
                "co_applicant_state":credit_application.co_applicant_state    or '',
                "co_applicant_zip":credit_application.co_applicant_zip    or '',
                "co_applicant_phone":credit_application.co_applicant_phone    or '',
                "co_applicant_secondary_phone":credit_application.co_applicant_secondary_phone    or '',
                "co_applicant_previous_address_of_applicant":credit_application.co_applicant_previous_address_of_applicant    or '',
                "co_applicant_previous_street":credit_application.co_applicant_previous_street    or '',
                "co_applicant_previous_street2":credit_application.co_applicant_previous_street2    or '',
                "co_applicant_previous_city":credit_application.co_applicant_previous_city    or '',
                "co_applicant_previous_state":credit_application.co_applicant_previous_state    or '',
                "co_applicant_previous_zip":credit_application.co_applicant_previous_zip    or '',
                "co_applicant_how_long":credit_application.co_applicant_how_long    or '',
                "co_applicant_present_employer":credit_application.co_applicant_present_employer    or '',
                "co_applicant_years_on_job":credit_application.co_applicant_years_on_job    or '',
                "co_applicant_occupation":credit_application.co_applicant_occupation,
                "co_applicant_present_employers_address":credit_application.co_applicant_present_employers_address    or '',
                "co_applicant_present_employers_street":credit_application.co_applicant_present_employers_street    or '',
                "co_applicant_present_employers_street2":credit_application.co_applicant_present_employers_street2    or '',
                "co_applicant_present_employers_city":credit_application.co_applicant_present_employers_city or '',
                "co_applicant_present_employers_state":credit_application.co_applicant_present_employers_state    or '',
                "co_applicant_present_employers_zip":credit_application.co_applicant_present_employers_zip    or '',
                "co_applicant_earnings_from_employment":credit_application.co_applicant_earnings_from_employment    or '',
                "co_applicant_supervisor_or_department":credit_application.co_applicant_supervisor_or_department    or '',
                "co_applicant_employers_phone_number":credit_application.co_applicant_employers_phone_number    or '',
                "co_applicant_previous_employers_address":credit_application.co_applicant_previous_employers_address    or '',
                "co_applicant_previous_employers_street":credit_application.co_applicant_previous_employers_street    or '',
                "co_applicant_previous_employers_street2":credit_application.co_applicant_previous_employers_street2    or '',
                "co_applicant_previous_employers_city":credit_application.co_applicant_previous_employers_city   or '',
                "co_applicant_previous_employers_state":credit_application.co_applicant_previous_employers_state    or '',
                "co_applicant_previoust_employers_zip":credit_application.co_applicant_previoust_employers_zip    or '',
                "co_applicant_earnings_per_month":credit_application.co_applicant_earnings_per_month    or '',
                "co_applicant_years_on_job_previous_employer":credit_application.co_applicant_years_on_job_previous_employer    or '',
                "co_applicant_occupation_previous_employer":credit_application.co_applicant_occupation_previous_employer    or '',
                "co_applicant_previous_employers_phone_number":credit_application.co_applicant_previous_employers_phone_number    or '',
                "source_of_other_income":credit_application.source_of_other_income,
                "amount_monthly":credit_application.amount_monthly   or '',
                "nearest_relative":credit_application.nearest_relative    or '',
                "relationship":credit_application.relationship    or '',
                "address_relationship":credit_application.address_relationship    or '',
                "address_relationship_street":credit_application.address_relationship_street    or '',
                "address_relationship_street2":credit_application.address_relationship_street2    or '',
                "address_relationship_city":credit_application.address_relationship_street2    or '',
                "address_relationship_state":credit_application.address_relationship_state    or '',
                "address_relationship_zip":credit_application.address_relationship_zip    or '',
                "phone_number_relationship":credit_application.phone_number_relationship    or '',
                "property_details":credit_application.property_details    or '',
                "lender_name":credit_application.lender_name    or '',
                "lender_address":credit_application.lender_address    or '',
                "lender_address_street":credit_application.lender_address_street    or '',
                "lender_address_street2":credit_application.lender_address_street2    or '',
                "lender_address_city":credit_application.lender_address_city    or '',
                "lender_address_state":credit_application.lender_address_state    or '',
                "lender_address_zip":credit_application.lender_address_zip    or '',
                "lender_phone":credit_application.lender_phone    or '',
                "original_purchase_price":credit_application.original_purchase_price    or '',
                "original_mortage_amount":credit_application.original_mortage_amount    or '',
                "monthly_mortage_payment":credit_application.monthly_mortage_payment    or '',
                "date_aquired":credit_application.date_aquired    or '',
                "present_balance":credit_application.present_balance    or '',
                "present_value_of_home":credit_application.present_value_of_home    or '',
                "second_mortage":credit_application.second_mortage    or '',
                "lender_name_or_phone":credit_application.lender_name_or_phone    or '',
                "applicant_second_mortage_phone": credit_application.applicant_second_mortage_phone or '',
                "original_amount":credit_application.original_amount    or '',
                "present_balance_second_mortage":credit_application.present_balance_second_mortage   or '',
                "monthly_payment":credit_application.monthly_payment    or '',
                "other_obligations":credit_application.other_obligations    or '',
                "total_monthly_payments":credit_application.total_monthly_payments    or '',
                "checking_account_no":credit_application.checking_account_no    or '',
                "checking_routing_no":credit_application.checking_routing_no    or '',
                "name_of_bank":credit_application.name_of_bank    or '',
                "bank_phone_number":credit_application.bank_phone_number    or '',
                "insurance_company": credit_application.insurance_company    or '',
                "agent":credit_application.agent    or '',
                "insurance_phone_no":credit_application.insurance_phone_no    or '',
                "coverage":credit_application.coverage    or '',
                "ethnicity":credit_application.ethnicity    or '',
                "race":credit_application.race    or '',
                "sex":credit_application.sex    or '',
                "marital_status":credit_application.marital_status    or '',
                "co_applicant_ethnicity":credit_application.co_applicant_ethnicity    or '',
                "co_applicant_race":credit_application.co_applicant_race    or '',
                "co_applicant_sex":credit_application.co_applicant_sex    or '',
                "co_applicant_marital_status":credit_application.co_applicant_marital_status    or '',
                "type_of_credit_requested":credit_application.co_applicant_marital_status    or '',
                "joint_credit_initials":credit_application.joint_credit_initials or '',
                "applicant_signature_date":credit_application.applicant_signature_date    or '',
                "co_applicant_signature_date":credit_application.co_applicant_signature_date    or '',
                "applicant_signature":applicant_signature_image,
                "co_applicant_signature":co_applicant_signature_image,
                "applicant_other_race":credit_application.applicant_other_race,
                "co_applicant_other_race":credit_application.co_applicant_other_race,
                "hunter_message_status":credit_application.hunter_message_status,
                }

        list.append(vals)
        status = {'result': 'Success', 'values': list, 'message': 'Listing Credit Application values Success'}
        return status

    @api.model
    def create_credit_application(self, data):
        _logger.info('---create_credit_application data ---------------')
        _logger.info(data)
        appointment_id = int(data.get('appointment_id', 0))
        if not appointment_id:
            _logger.info("------Empty Appointment id-------------")
            status = {'message': 'Empty Appointment id', 'result': 'Failed'}
            return status
        if not self.env['team.customer.appointment'].browse(appointment_id).exists():
            _logger.info("------ Appointment Not Exist-------------")
            status = {'message': 'Appointment Not Exist', 'result': 'Failed'}
            return status
        team_credit_application = self.env['team.credit.application'].search([('appointment_id', '=', appointment_id)], limit=1)
        if team_credit_application:
            team_credit_application.sudo().unlink()
        vals={}
        co_applicant_vals = {}
        applicant_vals = {}
        partner_vals = {}
        appointment = self.env['team.customer.appointment'].browse(int(appointment_id))
        partner = appointment.partner_id or False
        sale_order = self.env['sale.order'].search([('appointment_id', '=', appointment_id)], limit=1)
        co_applicant_skip = int(data.get('co_applicant_skip', '0'))
        if sale_order:
            vals.update({'order_id': sale_order.id})
            if int(data.get('co_applicant_skip', '0')) == 1:
                sale_order.write({'coapplicant_skip': True})
            else:
                sale_order.write({'coapplicant_skip': False})
        total_price = data.get('total_price', 0)
        if total_price:
            vals.update({'total_price':total_price})
        downpayment = data.get('downpayment', 0)
        if downpayment:
            vals.update({'downpayment':downpayment})
        amount_financed = data.get('amount_financed', 0)
        if amount_financed:
            vals.update({'amount_financed':amount_financed})
        type_of_loan = data.get('type_of_loan', 0)
        if type_of_loan:
            if type_of_loan not in ['Low Payment','No Interest','One Year no Payments']:
                _logger.info("------ Wrong value for type_of_loan-------------")
                status = {'message': 'Wrong value for type of loan', 'result': 'Failed'}
                return status
            vals.update({'type_of_loan':type_of_loan})
            if type_of_loan == 'Low Payment':
                vals.update({'low_payment': True})
            if type_of_loan == 'No Interest':
                vals.update({'no_interest': True})
            if type_of_loan == 'One Year no Payments':
                vals.update({'no_payment': True})
        type_of_property = data.get('type_of_property', "")
        if type_of_property:
            if type_of_property not in ['Single Family','Mobile Home','Condo']:
                _logger.info("------ Wrong value for type_of_property-------------")
                status = {'message': 'Wrong value for type of property', 'result': 'Failed'}
                return status
            vals.update({'type_of_property':type_of_property})
            if type_of_property == 'Single Family':
                vals.update({'single_family': True})
            if type_of_property == 'Mobile Home':
                vals.update({'mobile_family': True})
            if type_of_property == 'Condo':
                vals.update({'condoo': True})

        address_of_property = data.get('address_of_property', "")
        if address_of_property:
            vals.update({'address_of_property':address_of_property})

        applicant_first_name = data.get('applicant_first_name', "")
        if applicant_first_name:
            vals.update({'applicant_first_name':applicant_first_name})
            if appointment.applicant_first_name != applicant_first_name:
                applicant_vals.update({'applicant_first_name':applicant_first_name})
        applicant_middle_name = data.get('applicant_middle_name', "")
        if applicant_middle_name:
            vals.update({'applicant_middle_name':applicant_middle_name})
            if appointment.applicant_middle_name != applicant_middle_name:
                applicant_vals.update({'applicant_middle_name': applicant_middle_name})
        applicant_last_name = data.get('applicant_last_name', "")
        if applicant_last_name:
            vals.update({'applicant_last_name':applicant_last_name})
            if appointment.applicant_last_name != applicant_last_name:
                applicant_vals.update({'applicant_last_name': applicant_last_name})
        applicant_name = '%s, %s'%(applicant_last_name, applicant_first_name)
        if partner.name != applicant_name:
            partner_vals.update({'name': applicant_name})
        if appointment.customer_name != applicant_name:
            applicant_vals.update({'customer_name': applicant_name})
        drivers_license = data.get('drivers_license', "")
        if drivers_license:
            vals.update({'drivers_license':drivers_license})
        drivers_license_exp_date = data.get('drivers_license_exp_date', "")
        if drivers_license_exp_date:
            vals.update({'drivers_license_exp_date':datetime.strptime(drivers_license_exp_date, '%m/%d/%Y').strftime('%Y-%m-%d')})
        drivers_license_issue_date = data.get('drivers_license_issue_date', "")
        if drivers_license_issue_date:
            vals.update({'drivers_license_issue_date':datetime.strptime(drivers_license_issue_date, '%m/%d/%Y').strftime('%Y-%m-%d')})
        date_of_birth = data.get('date_of_birth', "")
        if date_of_birth:
            vals.update({'date_of_birth':datetime.strptime(date_of_birth, '%m/%d/%Y').strftime('%Y-%m-%d')})
        social_security_number = data.get('social_security_number', "")
        if social_security_number:
            vals.update({'social_security_number':social_security_number})
        address_of_applicant = data.get('address_of_applicant', "")
        if address_of_applicant:
            vals.update({'address_of_applicant':address_of_applicant})
            applicant_vals.update({'street':address_of_applicant})
            partner_vals.update({'street':address_of_applicant})
        address_of_applicant_street = data.get('address_of_applicant_street', "")
        if address_of_applicant_street:
            vals.update({'address_of_applicant_street': address_of_applicant_street})
        address_of_applicant_street2 = data.get('address_of_applicant_street2', "")
        if address_of_applicant_street2:
            vals.update({'address_of_applicant_street2': address_of_applicant_street2})
        address_of_applicant_city = data.get('address_of_applicant_city', "")
        if address_of_applicant_city:
            vals.update({'address_of_applicant_city': address_of_applicant_city})
            partner_vals.update({'city': address_of_applicant_city})
            applicant_vals.update({'city': address_of_applicant_city})
        address_of_applicant_state = data.get('address_of_applicant_state', "")
        if address_of_applicant_state:
            vals.update({'address_of_applicant_state':address_of_applicant_state})
        address_of_applicant_zip = data.get('address_of_applicant_zip', "")
        if address_of_applicant_zip:
            vals.update({'address_of_applicant_zip': address_of_applicant_zip})
            partner_vals.update({'zip': address_of_applicant_zip})
            applicant_vals.update({'zip': address_of_applicant_zip})
        previous_address_of_applicant = data.get('previous_address_of_applicant', "")
        if previous_address_of_applicant:
            vals.update({'previous_address_of_applicant':previous_address_of_applicant})
        previous_address_of_applicant_street = data.get('previous_address_of_applicant_street', "")
        if previous_address_of_applicant_street:
            vals.update({'previous_address_of_applicant_street':previous_address_of_applicant_street})
        previous_address_of_applicant_street2 = data.get('previous_address_of_applicant_street2', "")
        if previous_address_of_applicant_street2:
            vals.update({'previous_address_of_applicant_street2':previous_address_of_applicant_street2})
        previous_address_of_applicant_city = data.get('previous_address_of_applicant_city', "")
        if previous_address_of_applicant_city:
            vals.update({'previous_address_of_applicant_city':previous_address_of_applicant_city})
        previous_address_of_applicant_state = data.get('previous_address_of_applicant_state', "")
        if previous_address_of_applicant_state:
            vals.update({'previous_address_of_applicant_state':previous_address_of_applicant_state})
        previous_address_of_applicant_zip = data.get('previous_address_of_applicant_zip', "")
        if previous_address_of_applicant_zip:
            vals.update({'previous_address_of_applicant_zip':previous_address_of_applicant_zip})
        co_applicant_email = data.get('co_applicant_email', "")
        if co_applicant_email:
            vals.update({'co_applicant_email': co_applicant_email})
            co_applicant_vals.update({'co_applicant_email': co_applicant_email})
        co_applicant_phone = data.get('co_applicant_phone', "")
        if co_applicant_phone:
            vals.update({'co_applicant_phone': co_applicant_phone})
            co_applicant_vals.update({'co_applicant_phone': co_applicant_phone})
        co_applicant_secondary_phone = data.get('co_applicant_secondary_phone', "")
        if co_applicant_secondary_phone:
            vals.update({'co_applicant_secondary_phone': co_applicant_secondary_phone})
            co_applicant_vals.update({'co_applicant_secondary_phone': co_applicant_secondary_phone})
        applicant_email = data.get('applicant_email', "")
        if applicant_email:
            vals.update({'applicant_email': applicant_email})
            applicant_vals.update({'email': applicant_email})
            partner_vals.update({'email': applicant_email})
        cell_phone = data.get('cell_phone', "")
        if cell_phone:
            vals.update({'cell_phone':cell_phone})
        home_phone = data.get('home_phone', "")
        if home_phone:
            vals.update({'home_phone':home_phone})
            applicant_vals.update({'phone':home_phone})
            partner_vals.update({'phone':home_phone})
        how_long = data.get('how_long', "")
        if how_long:
            vals.update({'how_long':how_long})
        previous_address_how_long = data.get('previous_address_how_long', "")
        if previous_address_how_long:
            vals.update({'previous_address_how_long':previous_address_how_long})
        present_employer = data.get('present_employer', "")
        if present_employer:
            vals.update({'present_employer':present_employer})
        years_on_job = data.get('years_on_job', "")
        if years_on_job:
            vals.update({'years_on_job':years_on_job})
        occupation = data.get('occupation', "")
        if occupation:
            vals.update({'occupation':occupation})
        present_employers_address = data.get('present_employers_address', "")
        if present_employers_address:
            vals.update({'present_employers_address':present_employers_address})
        present_employers_address_street = data.get('present_employers_address_street', "")
        if present_employers_address_street:
            vals.update({'present_employers_address_street':present_employers_address_street})
        present_employers_address_street2 = data.get('present_employers_address_street2', "")
        if present_employers_address_street2:
            vals.update({'present_employers_address_street2':present_employers_address_street2})
        present_employers_address_city = data.get('present_employers_address_city', "")
        if present_employers_address_city:
            vals.update({'present_employers_address_city':present_employers_address_city})
        present_employers_address_state = data.get('present_employers_address_state', "")
        if present_employers_address_state:
            vals.update({'present_employers_address_state':present_employers_address_state})
        present_employers_address_zip = data.get('present_employers_address_zip', "")
        if present_employers_address_zip:
            vals.update({'present_employers_address_zip':present_employers_address_zip})
        earnings_from_employment = data.get('earnings_from_employment', "")
        if earnings_from_employment:
            vals.update({'earnings_from_employment':earnings_from_employment})
            vals.update({'is_earning_from_employment':True})
        supervisor_or_department = data.get('supervisor_or_department', "")
        if supervisor_or_department:
            vals.update({'supervisor_or_department':supervisor_or_department})
        employers_phone_number = data.get('employers_phone_number', "")
        if employers_phone_number:
            vals.update({'employers_phone_number':employers_phone_number})
        previous_employers_address = data.get('previous_employers_address', "")
        if previous_employers_address:
            vals.update({'previous_employers_address':previous_employers_address})
        previous_employers_address_street = data.get('previous_employers_address_street', "")
        if previous_employers_address_street:
            vals.update({'previous_employers_address_street':previous_employers_address_street})
        previous_employers_address_street2 = data.get('previous_employers_address_street2', "")
        if previous_employers_address_street2:
            vals.update({'previous_employers_address_street2':previous_employers_address_street2})
        previous_employers_address_city = data.get('previous_employers_address_city', "")
        if previous_employers_address_city:
            vals.update({'previous_employers_address_city':previous_employers_address_city})
        previous_employers_address_state = data.get('previous_employers_address_state', "")
        if previous_employers_address_state:
            vals.update({'previous_employers_address_state':previous_employers_address_state})
        previous_employers_address_zip = data.get('previous_employers_address_zip', "")
        if previous_employers_address_zip:
            vals.update({'previous_employers_address_zip':previous_employers_address_zip})
        earnings_per_month = data.get('earnings_per_month', "")
        if earnings_per_month:
            vals.update({'earnings_per_month':earnings_per_month})
        years_on_job_previous_employer = data.get('years_on_job_previous_employer', "")
        if years_on_job_previous_employer:
            vals.update({'years_on_job_previous_employer':years_on_job_previous_employer})
        occupation_previous_employer = data.get('occupation_previous_employer', "")
        if occupation_previous_employer:
            vals.update({'occupation_previous_employer':occupation_previous_employer})
        previous_employers_phone_number = data.get('previous_employers_phone_number', "")
        if previous_employers_phone_number:
            vals.update({'previous_employers_phone_number':previous_employers_phone_number})
        co_applicant_first_name = data.get('co_applicant_first_name', "")
        if co_applicant_first_name:
            vals.update({'co_applicant_first_name':co_applicant_first_name})
            co_applicant_vals.update({'co_applicant_first_name':co_applicant_first_name})
        co_applicant_middle_name = data.get('co_applicant_middle_name', "")
        if co_applicant_middle_name:
            vals.update({'co_applicant_middle_name':co_applicant_middle_name})
        co_applicant_last_name = data.get('co_applicant_last_name', "")
        if co_applicant_last_name:
            vals.update({'co_applicant_last_name':co_applicant_last_name})
            co_applicant_vals.update({'co_applicant_last_name':co_applicant_last_name})
        if co_applicant_last_name or co_applicant_first_name:
            co_applicant_vals.update(({'co_applicant': '%s, %s'%(co_applicant_last_name, co_applicant_first_name)}))
        co_applicant_drivers_license = data.get('co_applicant_drivers_license', "")
        if co_applicant_drivers_license:
            vals.update({'co_applicant_drivers_license':co_applicant_drivers_license})
        co_applicant_drivers_license_exp_date = data.get('co_applicant_drivers_license_exp_date', "")
        if co_applicant_drivers_license_exp_date:
            vals.update({'co_applicant_drivers_license_exp_date':datetime.strptime(co_applicant_drivers_license_exp_date, '%m/%d/%Y').strftime('%Y-%m-%d')})
        co_applicant_drivers_license_issue_date = data.get('co_applicant_drivers_license_issue_date', "")
        if co_applicant_drivers_license_issue_date:
            vals.update({'co_applicant_drivers_license_issue_date':datetime.strptime(co_applicant_drivers_license_issue_date, '%m/%d/%Y').strftime('%Y-%m-%d')})
        co_applicant_date_of_birth = data.get('co_applicant_date_of_birth', "")
        if co_applicant_date_of_birth:
            vals.update({'co_applicant_date_of_birth':datetime.strptime(co_applicant_date_of_birth, '%m/%d/%Y').strftime('%Y-%m-%d')})
        co_applicant_social_security_number = data.get('co_applicant_social_security_number', "")
        if co_applicant_social_security_number:
            vals.update({'co_applicant_social_security_number':co_applicant_social_security_number})
        co_applicant_address_of_applicant = data.get('co_applicant_address_of_applicant', "")
        if co_applicant_address_of_applicant:
            vals.update({'co_applicant_address_of_applicant':co_applicant_address_of_applicant})
            co_applicant_vals.update({'co_applicant_address':co_applicant_address_of_applicant})
        co_applicant_street = data.get('co_applicant_street', "")
        if co_applicant_street:
            vals.update({'co_applicant_street':co_applicant_street})
        co_applicant_street2 = data.get('co_applicant_street2', "")
        if co_applicant_street2:
            vals.update({'co_applicant_street2':co_applicant_street2})
        co_applicant_city = data.get('co_applicant_city', "")
        if co_applicant_city:
            vals.update({'co_applicant_city':co_applicant_city})
            co_applicant_vals.update({'co_applicant_city':co_applicant_city})
        co_applicant_state = data.get('co_applicant_state', "")
        if co_applicant_state:
            vals.update({'co_applicant_state':co_applicant_state})
            co_applicant_state_id = self.env['res.country.state'].search([
                ('country_id', '=', self.env.ref('base.us').id),
                '|', ('name', '=', co_applicant_state), ('code', '=', co_applicant_state)
            ], limit=1)
            if co_applicant_state_id:
                co_applicant_vals.update({'co_applicant_state':co_applicant_state_id.id})

        co_applicant_zip = data.get('co_applicant_zip', "")
        if co_applicant_zip:
            vals.update({'co_applicant_zip':co_applicant_zip})
            co_applicant_vals.update({'co_applicant_zip':co_applicant_zip})
        co_applicant_previous_address_of_applicant = data.get('co_applicant_previous_address_of_applicant', "")
        if co_applicant_previous_address_of_applicant:
            vals.update({'co_applicant_previous_address_of_applicant':co_applicant_previous_address_of_applicant})
        co_applicant_previous_street = data.get('co_applicant_previous_street', "")
        if co_applicant_previous_street:
            vals.update({'co_applicant_previous_street':co_applicant_previous_street})
        co_applicant_previous_street2 = data.get('co_applicant_previous_street2', "")
        if co_applicant_previous_street2:
            vals.update({'co_applicant_previous_street2':co_applicant_previous_street2})
        co_applicant_previous_city = data.get('co_applicant_previous_city', "")
        if co_applicant_previous_city:
            vals.update({'co_applicant_previous_city':co_applicant_previous_city})
        co_applicant_previous_state = data.get('co_applicant_previous_state', "")
        if co_applicant_previous_state:
            vals.update({'co_applicant_previous_state':co_applicant_previous_state})
        co_applicant_previous_zip = data.get('co_applicant_previous_zip', "")
        if co_applicant_previous_zip:
            vals.update({'co_applicant_previous_zip':co_applicant_previous_zip})
        co_applicant_how_long = data.get('co_applicant_how_long', "")
        if co_applicant_how_long:
            vals.update({'co_applicant_how_long':co_applicant_how_long})
        co_applicant_present_employer = data.get('co_applicant_present_employer', "")
        if co_applicant_present_employer:
            vals.update({'co_applicant_present_employer':co_applicant_present_employer})
        co_applicant_years_on_job = data.get('co_applicant_years_on_job', "")
        if co_applicant_years_on_job:
            vals.update({'co_applicant_years_on_job':co_applicant_years_on_job})
        co_applicant_occupation = data.get('co_applicant_occupation', "")
        if co_applicant_occupation:
            vals.update({'co_applicant_occupation':co_applicant_occupation})
        co_applicant_present_employers_address = data.get('co_applicant_present_employers_address', "")
        if co_applicant_present_employers_address:
            vals.update({'co_applicant_present_employers_address':co_applicant_present_employers_address})
        co_applicant_present_employers_street = data.get('co_applicant_present_employers_street', "")
        if co_applicant_present_employers_street:
            vals.update({'co_applicant_present_employers_street':co_applicant_present_employers_street})
        co_applicant_present_employers_street2 =   data.get('co_applicant_present_employers_street2', "")
        if co_applicant_present_employers_street2:
            vals.update({'co_applicant_present_employers_street2':co_applicant_present_employers_street2})
        co_applicant_present_employers_city = data.get('co_applicant_present_employers_city', "")
        if co_applicant_present_employers_city:
            vals.update({'co_applicant_present_employers_city':co_applicant_present_employers_city})
        co_applicant_present_employers_state = data.get('co_applicant_present_employers_state', "")
        if co_applicant_present_employers_state:
            vals.update({'co_applicant_present_employers_state':co_applicant_present_employers_state})
        co_applicant_present_employers_zip = data.get('co_applicant_present_employers_zip', "")
        if co_applicant_present_employers_zip:
            vals.update({'co_applicant_present_employers_zip':co_applicant_present_employers_zip})
        co_applicant_earnings_from_employment = data.get('co_applicant_earnings_from_employment', "")
        if co_applicant_earnings_from_employment:
            vals.update({'co_applicant_earnings_from_employment':co_applicant_earnings_from_employment})
        co_applicant_supervisor_or_department = data.get('co_applicant_supervisor_or_department', "")
        if co_applicant_supervisor_or_department:
            vals.update({'co_applicant_supervisor_or_department':co_applicant_supervisor_or_department})
        co_applicant_employers_phone_number = data.get('co_applicant_employers_phone_number', "")
        if co_applicant_employers_phone_number:
            vals.update({'co_applicant_employers_phone_number':co_applicant_employers_phone_number})
        co_applicant_previous_employers_address = data.get('co_applicant_previous_employers_address', "")
        if co_applicant_previous_employers_address:
            vals.update({'co_applicant_previous_employers_address':co_applicant_previous_employers_address})
        co_applicant_previous_employers_street = data.get('co_applicant_previous_employers_street', "")
        if co_applicant_previous_employers_street:
            vals.update({'co_applicant_previous_employers_street':co_applicant_previous_employers_street})
        co_applicant_previous_employers_street2 = data.get('co_applicant_previous_employers_street2', "")
        if co_applicant_previous_employers_street2:
            vals.update({'co_applicant_previous_employers_street2':co_applicant_previous_employers_street2})
        co_applicant_previous_employers_city = data.get('co_applicant_previous_employers_city', "")
        if co_applicant_previous_employers_city:
            vals.update({'co_applicant_previous_employers_city':co_applicant_previous_employers_city})
        co_applicant_previous_employers_state = data.get('co_applicant_previous_employers_state', "")
        if co_applicant_previous_employers_state:
            vals.update({'co_applicant_previous_employers_state':co_applicant_previous_employers_state})
        co_applicant_previoust_employers_zip = data.get('co_applicant_previoust_employers_zip', "")
        if co_applicant_previoust_employers_zip:
            vals.update({'co_applicant_previoust_employers_zip':co_applicant_previoust_employers_zip})
        co_applicant_earnings_per_month = data.get('co_applicant_earnings_per_month', "")
        if co_applicant_earnings_per_month:
            vals.update({'co_applicant_earnings_per_month':co_applicant_earnings_per_month})
        co_applicant_years_on_job_previous_employer = data.get('co_applicant_years_on_job_previous_employer', "")
        if co_applicant_years_on_job_previous_employer:
            vals.update({'co_applicant_years_on_job_previous_employer':co_applicant_years_on_job_previous_employer})
        co_applicant_occupation_previous_employer = data.get('co_applicant_occupation_previous_employer', "")
        if co_applicant_occupation_previous_employer:
            vals.update({'co_applicant_occupation_previous_employer':co_applicant_occupation_previous_employer})
        co_applicant_previous_employers_phone_number = data.get('co_applicant_previous_employers_phone_number', "")
        if co_applicant_previous_employers_phone_number:
            vals.update({'co_applicant_previous_employers_phone_number':co_applicant_previous_employers_phone_number})
        source_of_other_income = data.get('source_of_other_income', "")
        if source_of_other_income:
            if source_of_other_income not in ['Social Security','Pension','Child Support','Rental','Other']:
                _logger.info("------ Wrong value for source_of_other_income-------------")
                status = {'message': 'Wrong value for source of other income', 'result': 'Failed'}
                return status
            vals.update({'source_of_other_income': source_of_other_income})
            if source_of_other_income == 'Social Security':
                vals.update({'social_security': True})
            if source_of_other_income == 'Pension':
                vals.update({'pension': True})
            if source_of_other_income == 'Child Support':
                vals.update({'child_support': True})
            if source_of_other_income == 'Rental':
                vals.update({'rental': True})
            if source_of_other_income == 'Other':
                vals.update({'other_source_of_income': True})
        amount_monthly = data.get('amount_monthly', "")
        if amount_monthly:
            vals.update({'amount_monthly': amount_monthly})
            vals.update({'is_amount_monthly': True})
        nearest_relative = data.get('nearest_relative', "")
        if nearest_relative:
            vals.update({'nearest_relative': nearest_relative})
        relationship = data.get('relationship', "")
        if relationship:
            vals.update({'relationship': relationship})
        address_relationship = data.get('address_relationship', "")
        if address_relationship:
            vals.update({'address_relationship': address_relationship})
        address_relationship_street = data.get('address_relationship_street', "")
        if address_relationship_street:
            vals.update({'address_relationship_street': address_relationship_street})
        address_relationship_street2 = data.get('address_relationship_street2', "")
        if address_relationship_street2:
            vals.update({'address_relationship_street2': address_relationship_street2})
        address_relationship_city = data.get('address_relationship_city', "")
        if address_relationship_city:
            vals.update({'address_relationship_city': address_relationship_city})
        address_relationship_state = data.get('address_relationship_state', "")
        if address_relationship_state:
            vals.update({'address_relationship_state':address_relationship_state})
        address_relationship_zip = data.get('address_relationship_zip', "")
        if address_relationship_zip:
            vals.update({'address_relationship_zip': address_relationship_zip})
        phone_number_relationship = data.get('phone_number_relationship', "")
        if phone_number_relationship:
            vals.update({'phone_number_relationship': phone_number_relationship})
        lender_name = data.get('lender_name', "")
        if lender_name:
            vals.update({'lender_name': lender_name})
        lender_address = data.get('lender_address', "")
        if lender_address:
            vals.update({'lender_address': lender_address})
        lender_address_street = data.get('lender_address_street', "")
        if lender_address_street:
            vals.update({'lender_address_street': lender_address_street})
        lender_address_street2 = data.get('lender_address_street2', "")
        if lender_address_street2:
            vals.update({'lender_address_street2': lender_address_street2})
        lender_address_city = data.get('lender_address_city', "")
        if lender_address_city:
            vals.update({'lender_address_city': lender_address_city})
        lender_address_state = data.get('lender_address_state', "")
        if lender_address_state:
            vals.update({'lender_address_state':lender_address_state})
        lender_address_zip = data.get('lender_address_zip', "")
        if lender_address_zip:
            vals.update({'lender_address_zip': lender_address_zip})
        lender_phone = data.get('lender_phone', "")
        if lender_phone:
            vals.update({'lender_phone': lender_phone})
        original_purchase_price = data.get('original_purchase_price', "")
        if original_purchase_price:
            vals.update({'original_purchase_price': original_purchase_price})
        original_mortage_amount = data.get('original_mortage_amount', "")
        if original_mortage_amount:
            vals.update({'original_mortage_amount': original_mortage_amount})
        monthly_mortage_payment = data.get('monthly_mortage_payment', "")
        if monthly_mortage_payment:
            vals.update({'monthly_mortage_payment': monthly_mortage_payment})
        date_aquired = data.get('date_aquired', "")
        if date_aquired:
            vals.update({'date_aquired': datetime.strptime(date_aquired, '%m/%d/%Y').strftime('%Y-%m-%d')})
        present_balance = data.get('present_balance', "")
        if present_balance:
            vals.update({'present_balance': present_balance})
        present_value_of_home = data.get('present_value_of_home', "")
        if present_value_of_home:
            vals.update({'present_value_of_home': present_value_of_home})
        lender_name_or_phone = data.get('lender_name_or_phone', "")
        if lender_name_or_phone:
            vals.update({'lender_name_or_phone': lender_name_or_phone})
        applicant_second_mortage_phone = data.get('applicant_second_mortage_phone', "")
        if applicant_second_mortage_phone:
            vals.update({'applicant_second_mortage_phone': applicant_second_mortage_phone})
        original_amount = data.get('original_amount', "")
        if original_amount:
            vals.update({'original_amount': original_amount})
        present_balance_second_mortage = data.get('present_balance_second_mortage', "")
        if present_balance_second_mortage:
            vals.update({'present_balance_second_mortage': present_balance_second_mortage})
        monthly_payment = data.get('monthly_payment', "")
        if monthly_payment:
            vals.update({'monthly_payment': monthly_payment})
        other_obligations = data.get('other_obligations', "0")
        if other_obligations:
            vals.update({'other_obligations': float(other_obligations)})
        total_monthly_payments = data.get('total_monthly_payments', "")
        if total_monthly_payments:
            vals.update({'total_monthly_payments': total_monthly_payments})
        checking_account_no = data.get('checking_account_no', "")
        if checking_account_no:
            vals.update({'checking_account_no': checking_account_no})
        checking_routing_no = data.get('checking_routing_no', "")
        if checking_routing_no:
            vals.update({'checking_routing_no': checking_routing_no})
        name_of_bank = data.get('name_of_bank', "")
        if name_of_bank:
            vals.update({'name_of_bank': name_of_bank})
        bank_phone_number = data.get('bank_phone_number', "")
        if bank_phone_number:
            vals.update({'bank_phone_number': bank_phone_number})
        insurance_company = data.get('insurance_company', "")
        if insurance_company:
            vals.update({'insurance_company': insurance_company})
        agent = data.get('agent', "")
        if agent:
            vals.update({'agent': agent})
        insurance_phone_no = data.get('insurance_phone_no', "")
        if insurance_phone_no:
            vals.update({'insurance_phone_no': insurance_phone_no})
        coverage = data.get('coverage', "")
        if coverage:
            vals.update({'coverage': coverage})
        race = data.get('race', "")
        if race:
            if race not in ['I do not wish to furnish this information', 'American Indian or Alaskan Native',
                            'White/Caucasian (non Hispanic)', 'Hispanic', 'Asian or Pacific Islander',
                            'Black (non Hispanic)', 'Other']:
                _logger.info("------ Wrong value for race-------------")
                status = {'message': 'Wrong value for race', 'result': 'Failed'}
                return status
            vals.update({'race': race})
            if race == 'I do not wish to furnish this information':
                vals.update({'race_dont_furnish': True})
            if race == 'American Indian or Alaskan Native':
                vals.update({'race_american_indian': True})
            if race == 'White/Caucasian (non Hispanic)':
                vals.update({'race_white': True})
            if race == 'Hispanic':
                vals.update({'race_hispanic': True})
            if race == 'Asian or Pacific Islander':
                vals.update({'race_asian': True})
            if race == 'Black (non Hispanic)':
                vals.update({'race_black': True})
            if race == 'Other':
                vals.update({'race_other': True})
                if not data.get('applicant_otherRace',''):
                    _logger.info("------ Wrong value for applicant_otherRace-------------")
                    status = {'message': 'No value entered for applicant Other Race', 'result': 'Failed'}
                    return status
        sex = data.get('sex', "")
        if sex:
            if sex not in ['Male','Female']:
                _logger.info("------ Wrong value for sex-------------")
                status = {'message': 'Wrong value for sex', 'result': 'Failed'}
                return status
            vals.update({'sex': sex})
            if sex == 'Male':
                vals.update({'sex_male': True})
            if sex == 'Female':
                vals.update({'sex_female': True})
        marital_status = data.get('marital_status', "")
        if marital_status:
            if marital_status not in ['Married','Unmarried','Separated']:
                _logger.info("------ Wrong value for marital_status-------------")
                status = {'message': 'Wrong value for marital status', 'result': 'Failed'}
                return status
            vals.update({'marital_status': marital_status})
            if marital_status == 'Married':
                vals.update({'marital_status_married': True})
            if marital_status == 'Unmarried':
                vals.update({'marital_status_unmarried': True})
            if marital_status == 'Separated':
                vals.update({'marital_status_separated': True})
        co_applicant_race = data.get('co_applicant_race', "")
        if co_applicant_race and co_applicant_race != 'Select':
            if co_applicant_race not in ['I do not wish to furnish this information', 'American Indian or Alaskan Native',
                            'White/Caucasian (non Hispanic)', 'Hispanic', 'Asian or Pacific Islander',
                            'Black (non Hispanic)', 'Other']:
                _logger.info("------ Wrong value for co_applicant_race-------------")
                status = {'message': 'Wrong value for co_applicant race', 'result': 'Failed'}
                return status
            vals.update({'co_applicant_race': co_applicant_race})
            if co_applicant_race == 'I do not wish to furnish this information':
                vals.update({'co_applicant_race_dont_furnish': True})
            if co_applicant_race == 'American Indian or Alaskan Native':
                vals.update({'co_applicant_race_american_indian': True})
            if co_applicant_race == 'White/Caucasian (non Hispanic)':
                vals.update({'co_applicant_race_white': True})
            if co_applicant_race == 'Hispanic':
                vals.update({'co_applicant_race_hispanic': True})
            if co_applicant_race == 'Asian or Pacific Islander':
                vals.update({'co_applicant_race_asian': True})
            if co_applicant_race == 'Black (non Hispanic)':
                vals.update({'co_applicant_race_black': True})
            if co_applicant_race == 'Other':
                vals.update({'co_applicant_race_other': True})
                if not data.get('co_applicant_otherRace',''):
                    _logger.info("------ Wrong value for co_applicant_otherRace-------------")
                    status = {'message': 'No value entered for Co Applicant Other Race', 'result': 'Failed'}
                    return status
        co_applicant_sex = data.get('co_applicant_sex', "")
        if co_applicant_sex:
            if co_applicant_sex not in ['Male','Female']:
                _logger.info("------ Wrong value for co_applicant_sex-------------")
                status = {'message': 'Wrong value for co-applicant sex', 'result': 'Failed'}
                return status
            vals.update({'co_applicant_sex': co_applicant_sex})
            if co_applicant_sex == 'Male':
                vals.update({'co_applicant_sex_male': True})
            if co_applicant_sex == 'Female':
                vals.update({'co_applicant_sex_female': True})
        co_applicant_marital_status = data.get('co_applicant_marital_status', "")
        if co_applicant_marital_status:
            if co_applicant_marital_status not in ['Married','Unmarried','Separated']:
                _logger.info("------ Wrong value for co_applicant_marital_status-------------")
                status = {'message': 'Wrong value for co_applicant marital status', 'result': 'Failed'}
                return status
            vals.update({'co_applicant_marital_status': co_applicant_marital_status})
            if co_applicant_marital_status == 'Married':
                vals.update({'co_applicant_marital_status_married': True})
            if co_applicant_marital_status == 'Unmarried':
                vals.update({'co_applicant_marital_status_unmarried': True})
            if co_applicant_marital_status == 'Separated':
                vals.update({'co_applicant_marital_status_separated': True})
        type_of_credit_requested = data.get('type_of_credit_requested', "")
        if type_of_credit_requested:
            if type_of_credit_requested not in ['Individual Credit - relying solely on my income or assets','Joint Credit - We intend to apply for joint credit','Individual Credit - relying on my income or assets as well as income or assets from other sources']:
                _logger.info("------ Wrong value for type_of_credit_requested-------------")
                status = {'message': 'Wrong value for type of credit requested', 'result': 'Failed'}
                return status
            vals.update({'type_of_credit_requested': type_of_credit_requested})
            if type_of_credit_requested == 'Individual Credit - relying solely on my income or assets':
                vals.update({'individual_credit': True})
            if type_of_credit_requested == 'Joint Credit - We intend to apply for joint credit':
                vals.update({'joint_credit': True})
            if type_of_credit_requested == 'Individual Credit - relying on my income or assets as well as income or assets from other sources':
                vals.update({'individual_credit_other': True})
        joint_credit_initials = data.get('joint_credit_initials', "")
        if joint_credit_initials:
            vals.update({'joint_credit_initials': joint_credit_initials})
        applicant_signature_date = data.get('applicant_signature_date', "")
        if applicant_signature_date:
            vals.update({'applicant_signature_date': datetime.strptime(applicant_signature_date, '%m/%d/%Y').strftime('%Y-%m-%d')})
        co_applicant_signature_date = data.get('co_applicant_signature_date', "")
        if co_applicant_signature_date:
            vals.update({'co_applicant_signature_date': datetime.strptime(co_applicant_signature_date, '%m/%d/%Y').strftime('%Y-%m-%d')})
        if appointment_id:
            vals.update({'appointment_id': appointment_id})

        if appointment.partner_id:
            vals.update({'partner_id': appointment.partner_id.id})
        hunter_message_status = False
        if data.get('hunterMessageStatus', 'No') == 'Yes':
            hunter_message_status = True
        vals.update({
            'applicant_other_race':data.get('applicant_otherRace', ''),
            'co_applicant_other_race':data.get('co_applicant_otherRace',''),
            'hunter_message_status':hunter_message_status,
            })
        additional_monthly_income = data.get('additional_monthly_income', "")
        if additional_monthly_income:
            vals.update({'additional_monthly_income': additional_monthly_income})
        applicant_mortgage_company = data.get('applicant_mortgage_company', "")
        if applicant_mortgage_company:
            vals.update({'applicant_mortgage_company': applicant_mortgage_company})
        additional_income = data.get('additional_income', '')
        if additional_income:
            if additional_income not in ['Yes', 'No']:
                return {'message': 'Wrong value for Additional Income (Yes / No)', 'result': 'Failed'}
            vals.update({'additional_income': additional_income})
        _logger.info('------------------create_credit_application vals-----------')
        _logger.info(vals)
        team_credit_application = self.env['team.credit.application'].create(vals)
        self._cr.commit()
        result= {}
        if partner and partner_vals:
            partner.write(partner_vals)
        if co_applicant_vals and appointment and not data.get('co_applicant_skip', '0') == '1':
            co_applicant_vals.update(applicant_vals)
            appointment.write(co_applicant_vals)
            result = appointment.update_appointment_to_boomi()
        else:
            if applicant_vals:
                appointment.write(applicant_vals)
                result = appointment.update_appointment_to_boomi()
        if result:
            if result.get('success', '') == 'true':
                _logger.info("------ UpdateAppointmentProspect Success-------------")
                appointment.write({'prospect_info_updated': True})
            else:
                _logger.info("------ UpdateAppointmentProspect Failed-------------")
                if result and result.get('errors', []):
                    message = ''
                    for error in result.get('errors', []):
                        if not message:
                            message = error.get('message', '')
                        else:
                            message += ', ' + error.get('message', '')
                    if message:
                        message += '\n We are having issue with communicating our server . Please tap on Retry button to try again. If issue continues, please reach out to the support'
                    status = {'message': message, 'result': 'Failed'}
                else:
                    status = {'message': 'UpdateAppointmentProspect Failed', 'result': 'Failed'}
                return status

        result = self.submit_credit_application_to_boomi(team_credit_application)
        if team_credit_application and result.get('success', '') == 'true':
            _logger.info("------ Credit Application Create,Update Success-------------")
            status = {'message': 'Credit Application Create,Update Success', 'result': 'Success'}
            return status
        else:
            _logger.info("------ Credit Application Create,Update Failed-------------")
            if result and result.get('errors', []):
                message = ''
                for error in result.get('errors', []):
                    if not message:
                        message = error.get('message', '')
                    else:
                        message += ', ' + error.get('message', '')
                if message:
                    message += '\n We are having issue with communicating our server . Please tap on Retry button to try again. If issue continues, please reach out to the support'
                status = {'message': message, 'result': 'Failed'}
            else:
                status = {'message': 'Credit Application Create,Update Failed', 'result': 'Failed'}
            return status

    @api.model
    def create_payment_transaction_cash(self, data):
        if self.verify_parameters(data):
            order_id = int(data.get('order_id', 0))
        else:
            _logger.info("------Parameter Error------------")
            status = {
                'message': 'Parameter validation Error',
                'result': 'Failed',
            }
            return status

        order = self.env['sale.order'].search([('id', '=', order_id)], limit=1)
        if not order.down_payment_amount:
            _logger.info("------Downpayment Amount Empty------------")
            status = {
                'message': 'Downpayment Amount Empty',
                'result': 'Failed',
            }
            return status
        down_payment_amount = order.down_payment_amount
        if order.invoice_ids:
            _logger.info("------Payment Already Done------------")
            status = {
                'message': 'Payment Already Done',
                'result': 'Success',
                'document': order.link_to_share,
            }
            return status

        values = {
            'payment_method':'cash',
        }
        record = order.write(values)
        # journal_id = self.env['account.journal'].search([('type', '=', 'cash')], limit=1)
        # domain = [('payment_type', '=', 'inbound')]
        # payment_method_id = self.env['account.payment.method'].search(domain, limit=1).id
        # adv_wiz = self.env['sale.advance.payment.inv'].with_context(active_ids=[order.id], open_invoices=True).create({
        #     'advance_payment_method': 'fixed', 'fixed_amount': float(down_payment_amount)
        # })
        # invoice_created = adv_wiz.with_context(open_invoices=True).create_invoices()
        # order.invoice_ids.action_post()
        # register_payment_wizard = self.env['account.payment'].with_context(active_ids=[order.invoice_ids.ids]).create({
        #     'journal_id': journal_id.id, 'payment_type': 'inbound', 'payment_method_id': payment_method_id,
        #     'amount': down_payment_amount,
        #     'partner_type': 'customer','partner_id':order.partner_id.id,'communication':order.invoice_ids.name, 'invoice_ids': [(6, 0,order.invoice_ids.ids)]
        # })
        # register_payment_wizard.post()
        if record:
            # order.action_confirm()
            order.generate_link()
            _logger.info("------Payment done successfully------------")
            status = {
                'result': 'Success',
                'document': order.link_to_share,
                'message': 'Payment done successfully',
            }
            return status
        else:
            _logger.info("------ Payment_Transaction Creation Failed ------------")
            status = {
                'result': 'Failed',
                'message': 'Payment_Transaction Creation Failed ', }

            return status

    @api.model
    def create_payment_transaction_card(self, data):
        if self.verify_parameters(data):
            order_id = int(data.get('order_id', 0))
        else:
            _logger.info("------Parameter Error------------")
            status = {
                'message': 'Parameter validation Error',
                'result': 'Failed',
            }
            return status
        if data.get('payment_method', ''):
            payment_method = data.get('payment_method', "")
        else:
            _logger.info("------payment_method------------")
            status = {
                'message': 'payment method  Empty',
                'result': 'Failed',
            }
            return status
        if data.get('card_number', ''):
            card_number = data.get('card_number', '')
            card_number = card_number.replace(' ', '')
        else:
            _logger.info("------card_number Empty------------")
            status = {
                'message': 'card_number  Empty',
                'result': 'Failed',
            }
            return status
        if data.get('card_expiry', 0):
            card_expiry = data.get('card_expiry', 0)
        else:
            _logger.info("------card_expiry Empty------------")
            status = {
                'message': 'card_expiry  Empty',
                'result': 'Failed',
            }
            return status
        if data.get('card_holder_name', ''):
            card_holder_name = data.get('card_holder_name', "")
        else:
            _logger.info("------card_holder_name Empty------------")
            status = {
                'message': 'card_holder_name  Empty',
                'result': 'Failed',
            }
            return status
        if data.get('cardpin', ''):
            cardpin = data.get('cardpin', "")
        else:
            _logger.info("------cardpin Empty------------")
            status = {
                'message': 'cardpin  Empty',
                'result': 'Failed',
            }
            return status
        order = self.env['sale.order'].search([('id', '=', order_id)], limit=1)
        if not order.down_payment_amount:
            _logger.info("------Downpayment Amount Empty------------")
            status = {
                'message': 'Downpayment Amount Empty',
                'result': 'Failed',
            }
            return status
        down_payment_amount = order.down_payment_amount
        if order.invoice_ids:
            _logger.info("------Payment Already Done------------")
            status = {
                'message': 'Payment Already Done',
                'result': 'Success',
                'document':order.link_to_share,
            }
            return status
        values = {
            'payment_method':payment_method,
        }
        record = order.write(values)
        if card_expiry:
            month, year = card_expiry.split('/')
            if len(year) == 4:
                year = year[2:]
                card_expiry = '%s/%s'%(month, year)
        payment_data = {
            'sale_order_id': order.id,
            'cc_number': card_number,
            'cc_expiry': card_expiry,
            'cc_cvc': cardpin,
            'cc_holder_name': card_holder_name,
            'amount':down_payment_amount,
        }
        payment_status=order.action_authorize_payment(payment_data)
        if not payment_status['result'] == 'Success' :
            _logger.info("------ Payment_Transaction Failed------------")
            status = {
                'result': 'Failed',
                'message': payment_status['message'],
            }
            return status
        # adv_wiz = self.env['sale.advance.payment.inv'].with_context(active_ids=[order.id], open_invoices=True).create({
        #     'advance_payment_method': 'fixed', 'fixed_amount': float(down_payment_amount)
        # })
        # adv_wiz.with_context(open_invoices=True).create_invoices()
        # order.invoice_ids.action_post()
        if record and payment_status:
            # order.action_confirm()
            order.generate_link()
            _logger.info("------ Payment_Transaction Created ------------")
            status = {
                'result': 'Success',
                'document':order.link_to_share,
                'message': 'Payment done successfully',
            }
            return status
        else:
            _logger.info("------ Payment Transaction Failed ------------")
            status = {
                'result': 'Failed',
                'message': 'Payment Transaction Failed ', }

            return status

    @api.model
    def create_payment_transaction_check(self, data):
        if self.verify_parameters(data):
            order_id = int(data.get('order_id', 0))
        else:
            _logger.info("------Parameter Error------------")
            status = {
                'message': 'Parameter validation Error',
                'result': 'Failed',
            }
            return status
        if data.get('check_number', ''):
            check_number = data.get('check_number', "")
        else:
            _logger.info("------check_number Empty------------")
            status = {
                'message': 'check_number  Empty',
                'result': 'Failed',
            }
            return status
        if data.get('check_account_number', ''):
            check_account_number = data.get('check_account_number', "")
        else:
            _logger.info("------check_account_number Empty------------")
            status = {
                'message': 'check_account_number  Empty',
                'result': 'Failed',
            }
            return status
        if data.get('check_routing_number', ''):
            check_routing_number = data.get('check_routing_number', "")
        else:
            _logger.info("------check_routing_number Empty------------")
            status = {
                'message': 'check_routing_number  Empty',
                'result': 'Failed',
            }
            return status
        order = self.env['sale.order'].search([('id', '=', order_id)], limit=1)
        if not order.down_payment_amount:
            _logger.info("------Downpayment Amount Empty------------")
            status = {
                'message': 'Downpayment Amount Empty',
                'result': 'Failed',
            }
            return status
        down_payment_amount = order.down_payment_amount
        if order.invoice_ids:
            _logger.info("------Payment Already Done------------")
            status = {
                'message': 'Payment Already Done',
                'result': 'Success',
                'document':order.link_to_share,
            }
            return status

        values = {

            'payment_method':'check',
            'check_number':check_number,
            'check_account_number':check_account_number,
            'check_routing_number':check_routing_number,
        }

        record = order.write(values)
        # journal_id = self.env['account.journal'].search([('type', '=', 'bank')], limit=1)
        # domain = [('payment_type', '=', 'inbound')]
        # payment_method_id = self.env['account.payment.method'].search(domain, limit=1).id
        # adv_wiz = self.env['sale.advance.payment.inv'].with_context(active_ids=[order.id], open_invoices=True).create({
        #     'advance_payment_method': 'fixed', 'fixed_amount': float(down_payment_amount)
        # })
        # invoice_created = adv_wiz.with_context(open_invoices=True).create_invoices()
        # order.invoice_ids.action_post()
        # register_payment_wizard = self.env['account.payment'].with_context(active_ids=[order.invoice_ids.ids]).create({
        #     'journal_id': journal_id.id, 'payment_type': 'inbound', 'payment_method_id': payment_method_id,
        #     'amount': down_payment_amount,
        #     'partner_type': 'customer', 'partner_id': order.partner_id.id, 'communication': order.invoice_ids.name,
        #     'invoice_ids': [(6, 0,order.invoice_ids.ids)]
        # })
        # register_payment_wizard.post()
        if record:
            # order.action_confirm()
            order.generate_link()
            _logger.info("------Payment done successfully------------")
            status = {
                'result': 'Success',
                'document':order.link_to_share,
                'message': 'Payment done successfully',
            }
            return status
        else:
            _logger.info("------ Payment_Transaction  Failed ------------")
            status = {
                'result': 'Failed',
                'message': 'Payment Transaction  Failed ', }

            return status

    @api.model
    def check_document_status(self,data):
        sale_order_id = int(data.get('sale_order_id', False))
        sale_order = self.env['sale.order'].search([('id','=',sale_order_id)],limit=1)
        if not sale_order:
            status = {
                'result': 'Success',
                'message': 'sale order not found', }
            return status
        else:
            if sale_order.link_to_share:
                model_id=self.env['ir.model'].search([('model','=','sale.order')],limit=1)
                sign_request = self.env['otl_document_sign.request'].sudo().search([('model_id','=',model_id.id),('res_id','=',sale_order_id)],order='create_date desc', limit=1)
                if sign_request:
                    if sign_request.state == 'signed':
                        status = {
                            'result': 'Success',
                            'signed': 'True',
                            'message': 'Document signed succesfully'
                        }
                        return status
                    else:
                        status = {
                            'result': 'Success',
                            'signed': 'False',
                            'message': 'Document not signed'}
                        return status
                else:
                    status = {
                        'result': 'Success',
                        'signed': 'False',
                        'message': 'Sign Request not Found'
                    }
                    return status
            else:
                status = {
                    'result': 'Success',
                    'signed': 'False',
                    'message': 'Document link not generated for this order'
                }
                return status

    @api.model
    def get_contract_document_status(self, data):
        _logger.info('get_contract_document_status fn: %s'%(data))
        sale_order_id = int(data.get('sale_order_id', False))
        sale_order = self.env['sale.order'].search([('id', '=', sale_order_id)], limit=1)
        _logger.info('get_contract_document_status sale_order: %s' % (sale_order))
        if not sale_order:
            status = {
                'result': 'incomplete',
                'message': 'sale order not found', }
            return status
        model_id = self.env['ir.model'].search([('model', '=', 'sale.order')], limit=1)
        sign_request = self.env['otl_document_sign.request'].sudo().search(
            [('model_id', '=', model_id.id), ('res_id', '=', sale_order.id)], order='create_date desc', limit=1)
        if sign_request:
            if sign_request.state != 'signed':
                status = {
                    'result': 'incomplete',
                    'signed': 'False',
                    'message': self.env['ir.config_parameter'].sudo().get_param('doc_status_message') or ""}
                return status
            if sign_request.state == 'signed':
                status = {
                    'result': 'Success',
                    'signed': 'True',
                    'message': self.env['ir.config_parameter'].sudo().get_param('doc_completion_message') or "",
                    'document_url': sign_request.document_url or '',
                }
                return status
        else:
            status = {
                'result': 'incomplete',
                'signed': 'False',
                'message': 'Sign Request not Found'
            }
            return status

    def parse_error_response(self, result):
        message = ''
        if result and result.get('errors', []):
            for error in result.get('errors', []):
                if not message:
                    message = error.get('message', '')
                else:
                    message += ', ' + error.get('message', '')
        if message:
            message += '\n We are having issue with communicating our server . Please tap on Retry button to try again. If issue continues, please reach out to the support'
        return {'message': message, 'result': 'Failed'}

    def confirm_order_and_create_invoice(self):
        for order in self:
            order.action_confirm()
            if order.down_payment_amount:
                adv_wiz = self.env['sale.advance.payment.inv'].with_context(active_ids=[order.id],
                                                                            open_invoices=True).create({
                    'advance_payment_method': 'fixed',
                    'fixed_amount': float(order.down_payment_amount)
                })
                invoice_created = adv_wiz.with_context(open_invoices=True).create_invoices()
                order.invoice_ids.action_post()
                if order.payment_method in ['cash', 'check']:
                    domain = []
                    if order.payment_method == 'cash':
                        domain = [('type', '=', 'cash')]
                    else:
                        domain = [('type', '=', 'bank')]

                    journal_id = self.env['account.journal'].search(domain, limit=1)
                    domain = [('payment_type', '=', 'inbound')]
                    payment_method_id = self.env['account.payment.method'].search(domain, limit=1).id
                    register_payment_wizard = self.env['account.payment'].with_context(
                        active_ids=[order.invoice_ids.ids]).create({
                        'journal_id': journal_id.id,
                        'payment_type': 'inbound',
                        'payment_method_id': payment_method_id,
                        'amount': order.down_payment_amount,
                        'partner_type': 'customer',
                        'partner_id': order.partner_id.id,
                        'communication': order.invoice_ids.name,
                        'invoice_ids': [(6, 0, order.invoice_ids.ids)]
                    })
                    register_payment_wizard.post()
        return True


    @api.model
    def capture_payment(self, data):
        sale_order_id = int(data.get('sale_order_id', False))
        sale_order = self.env['sale.order'].search([('id', '=', sale_order_id)], limit=1)
        if not sale_order:
            status = {
                'result': 'Failed',
                'message': 'sale order not found', }
            return status
        model_id = self.env['ir.model'].search([('model', '=', 'sale.order')], limit=1)
        sign_request = self.env['otl_document_sign.request'].sudo().search(
            [('model_id', '=', model_id.id), ('res_id', '=', sale_order.id)], order='create_date desc', limit=1)
        if sign_request:
            if sign_request.state != 'signed':
                status = {
                    'result': 'incomplete',
                    'signed': 'False',
                    'message': self.env['ir.config_parameter'].sudo().get_param('doc_status_message') or ""}
                return status
            if sign_request.state == 'signed':
                if not sale_order.quote_id:
                    sale_order.confirm_order_and_create_invoice()
                    response_result = sale_order.add_sale_api()
                    if response_result.get('success', '') == 'true':
                        _logger.info("------ Add Sale API is Success-------------")
                    else:
                        _logger.info("------ Add Sale API is Failed-------------")
                        return self.parse_error_response(response_result)
                    response_result = sale_order.add_sale_items_api()
                    if response_result.get('success', '') == 'true':
                        _logger.info("------ Add Sale Item API is Success-------------")
                    else:
                        _logger.info("------ Add Sale Item API is Failed-------------")
                        return self.parse_error_response(response_result)
                if sale_order.contract_doc_attachment_id:
                    sale_order.add_contract_document_file()
                sale_order.add_sale_id_file()
                response_result = sale_order.set_appointment_result_api()
                if response_result.get('Result', '') == 'Success':
                    _logger.info("------ Set Appointment Result API is Success-------------")
                else:
                    _logger.info("------ Set Appointment Result API is Failed-------------")
                    return self.parse_error_response(response_result)
                if sale_order.payment_method in ['cash', 'check'] or (sale_order.balance_payment_method and sale_order.balance_payment_method == 'finance' and not sale_order.payment_method):
                    status = {
                        'result': 'Success',
                        'message': 'Payment has been Processed.\n\n This Appointment is Completed, please click on continue button to view the appointments',
                        'document_url': sign_request.document_url or '',
                    }
                    return status
                if not sale_order.authorize_transaction_id:
                    status = {
                        'result': 'Failed',
                        'message': 'Transaction Reference not found. Please try again', }
                    return status

                if sale_order.authorize_transaction_id:
                    payment_data = {
                        'transaction_id': sale_order.authorize_transaction_id,
                        'amount': sale_order.down_payment_amount,
                    }
                    payment_status = sale_order.action_capture_payment(payment_data)

                    if payment_status['result'] == 'Success':
                        status = {
                            'result': 'Success',
                            'message': "Payment has been Processed. \n\n This Appointment is Completed, please click on continue button to view the appointments",
                            'document_url': sign_request.document_url or '',
                        }
                        return status
                    else:
                        status = {
                            'result': 'Failed',
                            'message': payment_status['message'],
                        }
                        return status
        else:
            status = {
                'result': 'Success',
                'signed': 'False',
                'message': 'Sign Request not Found'
            }
            return status

    @api.model
    def capture_payment_without_upload(self, data):
        sale_order_id = int(data.get('sale_order_id', False))
        sale_order = self.env['sale.order'].search([('id', '=', sale_order_id)], limit=1)
        if not sale_order:
            status = {
                'result': 'Failed',
                'message': 'sale order not found', }
            return status
        model_id = self.env['ir.model'].search([('model', '=', 'sale.order')], limit=1)
        sign_request = self.env['otl_document_sign.request'].sudo().search(
            [('model_id', '=', model_id.id), ('res_id', '=', sale_order.id)], order='create_date desc', limit=1)
        if sign_request:
            if sign_request.state != 'signed':
                status = {
                    'result': 'incomplete',
                    'signed': 'False',
                    'message': self.env['ir.config_parameter'].sudo().get_param('doc_status_message') or ""}
                return status
            if sign_request.state == 'signed':
                if not sale_order.quote_id:
                    sale_order.confirm_order_and_create_invoice()
                    # response_result = sale_order.add_sale_api()
                    # if response_result.get('success', '') == 'true':
                    #     _logger.info("------ Add Sale API is Success-------------")
                    # else:
                    #     _logger.info("------ Add Sale API is Failed-------------")
                    #     return self.parse_error_response(response_result)
                    # response_result = sale_order.add_sale_items_api()
                    # if response_result.get('success', '') == 'true':
                    #     _logger.info("------ Add Sale Item API is Success-------------")
                    # else:
                    #     _logger.info("------ Add Sale Item API is Failed-------------")
                    #     return self.parse_error_response(response_result)
                    # if sale_order.contract_doc_attachment_id:
                    #     sale_order.add_contract_document_file()
                    # sale_order.add_sale_id_file()
                sale_order.appointment_id.write({'appointment_result': 'Sold', 'state': 'done', 'start_sync_to_i360': True})
                response_result = sale_order.set_appointment_result_api()
                _logger.info('-------i360 SetAppointmentResult Response: %s' % (response_result))
                # if response_result.get('Result', '') == 'Success':
                #     _logger.info("------ Set Appointment Result API is Success-------------")
                # else:
                #     _logger.info("------ Set Appointment Result API is Failed-------------")
                #     return self.parse_error_response(response_result)

                if sale_order.payment_method in ['cash', 'check'] or (sale_order.balance_payment_method and sale_order.balance_payment_method == 'finance' and not sale_order.payment_method):
                    status = {
                        'result': 'Success',
                        'message': 'Payment has been Processed.\n\n This Appointment is Completed, please click on continue button to view the appointments',
                        'document_url': sign_request.document_url or '',
                    }
                    return status
                if not sale_order.authorize_transaction_id:
                    status = {
                        'result': 'Failed',
                        'message': 'Transaction Reference not found. Please try again', }
                    return status

                if sale_order.authorize_transaction_id:
                    payment_data = {
                        'transaction_id': sale_order.authorize_transaction_id,
                        'amount': sale_order.down_payment_amount,
                    }
                    payment_status = sale_order.action_capture_payment(payment_data)

                    if payment_status['result'] == 'Success':
                        status = {
                            'result': 'Success',
                            'message': "Payment has been Processed. \n\n This Appointment is Completed, please click on continue button to view the appointments",
                            'document_url': sign_request.document_url or '',
                        }
                        return status
                    else:
                        status = {
                            'result': 'Failed',
                            'message': payment_status['message'],
                        }
                        return status
        else:
            status = {
                'result': 'Success',
                'signed': 'False',
                'message': 'Sign Request not Found'
            }
            return status

    @api.model
    def action_do_file_upload(self, data):
        _logger.info("------ Start Processing: action_do_file_upload-------------")
        sale_order_id = int(data.get('sale_order_id', False))
        model_id = self.env['ir.model'].search([('model', '=', 'sale.order')], limit=1)
        sale_order = self.env['sale.order'].search([('id', '=', sale_order_id)], limit=1)
        sale_order_vals = {}
        if not sale_order:
            status = {
                'result': 'Failed',
                'message': 'sale order not found', }
            return status
        if sale_order.appointment_id and sale_order.appointment_result and not sale_order.appointment_id.status_updated_to_i360:
            response_result = sale_order.set_appointment_result_api(sale_order.appointment_result)
            _logger.info('-------i360 SetAppointmentResult Response: %s' % (response_result))
        if sale_order.appointment_result and not sale_order.is_data_upload_completed:
            if not sale_order.quote_id:
                if sale_order.appointment_result == 'Sold':
                    response_result = sale_order.add_sale_api()
                else:
                    response_result = sale_order.add_quote_sales_app(sale_order.appointment_result)
                _logger.info('-------i360 AddSale Response: %s'%(response_result))
            if sale_order.appointment_result == 'Sold':
                response_result = sale_order.add_sale_items_api()
            else:
                response_result = sale_order.add_quote_items_sales_app()
            _logger.info('-------i360 AddSaleItem Response: %s'%(response_result))
            if sale_order.appointment_result == 'Sold':
                if sale_order.appointment_id.card_transaction_log_line.filtered(lambda x: x.state == 'failed' and not x.synced):
                    response_result = sale_order.add_card_decline_note_api()
                    _logger.info('-------i360 CreateChargeDeclineNotice Response: %s' % (response_result))
                contract_doc_attachment = sale_order.contract_doc_attachment_id or False
                if not contract_doc_attachment:
                    sign_request = self.env['otl_document_sign.request'].sudo().search(
                        [('model_id', '=', model_id.id), ('res_id', '=', sale_order.id)], order='create_date desc',
                        limit=1)
                    if sign_request:
                        if sign_request.state == 'signed':
                            if not sign_request.completed_document:
                                sign_request.generate_completed_document()
                            contract_doc_attachment = sign_request.document_image()
                            sale_order.write(
                                {'contract_doc_attachment_id': contract_doc_attachment.id, 'document_signed': True})
                if contract_doc_attachment and not sale_order.contract_document_uploaded:
                    result = sale_order.add_contract_document_file()
                    if result.get('success', '') == 'true':
                        sale_order_vals.update({'contract_document_uploaded': True})
            if not sale_order.other_files_uploaded:
                if sale_order.state in ['sale', 'done'] or sale_order.appointment_result == 'Sold':
                    result = sale_order.add_sale_id_file()
                else:
                    result = sale_order.add_quote_id_file(document=False)
                if result.get('success', '') == 'true':
                    sale_order_vals.update({'other_files_uploaded': True})
            sale_order.write(sale_order_vals)
            if sale_order.check_document_upload_completed():
                sale_order.write({'is_data_upload_completed': True})
            self.env.cr.commit()
        return {
            'result': 'success',
            'message': "Documents Uploaded successfully"
        }

    @api.model
    def cron_action_do_file_upload(self, data=[]):
        _logger.info("------ Start Processing: cron_action_do_file_upload-------------")
        # 02/02/2022 - 1 hour interval changed to 10 minuts
        one_hour_ago_time = datetime.now() - relativedelta(minutes=10)
        #find pending orders created 1 hour ago to sync for avoid the duplication of record creation in i360
        orders = self.search([('is_data_upload_completed', '=', False), ('appointment_id.sync_initiated_date', '<=', one_hour_ago_time)])
        model_id = self.env['ir.model'].search([('model', '=', 'sale.order')], limit=1)
        sync_log = self.env['otl.appointment.sync.log']
        for sale_order in orders:
            appointment = sale_order.appointment_id
            if appointment and appointment.start_sync_to_i360:
                if sale_order.appointment_result:
                    if not appointment.prospect_info_updated:
                        result = appointment.update_appointment_to_boomi()
                        if result.get('success', '') == 'true':
                            appointment.write({'prospect_info_updated': True})
                            sync_log.create({
                                'appointment_id': appointment.id,
                                'response': result,
                                'name': 'UpdateAppointmentProspect',
                            })
                        else:
                            sync_log.create({
                                'appointment_id': appointment.id,
                                'response': result,
                                'state': 'failed',
                                'name': 'UpdateAppointmentProspect',
                            })
                    if not appointment.status_updated_to_i360:
                        response_result = sale_order.set_appointment_result_api(sale_order.appointment_result)
                        _logger.info('-------i360 SetAppointmentResult Response: %s' % (response_result))
                        if response_result.get('Result', '') == 'Success' or response_result.get('success', '') == 'true':
                            sync_log.create({
                                'appointment_id': appointment.id,
                                'response': response_result,
                                'name': 'SetAppointmentResult',
                            })
                        else:
                            sync_log.create({
                                'appointment_id': appointment.id,
                                'response': response_result,
                                'state': 'failed',
                                'name': 'SetAppointmentResult',
                            })
                    team_credit_application = self.env['team.credit.application'].search(
                        [('appointment_id', '=', int(appointment.id))], limit=1)
                    if team_credit_application and not team_credit_application.improveit_id:
                        result = self.env['sale.order'].submit_credit_application_to_boomi(team_credit_application)
                        if result.get('success', '') == 'true':
                            _logger.info("------ Credit Application Create,Update Success-------------")
                            sync_log.create({
                                'appointment_id': appointment.id,
                                'response': result,
                                'name': 'AddCreditApplication',
                            })
                        else:
                            _logger.info("------ Credit Application Create,Update Failed-------------")
                            sync_log.create({
                                'appointment_id': appointment.id,
                                'response': result,
                                'state': 'failed',
                                'name': 'AddCreditApplication',
                            })
                    sale_order_vals = {}
                    if not sale_order.quote_id:
                        if sale_order.appointment_result == 'Sold':
                            if sale_order.state != 'sale':
                                sale_order.confirm_order_and_create_invoice()
                            response_result = sale_order.add_sale_api()
                            if response_result.get('success', '') == 'true':
                                sync_log.create({
                                    'appointment_id': appointment.id,
                                    'response': response_result,
                                    'name': 'AddSale',
                                })
                            else:
                                sync_log.create({
                                    'appointment_id': appointment.id,
                                    'response': response_result,
                                    'state': 'failed',
                                    'name': 'AddSale',
                                })
                        else:
                            response_result = sale_order.add_quote_sales_app(sale_order.appointment_result)
                            if response_result.get('success', '') == 'true':
                                sync_log.create({
                                    'appointment_id': appointment.id,
                                    'response': response_result,
                                    'name': 'AddQuote',
                                })
                            else:
                                sync_log.create({
                                    'appointment_id': appointment.id,
                                    'response': response_result,
                                    'state': 'failed',
                                    'name': 'AddQuote',
                                })
                        _logger.info('-------i360 AddSale Response: %s' % (response_result))
                    room_measurement_lines_to_sync = sale_order.room_measurement_line.filtered(
                        lambda x: not x.exclude_from_calculation and not x.improveit_id)
                    if room_measurement_lines_to_sync:
                        if sale_order.appointment_result == 'Sold':
                            response_result = sale_order.add_sale_items_api()
                            if response_result.get('success', '') == 'true':
                                sync_log.create({
                                    'appointment_id': appointment.id,
                                    'response': response_result,
                                    'name': 'AddSaleItem',
                                })
                            else:
                                sync_log.create({
                                    'appointment_id': appointment.id,
                                    'response': response_result,
                                    'state': 'failed',
                                    'name': 'AddSaleItem',
                                })
                        else:
                            response_result = sale_order.add_quote_items_sales_app()
                            if response_result.get('success', '') == 'true':
                                sync_log.create({
                                    'appointment_id': appointment.id,
                                    'response': response_result,
                                    'name': 'AddQuoteItem',
                                })
                            else:
                                sync_log.create({
                                    'appointment_id': appointment.id,
                                    'response': response_result,
                                    'state': 'failed',
                                    'name': 'AddQuoteItem',
                                })
                        _logger.info('-------i360 AddSaleItem Response: %s' % (response_result))
                    if sale_order.appointment_result == 'Sold':
                        if appointment.card_transaction_log_line.filtered(lambda x: x.state == 'failed' and not x.synced):
                            response_result = sale_order.add_card_decline_note_api()
                            _logger.info('-------i360 CreateChargeDeclineNotice Response: %s' % (response_result))
                            if response_result.get('success', '') == 'true':
                                sync_log.create({
                                    'appointment_id': appointment.id,
                                    'response': response_result,
                                    'name': 'CreateChargeDeclineNotice',
                                })
                            else:
                                sync_log.create({
                                    'appointment_id': appointment.id,
                                    'response': response_result,
                                    'state': 'failed',
                                    'name': 'CreateChargeDeclineNotice',
                                })

                        contract_doc_attachment = sale_order.contract_doc_attachment_id or False
                        if not contract_doc_attachment:
                            sign_request = self.env['otl_document_sign.request'].sudo().search(
                                [('model_id', '=', model_id.id), ('res_id', '=', sale_order.id)], order='create_date desc',
                                limit=1)
                            if sign_request:
                                if sign_request.state == 'signed':
                                    if not sign_request.completed_document:
                                        sign_request.generate_completed_document()
                                    contract_doc_attachment = sign_request.document_image()
                                    sale_order.write(
                                        {'contract_doc_attachment_id': contract_doc_attachment.id, 'document_signed': True})
                        if contract_doc_attachment and not sale_order.contract_document_uploaded:
                            result = sale_order.add_contract_document_file()
                            if result.get('success', '') == 'true':
                                sale_order_vals.update({'contract_document_uploaded': True})
                                sync_log.create({
                                    'appointment_id': appointment.id,
                                    'response': result,
                                    'name': 'Contract Document',
                                })
                            else:
                                sync_log.create({
                                    'appointment_id': appointment.id,
                                    'response': result,
                                    'state': 'failed',
                                    'name': 'Contract Document',
                                })
                    if not sale_order.other_files_uploaded:
                        if sale_order.state in ['sale', 'done'] or sale_order.appointment_result == 'Sold':
                            result= sale_order.add_sale_id_file()
                            if result.get('success', '') == 'true':
                                sale_order_vals.update({'contract_document_uploaded': True})
                                sync_log.create({
                                    'appointment_id': appointment.id,
                                    'response': result,
                                    'name': 'AddSaleAttachment',
                                })
                            else:
                                sync_log.create({
                                    'appointment_id': appointment.id,
                                    'response': result,
                                    'state': 'failed',
                                    'name': 'AddSaleAttachment',
                                })
                        else:
                            result= sale_order.add_quote_id_file(document=False)
                            if result.get('success', '') == 'true':
                                sale_order_vals.update({'contract_document_uploaded': True})
                                sync_log.create({
                                    'appointment_id': appointment.id,
                                    'response': result,
                                    'name': 'AddQuoteAttachment',
                                })
                            else:
                                sync_log.create({
                                    'appointment_id': appointment.id,
                                    'response': result,
                                    'state': 'failed',
                                    'name': 'AddQuoteAttachment',
                                })
                        if result.get('success', '') == 'true':
                            sale_order_vals.update({'other_files_uploaded': True})
                    sale_order.write(sale_order_vals)
                    if sale_order.check_document_upload_completed():
                        sale_order.write({'is_data_upload_completed': True})
                    self.env.cr.commit()
        return True

    @api.model
    def propose_reject_quote(self, data):
        sale_order_id = int(data.get('sale_order_id', False))
        sale_order = self.env['sale.order'].search([('id', '=', sale_order_id)], limit=1)
        order_status=data.get('status',False)
        if not order_status:
            status = {
                'result': 'Success',
                'message': 'Quote Status Empty', }
            return status
        if not sale_order:
            status = {
                'result': 'Success',
                'message': 'sale order not found', }
            return status
        else:
            if order_status == 'proposed':
                sale_order.add_quote_sales_app("proposed")
                sale_order.state = 'sent'
                status = {
                    'result': 'Success',
                    'message': 'Quote  proposed Successfully'
                }
                return status

            if order_status == 'rejected':
                sale_order.add_quote_sales_app("rejected")
                sale_order.state ='cancel'
                status = {
                            'result': 'Success',
                            'message': 'Quote Rejected Successfully'
                        }
                return status
            else:
                status = {
                    'result': 'Success',
                    'message': 'Invalid Parameter For Quote Status'}
                return status

    def date_by_adding_business_days(self,add_days):
        business_days_to_add = add_days
        current_date = datetime.today()
        while business_days_to_add > 0:
            current_date += timedelta(days=1)
            weekday = current_date.weekday()
            if weekday >= 5:
                continue
            business_days_to_add -= 1
        return current_date

    @api.model
    def create_sale_quotation_api(self, data):
        _logger.info('-------create_sale_quotation_api data---------')
        _logger.info(data)
        coapplicant_skip = int(data.get('coapplicant_skip', 0))
        appointment_id = int(data.get('appointment_id', 0))
        floor_type = int(data.get('floor_type', 0))
        discount = float(data.get('discount', 0))
        msrp = float(data.get('msrp', 0))
        adjustment = float(data.get('adjustment', 0))
        additional_cost = float(data.get('additional_cost', 0))
        down_payment_amount = float(data.get('down_payment_amount', 0))
        final_payment = float(data.get('final_payment', 0))
        finance_amount = float(data.get('finance_amount', 0))
        finance_option_id = int(data.get('finance_option_id', 0))
        loan_payment = float(data.get('loan_payment', 0))
        photo_permission = int(data.get('photo_permission', 0))
        installation_date = data.get('installation_date', False)
        owners_right_to_cancel = data.get('owners_right_to_cancel', 0)
        requested_installation = data.get('requested_installation', 0)
        final_date_to_cancel = self.date_by_adding_business_days(3)
        if installation_date:
            installation_date = datetime.strptime(installation_date, '%m/%d/%Y').strftime('%Y-%m-%d')
        if owners_right_to_cancel:
            owners_right_to_cancel = datetime.strptime(owners_right_to_cancel, '%m/%d/%Y').strftime('%Y-%m-%d')
        if requested_installation:
            requested_installation = datetime.strptime(requested_installation, '%m/%d/%Y').strftime('%Y-%m-%d')
        if not floor_type:
            _logger.info("------floor_type Empty------------")
            status = {
                'message': 'floor_type Empty',
                'result': 'Success',
            }
            return status
        if finance_amount and not finance_option_id:
            _logger.info("------Finance Option ID Empty------------")
            status = {
                'message': 'Finance Option ID Empty',
                'result': 'Success',
            }
            return status
        if finance_option_id and not self.env['team.downpayment.option'].browse(int(finance_option_id)).exists():
            _logger.info("------ Finance Option Not Exist-------------")
            status = {'message': 'Finance Option Not Exist', 'result': 'Success'}
            return status
        payment_method = data.get('payment_method', 0)
        if payment_method:
            if payment_method not in ['credit_card', 'debit_card', 'cash', 'check', 'finance']:
                _logger.info("------ Wrong Payment Method-------------")
                status = {'message': 'Wrong Payment Method', 'result': 'Success'}
                return status
        sale_order_obj = self.env['sale.order']
        res_partner_obj = self.env['res.partner']
        vals = {}
        payment_details = []
        if not appointment_id:
            _logger.info("------Appointment ID Empty------------")
            status = {
                'message': 'Appointment ID Empty',
                'result': 'Success',
            }
            return status

        if appointment_id and floor_type:
            appointment = self.env['team.customer.appointment'].search([('id', '=', appointment_id)], limit=1)
            if not appointment:
                _logger.info("------Appointment Not Exist------------")
                status = {
                    'message': 'Appointment Not Exist',
                    'result': 'Success',
                }
                return status
            plan = self.env['product.template'].search([('id', '=', floor_type)], limit=1)
            if not plan:
                _logger.info("------Floor Plan Not Exist------------")
                status = {
                    'message': 'Floor Type Not Exist',
                    'result': 'Success',
                }
                return status

            team_question_obj = self.env['team.contract.question.line'].search(
                [('appointment_id', '=', appointment_id)])
            team_room_obj = self.env['team.contract.room.measurement.line'].search(
                [('appointment_id', '=', appointment_id)])
            room_transition_obj = self.env['team.contract.transition.line'].search(
                [('appointment_id', '=', appointment_id)])
            sale_order_ref = self.env['sale.order'].search([('appointment_id', '=', appointment_id)], limit=1)
            sale_order_vals = {
                'cards': False,
                'cash': False,
                'check': False,
                'balance_finance': False,
            }
            if appointment and not sale_order_ref:
                if appointment.partner_id:
                    vals = {'partner_id': appointment.partner_id.id,
                            'floor_type': floor_type,
                            'appointment_id': appointment_id
                            }
                else:
                    if appointment.customer_name and floor_type:
                        partner_vals = {
                            'name': appointment.customer_name,
                            'phone': appointment.phone,
                            'mobile': appointment.mobile,
                            'street': appointment.street,
                            'street2': appointment.street2,
                            'city': appointment.city,
                            'state_id': appointment.state_id.id or False,
                            'zip': appointment.zip,
                            'country_id': appointment.country_id.id or False,
                            'email': appointment.email
                        }
                        if partner_vals:
                            customer = res_partner_obj.create(partner_vals)
                            if customer:
                                appointment.write({'partner_id': customer.id})
                                split_name = self.split_name(customer.name)
                                inititals = ''
                                if split_name['first_name'] and split_name['last_name']:
                                    inititals = split_name['first_name'][0] + split_name['last_name'][0]
                                if split_name['first_name'] and not split_name['last_name']:
                                    inititals = split_name['first_name'][0]
                                if inititals:
                                    inititals = inititals.upper() or ''
                                vals = {'partner_id': customer.id,
                                        'floor_type': floor_type,
                                        'appointment_id': appointment_id,
                                        'adjustment': adjustment,
                                        'down_payment_amount': down_payment_amount,
                                        'final_payment': final_payment,
                                        'finance_amount': finance_amount,
                                        'finance_option_id': finance_option_id or False,
                                        'balance_payment_method': payment_method,
                                        'loan_payment': loan_payment,
                                        'photo_permission_yes': True if photo_permission == 1 else False,
                                        'photo_permission_no': True if photo_permission == 0 else False,
                                        'coapplicant_skip' : True if coapplicant_skip == 1 else False,
                                        'installation_date': installation_date or False,
                                        'owners_right_to_cancel': final_date_to_cancel.strftime('%Y-%m-%d') or False,
                                        'requested_installation': requested_installation or False,
                                        'applicant_inititals': inititals or ''
                                        }
                if vals:
                    sale_order_ref = sale_order_obj.create(vals)
                    if finance_amount:
                        sale_order_vals.update({'balance_finance': True})
                    else:
                        if payment_method:
                            if payment_method in ['credit_card', 'debit_card']:
                                sale_order_vals.update({'cards': True})
                            if payment_method == 'cash':
                                sale_order_vals.update({'cash': True})
                            if payment_method == 'check':
                                sale_order_vals.update({'check': True})
            if sale_order_ref and appointment:
                if sale_order_ref.order_line:
                    if sale_order_ref.state != 'draft':
                        sale_order_vals.update({'state': 'draft'})
                    sale_order_ref.order_line.unlink()
                if team_question_obj:
                    team_question_obj.write({'order_id': sale_order_ref.id})
                if team_room_obj:
                    team_room_obj.write({'order_id': sale_order_ref.id})
                if room_transition_obj:
                    room_transition_obj.write({'order_id': sale_order_ref.id})
                sale_order_vals.update({
                    'floor_type': floor_type,
                    'down_payment_amount': down_payment_amount,
                    'final_payment': final_payment,
                    'finance_amount': finance_amount,
                    'finance_option_id': finance_option_id or False,
                    'balance_payment_method': payment_method,
                    'adjustment': adjustment,
                    'loan_payment': loan_payment,
                    'photo_permission_yes': True if photo_permission == 1 else False,
                    'photo_permission_no': True if photo_permission == 0 else False,
                    'coapplicant_skip': True if coapplicant_skip == 1 else False,
                    'installation_date': installation_date,
                    'requested_installation': requested_installation
                })
                sale_order_ref.add_payment_line(discount, adjustment, additional_cost, plan.monthly_promo,
                                                self.env['ir.config_parameter'].sudo().get_param(
                                                    'admin_fee') or 0.0 if photo_permission == 1 else 0.0)
                if finance_amount:
                    sale_order_vals.update({'balance_finance': True})
                else:
                    if payment_method:
                        if payment_method in ['credit_card', 'debit_card']:
                            sale_order_vals.update({'cards': True})
                        if payment_method == 'cash':
                            sale_order_vals.update({'cash': True})
                        if payment_method == 'check':
                            sale_order_vals.update({'check': True})

                split_name = self.split_name(sale_order_ref.partner_id.name)
                if split_name['first_name'] and split_name['last_name']:
                    inititals = split_name['first_name'][0] + split_name['last_name'][0]
                if split_name['first_name'] and not split_name['last_name']:
                    inititals = split_name['first_name'][0]
                if inititals:
                    sale_order_vals.update({'applicant_inititals': inititals.upper() or ''})
                sale_order_vals.update({'owners_right_to_cancel': final_date_to_cancel.strftime('%Y-%m-%d')})
                sale_order_ref.write(sale_order_vals)
                _logger.info("------Sale Order updated------------")

                # if not self.env.company.account_sale_tax_id:
                #     status = {
                #         'message': 'Tax Not Configured',
                #         'result': 'Success',
                #     }
                #     return status
                # amount_taxed = 0
                # if self.env.company.account_sale_tax_id.amount:
                #     amount_taxed = sale_order_ref.amount_untaxed * (self.env.company.account_sale_tax_id.amount or 0) /100
                payment_detail = {

                    'package': sale_order_ref.floor_type.name,
                    'total_area': sale_order_ref.total_area,
                    # 'msrp': sale_order_ref.total_area*sale_order_ref.floor_type.flooring_cost,
                    # 'discount_percentage':discount,
                    'msrp': msrp,
                    # 'tax_percentage': self.env.company.account_sale_tax_id.amount or 0,
                    # 'amount_taxed': amount_taxed and round(amount_taxed,2) or 0,
                    # 'total_amount ': round(sale_order_ref.amount_untaxed+amount_taxed,2),
                    'monthly_promo': sale_order_ref.floor_type.monthly_promo or 0,
                    'adjustment': sale_order_ref.adjustment or 0,
                    'price': sale_order_ref.amount_untaxed or 0,
                    'down_payment_amount': sale_order_ref.down_payment_amount or 0,
                    'final_payment': sale_order_ref.final_payment or 0,
                    'balance_payment_method': sale_order_ref.balance_payment_method or '',
                    'finance_amount': sale_order_ref.finance_amount or 0,
                    'finance_option': sale_order_ref.finance_option_id.name or '',
                    'loan_payment': sale_order_ref.loan_payment or 0,
                }

                payment_details.append(payment_detail)
                downpayment_percentages = self.env['team.payment.percentage'].search([])
                payment_percentage = []
                if downpayment_percentages:
                    for downpayment_percentage in downpayment_percentages:
                        payment_percentage_values = {
                            'id': downpayment_percentage.id or 0,
                            'name': downpayment_percentage.name or '',
                            'percentage': downpayment_percentage.percentage or ''
                        }
                        payment_percentage.append(payment_percentage_values)
                downpayment_methods = self.env['team.downpayment.method'].search([])
                payment_method = []
                if downpayment_methods:
                    for downpayment_method in downpayment_methods:
                        downpayment_method_values = {
                            'id': downpayment_method.id or 0,
                            'name': downpayment_method.name or '',
                        }
                        payment_method.append((downpayment_method_values))

                values = {
                    'payment_details': payment_details,
                    'downpayment_percetages': payment_percentage,
                    'downpayment_method': payment_method,

                }

                status = {
                    'message': ' Payment method and payment details',
                    'result': 'Success',
                    'values': [values],
                    'order_id': sale_order_ref.id
                }
                return status
        else:
            _logger.info("------Sale Order creation Failed Unable to  Get Payment Details -------------")
            status = {
                'message': 'Sale Order Creation Failed appointment_id or floor_type Not found',
                'result': 'Success'
            }

            return status


    def find_card_type(self, card_number):
        card_type = ''
        if card_number:
            number = str(card_number)
            if len(number) == 15:
                if number[:2] == "34" or number[:2] == "37":
                    card_type = "amex"
            if len(number) == 13:
                if str(number[:1]) == ("4"):
                    card_type = "visa"
            if len(number) == 16:
                if number[:4] == "6011":
                    card_type = "discover"
                if int(number[:2]) >= 51 and int(number[:2]) <= 55:
                    card_type = "mastercard"
                if number[:1] == "4":
                    card_type = "visa"
                if number[:4] == "3528" or number[:4] == "3529":
                    card_type = "jcb"
                if int(number[:3]) >= 353 and int(number[:3]) <= 359:
                    card_type = "jcb"
            if len(number) == 14:
                if number[:2] == "36":
                    card_type = "diners"
                if int(number[:3]) >= 300 and int(number[:3]) <= 305:
                    card_type = "diners"
        return card_type

    def prepare_authorize_payment_values(self, acquirer, order, data):
        partner = order.partner_id
        first_name = partner.name or ''
        last_name = ''
        appointment_id = order.appointment_id or False
        if appointment_id:
            if appointment_id.applicant_first_name:
                first_name = appointment_id.applicant_first_name or ''
            last_name = appointment_id.applicant_last_name or ''

        values = {
            "createTransactionRequest": {
                "merchantAuthentication": {
                    "name": acquirer.authorize_login,
                    "transactionKey": acquirer.authorize_transaction_key
                },
                "refId": order.name,
                "transactionRequest": {
                    "transactionType": "authOnlyTransaction",
                    "amount": str(data.get('amount', 0)),
                    "payment": {
                        "creditCard": {
                            "cardNumber": data.get('cc_number', ''),
                            "expirationDate": data.get('cc_expiry', ''),
                            "cardCode": data.get('cc_cvc', '')
                        }
                    },
                    "lineItems": {
                        "lineItem": {
                            "itemId": "1",
                            "name": "Advance Payment",
                            "description": "Advance Payment",
                            "quantity": "1",
                            "unitPrice": str(data.get('amount', 0))
                        }
                    },

                    "billTo": {
                        "firstName": first_name,
                        "lastName": last_name,
                        "company": "",
                        "address": partner.street or "",
                        "city": partner.city or "",
                        "state": partner.state_id and partner.state_id.code or "",
                        "zip": partner.zip or "",
                        "country": partner.country_id and partner.country_id.code or ""
                    },


                }
            }
        }
        return values

    def action_authorize_payment(self, data):
        """

        :param data:
            Sample format is as follows: {
                'sale_order_id': self.id,
                'cc_number': '4111111111111111',
                'cc_expiry': '02/22',
                'cc_cvc': '185',
                'cc_holder_name': 'Ajay Jayaram',
                'amount': 2000.0,
            }
        :return:
        """
        acquirer = self.env.ref('payment.payment_acquirer_authorize')
        for order in self:
            transaction = AuthorizeAPICustom(acquirer)
            if order.authorize_transaction_id:
                transaction.void(order.authorize_transaction_id or '')
            values = self.prepare_authorize_payment_values(acquirer, order, data)
            response = transaction._authorize_request_custom(values)
            if response and response.get('err_code'):
                self.env['otl.card.transaction.log'].create({
                    'sale_order_id': order.id,
                    'name': response.get('transaction_id', ''),
                    'error_code': response.get('err_code', ''),
                    'message': response.get('error_text', ''),
                    'state': 'failed',
                    'type': 'authorize',
                })
                return {
                    'result': 'Failed',
                    'message': response.get('error_text', '')
                }
            transaction_ref = response.get('transactionResponse', {}).get('transId', '')
            card_type = response.get('transactionResponse', {}).get('accountType', '')
            order.write({'authorize_transaction_id': transaction_ref, 'card_type': card_type})
            self.env['otl.card.transaction.log'].create({
                'sale_order_id': order.id,
                'name': transaction_ref,
                'message': response.get('transactionResponse', {}).get('messages')[0].get('description'),
                'state': 'success',
                'type': 'authorize',
            })
            return {
                'result': 'Success',
                'transaction_id': transaction_ref,
                'message': response.get('transactionResponse', {}).get('messages')[0].get('description'),
            }

    def prepare_capture_payment_values(self, acquirer, order, data):
        values = {
            "createTransactionRequest": {
                "merchantAuthentication": {
                    "name": acquirer.authorize_login,
                    "transactionKey": acquirer.authorize_transaction_key
                },
                "refId": order.name,
                "transactionRequest": {
                    "transactionType": "priorAuthCaptureTransaction",
                    "amount": str(data.get('amount', 0)),
                    "refTransId": data.get('transaction_id', '')
                }
            }
        }
        return values

    def action_capture_payment(self, data):
        """

        :param data:
            Sample data format is as follows {
                'transaction_id': '40053844556',
                'amount': 2000.0,
            }
        :return:
        """
        acquirer = self.env.ref('payment.payment_acquirer_authorize')
        for order in self:
            values = self.prepare_capture_payment_values(acquirer, order, data)
            transaction = AuthorizeAPICustom(acquirer)
            response = transaction._authorize_request_custom(values)
            if response and response.get('err_code'):
                self.env['otl.card.transaction.log'].create({
                    'sale_order_id': order.id,
                    'name': response.get('transaction_id', ''),
                    'error_code': response.get('err_code', ''),
                    'message': response.get('error_text', ''),
                    'state': 'failed',
                    'type': 'capture',
                })
                return {
                    'result': 'Failed',
                    'message': response.get('error_text', '')
                }
            currency = order.pricelist_id.currency_id
            partner = order.partner_id
            vals = {
                'amount': data.get('amount', 0),
                'currency_id': currency.id,
                'partner_id': partner.id,
                'sale_order_ids': [(6, 0, self.ids)],
                'acquirer_id': acquirer.id,
                'acquirer_reference': response.get('transactionResponse', {}).get('transId'),
                'date': fields.Datetime.now(),
            }
            transaction = self.env['payment.transaction'].create(vals)
            transaction._set_transaction_done()
            self.action_confirm()
            self.env['otl.card.transaction.log'].create({
                'sale_order_id': order.id,
                'name': response.get('transactionResponse', {}).get('transId'),
                'message': response.get('transactionResponse', {}).get('messages')[0].get('description'),
                'state': 'success',
                'type': 'capture',
            })
            return {
                'result': 'Success',
                'response_code': response.get('transactionResponse', {}).get('responseCode'),
                'trans_id': response.get('transactionResponse', {}).get('transId'),
                'message': response.get('transactionResponse', {}).get('messages')[0].get('description'),
            }



    """
    Code is commented since the process flow is changed
    def action_do_payment(self, data):
        acquirer = self.env.ref('payment_bancard.payment_acquirer_bancard')
        status = {}
        if not data.get('sale_order_id', False):
            return {
                'message': "Sale Order ID is missing.",
                'result': 'Failed',
            }
        order = self.search([('id', '=', data.get('sale_order_id', False))])
        if order:
            if not order.partner_id.zip:
                return {
                    'message': "Customer's ZIP Code is mandatory.",
                    'result': 'Failed',
                }
            cc_number = data['cc_number']
            cc_number = cc_number.replace(' ', '')
            cc_brand = self.find_card_type(cc_number)
            cc_expiry = data['cc_expiry'].replace('-', '/')
            cc_cvc = data['cc_cvc'],
            cc_holder_name = data['cc_holder_name']
            amount=data['amount']
            data.update({
                'cc_number': cc_number,
                'acquirer_id': acquirer.id,
                'partner_id': order.partner_id.id,
                'billing_partner_id': order.partner_invoice_id.id,
                'cc_brand': cc_brand,
                'cc_expiry': cc_expiry,
                'amount': amount,
                'zip': order.partner_id.zip,
                'cc_holder_name':cc_holder_name,
                'cc_cvc':cc_cvc,

            })
            print(data)
            try:
                x = acquirer.s2s_validate(data)
                print('authorize_s2s_form_validate ' + str(x))
                if not x:
                    status = {
                        'message':"Card Validation Error Wrong Data",
                        'result': 'Failed',
                    }
                    return status
                payment_token = acquirer.s2s_process(data)
                if  payment_token:
                    vals = {
                        'payment_token_id': payment_token.id,
                        'acquirer_id': acquirer.id,
                    }
                    tx = order._create_payment_transaction_with_data(vals, data)
                    print(tx)
                    if tx:
                        order.action_confirm()
                        PaymentProcessing.add_payment_transaction(tx)
                        status = {
                            'message': 'Payment done successfully',
                            'result': 'Success',
                        }
                        return status
                    else:
                        status = {
                            'message': "Payment transaction failed unable to complete transaction.",
                            'result': 'Failed',
                        }
                        return status
                else:
                    status = {
                        'message': "Payment transaction not completed failed to generate token.",
                        'result': 'Failed',
                    }
                    return status
            except (UserError) as e:
                status = {
                    'message': e.name,
                    'result': 'Failed',
                }
                return status
        else:
            status = {
                'message': 'Sale Order is not found for given order id.',
                'result': 'Failed',
            }

        return status
    """

class AuthorizeAPICustom(AuthorizeAPI):

    def _authorize_request_custom(self, data):
        _logger.info('_authorize_request: Sending values to URL %s, values:\n%s', self.url, data)
        try:
            resp = requests.post(self.url, json.dumps(data))
        except ConnectionResetError:
            return {
                'err_code': 'Errno 104',
                'error_text': 'ConnectionResetError'
            }
        resp.raise_for_status()
        resp = json.loads(resp.content)
        _logger.info("_authorize_request: Received response:\n%s", resp)
        transactionResponse = resp.get('transactionResponse', {})
        errors = transactionResponse.get('errors', [])
        responseCode = transactionResponse.get('responseCode', '')
        if errors and responseCode != '1':
            return {
                'err_code': errors[0].get('errorCode', ''),
                'error_text': errors[0].get('errorText', ''),
            }
        messages = resp.get('messages', {})
        if messages and messages.get('resultCode', '') == 'Error':
            error_text = ''
            if transactionResponse and transactionResponse.get('errors', []) and transactionResponse.get('errors', [])[0].get('errorText', ''):
                error_text = transactionResponse.get('errors', [])[0].get('errorText', '')
            return {
                'transaction_id': resp.get('transactionResponse', {}).get('transId', ''),
                'err_code': messages.get('message')[0].get('code'),
                'err_msg': messages.get('message')[0].get('text'),
                'error_text' : error_text or messages.get('message')[0].get('text'),
            }

        return resp



class ProductProduct(models.Model):
    _inherit ='product.product'

    @api.model
    def select_material_from_plan(self, data):
        appointment_id = int(data.get('appointment_id', 0))
        if not self.env['product.product'].browse(int(data.get('material_id', False))).exists():
            return {'message': 'Update Material Based on plan Failed Material not Found', 'result': False}
        material_id = int(data.get('material_id', False))
        if appointment_id and material_id:
            contract_room_lines = self.env['team.contract.room.measurement.line'].search(
                [('appointment_id', '=', appointment_id)])
            if contract_room_lines:
                for contract_room_line in contract_room_lines:
                    contract_room_line.write({'material_id': material_id})
                status = {'message': 'Update Material Based on plan  Success', 'result': 'True'}
                return status
            else:
                status = {'message': 'Update Material Based on plan Failed', 'result': 'False'}
                return status


    def profile_image(self,model_name):
        url = ''
        Attachment = self.env['ir.attachment'].sudo().search([('res_model', '=', model_name), ('res_id', '=', self.id)],
                                                             limit=1)
        if Attachment:
            Attachment.sudo().write({'datas': self.image_1920})
            if not Attachment.access_token:
                Attachment.generate_access_token()
            url = URL + '/web/image/' + str(Attachment.id) + '?access_token=' + str(Attachment.access_token)
        else:
            Attachment = self.env['ir.attachment'].sudo().create({
                'res_id': self.id,
                'res_model': model_name,
                'datas': self.image_1920,
                'name': self.name

            })
            Attachment.generate_access_token()
            url = URL + '/web/image/' + str(Attachment.id) + '?access_token=' + str(Attachment.access_token)
        return url

    @api.model
    def get_material_list(self, data):
        payment_plan_id = int(data.get('payment_plan_id', 0))
        list=[]
        if payment_plan_id:
            product_list = self.env['product.product'].search([('product_tmpl_id','=',payment_plan_id),('is_material','=',True)])
        else:
            product_list = self.env['product.product'].search([('is_material','=',True)])
        if product_list:
            for product in product_list:
                material_image_url = ''
                if product.image_1920:
                    material_image_url = product.profile_image('product.product')
                vals={
                    'material_id':product.id or 0,
                    'name':product.name,
                    'color':product.color or 'False',
                    'material_image_url': material_image_url
                }
                list.append(vals)
            status = {
                'result': 'Success',
                'values': list,
                'message': '',
            }
        else:
            status = {
                'result': 'Failed',
                'values': list,
                'message': 'No Details Found',
            }
        return status

class TeamPaymentTransaction(models.Model):
    _inherit = 'team.payment.transaction.line'

    @api.model
    def create_payment_transaction(self,data):
        if self.env['product.template'].browse(int(data.get('payment_plan', 0))).exists():
            payment_plan =int(data.get('payment_plan', 0))
        else:
            _logger.info("------ Payment Plan ID Empty------------")
            status = {
                'message': 'Payment Plan ID Empty',
                'result': 'Failed',
            }
            return status
        if self.env['team.downpayment.option'].browse(int(data.get('payment_option', 0))).exists():
            payment_option = int(data.get('payment_option', 0))
        else:
            _logger.info("------ Empty------------")
            status = {
                'message': 'payment_option ID Empty',
                'result': 'Failed',
            }
            return status
        if self.env['team.payment.percentage'].browse(int(data.get('downpayment_percentage', 0))).exists():
            downpayment_percentage = int(data.get('downpayment_percentage', 0))
        else:
            _logger.info("------ Empty downpayment_percentage------------")
            status = {
                'message': 'downpayment_percentage ID Empty',
                'result': 'Failed',
            }
            return status
        if self.env['team.downpayment.method'].browse(int(data.get('payment_method', 0))).exists():
            payment_method = int(data.get('payment_method', 0))
        else:
            _logger.info("------ payment_method Empty------------")
            status = {
                'message': 'payment_method ID Empty',
                'result': 'Failed',
            }
            return status
        if  self.env['sale.order'].browse(int(data.get('order_id', 0))).exists():
            order_id = int(data.get('order_id', 0))
        else:
            _logger.info("------order_id Empty------------")
            status = {
                'message': 'order_id ID Empty',
                'result': 'Failed',
            }
            return status
        total_price=0
        if data.get('total_price', 0):
            total_price = int(data.get('total_price', 0))
        downpayment=0
        if data.get('downpayment', 0):
            downpayment = int(data.get('downpayment', 0))
        balance=0
        if data.get('balance', 0):
            balance = int(data.get('balance', 0))


        values ={
            'payment_plan':int(payment_plan) or 0,
            'payment_option':int(payment_option) or 0,
            'downpayment_percentage':int(downpayment_percentage) or 0,
            'payment_method':payment_method or 0,
            'total_price':total_price,
            'downpayment':downpayment,
            'balance':balance,
            'order_id': int(order_id) or 0,
            'payment_success': True,
        }
        payment_obj=self.env['team.payment.transaction.line']
        record = payment_obj.create(values)
        if record:
            _logger.info("------ Payment_Transaction Created ------------")
            status = {
                'result': 'Success',
                'message':'Payment Transaction Created',
            }
            return status
        else:
            _logger.info("------ Payment_Transaction Creation Failed ------------")
            status = {
                'result': 'Failed',
                'message':'Payment_Transaction Creation Failed ',}

            return status

# -*- coding: utf-8 -*-
from odoo import api, fields, models, registry, _
from odoo.exceptions import UserError
from xml.etree.ElementTree import fromstring, ElementTree

from datetime import datetime,timedelta
import json
import logging
from werkzeug import urls
from PIL import Image
import requests
import pytz
from io import BytesIO
import base64
try:
    from urllib.request import urlopen  # pylint: disable=deprecated-module
except ImportError:
    from urllib import urlopen  # pylint: disable=deprecated-module

TIMEOUT = 50
_logger = logging.getLogger(__name__)

from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT


class TeamImproveitConfiguration(models.Model):
    _name = 'team.improveit.configuration'
    _description = "Team Improveit Api Configuration"

    name = fields.Char(string='Name')
    client_id = fields.Char(string='Client ID')
    client_secret = fields.Char(string='Client Secret')
    username = fields.Char(string='username')
    password = fields.Char(string='password')
    grant_type = fields.Char(string='Grant Type')
    token_generated = fields.Char(string='Token Generated')
    mode = fields.Selection([('live','Live'),('test','Test')], default='live')
    token_url = fields.Char(string='Token Endpoint URL')
    auth_url = fields.Char(string='Authentication Endpoint URL')
    active = fields.Boolean(default=True)
    api_type = fields.Selection([
        ('improveit', 'Improveit'),
        ('zapier', 'Zapier'),
        ('boomi', 'Boomi'),
        ('rules_engine', 'Rules Engine'),
        ('contract_doc', 'Contract Document'),
        ('review', 'Send Review'),
        ('order_checklist', 'Order Checklist'),
    ], string='API Type', default='improveit')
    section = fields.Selection([
        ('quote', 'Quote'),
        ('quote_item', 'Quote Item'),
        ('credit_application', 'Credit Application'),
        ('QuoteAddAttachment', 'Quote Add Attachment'),
        ('SaleAddAttachment', 'Sale Add Attachment'),
        ('CreditAddAttachment ', 'Credit Add Attachment'),
    ],'Zapier API Section')
    test_appointment_id = fields.Char('Test Appointment ID')
    update_existing_record = fields.Boolean('Update Existing Record')
    client_token = fields.Char('Client Token')
    sync_master_data_in_progress = fields.Boolean("Is Sync Master Data Executing?", default= False)
    enable_ssl = fields.Boolean('Enable SSL', default=True)

    def sync_appointment_data(self):
        configurations = self.env['team.improveit.configuration'].search([('api_type', '=', 'improveit')])
        for record in configurations:
            client_id = record.client_id
            username = record.username
            password = record.password
            client_secret = record.client_secret
            grant_type = record.grant_type
            url = record.token_url
            update_existing_record = record.update_existing_record

            headers = {"Content-type": "application/x-www-form-urlencoded"}
            data = {
                'client_id': client_id,
                'client_secret': client_secret,
                'username': username,
                'password': password,
                'grant_type': grant_type
            }
            try:
                req = requests.post(url, data=data, headers=headers, timeout=TIMEOUT, verify=configurations.enable_ssl)
                req.raise_for_status()
                content = req.json()
                record.token_generated = content['access_token']
                instance_url = content['instance_url']
                if not record.token_generated:
                    raise UserError(_("Access Token Not Generated."))
                access_token = record.token_generated
                query = "SELECT+i360__Address__c,i360__Start__c,i360__Start_Time__c,i360__Appt_Set_On__c,i360__City__c,i360__County__c,i360__State__c,i360__Zip__c,i360__Sales_Rep_1__c,i360__Sales_Rep_1_Next_Appointment__c,i360__Sales_Rep_2__c,i360__Sales_Rep_2_Next_Appointment__c+FROM+i360__Appointment__c+WHERE+i360__Start__c>=%s" % datetime.today().date()
                request_url = instance_url+"/services/data/v45.0/query/?q=%s" % (query)
                try:
                    result = requests.get(request_url, headers={'Authorization': 'Bearer %s' % access_token},timeout=TIMEOUT)
                    result.raise_for_status()
                    data = result.json()
                    count =1
                    for appointment in data["records"]:
                        record.process_appointment(instance_url,appointment, access_token,update_existing_record)
                        _logger.info("------Processing: %s of %s"%(count, len(data['records'])))
                        count +=1
                except requests.HTTPError:
                    raise UserError(_("Something went wrong while Fetching Appointments."))
            except IOError:
                error_msg = _(
                    "Something went wrong during token generation.")
                raise self.env['res.config.settings'].get_config_warning(error_msg)


    def process_appointment(self,instance_url,record,access_token,update_existing_record):
        url=instance_url+record['attributes']['url']
        user = self.env.user
        try:
            req = requests.get(url, headers={'Authorization': 'Bearer %s' % access_token},timeout=TIMEOUT)
            req.raise_for_status()
            content = req.json()
            name = content['Name']

            applicant_name = content['i360__Prospect_Name__c'] or ''
            applicant_name_split = self.split_name(applicant_name)
            co_applicant_name = content['i360__Prospect_Secondary__c'] or ''
            co_applicant_name_split = self.split_name(co_applicant_name)

            improveit_appointment_id = content['Id']
            user_id = content['i360__Sales_Rep_1__c']
            res_user_id = False
            if user_id:
                res_user_id = self.env['res.users'].search(
                    [('improveit_user_id', '=', user_id)], limit=1)
            customer_name = content['i360__Prospect_Name__c']
            if not customer_name:
                raise UserError(_("Customer Name Empty."))
            phone = content['i360__Prospect_Phone__c'] or ''
            email = content['i360__Email_Address__c'] or ''
            street = content.get('i360__Address__c', '')
            if not street:
                raise UserError(_("Address Empty."))
            city = content['i360__City__c'] or ''
            zip = content['i360__Zip__c'] or ''
            if content['i360__Latitude__c']:
                partner_latitude = float(content['i360__Latitude__c'])
            else:
                partner_latitude = 0
            if content['i360__Longitude__c']:
                partner_longitude = float(content['i360__Longitude__c'])
            else:
                partner_longitude = 0
            date_localization = content['i360__Leadsource_Taken_On__c']
            appointment_day = content['i360__Start__c']
            appointment_time = content['i360__Start_Time__c']
            appointment_date = appointment_day
            if appointment_day and appointment_time:
                appointment_date_str = '%s %s' % (appointment_day, appointment_time)
                date_obj = datetime.strptime(appointment_date_str, '%Y-%m-%d %I:%M %p')
                if user.tz:
                    tz = pytz.timezone(user.tz) or pytz.utc
                    appointment_date = tz.localize(date_obj).astimezone(pytz.utc).strftime('%Y-%m-%d %H:%M:%S')
                else:
                    appointment_date = date_obj.strftime('%Y-%m-%d %H:%M:%S')
            if not appointment_date:
                raise UserError(_("Something went wrong while Fetching Appointments."))
            state = content.get('i360__State__c', '')
            state_id = False
            if state:
                state_id = self.env['res.country.state'].search(
                    ['|', ('name', '=', state), ('code', '=', state)], limit=1)
            co_applicant = content['i360__Prospect_Secondary__c'] or ''
            partner = self.env['res.partner'].search([('email','=',email),(('email','!=',''))],limit=1)
            appointments = self.env['team.customer.appointment'].search([('improveit_appointment_id','=',improveit_appointment_id)],limit=1)
            if not appointments:
                appointment_values = {
                    'improveit_appointment_id': improveit_appointment_id,
                    'partner_id': partner.id if partner else False,
                    'user_id': res_user_id and res_user_id.id or False,
                    'customer_name': customer_name,
                    'street': street,
                    'city': city,
                    'zip': zip,
                    'phone': phone,
                    'email': email,
                    'appointment_date': appointment_date,
                    'co_applicant': co_applicant,
                    'date_localization': date_localization,
                    'partner_latitude': partner_latitude,
                    'partner_longitude': partner_longitude,
                    'state': 'scheduled',
                    'state_id': state_id and state_id.id or False,
                    'country_id': state_id and state_id.country_id.id or False,
                    'appointment_day': appointment_day,
                    'appointment_time': appointment_time,
                    'applicant_first_name':applicant_name_split['first_name'] or False,
                    'applicant_middle_name':applicant_name_split['middle_name'] or False,
                    'applicant_last_name':applicant_name_split['last_name'] or False,
                    'co_applicant_first_name':co_applicant_name_split['first_name'] or False,
                    'co_applicant_middle_name':co_applicant_name_split['last_name'] or False ,
                    'co_applicant_last_name':co_applicant_name_split['middle_name'] or False ,
                }
                appointment_obj=self.env['team.customer.appointment'].create(appointment_values)
            elif appointments and appointments.state == 'scheduled' and update_existing_record:
                appointment_values = {
                    'partner_id': partner.id if partner else False,
                    'customer_name': customer_name,
                    'user_id': res_user_id and res_user_id.id or False,
                    'street': street,
                    'city': city,
                    'zip': zip,
                    'phone': phone,
                    'email': email,
                    'appointment_date': appointment_date,
                    'co_applicant': co_applicant,
                    'date_localization': date_localization,
                    'partner_latitude': partner_latitude,
                    'partner_longitude': partner_longitude,
                    'state_id': state_id and state_id.id or False,
                    'country_id': state_id and state_id.country_id.id or False,
                    'appointment_day': appointment_day,
                    'appointment_time': appointment_time,
                    'applicant_first_name': applicant_name_split['first_name'] or False,
                    'applicant_middle_name': applicant_name_split['middle_name'] or False,
                    'applicant_last_name': applicant_name_split['last_name'] or False,
                    'co_applicant_first_name': co_applicant_name_split['first_name'] or False,
                    'co_applicant_middle_name': co_applicant_name_split['last_name'] or False,
                    'co_applicant_last_name': co_applicant_name_split['middle_name'] or False,
                }
                appointments.write(appointment_values)
            return True

        except requests.HTTPError:
            raise UserError(_("Something went wrong while Fetching Appointments."))

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


    def sync_sale_person_data(self):
        configurations = self.env['team.improveit.configuration'].search([('api_type', '=', 'improveit')])
        for record in configurations:
            client_id = record.client_id
            username = record.username
            password = record.password
            client_secret = record.client_secret
            grant_type = record.grant_type
            url = record.token_url

            headers = {"Content-type": "application/x-www-form-urlencoded"}
            data = {
                'client_id': client_id,
                'client_secret': client_secret,
                'username': username,
                'password': password,
                'grant_type': grant_type
            }
            try:
                req = requests.post(url, data=data, headers=headers, timeout=TIMEOUT)
                req.raise_for_status()
                content = req.json()
                record.token_generated = content['access_token']
                instance_url = content['instance_url']
                if not record.token_generated:
                    raise UserError(_("Access Token Not Generated."))
                access_token = record.token_generated
                query = "SELECT+Id+,+email+,+name+from+User"
                request_url = instance_url + "/services/data/v45.0/query/?q=%s" % (query)
                try:
                    result = requests.get(request_url, headers={'Authorization': 'Bearer %s' % access_token},
                                          timeout=TIMEOUT)
                    result.raise_for_status()
                    data = result.json()
                    for sale_person in data["records"]:
                        record.process_sales_person(instance_url, sale_person, access_token)
                except requests.HTTPError:
                    raise UserError(_("Something went wrong while Fetching Sale Person."))
            except IOError:
                error_msg = _(
                    "Something went wrong during token generation.")
                raise self.env['res.config.settings'].get_config_warning(error_msg)

    def process_sales_person(self, instance_url, record, access_token):
        url = instance_url + record['attributes']['url']
        try:
            req = requests.get(url, headers={'Authorization': 'Bearer %s' % access_token}, timeout=TIMEOUT)
            req.raise_for_status()
            content = req.json()
            improveit_user_id = content['Id']
            if not improveit_user_id:
                raise UserError(_("Sale person ID Empty."))
            name = content['Name']
            _logger.info("-------Processing: %s"%name)
            if not name:
                raise UserError(_("Sale person Name Empty."))
            email = content['Email']
            if not email:
                raise UserError(_("Sale person Email Empty."))
            login = content.get('Username', '') or email
            mobile = content['MobilePhone'] or ''
            title = content['Title'] or ''
            phone = content['Phone'] or ''
            street = content['Street'] or ''
            city = content['City'] or ''
            zip = content['PostalCode'] or ''
            state = content['State'] or ''
            country = content['Country'] or ''
            title_id = self.env['res.partner.title'].search(
                [('name', '=', title)], limit=1)
            res_user_id = self.env['res.users'].with_context(active_test=False).search(
                [('improveit_user_id', '=', improveit_user_id)], limit=1)
            state_id = self.env['res.country.state'].search(
                ['|', ('name', '=', state), ('code', '=', state)], limit=1)
            country_id = state_id and state_id.country_id or False
            user_image_url = content.get('FullPhotoUrl', '')
            user_image_data = False
            if_login_exist = self.env['res.users'].with_context(active_test=False).search([('login', '=', login)],
                                                                                          limit=1)
            # if user_image_url:
            #     response = requests.get(user_image_url)
            #     user_image_data = Image.open(BytesIO(response.url))
            if res_user_id and res_user_id.id == if_login_exist.id:
                vals = {
                    'improveit_user_id': improveit_user_id,
                    'login': login,
                    'name': name,
                    'mobile': mobile,
                    'phone': phone,
                    'email': email,
                    'street': street,
                    'city': city,
                    'zip': zip,
                    'country_id': country_id and country_id.id or False,
                    'state_id': state_id and state_id.id or False,
                    'title': title_id and title_id.id or False,
                    'image_1920': user_image_data,
                    'active': True,
                    'groups_id': [(6, 0, [self.env.ref('sales_team.group_sale_salesman').id,
                                          self.env.ref('base.group_partner_manager').id,self.env.ref('account.group_account_invoice').id])]
                }
                res_user_id.write(vals)
            elif not res_user_id and not if_login_exist:
                vals = {
                    'improveit_user_id': improveit_user_id,
                    'login': login,
                    'password': login,
                    'name': name,
                    'groups_id': [(6, 0, [self.env.ref('sales_team.group_sale_salesman').id,
                                          self.env.ref('base.group_partner_manager').id,self.env.ref('account.group_account_invoice').id])],
                    'mobile': mobile,
                    'phone': phone,
                    'email': email,
                    'street': street,
                    'city': city,
                    'zip': zip,
                    'country_id': country_id and country_id.id or False,
                    'state_id': state_id and state_id.id or False,
                    'title': title_id and title_id.id or False,
                    'image_1920': user_image_data,
                    'active': True
                }
                res_obj = self.env['res.users'].create(vals)
            return True

        except requests.HTTPError:
            raise UserError(_("Something went wrong while Fetching Sale Person."))


    def sync_product_data(self):
        configurations = self.env['team.improveit.configuration'].search([('api_type', '=', 'improveit')])
        for record in configurations:
            client_id = record.client_id
            username = record.username
            password = record.password
            client_secret = record.client_secret
            grant_type = record.grant_type
            url = record.token_url

            headers = {"Content-type": "application/x-www-form-urlencoded"}
            data = {
                'client_id': client_id,
                'client_secret': client_secret,
                'username': username,
                'password': password,
                'grant_type': grant_type
            }
            try:
                req = requests.post(url, data=data, headers=headers, timeout=TIMEOUT)
                req.raise_for_status()
                content = req.json()
                record.token_generated = content['access_token']
                instance_url = content['instance_url']
                if not record.token_generated:
                    raise UserError(_("Access Token Not Generated."))
                access_token = record.token_generated
                query = "SELECT+ID,Name,i360__Price__c+FROM+i360__Product__c+WHERE i360__Component__c='Vinyl Flooring'"
                request_url = instance_url + "/services/data/v45.0/query/?q=%s" % (query)
                try:
                    result = requests.get(request_url, headers={'Authorization': 'Bearer %s' % access_token},
                                          timeout=TIMEOUT)
                    result.raise_for_status()
                    data = result.json()
                    for products in data["records"]:
                        record.process_products(instance_url, products, access_token)
                except requests.HTTPError:
                    raise UserError(_("Something went wrong while Fetching Appointments."))
            except IOError:
                error_msg = _(
                    "Something went wrong during token generation.")
                raise self.env['res.config.settings'].get_config_warning(error_msg)

    def process_products(self, instance_url, record, access_token):
        url = instance_url + record['attributes']['url']
        try:
            req = requests.get(url, headers={'Authorization': 'Bearer %s' % access_token}, timeout=TIMEOUT)
            req.raise_for_status()
            content = req.json()
            improveit_product_id = content['Id']
            name = content['Name']
            price = content['i360__Price__c']
            is_deleted = content['IsDeleted']
            payment_plan = content['i360__Style__c']
            description = content['i360__Product_Description__c']
            product_template = self.env['product.template'].search([('improveit_product_id', '=', improveit_product_id)])
            if not product_template and not is_deleted and 'Stairs' not in name:
                product_template_values = {
                'name': name,
                'improveit_product_id': improveit_product_id,
                'type': 'consu',
                'list_price': price,
                'payment_plan': payment_plan,
                'description': description
                }
                product_template = self.env['product.template'].create(product_template_values)
                i360__Configuration__c = json.loads(content['i360__Configuration__c'])
                product_attribute = self.env['product.attribute'].search([('name', '=', 'colour')], limit=1)
                if not product_attribute:
                    product_attribute_vals = {
                        'name': 'colour'
                    }
                    product_attribute = self.env['product.attribute'].create(product_attribute_vals)
                if i360__Configuration__c.get('fields', []):
                    fields = i360__Configuration__c.get('fields', [])
                    variants = []
                    for field_data in fields:
                        if field_data.get('name', '') == 'Product Selected':
                            variants = field_data.get('values', [])
                            break
                    if variants:
                        attribute_value_id_list = []
                        for variant in variants:
                            names = [value.name for value in product_attribute.value_ids]
                            if variant['name'] not in names:
                                new_attribute_value = {
                                    'name': variant['name'],
                                    'attribute_id': product_attribute.id
                                }
                                attribute_value_id = self.env['product.attribute.value'].create(new_attribute_value)
                            attribute_value_id = self.env['product.attribute.value'].search(
                                [('name', '=', variant['name']), ('attribute_id', '=', product_attribute.id)], limit=1)
                            attribute_value_id_list.append((attribute_value_id.id))
                        attribute_line = self.env['product.template.attribute.line']
                        attribute_line_vals = {
                            'product_tmpl_id': product_template.id,
                            'attribute_id': product_attribute.id,
                            'value_ids': [(6, 0, attribute_value_id_list)],
                        }
                        attribute_line.create(attribute_line_vals)

        except requests.HTTPError:
            raise UserError(_("Something went wrong while Fetching Product Data."))


    def sync_question_data(self):
        configurations = self.env['team.improveit.configuration'].search([('api_type', '=', 'improveit')])
        for record in configurations:
            client_id = record.client_id
            username = record.username
            password = record.password
            client_secret = record.client_secret
            grant_type = record.grant_type
            url = record.token_url

            headers = {"Content-type": "application/x-www-form-urlencoded"}
            data = {
                'client_id': client_id,
                'client_secret': client_secret,
                'username': username,
                'password': password,
                'grant_type': grant_type
            }
            try:
                req = requests.post(url, data=data, headers=headers, timeout=TIMEOUT)
                req.raise_for_status()
                content = req.json()
                record.token_generated = content['access_token']
                instance_url = content['instance_url']
                if not record.token_generated:
                    raise UserError(_("Access Token Not Generated."))
                access_token = record.token_generated
                query = "SELECT+ID,Name,i360__Price__c+FROM+i360__Product__c+WHERE i360__Component__c='Vinyl Flooring'"
                request_url = instance_url + "/services/data/v45.0/query/?q=%s" % (query)
                try:
                    result = requests.get(request_url, headers={'Authorization': 'Bearer %s' % access_token},
                                          timeout=TIMEOUT)
                    result.raise_for_status()
                    data = result.json()
                    for products in data["records"]:
                        record.process_questions(instance_url, products, access_token)
                except requests.HTTPError:
                    raise UserError(_("Something went wrong while Fetching Appointments."))
            except IOError:
                error_msg = _(
                    "Something went wrong during token generation.")
                raise self.env['res.config.settings'].get_config_warning(error_msg)

    def process_questions(self, instance_url, record, access_token):
        url = instance_url + record['attributes']['url']
        try:
            req = requests.get(url, headers={'Authorization': 'Bearer %s' % access_token}, timeout=TIMEOUT)
            req.raise_for_status()
            content = req.json()
            i360__Configuration__c = json.loads(content['i360__Configuration__c'])
            if i360__Configuration__c.get('fields', []):
                questions = i360__Configuration__c.get('fields', [])
            if questions and content['Id'] == 'a0S6g000000mcnoEAA':
                question_list =[]
                for question in questions:
                    room_list = []
                    rooms = self.env['team.room.room'].search([])
                    for room in rooms:
                        room_list.append(room.id)
                    vals = {}
                    if question['name']:
                        check_quote_question  =self.env['team.quote.question'].search([('code','=',question['name'])],limit=1)
                        question_list.append(question['name'])
                        if 'Transition' not in question['name']:
                            vals.update({'name': question['name']})
                            vals.update({'code': question['name']})
                            vals.update({'show_in_measurement': True})
                            vals.update({'show_in_contract': True})
                            vals.update({'room_ids':[(6, 0, room_list)]})
                            if question['type'] == 'number':
                                if "amount" in question:
                                    amount = question['amount']
                                else:
                                    amount = 0.0
                                if "numberMin" in question:
                                    numberMin = question['numberMin']
                                if "numberMax" in question:
                                    numberMax = question['numberMax']
                                vals.update({'question_type':'numerical_box','amount':amount or 0.0,'validation_required':True
                                             ,'validation_min_float_value':numberMin or 0.0,'validation_max_float_value':numberMax or 0.0})
                            if question['type'] == 'list':
                                vals.update({'question_type': 'simple_choice'})
                            answer_lines = question['values']
                            if check_quote_question:
                                quote_question = check_quote_question.write(vals)
                                if check_quote_question.labels_ids:
                                    for quote_labels in check_quote_question.labels_ids:
                                        quote_labels.sudo().unlink()
                            else:
                                quote_question = self.env['team.quote.question'].create(vals)
                            if answer_lines:
                                quote_label_obj = self.env['team.quote.label']
                                for answer_line in answer_lines:
                                    if answer_line['name']:
                                        vals = {
                                                'question_id':check_quote_question.id if check_quote_question else quote_question.id,
                                                'value': answer_line['name'],
                                                'answer_score': answer_line['amount'] if 'amount' in answer_line and answer_line['amount'] else 0,
                                                }
                                        quote_label_obj.create(vals)
                all_questions = self.env['team.quote.question'].search([])
                for all_question in all_questions:
                    if all_question.code not in question_list:
                        all_question.active = False
        except requests.HTTPError:
            raise UserError(_("Something went wrong while Fetching Product Data."))


    def get_sales_appointment_api(self):
        configurations = self.env['team.improveit.configuration'].search([('api_type', '=', 'boomi')])
        for record in configurations:
            end_point_url = record.token_url
            client_token = record.client_token
            update_existing_record = record.update_existing_record
            if end_point_url and client_token:
                url = end_point_url + 'GetSalesAppointments' + client_token
                headers = {"Content-type": 'application/json'}
                res_users = self.env['res.users'].search([('improveit_user_id','!=',False)])
                for res_user in res_users:
                    if res_user.improveit_user_id:
                        data = {
                            "SalespersonID": res_user.improveit_user_id
                        }

                        try:
                            req = requests.post(url, data=json.dumps(data), headers=headers, timeout=TIMEOUT, verify=configurations.enable_ssl)
                            req.raise_for_status()
                            content = req.json()

                            for appointment in content:

                                appointments = self.env['team.customer.appointment'].search(
                                    [('improveit_appointment_id', '=', appointment['AppointmentID'])], limit=1)
                                if appointments and appointments.sale_order_ids:
                                    if appointments.sale_order_ids.filtered(lambda x: x.state in ['sale', 'done']):
                                        appointments = False
                                date = appointment['AppointmentDate'].split()
                                appointment_date_str = '%s %s' % (date[0], date[1])
                                date_obj = datetime.strptime(date[0], '%Y%m%d')
                                partner = self.env['res.partner'].search(
                                    [('name', '=', appointment.get('ProspectName','')), (('email', '=', appointment.get('ProspectEmail', '')))], limit=1)
                                applicant_name_split = self.split_name(appointment['ProspectName'])
                                str1= appointment['AppointmentTime']
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
                                # else:
                                #     appointment_date = appointment_date.strftime('%Y-%m-%d %H:%M:%S')
                                state = self.env['res.country.state'].search(
                                    [('country_id', '=', 233), ('code', '=', appointment.get('ProspectState', ''))],
                                    limit=1)
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

                                    }
                                    appointment_obj = self.env['team.customer.appointment'].create(appointment_values)
                                    if market_segment and not office_location_id:
                                        appointment_obj.message_post(
                                            body='Office Location is not found for Market Segment %s' % (
                                                market_segment))
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

                                    }
                                    appointments.write(appointment_values)
                                    if market_segment and not office_location_id:
                                        appointments.message_post(
                                            body='Office Location is not found for Market Segment %s' % (
                                                market_segment))

                        except IOError:
                            error_msg = _("Something went wrong during token generation.")
                            raise self.env['res.config.settings'].get_config_warning(error_msg)

    def get_products_api(self):
        configurations = self.env['team.improveit.configuration'].search([('api_type', '=', 'boomi')])
        if configurations:
            end_point_url = configurations.token_url
            client_token = configurations.client_token
            improveit_product_id_list = []
            if end_point_url and client_token:
                url = end_point_url + 'GetProducts' + client_token
                headers = {"Content-type": "application/json"}
                data = {}
                try:
                    req = requests.post(url, data=data, headers=headers, timeout=TIMEOUT, verify=configurations.enable_ssl)
                    req.raise_for_status()
                    content = req.json()
                    for product in content:
                        improveit_product_id = product['ProductID'] if product.get('ProductID') else ''
                        if improveit_product_id and improveit_product_id not in improveit_product_id_list:
                            improveit_product_id_list.append(improveit_product_id)
                        name = product['ProductName'] if product.get('ProductName') else ''
                        price = product['Price'] if product.get('Price') else ''
                        payment_plan = product['SubTitle'] if product.get('SubTitle') else ''
                        description = product['Description'] if product.get('Description') else ''
                        warranty_info = product['WarrantyInfo'] if product.get('WarrantyInfo') else ''
                        min_sale_price = product['MinimumDiscountedPrice'] if product.get('MinimumDiscountedPrice') else 0
                        msrp = product['MSRP'] if product.get('MSRP') else ''
                        elgible_discount = product['EligibleForAllDiscounts'] if product.get('ProductID') else ''
                        unit_of_measure = product['UnitOfMeasure'] if product.get('ProductID') else ''
                        sequence = product.get('DisplayOrder', 0) and int(product.get('DisplayOrder', 0)) or 0
                        available_colors=[]
                        category_name = product.get('Category', '')
                        grade = product.get('Grade', '')
                        category = False
                        if category_name:
                            category = self.env['product.category'].search([('name', '=', category_name)], limit=1)
                            if not category:
                                category = self.env['product.category'].create({'name': category_name})
                                _logger.info('----New Category %s is created-----'%category_name)
                        if product.get('AvailableColors'):
                            available_colors = product['AvailableColors'].split(';')
                        # available_colors = self.env['floor.color'].search([])
                        product_template = self.env['product.template'].search(
                            [('improveit_product_id', '=', improveit_product_id)])
                        if product_template:
                            product_template_values = {
                                'name': name,
                                'improveit_product_id': improveit_product_id,
                                'type': 'consu',
                                'list_price': price,
                                'payment_plan': payment_plan,
                                'description': description,
                                'warranty_info': warranty_info,
                                'min_sale_price': float(min_sale_price),
                                'msrp': msrp,
                                'unit_of_measure': unit_of_measure,
                                'eligible_for_discounts': elgible_discount,
                                'sequence': sequence,
                                'grade': grade,
                                'is_material': True,

                            }
                            if category:
                                product_template_values.update({'categ_id': category.id})
                            product_template.write(product_template_values)
                            product_attribute = self.env['product.attribute'].search([('name', '=', 'colour')], limit=1)
                            if not product_attribute:
                                product_attribute_vals = {
                                    'name': 'colour'
                                }
                                product_attribute = self.env['product.attribute'].create(product_attribute_vals)
                            if available_colors:
                                attribute_value_id_list = []
                                for variant in available_colors:
                                    names = [value.name for value in product_attribute.value_ids]
                                    if variant not in names:
                                        new_attribute_value = {
                                            'name': variant,
                                            'attribute_id': product_attribute.id,
                                        }
                                        attribute_value_id = self.env['product.attribute.value'].create(
                                            new_attribute_value)
                                    attribute_value_id = self.env['product.attribute.value'].search(
                                        [('name', '=', variant),
                                         ('attribute_id', '=', product_attribute.id)],
                                        limit=1)
                                    attribute_value_id_list.append((attribute_value_id.id))
                                attribute_line = self.env['product.template.attribute.line'].search([('product_tmpl_id','=',product_template.id),('attribute_id','=',product_attribute.id)],limit=1)
                                if attribute_line:
                                    attribute_line.write({'value_ids':[(6, 0, attribute_value_id_list)]})

                        if not product_template:
                            product_template_values = {
                                'name': name,
                                'improveit_product_id': improveit_product_id,
                                'type': 'consu',
                                'list_price': price,
                                'payment_plan': payment_plan,
                                'description':description,
                                'warranty_info':warranty_info,
                                'msrp':msrp,
                                'unit_of_measure':unit_of_measure,
                                'eligible_for_discounts':elgible_discount,
                                'sequence': sequence,
                                'grade': grade,
                                'is_material': True,

                            }
                            if category:
                                product_template_values.update({'categ_id': category.id})
                            product_template = self.env['product.template'].create(product_template_values)
                            product_attribute = self.env['product.attribute'].search([('name', '=', 'colour')], limit=1)
                            if not product_attribute:
                                product_attribute_vals = {
                                    'name': 'colour'
                                }
                                product_attribute = self.env['product.attribute'].create(product_attribute_vals)
                            if available_colors:
                                attribute_value_id_list = []
                                for variant in available_colors:
                                    names = [value.name for value in product_attribute.value_ids]
                                    if variant not in names:
                                        new_attribute_value = {
                                            'name': variant,
                                            'attribute_id': product_attribute.id,
                                        }
                                        attribute_value_id = self.env['product.attribute.value'].create(
                                            new_attribute_value)
                                    attribute_value_id = self.env['product.attribute.value'].search(
                                        [('name', '=', variant),
                                         ('attribute_id', '=', product_attribute.id)],
                                        limit=1)
                                    attribute_value_id_list.append((attribute_value_id.id))
                                attribute_line = self.env['product.template.attribute.line']
                                attribute_line_vals = {
                                    'product_tmpl_id': product_template.id,
                                    'attribute_id': product_attribute.id,
                                    'value_ids': [(6, 0, attribute_value_id_list)],
                                }
                                attribute_line.create(attribute_line_vals)
                    if improveit_product_id_list:
                        product_template_ids = self.env['product.template'].search(
                            [('improveit_product_id', '!=', False), ('improveit_product_id', 'not in', improveit_product_id_list)])
                        if product_template_ids:
                            product_template_ids.write({'active': False})
                except IOError:
                    error_msg = _("Something went wrong during token generation.")
                    raise self.env['res.config.settings'].get_config_warning(error_msg)

    def get_rooms_api(self):
        configurations = self.env['team.improveit.configuration'].search([('api_type', '=', 'boomi')])
        if configurations:
            end_point_url = configurations.token_url
            client_token = configurations.client_token
            if end_point_url and client_token:
                url = end_point_url + 'GetRoomNames' + client_token
                headers = {"Content-type": "application/json"}
                data = {}
                try:
                    req = requests.get(url, data=data, headers=headers, timeout=TIMEOUT, verify=configurations.enable_ssl)
                    req.raise_for_status()
                    content = req.json()
                    room_name_list = []
                    product_category_dict = {}
                    for room in content:
                        if room.get('ProductCategory', False) and room.get('ProductCategory', False) not in product_category_dict:
                            product_category = self.env['product.category'].search([('name', '=', room.get('ProductCategory', False))], limit=1)
                            if not product_category:
                                product_category = self.env['product.category'].create({'name': room.get('ProductCategory', False)})
                            product_category_dict.update({
                                room.get('ProductCategory', False): product_category.id
                            })

                    for room in content:
                        if room.get('Name',False) and room.get('ProductCategory', False):
                            room_dict = {
                                'name': room.get('Name', False),
                                'active': True,
                                'product_category_id': product_category_dict.get(room.get('ProductCategory', False), 0),
                            }
                            room_name_list.append(room.get('Name',False))
                            duplicate_room = self.env['team.room.room'].with_context(active_test=False).search([('name','=',room.get('Name',False))],limit=1)
                            if not duplicate_room:
                                self.env['team.room.room'].create(room_dict)
                            if duplicate_room:
                                duplicate_room.write(room_dict)
                    unused_rooms = self.env['team.room.room'].search([('name', 'not in', room_name_list), ('is_custom', '!=', True)])
                    if unused_rooms:
                        unused_rooms.write({'active': False})
                except IOError:
                    error_msg = _("Something went wrong during token generation.")
                    raise self.env['res.config.settings'].get_config_warning(error_msg)

    def get_payment_options(self):
        configurations = self.env['team.improveit.configuration'].search([('api_type', '=', 'boomi')])
        if configurations:
            end_point_url = configurations.token_url
            client_token = configurations.client_token
            if end_point_url and client_token:
                url = end_point_url + 'GetFinanceOptions' + client_token
                req = requests.get(url, verify=configurations.enable_ssl)
                req.raise_for_status()
                tree = ElementTree(fromstring(req.content))
                root = tree.getroot()
                payment_list = []
                payment_options_list = []
                for child_of_root in root:
                    finance_dict = {}
                    for child in child_of_root:
                        if child.text is not None:
                            finance_dict[child.tag] = child.text

                    payment_list.append(finance_dict)
                for payment_option in payment_list:
                    if payment_option.get('Name', False):
                        payment_options_list.append(payment_option.get('Name', False))
                        down_payment_message = payment_option.get('Down_Payment_Message__c', '')
                        if down_payment_message == 'false':
                            down_payment_message = ''
                        start_date = payment_option.get('Start_Date__c') if payment_option.get(
                            'Start_Date__c') else False
                        end_date = payment_option.get('End_Date__c') if payment_option.get('End_Date__c') else False
                        if start_date:
                            start_date = datetime.strptime(start_date, '%Y-%m-%d')
                        if end_date:
                            end_date = datetime.strptime(end_date, '%Y-%m-%d')
                        duplicate_payment_option = self.env['team.downpayment.option'].with_context(
                            active_test=False).search([('name', '=', payment_option.get('Name', False))], limit=1)
                        if not duplicate_payment_option:
                            payment_dict = {
                                'name': payment_option.get('Name', False),
                                'description': payment_option.get('Description__c', False),
                                'down_payment': payment_option.get('Down_Payment__c', False),
                                'final_payment': payment_option.get('Final_Payment__c', False),
                                'payment_factor': payment_option.get('Payment_Factor__c', False),
                                'secondary_payment_factor': payment_option.get('Secondary_Payment_Factor__c', '0'),
                                'balance_due': payment_option.get('Balance_Due__c', False),
                                'sequence': payment_option.get('Display_Order__c', False),
                                'payment_info': payment_option.get('Payment_Info__c', ''),
                                'down_payment_message': down_payment_message,
                                'start_date': start_date,
                                'end_date': end_date,
                            }
                            self.env['team.downpayment.option'].create(payment_dict)
                        if duplicate_payment_option and duplicate_payment_option.active == True:
                            payment_dict = {
                                'name': payment_option.get('Name', False),
                                'description': payment_option.get('Description__c', False),
                                'down_payment': payment_option.get('Down_Payment__c', False),
                                'final_payment': payment_option.get('Final_Payment__c', False),
                                'payment_factor': payment_option.get('Payment_Factor__c', False),
                                'secondary_payment_factor': payment_option.get('Secondary_Payment_Factor__c', '0'),
                                'balance_due': payment_option.get('Balance_Due__c', False),
                                'payment_info': payment_option.get('Payment_Info__c', ''),
                                'down_payment_message': down_payment_message,
                                'sequence': payment_option.get('Display_Order__c', False),
                                'start_date': start_date,
                                'end_date': end_date,
                            }
                            duplicate_payment_option.write(payment_dict)
                        if duplicate_payment_option and duplicate_payment_option.active == False:
                            duplicate_payment_option.active = True
                            payment_dict = {
                                'name': payment_option.get('Name', False),
                                'description': payment_option.get('Description__c', False),
                                'down_payment': payment_option.get('Down_Payment__c', False),
                                'final_payment': payment_option.get('Final_Payment__c', False),
                                'payment_factor': payment_option.get('Payment_Factor__c', False),
                                'secondary_payment_factor': payment_option.get('Secondary_Payment_Factor__c', '0'),
                                'balance_due': payment_option.get('Balance_Due__c', False),
                                'sequence': payment_option.get('Display_Order__c', False),
                                'down_payment_message': down_payment_message,
                                'start_date': start_date,
                                'end_date': end_date,
                            }
                            duplicate_payment_option.write(payment_dict)
                unused_payment_options = self.env['team.downpayment.option'].search(
                    [('name', 'not in', payment_options_list)])
                if unused_payment_options:
                    unused_payment_options.write({'active': False})
        return True

    def get_discount_coupons(self):
        configurations = self.env['team.improveit.configuration'].search([('api_type', '=', 'boomi')])
        if configurations:
            end_point_url = configurations.token_url
            client_token = configurations.client_token
            if end_point_url and client_token:
                url = end_point_url + 'GetDiscountCodes' + client_token
                discount_coupon_list = []
                list_discount_coupon = []
                req = requests.get(url, verify=configurations.enable_ssl)
                req.raise_for_status()
                content = req.json()
                for discount_codes in content:
                    discount_coupon_list.append(discount_codes)
                for discount_coupon in discount_coupon_list:
                    discount_code = discount_coupon.get('Code', '')
                    if discount_code:
                        list_discount_coupon.append(discount_code)
                        duplicate_discount_coupon = self.env['team.monthly.promo'].with_context(
                            active_test=False).search([('code', '=', discount_code)], limit=1)
                        thumb_nail = discount_coupon.get('ImageURL') or ''
                        image_binary = False
                        if thumb_nail:
                            image_url = "https://refloormichigan.com/DiscountImages/%s" % (thumb_nail)
                            try:
                                image_data = urlopen(image_url).read()
                                image_binary = base64.encodestring(image_data)
                            except:
                                image_binary = False
                        discount_coupon_dict = {
                            'name': discount_coupon.get('DisplayName', '') or discount_code,
                            'code': discount_code,
                            'amount': discount_coupon.get('Amount', False),
                            'type': discount_coupon.get('Type', False),
                            'active': True
                        }
                        if image_binary:
                            if duplicate_discount_coupon and duplicate_discount_coupon.attachment_id:
                                attachment = duplicate_discount_coupon.attachment_id
                                attachment.sudo().write({
                                    'datas': image_binary,
                                    'name': thumb_nail
                                })
                            else:
                                attachment = self.env['ir.attachment'].sudo().create({
                                    'datas': image_binary,
                                    'name': thumb_nail

                                })
                            attachment.generate_access_token()
                            discount_coupon_dict.update({
                                'attachment_id': attachment.id
                            })
                        if not duplicate_discount_coupon:
                            self.env['team.monthly.promo'].create(discount_coupon_dict)
                        else:
                            duplicate_discount_coupon.write(discount_coupon_dict)
                unused_discount_coupons = self.env['team.monthly.promo'].search([('code', 'not in', list_discount_coupon)])
                if unused_discount_coupons:
                    unused_discount_coupons.write({'active': False})


    def get_appointment_result(self):
        configurations = self.env['team.improveit.configuration'].search([('api_type', '=', 'boomi')])
        if configurations:
            end_point_url = configurations.token_url
            client_token = configurations.client_token
            if end_point_url and client_token:
                url = end_point_url + 'GetAppointmentResults' + client_token
                appointment_result_list = []
                list_appointment_result = []
                req = requests.get(url, verify=configurations.enable_ssl)
                req.raise_for_status()
                content = req.json()
                for appointment_result in content:
                    appointment_result_list.append(appointment_result)
                for result_data in appointment_result_list:
                    if result_data.get('Result', False):
                        list_appointment_result.append(result_data.get('Result', False))
                        duplicate_appointment_result = self.env['appointment.result'].with_context(
                            active_test=False).search([('result', '=', result_data.get('Result', False))], limit=1)
                        if not duplicate_appointment_result:
                            appointment_result_dict = {
                                'result': result_data.get('Result', ''),
                                'last_available_screen': result_data.get('LastAvailableScreen', ''),
                            }
                            self.env['appointment.result'].create(appointment_result_dict)
                        if duplicate_appointment_result and duplicate_appointment_result.active == True:
                            appointment_result_dict = {
                                'result': result_data.get('Result', ''),
                                'last_available_screen': result_data.get('LastAvailableScreen', ''),
                            }
                            duplicate_appointment_result.write(appointment_result_dict)
                        if duplicate_appointment_result and duplicate_appointment_result.active == False:
                            duplicate_appointment_result.active = True
                            appointment_result_dict = {
                                'result': result_data.get('Result', ''),
                                'last_available_screen': result_data.get('LastAvailableScreen', ''),
                            }
                            duplicate_appointment_result.write(appointment_result_dict)
                unused_appointment_results = self.env['appointment.result'].search([('result', 'not in', list_appointment_result)])
                if unused_appointment_results:
                    unused_appointment_results.write({'active': False})

    def get_molding_types(self):
        configurations = self.env['team.improveit.configuration'].search([('api_type', '=', 'boomi')])
        if configurations:
            _logger.info('------Starting Molding Type Sync')
            end_point_url = configurations.token_url
            client_token = configurations.client_token
            if end_point_url and client_token:
                url = end_point_url + 'GetMoldingTypes' + client_token
                molding_type_list = []
                list_molding_type = []
                req = requests.get(url, verify=configurations.enable_ssl)
                req.raise_for_status()
                content = req.json()
                for molding_type in content:
                    molding_type_list.append(molding_type)
                sequence = 1
                for result_data in molding_type_list:
                    if result_data.get('Name', False):
                        molding_type_dict = {
                            'name': result_data.get('Name', False),
                            'sequence': sequence,
                            'active': True,
                            'unit_price': result_data.get('PricePerUnit', 0),
                            'default_delivery': result_data.get('DefaultDelivery', '')
                        }
                        sequence += 1
                        list_molding_type.append(result_data.get('Name', False))
                        molding_type = self.env['team.floor.molding'].with_context(
                            active_test=False).search([('name', '=', result_data.get('Name', False))], limit=1)
                        if not molding_type:
                            molding_type = self.env['team.floor.molding'].create(molding_type_dict)
                            _logger.info('----New Molding Created: %s'%result_data.get('Name', False))
                        else:
                            molding_type.write(molding_type_dict)
                        if molding_type:
                            delivery_options_list = result_data.get('DeliveryOptions')
                            if delivery_options_list:
                                for delivery_option in delivery_options_list:
                                    option_line = self.env['otl.delivery.option.line'].search([
                                        ('molding_type_id', '=', molding_type.id),
                                        ('name', '=', delivery_option)
                                    ])
                                    if not option_line:
                                        self.env['otl.delivery.option.line'].create({
                                            'name': delivery_option,
                                            'molding_type_id': molding_type.id
                                        })
                unused_molding_types = self.env['team.floor.molding'].search([('name', 'not in', list_molding_type)])
                if unused_molding_types:
                    unused_molding_types.write({'active': False})

    def is_valid_url_image(self, image_url):
        try:
            image = Image.open(requests.get(image_url, stream=True).raw)
        except:
            return False
        return image

    def get_office_locations(self):
        location_data = {}
        locations = self.env['otl.office.location'].search([])
        for location in locations:
            location_data.update({
                location.name: location.id
            })
        return location_data

    def get_floor_color_api(self):
        configurations = self.env['team.improveit.configuration'].search([('api_type', '=', 'boomi')])
        if configurations:
            end_point_url = configurations.token_url
            client_token = configurations.client_token
            if end_point_url and client_token:
                url = end_point_url + 'GetFlooringColors' + client_token
                headers = {"Content-type": "application/json"}
                data = {}
                try:
                    req = requests.get(url, data=data, headers=headers, timeout=TIMEOUT, verify=configurations.enable_ssl)
                    req.raise_for_status()
                    content = req.json()
                    location_dict = self.get_office_locations()
                    floor_color_list = []
                    for color in content:
                        name = color.get('name') or ''
                        display_name_in_app = color.get('salesAppDisplayName') or color.get('name') or ''
                        product_lines = color.get('productLines', '') or color.get('ProductLines', '') or ''
                        color_up_charge_price = color.get('colorUpcharge', 0) or 0
                        in_stock = color.get('inStock', False) or False
                        glue_down = color.get('glueDown', False) or False
                        special_order = color.get('specialOrder', False) or False
                        market_segments = color.get('marketSegment', '') or ''
                        office_location_ids = []
                        if market_segments:
                            market_segment_list = market_segments.split(';')
                            for market_segment in market_segment_list:
                                if market_segment not in location_dict:
                                    location_id = self.env['otl.office.location'].create({
                                        'name': market_segment
                                    })
                                    location_dict.update({
                                        market_segment: location_id.id
                                    })
                                office_location_ids.append(location_dict.get(market_segment, 0))
                        if product_lines:
                            thumb_nail = color.get('thumbnail') or ''
                            image_url = ''
                            if thumb_nail:
                                image_url = "https://refloormichigan.com/FlooringThumbs/%s"%(thumb_nail)
                            _logger.info('image_url: %s'%image_url)
                            image_data = self.is_valid_url_image(image_url)
                            image_binary = False
                            if image_data:
                                try:
                                    image_data = urlopen(image_url).read()
                                    # image_binary = base64.encodestring(image_data)
                                    image_binary = base64.b64encode(image_data)
                                except:
                                    image_binary = False
                            else:
                                image_url = ''
                            product_line_template = product_lines.split(';')
                            products = self.env['product.product'].search([('product_tmpl_id.grade', 'in', product_line_template)])
                            floor_color = self.env['floor.color'].with_context(active_test=False).search([('name', '=', name)], limit=1)
                            floor_color_vals = {
                                'name': name,
                                'product_line': product_lines,
                                'thumb_nail': thumb_nail,
                                'url': image_url,
                                'color_up_charge_price': color_up_charge_price,
                                'display_name_in_app': display_name_in_app,
                                'in_stock': in_stock,
                                'glue_down': glue_down,
                                'special_order': special_order,
                                'office_location_ids': [(6, 0, office_location_ids)],
                                'active': True
                            }
                            if floor_color:
                                self.env['floor.color'].write(floor_color_vals)
                            else:
                                floor_color= self.env['floor.color'].create(floor_color_vals)
                            if floor_color.id not in floor_color_list:
                                floor_color_list.append(floor_color.id)
                            for product in products:
                                if product.product_template_attribute_value_ids.filtered(lambda x: x.name == name and x.attribute_id.name == 'colour'):
                                    attachment = False
                                    product.write({
                                        'floor_color': name,
                                        'product_line': product_lines,
                                        'thumb_nail': thumb_nail,
                                        'url': image_url,
                                        'color_up_charge_price': color_up_charge_price,
                                        'display_name_in_app': display_name_in_app,
                                        'image_variant_1920': image_binary,
                                        'in_stock': in_stock,
                                        'glue_down': glue_down,
                                        'special_order': special_order,
                                        'office_location_ids': [(6, 0, office_location_ids)]
                                    })
                                    if product.color_attachment_id:
                                        if not product.image_variant_128:
                                            product.color_attachment_id.unlink()
                                        else:
                                            attachment = product.color_attachment_id
                                            attachment.sudo().write({
                                                'datas': product.image_variant_128,
                                                'name': thumb_nail
                                            })
                                    else:
                                        attachment = self.env['ir.attachment'].sudo().create({
                                            'datas': product.image_variant_128,
                                            'name': thumb_nail

                                        })
                                    product.write({'color_attachment_id': attachment and attachment.id or False})
                                    floor_color_line = self.env['floor.color.line'].search([
                                        ('floor_color_id', '=', floor_color.id),
                                        ('product_id', '=', product.id)
                                    ])
                                    if not floor_color_line:
                                        self.env['floor.color.line'].create({
                                            'floor_color_id': floor_color.id,
                                            'product_id': product.id,
                                        })
                    archive_floor_colors = self.env['floor.color'].search([('id', 'not in', floor_color_list)])
                    for floor_color in archive_floor_colors:
                        floor_color.write({'active': False})
                except IOError:
                    error_msg = _("Something went wrong during token generation.")
                    raise self.env['res.config.settings'].get_config_warning(error_msg)

    def get_resision_date(self):
        configurations = self.env['team.improveit.configuration'].search([('api_type', '=', 'boomi')])
        if configurations:
            end_point_url = configurations.token_url
            client_token = configurations.client_token
            if end_point_url and client_token:
                url = end_point_url + 'GetRecisionDate' + client_token
                req = requests.get(url, verify=configurations.enable_ssl)
                req.raise_for_status()
                content = req.json()
                if content.get('RecisionDate', False):
                    recesion_date = datetime.strptime(content.get('RecisionDate', False), '%m/%d/%Y').strftime(
                        '%Y-%m-%d')
                    self.env.user.company_id.recision_date =  recesion_date



    def get_question_data_api(self):
        configurations = self.env['team.improveit.configuration'].search([('api_type', '=', 'boomi')])
        if configurations:
            end_point_url = configurations.token_url
            client_token = configurations.client_token
            if end_point_url and client_token:
                _logger.info('-------Starting Question Sync----------')
                url = end_point_url + 'GetQuestionaireQuestions' + client_token
                headers = {"Content-type": "application/json"}
                data = {}
                try:
                    req = requests.get(url, data=data, headers=headers, timeout=TIMEOUT, verify=configurations.enable_ssl)
                    req.raise_for_status()
                    content = req.json()
                    question_list = []
                    product_category_dict = {}
                    for room in content:
                        if room.get('ProductCategories', False) and room.get('ProductCategories',
                                                                           False) not in product_category_dict:
                            category_name = room.get('ProductCategories', False)
                            category_ids = []
                            if ';' in category_name:
                                category_name_list = category_name.split(';')
                                for category in category_name_list:
                                    product_category = self.env['product.category'].search(
                                        [('name', '=', category)], limit=1)
                                    if not product_category:
                                        product_category = self.env['product.category'].create(
                                            {'name': category})
                                    category_ids.append(product_category.id)
                            else:
                                product_category = self.env['product.category'].search(
                                    [('name', '=', category_name)], limit=1)
                                if not product_category:
                                    product_category = self.env['product.category'].create(
                                        {'name': category_name})
                                category_ids.append(product_category.id)
                            product_category_dict.update({
                                category_name: category_ids
                            })
                    for question in content:
                        room_list = []
                        answer_list = []
                        rooms = self.env['team.room.room'].search([])
                        for room in rooms:
                            room_list.append(room.id)
                        vals = {'active': True}
                        check_quote_question = self.env['team.quote.question'].with_context(active_test=False).search(
                            [('code', '=', question.get('ItemMapFieldName',''))], limit=1)
                        question_list.append(question.get('ItemMapFieldName',''))
                        vals.update({'name': question.get('QuestionText','')})
                        vals.update({'code': question.get('ItemMapFieldName','')})
                        vals.update({'show_in_measurement': True})
                        vals.update({'show_in_contract': True})
                        reflect_cost = False
                        multiply_with_area = False
                        calculation_type = 'unit'
                        if question.get('UnitOfMeasure', '') == 'Per Room':
                            calculation_type = 'fixed'
                        elif question.get('UnitOfMeasure', '') in ['Sqft', 'Layers']:
                            calculation_type = 'sqft'
                            if question.get('UnitOfMeasure', '') == 'Layers':
                                multiply_with_area=True
                        vals.update({
                            'calculation_type': calculation_type,
                            'multiply_with_area': multiply_with_area,
                            'sequence': int(question.get('DisplayOrder', 0)),
                            'amount_included': float(question.get('AmountIncluded', 0))
                        })
                        exclude_from_discount = False
                        if question.get('ExcludeFromDiscount', False) in ['true', True]:
                            exclude_from_discount = True
                        vals.update({'exclude_from_discount': exclude_from_discount})

                        exclude_from_promotion = False
                        if question.get('ExcludeFromPromotion', False) in ['true', True]:
                            exclude_from_promotion = True
                        vals.update({'exclude_from_promotion': exclude_from_promotion})

                        if question.get('Price', 0):
                            reflect_cost = True
                        vals.update({'amount': question.get('Price', 0)})
                        if question.get('Required', False):
                            vals.update({'constr_mandatory': True})
                        else:
                            vals.update({'constr_mandatory': False})
                        vals.update({'room_ids': [(6, 0, room_list)]})
                        if question.get('ProductCategories', False):
                            vals.update({
                                'product_category_ids': product_category_dict.get(question.get('ProductCategories', False), [])
                            })
                        if question.get('Type','') == 'List':
                            answer_list = question.get('Values','').split("\n")
                            vals.update({'question_type':'simple_choice'})
                            if question.get('LaborChargeUnits',''):
                                vals.update({'labor_charge_units': question.get('LaborChargeUnits','')})
                            if question.get('LaborCharge',''):
                                vals.update({'amount': question.get('LaborCharge','')})
                                vals.update({'calculation_type': question.get('fixed', '')})
                        if question.get('Type','') == 'Boolean':
                            vals.update({'question_type': 'simple_choice'})
                            if question.get('LaborChargeUnits',''):
                                vals.update({'labor_charge_units': question.get('LaborChargeUnits','')})
                            if question.get('LaborCharge',''):
                                vals.update({'amount': question.get('LaborCharge','')})
                                vals.update({'calculation_type': question.get('fixed', '')})
                        if question.get('Type', '') == 'Integer':
                            vals.update({'question_type': 'numerical_box',
                                         'validation_required': True
                                         })
                            if question.get('LaborChargeUnits',''):
                                vals.update({'labor_charge_units': question.get('LaborChargeUnits','')})
                            if question.get('LaborCharge',''):
                                vals.update({'amount': question.get('LaborCharge','')})
                                vals.update({'calculation_type': question.get('fixed', '')})
                        vals.update({'reflect_cost': reflect_cost})
                        if check_quote_question:
                            check_quote_question.write(vals)

                        else:
                            check_quote_question = self.env['team.quote.question'].create(vals)

                        if answer_list or question.get('Type','') == 'Boolean':
                            quote_label_obj = self.env['team.quote.label']
                            if question.get('Type','') == 'Boolean':
                                answer_list = ['Yes','No']
                            updated_answer_lines = []
                            for answer_line in answer_list:
                                answer_line_value = ''
                                answer_line_score = 0
                                if ';' in answer_line:
                                    answer_line_list = answer_line.split(';')
                                    if answer_line_list and answer_line_list[1]:
                                        reflect_cost = True
                                    answer_line_value = answer_line_list[0]
                                    answer_line_score = float(answer_line_list[1]) or 0
                                else:
                                    answer_line_value = answer_line
                                existing_answer_line = check_quote_question.labels_ids.filtered(lambda x: x.value == answer_line_value)
                                if existing_answer_line:
                                    if existing_answer_line[0].answer_score != answer_line_score:
                                        existing_answer_line[0].write({'answer_score': answer_line_score})
                                else:
                                    vals = {
                                        'question_id': check_quote_question.id,
                                        'value': answer_line_value,
                                        'answer_score': answer_line_score,
                                    }
                                    quote_label_obj.create(vals)
                                updated_answer_lines.append(answer_line_value)
                            existing_answer_line = check_quote_question.labels_ids.filtered(lambda x: x.value not in updated_answer_lines)
                            if existing_answer_line:
                                existing_answer_line.sudo().unlink()
                            check_quote_question.write({'reflect_cost': reflect_cost})
                        else:
                            if check_quote_question.labels_ids:
                                for quote_labels in check_quote_question.labels_ids:
                                    quote_labels.sudo().unlink()
                        not_used_questions = self.env['team.quote.question'].search([('code', 'not in', question_list)])
                        if not_used_questions:
                            not_used_questions.write({'active': False})


                except IOError:
                    error_msg = _("Something went wrong during token generation.")
                    raise self.env['res.config.settings'].get_config_warning(error_msg)

    def get_special_pricing_api(self):
        configurations = self.env['team.improveit.configuration'].search([('api_type', '=', 'boomi')])
        if configurations:
            end_point_url = configurations.token_url
            client_token = configurations.client_token
            if end_point_url and client_token:
                url = end_point_url + 'GetSpecialPricing' + client_token
                headers = {"Content-type": "application/json"}
                data = {}
                try:
                    req = requests.get(url, data=data, headers=headers, timeout=TIMEOUT, verify=configurations.enable_ssl)
                    req.raise_for_status()
                    content = req.json()
                    special_price_list = []
                    for special_price in content:
                        office_location_improveit_id = special_price.get('OfficeId', '')
                        office_location_name = special_price.get('Office', '')
                        improveit_product_id = special_price.get('ProductId', '')
                        start_date = special_price.get('Start_Date', '')
                        end_date = special_price.get('End_Date', '')
                        name = special_price.get('Name', '')
                        price = special_price.get('Price', 0)
                        msrp = special_price.get('MSRP', 0)
                        max_discount = special_price.get('MaxDiscount', 0)
                        office_location = self.env['otl.office.location'].with_context(active_test=False).search(['|', ('name', '=', office_location_name), ('improveit_id', '=', office_location_improveit_id)], limit=1)
                        if not office_location:
                            office_location = self.env['otl.office.location'].create({
                                'name': office_location_name,
                                'improveit_id': office_location_improveit_id
                            })
                        if not office_location.active:
                            office_location.write({'active': True})
                        product_tmpl = self.env['product.template'].search([('improveit_product_id', '=', improveit_product_id)], limit=1)
                        if product_tmpl:
                            special_price_obj = self.env['otl.product.special.price'].search([
                                ('office_location_id.improveit_id', '=', office_location.id),
                                ('product_tmpl_id.improveit_product_id', '=', improveit_product_id),
                                ('start_date', '=', start_date),
                                ('end_date', '=', end_date),
                            ])
                            vals = {
                                'product_tmpl_id': product_tmpl.id,
                                'start_date': datetime.strptime(start_date, '%m/%d/%Y').strftime(DEFAULT_SERVER_DATE_FORMAT),
                                'end_date': datetime.strptime(end_date, '%m/%d/%Y').strftime(DEFAULT_SERVER_DATE_FORMAT),
                                'name': name,
                                'list_price': price,
                                'msrp': msrp,
                                'max_discount': max_discount,
                            }
                            if special_price_obj:
                                self.env['otl.product.special.price'].write(vals)
                            else:
                                vals.update({
                                    'office_location_id': office_location.id,
                                })
                                special_price_obj = self.env['otl.product.special.price'].create(vals)
                            if special_price_obj.id not in special_price_list:
                                special_price_list.append(special_price_obj.id)
                    inactive_special_price = self.env['otl.product.special.price'].search([('id', 'not in', special_price_list)])
                    if inactive_special_price:
                        inactive_special_price.write({'active': False})

                except IOError:
                    error_msg = _("Something went wrong during token generation.")
                    raise self.env['res.config.settings'].get_config_warning(error_msg)

    def get_promocode_api(self):
        configurations = self.env['team.improveit.configuration'].search([('api_type', '=', 'boomi')])
        if configurations:
            end_point_url = configurations.token_url
            client_token = configurations.client_token
            if end_point_url and client_token:
                url = end_point_url + 'GetPromotions' + client_token
                headers = {"Content-type": "application/json"}
                data = {}
                try:
                    req = requests.get(url, data=data, headers=headers, timeout=TIMEOUT, verify=configurations.enable_ssl)
                    req.raise_for_status()
                    content = req.json()
                    promocode_list = []
                    promocode_obj = self.env['otl.promotion.code']
                    user = self.env.user
                    tz = user.tz and pytz.timezone(user.tz) or pytz.utc
                    for data in content:
                        start_date_str = data.get('BeginDate', '')
                        end_date_str = data.get('EndDate', '')
                        name = data.get('Promotion', '')
                        price = 0
                        calculation_type = 'sqft'
                        promotion_type = data.get('PromotionType', 'Sqft')
                        discount_sqft = data.get('DiscountSqft', 0)
                        discount_perc = data.get('DiscountPercentage', 0)
                        discount_fixed = data.get('DiscountFixedDollars', 0)
                        if promotion_type == 'Sqft':
                            calculation_type = 'sqft'
                            price = discount_sqft
                        elif promotion_type == 'Percent':
                            calculation_type = 'percentage'
                            price = discount_perc
                        elif promotion_type == 'Dollars':
                            calculation_type = 'fixed'
                            price = discount_fixed
                        promocode = promocode_obj.search([('name', '=', name)], limit=1)
                        if 'T' in start_date_str:
                            start_date_obj = datetime.strptime(start_date_str, '%Y-%m-%dT%H:%M:%S')
                            end_date_obj = datetime.strptime(end_date_str, '%Y-%m-%dT%H:%M:%S')
                            start_date = start_date_obj.strftime('%Y-%m-%d')
                            end_date = end_date_obj.strftime('%Y-%m-%d')
                        else:
                            start_date = start_date_str
                            end_date = end_date_str
                        vals= {
                            'start_date': start_date,
                            'end_date': end_date,
                            'name': name,
                            'discount': price,
                            'calculation_type': calculation_type,
                        }
                        if promocode:
                            promocode.write(vals)
                        else:
                            promocode = promocode_obj.create(vals)
                        promocode_list.append(promocode.id)
                    inactive_promocode = promocode_obj.search([('id', 'not in', promocode_list)])
                    if inactive_promocode:
                        inactive_promocode.write({'active': False})

                except IOError:
                    error_msg = _("Something went wrong during token generation.")
                    raise self.env['res.config.settings'].get_config_warning(error_msg)

    def get_appointment_result_detail_api(self):
        configurations = self.env['team.improveit.configuration'].search([('api_type', '=', 'boomi')])
        if configurations:
            end_point_url = configurations.token_url
            client_token = configurations.client_token
            if end_point_url and client_token:
                url = end_point_url + 'GetAppointmentResultDetails' + client_token
                headers = {"Content-type": "application/json"}
                data = {}
                try:
                    req = requests.get(url, data=data, headers=headers, timeout=TIMEOUT, verify=configurations.enable_ssl)
                    req.raise_for_status()
                    content = req.json()
                    reason_i360_ref_list = []
                    reason_obj = self.env['otl.appointment.result.reason']
                    sequence = 10
                    appointment_results = self.env['appointment.result'].search([])
                    reasons = reason_obj.search([])
                    if reasons:
                        reasons.write({'appointment_result_ids': [(6, 0, [])]})
                    content_data = {}
                    if content:
                        content_data = content[0]
                    for result in appointment_results:
                        for data in content_data.get(result.result, []):
                            # reference id is not passing in the latest change(Q4-2024)
                            # reference_id = data.get('Id', '')
                            values = {
                                'active': True,
                                'name': data,
                                # 'reference_id': reference_id,
                                'sequence': sequence,
                                'appointment_result_ids': [(4, result.id)]
                            }
                            reason_i360_ref_list.append(data)
                            reason = reason_obj.with_context(active_test=False).search([('name', '=', data)])
                            if reason:
                                reason.write(values)
                            else:
                                reason_obj.create(values)
                            sequence += 10
                    unwanted_reasons = reason_obj.search([('name', 'not in', reason_i360_ref_list)])
                    if unwanted_reasons:
                        unwanted_reasons.write({'active': False})
                except IOError:
                    error_msg = _("Something went wrong during GetAppointmentResultDetails API execution.")
                    raise self.env['res.config.settings'].get_config_warning(error_msg)
    
    def get_finance_order_checklist_api(self):
        configurations = self.env['team.improveit.configuration'].search([('api_type', '=', 'order_checklist')])
        if configurations:
            end_point_url = configurations.token_url
            client_token = configurations.client_token
            if end_point_url and client_token:
                url = end_point_url + 'GetArrivalCompletionChecklist' + client_token
                headers = {"Content-type": "application/json"}
                data = {}
                try:
                    req = requests.get(url, data=data, headers=headers, timeout=TIMEOUT, verify=configurations.enable_ssl)
                    req.raise_for_status()
                    content = req.json()
                    order_checklist = []
                    checklist_obj = self.env['otl.finance.checklist.items']
                    for data in content:
                        checklist_name = data.get('name', '')
                        sequence = data.get('display_Order')
                        vals = {
                            'name': checklist_name,
                            'sequence': sequence,
                            'active': True
                        }
                        if checklist_name:
                            checklist = checklist_obj.with_context(active_test=False).search([('name', '=', checklist_name)], limit=1)
                            if checklist:
                                checklist.write(vals)
                            else:
                                checklist = checklist_obj.create(vals)
                            order_checklist.append(checklist.id)
                    if order_checklist:
                        inactive_checklists = checklist_obj.search([('id', 'not in', order_checklist)])
                        if inactive_checklists:
                            inactive_checklists.write({'active': False})




                except IOError:
                    error_msg = _("Something went wrong during GetArrivalCompletionChecklist API execution.")
                    raise self.env['res.config.settings'].get_config_warning(error_msg)
    
    
    def action_sync_master_data(self, data={}):
        _logger.info('-------Starting: action_sync_master_data')
        for record in self.sudo().search([('api_type', '=', 'boomi')]):
            if record.sync_master_data_in_progress:
                current_date = datetime.now()
                time_after_last_execution = (current_date - record.write_date).total_seconds()
                print(time_after_last_execution)
                if int(time_after_last_execution) < 300:
                    _logger.info('-------Not Executed: action_sync_master_data')
                    return {
                        'result': 'success',
                        'message': "Master Data synchronized successfully",
                    }
            record.sudo().write({'sync_master_data_in_progress': True})
            record.env.cr.commit()
            _logger.info('-------Starting: get_products_api')
            record.sudo().get_products_api()
            _logger.info('-------Starting: get_question_data_api')
            record.sudo().get_question_data_api()
            _logger.info('-------Starting: get_rooms_api')
            record.sudo().get_rooms_api()
            _logger.info('-------Starting: get_floor_color_api')
            record.sudo().get_floor_color_api()
            _logger.info('-------Starting: get_payment_options')
            record.sudo().get_payment_options()
            _logger.info('-------Starting: get_discount_coupons')
            record.sudo().get_discount_coupons()
            _logger.info('-------Starting: get_appointment_result')
            record.sudo().get_appointment_result()
            _logger.info('-------Starting: get_molding_types')
            record.sudo().get_molding_types()
            _logger.info('-------Starting: get_resision_date')
            record.sudo().get_resision_date()
            _logger.info('-------Starting: get_special_pricing_api')
            record.sudo().get_special_pricing_api()
            _logger.info('-------Starting: get_promocode_api')
            record.sudo().get_promocode_api()
            _logger.info('-------Starting: get_appointment_result_detail_api')
            record.sudo().get_appointment_result_detail_api()
            record.sudo().write({'sync_master_data_in_progress': False})
            # record.env.cr.commit()
        _logger.info('-------Completed: action_sync_master_data')
        return {
            'result': 'success',
            'message': "Master Data synchronized successfully",
        }


class TeamCustomerAppointment(models.Model):
    _inherit = 'team.customer.appointment'

    improveit_appointment_id = fields.Char(string='i360 Appointment ID')

    _sql_constraints = [
        ('i360_id_uniq', 'unique (improveit_appointment_id)', "i360 Reference must be unique!"),
    ]

class Users(models.Model):
    _inherit = 'res.users'

    improveit_user_id = fields.Char(string='i360 Salesperson ID')
    restrict_geolocation = fields.Boolean('Restrict Geolocation Tracking', default=False)
    device_name = fields.Char(string='Device Name')
    device_os = fields.Char(string='Device OS')
    app_version = fields.Char(string='App Version')



# -*- coding: utf-8 -*-
# import xml.etree.ElementTree as ET
import re
from xml.etree.ElementTree import fromstring, ElementTree
from odoo import models, fields, api, _, registry
import json
import ast
from odoo.exceptions import UserError
from odoo.tools import format_date, str2bool
from odoo.addons.team_api_configuration.controllers.configurations import URL, DB, API_USER_ID, API_USER_PASSWORD
from odoo.http import request
from odoo.addons.payment_authorize.models.authorize_request import AuthorizeAPI
from datetime import datetime, timedelta
import requests
import pytz

TIMEOUT = 50
from dateutil.relativedelta import relativedelta
from datetime import datetime, date

from odoo.tools import DEFAULT_SERVER_DATE_FORMAT, DEFAULT_SERVER_DATETIME_FORMAT
from odoo.addons.team_api_connection.models.model import AuthorizeAPICustom
from odoo.addons.resource.models.utils import float_to_time
from odoo.addons.base.models.res_partner import _tz_get
import threading
import time

from fusion_refloor.configuration import Configuration
from fusion_refloor.api_client import ApiClient, ApiException
from fusion_refloor.api import scheduling_services_api
from fusion_refloor.models.schedule_request import ScheduleRequest

import base64
try:
    from urllib.request import urlopen  # pylint: disable=deprecated-module
except ImportError:
    from urllib import urlopen  # pylint: disable=deprecated-module

import logging
_logger = logging.getLogger(__name__)

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


class ResUsers(models.Model):
    _inherit = 'res.users'

    @api.model
    def check_sales_app_version(self, app_version_name):
        version_obj = self.env['otl.sales.app.version']
        app_version = version_obj.search([('name', '=', app_version_name)], limit=1)
        if not app_version:
            return {
                'result': 'Failed',
                'message': 'No matching app version was found in the system.',
            }
        else:
            current_date = fields.Date.today()
            latest_app_version = version_obj.search([('date', '<=', current_date), ('date', '>', app_version.date)], limit=1)
            if latest_app_version:
                return {
                    'result': 'Failed',
                    'message': str(self.env['ir.config_parameter'].sudo().get_param('team_sale_contract.version_mismatch_message')) or '',
                    'force_logout': 1
                }
        return {
            'result': 'Success',
        }




    @api.model
    def action_get_appointment_sync_status(self, user_id=None):
        result = {
            'result': 'Success',
            'message': 'No Force sync is enabled for the user',
            'data': {
                'force_sync_enabled': 0,
            }
        }
        if user_id:
            user = self.browse(user_id)
            if user.exists():
                appointments= []
                if user.enable_force_sync:
                    pending_appointments = self.env['team.customer.appointment'].search([('user_id', '=', user_id), ('start_sync_to_i360', '=', False), ('state', 'in', ['scheduled', 'canceled'])])
                    for appointment in pending_appointments:
                        if appointment.api_sync_log_line:
                            success_logs = self.env['otl.api.sync.log'].search([
                                ('appointment_id', '=', appointment.id),
                                ('state', '=', 'success'),
                                ('user_id', '=', user_id)
                            ], limit=1, order='created_date desc')
                            if success_logs:
                                appointments.append({
                                    'appointment_id': appointment.id,
                                    'last_api': success_logs.name or ''
                                })
                    result['data'].update({
                        'appointments': appointments,
                        'force_sync_enabled': 1,

                    })
                    result.update({
                        'message': 'Force sync is enabled for the user %s' % (user.name)
                    })
            else:
                return {
                    'result': 'Failed',
                    'message': 'User is not existing',
                }
        return result


    @api.model
    def action_logout_from_device(self, user_id = None):
        result = {
            'result': 'Success',
            'message': 'User is logout successfully from the device.'
        }
        if user_id:
            user = self.browse(user_id)
            if user.exists():
                user.sudo().write({'token_name': ''})
            else:
                result = {
                    'result': 'Failed',
                    'message': 'User is not existing.'
                }
        else:
            result = {
                'result': 'Failed',
                'message': 'User ID is missing.'
            }
        return result

    def get_special_pricing(self):
        special_price_list = []
        special_prices = self.env['otl.product.special.price'].search([])
        for special_price in special_prices:
            special_price_list.append({
                'special_price_id': special_price.id,
                'office_location_id': special_price.office_location_id.id,
                'product_tmpl_id': special_price.product_tmpl_id.id,
                'start_date': '%s 00:00:00'%(special_price.start_date),
                'end_date': '%s 23:59:59'%(special_price.end_date),
                'name': special_price.name,
                'list_price': special_price.list_price,
                'msrp': special_price.msrp,
                'max_discount': special_price.max_discount,
            })
        return special_price_list

    def get_promotion_codes(self):
        promotion_code_list = []
        promotion_codes  = self.env['otl.promotion.code'].search([])
        for code in promotion_codes:
            promotion_code_list.append({
                'promotion_code_id': code.id,
                'name': code.name,
                'discount': code.discount or 0,
                'start_date': '%s 00:00:00' % (code.start_date.strftime(DEFAULT_SERVER_DATE_FORMAT)),
                'end_date': '%s 23:59:59' % (code.end_date.strftime(DEFAULT_SERVER_DATE_FORMAT)),
                'calculation_type': code.calculation_type or ''
            })
        return promotion_code_list

    def get_transition_heights(self):
        transition_height_list = []
        transition_heights  = self.env['otl.transition.height'].search([])
        for height in transition_heights:
            transition_height_list.append({
                'transition_height_id': height.id,
                'name': height.name,
                'sequence': height.sequence or 0
            })
        return transition_height_list

    def get_restriction_rules_api(self):
        current_date = fields.Date.today()
        rules = self.env['otl.payment.restriction.rule'].search([('active', '=', True), ('end_date', '>=', current_date)])
        rule_list = [{'name': rule.name or '',
                      'start_date': '%s 00:00:00' % (rule.start_date.strftime(DEFAULT_SERVER_DATE_FORMAT) or ''),
                      'end_date': '%s 23:59:59' % (rule.end_date.strftime(DEFAULT_SERVER_DATE_FORMAT) or ''),
                      'conditions': rule.conditions or '',
                      'amount': rule.min_order_total or '',
                      'margin_amount': rule.min_margin_amount or '',
                      'grade': rule.grade or '',
                      'company': [{'id': company.id, 'name': company.name} for company in rule.company_id],
                      'allowed_days': [{'id': day.id, 'name': day.name} for day in rule.allowed_days_ids],
                      'office_locations': [{'id': location.id,'name': location.name} for location in rule.location_ids],
                      'restricted_promotions': [{'id': promo.id,'name': promo.name} for promo in rule.promotion_code_ids],
                      'conditional_promotions': [{'id': conditional_promo.id,'name': conditional_promo.name} for conditional_promo in rule.promos_ids],
                      'restricted_discounts': [{'id': discount.id,'code': discount.code} for discount in rule.discount_code_ids],
                      'payment_options': [{'id': fin.id,'name': fin.name} for fin in rule.payment_option_ids] or ''} for rule in rules]
        return rule_list

    def get_appointment_result_reasons_api(self):
        reasons = self.env['otl.appointment.result.reason'].search([])
        reason_list = [{
            'reason':  reason.name or "",
            'reason_id' : reason.id or 0,
            'applicable_result_ids': reason.appointment_result_ids and reason.appointment_result_ids.ids or []
        }
            for reason in reasons]
        return reason_list

    def get_dynamic_contract_vals_api(self, app_version):

        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')

        applicant_list = []
        non_applicant_list = []
        latest_version = False
        if app_version:
            latest_version = self.env['otl.sales.app.version'].search([('name', '=', app_version)], order='date desc', limit=1)
        if not latest_version:
            latest_version = self.env['otl.sales.app.version'].search([], order='date desc', limit=1)
        app_dict = [

                    # 'app_id': latest_version.id,
                    # 'app_name': latest_version.name,
                    # 'with_co_applicant_template_url':url,
                    # 'non_co_applicant_template_url':url

                    ]
        if latest_version.sale_contract_tmpl_id:
            attachment = latest_version.sale_contract_tmpl_id.attachment_id
            if not attachment.access_token:
                attachment.sudo().generate_access_token()
            contract_template_url = _('%s/web/image/%s?access_token=%s' % (base_url, attachment.id, attachment.access_token))
            contract_template = latest_version.sale_contract_tmpl_id
            for value in contract_template.sign_item_ids:
                applicant_list.append({
                    # 'id' : value.id and value.id or '',
                    'type': value.type_id and value.type_id.name or '',
                    'field_type': value.type_id and value.type_id.item_type or '',
                    'option': value.type_id and value.type_id.option_field or '',
                    'related_field': value.type_id.auto_field and value.type_id.auto_field or '',
                    'responsible_id': value.responsible_id.name or '',
                    'page': value.page or '',
                    'posX': value.posX or '',
                    'posY': value.posY or '',
                    'width': value.width or '',
                    'height': value.height or '',
                    'required': value.required and 1 or 0,
                })
            app_dict.append({
                'template_id': contract_template.id,
                'document_url': contract_template_url,
                'name': contract_template.name,
                'type': 'with_co_applicant',
                'fields': applicant_list})
        #
        if latest_version.sale_contract_tmpl_id_ncp:
            attachment_non_co_app = latest_version.sale_contract_tmpl_id_ncp.attachment_id
            if not attachment_non_co_app.access_token:
                attachment_non_co_app.sudo().generate_access_token()
            contract_template_url_non_co_applicant = _('%s/web/image/%s?access_token=%s' % (base_url, attachment_non_co_app.id, attachment_non_co_app.access_token))
            contract_template_non_co = latest_version.sale_contract_tmpl_id_ncp
            for value in contract_template_non_co.sign_item_ids:
                non_applicant_list.append({
                    'type': value.type_id and value.type_id.name or '',
                    'field_type': value.type_id and value.type_id.item_type or '',
                    'option': value.type_id and value.type_id.option_field or '',
                    'responsible_id': value.responsible_id.name or '',
                    'related_field': value.type_id.auto_field and value.type_id.auto_field or '',
                    'page': value.page or '',
                    'posX': value.posX or '',
                    'posY': value.posY or '',
                    'width': value.width or '',
                    'height': value.height or '',
                    'required': value.required and 1 or 0,
                })
            app_dict.append({'template_id': contract_template_non_co.id,
                             'document_url': contract_template_url_non_co_applicant,
                             'name': contract_template_non_co.name,
                             'type': 'without_co_applicant',
                             'fields': non_applicant_list})

        return app_dict

    def get_external_application_credentials(self):
        credential_list = []
        applications = self.env['otl.external.application.credentials'].search([])
        for application in applications:
            credential_list.append({
                'ext_credential_id': application.id,
                'url': application.url or '',
                'api_key': application.api_key or '',
                'entity_key': application.entity_key or '',
                'provider': application.provider or '',
                'available_office_location_ids': application.office_location_ids and application.office_location_ids.ids or []
            })
        return credential_list

    def get_finance_checklist_items(self):
        finance_checklist = []
        checklists = self.env['otl.finance.checklist.items'].search([])
        for checklist in checklists:
            providers_list = []
            if checklist.applicable_finance_providers:
                providers_list = [x.code for x in checklist.applicable_finance_providers]
            finance_checklist.append({
                'checklist_id': checklist.id,
                'name': checklist.name or '',
                'sequence': checklist.sequence,
                'applicable_type': checklist.applicable_type or '',
                'applicable_finance_providers': providers_list,

            })
        return finance_checklist

    def get_auto_answer_logic(self):
        logic_list = []
        logics = self.env['otl.questionnaire.calc.logic'].search([])
        for logic in logics:
            logic_line = []
            for line in logic.logic_line:
                logic_line.append({
                    'question_id': line.question_id.id  or 0,
                    'excluded_question_ids': line.excluded_question_ids and line.excluded_question_ids.ids or [],
                    'code': line.code,
                })
            logic_list.append({
                'logic_type': logic.type,
                'question_lines': logic_line
            })
        return logic_list

    def get_destination_selection(self):
        destination_list = []
        destinations = self.env['otl.destination.selection'].search([])
        for destination in destinations:
            destination_list.append({
                'destination_id': destination.id,
                'name': destination.name or '',
                'terms_and_conditions': destination.terms_and_conditions or '',
            })
        return destination_list



    @api.model
    def get_master_data_contents(self, data={}):
        result = {
            'result': 'Success',
            'message': 'Master Data retrieved successfully.'
        }
        # try:
        app_version = data.get('app_version', '')
        room_list = self.env['team.room.room'].get_rooms()
        questionnaire_list = self.env['team.quote.question'].get_all_questionnaires()
        flooring_colors_list = self.env['product.product'].get_all_flooring_colors()
        floor_colors_list = self.env['product.product'].get_all_flooring_colors('floor')
        stair_colors_list = self.env['product.product'].get_all_flooring_colors('stair')
        molding_type_list = self.env['team.floor.molding'].get_all_molding_types()
        payment_option_list = self.env['team.downpayment.option'].get_all_payment_options()
        discount_coupon_list = self.env['team.monthly.promo'].get_all_discount_coupons()
        products_list = self.env['product.template'].get_all_products()
        appointment_data = self.env['team.customer.appointment'].action_get_appointment_data(self.env.user.id)
        appointment_list = appointment_data.get('data', [])
        appointment_result_list = self.env['appointment.result'].get_appointment_results()
        special_price_list = self.get_special_pricing()
        promotion_code_list = self.get_promotion_codes()
        transition_height_list = self.get_transition_heights()
        rules = self.get_restriction_rules_api()
        reasons_list = self.get_appointment_result_reasons_api()
        finance_checklist = self.get_finance_checklist_items()
        auto_answer_logic_list = self.get_auto_answer_logic()
        destination_list = self.get_destination_selection()
        templates = self.sudo().get_dynamic_contract_vals_api(app_version)
        credential_list = self.sudo().get_external_application_credentials()
        auto_logout_time = ''
        if self.env.user.company_id.enable_auto_logout:
            logout_time = self.env.user.company_id.auto_logout_time or 0
            auto_logout_time = str(float_to_time(logout_time))
            # user = self.env.user
            # tz = user.tz and pytz.timezone(user.tz) or pytz.utc
            # current_time = fields.Datetime.now().replace(tzinfo=pytz.utc)
            # hour, minute, seconds = auto_logout_time.split(':')
            # auto_logout_date = current_time.replace(hour=int(hour), minute=int(minute), second=int(seconds), tzinfo=None)
            # auto_logout_date_local = tz.localize(auto_logout_date).astimezone(pytz.utc)
            # if current_time >  auto_logout_date_local:
            #     auto_logout_date_local = auto_logout_date_local + relativedelta(days=1)
        company = self.env.user.company_id
        result.update({
            'rooms': room_list,
            'questionnaires': questionnaire_list,
            'flooring_colors': flooring_colors_list,
            'floor_colors_list': floor_colors_list,
            'stair_colors_list': stair_colors_list,
            'molding_types': molding_type_list,
            'payment_options': payment_option_list,
            'discount_coupons': discount_coupon_list,
            'product_plans': products_list,
            'appointments': appointment_list,
            'appointment_results': appointment_result_list,
            'special_prices': special_price_list,
            'promotion_codes': promotion_code_list,
            'transition_heights': transition_height_list,
            'min_sale_price': float(self.env['ir.config_parameter'].sudo().get_param('team_sale_contract.min_sale_price')) or 0.0,
            'max_no_transitions': int(self.env['ir.config_parameter'].sudo().get_param('team_sale_contract.max_no_transitions')) or 0,
            'recision_date': company.recision_date and company.recision_date.strftime(DEFAULT_SERVER_DATE_FORMAT) or '',
            'auto_logout_time': auto_logout_time  or '',
            'payment_restriction_rules': rules,
            'appointment_result_reasons': reasons_list,
            'contract_document_templates': templates,
            'finance_checklist': finance_checklist,
            'auto_answer_logic_list': auto_answer_logic_list,
            'destination_selection_list': destination_list,
            'versatile_url': company.versatile_url or '',
            'versatile_api_key': company.versatile_api_key or '',
            'versatile_entity_key': company.versatile_entity_key or '',
            'enable_geolocation': eval(str(self.env['ir.config_parameter'].sudo().get_param('team_sale_contract.enable_geolocation'))) or False,
            'geolocation_radius_limit': int(self.env['ir.config_parameter'].sudo().get_param('team_sale_contract.geolocation_radius_limit')) or 0,
            'external_credentials': credential_list,
            'max_stair_width': float(self.env['ir.config_parameter'].sudo().get_param('team_sale_contract.max_stair_width')) or 0,
            'min_down_payment_amount': float(self.env['ir.config_parameter'].sudo().get_param('team_sale_contract.min_down_payment_amount')) or 0.0,
            'destination_selection_consent_message': str(self.env['ir.config_parameter'].sudo().get_param('team_sale_contract.destination_selection_consent_message')) or '',
            'address_visible_time_limit': int(self.env['ir.config_parameter'].sudo().get_param('team_sale_contract.address_visible_time_limit')) or 0,
        })
        # except:
        #     result = {
        #         'result': 'Failed',
        #         'message': 'Something went wrong while fetching master data.'
        #     }
        return result

    def get_stair_width_id(self, data={}):
        result = {
            'result': 'Success',
            'message': 'Master Data retrieved successfully.'
        }
        team_quote_question_id = self.env['team.quote.question'].search([('code', '=', 'StairWidth')], limit=1)
        if team_quote_question_id:
            result.update({
                'stair_width_id': team_quote_question_id.id,
            })
            return result
        else:
            result = {
            'result': 'False',
            'message': 'Stair Width ID is not found.'
        }
            
    def get_stair_cover_risers(self, data={}):
        result = {
            'result': 'Success',
            'message': 'Master Data retrieved successfully.'
        }
        team_quote_question_id = self.env['team.quote.question'].search([('code', '=', 'CurrentCoveringType')], limit=1)
        if team_quote_question_id:
            result.update({
                'stair_cover_risers': team_quote_question_id.id,
            })
            return result
        else:
            result = {
            'result': 'False',
            'message': 'Stair Width ID is not found.'
        }


    def get_sales_appointment_api_offline(self,user_id):
        configurations = self.env['team.improveit.configuration'].search([('api_type', '=', 'boomi')])
        result = {
            'result': 'Success',
            'message': 'Appointment synced successfully'
        }
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
                    try:
                        req = requests.post(url, data=json.dumps(data), headers=headers, timeout=TIMEOUT, verify=configurations.enable_ssl)
                        req.raise_for_status()
                        content = req.json()
                    except Exception as e:
                        _logger.error('-----get_sales_appointment_api_offline Error: %s'%e)
                        return {
                            'result': 'Failed',
                            'message': 'Error is occurred while fetching appointments.'
                        }
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
                            appointment_timezone = appointment.get('TimeZone', '')
                            str1 = appointment.get('AppointmentTime', '0:00 AM')
                            if str1 is None:
                                return {
                                    'result': 'Failed',
                                    'message': 'Appointment time is missing in the appointment for customer %s'%(appointment.get('ProspectName', ''))
                                }
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
                            if appointment_timezone and appointment_timezone in [tz[0] for tz in _tz_get(self)]:
                                tz = pytz.timezone(appointment_timezone)
                            else:
                                tz = user.tz and pytz.timezone(user.tz) or pytz.utc
                            appointment_date = tz.localize(appointment_date).astimezone(pytz.utc).strftime(
                                '%Y-%m-%d %H:%M:%S')
                            state = self.env['res.country.state'].search(
                                [('country_id', '=', 233), ('code', '=', appointment.get('ProspectState',''))],limit=1)
                            appointments = self.env['team.customer.appointment'].sudo().search(
                                [('improveit_appointment_id', '=', appointment['AppointmentID'])], limit=1, order='id desc')
                            if appointments and appointments.sale_order_ids:
                                if appointments.appointment_date and appointments.appointment_date.strftime(
                                '%Y-%m-%d %H:%M:%S') == appointment_date:
                                    continue
                                elif appointments.sale_order_ids.filtered(lambda x: x.is_data_upload_completed):
                                    appointments = False

                            _logger.info('Existing Appointment: %s'%(appointments))
                            market_segment = appointment.get('MarketSegment', '')
                            office_location_id = False
                            if market_segment:
                                office_location_id = self.env['otl.office.location'].search([('name', '=', market_segment)], limit=1)
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
                                    'appointment_timezone': appointment_timezone,

                                }
                                try:
                                    appointment_obj = self.env['team.customer.appointment'].create(appointment_values)
                                except Exception as e:
                                    appointment_obj = False
                                    _logger.error('Following Error is occurred while creating appointment: %s'%e)
                                    return {
                                        'result': 'Failed',
                                        'message': 'Following Error is occurred while creating appointment: %s'%e
                                    }
                                if appointment_obj:
                                    try:
                                        appointment_obj.geo_localize()
                                    except Exception as e:
                                        _logger.error('Following Error is occurred while fetching Geo Localization: %s' % e)
                                        continue
                                    if appointment_obj and market_segment and not office_location_id:
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
                                    'appointment_timezone': appointment_timezone,
                                }
                                appointments.write(appointment_values)
                                try:
                                    appointments.geo_localize()
                                except:
                                    continue
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
        return result

    @api.model
    def action_check_auto_logout(self, data =None):
        auto_logout_time = ''
        enable_auto_logout = 0
        if self.env.user.company_id.enable_auto_logout:
            enable_auto_logout = 1
            logout_time = self.env.user.company_id.auto_logout_time or 0
            auto_logout_time = str(float_to_time(logout_time))
            # user = self.env.user
            # tz = user.tz and pytz.timezone(user.tz) or pytz.utc
            # current_time = fields.Datetime.now().replace(tzinfo=pytz.utc)
            # hour, minute, seconds = auto_logout_time.split(':')
            # auto_logout_date = current_time.replace(hour=int(hour), minute=int(minute), second=int(seconds),
            #                                         tzinfo=None)
            # auto_logout_date_local = tz.localize(auto_logout_date).astimezone(pytz.utc)
            # if current_time > auto_logout_date_local:
            #     auto_logout_date_local = auto_logout_date_local + relativedelta(days=1)
        result = {
            'result': 'Success',
            'enable_auto_logout': enable_auto_logout,
            'auto_logout_time': auto_logout_time or '',
        }
        return result

    @api.model
    def action_log_user_authentication(self, uid, action, token, user_data={}):
        values = user_data.copy()
        vals = {
            'user_id': int(uid),
            'action': action,
            'token': token,
        }
        if values:
            values.pop('device_reg_id', '')
            vals.update(values)
        log = self.env['otl.user.authentication.log'].sudo().create(vals)
        _logger.info("Authentication log created successfully----. Vals: %s, Record: %s"%(vals, log.id))
        return True


    @api.model
    def get_user_details(self, uid):
        result = super(ResUsers, self).get_user_details(uid)
        user = self.env['res.users'].search([('id', '=', uid)])
        if user:
            enable_user_qrcode = eval(str(self.env['ir.config_parameter'].sudo().get_param(
                'team_sale_contract.enable_user_qrcode'))) or False
            qrcode_url = ''
            if enable_user_qrcode and not user.gtr_not_existing:
                res = user.get_user_qrcode_from_gtr()
                _logger.info('Response of get_user_qrcode_from_gtr for user %s. Message: %s' % (user.name, res.get('message', '')))
                if user.qrcode_attachment_id and user.qrcode_attachment_id.datas:
                    attachment = user.qrcode_attachment_id
                    attachment.sudo().generate_access_token()
                    base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
                    qrcode_url = _('%s/web/image/%s?access_token=%s' % (base_url, attachment.id, attachment.access_token))
            result.update({
                "restrict_geolocation": user.restrict_geolocation and 1 or 0,
                "referral_qr_code_url": qrcode_url,
            })
        return result

    def get_user_qrcode_from_gtr(self):
        for user in self:
            configurations = self.env['team.improveit.configuration'].search([('api_type', '=', 'gtr')])
            if configurations:
                end_point_url = configurations.token_url
                client_secret = configurations.client_secret
                gtr_page_limit = int(self.env['ir.config_parameter'].sudo().get_param(
                    'team_sale_contract.gtr_page_limit')) or 0
                if end_point_url and client_secret:
                    if user.gtr_user_id:
                        url = "%s/v2/salesreps/%s" % (end_point_url, user.gtr_user_id or '')
                    else:
                        url = "%s/v2/salesreps?page_size=%s" % (end_point_url, gtr_page_limit)
                    headers = {
                        'Authorization': "Bearer %s" % client_secret,
                        'Content-Type': 'application/json'
                    }
                    data = {}
                    try:
                        req = requests.get(url, data=data, headers=headers, timeout=TIMEOUT,
                                           verify=configurations.enable_ssl)
                        req.raise_for_status()
                        content = req.json()
                        sales_rep_data = content.get('salesreps', [])
                        for data in sales_rep_data:
                            user_data = data.get('attributes', {})
                            qrcode_url = user_data.get('qr_code_url', '')
                            if qrcode_url:
                                image_data = self.env['team.improveit.configuration'].is_valid_url_image(qrcode_url)
                                image_binary = False
                                if image_data:
                                    try:
                                        image_data = urlopen(qrcode_url).read()
                                        image_binary = base64.b64encode(image_data)
                                    except:
                                        image_binary = False
                                    if image_binary:
                                        if user.gtr_user_id:
                                            if str(data.get('id')) == str(user.gtr_user_id):
                                                    user.write({'referral_qrcode': image_binary})
                                                    return {
                                                        'result': 'Success',
                                                        'message': 'QR code fetched successfully from GTR.'
                                                    }
                                        else:
                                            if user.email == user_data.get('email', ''):
                                                user.write({'referral_qrcode': image_binary, 'gtr_user_id': data.get('id')})
                                                return {
                                                    'result': 'Success',
                                                    'message': 'QR code fetched successfully from GTR.'
                                                }

                        #if the code reaches here, it means QR code is not fetched for the user,
                        # so removing any existing QR code for the user to avoid mismatch of QR code in case of any future successful fetch.
                        user.write({'referral_qrcode': False, 'gtr_not_existing': True})
                    except:
                        return {
                            'result': 'Failed',
                            'message': 'Error is occurred while fetching QR code from GTR.'
                        }

            else:
                return {
                    'result': 'Failed',
                    'message': 'API Configuration is missing for GTR.'
                }
        return {
            'result': 'Failed',
            'message': 'User does not have GTR User ID or QR code URL is missing.'
        }

    # field for skip GTR search if the value is True
    gtr_not_existing = fields.Boolean('Not Existing on GTR', default=False)


class TeamQuoteQuestion(models.Model):
    _inherit = 'team.quote.question'

    @api.model
    def get_all_questionnaires(self):
        questionnaire_list = []
        questions = self.search([], order='sequence asc')
        for question in questions:
            quote_label = question.get_quote_label()
            applicable_to = 'rooms'
            stair_product = False
            floor_product = False
            if question.product_category_ids:
                if question.product_category_ids.filtered(lambda x: x.name.upper() == 'VINYL STAIRS'):
                    stair_product = True
                if question.product_category_ids.filtered(lambda x: x.name.upper() == 'VINYL FLOORING'):
                    floor_product = True
                if floor_product and stair_product:
                    applicable_to = 'common'
                elif stair_product and not floor_product:
                    applicable_to = 'stairs'
            amount = 0
            if question.code != 'StairCount':
                amount = question.amount or 0
            applicable_rooms_list = []
            if question.applicable_rooms:
                for room in question.applicable_rooms:
                    applicable_rooms_list.append({
                        'room_id': room.id,
                        'room_name': room.name and room.name.upper() or '',
                    })
            questionnaire_list.append({
                'id': question.id,
                'name': question.name or '',
                'code': question.code or '',
                'max_allowed_limit': question.max_allowed_limit or 0,
                'company_id': question.company_id.id,
                'description': question.description or '',
                'question_type': question.question_type or '',
                'validation_required': question.validation_required,
                'validation_email_required': question.validation_email,
                'validation_error_msg': question.validation_error_msg or '',
                'mandatory_answer': question.constr_mandatory or '',
                'Error_message': question.constr_error_msg or '',
                'Refelct_in_cost': question.reflect_cost,
                'calculation_type': question.calculation_type,
                'amount': amount,
                'amount_included': question.amount_included or 0,
                'sequence': question.sequence or 0,
                'default_answer': question.default_answer or '',
                'exclude_from_discount': question.exclude_from_discount or False,
                'exclude_from_promotion': question.exclude_from_promotion or False,
                'calculate_order_wise': question.calculate_order_wise or False,
                'multiply_with_area': question.multiply_with_area or False,
                'set_default_answer': question.set_default_answer or False,
                'applicable_current_surface': question.applicable_current_surface or '',
                'quote_label': quote_label,
                'applicable_to': applicable_to,
                'applicable_rooms': applicable_rooms_list,
                'mandatory_for_current_surface_concrete': question.mandatory_for_current_surface_concrete or False,
            })
        return questionnaire_list


class ProductProduct(models.Model):
    _inherit = 'product.product'


    def get_material_color_url(self):
        url = ''
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        if self.color_attachment_id:
            attachment = self.color_attachment_id
            attachment.sudo().generate_access_token()
            url = base_url + '/web/image/' + str(attachment.id) + '?access_token=' + str(attachment.access_token)
        return url

    @api.model
    def get_all_flooring_colors(self, room_type=''):
        domain = [('active', '=', True), ('is_material', '=', True), ('floor_color', '!=', False)]
        if room_type == 'floor':
            domain.append(('categ_id.name', 'not ilike', 'Stairs'))
        elif room_type == 'stair':
            domain.append(('categ_id.name', 'ilike', 'Stairs'))
        product_list = self.search(domain)
        materials_list = []
        default_material_image_attachment_id = self.env.user.company_id.material_image_attachment_id or False
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        default_image_url = ''
        if default_material_image_attachment_id:
            if not default_material_image_attachment_id.access_token:
                default_material_image_attachment_id.sudo().generate_access_token()
            default_image_url = _('%s/web/image/%s?access_token=%s' % (
                base_url, default_material_image_attachment_id.id, default_material_image_attachment_id.access_token))
        color_list = []
        if product_list:
            for product in product_list:
                color = product.display_name_in_app and product.display_name_in_app or product.floor_color
                if color and color not in color_list:
                    if product.image_variant_128:
                        floor_color_url = product.get_material_color_url()
                    else:
                        floor_color_url = default_image_url

                    vals = {
                        'material_id': product.id or 0,
                        'name': product.name,
                        'color': color,
                        'material_image_url': floor_color_url,
                        'color_up_charge_price': product.color_up_charge_price or 0,
                        'in_stock': product.in_stock and 1 or 0,
                        'glue_down': product.glue_down and 1 or 0,
                        'special_order': product.special_order and 1 or 0,
                        'office_location_ids': product.office_location_ids and product.office_location_ids.ids or [],
                        'special_order_location_ids': product.special_order_office_location_ids and product.special_order_office_location_ids.ids or []
                    }

                    color_list.append(color)
                    materials_list.append(vals)
        sorted_material_list = sorted(materials_list, key=lambda k: k['color'])
        return sorted_material_list


class FloorMolding(models.Model):
    _inherit = 'team.floor.molding'

    @api.model
    def get_all_molding_types(self):
        molding_type_list = []
        molding_types = self.search([])
        for molding in molding_types:
            molding_type_list.append({
                'molding_id': molding.id,
                'name': molding.name,
                'unit_price': molding.unit_price or 0,
                'default_delivery': molding.default_delivery or '',
                'delivery_options': [option_line.name for option_line in molding.delivery_option_line]
            })
        return molding_type_list


class DownPaymentOption(models.Model):
    _inherit = 'team.downpayment.option'

    @api.model
    def get_all_payment_options(self):
        payment_list = []
        all_payment_options = self.search([], order='sequence asc')
        for payment_options in all_payment_options:
            payment_options_dict = {
                'id': payment_options.id or 0,
                'Name': payment_options.name or '',
                'Description__c': payment_options.description or '',
                'Down_Payment__c': payment_options.down_payment or '',
                'Final_Payment__c': payment_options.final_payment or '',
                'Payment_Factor__c': payment_options.payment_factor or '',
                'Secondary_Payment_Factor__c': payment_options.secondary_payment_factor or '0',
                'Balance_Due__c': payment_options.balance_due or '',
                'Payment_Info__c': payment_options.payment_info or '',
                'sequence': payment_options.sequence or 0,
                'down_payment_message': payment_options.down_payment_message or '',
                'start_date': payment_options.start_date if payment_options.start_date else '',
                'end_date': payment_options.end_date if payment_options.end_date else '',
            }
            payment_list.append(payment_options_dict)
        return payment_list


class TeamMonthlyPromo(models.Model):
    _inherit = 'team.monthly.promo'

    @api.model
    def get_all_discount_coupons(self):
        discount_coupon_list = []
        all_discount_coupons = self.env['team.monthly.promo'].search([])
        default_promo_image_attachment_id = self.env.user.company_id.promo_image_attachment_id or False
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        default_promo_img_url = ''
        if default_promo_image_attachment_id:
            if not default_promo_image_attachment_id.access_token:
                default_promo_image_attachment_id.sudo().generate_access_token()
            default_promo_img_url = _('%s/web/image/%s?access_token=%s' % (
                base_url, default_promo_image_attachment_id.id, default_promo_image_attachment_id.access_token))
        for discount_coupon in all_discount_coupons:
            promo_image_attachment_id = discount_coupon.attachment_id and discount_coupon.attachment_id.sudo() or False
            promo_img_url = ''
            if promo_image_attachment_id:
                if not promo_image_attachment_id.access_token:
                    promo_image_attachment_id.sudo().generate_access_token()
                promo_img_url = _('%s/web/image/%s?access_token=%s' % (
                    base_url, promo_image_attachment_id.id, promo_image_attachment_id.access_token))

            discount_coupon_dict = {
                'Code': discount_coupon.code or '',
                'DisplayName': discount_coupon.name or '',
                'Amount': discount_coupon.amount or '',
                'Type': discount_coupon.type or '',
                'promo_image_url': promo_img_url or default_promo_img_url or ''
            }
            discount_coupon_list.append(discount_coupon_dict)
        return discount_coupon_list


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    @api.model
    def get_all_products(self):
        product_list = []
        products = self.search(
            [('type', '=', 'consu'), ('product_variant_ids', '!=', False), ('categ_id.name', 'not ilike', 'Stairs')],
            order='sequence asc')
        min_sale_price = float(self.env['ir.config_parameter'].sudo().get_param('team_sale_contract.min_sale_price')) or 0.0
        for product in products:
            stair_product = self.search([
                ('type', '=', 'consu'),
                ('product_variant_ids', '!=', False),
                ('categ_id.name', 'ilike', 'Stairs'),
                ('grade', '=', product.grade)
            ], order='sequence asc', limit=1)
            warranty = dict(product._fields['warranty'].selection).get(product.warranty)
            product_list.append({
                'id': product.id,
                'plan_title': product.display_name_in_app or '',
                'plan_subtitle': product.payment_plan or '',
                'description': product.description or '',
                'material_cost': product.list_price,
                'warranty': warranty or '',
                'sequence': product.sequence or '',
                'company_id': product.company_id.id or 0,
                'cost_per_sqft': product.msrp or 0,
                'monthly_promo': product.monthly_promo or 0,
                'warranty_info': product.warranty_info or '',
                'min_sale_price': product.min_sale_price and product.min_sale_price or min_sale_price,
                'eligible_for_discounts': product.eligible_for_discounts or '',
                'unit_of_measure': product.unit_of_measure or '',
                'grade': product.grade or '',
                'stair_cost': stair_product and stair_product.list_price or 0,
                'stair_msrp': stair_product and stair_product.msrp or 0,
                'stair_product_id': stair_product and stair_product.id or 0,
                'office_location_ids': product.office_location_ids and product.office_location_ids.ids or []

            })
        return product_list


class AppointmentResult(models.Model):
    _inherit = "appointment.result"

    @api.model
    def get_appointment_results(self):
        result_list = []
        appointment_results = self.search([])
        for appointment_result in appointment_results:
            result_list.append({
                'id': appointment_result.id,
                'result': appointment_result.result or '',
                'last_available_screen': appointment_result.last_available_screen or ''
            })
        return result_list


class TeamCustomerAppointment(models.Model):
    _inherit = 'team.customer.appointment'

    start_sync_to_i360 = fields.Boolean('Start Sync to i360', default=False, copy=False)
    prospect_info_updated = fields.Boolean('Prospect Info Updated to i360', default=False, copy=False)
    completed_date = fields.Datetime('Appointment Completed Date')
    sync_initiated_date = fields.Datetime('Sync Initiated Time', copy=False)
    timezone = fields.Char('Timezone', default='US/Eastern')
    related_attachment_ids = fields.One2many('ir.attachment', 'appointment_id', string="Related Attachments")

    @api.model
    def action_get_appointment_data(self, user_id):

        list = []
        if user_id:
            user = self.env['res.users'].browse(int(user_id))
            if user and user.improveit_user_id:
                result = self.env['res.users'].get_sales_appointment_api_offline(user.improveit_user_id)
                if result.get('result', '') == 'Failed':
                    return result
        tz = user.tz or self._context.get('tz') or 'UTC'
        first_start_date_utc, first_end_date_utc = get_week_date(0, tz)
        appointment_data = self.env['team.customer.appointment'].search(
            [
                ('user_id', '=', int(user_id)),
                ('state', '=', 'scheduled'),
                ('start_sync_to_i360', '!=', True),
                # ('appointment_date', '>=', first_start_date_utc),
                # ('appointment_date', '<', first_end_date_utc),
            ], order='appointment_date asc')
        improveit_appointment_ids = []
        enable_destination_selection = eval(str(self.env['ir.config_parameter'].sudo().get_param('team_sale_contract.enable_destination_selection'))) or False

        if appointment_data:
            for data in appointment_data:
                if data.improveit_appointment_id:
                    if data.improveit_appointment_id in improveit_appointment_ids:
                        continue
                    improveit_appointment_ids.append(data.improveit_appointment_id)
                appointment_date = data.appointment_date and utc_2_local(data.appointment_date, tz) or False
                appointment_datetime = ''
                if appointment_date:
                    appointment_datetime = appointment_date.strftime('%d %b %I:%M %p')
                external_entity_keys = []
                if data.office_location_id:
                    location_entity_keys = self.env['otl.location.entity.key.line'].search([
                        ('office_location_id', '=', data.office_location_id.id),
                        ('external_application_id.provider', '=', 'versatile')
                    ])
                    if location_entity_keys:
                        for location_entity_key in location_entity_keys:
                            application = location_entity_key.external_application_id
                            external_entity_keys.append({
                                'entity_key': location_entity_key.entity_key or '',
                                'provider': application.provider or '',
                            })
                vals = {
                    'id': data.id,
                    'improveit_appointment_id': data.improveit_appointment_id or '',
                    'name': data.name,
                    'customer_name': data.customer_name and data.customer_name.upper() or '',
                    'applicant_first_name': data.applicant_first_name or '',
                    'applicant_middle_name': data.applicant_middle_name or '',
                    'applicant_last_name': data.applicant_last_name or '',
                    'co_applicant_first_name': data.co_applicant_first_name or '',
                    'co_applicant_middle_name': data.co_applicant_middle_name or '',
                    'co_applicant_last_name': data.co_applicant_last_name or '',
                    'co_applicant_phone': data.co_applicant_phone or '',
                    'co_applicant_email': data.co_applicant_email or '',
                    'co_applicant_address': data.co_applicant_address or '',
                    'co_applicant_city': data.co_applicant_city or '',
                    'co_applicant_state_id': data.co_applicant_state.id or '',
                    'co_applicant_state_code': data.co_applicant_state.code or '',
                    'co_applicant_state_name': data.co_applicant_state.name or '',
                    'co_applicant_zip': data.co_applicant_zip or '',
                    'co_applicant_secondary_phone': data.co_applicant_secondary_phone or '',
                    'is_room_measurement_exist': data.measurement_exist,
                    'customer_id': data.partner_id.id or 0,
                    'co_applicant': data.co_applicant or '',
                    'appointment_date': appointment_date,
                    'appointment_datetime': appointment_datetime,
                    'street': data.street or '',
                    'street2': data.street2 or '',
                    'city': data.city or '',
                    'state_id': data.state_id.id or 0,
                    'office_location_id': data.office_location_id and data.office_location_id.id or 0,
                    'enable_destination_selection': enable_destination_selection and data.office_location_id and data.office_location_id.enable_destination_selection and 1 or 0,
                    'state_code': data.state_id.code or '',
                    'state': data.state_id.name or '',
                    'country_id': data.country_id.id or 0,
                    'country': data.country_id.name or '',
                    'zip': data.zip or '',
                    'country_code': data.country_id.code or '',
                    'phone': data.phone or '',
                    'mobile': data.mobile,
                    'email': data.email or '',
                    'sales_person': data.user_id.name or '',
                    'salesperson_id': data.user_id.id or 0,
                    'partner_latitude': data.partner_latitude or 0,
                    'partner_longitude': data.partner_longitude or 0,
                    'recision_date': self.env.user.company_id.recision_date and self.env.user.company_id.recision_date.strftime(
                        DEFAULT_SERVER_DATE_FORMAT) or '',
                    'external_entity_keys': external_entity_keys,
                    'appointment_timezone': data.appointment_timezone or '',
                }
                list.append(vals)

        return {
            'result': 'Success',
            'data': list
        }

    def get_timezone_based_time(self, date, timezone):
        datetime_obj = datetime.strptime(date, DEFAULT_SERVER_DATETIME_FORMAT)
        timezone_time = ''
        if timezone == 'EST' or timezone == 'CDT':
            timezone_time = '-5:00'
        elif timezone == 'EDT':
            timezone_time = '-4:00'
        elif timezone == 'CST':
            timezone_time = '-6:00'
        elif timezone == 'IST':
            timezone_time = '+5:30'
        elif 'GMT' in timezone:
            timezone_time = timezone.replace('GMT', '')
        if timezone_time:
            if ':' not in timezone_time:
                timezone_time += ':00'
            hours, minutes = timezone_time.split(':')
            updated_time = datetime_obj - relativedelta(hours=int(hours), minutes=int(minutes))
            return updated_time
        return datetime_obj

    def action_update_appointment(self, data, app_version=''):
        result = {}
        for appointment in self:
            partner_vals = {}
            completed_date = data.get('completed_date', '')
            timezone = data.get('timezone', 'US/Eastern')
            completed_date_utc = False
            if completed_date:
                completed_date_utc = completed_date
                if timezone:
                    completed_date_utc = self.get_timezone_based_time(completed_date, timezone)
            send_physical_document = False
            if data.get('send_physical_document', 0) == 1:
                send_physical_document = True
            flexible_installation = False
            if data.get('flexible_installation', 0) == 1:
                flexible_installation = True
            both_parties_present = False
            if data.get('both_parties_present', 0) == 1:
                both_parties_present = True
            app_version_id = False
            if app_version:
                app_version_id = self.env['otl.sales.app.version'].search([('name', '=', app_version)], limit=1)
            resulting_reason_id = False
            if data.get('resulting_reason_id', False):
                resulting_reason_id = int(data.get('resulting_reason_id', 0))
                resulting_reason= self.env['otl.appointment.result.reason'].browse(resulting_reason_id)
                if not resulting_reason or not resulting_reason.exists():
                    return {'message': 'Wrong value for Appointment Resulting Reason', 'result': 'Failed'}
            destination_selection_id = False
            if data.get('destination_selection_id', False):
                destination_selection_id = int(data.get('destination_selection_id', 0))
                destination_selection= self.env['otl.appointment.result.reason'].browse(destination_selection_id)
                if not destination_selection or not destination_selection.exists():
                    return {'message': 'Wrong value for Destination Selection', 'result': 'Failed'}
            vals = {
                'what_happened_notes': data.get('what_happened_notes', ''),
                'whats_next_notes': data.get('whats_next_notes', ''),
                'resulting_reason_id': resulting_reason_id,
                'additional_comments': data.get('additional_comments', ''),
                'send_physical_document':  send_physical_document,
                'flexible_installation':  flexible_installation,
                'both_parties_present':  both_parties_present,
                'timezone': data.get('timezone', ''),
                'app_version_id':  app_version_id,
                'last_price_quoted_value': data.get('last_price_quoted_value') if 'last_price_quoted_value' in data else 0,
            }
            if destination_selection_id:
                vals.update({'destination_selection_id':  destination_selection_id})
            if completed_date_utc:
                vals.update({'completed_date': completed_date_utc})
            manual_arrival_date = data.get('manual_arrival_date', False)
            manual_arrival_date_utc = manual_arrival_date
            if manual_arrival_date:
                if timezone:
                    manual_arrival_date_utc = self.get_timezone_based_time(manual_arrival_date, timezone)
            if manual_arrival_date_utc:
                vals.update({'manual_arrival_date': manual_arrival_date_utc})
            applicant_first_name = ''
            applicant_last_name = ''
            partner = appointment.partner_id or False
            if not data.get('appointment_result', ''):
                return {'message': 'Appointment Result is missing', 'result': 'Failed'}
            appointment_results_data = self.env["appointment.result"].search_read([], ['result'])
            appointment_results = []
            for value in appointment_results_data:
                appointment_results.append(value.get('result', ''))
            appointment_results.append('Sold')
            if data.get('appointment_result', '') not in appointment_results:
                return {'message': 'Wrong value for Appointment Results', 'result': 'Failed'}
            vals.update({'appointment_result': data.get('appointment_result', 'Sold')})
            if data.get('street', ''):
                vals.update({'street': data.get('street')})
                partner_vals.update({'street': data.get('street')})
            if data.get('street2', ''):
                vals.update({'street2': data.get('street2')})
                partner_vals.update({'street2': data.get('street2')})
            if data.get('city', ''):
                vals.update({'city': data.get('city')})
                partner_vals.update({'city': data.get('city')})
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
            if data.get('state_code', ''):
                state = self.env['res.country.state'].search(
                    [('country_id', '=', 233), ('code', '=', data.get('state_code', '').upper())], limit=1)
                if state:
                    vals.update({
                        'state_id': state.id,
                        'country_id': state.country_id and state.country_id.id or False
                    })
                    partner_vals.update({
                        'state_id': state.id,
                        'country_id': state.country_id and state.country_id.id or False
                    })
                else:
                    vals.update({'state_code': data.get('state_code', '')})
                    partner_vals.update({'state_code': data.get('state_code', '')})
                    # return {'message': 'Wrong State Code', 'result': 'Failed'}
            if data.get('partner_latitude', ''):
                vals.update({'partner_latitude': data.get('partner_latitude')})
            if data.get('partner_longitude', ''):
                vals.update({'partner_longitude': data.get('partner_longitude')})
            if data.get('applicant_first_name', ''):
                vals.update({'applicant_first_name': data.get('applicant_first_name')})
                applicant_first_name = data.get('applicant_first_name')
            if data.get('applicant_middle_name', ''):
                vals.update({'applicant_middle_name': data.get('applicant_middle_name')})
            if data.get('applicant_last_name', ''):
                vals.update({'applicant_last_name': data.get('applicant_last_name')})
                applicant_last_name = data.get('applicant_last_name')
            applicant_name = '%s, %s' % (applicant_last_name, applicant_first_name)
            if applicant_name:
                partner_vals.update({
                    'name': applicant_name,
                })
            customer_name = '%s, %s' % (data.get('applicant_last_name', ''), data.get('applicant_first_name', ''))
            if customer_name:
                vals.update({'customer_name': customer_name})
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
            co_applicant_phone = data.get('co_applicant_phone', "")
            if co_applicant_phone:
                vals.update({'co_applicant_phone': co_applicant_phone})
            co_applicant_email = data.get('co_applicant_email', "")
            if co_applicant_email:
                vals.update({'co_applicant_email': co_applicant_email})
            if data.get('co_applicant_last_name', '') or data.get('co_applicant_first_name', ''):
                vals.update(
                    ({'co_applicant': '%s, %s' % (
                        data.get('co_applicant_last_name', ''), data.get('co_applicant_first_name', ''))}))
            if data.get('co_applicant_state', ''):
                co_applicant_state = self.env['res.country.state'].search(
                    [('country_id', '=', 233), ('code', '=', data.get('co_applicant_state', '').upper())], limit=1)
                if co_applicant_state:
                    vals.update({
                        'co_applicant_state': co_applicant_state.id,
                        'co_applicant_country_id': co_applicant_state.country_id and co_applicant_state.country_id.id or False,
                    })
                else:
                    vals.update({'co_applicant_state_code': data.get('co_applicant_state', '')})
                    # return {'message': 'Wrong Co-Applicant State Code', 'result': 'Failed'}
            if partner_vals:
                if partner:
                    partner.write(partner_vals)
                else:
                    partner = self.env['res.partner'].create(partner_vals)
                    self.env.cr.commit()
                    vals.update({
                        'partner_id': partner.id,
                    })
            if vals:
                vals.update({
                    'write_uid': self.env.user.id,
                    'write_date': datetime.now().replace(tzinfo=pytz.utc)
                })
                appointment.write(vals)
            result = {
                'message': 'Appointment updated successfully',
                'result': 'Success',
            }
        return result

    def action_update_room_measurements(self, room_list, sale_order=False):
        result = {}
        room_measure_obj = self.env['team.contract.room.measurement.line']
        _logger.info('--------------Inside action_update_room_measurements------------')
        room_measure = room_measure_obj.search([('appointment_id', '=', self.id)])
        if room_measure:
            room_measure.unlink()
        transition_lines = self.env['team.contract.transition.line'].search([('appointment_id', '=', self.id)])
        if transition_lines:
            transition_lines.unlink()
        for data in room_list:
            custom_room_measured = int(data.get('is_custom_room', 0)) or 0
            if data.get('room_id', False) or custom_room_measured:
                room_id = int(data.get('room_id', False)) or 0
                if custom_room_measured:
                    room = self.env['team.room.room'].search([('is_custom', '=', True)], limit=1)
                    room_id = room and room.id or 0
                    if not room_id:
                        return {
                            'result': 'Failed',
                            'message': 'Custom Room is not available in the system.'
                        }
                exclude_from_calculation = int(data.get('exclude_from_calculation', 0)) or 0
                room = self.env['team.room.room'].browse(room_id)
                if room.exists():
                    material_id = int(data.get('material_id', 0))
                    vals = {
                        'custom_room_name': data.get('room_name', ''),
                        'comments': data.get('room_comments', ''),
                        'room_area': float(data.get('room_area', 0)),
                        'adjusted_area': float(data.get('room_adjusted_area', 0)),
                        'room_perimeter': float(data.get('room_perimeter', 0)),
                        'exclude_from_calculation': exclude_from_calculation and True or False,
                        'custom_room_measured': custom_room_measured and True or False,
                        'misc_charge_comments': data.get('misc_charge_comments', ''),
                        'delivery_option': data.get('delivery_option', ''),
                    }
                    if material_id and self.env['product.product'].browse(material_id).exists():
                        vals.update({
                            'material_id': material_id,
                            'color_up_charge_price': self.env['product.product'].browse(
                                material_id).color_up_charge_price or 0,
                        })
                        if room.product_category_id.name.upper() != 'VINYL STAIRS':
                            moulding = data.get('moulding_type', '')
                            molding_type = self.env['team.floor.molding'].search([('name', '=', moulding)], limit=1)
                            if self.appointment_result == 'Sold' and not molding_type and not exclude_from_calculation:
                                _logger.info('--------------Molding is not existing------------')
                                return {
                                    'result': 'Failed',
                                    'message': 'Selected Molding is not existing in the system'
                                }
                            vals.update({
                                'molding_type_id': molding_type.id,
                                'molding_unit_price': molding_type.unit_price or 0,
                            })

                    else:
                        _logger.info("------ Material ID Wrong-------------")
                        if self.appointment_result == 'Sold' and not exclude_from_calculation:
                            result = {'message': 'Wrong Material Value', 'result': 'Failed'}
                            return result

                    vals.update({
                        'appointment_id': self.id,
                        'room_id': room_id,
                        'order_id': sale_order and sale_order.id or False
                         })
                    room_measure = room_measure_obj.create(vals)
                    if data.get('transitions', []):
                        for transition_data in data.get('transitions', []):
                            if transition_data.get('name', '') and transition_data.get('width', 0):
                                self.env['team.contract.transition.line'].create({
                                    'name': transition_data.get('name', ''),
                                    'transition_width': float(transition_data.get('width', 0)),
                                    'transition_height': transition_data.get('height', ''),
                                    'transition_height_id': transition_data.get('transition_height_id', False),
                                    'room_measurement_id': room_measure.id,
                                    'room_id': room_id,
                                    'appointment_id': self.id,
                                    'order_id': sale_order and sale_order.id or False
                                })
                    result = {
                        'message': 'Room data updated successfully',
                        'result': 'Success'
                    }
                else:
                    _logger.info("------ Room_id Wrong-------------")
                    result = {'message': 'Wrong Room Value', 'result': 'Failed'}
            else:
                _logger.info("------ Room_id Empty-------------")
                result = {'message': 'Room ID Empty', 'result': 'Failed'}
        _logger.info('--------------Completed: action_update_room_measurements: %s------------'%(result))
        return result

    def action_update_questionnaires(self, questionnaire_list, sale_order=False):
        result = {}
        room_measure_obj = self.env['team.contract.room.measurement.line']
        room_question_obj = self.env['team.contract.question.line']
        answer_obj = self.env['team.contract.answer.line']
        _logger.info('--------------Inside action_update_questionnaires------------')
        room_questions = room_question_obj.search([('appointment_id', '=', self.id)])
        if room_questions:
            room_questions.unlink()
        custom_room = self.env['team.room.room'].search([('is_custom', '=', True)], limit=1)
        for data in questionnaire_list:
            room_name = data.get('room_name', '')
            calculate_order_wise = data.get('calculate_order_wise', 0)
            if data.get('room_id', False) or room_name:
                room_id = int(data.get('room_id', False)) or 0
                if not room_id:
                    room_id = custom_room and custom_room.id or 0
                question_id = int(data.get('question_id', False)) or 0
                answers = data.get('answer', [])
                answer_exists = False
                for answer in answers:
                    if answer:
                        answer_exists = True
                if answer_exists:
                    if self.env['team.room.room'].browse(room_id).exists():
                        if not question_id:
                            _logger.info("------ Question ID Missing-------------")
                            return {'message': 'Question ID Missing', 'result': 'Failed'}
                        if self.env['team.quote.question'].browse(question_id).exists():
                            if room_name:
                                room_measure = room_measure_obj.search(
                                    [('appointment_id', '=', self.id), ('custom_room_name', '=', room_name)], limit=1)
                            else:
                                room_measure = room_measure_obj.search(
                                    [('appointment_id', '=', self.id), ('room_id', '=', room_id)], limit=1)
                            room_question = room_question_obj.create({
                                'room_id': room_id,
                                'question_id': question_id,
                                'room_name': room_name,
                                'room_measurement_id': room_measure and room_measure.id or False,
                                'calculate_order_wise': calculate_order_wise and True or False,
                                'appointment_id': self.id,
                                'order_id': sale_order and sale_order.id or False
                            })
                            for answer in answers:
                                if answer:
                                    answer_record = answer_obj.create({
                                        'question_id': room_question.id,
                                        'answer': answer
                                    })
                            result = {
                                'message': 'Room questionnaire data updated successfully',
                                'result': 'Success'
                            }

                        else:
                            _logger.info("------ Question ID Wrong-------------")
                            result = {'message': 'Question ID Wrong', 'result': 'Failed'}

                    else:
                        _logger.info("------ Room_id Wrong-------------")
                        result = {'message': 'Wrong Room Value', 'result': 'Failed'}
            else:
                _logger.info("------ Room_id Empty-------------")
                result = {'message': 'Room_id Empty', 'result': 'Failed'}
        _logger.info('--------------Completed: action_update_questionnaires: %s------------' % (result))
        return result

    @api.model
    def action_update_customer_and_room_information(self,  data={}):
        result = {
            'message': 'No Data found to update',
            'result': 'Failed'
        }
        _logger.info("------action_update_customer_and_room_information data: %s-------------"%(data))
        try:
            appointment_id = data.get('appointment_id', 0) and int(data.get('appointment_id', 0)) or 0
            if appointment_id:
                appointment = self.browse(appointment_id)
                if appointment.exists():
                    data_completed = data.get('data_completed', 0) and int(data.get('data_completed', 0)) or 0
                    if data.get('rooms', []):
                        room_measure_obj = self.env['team.contract.room.measurement.line']
                        room_measure = room_measure_obj.search([('appointment_id', '=', int(appointment_id))])
                        if room_measure:
                            result = {
                                'message': 'Room data are already updated',
                                'result': 'Success'
                            }
                            _logger.info(
                                "------action_update_customer_and_room_information result: %s-------------" % (result))
                            return result
                    if data.get('customer', {}):
                        appointment_result = appointment.action_update_appointment(data.get('customer', {}))
                        if appointment_result.get('result', False) == 'Success':
                            if data.get('rooms', []):
                                room_measure_result = appointment.action_update_room_measurements(data.get('rooms', []))
                                if room_measure_result.get('result', False) == 'Failed':
                                    return room_measure_result
                                if data.get('answer', []):
                                    room_quesionnaire_result = appointment.action_update_questionnaires(data.get('answer', []))
                                    if room_quesionnaire_result.get('result', False) == 'Failed':
                                        return room_quesionnaire_result
                            result = {
                                'message': 'Customer, Room & Questionnaire data are updated successfully',
                                'result': 'Success'
                            }
                            # if data_completed == 1:
                            #     appointment.write({'start_sync_to_i360': True, 'state': 'done'})
                        else:
                            result= appointment_result
                else:
                    _logger.info("------Wrong Appointment id-------------")
                    result = {
                        'message': 'Wrong Appointment id',
                        'result': 'Failed'
                    }
            else:
                _logger.info("------Empty Appointment id-------------")
                result = {
                    'message': 'Empty Appointment id',
                    'result': 'Failed'
                }
        except:
            result= {
                'message': 'Something went wrong',
                'result': 'Failed'
            }
        _logger.info("------action_update_customer_and_room_information result: %s-------------" % (result))
        return result

    def action_create_sale_order(self, data, execution_order='room_order'):
        status = {
            'message': 'Sale order creation failed due to some unknown reason',
            'result': 'Failed'
        }
        _logger.info('-------create_sale_order data---------')
        _logger.info(data)
        for appointment in self:
            coapplicant_skip = int(data.get('coapplicant_skip', 0))
            appointment_id = appointment.id
            selected_package_id = int(data.get('selected_package_id', 0))
            finance_provider_id = int(data.get('finance_provider_id', 0))
            discount = float(data.get('discount', 0))
            msrp = float(data.get('msrp', 0))
            savings_amount = float(data.get('savings', 0))
            excluded_amount_promotion = float(data.get('excluded_amount_promotion', 0))
            final_sale_price = float(data.get('price', 0))
            adjustment = float(data.get('adjustment', 0))
            additional_cost = float(data.get('additional_cost', 0))
            down_payment_amount = float(data.get('down_payment_amount', 0))
            final_payment = float(data.get('final_payment', 0))
            finance_amount = float(data.get('finance_amount', 0))
            finance_option_id = int(data.get('finance_option_id', 0))
            special_price_id = int(data.get('special_price_id', 0))
            stair_special_price_id = int(data.get('stair_special_price_id', 0))
            promotion_code_id = int(data.get('promotion_code_id', 0))
            loan_payment = float(data.get('loan_payment', 0))
            min_sale_price = float(data.get('min_sale_price', 0))
            calc_based_on = data.get('calc_based_on', 'list_price')
            stair_calc_based_on = data.get('stair_calc_based_on', 'list_price')
            if not min_sale_price:
                min_sale_price = float(self.env['ir.config_parameter'].sudo().get_param('team_sale_contract.min_sale_price')) or 0.0
            if calc_based_on not in ['list_price', 'msrp']:
                _logger.info("------ Wrong value for Calculation Based On-------------")
                status = {'message': 'Wrong value for Calculation Based On', 'result': 'Failed'}
                return status
            if stair_calc_based_on not in ['list_price', 'msrp']:
                _logger.info("------ Wrong value for Stair Calculation Based On-------------")
                status = {'message': 'Wrong value for Stair Calculation Based On', 'result': 'Failed'}
                return status
            sale_order_obj = self.env['sale.order']
            res_partner_obj = self.env['res.partner']
            if not selected_package_id:
                _logger.info("------selected_package_id Empty------------")
                status = {
                    'message': 'selected_package_id Empty',
                    'result': 'Failed',
                }
                return status
            if finance_amount and not finance_option_id:
                _logger.info("------Finance Option ID Empty------------")
                status = {
                    'message': 'Finance Option ID Empty',
                    'result': 'Failed',
                }
                return status
            if finance_option_id and not self.env['team.downpayment.option'].browse(int(finance_option_id)).exists():
                _logger.info("------ Finance Option Not Exist-------------")
                status = {
                    'message': 'Finance Option Not Exist',
                    'result': 'Failed'
                }
                return status
            if special_price_id and not self.env['otl.product.special.price'].browse(int(special_price_id)).exists():
                _logger.info("------ Special Price Not Exist-------------")
                status = {
                    'message': 'Special Price Not Exist',
                    'result': 'Failed'
                }
                return status
            if stair_special_price_id and not self.env['otl.product.special.price'].browse(int(stair_special_price_id)).exists():
                _logger.info("------ Stair Special Price Not Exist-------------")
                status = {
                    'message': 'Stair Special Price Not Exist',
                    'result': 'Failed'
                }
                return status
            if promotion_code_id and not self.env['otl.promotion.code'].browse(int(promotion_code_id)).exists():
                _logger.info("------ Promotion Code is Not Exists-------------")
                status = {
                    'message': 'Promotion Code is Not Exists',
                    'result': 'Failed'
                }
                return status
            if finance_provider_id and not self.env['otl.external.application.credentials'].browse(finance_provider_id).exists():
                _logger.info("------ Finance Provider Not Exist-------------")
                status = {
                    'message': 'Finance Provider Not Exist',
                    'result': 'Failed'
                }
                return status
            if not appointment_id:
                _logger.info("------Appointment ID Empty------------")
                status = {
                    'message': 'Appointment ID Empty',
                    'result': 'Failed',
                }
                return status
            sale_order = self.env['sale.order'].search([('appointment_id', '=', appointment_id)], limit=1)
            if sale_order:
                return {
                    'message': 'Sale order is already existing',
                    'result': 'Success',
                }
            plan = self.env['product.template'].with_context(active_test=False).search([('id', '=', selected_package_id)], limit=1)
            if not plan:
                _logger.info("------Payment Package Not Exist------------")
                status = {
                    'message': 'Payment Package is Not Exists',
                    'result': 'Failed',
                }
                return status
            if not plan.active:
                active_package = self.env['product.template'].search([('grade', '=', plan.grade), ('categ_id', '=', plan.categ_id.id)], limit=1)
                if not active_package:
                    status = {
                        'message': 'No Active Payment Package is Exists',
                        'result': 'Failed',
                    }
                    return status
                selected_package_id = active_package.id
            payment_method = data.get('payment_method', '')
            if payment_method:
                if payment_method not in ['credit_card', 'debit_card', 'cash', 'check', 'finance']:
                    _logger.info("------ Wrong Payment Method-------------")
                    status = {'message': 'Wrong Payment Method', 'result': 'Failed'}
                    return status
            if execution_order == 'room_order':
                team_question_obj = self.env['team.contract.question.line'].search(
                    [('appointment_id', '=', appointment_id)])
                team_room_obj = self.env['team.contract.room.measurement.line'].search(
                    [('appointment_id', '=', appointment_id)])
                room_transition_obj = self.env['team.contract.transition.line'].search(
                    [('appointment_id', '=', appointment_id)])
                if not team_room_obj:
                    status = {
                        'message': 'Room measurement is not existing in corresponding appointment',
                        'result': 'Failed',
                    }
                    return status
                if not team_question_obj:
                    status = {
                        'message': 'Questionnaires is not existing in corresponding appointment',
                        'result': 'Failed',
                    }
                    return status

            sale_order_vals = {
                'cards': False,
                'cash': False,
                'check': False,
                'balance_finance': False,
            }
            discount_history_vals_list = []
            discount_history_list = data.get('discount_history_line', [])
            for history_data in discount_history_list:
                discount_history_vals_list.append((0, 0, {
                    'name': history_data.get('value', ''),
                    'discount_amount': history_data.get('discount_amount', 0),
                    'excluded_amount_discount': history_data.get('excluded_amount_discount', 0),
                    'sale_price': history_data.get('sale_price', 0),
                    'actual_price': history_data.get('actual_price', 0),
                    'type': history_data.get('type', ''),
                    'promo_type': history_data.get('promo_type', False),
                }))
            if discount_history_vals_list:
                sale_order_vals.update({
                    'discount_history_line': discount_history_vals_list
                })

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
            split_name = '%s%s' % (appointment.applicant_first_name and appointment.applicant_first_name[0] or '',
                                   appointment.applicant_last_name and appointment.applicant_last_name[0] or '')
            initials = ''
            if split_name:
                initials = split_name.upper() or ''
            sale_order_vals.update({
                'floor_type': selected_package_id,
                'down_payment_amount': down_payment_amount,
                'final_payment': final_payment,
                'finance_amount': finance_amount,
                'discount': discount,
                'additional_cost': additional_cost,
                'finance_option_id': finance_option_id or False,
                'special_price_id': special_price_id or False,
                'stair_special_price_id': stair_special_price_id or False,
                'promotion_code_id': promotion_code_id or False,
                'finance_provider_id': finance_provider_id or False,
                'calc_based_on': calc_based_on,
                'stair_calc_based_on': stair_calc_based_on,
                'balance_payment_method': payment_method,
                'adjustment': adjustment,
                'loan_payment': loan_payment,
                'min_sale_price': min_sale_price,
                'msrp_amount': msrp,
                'savings_amount': savings_amount,
                'excluded_amount_promotion': excluded_amount_promotion,
                'final_sale_price': final_sale_price,
                'one_year_price': msrp+additional_cost,
                'coapplicant_skip': True if coapplicant_skip == 1 else False,
                'applicant_inititals': initials or '',
                'write_uid': self.env.user.id,
                'write_date': datetime.now().replace(tzinfo=pytz.utc)
            })

            if not sale_order:
                if appointment.partner_id:
                    customer = appointment.partner_id
                else:
                    partner_vals = {
                        'name': appointment.customer_name,
                        'phone': appointment.phone,
                        'mobile': appointment.mobile,
                        'street': appointment.street,
                        'street2': appointment.street2,
                        'city': appointment.city,
                        'state_id': appointment.state_id.id or False,
                        'state_code': appointment.state_code,
                        'zip': appointment.zip,
                        'country_id': appointment.country_id.id or False,
                        'email': appointment.email
                    }
                    if partner_vals:
                        customer = res_partner_obj.create(partner_vals)
                        if customer:
                            appointment.write({'partner_id': customer.id})

                sale_order_vals.update({
                    'partner_id': customer.id,
                    'floor_type': selected_package_id,
                    'appointment_id': appointment_id,
                })
                sale_order = sale_order_obj.create(sale_order_vals)
                self.env.cr.commit()
                _logger.info("------Sale Order Created: %s------------"%(sale_order))
            else:
                if sale_order.state != 'draft':
                    sale_order.write({'state': 'draft'})
                if sale_order.order_line:
                    sale_order.order_line.unlink()
                if sale_order.discount_history_line:
                    sale_order.discount_history_line.unlink()
                if sale_order_vals:
                    sale_order.write(sale_order_vals)
            if execution_order == 'room_order':
                if team_question_obj:
                    team_question_obj.write({'order_id': sale_order.id})
                if team_room_obj:
                    team_room_obj.write({'order_id': sale_order.id})
                if room_transition_obj:
                    room_transition_obj.write({'order_id': sale_order.id})

                _logger.info("------Sale Order updated------------")
                sale_order.add_payment_line(discount, adjustment, additional_cost, plan.monthly_promo, 0, final_sale_price)

            status = {
                'message': ' Payment plan details are updated successfully',
                'result': 'Success',
                'order_id': sale_order.id
            }
        return status

    @api.model
    def action_update_contract_information(self, data={}):
        result = {
            'message': 'No Data found to update',
            'result': 'Failed'
        }
        _logger.info("------action_update_contract_information data: %s-------------" % (data))
        try:
            appointment_id = data.get('appointment_id', 0) and int(data.get('appointment_id', 0)) or 0
            if appointment_id:
                appointment = self.browse(appointment_id)
                if appointment.exists():
                    if data.get('paymentdetails', {}):
                        order_result = appointment.action_create_sale_order(data.get('paymentdetails', {}))
                        if order_result.get('result', '') == 'Success':
                            order_id = order_result.get('order_id', False)
                            order = self.env['sale.order'].browse(order_id)
                            if order.down_payment_amount:
                                if data.get('paymentmethod', {}):
                                    payment_result = order.action_update_payment_data(data.get('paymentmethod', {}))
                                    if payment_result.get('result', '') == 'Success':
                                        if data.get('applicationInfo', {}):
                                            credit_application_result =  order.action_create_credit_application(data.get('applicationInfo', {}))
                                            if credit_application_result.get('result', '') == 'Failed':
                                                return credit_application_result
                                    else:
                                        return payment_result
                                else:
                                    if appointment.appointment_result == 'Sold':
                                        result = {
                                            'message': 'Payment method Details are missing',
                                            'result': 'Failed'
                                        }
                                result = {
                                    'message': 'Order details updated successfully',
                                    'result': 'Success'
                                }
                            else:
                                if data.get('applicationInfo', {}):
                                    credit_application_result = order.action_create_credit_application(
                                        data.get('applicationInfo', {}))
                                    if credit_application_result.get('result', '') == 'Failed':
                                        return credit_application_result
                                result = {
                                    'message': 'Order Data are updated successfully',
                                    'result': 'Success'
                                }

                            # if data.get('data_completed', 0) and int(data.get('data_completed', 0)) == 1:
                            #     appointment.write({'start_sync_to_i360': True, 'state': 'done'})
                        else:
                            return order_result
                    else:
                        result = {
                            'message': 'Payment Details are missing',
                            'result': 'Failed'
                        }
                else:
                    _logger.info("------Wrong Appointment id-------------")
                    result = {
                        'message': 'Wrong Appointment id',
                        'result': 'Failed'
                    }
            else:
                _logger.info("------Empty Appointment id-------------")
                result = {
                    'message': 'Empty Appointment id',
                    'result': 'Failed'
                }
        except:
            result= {
                'message': 'Something went wrong',
                'result': 'Failed'
            }
        _logger.info("------action_update_contract_information result: %s-------------" % (result))
        return result

    @api.model
    def action_link_uploaded_image(self, data):
        result = {
            'message': 'Something went wrong while uploading the images',
            'result': 'Failed'
        }
        _logger.info("------action_link_uploaded_image data: %s-------------" % (data))
        appointment_id = data.get('appointment_id', 0) and int(data.get('appointment_id', 0)) or 0
        room_id = data.get('room_id', 0) and int(data.get('room_id', 0)) or 0
        room_name = data.get('room_name', '')
        image_type = data.get('image_type', '')
        image_name = data.get('image_name', '')
        attachment_id = data.get('attachment_id', False)
        room_measure_obj = self.env['team.contract.room.measurement.line']
        if not attachment_id:
            _logger.info("------Empty attachment_id id-------------")
            return {
                'message': 'Empty attachment_id',
                'result': 'Failed'
            }
        attachment = self.env['ir.attachment'].browse(attachment_id)
        if attachment and not attachment.datas:
            return {
                'message': 'Attachment has no content. Due to some error file content is not stored in Odoo.',
                'result': 'Failed'
            }
        if not image_type:
            return {
                'message': 'Empty Image Type',
                'result': 'Failed'
            }
        if not image_name:
            return {
                'message': 'Empty Image Name',
                'result': 'Failed'
            }
        if image_type in ['room_photo', 'measurement_image', 'protrusion_image']:
            if not room_name and not room_id:
                return {
                    'message': 'Either Room ID or Room Name is required',
                    'result': 'Failed'
                }
        if appointment_id:
            appointment = self.browse(appointment_id)
            room_measure_vals = {}
            appointment_vals = {}
            if appointment.exists():
                if image_type == 'snapshot':
                    appointment_vals.update({'attachment_ids': [(4, attachment_id)]})
                elif image_type == 'applicant_signature':
                    if appointment.applicant_signature_id:
                        appointment.applicant_signature_id.sudo().unlink()
                    appointment_vals.update({'applicant_signature_id': attachment_id})
                elif image_type == 'applicant_initial':
                    if appointment.applicant_initial_id:
                        appointment.applicant_initial_id.sudo().unlink()
                    appointment_vals.update({'applicant_initial_id': attachment_id})
                elif image_type == 'co_applicant_signature':
                    if appointment.co_applicant_signature_id:
                        appointment.co_applicant_signature_id.sudo().unlink()
                    appointment_vals.update({'co_applicant_signature_id': attachment_id})
                elif image_type == 'co_applicant_initial':
                    if appointment.co_applicant_initial_id:
                        appointment.co_applicant_initial_id.sudo().unlink()
                    appointment_vals.update({'co_applicant_initial_id': attachment_id})
                elif image_type in ['room_photo', 'measurement_image', 'protrusion_image']:
                    if not room_name:
                        if not self.env['team.room.room'].browse(room_id).exists():
                            return {
                                'message': 'Room ID is Wrong',
                                'result': 'Failed'
                            }
                    if room_name:
                        room_measure = room_measure_obj.search(
                            [('appointment_id', '=', appointment_id), ('custom_room_name', '=', room_name)], limit=1)
                    else:
                        room_measure = room_measure_obj.search(
                            [('appointment_id', '=', appointment_id), ('room_id', '=', room_id)], limit=1)
                    if not room_measure or not room_measure.exists():
                        return {
                            'message': 'Room Measurement is not existing for given Room',
                            'result': 'Failed'
                        }
                    if image_type == 'measurement_image':
                        if room_measure.shape_image_id:
                            room_measure.shape_image_id.sudo().unlink()
                        room_measure_vals.update({'shape_image_id': attachment_id})
                    elif image_type == 'protrusion_image':
                        room_measure_vals.update({'protrusion_image_ids': [(4, attachment_id)]})
                    else:
                        room_measure_vals.update({'attachment_ids': [(4, attachment_id)]})
                    if room_measure_vals:
                        room_measure_vals.update({'write_uid': self.env.user.id, 'write_date': datetime.now().replace(tzinfo=pytz.utc)})
                        _logger.info("------Before write, Room Measure ID: %s-------------"%(room_measure.id))
                        room_measure.write(room_measure_vals)
                        _logger.info("------After write, Room Measure ID: %s-------------"%(room_measure.id))
                if appointment_vals:
                    appointment_vals.update({'write_uid': self.env.user.id, 'write_date': datetime.now().replace(tzinfo=pytz.utc)})
                    appointment.write(appointment_vals)
                result= {
                    'message': 'File upload successfully',
                    'result': 'Success',
                    'image_name': image_name
                }
                # if data.get('data_completed', 0) and int(data.get('data_completed', 0)) == 1:
                #     appointment.write({'start_sync_to_i360': True, 'state': 'done'})
                _logger.info("------Image Linked Successfully-------------")
            else:
                _logger.info("------Wrong Appointment id-------------")
                result = {
                    'message': 'Wrong Appointment id',
                    'result': 'Failed'
                }
        else:
            _logger.info("------Empty Appointment id-------------")
            result = {
                'message': 'Empty Appointment id',
                'result': 'Failed'
            }
        return result

    def action_sync_sale_data_to_i360(self, appointment, sale_order, return_on_failure=False):
        sync_log = self.env['otl.appointment.sync.log']
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
                if return_on_failure:
                    return {
                        'message': 'UpdateAppointmentProspect Failed due to following reason: %s'%(result),
                        'result': 'Failed'
                    }
        if sale_order and appointment:
            if sale_order.appointment_result:
                if not appointment.status_updated_to_i360:
                    notes = {
                        'last_price_quoted_value': appointment.last_price_quoted_value or 0
                    }
                    if appointment.what_happened_notes and appointment.whats_next_notes:
                        notes.update({
                            'what_happened_notes': appointment.what_happened_notes,
                            'whats_next_notes': appointment.whats_next_notes,
                        })
                    if appointment.resulting_reason_id:
                        notes.update({
                            'result_details': appointment.resulting_reason_id.name,
                        })
                    response_result = sale_order.set_appointment_result_api(sale_order.appointment_result, notes=notes)
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
                sale_order_vals = {}
                included_room_measurement_lines = sale_order.room_measurement_line.filtered(
                    lambda x: not x.exclude_from_calculation)
                excluded_room_measurement_lines = sale_order.room_measurement_line.filtered(
                    lambda x: x.exclude_from_calculation)
                if (included_room_measurement_lines and not sale_order.quote_id) or (excluded_room_measurement_lines  and not sale_order.excluded_quote_id):
                    if sale_order.appointment_result == 'Sold':
                        if sale_order.state != 'sale' and sale_order.payment_method in ['credit_card',
                                                         'debit_card'] and sale_order.down_payment_amount and not sale_order.card_transaction_log_line.filtered(
                                lambda x: x.state == 'success'):
                            sale_order.action_confirm()
                        else:
                            sale_order.confirm_order_and_create_invoice()
                        response_result = sale_order.add_sale_api()
                        _logger.info('-------i360 AddSale Response: %s' % (response_result))
                        if response_result.get('success', '') == 'true':
                            sync_log.create({
                                'appointment_id': appointment.id,
                                'response': response_result,
                                'name': 'AddSale',
                            })
                            if response_result.get('duplicate', '') == 'true':
                                _logger.info('-------Sync Aborting due to Duplicate Sale - %s, Response: %s' % (
                                sale_order.id, response_result))
                                return True
                        else:
                            sync_log.create({
                                'appointment_id': appointment.id,
                                'response': response_result,
                                'state': 'failed',
                                'name': 'AddSale',
                            })
                            if return_on_failure:
                                return {
                                    'message': 'AddSale Failed due to following reason: %s' % (
                                        response_result),
                                    'result': 'Failed'
                                }
                    else:
                        
                        if (included_room_measurement_lines and not sale_order.quote_id) or (excluded_room_measurement_lines  and not sale_order.excluded_quote_id):
                            response_result = sale_order.add_quote_sales_app(sale_order.appointment_result)
                            _logger.info('-------i360 AddQuote Response: %s' % (response_result))
                            if response_result.get('success', '') == 'true':
                                sync_log.create({
                                    'appointment_id': appointment.id,
                                    'response': response_result,
                                    'name': 'AddQuote',
                                })
                                if response_result.get('duplicate', '') == 'true':
                                    _logger.info('-------Sync Aborting due to Duplicate Quote - %s, Response: %s' % (
                                    sale_order.id, response_result))
                            else:
                                sync_log.create({
                                    'appointment_id': appointment.id,
                                    'response': response_result,
                                    'state': 'failed',
                                    'name': 'AddQuote',
                                })
                                if return_on_failure:
                                    return {
                                        'message': 'AddQuote Failed due to following reason: %s' % (
                                            response_result),
                                        'result': 'Failed'
                                    }

                room_measurement_lines_to_sync = sale_order.room_measurement_line.filtered(lambda x: not x.improveit_id)
                if room_measurement_lines_to_sync:
                    if sale_order.appointment_result == 'Sold':
                        if room_measurement_lines_to_sync.filtered(lambda x: not x.improveit_id):
                            response_result = sale_order.add_sale_items_api()
                            _logger.info('-------i360 AddSaleItem Response: %s' % (response_result))
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
                                if return_on_failure:
                                    return {
                                        'message': 'AddSaleItem Failed due to following reason: %s' % (
                                            response_result),
                                        'result': 'Failed'
                                    }
                    else:
                        response_result = sale_order.add_quote_items_sales_app()
                        _logger.info('-------i360 AddQuoteItem Response: %s' % (response_result))
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
                            if return_on_failure:
                                return {
                                    'message': 'AddSaleItem Failed due to following reason: %s' % (
                                        response_result),
                                    'result': 'Failed'
                                }
        return {
            'message': 'Data synced successfully to i360',
            'result': 'Success'
        }



    def action_start_sync_to_i360(self, appointment_id, sale_order_id):
        time.sleep(3)
        # Create new cursor
        # new_cr = self.pool.cursor()
        try:
            # Switch to environment with new cursor 
            # self = self.with_env(self.env(cr=new_cr))
            # As this function is in a new thread, I need to open a new cursor, because the old one may be closed
            new_cr = self.pool.cursor()
            self = self.with_env(self.env(cr=new_cr))
            sync_log = self.env['otl.appointment.sync.log']
            _logger.info('------Starting action_start_sync_to_i360------: %s'%(sale_order_id))
            appointment = self.env['team.customer.appointment'].browse(int(appointment_id))
            sale_order = self.env['sale.order'].browse(int(sale_order_id))
            sale_sync_result = self.action_sync_sale_data_to_i360(appointment, sale_order)
            if sale_order and appointment:
                if sale_order.appointment_result:
                    team_credit_application = self.env['team.credit.application'].search(
                        [('appointment_id', '=', int(appointment_id))], limit=1)
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
                    ext_credit_application = self.env['otl.versatile.credit.application'].search(
                        [('appointment_id', '=', int(appointment_id)), ('status', '=ilike', 'approved')], limit=1)
                    if ext_credit_application and not ext_credit_application.improveit_id:
                        result = sale_order.action_sync_ext_loan_data_to_i360(ext_credit_application)
                        if result.get('success', '') == 'true':
                            _logger.info("------ SyncLoanData Create,Update Success-------------")
                            sync_log.create({
                                'appointment_id': appointment.id,
                                'response': result,
                                'name': 'SyncLoanData',
                            })
                        else:
                            _logger.info("------ SyncLoanData Create,Update Failed-------------")
                            sync_log.create({
                                'appointment_id': appointment.id,
                                'response': result,
                                'state': 'failed',
                                'name': 'SyncLoanData',
                            })
                    if (sale_order.discount_history_line or sale_order.promotion_code_id) and not sale_order.discount_history_sync_i360_ref:
                        result = sale_order.action_sync_discount_history_line_to_i360()
                        if result.get('success', '') == 'true':
                            _logger.info("------ AppliedDiscounts Create,Update Success-------------")
                            sync_log.create({
                                'appointment_id': appointment.id,
                                'response': result,
                                'name': 'AppliedDiscounts',
                            })
                        else:
                            _logger.info("------ AppliedDiscounts Create,Update Failed-------------")
                            sync_log.create({
                                'appointment_id': appointment.id,
                                'response': result,
                                'state': 'failed',
                                'name': 'AppliedDiscounts',
                            })
                    sale_order_vals = {}
                    if sale_order.appointment_result == 'Sold':
                        if appointment.card_transaction_log_line.filtered(
                                lambda x: x.state == 'failed' and not x.synced):
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
                            model_id = self.env['ir.model'].sudo().search([('model', '=', 'sale.order')], limit=1)
                            sign_request = self.env['otl_document_sign.request'].sudo().search(
                                [('model_id', '=', model_id.id), ('res_id', '=', sale_order.id)],
                                order='create_date desc',
                                limit=1)
                            if sign_request:

                                if sign_request.state == 'signed':
                                    if not sign_request.completed_document:
                                        sign_request.generate_completed_document()
                                    contract_doc_attachment = sign_request.document_image()
                                    sale_order.write(
                                        {'contract_doc_attachment_id': contract_doc_attachment.id,
                                         'document_signed': True})
                        if contract_doc_attachment:
                            if not sale_order.contract_document_uploaded or not contract_doc_attachment.improveit_id:
                                result = sale_order.action_sync_contract_doc_on_i360()
                                _logger.info('-------i360 salesapp call contract_doc_upload_response Response: %s' % (result))
                                if result.get('success', '') == 'true':
                                    sale_order_vals.update({'contract_document_uploaded': True})

                            if not sale_order.email_sent:
                                result = sale_order.add_contract_document_file()
                                if result.get('success', '') == 'true':
                                    sync_log.create({
                                        'appointment_id': appointment.id,
                                        'response': result,
                                        'name': 'Send Contract Email To Customer',
                                    })
                                else:
                                    sync_log.create({
                                        'appointment_id': appointment.id,
                                        'response': result,
                                        'state': 'failed',
                                        'name': 'Send Contract Email To Customer',
                                    })
                    if not sale_order.other_files_uploaded:
                        if sale_order.state in ['sale', 'done'] or sale_order.appointment_result == 'Sold':
                            result = sale_order.add_sale_id_file()
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
                            result = sale_order.add_quote_id_file(document=False)
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
                    # enable_additional_comment_api = eval(
                    #     str(self.env['ir.config_parameter'].sudo().get_param('enable_additional_comment_api')))
                    enable_additional_comment_api = str2bool(self.env['ir.config_parameter'].sudo().get_param('team_sale_contract.enable_additional_comment_api'))
                    if sale_order.appointment_result == 'Sold' and enable_additional_comment_api and not sale_order.additional_comment_synced:
                        result = sale_order.create_additional_comments_in_i360()
                        if result.get('success', '') == 'true':
                            sync_log.create({
                                'appointment_id': appointment.id,
                                'response': result,
                                'name': 'AddSaleComments',
                            })
                        else:
                            sync_log.create({
                                'appointment_id': appointment.id,
                                'response': result,
                                'state': 'failed',
                                'name': 'AddSaleComments',
                            })
                    if appointment.destination_selection_id and not sale_order.update_destination_selection_synced:
                        result = sale_order.update_destination_selection_in_i360()
                        if result.get('success', '') == 'true':
                            sync_log.create({
                                'appointment_id': appointment.id,
                                'response': result,
                                'name': 'UpdateDestinationSelection',
                            })
                        else:
                            sync_log.create({
                                'appointment_id': appointment.id,
                                'response': result,
                                'state': 'failed',
                                'name': 'UpdateDestinationSelection',
                            })
                    if sale_order_vals:
                        sale_order_vals.update({
                            'write_uid': self.env.user.id,
                            'write_date': datetime.now().replace(tzinfo=pytz.utc)
                        })
                        sale_order.write(sale_order_vals)
                        if sale_order.check_document_upload_completed():
                            sale_order.write({
                                'is_data_upload_completed': True,
                                'write_uid': self.env.user.id,
                                'write_date': datetime.now().replace(tzinfo=pytz.utc)
                            })
                    self.env.cr.commit()
            new_cr.close()
            _logger.info('------End of action_start_sync_to_i360------: %s' % (sale_order_id))
        except Exception as e:
            _logger.info('------Exception in action_start_sync_to_i360------: %s' % (e))
            new_cr.rollback()
        return True

    @api.model
    def action_initiate_sync_to_i360(self, data = {}):
        result = {
            'message': 'Something went wrong while initiating sync to i360',
            'result': 'Failed'
        }
        sync_delay = int(data.get('sync_delay', 1))
        _logger.info("-------sync_delay time: %s"%(sync_delay))
        time.sleep(sync_delay)
        _logger.info("------action_initiate_sync_to_i360 data: %s-------------" % (data))
        appointment_id = data.get('appointment_id', 0) and int(data.get('appointment_id', 0)) or 0
        screen_log_obj = self.env['otl.app.screen.log']
        res_partner_obj = self.env['res.partner']
        sale_order_obj = self.env['sale.order']
        screen_logs = data.get('screen_logs', [])
        appointment_result = data.get('appointment_result', '')
        if appointment_id:
            appointment = self.browse(appointment_id)
            if appointment.exists():
                if appointment.start_sync_to_i360:
                    _logger.info("------Sync is already initiated for the appointment %s-------------"%(appointment.id))
                    result = {
                        'message': 'Sync is already initiated for the appointment %s'%(appointment.id),
                        'result': 'Success'
                    }
                else:
                    # try:
                    vals = {
                        'start_sync_to_i360': True,
                        'state': 'done',
                        'sync_initiated_date': fields.Datetime.now()
                    }
                    if appointment_result and appointment_result != appointment.appointment_result:
                        vals.update({'appointment_result': data.get('appointment_result', '')})
                    appointment.write(vals)
                    if appointment.app_screen_log_line:
                        appointment.app_screen_log_line.unlink()
                    timezone = appointment.timezone
                    for log in screen_logs:
                        completion_date = log.get('completion_time', '')
                        completion_date_utc = completion_date
                        if completion_date:
                            if timezone:
                                completion_date_utc = self.get_timezone_based_time(completion_date, timezone)
                        screen_log_obj.create({
                            'appointment_id': appointment.id,
                            'name': log.get('screen_name', ''),
                            'completion_date': completion_date_utc,
                        })

                    sale_order = sale_order_obj.search([('appointment_id', '=', appointment_id)], limit=1)
                    if not sale_order:
                        sale_order_vals = {
                            'cards': False,
                            'cash': False,
                            'check': False,
                            'balance_finance': False,
                        }
                        split_name = '%s%s' % (
                        appointment.applicant_first_name and appointment.applicant_first_name[0] or '',
                        appointment.applicant_last_name and appointment.applicant_last_name[0] or '')
                        initials = ''
                        if split_name:
                            initials = split_name.upper() or ''
                        if appointment.partner_id:
                            customer = appointment.partner_id
                        else:
                            partner_vals = {
                                'name': appointment.customer_name,
                                'phone': appointment.phone,
                                'mobile': appointment.mobile,
                                'street': appointment.street,
                                'street2': appointment.street2,
                                'city': appointment.city,
                                'state_id': appointment.state_id.id or False,
                                'state_code': appointment.state_code,
                                'zip': appointment.zip,
                                'country_id': appointment.country_id.id or False,
                                'email': appointment.email
                            }
                            if partner_vals:
                                customer = res_partner_obj.create(partner_vals)
                                if customer:
                                    appointment.write({'partner_id': customer.id})

                        sale_order_vals.update({
                            'partner_id': customer.id,
                            'appointment_id': appointment_id,
                        })
                        sale_order = sale_order_obj.create(sale_order_vals)
                        self.env.cr.commit()
                        _logger.info("------Sale Order Created: %s------------" % (sale_order))
                        team_question_obj = self.env['team.contract.question.line'].search(
                            [('appointment_id', '=', int(appointment_id))])
                        team_room_obj = self.env['team.contract.room.measurement.line'].search(
                            [('appointment_id', '=', int(appointment_id))])
                        room_transition_obj = self.env['team.contract.transition.line'].search(
                            [('appointment_id', '=', int(appointment_id))])
                        if team_question_obj:
                            team_question_obj.write({'order_id': sale_order.id})
                        if team_room_obj:
                            team_room_obj.write({'order_id': sale_order.id})
                        if room_transition_obj:
                            room_transition_obj.write({'order_id': sale_order.id})
                    if sync_delay >= 1:
                        t1 = threading.Thread(target=self.action_start_sync_to_i360, args=(appointment.id, sale_order.id))
                        t1.start()
                        _logger.info("thread %s started!" % t1)
                    result = {
                        'message': 'Data sync successfully to i360',
                        'result': 'Success'
                    }
                    # except:
                    #     self.env.cr.rollback()
                    #     appointment.write({'start_sync_to_i360': True, 'state': 'done'})
                    #     _logger.info("------Exception occurred in action_initiate_sync_to_i360-------------")
                    #     result = {
                    #         'message': 'Exception occurred in action_initiate_sync_to_i360',
                    #         'result': 'Failed'
                    #     }
            else:
                _logger.info("------Wrong Appointment id-------------")
                result = {
                    'message': 'Wrong Appointment id',
                    'result': 'Failed'
                }
        else:
            _logger.info("------Empty Appointment id-------------")
            result = {
                'message': 'Empty Appointment id',
                'result': 'Failed'
            }
        return result

    @api.model
    def action_update_sync_log(self, logs):
        result = {
            'message': 'Something went wrong while initiating sync logs',
            'result': 'Failed'
        }
        _logger.info("------action_update_sync_log data: %s-------------" % (logs))
        sync_log_obj = self.env['otl.app.appointment.sync.log']
        data_created=False
        for data in logs:
            appointment_id = data.get('appointment_id', 0) and int(data.get('appointment_id', 0)) or 0
            if appointment_id:
                appointment = self.sudo().browse(appointment_id)
                if appointment.exists():
                    sync_date = data.get('sync_time', '')
                    message = data.get('message', '')
                    if not sync_date:
                        return {
                            'message': 'Sync Date is missing',
                            'result': 'Failed'
                        }
                    if not message:
                        return {
                            'message': 'Sync Message is missing',
                            'result': 'Failed'
                        }
                    sync_date_utc = sync_date
                    timezone = appointment.timezone
                    completed_date_utc = False
                    if sync_date:
                        if timezone:
                            sync_date_utc = self.get_timezone_based_time(sync_date, timezone)
                    sync_log_obj.create({
                        'appointment_id': appointment_id,
                        'sync_date': sync_date_utc,
                        'name': message,
                    })
                    data_created = True
                else:
                    _logger.info("------Wrong Appointment id-------------")
                    return {
                        'message': 'Wrong Appointment id',
                        'result': 'Failed'
                    }
            else:
                _logger.info("------Empty Appointment id-------------")
                return {
                    'message': 'Empty Appointment id',
                    'result': 'Failed'
                }
        if data_created:
            result= {
                'message': 'Logs Uploaded Successfully',
                'result': 'Success'
            }
        return result

    @api.model
    def action_generate_contract_document_manually(self):
        """
        Script for generating contract document manually from API data
        :return:
        """
        for record in self:
            order = record.sale_order_ids[0]
            contract_document_creation_log = self.env['otl.api.sync.log'].search(
                [('name', '=', '/api/generate_contract_document'), ('appointment_id', '=', record.id)], limit=1)
            if contract_document_creation_log and contract_document_creation_log.data:
                data = eval(contract_document_creation_log.data)
                order.action_generate_contract_document(data)
        return True

    @api.model
    def action_room_questionnaire_manual_update(self, api_name):
        """
        Script for updating sale order manually from API data
        :param api_name:
        :return:
        """
        for record in self:
            order = record.sale_order_ids[0]
            order_creation_log = self.env['otl.api.sync.log'].search([('name', '=', api_name), ('appointment_id', '=', record.id)], limit=1)
            if order_creation_log and order_creation_log.data:
                data = eval(order_creation_log.data)
                room_list = data.get('rooms', [])
                if room_list:
                    record.action_update_room_measurements(room_list, order)
                answer_list = data.get('answer', [])
                if answer_list:
                    record.action_update_questionnaires(answer_list, order)
                if order.state != 'draft':
                    order.write({'state': 'draft'})
                if order.floor_type:
                    order.add_payment_line(order.discount, order.adjustment, order.additional_cost, 0, 0, order.final_sale_price)
                for room_data in room_list:
                    room_id = room_data.get('room_id', False)
                    room_measurement_line = order.room_measurement_line.filtered(
                        lambda x: x.room_id.id == int(room_id))
                    if room_measurement_line:
                        measurement_image = self.env['ir.attachment'].search(
                            [('appointment_id', '=', record.id),
                             ('name', '=', room_data.get('room_area_image', ''))])
                        if measurement_image and not room_measurement_line.shape_image_id:
                            room_measurement_line.write({'shape_image_id': measurement_image.id})
                        room_images = self.env['ir.attachment'].search(
                            [('appointment_id', '=', record.id),
                             ('name', 'in', room_data.get('room_image_names', []))])
                        if room_images and not room_measurement_line.attachment_ids:
                            room_measurement_line.write({'attachment_ids': [(6, 0, room_images.ids)]})
                if order.down_payment_amount and not order.payment_method:
                    if data.get('paymentmethod', {}):
                        payment_result = order.action_update_payment_data(data.get('paymentmethod', {}))
                        order_values = payment_result.get('values', {})
                        if order_values:
                            order.write(order_values)
                if data.get('applicationInfo', {}):
                    credit_application = self.env['team.credit.application'].search(
                        [('appointment_id', '=', record.id)], limit=1)
                    if not credit_application:
                        credit_application_result = order.action_create_credit_application(
                            data.get('applicationInfo', {}))
        return True

    @api.model
    def action_create_order_and_update_measurements(self, data={}):
        result = {
            'message': 'No Data found to update',
            'result': 'Failed'
        }
        payment_status = 'Not Done'
        payment_message = 'Payment is not Done'
        success_msg = 'Order details updated successfully'
        _logger.info("------action_create_order_and_update_measurements data: %s-------------" % (data))
        sale_order_obj = self.env['sale.order']
        # accepted values - online, offline
        operation_mode = data.get('operation_mode', 'offline')
        app_version = data.get('app_version', '')
        transaction_id = 'Invalid'
        card_type = ''
        try:
            appointment_id = data.get('appointment_id', 0) and int(data.get('appointment_id', 0)) or 0
            if appointment_id:
                appointment = self.browse(appointment_id)
                if appointment.exists():
                    order = self.env['sale.order'].search([('appointment_id', '=', appointment_id)], limit=1)
                    if order:
                        payment_method_dict = data.get('paymentmethod', {})
                        paymentdetails_dict = data.get('paymentdetails', {})
                        credit_application_dict = data.get('applicationInfo', {})
                        payment_transaction_info_dict = data.get('payment_transaction_info', {})
                        rooms_list = data.get('rooms', [])
                        answer_list = data.get('answer', [])
                        customer_dict = data.get('customer', {})
                        if customer_dict.get('appointment_result', '') and appointment.appointment_result != customer_dict.get('appointment_result', ''):
                            appointment_result = appointment.action_update_appointment(customer_dict, app_version)
                            if appointment_result.get('result', False) == 'Failed':
                                appointment_result.update({
                                    'payment_status': payment_status,
                                    'payment_message': payment_message,
                                })
                                return appointment_result
                        existing_auth_transaction_id = ''
                        if payment_transaction_info_dict:
                            existing_auth_transaction_id = payment_transaction_info_dict.get('authorize_transaction_id', 0)
                            card_type = payment_transaction_info_dict.get('card_type', '')
                        invoice_created = False
                        if order.order_line.filtered(lambda x: x.invoice_lines):
                            invoice_created = True
                        retry_order_creation = False
                        if payment_method_dict and paymentdetails_dict and not existing_auth_transaction_id:
                            payment_method = payment_method_dict.get('payment_method', '')
                            down_payment_amount = float(paymentdetails_dict.get('down_payment_amount', 0))
                            if order.payment_method in ['credit_card', 'debit_card', 'ach'] and down_payment_amount and not order.card_transaction_log_line.filtered(lambda x: x.state == 'success'):
                                retry_order_creation = True
                            elif order.payment_method in ['credit_card', 'debit_card', 'ach'] and down_payment_amount and order.card_transaction_log_line.filtered(lambda x: x.state == 'success') and order.payment_method != payment_method:
                                retry_order_creation = True
                            elif order.payment_method in ['credit_card', 'debit_card', 'ach'] and down_payment_amount and order.card_transaction_log_line.filtered(lambda x: x.state == 'success') and order.payment_method == payment_method and down_payment_amount == order.down_payment_amount:
                                return {
                                    'message': 'Order details are already updated successfully.',
                                    'result': 'Success',
                                    'payment_status': 'Success',
                                    'payment_message': "Payment is already processed.",
                                }

                        if (operation_mode == 'online' or (invoice_created and retry_order_creation)) and not existing_auth_transaction_id:
                            valid_transactions_lines = appointment.card_transaction_log_line.filtered(lambda x:x.state == 'success' and not x.void_transaction)
                            for line in valid_transactions_lines:
                                authorize_transaction_id = line.name or ''
                                if authorize_transaction_id:
                                    acquirer = self.env.ref('payment.payment_provider_authorize').sudo()
                                    if line.provider_id:
                                        acquirer = line.provider_id.sudo()
                                    if acquirer.code == 'authorize':
                                        transaction = AuthorizeAPICustom(acquirer)
                                        response = transaction.void(authorize_transaction_id or '')
                                        if response.get('x_trans_id', ''):
                                            line.write({
                                                'void_transaction': True,
                                                'void_transaction_id': response.get('x_trans_id', '')
                                            })
                                        elif response.get('x_response_code', ''):
                                            line.write({
                                                'error_code': response.get('x_response_reason_text', '')
                                            })
                                    elif acquirer.code == 'cardpoint':
                                        response = acquirer._cardpoint_void_transaction(order.authorize_transaction_id)
                                        if response.get('respstat', '') == 'A':
                                            line.write({
                                                'void_transaction': True,
                                                'void_transaction_id': response.get('retref', '')
                                            })
                                        elif response.get('respstat', '') != 'A':
                                            line.write({
                                                'error_code': response.get('resptext', '')
                                            })

                            order.action_cancel()
                            order.action_draft()
                            order.write({'active': False})
                        else:
                            if not retry_order_creation:
                                if credit_application_dict:
                                    credit_application = self.env['team.credit.application'].search([('appointment_id', '=', appointment_id)],
                                                                                     limit=1)
                                    if not credit_application:
                                        credit_application_result = order.action_create_credit_application(credit_application_dict)
                                        if credit_application_result.get('result', '') == 'Failed':
                                            credit_application_result.update({
                                                'payment_status': payment_status,
                                                'payment_message': payment_message,
                                            })
                                            return credit_application_result
                                if order.state != 'draft':
                                    order.write({'state': 'draft'})
                                room_measure_result = {}
                                if rooms_list:
                                    all_room_updated = True
                                    if not order.room_measurement_line:
                                        all_room_updated = False
                                    else:
                                        for room_data in rooms_list:
                                            if not order.room_measurement_line.filtered(lambda x: x.custom_room_name == room_data.get('room_name', '') or (room_data.get('room_id') and x.room_id.id == int(room_data.get('room_id')) or False)):
                                                all_room_updated= False
                                    if not all_room_updated:
                                        room_measure_result = appointment.action_update_room_measurements(rooms_list, order)
                                        if room_measure_result.get('result', False) == 'Failed':
                                            room_measure_result.update({
                                                'payment_status': payment_status,
                                                'payment_message': payment_message,
                                            })
                                            return room_measure_result
                                if answer_list and not order.contract_question_line:
                                    room_quesionnaire_result = appointment.action_update_questionnaires(answer_list, order)
                                    if room_quesionnaire_result.get('result', False) == 'Failed':
                                        room_quesionnaire_result.update({
                                            'payment_status': payment_status,
                                            'payment_message': payment_message,
                                        })
                                        return room_quesionnaire_result
                                if order.floor_type:
                                    monthly_promo = order.floor_type and order.floor_type.monthly_promo or 0
                                    order.add_payment_line(order.discount, order.adjustment, order.additional_cost,
                                                       monthly_promo, 0, order.final_sale_price)
                                if order.down_payment_amount and data.get('paymentmethod', {}) and not order.payment_method:
                                    payment_result = order.action_update_payment_data(data.get('paymentmethod', {}), existing_auth_transaction_id, card_type)
                                    payment_status = payment_result.get('result', '')
                                    if payment_result.get('result', '') != 'Success':
                                        payment_message = payment_result.get('message', '')
                                        if operation_mode == 'online':
                                            payment_result.update({
                                                'payment_status': payment_status,
                                                'payment_message': payment_message,
                                            })
                                            return payment_result
                                        else:
                                            company = order.company_id
                                            if company.push_api_key_id:
                                                MobileNotificationObj = self.env['mobile.notifications']
                                                description = payment_result.get('message', '')
                                                if description:
                                                    user_id = appointment.user_id
                                                    notification = MobileNotificationObj.sudo().create({
                                                        'title': "Payment Failed - %s %s" % (
                                                        appointment.applicant_first_name,
                                                        appointment.applicant_last_name),
                                                        'name': description,
                                                        'user_id': user_id.id,
                                                        'res_id': appointment.id,
                                                        'res_model': appointment._name,
                                                        'active': True
                                                    })
                                                    if notification:
                                                        if user_id and user_id.device_reg_id:
                                                            device_id = user_id.device_reg_id
                                                            message_body = description
                                                            message_title = "Payment Failed - %s %s" % (
                                                            appointment.applicant_first_name,
                                                            appointment.applicant_last_name)
                                                            extra_data = {'type': notification.res_model,
                                                                          'id': str(notification.id),
                                                                          'name': str(notification.res_id)}
                                                            notification_result = notification.push_pyfcm_single(
                                                                company, device_id,
                                                                message_title,
                                                                message_body,
                                                                extra_data=extra_data)
                                                            if notification_result and notification_result.get('success', False):
                                                                notification.status = 'sent'
                                                            else:
                                                                notification.status = 'failed'
                                                        else:
                                                            notification.status = 'failed'
                                    else:
                                        payment_message = 'Payment Processed Successfully'
                                        order_values = payment_result.get('values', {})
                                        if order_values:
                                            transaction_id = order_values.get('authorize_transaction_id','')
                                            card_type = order_values.get('card_type','')
                                            order.write(order_values)

                            return {
                                'message': 'Order details updated successfully.',
                                'result': 'Success',
                                'payment_status': payment_status,
                                'payment_message': payment_message,
                            }
                    if data.get('customer', {}):
                        appointment_result = appointment.action_update_appointment(data.get('customer', {}), app_version)
                        if appointment_result.get('result', False) == 'Failed':
                            appointment_result.update({
                                'payment_status': payment_status,
                                'payment_message': payment_message,
                            })
                            return appointment_result
                        if not data.get('paymentdetails', {}):
                            sale_order_vals = {
                                'partner_id': appointment.partner_id.id,
                                'appointment_id': appointment_id,
                            }
                            order = sale_order_obj.create(sale_order_vals)
                        else:
                            order_result = appointment.action_create_sale_order(data.get('paymentdetails', {}), execution_order='order_room')
                            if order_result.get('result', '') == 'Failed':
                                order_result.update({
                                    'payment_status': payment_status,
                                    'payment_message': payment_message,
                                })
                                return order_result
                            order_id = order_result.get('order_id', False)
                            order = sale_order_obj.browse(order_id)
                        if data.get('rooms', []):
                            room_measure_result = appointment.action_update_room_measurements(data.get('rooms', []), order)
                            if room_measure_result.get('result', False) == 'Failed':
                                room_measure_result.update({
                                    'payment_status': payment_status,
                                    'payment_message': payment_message,
                                })
                                return room_measure_result
                            if data.get('answer', []):
                                room_quesionnaire_result = appointment.action_update_questionnaires(
                                    data.get('answer', []), order)
                                if room_quesionnaire_result.get('result', False) == 'Failed':
                                    room_quesionnaire_result.update({
                                        'payment_status': payment_status,
                                        'payment_message': payment_message,
                                    })
                                    return room_quesionnaire_result
                            if order.floor_type:
                                monthly_promo = order.floor_type and order.floor_type.monthly_promo or 0
                                order.add_payment_line(order.discount, order.adjustment, order.additional_cost, monthly_promo, 0, order.final_sale_price)
                        if order.down_payment_amount:
                            if data.get('paymentmethod', {}):
                                payment_result = order.action_update_payment_data(data.get('paymentmethod', {}))
                                payment_status = payment_result.get('result', '')
                                if payment_result.get('result', '') != 'Success':
                                    payment_message = payment_result.get('message', '')
                                    if operation_mode == 'online':
                                        payment_result.update({
                                            'payment_status': payment_status,
                                            'payment_message': payment_message,
                                            'authorize_transaction_id': transaction_id,
                                        })
                                        return payment_result
                                    else:
                                        company = order.company_id
                                        if company.push_api_key_id:
                                            MobileNotificationObj = self.env['mobile.notifications']
                                            description = payment_result.get('message', '')
                                            if description:
                                                user_id = appointment.user_id
                                                notification = MobileNotificationObj.sudo().create({
                                                    'title': "Payment Failed - %s %s"%(appointment.applicant_first_name, appointment.applicant_last_name),
                                                    'name': description,
                                                    'user_id': user_id.id,
                                                    'res_id': appointment.id,
                                                    'res_model': appointment._name,
                                                    'active': True
                                                })
                                                if notification:
                                                    if user_id and user_id.device_reg_id:
                                                        device_id = user_id.device_reg_id
                                                        message_body = description
                                                        message_title = "Payment Failed - %s %s"%(appointment.applicant_first_name, appointment.applicant_last_name)
                                                        extra_data = {'type': notification.res_model,
                                                                      'id': str(notification.id),
                                                                      'name': str(notification.res_id)}
                                                        notification_result = notification.push_pyfcm_single(
                                                            company, device_id,
                                                            message_title,
                                                            message_body,
                                                            extra_data=extra_data)
                                                        if notification_result and notification_result.get('success', False):
                                                            notification.status = 'sent'
                                                        else:
                                                            notification.status = 'failed'
                                                    else:
                                                        notification.status = 'failed'
                                else:
                                    payment_message = 'Payment Processed Successfully'
                                    order_values = payment_result.get('values', {})
                                    if order_values:
                                        transaction_id = order_values.get('authorize_transaction_id', '')
                                        card_type = order_values.get('card_type', '')
                                        order.write(order_values)
                                        if order.appointment_id.make_payment_failure:
                                            x = False
                                            x.append('1')
                                if data.get('applicationInfo', {}):
                                    credit_application_result = order.action_create_credit_application(
                                        data.get('applicationInfo', {}))
                                    if credit_application_result.get('result', '') == 'Failed':
                                        credit_application_result.update({
                                            'payment_status': payment_status,
                                            'payment_message': payment_message,
                                        })
                                        return credit_application_result
                            else:
                                if appointment.appointment_result == 'Sold':
                                    result = {
                                        'message': 'Payment method Details are missing',
                                        'result': 'Failed',
                                        'payment_status': payment_status,
                                        'payment_message': payment_message,
                                    }
                            result = {
                                'message': success_msg,
                                'result': 'Success',
                                'payment_status': payment_status,
                                'payment_message': payment_message,
                            }
                        else:
                            if data.get('applicationInfo', {}):
                                credit_application_result = order.action_create_credit_application(
                                    data.get('applicationInfo', {}))
                                if credit_application_result.get('result', '') == 'Failed':
                                    credit_application_result.update({
                                        'payment_status': payment_status,
                                        'payment_message': payment_message,
                                    })
                                    return credit_application_result
                            result = {
                                'message': 'Order details updated successfully.',
                                'result': 'Success',
                                'payment_status': payment_status,
                                'payment_message': payment_message,
                            }

                    else:
                        result = {
                            'message': 'Customer Details are missing',
                            'result': 'Failed'
                        }
                else:
                    _logger.info("------Wrong Appointment id-------------")
                    result = {
                        'message': 'Wrong Appointment id',
                        'result': 'Failed'
                    }
            else:
                _logger.info("------Empty Appointment id-------------")
                result = {
                    'message': 'Empty Appointment id',
                    'result': 'Failed'
                }
        except:
            result = {
                'message': 'Something went wrong',
                'result': 'Failed',
                'authorize_transaction_id': transaction_id,
                'card_type': card_type,
                'payment_status': payment_status,
                'payment_message': payment_message,
            }
        _logger.info("------action_create_order_and_update_measurements result: %s-------------" % (result))
        return result

    def action_get_available_dates_from_rule_engine_api(self, sale_order):
        result = {
            'result': 'Success',
            'data': {},
            'message': ''
        }
        api_configuration = self.env['team.improveit.configuration'].search([('api_type', '=', 'rules_engine')], limit=1)
        if not api_configuration:
            return {
                'message': 'Installer API Configuration is missing',
                'result': 'Failed'
            }
        api_response = {}
        # if api_configuration.mode == 'test':
        #     crews = [
        #         {
        #             "id": "a0j74000000PTY4",
        #             "name": "Justin Kennedy - Pikes Peak Flooring",
        #             "totalCompletedInstalls": 40,
        #             "starRating": 4.5,
        #             "grade": "H",
        #             "slot": {
        #                 "start_date": datetime.strptime("2023-10-09 09:00:00", DEFAULT_SERVER_DATETIME_FORMAT),
        #                 "end_date": datetime.strptime("2023-10-10 17:00:00", DEFAULT_SERVER_DATETIME_FORMAT)
        #             }
        #         },
        #         {
        #             "id": "a0j74000000PTWr",
        #             "name": "Idris (Alex) Hunn - Hunn Homes Inc",
        #             "totalCompletedInstalls": 15,
        #             "starRating": 4.5,
        #             "grade": "M",
        #             "slot": {
        #                 "start_date": datetime.strptime("2023-09-18 09:00:00", DEFAULT_SERVER_DATETIME_FORMAT),
        #                 "end_date": datetime.strptime("2023-09-20 17:00:00", DEFAULT_SERVER_DATETIME_FORMAT)
        #             }
        #         },
        #         {
        #             "id": "a0j74000000PTWq3",
        #             "name": "John Escamilla - J Mack Flooring",
        #             "totalCompletedInstalls": 25,
        #             "starRating": 4.0,
        #             "grade": "H",
        #             "slot": {
        #                 "start_date": datetime.strptime("2023-10-09 09:00:00", DEFAULT_SERVER_DATETIME_FORMAT),
        #                 "end_date": datetime.strptime("2023-10-11 17:00:00", DEFAULT_SERVER_DATETIME_FORMAT)
        #             }
        #         },
        #         {
        #             "id": "a0j74000000PTWq",
        #             "name": "Michael Miller - Flooring Family",
        #             "totalCompletedInstalls": 26,
        #             "starRating": 4.0,
        #             "grade": "H",
        #             "slot": {
        #                 "start_date": datetime.strptime("2023-10-02 09:00:00", DEFAULT_SERVER_DATETIME_FORMAT),
        #                 "end_date": datetime.strptime("2023-10-04 17:00:00", DEFAULT_SERVER_DATETIME_FORMAT)
        #             }
        #         },
        #         {
        #             "id": "a0j74000000PTWp4",
        #             "name": "Nick Mastruserio - Nick Squared Contracting",
        #             "totalCompletedInstalls": 36,
        #             "starRating": 3.0,
        #             "grade": "M",
        #             "slot": {
        #                 "start_date": datetime.strptime("2023-10-09 09:00:00", DEFAULT_SERVER_DATETIME_FORMAT),
        #                 "end_date": datetime.strptime("2023-10-12 17:00:00", DEFAULT_SERVER_DATETIME_FORMAT)
        #             }
        #         },
        #         {
        #             "id": "a0j74000000PTWp5",
        #             "name": "John Kidd Jr. - Kidd Flooring",
        #             "totalCompletedInstalls": 29,
        #             "starRating": 3.0,
        #             "grade": "H",
        #             "slot": {
        #                 "start_date": datetime.strptime("2023-10-02 09:00:00", DEFAULT_SERVER_DATETIME_FORMAT),
        #                 "end_date": datetime.strptime("2023-10-03 17:00:00", DEFAULT_SERVER_DATETIME_FORMAT)
        #             }
        #         },
        #         {
        #             "id": "a0j74000000PTWp6",
        #             "name": "Spencer Nunnelly - Carpenter Bee Contracting",
        #             "totalCompletedInstalls": 18,
        #             "starRating": 3.0,
        #             "grade": "H"
        #         },
        #         {
        #             "id": "a0j74000000PTWp12",
        #             "name": "Santy Castro - D'castro Carpeting and Flooring",
        #             "totalCompletedInstalls": 39,
        #             "starRating": 3.0,
        #             "grade": "M",
        #             "slot": {
        #                 "start_date": datetime.strptime("2023-10-02 09:00:00", DEFAULT_SERVER_DATETIME_FORMAT),
        #                 "end_date": datetime.strptime("2023-10-04 17:00:00", DEFAULT_SERVER_DATETIME_FORMAT)
        #             }
        #         },
        #         {
        #             "id": "a0j4V00000CCOncQAH",
        #             "name": "Cody Harris - Mojo's Flooring",
        #             "totalCompletedInstalls": 23,
        #             "starRating": 2.5,
        #             "grade": "M",
        #             "slot": {
        #                 "start_date": datetime.strptime("2023-10-09 09:00:00", DEFAULT_SERVER_DATETIME_FORMAT),
        #                 "end_date": datetime.strptime("2023-10-12 17:00:00", DEFAULT_SERVER_DATETIME_FORMAT)
        #             }
        #         },
        #         {
        #             "id": "a0j74000000PTWp",
        #             "name": "Anthony Waters - Anthony's Renovation & Remodeling",
        #             "slot": {
        #                 "start_date": datetime.strptime("2023-09-14 09:00:00", DEFAULT_SERVER_DATETIME_FORMAT),
        #                 "end_date": datetime.strptime("2023-09-14 17:00:00", DEFAULT_SERVER_DATETIME_FORMAT)
        #             }
        #         }
        #     ]
        #     result.update({
        #         'data': crews
        #     })
        #     return result
        if not api_configuration.auth_url:
            return {
                'message': 'Authentication URL is missing',
                'result': 'Failed'
            }
        auth = requests.post(api_configuration.auth_url, data={
            "client_id": api_configuration.client_id,
            "client_secret": api_configuration.client_secret,
            "grant_type": api_configuration.grant_type,
            "Content-Type": "application/x-www-form-urlencoded"})
        try:
            auth_json = auth.json()
            auth_token = auth_json['access_token']
        except:
            auth_token = ''
        _logger.info('Auth Token--%s'%auth_token)
        if not auth_token:
            return {
                'message': 'Authentication API is Failed',
                'result': 'Failed'
            }
        configuration = Configuration(
            host=api_configuration.token_url,
            access_token=auth_token
        )
        if configuration:
            configuration.verify_ssl = api_configuration.enable_ssl
            api_client = ApiClient(configuration)
            api_instance = scheduling_services_api.SchedulingServicesApi(api_client)
            environment = "production"
            if api_configuration.mode == "test":
                environment = "development"
            
            try:
                # Request schedule using a new sales order
                appointment_date = sale_order.appointment_id and sale_order.appointment_id.appointment_date.date() or date.today()
                installer_date_range_limit = int(self.env['ir.config_parameter'].sudo().get_param('team_sale_contract.installer_date_range_limit')) or 30
                finance_installation_delay = sale_order.finance_provider_id and sale_order.finance_provider_id.installation_delay_days or 0
                is_special_order = sale_order.room_measurement_line.filtered(lambda x: x.special_order_material)
                if is_special_order:
                    special_order_delay_limit = int(self.env['ir.config_parameter'].sudo().get_param('team_sale_contract.special_order_delay_limit')) or 14
                else:
                    special_order_delay_limit = 0
                total_delay = 1
                if finance_installation_delay > 0:
                    if finance_installation_delay > special_order_delay_limit:
                        total_delay += finance_installation_delay
                    else:
                        total_delay += special_order_delay_limit
                else:
                    total_delay += special_order_delay_limit
                start_date = appointment_date + relativedelta(days=total_delay)
                end_date = start_date + relativedelta(days=installer_date_range_limit)

                model = ScheduleRequest()
                model.proposed_start_date = start_date
                model.proposed_end_date = end_date

                api_response = api_instance.schedule_existing_order(sale_order.quote_id,
                                                                    schedule_request=model,
                                                                    _headers={
                                                                        "x_refloor_environment": environment
                                                                    })
                _logger.info(api_response)
                if not isinstance(api_response, dict):
                    # api_response = api_response.dict()
                    api_response = api_response.model_dump()
                result.update({
                    'data': api_response.get('crews', [])
                })
            except Exception as e:
                error_content = e.body and eval(e.body) or {}
                error_message = "Error occurred while searching available dates."
                if error_content and error_content.get('message', ""):
                    error_message = error_content.get('message', "")
                _logger.info("Exception when calling SchedulingServicesApi->schedules_post: %s\n" % e)
                result.update({
                    'result': 'Failed',
                    'message': error_message
                })
        return result


    @api.model
    def action_get_available_installation_date(self, data):
        result = {
            'message': 'No Data found to update',
            'result': 'Failed'
        }
        sale_order_obj = self.env['sale.order']
        crew_obj = self.env['otl.installation.crew']
        _logger.info("------action_get_available_installation_date data: %s-------------" % (data))
        try:
            appointment_id = data.get('appointment_id', 0) and int(data.get('appointment_id', 0)) or 0
            only_fetch_installation_dates = data.get('only_fetch_installation_dates', False) and eval(data.get('only_fetch_installation_dates', False)) or False
            if appointment_id:
                appointment = self.browse(appointment_id)
                if appointment.exists():
                    user = self.env.user
                    tz = user.tz and pytz.timezone(user.tz) or pytz.utc
                    timezone = user.tz or 'UTC'
                    sale_order = sale_order_obj.search([('appointment_id', '=', appointment_id)], limit=1)
                    if sale_order:
                        if not only_fetch_installation_dates:
                            sale_sync_result = self.action_sync_sale_data_to_i360(appointment, sale_order, return_on_failure=True)
                            _logger.info('i360 Sale Manual Sync Response: --%s'%(sale_sync_result))
                            if sale_sync_result.get('result', '') == 'Success':
                                rules_engine_result = self.action_get_available_dates_from_rule_engine_api(sale_order)
                                if rules_engine_result.get('result', '') == 'Failed':
                                    return rules_engine_result
                                crews_list = rules_engine_result.get('data', [])
                                if not crews_list:
                                    return {
                                        'message': 'No Data received from Rules Engine',
                                        'result': 'Failed'
                                    }
                                start_date_list = []

                                if sale_order.available_installation_line:
                                    sale_order.available_installation_line.unlink()
                                for crew_data in crews_list:
                                    i360_id = crew_data.get('id', '')
                                    name = crew_data.get('name', '')
                                    crew = crew_obj.search([('improveit_id', '=', i360_id)], limit=1)
                                    if not crew:
                                        crew = crew_obj.create({'improveit_id': i360_id, 'name': name})
                                    time_slot = crew_data.get('slot', {})
                                    if time_slot:
                                        start_date = time_slot.get('start_date', False)
                                        end_date = time_slot.get('end_date', False)
                                        start_date_utc = tz.localize(start_date).astimezone(pytz.utc).strftime(DEFAULT_SERVER_DATETIME_FORMAT)
                                        if start_date_utc not in start_date_list:
                                            start_date_list.append(start_date_utc)
                                            end_date_utc = tz.localize(end_date).astimezone(pytz.utc).strftime(DEFAULT_SERVER_DATETIME_FORMAT)
                                            self.env['otl.available.installation.line'].create({
                                                    'start_date': start_date_utc,
                                                    'end_date': end_date_utc,
                                                    'order_id': sale_order.id,
                                                    'crew_id': crew.id
                                                })
                                if not start_date_list:
                                    return {
                                        'message': 'No Dates are Available',
                                        'result': 'Failed'
                                    }
                            else:
                                return sale_sync_result
                        available_date_list = []
                        for installation_date in sale_order.available_installation_line:
                            start_date = utc_2_local(installation_date.start_date, timezone)
                            end_date = utc_2_local(installation_date.end_date, timezone)
                            available_date_list.append({
                                'installation_id': installation_date.id,
                                'start_date': start_date.strftime(DEFAULT_SERVER_DATETIME_FORMAT),
                                'end_date': end_date.strftime(DEFAULT_SERVER_DATETIME_FORMAT),
                                'crew_id': installation_date.crew_id.id,
                                'crew_name': installation_date.crew_id.name,
                            })
                        if available_date_list:
                            available_date_list.sort(key = lambda x:x['start_date'])
                        return {
                            'result': 'Success',
                            'message': "Available Installation Date retrieved Successfully",
                            'data': {
                                'available_dates': available_date_list,
                                'sale_order_id': sale_order.id
                            }
                        }
                    else:
                        _logger.info("------Sale Order is not existing against this appointment-------------")
                        result = {
                            'message': 'Sale Order is not existing against this appointment',
                            'result': 'Failed'
                        }
                else:
                    _logger.info("------Wrong Appointment id-------------")
                    result = {
                        'message': 'Wrong Appointment id',
                        'result': 'Failed'
                    }
            else:
                _logger.info("------Empty Appointment id-------------")
                result = {
                    'message': 'Empty Appointment id',
                    'result': 'Failed'
                }
        except:
            result = {
                'message': 'Something went wrong.',
                'result': 'Failed',
            }
        _logger.info("------action_get_available_installation_date result: %s-------------" % (result))
        return result

    def action_check_selected_date_still_available(self, sale_order, selected_installation):
        result = {
            'result': 'Failed',
            'date_available': False
        }
        selected_installation_date = selected_installation.start_date.strftime(DEFAULT_SERVER_DATETIME_FORMAT)
        rules_engine_result = self.action_get_available_dates_from_rule_engine_api(sale_order)
        if rules_engine_result.get('result', '') == 'Failed':
            return rules_engine_result
        crews_list = rules_engine_result.get('data', [])
        if not crews_list:
            return {
                'message': 'No Data received from Rules Engine',
                'result': 'Failed'
            }
        user = self.env.user
        tz = user.tz and pytz.timezone(user.tz) or pytz.utc
        timezone = user.tz or 'UTC'
        for crew_data in crews_list:
            time_slot = crew_data.get('slot', {})
            crew_i360_id = crew_data.get('id', '')
            if time_slot:
                start_date = time_slot.get('start_date', False)
                start_date_utc = tz.localize(start_date).astimezone(pytz.utc).strftime(DEFAULT_SERVER_DATETIME_FORMAT)
                if start_date_utc == selected_installation_date and crew_i360_id == selected_installation.crew_id.improveit_id:
                    result.update({
                        'result': 'Success',
                        'date_available': True
                    })
                    return result
        return result

    @api.model
    def action_submit_selected_installation_date(self, data):
        result = {
            'message': 'No Data found to update',
            'result': 'Failed'
        }
        sale_order_obj = self.env['sale.order']
        _logger.info("------action_submit_selected_installation_date data: %s-------------" % (data))
        try:
            sale_order_id = data.get('sale_order_id', 0) and int(data.get('sale_order_id', 0)) or 0
            if sale_order_id:
                sale_order = sale_order_obj.browse(sale_order_id)
                if sale_order.exists():
                    appointment = sale_order.appointment_id
                    installation_id = data.get('installation_id', 0) and int(data.get('installation_id', 0)) or 0
                    if installation_id:
                        exists_selected_installation = sale_order.available_installation_line.filtered(lambda x: x.selected)
                        if exists_selected_installation:
                            return {
                                'message': 'Your installation is already scheduled to %s. You can now skip to appointments list.'%(exists_selected_installation.start_date.strftime('%m-%d-%Y')),
                                'result': 'Failed'
                            }
                        selected_installation = sale_order.available_installation_line.filtered(lambda x: x.id == installation_id)
                        if selected_installation:
                            response = self.action_check_selected_date_still_available(sale_order, selected_installation)
                            if response.get('result', '') == 'Failed':
                                if 'date_available' in response:
                                    return {
                                        'message': 'Selected Date is not available now. Please select different date',
                                        'result': 'Failed'
                                    }
                                else:
                                    return response
                            else:
                                sync_log = self.env['otl.appointment.sync.log']
                                if not selected_installation.project_i360_id:
                                    response_result = sale_order.create_project_in_i360(selected_installation)
                                    if response_result.get('success', '') == 'true':
                                        sync_log.create({
                                            'appointment_id': appointment.id,
                                            'response': response_result,
                                            'name': 'CreateProject',
                                        })
                                        if response_result.get('duplicate', '') == 'true':
                                            _logger.info(
                                                '-------Sync Aborting due to Duplicate Project - %s, Response: %s' % (
                                                    sale_order.id, response_result))
                                    else:
                                        sync_log.create({
                                            'appointment_id': appointment.id,
                                            'response': response_result,
                                            'state': 'failed',
                                            'name': 'CreateProject',
                                        })
                                        return {
                                                'message': 'CreateProject Failed due to following reason: %s' % (
                                                    response_result),
                                                'result': 'Failed'
                                            }
                                if not selected_installation.project_activity_i360_id:
                                    response_result = sale_order.create_project_activity_in_i360(selected_installation)
                                    if response_result.get('success', '') == 'true':
                                        sync_log.create({
                                            'appointment_id': appointment.id,
                                            'response': response_result,
                                            'name': 'CreateProjectActivity',
                                        })
                                        if response_result.get('duplicate', '') == 'true':
                                            _logger.info(
                                                '-------Sync Aborting due to Duplicate CreateProjectActivity - %s, Response: %s' % (
                                                    sale_order.id, response_result))
                                    else:
                                        sync_log.create({
                                            'appointment_id': appointment.id,
                                            'response': response_result,
                                            'state': 'failed',
                                            'name': 'CreateProjectActivity',
                                        })
                                        return {
                                                'message': 'CreateProjectActivity Failed due to following reason: %s' % (
                                                    response_result),
                                                'result': 'Failed'
                                            }
                                selected_installation.write({'selected': True})
                                result = {
                                    'message': 'Your installation request has been submitted successfully',
                                    'result': 'Success'
                                }

                        else:
                            _logger.info("------Given Installation ID is not belongs to this order.-------------")
                            result = {
                                'message': 'Given Installation ID is not belongs to this order.',
                                'result': 'Failed'
                            }
                    else:
                        _logger.info("------Installation ID is Empty-------------")
                        result = {
                            'message': 'Installation ID is Empty',
                            'result': 'Failed'
                        }
                else:
                    _logger.info("------Wrong Sale Order id-------------")
                    result = {
                        'message': 'Wrong Sale Order id',
                        'result': 'Failed'
                    }
            else:
                _logger.info("------Empty Sale Order id-------------")
                result = {
                    'message': 'Empty Sale Order id',
                    'result': 'Failed'
                }
        except:
            result = {
                'message': 'Something went wrong.',
                'result': 'Failed',
            }
        _logger.info("------action_submit_selected_installation_date result: %s-------------" % (result))
        return result

    @api.model
    def action_update_additional_appointment_data(self, data):
        result = {
            'message': 'Something went wrong updating the appointment',
            'result': 'Failed'
        }
        _logger.info("------action_update_additional_appointment_data data: %s-------------" % (data))
        try:
            appointment_id = data.get('appointment_id', 0) and int(data.get('appointment_id', 0)) or 0
            send_physical_document = False
            if data.get('send_physical_document', 0) == 1:
                send_physical_document = True
            flexible_installation = False
            if data.get('flexible_installation', 0) == 1:
                flexible_installation = True
            destination_selection_id = False
            both_parties_present = False
            if data.get('both_parties_present', 0) == 1:
                both_parties_present = True
            if data.get('destination_selection_id', False):
                destination_selection_id = int(data.get('destination_selection_id', 0))
                destination_selection = self.env['otl.appointment.result.reason'].browse(destination_selection_id)
                if not destination_selection or not destination_selection.exists():
                    return {'message': 'Wrong value for Destination Selection', 'result': 'Failed'}
            if appointment_id:
                appointment = self.env['team.customer.appointment'].browse(appointment_id)
                if appointment.exists():
                    appointment_vals = {
                        'additional_comments': data.get('additional_comments', ''),
                        'send_physical_document': send_physical_document,
                        'flexible_installation': flexible_installation,
                        'both_parties_present': both_parties_present,
                    }
                    if destination_selection_id:
                        appointment_vals.update({'destination_selection_id': destination_selection_id})
                    appointment.write(appointment_vals)
                    order = self.env['sale.order'].search([('appointment_id', '=', appointment_id)], limit=1)
                    if not order:
                        return {
                            'message': 'Sale order is not found against the appointment',
                            'result': 'Failed'
                        }
                    if data.get('recision_date', False):
                        order.write({'recision_date': data.get('recision_date', False)})
                    result = {
                        'message': 'Data Updated Successfully',
                        'result': 'Success',
                    }
                    _logger.info("------Data Updated Successfully-------------")
                else:
                    _logger.info("------Wrong Appointment Id-------------")
                    result = {
                        'message': 'Wrong Appointment Id',
                        'result': 'Failed'
                    }

            else:
                _logger.info("------Empty Appointment Id-------------")
                result = {
                    'message': 'Empty Appointment Id',
                    'result': 'Failed'
                }
        except:
            result = {
                'message': 'Something Went Wrong.',
                'result': 'Failed'
            }
        _logger.info("------action_update_additional_appointment_data result: %s-------------" % (result))
        return result

    @api.model
    def action_get_credit_application_status(self, data):
        result = {
            'message': 'Something went wrong updating the appointment',
            'result': 'Failed'
        }
        _logger.info("------action_get_credit_application_status data: %s-------------" % (data))
        try:
            appointment_id = data.get('appointment_id', 0) and int(data.get('appointment_id', 0)) or 0
            improveit_appointment_id = data.get('improveit_appointment_id', '') and data.get('improveit_appointment_id', '') or ''
            loan_type = data.get('loan_type', '')
            if not loan_type:
                return {
                    'message': 'Empty Loan Type',
                    'result': 'Failed'
                }
            if loan_type not in ['versatile', 'hunter']:
                return {
                    'message': 'Wrong Loan Type',
                    'result': 'Failed'
                }
            appointment = False
            versatile_application = False
            if improveit_appointment_id:
                appointment = self.env['team.customer.appointment'].search([('improveit_appointment_id', '=', improveit_appointment_id)], limit=1)
                versatile_application = self.env['otl.versatile.credit.application'].search(
                    [('ext_customer_id', '=', improveit_appointment_id), ('finance_provider', '=', loan_type)], limit=1)
            elif appointment_id:
                appointment = self.env['team.customer.appointment'].browse(appointment_id)
                versatile_application = self.env['otl.versatile.credit.application'].search(
                    [('appointment_id', '=', appointment_id), ('finance_provider', '=', loan_type)], limit=1)
            if appointment and appointment.exists():
                    if not versatile_application:
                        result = {
                            'message': 'Credit application is not existing',
                            'result': 'Failed'
                        }
                    else:
                        result = {
                            "result": "Success",
                            "data": {
                                "application_id": versatile_application.application_id or "",
                                "provider": versatile_application.provider or "",
                                "provider_reference": versatile_application.provider_reference or "",
                                "status": versatile_application.status or "",
                                "approved_amount": versatile_application.approved_amount or 0,
                                "finance_provider": versatile_application.finance_provider or "",
                                "co_applicant_exists": versatile_application.co_applicant_first_name and 1 or 0,
                            }
                        }
            else:
                _logger.info("------Wrong Appointment Id-------------")
                result = {
                    'message': 'Wrong Appointment Id',
                    'result': 'Failed'
                }
        except:
            result = {
                'message': 'Something went wrong while fetching application status.',
                'result': 'Failed'
            }
        _logger.info("------action_get_credit_application_status result: %s-------------" % (result))
        return result

    def action_start_sync_arrival_departure_time_to_i360(self, appointment_id):
        time.sleep(3)
        try:
            # As this function is in a new thread, I need to open a new cursor, because the old one may be closed
            new_cr = self.pool.cursor()
            self = self.with_env(self.env(cr=new_cr))
            sync_log = self.env['otl.appointment.sync.log']
            _logger.info('------Starting action_start_sync_arrival_departure_time_to_i360------: %s'%(appointment_id))
            appointment = self.env['team.customer.appointment'].browse(int(appointment_id))
            if (appointment.arrival_date or appointment.departure_date) and not appointment.arrival_departure_synced:
                result = appointment.update_arrival_departure_time_in_i360()
                if result.get('success', '') == 'true':
                    _logger.info("------ SalesRepArrivalDeparture Success-------------")
                    sync_log.create({
                        'appointment_id': appointment.id,
                        'response': result,
                        'name': 'SalesRepArrivalDeparture',
                    })
                else:
                    _logger.info("------ SalesRepArrivalDeparture Failed-------------")
                    sync_log.create({
                        'appointment_id': appointment.id,
                        'response': result,
                        'state': 'failed',
                        'name': 'SalesRepArrivalDeparture',
                    })
            else:
                _logger.info('-----No Arrival & Departure Time in appointment----')
            self.env.cr.commit()
            new_cr.close()
            _logger.info('------End of action_start_sync_arrival_departure_time_to_i360------: %s' % (appointment_id))
        except Exception as e:
            _logger.info('------Exception in action_start_sync_to_i360------: %s' % (e))
            new_cr.rollback()
        return True

    @api.model
    def action_update_arrival_departure_time(self, data):
        result = {
            'message': 'Something went wrong updating the appointment',
            'result': 'Failed'
        }
        _logger.info("------action_update_arrival_departure_time data: %s-------------" % (data))
        try:
            appointment_id = data.get('appointment_id', 0) and int(data.get('appointment_id', 0)) or 0
            arrival_date = data.get('arrival_date', False)
            departure_date = data.get('departure_date', False)
            timezone = data.get('timezone', 'US/Eastern')
            arrival_date_utc = False
            departure_date_utc = False
            if appointment_id:
                appointment = self.env['team.customer.appointment'].browse(appointment_id)
                if appointment.exists():
                    if arrival_date:
                        arrival_date_utc = arrival_date
                        if timezone:
                            arrival_date_utc = self.get_timezone_based_time(arrival_date, timezone)
                    if departure_date:
                        departure_date_utc = departure_date
                        if timezone:
                            departure_date_utc = self.get_timezone_based_time(departure_date, timezone)
                    appointment.write({
                        'arrival_date': arrival_date_utc,
                        'departure_date': departure_date_utc,
                        'timezone': timezone,
                    })
                    result = {
                        'message': 'Data Updated Successfully',
                        'result': 'Success',
                    }
                    _logger.info("------Data Updated Successfully-------------")
                    t1 = threading.Thread(target=self.action_start_sync_arrival_departure_time_to_i360, args=(appointment.id,))
                    t1.start()
                    _logger.info("thread %s started!" % t1)
                else:
                    _logger.info("------Wrong Appointment Id-------------")
                    result = {
                        'message': 'Wrong Appointment Id',
                        'result': 'Failed'
                    }

            else:
                _logger.info("------Empty Appointment Id-------------")
                result = {
                    'message': 'Empty Appointment Id',
                    'result': 'Failed'
                }
        except:
            result = {
                'message': 'Something Went Wrong.',
                'result': 'Failed'
            }
        _logger.info("------action_update_arrival_departure_time result: %s-------------" % (result))
        return result

    def action_start_sync_manual_arrival_date_to_i360(self, appointment_id):
        time.sleep(3)
        try:
            # As this function is in a new thread, I need to open a new cursor, because the old one may be closed
            new_cr = self.pool.cursor()
            self = self.with_env(self.env(cr=new_cr))
            sync_log = self.env['otl.appointment.sync.log']
            _logger.info('------Starting action_start_sync_manual_arrival_date_to_i360------: %s'%(appointment_id))
            appointment = self.env['team.customer.appointment'].browse(int(appointment_id))
            if appointment.manual_arrival_date and not appointment.manual_arrival_date_synced:
                result = appointment.update_manual_arrival_date_in_i360()
                if result.get('success', '') == 'true':
                    _logger.info("------ SalesRepArrivalDeparture Success-------------")
                    sync_log.create({
                        'appointment_id': appointment.id,
                        'response': result,
                        'name': 'SalesRepArrivalDeparture-ManualArrivalDate',
                    })
                else:
                    _logger.info("------ SalesRepArrivalDeparture Failed-------------")
                    sync_log.create({
                        'appointment_id': appointment.id,
                        'response': result,
                        'state': 'failed',
                        'name': 'SalesRepArrivalDeparture-ManualArrivalDate',
                    })
            else:
                _logger.info('-----No Arrival & Departure Time in appointment----')
            self.env.cr.commit()
            new_cr.close()
            _logger.info('------End of action_start_sync_manual_arrival_date_to_i360------: %s' % (appointment_id))
        except Exception as e:
            _logger.info('------Exception in action_start_sync_manual_arrival_date_to_i360------: %s' % (e))
            new_cr.rollback()
        return True

    @api.model
    def action_update_manual_arrival_date(self, data):
        result = {
            'message': 'Something went wrong updating the appointment',
            'result': 'Failed'
        }
        _logger.info("------action_update_manual_arrival_date data: %s-------------" % (data))
        try:
            appointment_id = data.get('appointment_id', 0) and int(data.get('appointment_id', 0)) or 0
            manual_arrival_date = data.get('manual_arrival_date', False)
            timezone = data.get('timezone', 'US/Eastern')
            manual_arrival_date_utc = False
            if appointment_id:
                appointment = self.env['team.customer.appointment'].browse(appointment_id)
                if appointment.exists():
                    if appointment.manual_arrival_date_synced:
                        result = {
                            'message': 'The Arrival Date has already been synchronized.',
                            'result': 'Failed',
                        }
                    else:
                        if manual_arrival_date:
                            manual_arrival_date_utc = manual_arrival_date
                            if timezone:
                                manual_arrival_date_utc = self.get_timezone_based_time(manual_arrival_date, timezone)
                        appointment.write({
                            'manual_arrival_date': manual_arrival_date_utc,
                            'timezone': timezone,
                        })
                        result = {
                            'message': 'Data Updated Successfully',
                            'result': 'Success',
                        }
                        _logger.info("------Data Updated Successfully-------------")
                        t1 = threading.Thread(target=self.action_start_sync_manual_arrival_date_to_i360, args=(appointment.id,))
                        t1.start()
                        _logger.info("thread %s started!" % t1)
                else:
                    _logger.info("------Wrong Appointment Id-------------")
                    result = {
                        'message': 'Wrong Appointment Id',
                        'result': 'Failed'
                    }

            else:
                _logger.info("------Empty Appointment Id-------------")
                result = {
                    'message': 'Empty Appointment Id',
                    'result': 'Failed'
                }
        except:
            result = {
                'message': 'Something Went Wrong.',
                'result': 'Failed'
            }
        _logger.info("------action_update_manual_arrival_date result: %s-------------" % (result))
        return result

    @api.model
    def action_send_review_link(self, data):
        result = {
            'message': 'Something went wrong updating the appointment',
            'result': 'Failed'
        }
        _logger.info("------action_send_review_link data: %s-------------" % (data))
        try:
            appointment_id = data.get('appointment_id', 0) and int(data.get('appointment_id', 0)) or 0
            phone = data.get('phone', False)
            if appointment_id:
                appointment = self.env['team.customer.appointment'].browse(appointment_id)
                if appointment.exists():
                    if phone:
                        appointment.write({'phone': phone})
                        result = appointment.action_send_review_link_to_i360()
                    else:
                        result = {
                            'message': 'Phone Number is missing.',
                            'result': 'Failed'
                        }
        except:
            result = {
                'message': 'Something Went Wrong.',
                'result': 'Failed'
            }
        _logger.info("------action_send_review_link result: %s-------------" % (result))
        return result

    @api.model
    def action_get_appointment_current_status(self, data):
        result = {
            'message': 'Something went wrong updating the appointment',
            'result': 'Failed'
        }
        _logger.info("------action_get_appointment_current_status data: %s-------------" % (data))
        try:
            appointment_id = data.get('appointment_id', 0) and int(data.get('appointment_id', 0)) or 0
            user_id = data.get('user_id', 0) and int(data.get('user_id', 0)) or 0
            if appointment_id:
                if user_id:
                    user = self.env['res.users'].browse(int(user_id))
                    if user and user.improveit_user_id:
                        result = self.env['res.users'].get_sales_appointment_api_offline(user.improveit_user_id)
                        if result.get('result', '') == 'Failed':
                            return result
                appointment = self.sudo().search([('id', '=', appointment_id)], limit=1)
                if appointment:
                    if appointment.appointment_result:
                        initiate_sync_log = self.env['otl.api.sync.log'].search([
                            ('appointment_id', '=', appointment_id),
                            ('name', '=', '/api/initiate_sync_to_i360_json'),
                            ('state', '=', 'success')
                        ], limit=1)
                        if initiate_sync_log:
                            result = {
                                'message': 'The appointment has already been completed.',
                                'result': 'Failed'
                            }
                    elif appointment.user_id.id != user_id:
                        result = {
                            'message': 'You are not the assigned salesperson for this appointment',
                            'result': 'Failed'
                        }
                    elif appointment.state != 'scheduled':
                        result = {
                            'message': 'This appointment has been canceled and cannot be started.',
                            'result': 'Failed'
                        }
                    else:
                        result = {
                            'message': 'The appointment is now ready to start.',
                            'result': 'Success'
                        }
                else:
                    result = {
                        'message': 'No appointment found for the given ID.',
                        'result': 'Failed'
                    }
            else:
                result = {
                    'message': 'Appointment ID is missing',
                    'result': 'Failed'
                }
        except:
            result = {
                'message': 'Something Went Wrong.',
                'result': 'Failed'
            }
        _logger.info("------action_get_appointment_current_status result: %s-------------" % (result))
        return result

    def action_start_sync_live_screen_log_to_i360(self, live_screen_log_id):
        time.sleep(3)
        new_cr = None

        try:
            db_registry = registry(self.env.cr.dbname)
            new_cr = db_registry.cursor()

            env = api.Environment(new_cr, self.env.uid, self.env.context)

            live_screen_log_obj = env['otl.app.live.screen.log']
            sync_log = env['otl.appointment.sync.log']

            live_screen_log = live_screen_log_obj.browse(int(live_screen_log_id))
            appointment = live_screen_log.appointment_id

            _logger.info(
                '------Starting action_start_sync_live_screen_log_to_i360------: %s - %s',
                appointment.id, live_screen_log.name
            )

            if not live_screen_log.synced_to_i360:
                result = appointment.update_live_screen_log_in_i360(live_screen_log)

                vals = {
                    'appointment_id': appointment.id,
                    'response': result,
                    'name': 'LastScreenAPI',
                }

                if result.get('success') != 'true':
                    vals['state'] = 'failed'

                sync_log.create(vals)
            else:
                _logger.info('-----Data already synced to i360----')

            new_cr.commit()

            _logger.info(
                '------End of action_start_sync_live_screen_log_to_i360------: %s - %s',
                appointment.id, live_screen_log.name
            )

        except Exception as e:
            _logger.exception(
                '------Exception in action_start_sync_live_screen_log_to_i360------:%s' %e
            )
            if new_cr:
                new_cr.rollback()

        finally:
            if new_cr:
                new_cr.close()

        return True

    @api.model
    def action_update_live_screen_log(self, data):
        result = {
            'message': 'Something went wrong updating the appointment',
            'result': 'Failed'
        }
        _logger.info("------action_update_live_screen_log data: %s-------------" % (data))
        try:
            appointment_id = data.get('appointment_id', 0) and int(data.get('appointment_id', 0)) or 0
            user_id = data.get('user_id', 0) and int(data.get('user_id', 0)) or 0
            screen_entry_date = data.get('screen_entry_date', False) and data.get('screen_entry_date', False) or ''
            screen_name = data.get('screen_name', False) and data.get('screen_name', False) or ''
            live_screen_log_obj = self.env['otl.app.live.screen.log']
            if appointment_id:
                appointment = self.sudo().search([('id', '=', appointment_id)], limit=1)
                screen_entry_date_utc = screen_entry_date
                if appointment:
                    timezone = data.get('timezone', 'US/Eastern')
                    if timezone:
                        screen_entry_date_utc = self.get_timezone_based_time(screen_entry_date, timezone)
                    live_screen_log = live_screen_log_obj.search([
                        ('appointment_id', '=', appointment_id),
                        ('screen_entry_date', '=', screen_entry_date_utc)
                    ])
                    if not live_screen_log:
                        live_screen_log = live_screen_log_obj.create({
                            'appointment_id': appointment.id,
                            'name': screen_name,
                            'screen_entry_date': screen_entry_date_utc,
                        })
                        self.env.cr.commit()
                        t1 = threading.Thread(target=self.action_start_sync_live_screen_log_to_i360,
                                              args=(live_screen_log.id,))
                        t1.start()
                        _logger.info("thread %s started!" % t1)
                    result = {
                        'message': 'Live Screen Entry Log updated successfully.',
                        'result': 'Success'
                    }

                else:
                    result = {
                        'message': 'No appointment found for the given ID.',
                        'result': 'Failed'
                    }
            else:
                result = {
                    'message': 'Appointment ID is missing',
                    'result': 'Failed'
                }
        except:
            result = {
                'message': 'Something Went Wrong.',
                'result': 'Failed'
            }
        _logger.info("------action_update_live_screen_log result: %s-------------" % (result))
        return result

    @api.model
    def action_process_credit_card_payment(self, data):
        result = {
            'message': 'No Data found to update',
            'result': 'Failed'
        }
        payment_status = 'Not Done'
        payment_message = 'Payment is not Done'
        success_msg = 'Order details updated successfully'
        _logger.info("------action_process_credit_card_payment data: %s-------------" % (data))
        sale_order_obj = self.env['sale.order']
        # accepted values - online, offline
        operation_mode = data.get('operation_mode', 'offline')
        transaction_id = 'Invalid'
        card_type = ''
        down_payment_amount = 0
        try:
            appointment_id = data.get('appointment_id', '')
            if appointment_id:
                appointment = self.search([('improveit_appointment_id', '=', appointment_id)], limit=1, order='id desc')
                if appointment.exists():
                    order = self.env['sale.order'].search([('appointment_id', '=', appointment.id)], limit=1)
                    if order:
                        payment_method_dict = data.get('payment_method', {})
                        payment_transaction_info_dict = data.get('payment_transaction_info', {})
                        existing_auth_transaction_id = ''
                        if payment_transaction_info_dict:
                            existing_auth_transaction_id = payment_transaction_info_dict.get('authorize_transaction_id',
                                                                                             0)
                            card_type = payment_transaction_info_dict.get('card_type', '')
                        if payment_method_dict and not existing_auth_transaction_id:
                            payment_method = payment_method_dict.get('payment_method', '')
                            down_payment_amount = float(payment_method_dict.get('down_payment_amount', 0))
                            down_payment_lines = order.order_line.filtered(lambda x: x.is_downpayment)
                            if down_payment_lines:
                                invoiced_amount = 0
                                for line in down_payment_lines:
                                    invoiced_amount += line.price_unit or 0
                                if round(invoiced_amount+down_payment_amount)> round(order.amount_total):
                                    return {
                                        'result': 'Failed',
                                        'message': 'The payment amount exceeds the remaining balance on this order. Please enter an amount equal to or less than the outstanding balance.'
                                    }

                        if down_payment_amount and data.get('payment_method', {}):
                            payment_result = order.action_update_payment_data(data.get('payment_method', {}),
                                                                              existing_auth_transaction_id,
                                                                              card_type, transaction_amount= down_payment_amount, allow_multiple_payment=True)
                            payment_status = payment_result.get('result', '')
                            if payment_result.get('result', '') != 'Success':
                                payment_message = payment_result.get('message', '')
                                if operation_mode == 'online':
                                    payment_result.update({
                                        'payment_status': payment_status,
                                        'payment_message': payment_message,
                                    })
                                    return payment_result
                            else:
                                payment_message = 'Payment Processed Successfully'
                                order_values = payment_result.get('values', {})
                                if order_values:
                                    transaction_id = order_values.get('authorize_transaction_id', '')
                                    card_type = order_values.get('card_type', '')
                                    order.confirm_order_and_create_invoice(transaction_amount= down_payment_amount)
                                    # no need to write values to sale order since it is calling from installer app.
                                    # order.write(order_values)
                        else:
                            return {
                                'result': 'Failed',
                                'message': 'Payment amount or Payment method is missing'
                            }

                        return {
                            'message': 'Order details updated successfully.',
                            'result': 'Success',
                            'payment_status': payment_status,
                            'payment_message': payment_message,
                            'transaction_id': transaction_id,
                            'card_type': card_type
                        }
                    else:
                        _logger.info("------Empty Sale Order-------------")
                        result = {
                            'message': 'Sale order is not existing for the appointment.',
                            'result': 'Failed'
                        }
                else:
                    _logger.info("------Wrong Appointment id-------------")
                    result = {
                        'message': 'Wrong Appointment id',
                        'result': 'Failed'
                    }
            else:
                _logger.info("------Empty Appointment id-------------")
                result = {
                    'message': 'Empty Appointment id',
                    'result': 'Failed'
                }
        except:
            result = {
                'message': 'Something went wrong',
                'result': 'Failed',
                'transaction_id': transaction_id,
                'card_type': card_type,
                'payment_status': payment_status,
                'payment_message': payment_message,
            }
        _logger.info("------action_process_credit_card_payment result: %s-------------" % (result))
        return result
    

class SaleOrder(models.Model):
    _inherit='sale.order'

    def prepare_authcapture_payment_values(self, acquirer, order, data, transaction_type="authCaptureTransaction"):
        partner = order.partner_id
        first_name = partner.name or ''
        last_name = ''
        appointment_id = order.appointment_id or False
        if appointment_id:
            if appointment_id.applicant_first_name:
                first_name = appointment_id.applicant_first_name or ''
            last_name = appointment_id.applicant_last_name or ''
        state = partner.state_id and partner.state_id.code or ""
        if not state:
            state = partner.state_code or ''
        values = {
            "createTransactionRequest": {
                "merchantAuthentication": {
                    "name": acquirer.authorize_login,
                    "transactionKey": acquirer.authorize_transaction_key
                },
                "refId": order.name,
                "transactionRequest": {
                    "transactionType": transaction_type,
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
                        "state": state,
                        "zip": partner.zip or "",
                        "country": partner.country_id and partner.country_id.code or ""
                    },


                }
            }
        }
        return values

    def format_expiry(self, expiry):
        month, year = expiry.replace("/", "-").split("-")
        if len(year) == 4:
            year = year[-2:]
        return f"{month.zfill(2)}{year}"

    def action_authcapture_payment(self, data, allow_multiple_payment=False):
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
        acquirer = self.env.ref('payment.payment_provider_authorize').sudo()
        card_type = ''
        for order in self:
            reference = order.name
            office_location = order.appointment_id.office_location_id or False
            if office_location and office_location.payment_provider_id:
                acquirer = office_location.payment_provider_id.sudo()
            currency = order.currency_id
            partner = order.partner_id
            transaction_ref = ''
            transaction_response = ''
            payment_transaction = self.env['payment.transaction'].sudo().search([
                ('sale_order_ids', 'in', order.ids),
                ('state', 'in', ['draft'])
            ], limit=1)
            transaction_type = "authCaptureTransaction"
            transaction_type_to_log = "authcapture"
            if data.get('pay_later', 0):
                transaction_type = "authOnlyTransaction"
                transaction_type_to_log = "authorize"
            if not payment_transaction:
                reference = self.env['payment.transaction']._compute_reference(
                    acquirer.code)
                vals = {
                    'amount': data.get('amount', 0),
                    'currency_id': currency.id,
                    'partner_id': partner.id,
                    'provider_id': acquirer.id,
                    'sale_order_ids': [(6, 0, self.ids)],
                    'payment_method_id': self.env.ref('payment.payment_method_card').id,
                    'reference': reference,
                    # 'acquirer_id': acquirer.id,
                    # 'acquirer_reference': response.get('transactionResponse', {}).get('transId', ''),
                    # 'date': fields.Datetime.now(),
                }
                payment_transaction = self.env['payment.transaction'].create([vals])

            if acquirer.code == 'authorize':
                transaction = AuthorizeAPICustom(acquirer)
                if order.authorize_transaction_id and not allow_multiple_payment:
                    transaction.void(order.authorize_transaction_id or '')
                values = self.prepare_authcapture_payment_values(acquirer, order, data, transaction_type)
                response = transaction._authorize_request_custom(values)
                if response and response.get('err_code'):
                    self.env['otl.card.transaction.log'].create({
                        'sale_order_id': order.id,
                        'name': response.get('transaction_id', ''),
                        'error_code': response.get('err_code', ''),
                        'message': response.get('error_text', ''),
                        'state': 'failed',
                        'type': transaction_type_to_log,
                        'provider_id': acquirer.id
                    })
                    self.env.cr.commit()
                    return {
                        'result': 'Failed',
                        'message': response.get('error_text', '')
                    }
                transaction_ref = response.get('transactionResponse', {}).get('transId', '')
                card_type = response.get('transactionResponse', {}).get('accountType', '')
                transaction_response = response.get('transactionResponse', {}).get('messages')[0].get('description')
                # [FIX] order update restricting to avoid concurrent error
                #order.write({'authorize_transaction_id': transaction_ref, 'card_type': card_type})
                transc_ref = response.get('transactionResponse', {}) and response.get('transactionResponse', {}).get('transId', '') + ' ' + response.get('transactionResponse', {}).get('transId', '') + ' ' + fields.Datetime.now().strftime(DEFAULT_SERVER_DATETIME_FORMAT) or ''
            elif acquirer.code == 'cardpoint':
                if order.authorize_transaction_id and not allow_multiple_payment:
                    acquirer._cardpoint_void_transaction(order.authorize_transaction_id)
                tokenize_data = {
                    "account": data.get('cc_number', ''),
                    "expiry": self.format_expiry(data.get('cc_expiry', '')),
                    "cvv": data.get('cc_cvc', ''),
                }
                tokenize_response = acquirer._cardpointe_tokenize(tokenize_data)
                token = ''
                if tokenize_response.get('token', '') and tokenize_response.get('errorcode', 0) in [0]:
                    token = tokenize_response.get('token')
                else:
                    message = tokenize_response.get('message', '')
                    if message:
                        return {
                            'result': 'Failed',
                            'message': 'Tokenization is failed with following reason : %s.'%(message)
                        }
                    else:
                        return {
                            'result': 'Failed',
                            'message': 'Tokenization is failed.'
                        }
                # Build payment data
                payment_data = {
                    'payment_type': 'card',
                    'token': token,
                    'card_name': partner.name,
                    "expiry": self.format_expiry(data.get('cc_expiry', '')),
                }

                # Process the payment
                payment_transaction._cardpoint_process_payment(payment_data, transaction_type)
                if payment_transaction.cardpoint_respcode in ['A'] and payment_transaction.cardpoint_retref:
                    transaction_ref = payment_transaction.cardpoint_retref
                    card_type = payment_transaction.cardpoint_account_type
                    transaction_response = payment_transaction.cardpoint_resptext
                else:
                    # C, D, F, P, R, E = declined/error
                    error_message = payment_transaction.cardpoint_resptext
                    if error_message:
                        self.env['otl.card.transaction.log'].create({
                            'sale_order_id': order.id,
                            'name': payment_transaction.cardpoint_retref,
                            'error_code': payment_transaction.cardpoint_respcode,
                            'message': error_message,
                            'state': 'failed',
                            'type': transaction_type_to_log,
                            'provider_id': acquirer.id
                        })
                        return {
                            'result': 'Failed',
                            'message': error_message
                        }
                _logger.info(
                    "CardPointe payment processed for transaction with reference %s, state: %s",
                    reference, payment_transaction.state,
                )
            else:
                return {
                    'result': 'Failed',
                    'message': 'Wrong Payment Acquirer.'
                }


            payment_transaction.write({'provider_reference': transaction_ref})
            payment_transaction._set_done()
            self.env['otl.card.transaction.log'].create({
                'sale_order_id': order.id,
                'name': transaction_ref,
                'message': transaction_response,
                'state': 'success',
                'type': transaction_type_to_log,
                'provider_id': acquirer.id

            })
            self.env.cr.commit()
            return {
                'result': 'Success',
                'transaction_id': transaction_ref,
                'card_type': card_type,
                'message': transaction_response,
            }

    def action_authcapture_ach_payment(self, data, allow_multiple_payment=False):
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
        acquirer = self.env.ref('otl_payment_cardpointe.payment_provider_cardpoint').sudo()
        card_type = ''
        for order in self:
            reference = order.name
            currency = order.currency_id
            partner = order.partner_id
            transaction_ref = ''
            transaction_response = ''
            payment_transaction = self.env['payment.transaction'].sudo().search([
                ('sale_order_ids', 'in', order.ids),
                ('state', 'in', ['draft'])
            ], limit=1)
            if not payment_transaction:
                reference = self.env['payment.transaction']._compute_reference(
                    acquirer.code)
                vals = {
                    'amount': data.get('amount', 0),
                    'currency_id': currency.id,
                    'partner_id': partner.id,
                    'provider_id': acquirer.id,
                    'sale_order_ids': [(6, 0, self.ids)],
                    'payment_method_id': self.env.ref('payment.payment_method_ach_direct_debit').id,
                    'reference': reference,
                    # 'acquirer_id': acquirer.id,
                    # 'acquirer_reference': response.get('transactionResponse', {}).get('transId', ''),
                    # 'date': fields.Datetime.now(),
                }
                payment_transaction = self.env['payment.transaction'].create([vals])

            if order.authorize_transaction_id and not allow_multiple_payment:
                acquirer._cardpoint_void_transaction(order.authorize_transaction_id)

            tokenize_data = {
                "account": "%s/%s"%(data.get('bank_routing_number', ''), data.get('bank_account_number', '')),
            }
            tokenize_response = acquirer._cardpointe_tokenize(tokenize_data)
            token = ''
            if tokenize_response.get('token', '') and tokenize_response.get('errorcode', 0) in [0]:
                token = tokenize_response.get('token')
            else:
                message = tokenize_response.get('message', '')
                if message:
                    return {
                        'result': 'Failed',
                        'message': 'Tokenization is failed with following reason : %s.' % (message)
                    }
                else:
                    return {
                        'result': 'Failed',
                        'message': 'Tokenization is failed.'
                    }

            # Build payment data
            payment_data = {
                'payment_type': 'ach_direct_debit',
                'token': token,
                'acct_type': data.get('acct_type', ''),
            }

            # Process the payment
            payment_transaction._cardpoint_process_payment(payment_data)
            if payment_transaction.cardpoint_respcode in ['A', 'B'] and payment_transaction.cardpoint_retref:
                transaction_ref = payment_transaction.cardpoint_retref
                transaction_response = payment_transaction.cardpoint_resptext
            else:
                # C, D, F, P, R, E = declined/error
                error_message = payment_transaction.cardpoint_resptext
                if error_message:
                    self.env['otl.card.transaction.log'].create({
                        'sale_order_id': order.id,
                        'name': payment_transaction.cardpoint_retref,
                        'error_code': payment_transaction.cardpoint_respcode,
                        'message': error_message,
                        'state': 'failed',
                        'type': 'authcapture',
                        'provider_id': acquirer.id
                    })
                    return {
                        'result': 'Failed',
                        'message': error_message
                    }
                _logger.info(
                    "CardPointe payment processed for transaction with reference %s, state: %s",
                    reference, payment_transaction.state,
                )

            payment_transaction.write({'provider_reference': transaction_ref})
            payment_transaction._set_done()
            self.env['otl.card.transaction.log'].create({
                'sale_order_id': order.id,
                'name': transaction_ref,
                'message': transaction_response,
                'state': 'success',
                'type': 'authcapture',
                'provider_id': acquirer.id
            })
            self.env.cr.commit()
            return {
                'result': 'Success',
                'transaction_id': transaction_ref,
                'card_type': card_type,
                'message': transaction_response,
            }

    def action_update_payment_data(self, data={}, existing_auth_transaction_id='', existing_card_type='', transaction_amount= 0, allow_multiple_payment=False):
        status = {
            'message': 'Sale order payment method update is failed due to some unknown reason',
            'result': 'Failed'
        }
        values = {}
        for order in self:
            if not transaction_amount:
                transaction_amount = order.down_payment_amount
            payment_method = data.get('payment_method', '')
            if payment_method not in ['credit_card', 'debit_card', 'cash', 'check', 'ach']:
                _logger.info("------ Wrong Payment Method-------------")
                status = {'message': 'Wrong Payment Method', 'result': 'Failed'}
                return status
            values.update({
                'payment_method': payment_method,
                'state': 'sale',
                'date_order': order.appointment_id.completed_date,
                'write_uid': self.env.user.id,
                'write_date': datetime.now().replace(tzinfo=pytz.utc),
                'pay_later': data.get('pay_later', 0) == 1 and True or False,
            })
            if order.invoice_ids and not allow_multiple_payment:
                _logger.info("------Payment Already Done------------")
                status = {
                    'message': 'Payment Already Done',
                    'result': 'Failed',
                }
                return status
            if not order.balance_finance:
                if payment_method:
                    if payment_method in ['credit_card', 'debit_card']:
                        values.update({'cards': True, 'cash': False, 'check': False})
                    if payment_method == 'cash':
                        values.update({'cash': True, 'cards': False, 'check': False})
                    if payment_method == 'check':
                        values.update({'check': True, 'cards': False, 'cash': False})
            if payment_method == 'check':
                check_account_number = ''
                check_routing_number = ''
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
                # else:
                #     _logger.info("------check_account_number Empty------------")
                #     status = {
                #         'message': 'check_account_number  Empty',
                #         'result': 'Failed',
                #     }
                #     return status
                if data.get('check_routing_number', ''):
                    check_routing_number = data.get('check_routing_number', "")
                # else:
                #     _logger.info("------check_routing_number Empty------------")
                #     status = {
                #         'message': 'check_routing_number  Empty',
                #         'result': 'Failed',
                #     }
                #     return status
                values.update({
                    'check_number': check_number,
                    'check_account_number': check_account_number,
                    'check_routing_number': check_routing_number,
                })
            elif payment_method in ['credit_card', 'debit_card']:
                if existing_auth_transaction_id:
                    values.update({
                        'authorize_transaction_id': existing_auth_transaction_id,
                        'card_type': existing_card_type
                    })
                    acquirer = False
                    payment_transaction = self.env['payment.transaction'].sudo().search([('provider_reference', '=', existing_auth_transaction_id)], limit=1)
                    if payment_transaction:
                        acquirer = payment_transaction.provider_id.id
                    if not order.card_transaction_log_line.filtered(lambda x: x.name == existing_auth_transaction_id):
                        transaction_type_to_log = "authcapture"
                        if order.pay_later:
                            transaction_type_to_log = "authorize"
                        self.env['otl.card.transaction.log'].create({
                            'sale_order_id': order.id,
                            'name': existing_auth_transaction_id,
                            'message': '',
                            'state': 'success',
                            'type': transaction_type_to_log,
                            'provider_id': acquirer.id
                        })

                else:
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
                    if data.get('expiry_date', 0):
                        card_expiry = data.get('expiry_date', 0)
                    else:
                        _logger.info("------expiry_date Empty------------")
                        status = {
                            'message': 'expiry_date  Empty',
                            'result': 'Failed',
                        }
                        return status
                    if data.get('card_name', ''):
                        card_holder_name = data.get('card_name', "")
                    else:
                        _logger.info("------card_name Empty------------")
                        status = {
                            'message': 'card_name  Empty',
                            'result': 'Failed',
                        }
                        return status
                    if data.get('card_pinorcvv', ''):
                        cardpin = data.get('card_pinorcvv', "")
                    else:
                        _logger.info("------card_pinorcvv Empty------------")
                        status = {
                            'message': 'card_pinorcvv  Empty',
                            'result': 'Failed',
                        }
                        return status
                    if card_expiry:
                        if '/' in card_expiry:
                            month, year = card_expiry.split('/')
                        elif '-' in card_expiry:
                            month, year = card_expiry.split('-')
                        if len(year) == 4:
                            year = year[2:]
                            card_expiry = '%s/%s' % (month, year)
                    payment_data = {
                        'sale_order_id': order.id,
                        'cc_number': card_number,
                        'cc_expiry': card_expiry,
                        'cc_cvc': cardpin,
                        'cc_holder_name': card_holder_name,
                        'amount': transaction_amount,
                        'pay_later': data.get('pay_later', 0),
                    }
                    payment_status = order.action_authcapture_payment(payment_data, allow_multiple_payment)
                    if payment_status['result'] == 'Success':
                        if payment_status.get('transaction_id', ''):
                            values.update({
                                'authorize_transaction_id': payment_status.get('transaction_id', '')
                            })
                        if payment_status.get('card_type', ''):
                            values.update({
                                'card_type': payment_status.get('card_type', '')
                            })
                    else:
                        _logger.info("------ Payment_Transaction Failed------------")
                        status = {
                            'result': 'Failed',
                            'message': payment_status['message'],
                        }
                        return status
            elif payment_method in ['ach']:
                if existing_auth_transaction_id:
                    values.update({
                        'authorize_transaction_id': existing_auth_transaction_id,
                        'card_type': existing_card_type
                    })
                    acquirer = False
                    payment_transaction = self.env['payment.transaction'].sudo().search([('provider_reference', '=', existing_auth_transaction_id)], limit=1)
                    if payment_transaction:
                        acquirer = payment_transaction.provider_id.id
                    if not order.card_transaction_log_line.filtered(lambda x: x.name == existing_auth_transaction_id):
                        transaction_type_to_log = "authcapture"
                        if order.pay_later:
                            transaction_type_to_log = "authorize"
                        self.env['otl.card.transaction.log'].create({
                            'sale_order_id': order.id,
                            'name': existing_auth_transaction_id,
                            'message': '',
                            'state': 'success',
                            'type': transaction_type_to_log,
                            'provider_id': acquirer.id
                        })
                else:
                    acct_type = ''
                    if data.get('acct_type', ''):
                        acct_type = data.get('acct_type', '')
                        if acct_type not in ['ECHK', 'ESAV']:
                            return {
                                'message': 'Wrong Value for Account Type',
                                'result': 'Failed',
                            }
                    else:
                        _logger.info("------acct_type Empty------------")
                        status = {
                            'message': 'Account Type   Empty',
                            'result': 'Failed',
                        }
                        return status
                    if data.get('bank_account_number', ''):
                        bank_account_number = data.get('bank_account_number', '')
                    else:
                        _logger.info("------bank_account_number Empty------------")
                        status = {
                            'message': 'bank_account_number  Empty',
                            'result': 'Failed',
                        }
                        return status
                    if data.get('bank_routing_number', ''):
                        bank_routing_number = data.get('bank_routing_number', '')
                    else:
                        _logger.info("------bank_routing_number Empty------------")
                        status = {
                            'message': 'bank_routing_number  Empty',
                            'result': 'Failed',
                        }
                        return status
                    values.update({
                        'check_account_number': bank_account_number,
                        'check_routing_number': bank_routing_number,
                    })
                    payment_data = {
                        'sale_order_id': order.id,
                        'bank_account_number': bank_account_number,
                        'bank_routing_number': bank_routing_number,
                        'amount': transaction_amount,
                        'acct_type': acct_type,
                    }
                    payment_status = order.action_authcapture_ach_payment(payment_data, allow_multiple_payment)
                    if payment_status['result'] == 'Success':
                        if payment_status.get('transaction_id', ''):
                            values.update({
                                'authorize_transaction_id': payment_status.get('transaction_id', '')
                            })
                    else:
                        _logger.info("------ Payment_Transaction Failed------------")
                        status = {
                            'result': 'Failed',
                            'message': payment_status['message'],
                        }
                        return status
            #[FIX] Dtd: 07/07/2023 - to solve concurrent update error, passing 'state' & 'order date' in values instead of calling action_confirm() function.
            #order.action_confirm()

            # [FIX] order update restricting to avoid concurrent error
            # if order.appointment_id.completed_date:
            #     order.write({'date_order': order.appointment_id.completed_date})
            status = {
                'message': 'Sale order payment method is updated successfully',
                'result': 'Success',
                'values': values
            }
        return status

    def action_format_date(self, date):
        date = date.replace('\\', '')
        try:
            date_formated = datetime.strptime(date, '%m/%d/%Y').strftime(DEFAULT_SERVER_DATE_FORMAT)
        except:
            date_formated = date
        return date_formated

    def action_create_credit_application(self, data):
        status = {
            'message': 'Credit application creation is failed due to some unknown reason',
            'result': 'Failed'
        }
        _logger.info('---action_create_credit_application data ---------------')
        _logger.info(data)
        for sale_order in self:
            appointment = sale_order.appointment_id or False
            appointment_id = int(data.get('appointment_id', 0))
            if not appointment or not appointment.exists():
                _logger.info("------ Appointment Not Exist-------------")
                status = {'message': 'Appointment Not Exist', 'result': 'Failed'}
                return status
            appointment_id = appointment.id
            team_credit_application = self.env['team.credit.application'].search([('appointment_id', '=', appointment_id)],
                                                                                 limit=1)
            if team_credit_application:
                team_credit_application.sudo().unlink()
            vals = {
                'order_id': sale_order.id,
                'appointment_id': appointment_id,
                'partner_id': sale_order.partner_id.id,
            }
            if int(data.get('co_applicant_skip', '0')) == 1:
                sale_order.write({'coapplicant_skip': True})
            else:
                sale_order.write({'coapplicant_skip': False})
            total_price = data.get('total_price', 0)
            if total_price:
                vals.update({'total_price': total_price})
            downpayment = data.get('downpayment', 0)
            if downpayment:
                vals.update({'downpayment': downpayment})
            amount_financed = data.get('amount_financed', 0)
            if amount_financed:
                vals.update({'amount_financed': amount_financed})
            type_of_loan = data.get('type_of_loan', 0)
            if type_of_loan:
                if type_of_loan not in ['Low Payment', 'No Interest', 'One Year no Payments']:
                    _logger.info("------ Wrong value for type_of_loan-------------")
                    status = {'message': 'Wrong value for type of loan', 'result': 'Failed'}
                    return status
                vals.update({'type_of_loan': type_of_loan})
                if type_of_loan == 'Low Payment':
                    vals.update({'low_payment': True})
                if type_of_loan == 'No Interest':
                    vals.update({'no_interest': True})
                if type_of_loan == 'One Year no Payments':
                    vals.update({'no_payment': True})
            type_of_property = data.get('type_of_property', "")
            if type_of_property:
                if type_of_property not in ['Single Family', 'Mobile Home', 'Condo']:
                    _logger.info("------ Wrong value for type_of_property-------------")
                    status = {'message': 'Wrong value for type of property', 'result': 'Failed'}
                    return status
                vals.update({'type_of_property': type_of_property})
                if type_of_property == 'Single Family':
                    vals.update({'single_family': True})
                if type_of_property == 'Mobile Home':
                    vals.update({'mobile_family': True})
                if type_of_property == 'Condo':
                    vals.update({'condoo': True})

            address_of_property = data.get('address_of_property', "")
            if address_of_property:
                vals.update({'address_of_property': address_of_property})

            applicant_first_name = data.get('applicant_first_name', "")
            if applicant_first_name:
                vals.update({'applicant_first_name': applicant_first_name})
            applicant_middle_name = data.get('applicant_middle_name', "")
            if applicant_middle_name:
                vals.update({'applicant_middle_name': applicant_middle_name})
            applicant_last_name = data.get('applicant_last_name', "")
            if applicant_last_name:
                vals.update({'applicant_last_name': applicant_last_name})
            drivers_license = data.get('drivers_license', "")
            if drivers_license:
                vals.update({'drivers_license': drivers_license})
            drivers_license_exp_date = data.get('drivers_license_exp_date', "")
            if drivers_license_exp_date:
                drivers_license_exp_date = self.action_format_date(drivers_license_exp_date)
                vals.update({'drivers_license_exp_date': drivers_license_exp_date})
            drivers_license_issue_date = data.get('drivers_license_issue_date', "")
            if drivers_license_issue_date:
                drivers_license_issue_date = self.action_format_date(drivers_license_issue_date)
                vals.update({'drivers_license_issue_date': drivers_license_issue_date})
            date_of_birth = data.get('date_of_birth', "")
            if date_of_birth:
                date_of_birth = self.action_format_date(date_of_birth)
                vals.update({'date_of_birth': date_of_birth})
            social_security_number = data.get('social_security_number', "")
            if social_security_number:
                vals.update({'social_security_number': social_security_number})
            address_of_applicant = data.get('address_of_applicant', "")
            if address_of_applicant:
                vals.update({'address_of_applicant': address_of_applicant})
            address_of_applicant_street = data.get('address_of_applicant_street', "")
            if address_of_applicant_street:
                vals.update({'address_of_applicant_street': address_of_applicant_street})
            address_of_applicant_street2 = data.get('address_of_applicant_street2', "")
            if address_of_applicant_street2:
                vals.update({'address_of_applicant_street2': address_of_applicant_street2})
            address_of_applicant_city = data.get('address_of_applicant_city', "")
            if address_of_applicant_city:
                vals.update({'address_of_applicant_city': address_of_applicant_city})
            address_of_applicant_state = data.get('address_of_applicant_state', "")
            if address_of_applicant_state:
                vals.update({'address_of_applicant_state': address_of_applicant_state})
            address_of_applicant_zip = data.get('address_of_applicant_zip', "")
            if address_of_applicant_zip:
                vals.update({'address_of_applicant_zip': address_of_applicant_zip})
            previous_address_of_applicant = data.get('previous_address_of_applicant', "")
            if previous_address_of_applicant:
                vals.update({'previous_address_of_applicant': previous_address_of_applicant})
            previous_address_of_applicant_street = data.get('previous_address_of_applicant_street', "")
            if previous_address_of_applicant_street:
                vals.update({'previous_address_of_applicant_street': previous_address_of_applicant_street})
            previous_address_of_applicant_street2 = data.get('previous_address_of_applicant_street2', "")
            if previous_address_of_applicant_street2:
                vals.update({'previous_address_of_applicant_street2': previous_address_of_applicant_street2})
            previous_address_of_applicant_city = data.get('previous_address_of_applicant_city', "")
            if previous_address_of_applicant_city:
                vals.update({'previous_address_of_applicant_city': previous_address_of_applicant_city})
            previous_address_of_applicant_state = data.get('previous_address_of_applicant_state', "")
            if previous_address_of_applicant_state:
                vals.update({'previous_address_of_applicant_state': previous_address_of_applicant_state})
            previous_address_of_applicant_zip = data.get('previous_address_of_applicant_zip', "")
            if previous_address_of_applicant_zip:
                vals.update({'previous_address_of_applicant_zip': previous_address_of_applicant_zip})
            co_applicant_email = data.get('co_applicant_email', "")
            if co_applicant_email:
                vals.update({'co_applicant_email': co_applicant_email})
            co_applicant_phone = data.get('co_applicant_phone', "")
            if co_applicant_phone:
                vals.update({'co_applicant_phone': co_applicant_phone})
            co_applicant_secondary_phone = data.get('co_applicant_secondary_phone', "")
            if co_applicant_secondary_phone:
                vals.update({'co_applicant_secondary_phone': co_applicant_secondary_phone})
            applicant_email = data.get('applicant_email', "")
            if applicant_email:
                vals.update({'applicant_email': applicant_email})
            cell_phone = data.get('cell_phone', "")
            if cell_phone:
                vals.update({'cell_phone': cell_phone})
            home_phone = data.get('home_phone', "")
            if home_phone:
                vals.update({'home_phone': home_phone})
            how_long = data.get('how_long', "")
            if how_long:
                vals.update({'how_long': how_long})
            previous_address_how_long = data.get('previous_address_how_long', "")
            if previous_address_how_long:
                vals.update({'previous_address_how_long': previous_address_how_long})
            present_employer = data.get('present_employer', "")
            if present_employer:
                vals.update({'present_employer': present_employer})
            years_on_job = data.get('years_on_job', "")
            if years_on_job:
                vals.update({'years_on_job': years_on_job})
            occupation = data.get('occupation', "")
            if occupation:
                vals.update({'occupation': occupation})
            present_employers_address = data.get('present_employers_address', "")
            if present_employers_address:
                vals.update({'present_employers_address': present_employers_address})
            present_employers_address_street = data.get('present_employers_address_street', "")
            if present_employers_address_street:
                vals.update({'present_employers_address_street': present_employers_address_street})
            present_employers_address_street2 = data.get('present_employers_address_street2', "")
            if present_employers_address_street2:
                vals.update({'present_employers_address_street2': present_employers_address_street2})
            present_employers_address_city = data.get('present_employers_address_city', "")
            if present_employers_address_city:
                vals.update({'present_employers_address_city': present_employers_address_city})
            present_employers_address_state = data.get('present_employers_address_state', "")
            if present_employers_address_state:
                vals.update({'present_employers_address_state': present_employers_address_state})
            present_employers_address_zip = data.get('present_employers_address_zip', "")
            if present_employers_address_zip:
                vals.update({'present_employers_address_zip': present_employers_address_zip})
            earnings_from_employment = data.get('earnings_from_employment', "")
            if earnings_from_employment:
                vals.update({'earnings_from_employment': earnings_from_employment})
                vals.update({'is_earning_from_employment': True})
            supervisor_or_department = data.get('supervisor_or_department', "")
            if supervisor_or_department:
                vals.update({'supervisor_or_department': supervisor_or_department})
            employers_phone_number = data.get('employers_phone_number', "")
            if employers_phone_number:
                vals.update({'employers_phone_number': employers_phone_number})
            previous_employers_address = data.get('previous_employers_address', "")
            if previous_employers_address:
                vals.update({'previous_employers_address': previous_employers_address})
            previous_employers_address_street = data.get('previous_employers_address_street', "")
            if previous_employers_address_street:
                vals.update({'previous_employers_address_street': previous_employers_address_street})
            previous_employers_address_street2 = data.get('previous_employers_address_street2', "")
            if previous_employers_address_street2:
                vals.update({'previous_employers_address_street2': previous_employers_address_street2})
            previous_employers_address_city = data.get('previous_employers_address_city', "")
            if previous_employers_address_city:
                vals.update({'previous_employers_address_city': previous_employers_address_city})
            previous_employers_address_state = data.get('previous_employers_address_state', "")
            if previous_employers_address_state:
                vals.update({'previous_employers_address_state': previous_employers_address_state})
            previous_employers_address_zip = data.get('previous_employers_address_zip', "")
            if previous_employers_address_zip:
                vals.update({'previous_employers_address_zip': previous_employers_address_zip})
            earnings_per_month = data.get('earnings_per_month', "")
            if earnings_per_month:
                vals.update({'earnings_per_month': earnings_per_month})
            years_on_job_previous_employer = data.get('years_on_job_previous_employer', "")
            if years_on_job_previous_employer:
                vals.update({'years_on_job_previous_employer': years_on_job_previous_employer})
            occupation_previous_employer = data.get('occupation_previous_employer', "")
            if occupation_previous_employer:
                vals.update({'occupation_previous_employer': occupation_previous_employer})
            previous_employers_phone_number = data.get('previous_employers_phone_number', "")
            if previous_employers_phone_number:
                vals.update({'previous_employers_phone_number': previous_employers_phone_number})
            co_applicant_first_name = data.get('co_applicant_first_name', "")
            if co_applicant_first_name:
                vals.update({'co_applicant_first_name': co_applicant_first_name})
            co_applicant_middle_name = data.get('co_applicant_middle_name', "")
            if co_applicant_middle_name:
                vals.update({'co_applicant_middle_name': co_applicant_middle_name})
            co_applicant_last_name = data.get('co_applicant_last_name', "")
            if co_applicant_last_name:
                vals.update({'co_applicant_last_name': co_applicant_last_name})
            co_applicant_drivers_license = data.get('co_applicant_drivers_license', "")
            if co_applicant_drivers_license:
                vals.update({'co_applicant_drivers_license': co_applicant_drivers_license})
            co_applicant_drivers_license_exp_date = data.get('co_applicant_drivers_license_exp_date', "")
            if co_applicant_drivers_license_exp_date:
                co_applicant_drivers_license_exp_date = self.action_format_date(co_applicant_drivers_license_exp_date)
                vals.update({'co_applicant_drivers_license_exp_date': co_applicant_drivers_license_exp_date})
            co_applicant_drivers_license_issue_date = data.get('co_applicant_drivers_license_issue_date', "")
            if co_applicant_drivers_license_issue_date:
                co_applicant_drivers_license_issue_date = self.action_format_date(co_applicant_drivers_license_issue_date)
                vals.update({'co_applicant_drivers_license_issue_date': co_applicant_drivers_license_issue_date})
            co_applicant_date_of_birth = data.get('co_applicant_date_of_birth', "")
            if co_applicant_date_of_birth:
                co_applicant_date_of_birth = self.action_format_date(co_applicant_date_of_birth)
                vals.update({'co_applicant_date_of_birth': co_applicant_date_of_birth})
            co_applicant_social_security_number = data.get('co_applicant_social_security_number', "")
            if co_applicant_social_security_number:
                vals.update({'co_applicant_social_security_number': co_applicant_social_security_number})
            co_applicant_address_of_applicant = data.get('co_applicant_address_of_applicant', "")
            if co_applicant_address_of_applicant:
                vals.update({'co_applicant_address_of_applicant': co_applicant_address_of_applicant})
            co_applicant_street = data.get('co_applicant_street', "")
            if co_applicant_street:
                vals.update({'co_applicant_street': co_applicant_street})
            co_applicant_street2 = data.get('co_applicant_street2', "")
            if co_applicant_street2:
                vals.update({'co_applicant_street2': co_applicant_street2})
            co_applicant_city = data.get('co_applicant_city', "")
            if co_applicant_city:
                vals.update({'co_applicant_city': co_applicant_city})
            co_applicant_state = data.get('co_applicant_state', "")
            if co_applicant_state:
                vals.update({'co_applicant_state': co_applicant_state})
            co_applicant_zip = data.get('co_applicant_zip', "")
            if co_applicant_zip:
                vals.update({'co_applicant_zip': co_applicant_zip})
            co_applicant_previous_address_of_applicant = data.get('co_applicant_previous_address_of_applicant', "")
            if co_applicant_previous_address_of_applicant:
                vals.update({'co_applicant_previous_address_of_applicant': co_applicant_previous_address_of_applicant})
            co_applicant_previous_street = data.get('co_applicant_previous_street', "")
            if co_applicant_previous_street:
                vals.update({'co_applicant_previous_street': co_applicant_previous_street})
            co_applicant_previous_street2 = data.get('co_applicant_previous_street2', "")
            if co_applicant_previous_street2:
                vals.update({'co_applicant_previous_street2': co_applicant_previous_street2})
            co_applicant_previous_city = data.get('co_applicant_previous_city', "")
            if co_applicant_previous_city:
                vals.update({'co_applicant_previous_city': co_applicant_previous_city})
            co_applicant_previous_state = data.get('co_applicant_previous_state', "")
            if co_applicant_previous_state:
                vals.update({'co_applicant_previous_state': co_applicant_previous_state})
            co_applicant_previous_zip = data.get('co_applicant_previous_zip', "")
            if co_applicant_previous_zip:
                vals.update({'co_applicant_previous_zip': co_applicant_previous_zip})
            co_applicant_how_long = data.get('co_applicant_how_long', "")
            if co_applicant_how_long:
                vals.update({'co_applicant_how_long': co_applicant_how_long})
            co_applicant_present_employer = data.get('co_applicant_present_employer', "")
            if co_applicant_present_employer:
                vals.update({'co_applicant_present_employer': co_applicant_present_employer})
            co_applicant_years_on_job = data.get('co_applicant_years_on_job', "")
            if co_applicant_years_on_job:
                vals.update({'co_applicant_years_on_job': co_applicant_years_on_job})
            co_applicant_occupation = data.get('co_applicant_occupation', "")
            if co_applicant_occupation:
                vals.update({'co_applicant_occupation': co_applicant_occupation})
            co_applicant_present_employers_address = data.get('co_applicant_present_employers_address', "")
            if co_applicant_present_employers_address:
                vals.update({'co_applicant_present_employers_address': co_applicant_present_employers_address})
            co_applicant_present_employers_street = data.get('co_applicant_present_employers_street', "")
            if co_applicant_present_employers_street:
                vals.update({'co_applicant_present_employers_street': co_applicant_present_employers_street})
            co_applicant_present_employers_street2 = data.get('co_applicant_present_employers_street2', "")
            if co_applicant_present_employers_street2:
                vals.update({'co_applicant_present_employers_street2': co_applicant_present_employers_street2})
            co_applicant_present_employers_city = data.get('co_applicant_present_employers_city', "")
            if co_applicant_present_employers_city:
                vals.update({'co_applicant_present_employers_city': co_applicant_present_employers_city})
            co_applicant_present_employers_state = data.get('co_applicant_present_employers_state', "")
            if co_applicant_present_employers_state:
                vals.update({'co_applicant_present_employers_state': co_applicant_present_employers_state})
            co_applicant_present_employers_zip = data.get('co_applicant_present_employers_zip', "")
            if co_applicant_present_employers_zip:
                vals.update({'co_applicant_present_employers_zip': co_applicant_present_employers_zip})
            co_applicant_earnings_from_employment = data.get('co_applicant_earnings_from_employment', "")
            if co_applicant_earnings_from_employment:
                vals.update({'co_applicant_earnings_from_employment': co_applicant_earnings_from_employment})
            co_applicant_supervisor_or_department = data.get('co_applicant_supervisor_or_department', "")
            if co_applicant_supervisor_or_department:
                vals.update({'co_applicant_supervisor_or_department': co_applicant_supervisor_or_department})
            co_applicant_employers_phone_number = data.get('co_applicant_employers_phone_number', "")
            if co_applicant_employers_phone_number:
                vals.update({'co_applicant_employers_phone_number': co_applicant_employers_phone_number})
            co_applicant_previous_employers_address = data.get('co_applicant_previous_employers_address', "")
            if co_applicant_previous_employers_address:
                vals.update({'co_applicant_previous_employers_address': co_applicant_previous_employers_address})
            co_applicant_previous_employers_street = data.get('co_applicant_previous_employers_street', "")
            if co_applicant_previous_employers_street:
                vals.update({'co_applicant_previous_employers_street': co_applicant_previous_employers_street})
            co_applicant_previous_employers_street2 = data.get('co_applicant_previous_employers_street2', "")
            if co_applicant_previous_employers_street2:
                vals.update({'co_applicant_previous_employers_street2': co_applicant_previous_employers_street2})
            co_applicant_previous_employers_city = data.get('co_applicant_previous_employers_city', "")
            if co_applicant_previous_employers_city:
                vals.update({'co_applicant_previous_employers_city': co_applicant_previous_employers_city})
            co_applicant_previous_employers_state = data.get('co_applicant_previous_employers_state', "")
            if co_applicant_previous_employers_state:
                vals.update({'co_applicant_previous_employers_state': co_applicant_previous_employers_state})
            co_applicant_previoust_employers_zip = data.get('co_applicant_previoust_employers_zip', "")
            if co_applicant_previoust_employers_zip:
                vals.update({'co_applicant_previoust_employers_zip': co_applicant_previoust_employers_zip})
            co_applicant_earnings_per_month = data.get('co_applicant_earnings_per_month', "")
            if co_applicant_earnings_per_month:
                vals.update({'co_applicant_earnings_per_month': co_applicant_earnings_per_month})
            co_applicant_years_on_job_previous_employer = data.get('co_applicant_years_on_job_previous_employer', "")
            if co_applicant_years_on_job_previous_employer:
                vals.update({'co_applicant_years_on_job_previous_employer': co_applicant_years_on_job_previous_employer})
            co_applicant_occupation_previous_employer = data.get('co_applicant_occupation_previous_employer', "")
            if co_applicant_occupation_previous_employer:
                vals.update({'co_applicant_occupation_previous_employer': co_applicant_occupation_previous_employer})
            co_applicant_previous_employers_phone_number = data.get('co_applicant_previous_employers_phone_number', "")
            if co_applicant_previous_employers_phone_number:
                vals.update({'co_applicant_previous_employers_phone_number': co_applicant_previous_employers_phone_number})
            source_of_other_income = data.get('source_of_other_income', "")
            if source_of_other_income:
                if source_of_other_income not in ['Social Security', 'Pension', 'Child Support', 'Rental', 'Other']:
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
                vals.update({'address_relationship_state': address_relationship_state})
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
                vals.update({'lender_address_state': lender_address_state})
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
                date_aquired = self.action_format_date(date_aquired)
                vals.update({'date_aquired': date_aquired})
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
            race = race.replace("\\", "")
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
                    if not data.get('applicant_otherRace', ''):
                        _logger.info("------ Wrong value for applicant_otherRace-------------")
                        status = {'message': 'No value entered for applicant Other Race', 'result': 'Failed'}
                        return status
            sex = data.get('sex', "")
            if sex:
                if sex not in ['Male', 'Female']:
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
                if marital_status not in ['Married', 'Unmarried', 'Separated']:
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
            co_applicant_race = co_applicant_race.replace("\\", "")
            if co_applicant_race and co_applicant_race != 'Select':
                if co_applicant_race not in ['I do not wish to furnish this information',
                                             'American Indian or Alaskan Native',
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
                    if not data.get('co_applicant_otherRace', ''):
                        _logger.info("------ Wrong value for co_applicant_otherRace-------------")
                        status = {'message': 'No value entered for Co Applicant Other Race', 'result': 'Failed'}
                        return status
            co_applicant_sex = data.get('co_applicant_sex', "")
            if co_applicant_sex:
                if co_applicant_sex not in ['Male', 'Female']:
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
                if co_applicant_marital_status not in ['Married', 'Unmarried', 'Separated']:
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
                if type_of_credit_requested not in ['Individual Credit - relying solely on my income or assets',
                                                    'Joint Credit - We intend to apply for joint credit',
                                                    'Individual Credit - relying on my income or assets as well as income or assets from other sources']:
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
                applicant_signature_date = self.action_format_date(applicant_signature_date)
                vals.update({'applicant_signature_date': applicant_signature_date})
            co_applicant_signature_date = data.get('co_applicant_signature_date', "")
            if co_applicant_signature_date:
                co_applicant_signature_date = self.action_format_date(co_applicant_signature_date)
                vals.update({'co_applicant_signature_date': co_applicant_signature_date})
            hunter_message_status = False
            if data.get('hunterMessageStatus', 'No') == 'Yes':
                hunter_message_status = True
            vals.update({
                'applicant_other_race': data.get('applicant_otherRace', ''),
                'co_applicant_other_race': data.get('co_applicant_otherRace', ''),
                'hunter_message_status': hunter_message_status,
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
            second_mortage = data.get('second_mortage', '')
            if second_mortage:
                if second_mortage not in ['Yes', 'No']:
                    return {'message': 'Wrong value for Second Mortage (Yes / No)', 'result': 'Failed'}
                vals.update({'second_mortage': second_mortage})
            property_details = data.get('property_details', "")
            if property_details:
                if property_details not in ['MORTGAGE', 'LAND', 'CONTRACT', 'FREE AND CLEAR']:
                    _logger.info("------ Wrong value for property_details-------------")
                    status = {'message': 'Wrong value for property_details', 'result': 'Failed'}
                    return status
                vals.update({'property_details': property_details})
            _logger.info('------------------create_credit_application vals-----------')
            _logger.info(vals)
            team_credit_application = self.env['team.credit.application'].create(vals)
            _logger.info("------Credit application created: %s"%(team_credit_application))
            status = {
                'message': 'Credit Application is created successfully',
                'result': 'Success',
                'team_credit_application_id': team_credit_application.id
            }
        return status

    @api.model
    def action_generate_contract_document(self, data):
        result = {
            'message': 'Something went wrong while creating contract document',
            'result': 'Failed'
        }
        _logger.info("------action_generate_contract_document data: %s-------------" % (data))
        try:
            sign_req_obj = self.env['otl_document_sign.request']
            sign_req_item_obj = self.env['otl_document_sign.request.item']
            appointment_id = data.get('appointment_id', 0) and int(data.get('appointment_id', 0)) or 0
            contract_plumbing_option_1 = data.get('contract_plumbing_option_1', 0)
            contract_plumbing_option_2 = data.get('contract_plumbing_option_2', 0)
            send_physical_document = False
            if data.get('send_physical_document', 0) == 1:
                send_physical_document = True
            flexible_installation = False
            if data.get('flexible_installation', 0) == 1:
                flexible_installation = True
            destination_selection_id = False
            if data.get('destination_selection_id', False):
                destination_selection_id = int(data.get('destination_selection_id', 0))
                destination_selection = self.env['otl.appointment.result.reason'].browse(destination_selection_id)
                if not destination_selection or not destination_selection.exists():
                    return {'message': 'Wrong value for Destination Selection', 'result': 'Failed'}
            if appointment_id:
                appointment = self.env['team.customer.appointment'].browse(appointment_id)
                if appointment.exists():
                    appointment_vals = {
                        'additional_comments': data.get('additional_comments', ''),
                        'send_physical_document':  send_physical_document,
                        'flexible_installation':  flexible_installation,
                    }
                    if destination_selection_id:
                        appointment_vals.update({'destination_selection_id': destination_selection_id})
                    appointment.write(appointment_vals)
                    order = self.search([('appointment_id', '=', appointment_id)], limit=1)
                    if not order:
                        return {
                            'message': 'Sale order is not found against the appointment',
                            'result': 'Failed'
                        }
                    if not order.room_measurement_line:
                        team_room_obj = self.env['team.contract.room.measurement.line'].search(
                            [('appointment_id', '=', appointment_id)])
                        if team_room_obj:
                            team_room_obj.write({'order_id': order.id})
                    if not order.contract_question_line:
                        team_question_obj = self.env['team.contract.question.line'].search(
                            [('appointment_id', '=', appointment_id)])
                        if team_question_obj:
                            team_question_obj.write({'order_id': order.id})
                    if not order.room_transition_line:
                        room_transition_obj = self.env['team.contract.transition.line'].search(
                            [('appointment_id', '=', appointment_id)])
                        if room_transition_obj:
                            room_transition_obj.write({'order_id': order.id})
                    model_id = self.env['ir.model'].sudo().search([('model', '=', 'sale.order')], limit=1)
                    sign_requests = self.env['otl_document_sign.request'].sudo().search(
                        [('model_id', '=', model_id.id), ('res_id', '=', order.id)], order='create_date desc')
                    if sign_requests:
                        sign_logs = self.env['otl_document_sign.log'].search(
                            [('sign_request_id', 'in', sign_requests.ids)])
                        if sign_logs:
                            sign_logs.sudo().with_context(delete_log=True).unlink()
                        sign_requests.sudo().unlink()
                    order_vals = {}
                    if order.appointment_id.completed_date:
                        order_vals.update({'date_order': order.appointment_id.completed_date})
                    if data.get('recision_date', False):
                        order_vals.update({'recision_date': data.get('recision_date', False)})
                    if order_vals:
                        order.write(order_vals)
                    if appointment.app_version_id:
                        if order.coapplicant_skip or not order.appointment_id.co_applicant:
                            document_template_id = appointment.app_version_id.sale_contract_tmpl_id_ncp.id or False
                        else:
                            document_template_id = appointment.app_version_id.sale_contract_tmpl_id.id or False
                    else:
                        if order.coapplicant_skip or not order.appointment_id.co_applicant:
                            document_template_id = self.env['ir.config_parameter'].sudo().get_param(
                                'team_sale_contract.sale_contract_tmpl_id_ncp') or False
                        else:
                            document_template_id = self.env['ir.config_parameter'].sudo().get_param(
                                'team_sale_contract.sale_contract_tmpl_id') or False
                    if document_template_id:
                        template = self.env['otl_document_sign.template'].sudo().browse(int(document_template_id))
                        # if template.sign_item_ids.filtered(lambda x: x.type_id.option_field):
                        #     if (contract_plumbing_option_1 and contract_plumbing_option_2) or \
                        #             (not contract_plumbing_option_1 and not contract_plumbing_option_2):
                        #         return {
                        #             'result': 'Failed',
                        #             'message': 'Plumbing option should select either one option'
                        #         }
                        vals = {
                            'template_id': template.id,
                            'reference': template.name,
                            'model_id': template.model_id.id,
                            'res_id': order.id,
                        }
                        sign_request = sign_req_obj.create(vals)
                        if sign_request:
                            item_vals = {
                                'partner_id': order.partner_id.id,
                                'sign_request_id': sign_request.id,
                                'role_id': template.sign_item_ids and template.sign_item_ids.mapped('responsible_id').id,

                            }
                            request_item = sign_req_item_obj.create(item_vals)
                            if request_item:
                                sign_request.action_sent()
                                current_request_item = sign_request.request_item_ids
                                sign_item_types = self.env['otl_document_sign.item.type'].sudo().search_read(
                                    [('model_id', '=', template.model_id.id)])
                                if current_request_item:
                                    for item_type in sign_item_types:
                                        if item_type['auto_field']:
                                            auto_fields = item_type['auto_field'].split('.')
                                            selected_record = self.env[
                                                current_request_item.model_id.model].sudo().search(
                                                [('id', '=', current_request_item.res_id)], limit=1)
                                            auto_field = selected_record if selected_record else current_request_item.partner_id
                                            for field in auto_fields:
                                                if auto_field and field in auto_field:
                                                    auto_field = auto_field[field]
                                                else:
                                                    auto_field = ""
                                                    break
                                            if auto_field == 0.0:
                                                if isinstance(auto_field, bool):
                                                    auto_field = ''
                                                else:
                                                    auto_field = '0.0'
                                            if isinstance(auto_field, date):
                                                lg = self.env['res.lang']._lang_get(self.env.user.lang)
                                                auto_field = auto_field.strftime(lg.date_format) or auto_field
                                            SignItemValue = self.env['otl_document_sign.request.item.value']
                                            sign_item_ids = sign_request.template_id.sign_item_ids.filtered(lambda
                                                                                                                r: not r.responsible_id or r.responsible_id.id == request_item.role_id.id)
                                            for sign_item_id in sign_item_ids:
                                                id_sign_item = False
                                                if sign_item_id.type_id.id == int(item_type['id']):
                                                    id_sign_item = sign_item_id
                                                if id_sign_item:
                                                    if item_type['option_field']  == 'option':
                                                        if item_type['name']  == 'initials7' and not contract_plumbing_option_1:
                                                            continue
                                                        elif item_type['name']  == 'initials8' and not contract_plumbing_option_2:
                                                            continue

                                                    item_value = SignItemValue.create(
                                                        {'sign_item_id': id_sign_item.id, 'sign_request_id': sign_request.id,
                                                         'value': auto_field, 'sign_request_item_id': request_item.id})
                                sr_values = self.env['otl_document_sign.request.item.value'].sudo().search(
                                    [('sign_request_id', '=', sign_request.id)])
                                item_values = {}
                                for value in sr_values:
                                    item_values[value.sign_item_id.id] = value.value
                                request_item.sign(request_item.signature)
                                current_date = fields.Date.context_today(self).strftime(DEFAULT_SERVER_DATE_FORMAT)
                                request_item.write({'signing_date': current_date, 'state': 'completed'})
                                # request_item.action_completed()
                                # sign_request.action_signed()
                                sign_request.write({'state': 'signed'})
                                # appointment.write({'start_sync_to_i360': True})
                        result = {
                            'message': 'Document created successfully',
                            'result': 'Success',
                        }
                        _logger.info("------Document created successfully-------------")
                else:
                    _logger.info("------Wrong Appointment id-------------")
                    result = {
                        'message': 'Wrong Appointment id',
                        'result': 'Failed'
                    }
            else:
                _logger.info("------Empty Appointment id-------------")
                result = {
                    'message': 'Empty Appointment id',
                    'result': 'Failed'
                }
        except:
            result = {
                'message': 'Something went wrong.',
                'result': 'Failed'
            }
        _logger.info("------action_generate_contract_document result: %s-------------" % (result))
        return result


class IRAttachment(models.Model):
    _inherit = 'ir.attachment'

    appointment_id = fields.Many2one('team.customer.appointment', 'Appointment')
    image_type = fields.Selection([
        ('measurement_image', 'Measurement Image'),
        ('protrusion_image', 'Anomaly Image'),
        ('room_photo', 'Room Images'),
        ('applicant_signature', 'Applicant Sign'),
        ('applicant_initial', 'Applicant Initial'),
        ('co_applicant_signature', 'Co-Applicant Sign'),
        ('co_applicant_initial', 'Co-Applicant Initial'),
        ('snapshot', 'Snapshot'),
    ], string='Image Type')

    @api.model
    def action_upload_images(self, data):
        attachment_id = False
        image_list = []
        image_already_existing= True
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        file_name = data.get('file_name', 'Attachment').replace(" ", "_").replace(":", "_")
        if data.get('image', False):
            vals = {
                'name': file_name,
                'datas': data.get('image'),
                'image_type': data.get('image_type', ''),
                'store_fname': file_name,
            }
            if data.get('appointment_id', False):
                vals.update({
                    'appointment_id': int(data.get('appointment_id', 0))
                })
            attachment = self.env['ir.attachment'].sudo().search([
                ('name', '=', file_name),
                ('appointment_id', '=', int(data.get('appointment_id', '0')))
            ], limit=1)
            if not attachment:
                attachment = self.env['ir.attachment'].sudo().create(vals)
                image_already_existing = False
            if attachment:
                if not attachment.datas:
                    attachment.write({'datas': data.get('image')})
                    image_already_existing = False
                attachment.generate_access_token()
                if attachment.access_token:
                    image_list.append({'attachment_id': attachment.id,
                                 'name': attachment.name,
                                 'image_already_existing': image_already_existing,
                                 'url': base_url + '/web/image/' + str(attachment.id) + '?access_token=' + str(
                                     attachment.access_token)})

        return image_list
    @api.model
    def upload_compressed_files(self, data):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        appointment_id = data.get('appointment_id', False)
        appointment = False
        if data.get('image', False):
            vals = {
                'name': data.get('file_name', 'Attachment'),
                'datas': data.get('image')
            }
            if data.get('appointment_id', False):
                appointment = self.env['team.customer.appointment'].browse(appointment_id)
                vals.update({'appointment_id':appointment.id})
            attachment = self.env['ir.attachment'].sudo().create(vals)
            if attachment:
                attachment.generate_access_token()
                if attachment.access_token:
                    appointment.write({'compressed_attachment_id':attachment.id})
                    return {'attachment_id': attachment.id,
                            'name': attachment.name,

                            'url': base_url + '/web/image/' + str(attachment.id) + '?access_token=' + str(
                                attachment.access_token)}

        return False
    

class VersatileCreditApplication(models.Model):
    _inherit = 'otl.versatile.credit.application'

    def convert_date_to_utc(self, date, tz):
        # Step 1: Trim nanoseconds → microseconds (6 digits)
        date = re.sub(r"(\.\d{6})\d+Z", r"\1Z", date)
        # Step 2: Handle case where no microseconds exist
        if "." not in date:
            date = date.replace("Z", ".000000Z")
        date_obj = datetime.strptime(date, '%Y-%m-%dT%H:%M:%S.%fZ')
        date_utc = tz.localize(date_obj).astimezone(pytz.utc).strftime('%Y-%m-%d %H:%M:%S')
        return date_utc

    @api.model
    def action_create_versatile_credit_application(self, versatile_payload={}):
        result = {
            "result": "Failed",
            "message": "Something went wrong"
        }
        user = self.env.user
        data = versatile_payload.get("data", {})
        webhook_event_id = versatile_payload.get('id', "")
        event_type = versatile_payload.get('type', "")
        event_date = versatile_payload.get('dateTime', "")
        application_id = data.get("applicationId", "")
        ext_customer_id = data.get("externalCustomerId", "")
        finance_provider = data.get("financeProvider", "versatile")
        if not ext_customer_id:
            return {"result": "Failed", "message": "externalCustomerId is missing"}
        appointment = self.env['team.customer.appointment'].search([('improveit_appointment_id', '=', ext_customer_id)], limit=1)
        if not appointment:
            return {"result": "Failed", "message": "Appointment is not found related to the External Customer ID '%s'."%(ext_customer_id)}
        credit_application = self.search([('appointment_id', '=', appointment.id)], limit=1)
        tz = user.tz and pytz.timezone(user.tz) or pytz.utc
        timezone = user.tz or 'UTC'
        if event_date:
            event_date = self.convert_date_to_utc(event_date, tz)

        account_id = data.get("accountId", "")
        provider = data.get("providerId", "")
        session_id = data.get("sessionId", "")
        provider_reference = data.get("providerReferenceNumber", "")
        status = data.get("status", "")
        submitted_date = data.get("submittedDateTime", False)
        if submitted_date:
            submitted_date = self.convert_date_to_utc(submitted_date, tz)
        approved_amount_cent = data.get("approvedAmount", "")
        applicant_data = data.get("applicant", {}) and data.get("applicant", {}) or {}
        co_applicant_data = data.get("jointApplicant", {}) and data.get("jointApplicant", {}) or {}
        applicant_first_name = ''
        applicant_last_name = ''
        co_applicant_first_name = ''
        co_applicant_last_name = ''
        if applicant_data:
            applicant_first_name = applicant_data.get("firstName", "")
            applicant_last_name = applicant_data.get("lastName", "")
        if co_applicant_data:
            co_applicant_first_name = co_applicant_data.get("firstName", "")
            co_applicant_last_name = co_applicant_data.get("lastName", "")
        error_list = data.get("errors", [])
        vals = {
            "webhook_event_id": webhook_event_id,
            "event_type": event_type,
            "event_date": event_date,
            "appointment_id": appointment.id,
            "application_id": application_id,
            "account_id": account_id,
            "provider": provider,
            "session_id": session_id,
            "provider_reference": provider_reference,
            "status": status,
            "submitted_date": submitted_date,
            "approved_amount_cent": approved_amount_cent,
            "ext_customer_id": ext_customer_id,
            "applicant_first_name": applicant_first_name,
            "applicant_last_name": applicant_last_name,
            "co_applicant_first_name": co_applicant_first_name,
            "co_applicant_last_name": co_applicant_last_name,
            "finance_provider": finance_provider,
            "error_line": [(0, 0, {"name": error}) for error in error_list],
        }
        if credit_application:
            credit_application.write(vals)
            result = {
                "result": "Success",
                "message": "Credit Application Updated Successfully",
                "credit_application_id": credit_application.id
            }
        else:
            credit_application = self.create(vals)
            result = {
                "result": "Success",
                "message": "Credit Application Created Successfully",
                "credit_application_id": credit_application.id
            }
        return result



from odoo import models, fields, api, _, http
from odoo.exceptions import ValidationError, UserError
import uuid
from odoo.addons.payment.controllers.portal import PaymentProcessing
import requests
import base64
import json
from datetime import datetime,timedelta,date
from datetime import date
from dateutil.relativedelta import relativedelta
import logging
_logger = logging.getLogger(__name__)
from odoo.addons.team_api_configuration.controllers.configurations import URL, DB, API_USER_ID, API_USER_PASSWORD
from werkzeug import FileStorage
from io import BytesIO
from requests_toolbelt import MultipartEncoder
from odoo.http import content_disposition, Controller, request, route
TIMEOUT = 50
import pytz
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT

from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)


# class TeamFloorType(models.Model):
#     _name='team.floor.type'

class ResPartner(models.Model):
    _inherit = 'res.partner'

    state_code = fields.Char('State Code')


class TeamCustomerAppointment(models.Model):
    _inherit = "team.customer.appointment"

    @api.model
    def create(self, vals):
        if not vals.get('customer_name', ''):
            customer_name = (vals.get('applicant_first_name','') or '') + ' ' + (
                vals.get('applicant_middle_name','') or '') + ' ' + (vals.get('applicant_last_name','') or '')
            vals.update({'customer_name': customer_name})
        return super(TeamCustomerAppointment, self).create(vals)

    def write(self, vals):
        _logger.info('inside appointment-%s write: values -  %s' % (self and self[0].name or '', vals))
        if not self.customer_name:
            customer_name = (self.applicant_first_name or '') + ' ' + (self.applicant_middle_name or '') + '  ' + (
                        self.applicant_last_name or '')
            vals.update({'customer_name': customer_name})
        return super(TeamCustomerAppointment, self).write(vals)

    def update_arrival_departure_time_in_i360(self):
        result = {
            "success": "true",
            "errors": []
        }
        try:
            configurations = self.env['team.improveit.configuration'].search(
                [('api_type', '=', 'boomi')], limit=1)
            for appointment in self:
                _logger.info('--------Starting SalesRepArrivalDeparture API Appointment ID---------: %s' % (appointment.id))
                if appointment.improveit_appointment_id and appointment.arrival_date and appointment.departure_date:
                    if appointment.arrival_departure_synced:
                        return {
                            "success": "false",
                            "errors": [{"message": "It is already synced to i360."}]
                        }
                    data = {
                        'AppointmentID': appointment.improveit_appointment_id or '',
                        'SalesRepArrivalTime': appointment.arrival_date.strftime('%Y-%m-%dT%H:%M:%S'),
                        'SalesRepDepartureTime': appointment.departure_date.strftime('%Y-%m-%dT%H:%M:%S'),
                    }
                    headers = {
                        'Content-type': 'application/json',
                    }
                    end_point_url = configurations.token_url
                    client_token = configurations.client_token
                    _logger.info('SalesRepArrivalDeparture API Input Payload of Appointment %s :%s' % (
                        appointment.id, data))
                    if end_point_url and client_token:
                        request_url = end_point_url + 'SalesRepArrivalDeparture' + client_token
                    req = requests.post(request_url, data=json.dumps(data), headers=headers, timeout=TIMEOUT,
                                        verify=configurations.enable_ssl)
                    req.raise_for_status()
                    content = req.json()
                    if isinstance(content, str):
                        content = json.loads(content)
                    _logger.info('SalesRepArrivalDeparture API Response of Appointment %s :%s' % (
                    appointment.id, content))
                    if content.get('Result', '') == "Success":
                        appointment.write({
                            'arrival_departure_synced': True,
                            'write_uid': self.env.user.id,
                            'write_date': datetime.now().replace(tzinfo=pytz.utc)
                        })
                    if content.get('success', '') == "false":
                        return content
                    elif "Errors" in content:
                        return content.get('Errors', {})

        except IOError:
            pass
            _logger.error("******--------Error in update_arrival_departure_time_in_i360 API---------********")
            result.update({"success": "false"})
        return result


class SignRequest(models.Model):
    _inherit = "otl_document_sign.request"

    document_url = fields.Char('Completed Document URL')

    def document_image(self):
        url = ''
        Attachment = self.env['ir.attachment'].sudo().create({
                'res_id': self.id,
                'res_model': self._name,
                'type': 'binary',
                'datas': self.completed_document,
                'name': self.reference,

            })
        Attachment.generate_access_token()
        # url = URL + '/web/image/' + str(Attachment.id) + '?access_token=' + str(Attachment.access_token)
        # self.write({'document_url': url})
        return Attachment

    def action_signed(self):
        res = super(SignRequest, self).action_signed()
        if not self.check_is_encrypted():
            # if the file is encrypted, we must wait that the document is decrypted
            sale_order = self.env['sale.order'].search([('id', '=', self.res_id)])
            if sale_order and self.model_id.model == 'sale.order':
                # sale_order.create_attachment(self.completed_document, self.reference)
                # sale_order.add_quote_sales_app("Accepted")
                # sale_order.add_quote_items_sales_app()
                # sale_order.add_quote_id_file(self.completed_document)
                #---------------------------------------------------
                # i360 sync code is moved to capture_payment function
                # sale_order.add_sale_api()
                # sale_order.add_sale_items_api()
                self.generate_completed_document()
                if self.completed_document:
                    contract_doc_attachment = self.document_image()
                    sale_order.write({'contract_doc_attachment_id': contract_doc_attachment.id, 'document_signed': True})
                    # sale_order.add_sale_id_file(contract_doc_attachment)
                    # sale_order.document_signed = True

        return res



class SaleOrder(models.Model):
    _inherit='sale.order'

    @api.depends('order_line.price_total')
    def _amount_all(self):
        """
        Compute the total amounts of the SO.
        """
        for order in self:
            amount_untaxed = amount_tax = 0.0
            for line in order.order_line:
                amount_untaxed += line.price_subtotal
                amount_tax += line.price_tax
            amount_total_not_rounded = amount_untaxed + amount_tax
            order.update({
                'amount_untaxed': amount_untaxed,
                'amount_tax': amount_tax,
                'amount_total': round(amount_total_not_rounded),
                'amount_total_not_rounded': amount_total_not_rounded,
            })

    def get_date_with_tz(self, date):
        tz = self.env.user.tz or self._context.get('tz') or 'UTC'
        local_tz = pytz.timezone(tz)
        utc_tz = pytz.timezone('UTC')
        datetime_in_utc = utc_tz.localize(date,is_dst=None)
        datetime_with_tz = datetime_in_utc.astimezone(local_tz)
        return datetime_with_tz

    def _compute_current_date(self):
        for record in self:
            current_date = fields.datetime.now()
            local_time = self.get_date_with_tz(current_date)
            print(local_time)
            record.current_date = local_time.date()

    @api.depends('room_measurement_line', 'room_measurement_line.room_id', 'room_measurement_line.molding_type_id',
                 'room_measurement_line.material_id')
    def _compute_room_color_molding(self):
        for record in self:
            room_color_molding1 = ''
            room_color_molding2 = ' '
            room_color_molding3 = ' '
            room_color_molding = ''
            for room in record.room_measurement_line.filtered(lambda x: not x.exclude_from_calculation):
                room_data = ''
                if room.room_id and room.molding_type_id and room.material_id:
                    room_data = '%s:%s:%s'%(room.room_id.name, room.material_id.floor_color or '', room.molding_type_id.name)
                elif room.room_id and room.material_id and not room.molding_type_id:
                    room_data = '%s:%s' % (room.room_id.name, room.material_id.floor_color or '')
                if room_data:
                    if not room_color_molding:
                        room_color_molding = room_data
                    else:
                        room_color_molding += ', ' + room_data
            if room_color_molding:
                if len(room_color_molding) < 55:
                    room_color_molding1 = room_color_molding
                else:
                    room_color_molding1 = room_color_molding[:55]
                    room_color_molding = room_color_molding[55:]
                    if len(room_color_molding) < 118:
                        room_color_molding2 = room_color_molding
                    else:
                        room_color_molding2 = room_color_molding[:118]
                        room_color_molding = room_color_molding[118:]
                        room_color_molding3 = room_color_molding[:118]
            record.room_color_molding1 = room_color_molding1
            record.room_color_molding2 = room_color_molding2
            record.room_color_molding3 = room_color_molding3

    @api.depends('room_measurement_line', 'room_measurement_line.molding_type_id')
    def _compute_molding_type(self):
        for record in self:
            molding_none = False
            molding_vinyl = False
            molding_unfinished = False
            molding_coved_baseboard = False
            if record.room_measurement_line.filtered(lambda x: x.molding_type_id and x.molding_type_id.name.lower() == 'no molding' and not x.exclude_from_calculation):
                molding_none = True
            if record.room_measurement_line.filtered(lambda x: x.molding_type_id and x.molding_type_id.name.lower() == 'vinyl white' and not x.exclude_from_calculation):
                molding_vinyl = True
            if record.room_measurement_line.filtered(lambda x: x.molding_type_id and x.molding_type_id.name.lower() == 'unfinished' and not x.exclude_from_calculation):
                molding_unfinished = True
            if record.room_measurement_line.filtered(lambda x: x.molding_type_id and x.molding_type_id.name.lower() == 'cove baseboard' and not x.exclude_from_calculation):
                molding_coved_baseboard = True
            record.molding_none = molding_none
            record.molding_vinyl = molding_vinyl
            record.molding_unfinished = molding_unfinished
            record.molding_coved_baseboard = molding_coved_baseboard

    @api.depends('card_type', 'cards',  'cash', 'check')
    def _compute_card_type(self):
        for record in self:
            card_visa = False
            card_amex = False
            card_master = False
            if record.cards and record.card_type:
                if record.card_type == 'Visa':
                    card_visa = True
                if record.card_type == 'MasterCard':
                    card_master = True
                if record.card_type == 'AmericanExpress':
                    card_amex = True
            record.card_visa = card_visa
            record.card_amex = card_amex
            record.card_master = card_master

    room_measurement_line = fields.One2many('team.contract.room.measurement.line', 'order_id', string='Room Measurement Line', copy=False)
    contract_question_line = fields.One2many('team.contract.question.line', 'order_id', string='Contract Question Line', copy=False)
    room_transition_line = fields.One2many('team.contract.transition.line', 'order_id', string='Room Transitions', copy=False)
    payment_transaction_line = fields.One2many('team.payment.transaction.line', 'order_id', string='Payment Transactions', copy=False)
    total_area = fields.Float('Total Area in sq.ft',compute='_compute_total_area')
    floor_type = fields.Many2one('product.template',string=' Product Plan')
    link_to_share = fields.Char("Contract Document")
    appointment_id = fields.Many2one('team.customer.appointment', string='Appointment')
    appointment_result = fields.Char('Appointment Result', related='appointment_id.appointment_result', store=True)
    contract_document_uploaded = fields.Boolean('Contract Document Uploaded', default=False)
    other_files_uploaded = fields.Boolean('Other Documents Uploaded', default=False)
    total_amount = fields.Float('Total Amount')
    msrp_amount = fields.Float('MSRP Amount')
    savings_amount = fields.Float('Savings Amount')
    one_year_price = fields.Float('1 Year Price')
    downpayment_percentage = fields.Float('Down Payment Percentage')
    down_payment_amount = fields.Float('Down Payment Amount')
    amount_balance = fields.Float('Amount Balance')
    payment_method = fields.Selection([('credit_card', 'Credit Card'), ('debit_card', 'Debit Card'),('cash', 'Cash'),('check', 'Check')],string="Down Payment Method",)
    balance_payment_option = fields.Selection([('job_completion', 'Job Completion'), ('loan', 'Loan')],string="Balance Amount Payment Option",)
    balance_payment_method = fields.Selection([('credit_card', 'Credit Card'), ('debit_card', 'Debit Card'), ('cash', 'Cash'),('check','Check'), ('finance', 'Finance')],string="Payment Method of Balance",)
    check_number = fields.Char('Check No')
    check_account_number = fields.Char('Check account number')
    check_routing_number = fields.Char('Check routing number')
    discount = fields.Float('discount')
    additional_cost = fields.Float('Additional Cost')
    monthly_promo = fields.Float('Monthly Promo')

    grand_amount_total = fields.Char('Total Amount', compute='_compute_total_amount')
    balance_amount = fields.Char('Balance Amount', compute='_compute_total_balance')
    deposit_amount = fields.Char('Deposit Amount', compute='_compute_deposit')
    cards = fields.Boolean('Card',default=False)
    cash = fields.Boolean('Cash',default=False)
    check = fields.Boolean('Check',default=False)
    balance_finance = fields.Boolean('balance_finance',default=False)
    balance_due_delivery = fields.Boolean('Loan')
    quote_order_date = fields.Date('Quote Order Date', compute='_compute_order_date', store=True)

    adjustment = fields.Float('Adjustment amount')
    final_payment = fields.Float('Final Payment')
    finance_option_id = fields.Many2one('team.downpayment.option',string='Finance Options')
    finance_amount = fields.Float('Finance Amount')
    loan_payment = fields.Float('Loan Payment')
    quote_id = fields.Char('i360 Reference ID')
    excluded_quote_id = fields.Char('Excluded Quote i360 Reference ID')
    document_signed = fields.Boolean(string='Document Signed', default=False)

    photo_permission_yes = fields.Boolean(string='Photo Permission Yes', default=False)
    photo_permission_no = fields.Boolean(string='Photo Permission NO', default=False)

    installation_date = fields.Date('Installation Date')
    owners_right_to_cancel = fields.Date('Owners Right To Cancel')
    requested_installation = fields.Date('Requested Installation')
    applicant_inititals = fields.Char('Initials')
    coapplicant_skip = fields.Boolean(string="Co-Applicant Skip")
    recision_date = fields.Date('Recision Date')
    contract_doc_attachment_id = fields.Many2one('ir.attachment', 'Contract Document Attachment')
    amount_total_not_rounded = fields.Monetary(string='Total(Without Rounding)', store=True, readonly=True, compute='_amount_all', tracking=4)
    amount_untaxed = fields.Monetary(string='Untaxed Amount', store=True, readonly=True, compute='_amount_all',
                                     tracking=5)
    amount_tax = fields.Monetary(string='Taxes', store=True, readonly=True, compute='_amount_all')
    amount_total = fields.Monetary(string='Total', store=True, readonly=True, compute='_amount_all', tracking=4)
    plan_and_color_selected = fields.Char('Plan & Color Selected', compute='_compute_color_selected', store=True)
    current_date = fields.Date('Current Date', compute='_compute_current_date')
    room_color_molding1 = fields.Char('Room:Color:Molding 1', compute='_compute_room_color_molding')
    room_color_molding2 = fields.Char('Room:Color:Molding 2', compute='_compute_room_color_molding')
    room_color_molding3 = fields.Char('Room:Color:Molding 3', compute='_compute_room_color_molding')
    molding_none = fields.Boolean('Molding: None', compute='_compute_molding_type')
    molding_vinyl = fields.Boolean('Mulding: Vinyl', compute='_compute_molding_type')
    molding_unfinished = fields.Boolean('Molding: Unfinished', compute='_compute_molding_type')
    molding_coved_baseboard = fields.Boolean('Molding: Coved Baseboard', compute='_compute_molding_type')
    card_type = fields.Char('Card Type', copy=False)
    card_visa = fields.Boolean('Card: Visa',  compute='_compute_card_type')
    card_amex = fields.Boolean('Card: Amex',  compute='_compute_card_type')
    card_master = fields.Boolean('Card: MasterCard',  compute='_compute_card_type')
    card_transaction_log_line = fields.One2many('otl.card.transaction.log', 'sale_order_id', string='Card Transaction Log Line')
    discount_history_line = fields.One2many('otl.discount.history.line', 'order_id', string='Progressive Discount')
    active = fields.Boolean('Active', default=True, copy=False)
    special_price_id = fields.Many2one('otl.product.special.price', 'Special Price')
    stair_special_price_id = fields.Many2one('otl.product.special.price', 'Stair Special Price')
    promotion_code_id = fields.Many2one('otl.promotion.code', 'Promotion Code')
    calc_based_on = fields.Selection([('list_price', 'Sale Price'), ('msrp', 'MSRP')], string='Calculation Based On',
                                     default='list_price')
    stair_calc_based_on = fields.Selection([('list_price', 'Sale Price'), ('msrp', 'MSRP')], string='Stair Calculation Based On',
                                     default='list_price')
    excluded_amount_promotion = fields.Float('Excluded Amount From Promotion')
    final_sale_price = fields.Float('Finalized Sale Price')
    min_sale_price = fields.Float('Minimum Sale Price', default=0)
    available_installation_line = fields.One2many('otl.available.installation.line', 'order_id', string='Available Installtion Dates')
    additional_comment_synced = fields.Boolean("Synced Additional Comments", default=False)
    email_sent = fields.Boolean('Email Sent', default=False)
    synced_to_cloud_storage = fields.Boolean('Synced Files to Cloud Storage', default=False)


    def write(self, vals):
        _logger.info('inside sale order-%s write: values -  %s'%(self and self[0].name or '', vals))
        return super(SaleOrder, self).write(vals)

    def _send_order_confirmation_mail(self):
        """
        Function overrided to prevent sending of emails
        :return:
        """
        return True

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

    @api.depends('floor_type', 'room_measurement_line', 'room_measurement_line.material_id')
    def _compute_color_selected(self):
        for record in self:
            plan_and_color_selected = 'As specified in this packet'
            # plan_selected = ''
            # if record.floor_type:
            #     plan_selected = record.floor_type.name
            # material_ids = []
            # for room in record.room_measurement_line.filtered(lambda x: not x.exclude_from_calculation):
            #     if room.material_id and room.material_id not in material_ids:
            #         material_ids.append(room.material_id)
            # material_name = ''
            # for material in material_ids:
            #     attribute_line = material.product_template_attribute_value_ids.filtered(lambda x: x.attribute_id.name.upper() == 'COLOUR')
            #     if attribute_line:
            #         if not material_name:
            #             material_name = attribute_line.name
            #         else:
            #             material_name += ', ' + attribute_line.name
            # if material_name and plan_selected:
            #     plan_and_color_selected = '%s(%s)'%(plan_selected, material_name)
            record.plan_and_color_selected = plan_and_color_selected


    @api.depends('date_order')
    def _compute_order_date(self):
        for record in self:
            current_date = False
            record.quote_order_date = False
            if record.date_order:
                current_date = record.date_order
            if current_date:
                local_time = self.get_date_with_tz(current_date)
                print(local_time)
                record.quote_order_date = local_time.date()

    # @api.depends('balance_payment_option')
    # def _compute_balance_payment(self):
    #     for record in self:
    #         record.balance_finance=False
    #         record. balance_due_delivery=False
    #         if record.balance_payment_option=='job_completion':
    #             record.balance_finance=True
    #         if record.balance_payment_option=='loan':
    #             record.balance_due_delivery=True

    @api.depends('payment_method')
    def _compute_payment_method(self):
        for record in self:
            record.cards = False
            record.cash = False
            record.check = False
            if record.payment_method in ['credit_card','debit_card']:
                record.cards=True
            if record.payment_method=='cash':
                record.cash=True
            if record.payment_method=='check':
                record.check=True

    @api.depends('amount_total')
    def _compute_total_amount(self):
        for record in self:
            grand_amount_total = '0.00'
            # if record.currency_id:
            #     grand_amount_total=record.currency_id.symbol+' '+'0'
            #     if record.amount_total:
            #         grand_amount_total=record.currency_id.symbol+' '+'{:,.2f}'.format(record.amount_total)
            grand_amount_total = '{:,.2f}'.format(record.amount_total)
            record.grand_amount_total = grand_amount_total

    @api.depends('amount_total','down_payment_amount')
    def _compute_total_balance(self):
        for record in self:
            balance_amount = ''
            if record.currency_id:
                balance_amount='0.00'
                down_payment_amount = 0
                if  record.down_payment_amount:
                    down_payment_amount = record.down_payment_amount
                if record.amount_total:
                    balance = record.amount_total - down_payment_amount
                    # balance_amount=record.currency_id.symbol+' '+'{:,.2f}'.format(balance)
                    balance_amount='{:,.2f}'.format(balance)
            record.balance_amount = balance_amount

    @api.depends('down_payment_amount')
    def _compute_deposit(self):
        for record in self:
            deposit_amount = ''
            if record.currency_id:
                deposit_amount='0.00'
                if record.down_payment_amount:
                    # deposit_amount=record.currency_id.symbol+' '+'{:,.2f}'.format(record.down_payment_amount)
                    deposit_amount='{:,.2f}'.format(record.down_payment_amount)
            record.deposit_amount = deposit_amount

    @api.depends('room_measurement_line')
    def _compute_total_area(self):
        for record in self:
            total_area=0
            for line in record.room_measurement_line:
                if not line.exclude_from_calculation:
                    total_area = total_area + line.adjusted_area
            record.total_area=total_area

    def document_image(self, name, model_name, image, res_id):
        url = ''

        Attachment = self.env['ir.attachment'].sudo().create({
                'res_id': res_id,
                'res_model': model_name,
                'type': 'binary',
                'datas': image,
                'name': name

            })
        Attachment.generate_access_token()
        url = URL + '/web/image/' + str(Attachment.id) + '?access_token=' + str(Attachment.access_token)
        return url

    def generate_link(self):
        sign_req_obj = self.env['otl_document_sign.request']
        sign_req_item_obj = self.env['otl_document_sign.request.item']
        for order in self:
            if order.appointment_id.app_version_id:
                if order.coapplicant_skip:
                    document_template_id = order.appointment_id.app_version_id.sale_contract_tmpl_id_ncp.id or False
                else:
                    document_template_id = order.appointment_id.app_version_id.sale_contract_tmpl_id.id or False
            else:
                if order.coapplicant_skip or not order.appointment_id.co_applicant:
                    document_template_id = self.env['ir.config_parameter'].sudo().get_param('sale_contract_tmpl_id_ncp') or False
                else:
                    document_template_id = self.env['ir.config_parameter'].sudo().get_param('sale_contract_tmpl_id') or False
            if document_template_id:
                template = self.env['otl_document_sign.template'].sudo().browse(int(document_template_id))
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
                        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
                        share_url = '%(base_url)s/sign/document/%(request_id)s/%(access_token)s' % {
                            'base_url': base_url, 'request_id': sign_request.id,
                            'access_token': request_item.access_token}
                        if share_url:
                            order.link_to_share = share_url
            else:
                raise UserError("Please update contract template in the settings before proceeding.")
        return True

    # def generate_link_test(self):
    #     sign_req_obj = self.env['otl_document_sign.request']
    #     sign_req_item_obj = self.env['otl_document_sign.request.item']
    #     for order in self:
    #         document_template_id = self.env['ir.config_parameter'].sudo().get_param('sale_contract_tmpl_id') or False
    #         if document_template_id:
    #             template = self.env['otl_document_sign.template'].sudo().browse(int(document_template_id))
    #             vals = {
    #                 'template_id': template.id,
    #                 'reference': template.name,
    #                 'model_id': template.model_id.id,
    #                 'res_id': order.id,
    #             }
    #             sign_request = sign_req_obj.create(vals)
    #             if sign_request:
    #                 item_vals = {
    #                     'partner_id': order.partner_id.id,
    #                     'sign_request_id': sign_request.id,
    #                     'role_id': template.sign_item_ids and template.sign_item_ids.mapped('responsible_id').id,
    #                 }
    #                 request_item = sign_req_item_obj.create(item_vals)
    #                 if request_item:
    #                     sign_request.action_sent()
    #                     base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
    #                     share_url = '%(base_url)s/sign/document/%(request_id)s/%(access_token)s' % {
    #                         'base_url': base_url, 'request_id': sign_request.id,
    #                         'access_token': request_item.access_token}
    #                     current_request_item = sign_request.request_item_ids
    #                     sign_item_types = self.env['otl_document_sign.item.type'].sudo().search_read([])
    #                     if current_request_item:
    #                         for item_type in sign_item_types:
    #                             if item_type['auto_field']:
    #                                 fields = item_type['auto_field'].split('.')
    #                                 selected_record = self.env[
    #                                     current_request_item.model_id.model].sudo().search(
    #                                     [('id', '=', current_request_item.res_id)], limit=1)
    #                                 auto_field = selected_record if selected_record else current_request_item.partner_id
    #                                 for field in fields:
    #                                     if auto_field and field in auto_field:
    #                                         if 'partner_id' and 'name' in field:
    #                                             partner_name = auto_field[field]
    #                                             auto_field = partner_name.replace(",", "")
    #                                         else:
    #                                             auto_field = auto_field[field]
    #                                     else:
    #                                         auto_field = ""
    #                                         break
    #                                 if auto_field == 0.0:
    #                                     if isinstance(auto_field, bool):
    #                                         auto_field = ''
    #                                     else:
    #                                         auto_field = '0.0'
    #                                 if isinstance(auto_field, date):
    #                                     lg = self.env['res.lang']._lang_get(self.env.user.lang)
    #                                     auto_field = auto_field.strftime(lg.date_format) or auto_field
    #                                 SignItemValue = self.env['otl_document_sign.request.item.value']
    #                                 sign_item_ids = sign_request.template_id.sign_item_ids.filtered(lambda r: not r.responsible_id or r.responsible_id.id == request_item.role_id.id)
    #                                 id_sign_item = False
    #                                 for sign_item_id in sign_item_ids:
    #                                     if sign_item_id.type_id.id == int(item_type['id']):
    #                                         id_sign_item = sign_item_id.id
    #                                 if id_sign_item:
    #                                     item_value = SignItemValue.create(
    #                                         {'sign_item_id': id_sign_item, 'sign_request_id': sign_request.id,
    #                                          'value': auto_field, 'sign_request_item_id': request_item.id})
    #                     sr_values = self.env['otl_document_sign.request.item.value'].sudo().search(
    #                         [('sign_request_id', '=', sign_request.id)])
    #                     item_values = {}
    #                     for value in sr_values:
    #                         item_values[value.sign_item_id.id] = value.value
    #                     request_item.sign(request_item.signature)
    #                     request_item.action_completed()
    #                     sign_request.action_signed()
    #                     sign_request.generate_completed_document()
    #                     if share_url:
    #                         if sign_request.completed_document:
    #                             document_url = self.document_image(sign_request.reference, 'otl_document_sign.request',sign_request.completed_document, sign_request.id)
    #                             order.link_to_share = document_url
    #         else:
    #             raise UserError("Please update contract template in the settings before proceeding.")
    #     return True

    def _create_payment_transaction_with_data(self, vals, data):
        '''Similar to self.env['payment.transaction'].create(vals) but the values are filled with the
        current sales orders fields (e.g. the partner or the currency).
        :param vals: The values to create a new payment.transaction.
        :return: The newly created payment.transaction record.
        '''
        # Ensure the currencies are the same.
        currency = self[0].pricelist_id.currency_id
        if any([so.pricelist_id.currency_id != currency for so in self]):
            raise ValidationError(_('A transaction can\'t be linked to sales orders having different currencies.'))

        # Ensure the partner are the same.
        partner = self[0].partner_id
        if any([so.partner_id != partner for so in self]):
            raise ValidationError(_('A transaction can\'t be linked to sales orders having different partners.'))

        # Try to retrieve the acquirer. However, fallback to the token's acquirer.
        acquirer_id = vals.get('acquirer_id')
        acquirer = False
        payment_token_id = vals.get('payment_token_id')

        if payment_token_id:
            payment_token = self.env['payment.token'].sudo().browse(payment_token_id)

            # Check payment_token/acquirer matching or take the acquirer from token
            if acquirer_id:
                acquirer = self.env['payment.acquirer'].browse(acquirer_id)
                if payment_token and payment_token.acquirer_id != acquirer:
                    raise ValidationError(_('Invalid token found! Token acquirer %s != %s') % (
                    payment_token.acquirer_id.name, acquirer.name))
                if payment_token and payment_token.partner_id != partner:
                    raise ValidationError(_('Invalid token found! Token partner %s != %s') % (
                    payment_token.partner.name, partner.name))
            else:
                acquirer = payment_token.acquirer_id

        # Check an acquirer is there.
        if not acquirer_id and not acquirer:
            raise ValidationError(_('A payment acquirer is required to create a transaction.'))

        if not acquirer:
            acquirer = self.env['payment.acquirer'].browse(acquirer_id)

        # Check a journal is set on acquirer.
        if not acquirer.journal_id:
            raise ValidationError(_('A journal must be specified of the acquirer %s.' % acquirer.name))

        if not acquirer_id and acquirer:
            vals['acquirer_id'] = acquirer.id

        amount=data.get('amount', 0)

        vals.update({
            'amount': amount if amount else sum(self.mapped('amount_total')),
            'currency_id': currency.id,
            'partner_id': partner.id,
            'sale_order_ids': [(6, 0, self.ids)],
        })
        transaction = self.env['payment.transaction'].create(vals)

        # Process directly if payment_token
        if transaction.payment_token_id:
            transaction.s2s_do_transaction(**data)

        return transaction

    def add_payment_line(self, discount, adjustment, additional_cost, monthly_promo, admin_fee, final_sale_price=0):
        min_sale_price = float(self.env['ir.config_parameter'].sudo().get_param('min_sale_price')) or 0.0
        obj = self.env['sale.order.line']
        for record in self:
            if record.state == 'draft':
                if not record.floor_type:
                    raise ValidationError(_('Floor Type Not Selected.'))
                for order_line in record.order_line:
                    order_line.sudo().unlink()
                product = self.env.ref('team_sale_contract.product_payment')
                additional_product = self.env.ref('team_sale_contract.additional_cost')
                adjustment_product = self.env.ref('team_sale_contract.adjustment_cost')
                promotion_discount_product = self.env.ref('team_sale_contract.quote_promotion_discount')
                promo_product = self.env.ref('team_sale_contract.monthly_promo')
                admin_fee_product = self.env.ref('team_sale_contract.admin_fee')
                quote_round_off_product = self.env.ref('team_sale_contract.quote_round_off')
                stair_count = 0
                stair_product = False
                if record.min_sale_price:
                    min_sale_price = record.min_sale_price

                stair_count_lines = record.contract_question_line.filtered(
                    lambda x: x.question_id.code == 'StairCount' and not x.room_measurement_id.exclude_from_calculation)
                if stair_count_lines:
                    for stair_count_line in stair_count_lines:
                        for answer_line in stair_count_line.answers:
                            if answer_line.answer:
                                stair_count += float(answer_line.answer)
                if stair_count:
                    stair_product = self.env['product.template'].search([
                        ('type', '=', 'product'),
                        ('product_variant_ids', '!=', False),
                        ('categ_id.name', 'ilike', 'Stairs'),
                        ('grade', '=', record.floor_type.grade)
                    ], order='sequence asc', limit=1)
                stair_price = 0
                stair_unit_price = 0
                if stair_count and stair_product:
                    if record.stair_calc_based_on == 'list_price':
                        stair_unit_price = stair_product.list_price or 0
                        if record.stair_special_price_id and record.stair_special_price_id.list_price:
                            stair_unit_price = record.stair_special_price_id.list_price or 0
                    else:
                        stair_unit_price = stair_product.msrp or 0
                        if record.stair_special_price_id and record.stair_special_price_id.msrp:
                            stair_unit_price = record.stair_special_price_id.msrp or 0
                    stair_price = stair_unit_price * stair_count
                measurement_price = 0
                promotion_amount = 0
                if record.calc_based_on == 'list_price':
                    list_price = record.floor_type.list_price or 0
                    if record.special_price_id and record.special_price_id.list_price:
                        list_price = record.special_price_id.list_price or 0
                else:
                    list_price = record.floor_type.msrp or 0
                    if record.special_price_id and record.special_price_id.msrp:
                        list_price = record.special_price_id.msrp or 0
                    if record.promotion_code_id and record.promotion_code_id.discount:
                        if record.promotion_code_id.calculation_type == 'sqft':
                            promo_discount = record.promotion_code_id.discount or 0
                            promotion_amount = record.total_area * promo_discount
                        elif record.promotion_code_id.calculation_type == 'percentage':
                            promotion_amount = (record.total_area * list_price + additional_cost + stair_price - record.excluded_amount_promotion)*record.promotion_code_id.discount/100.0
                        else:
                            promotion_amount = record.promotion_code_id.discount or 0
                measurement_price = record.total_area * list_price
                net_amount = measurement_price + additional_cost + stair_price - adjustment - monthly_promo - promotion_amount
                if final_sale_price:
                    round_off_amount = final_sale_price - net_amount
                else:
                    round_off_mismatched_amount = round(measurement_price+additional_cost+stair_price+promotion_amount) - (measurement_price+additional_cost+stair_price+promotion_amount)
                    # round_off_mismatched_amount += round(adjustment) - adjustment
                    round_off_mismatched_amount += round(monthly_promo) - monthly_promo
                    if min_sale_price and net_amount < min_sale_price:
                        round_off_amount = min_sale_price - net_amount + round_off_mismatched_amount
                    else:
                        round_off_amount = round_off_mismatched_amount
                if round_off_amount and quote_round_off_product:
                    vals = {
                        'product_id': quote_round_off_product.id,
                        'product_uom_qty': 1,
                        'name': quote_round_off_product.name,
                        'order_id': record.id,
                        'price_unit': float(round_off_amount),
                        'discount': 0
                    }
                    obj.create(vals)
                if admin_fee_product and admin_fee!= 0.0:
                    vals = {
                        'product_id': admin_fee_product.id,
                        'product_uom_qty': 1,
                        'name': admin_fee_product.name,
                        'order_id': record.id,
                        'price_unit': - float(admin_fee),
                        'discount': 0
                    }
                    obj.create(vals)
                if adjustment_product and adjustment != 0.0:
                    vals = {
                        'product_id': adjustment_product.id,
                        'product_uom_qty': 1,
                        'name': adjustment_product.name,
                        'order_id': record.id,
                        'price_unit': -adjustment,
                        'discount':  0
                    }
                    obj.create(vals)
                if promotion_discount_product and promotion_amount != 0.0:
                    vals = {
                        'product_id': promotion_discount_product.id,
                        'product_uom_qty': 1,
                        'name': promotion_discount_product.name,
                        'order_id': record.id,
                        'price_unit': -(promotion_amount),
                        'discount':  0
                    }
                    obj.create(vals)
                if promo_product and monthly_promo != 0:
                    vals = {
                        'product_id': promo_product.id,
                        'product_uom_qty': 1,
                        'name': promo_product.name,
                        'order_id': record.id,
                        'price_unit': -monthly_promo,
                        'discount': 0
                    }
                    obj.create(vals)
                if additional_product and additional_cost != 0:
                    vals = {
                        'product_id': additional_product.id,
                        'product_uom_qty': 1,
                        'name': additional_product.name,
                        'order_id': record.id,
                        'price_unit': additional_cost,
                        'discount': 0
                    }
                    obj.create(vals)

                if product:
                    if record.total_area:
                        vals = {
                            'product_id': product.id,
                            'product_uom_qty': record.total_area,
                            'name': product.name,
                            'order_id': record.id,
                            'price_unit': list_price,
                            'discount': discount or 0
                        }
                        obj.create(vals)
                    if stair_count and stair_product:
                            vals = {
                                'product_id': product.id,
                                'product_uom_qty': stair_count,
                                'name': product.name,
                                'order_id': record.id,
                                'price_unit': stair_unit_price,
                            }
                            obj.create(vals)
        return True

    def create_attachment(self, document, reference):
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
                request_url = instance_url + "/services/data/v45.0/sobjects/Attachment"
                try:
                    for sale_order in self:
                        if sale_order.appointment_id.improveit_appointment_id:
                            _logger.info('started - appointment_id %s ' % sale_order.appointment_id.improveit_appointment_id )
                            improveit_appointment_id = record.test_appointment_id or sale_order.appointment_id.improveit_appointment_id or ''
                            if document and reference:
                                _logger.info('Started Attaching Document %s ' % reference)
                                decoded_image = base64.decodestring(document)
                                data = {
                                    "Name": reference,
                                    "Body": base64.b64encode(decoded_image).decode('utf-8'),
                                    "parentId": improveit_appointment_id

                                }
                                headers = {
                                    'Content-type': 'application/json',
                                    'Authorization': 'Bearer %s' % access_token
                                }
                                req = requests.post(request_url, data=json.dumps(data), headers=headers,
                                                    timeout=TIMEOUT)
                                req.raise_for_status()
                                content = req.json()
                                _logger.info('Attaching Document Finished %s ' % content)
                            for room_lines in sale_order.room_measurement_line:
                                _logger.info('Attaching Room line  Data %s' % room_lines.name)
                                if room_lines.shape_image_id.datas:
                                    _logger.info('Started Attaching Room Shape Drawing')
                                    decoded_image = base64.decodestring(room_lines.shape_image_id.datas)
                                    data = {

                                        "Name": room_lines.shape_image_id.name,
                                        "Body": base64.b64encode(decoded_image).decode('utf-8'),
                                        "parentId": improveit_appointment_id

                                                }
                                    headers = {
                                        'Content-type': 'application/json',
                                        'Authorization': 'Bearer %s' % access_token
                                                }
                                    req = requests.post(request_url, data=json.dumps(data), headers=headers,timeout=TIMEOUT)
                                    req.raise_for_status()
                                    content = req.json()
                                    _logger.info('Attaching Room Shape Drawing Finished %s ' % content)
                                if room_lines.attachment_ids:
                                    for attachemnt in room_lines.attachment_ids:
                                        _logger.info('Attaching Room Images')
                                        decoded_image = base64.decodestring(attachemnt.datas)
                                        data = {

                                            "Name": attachemnt.name,
                                            "Body": base64.b64encode(decoded_image).decode('utf-8'),
                                            "parentId": improveit_appointment_id

                                        }

                                        headers = {
                                        'Content-type': 'application/json',
                                        'Authorization': 'Bearer %s' % access_token
                                                    }
                                        req = requests.post(request_url, data=json.dumps(data), headers=headers,timeout=TIMEOUT)
                                        req.raise_for_status()
                                        content = req.json()
                                        _logger.info('Attached Image %s ' % content)
                                _logger.info(' Attaching Room line Data Finished %s' % room_lines.name)
                except requests.HTTPError:
                    raise UserError(_("Something went wrong while Creating Attachments."))
            except IOError:
                error_msg = _(
                    "Something went wrong during token generation.")
                raise self.env['res.config.settings'].get_config_warning(error_msg)

    # def add_quote(self,status):
    #     try:
    #         configurations = self.env['team.improveit.configuration'].search([('api_type', '=', 'zapier'), ('section', '=', 'quote')])
    #         for sale_order in self:
    #             if sale_order.appointment_id.improveit_appointment_id:
    #                 customer_name = sale_order.appointment_id.customer_name
    #                 lastname = customer_name.split()[1]
    #                 first_name = customer_name.split()[0]
    #                 date_quote_format=sale_order.create_date.strftime('%m%d%H%M%S')
    #                 date_validation= sale_order.create_date + relativedelta(days=90)
    #                 validation_date = datetime.strptime(str(date_validation), "%Y-%m-%d %H:%M:%S.%f").date()
    #                 quote_name = lastname + " ," + first_name + "-" + date_quote_format
    #                 sale_tax_rate = self.env.company.account_sale_tax_id.amount or 0
    #                 improveit_appointment_id = configurations.test_appointment_id or sale_order.appointment_id.improveit_appointment_id or ''
    #                 data = {
    #                     "AppointmentID": improveit_appointment_id,
    #
    #                     "QuoteName": quote_name,
    #
    #                     "Status": status,
    #
    #                     "Description": sale_order.note or "",
    #
    #                     "ValidUntilDate": str(validation_date),
    #
    #                     "SalesTaxRate": sale_tax_rate
    #
    #                 }
    #                 headers = {
    #                     'Content-type': 'application/json',
    #
    #                 }
    #                 request_url = configurations.token_url
    #                 req = requests.post(request_url, data=json.dumps(data), headers=headers,
    #                                     timeout=TIMEOUT)
    #                 req.raise_for_status()
    #                 content = req.json()
    #                 sale_order.quote_id = content['id'] or ''
    #     except IOError:
    #         error_msg = _(
    #             "Something went wrong during adding quote")
    #         raise self.env['res.config.settings'].get_config_warning(error_msg)

    def add_quote_sales_app(self, status):
        result = {
            "success": "true",
            "errors": []
        }
        try:
            configurations = self.env['team.improveit.configuration'].search([('api_type', '=', 'boomi')],limit=1)
            if configurations:
                for sale_order in self:
                    if sale_order.appointment_id.improveit_appointment_id:
                        customer_name = sale_order.appointment_id.customer_name
                        lastname = customer_name.split()[1]
                        first_name = customer_name.split()[0]
                        date_quote_format=sale_order.create_date.strftime('%m%d%H%M%S')
                        date_validation= sale_order.create_date + relativedelta(days=90)
                        validation_date = datetime.strptime(str(date_validation), "%Y-%m-%d %H:%M:%S.%f").date()
                        # quote_name = lastname.strip(',') + " ," + first_name.strip(',') + "-" + date_quote_format
                        quote_name = lastname.strip(',') + " ," + first_name.strip(',')
                        sale_tax_rate = self.env.company.account_sale_tax_id.amount or 0
                        improveit_appointment_id = configurations.test_appointment_id or sale_order.appointment_id.improveit_appointment_id or ''
                        included_room_measurement_lines = sale_order.room_measurement_line.filtered(
                            lambda x: not x.exclude_from_calculation)
                        excluded_room_measurement_lines = sale_order.room_measurement_line.filtered(
                            lambda x: x.exclude_from_calculation)
                        if included_room_measurement_lines and not sale_order.quote_id:
                            data = {
                                "AppointmentID": improveit_appointment_id,
                                "QuoteName": quote_name,
                                "Status": status,
                                "Description": sale_order.note or "",
                                "ValidUntilDate": str(validation_date),
                                "SalesTaxRate": sale_tax_rate,
                                "AdditionalComments": sale_order.appointment_id.additional_comments or "",
                                "Excluded": False,

                            }
                            headers = {
                                'Content-type': 'application/json',

                            }
                            end_point_url = configurations.token_url
                            client_token = configurations.client_token
                            _logger.info('Add Quote API Input Payload of sale %s: %s' %(sale_order.id, data))
                            if end_point_url and client_token:
                                request_url = end_point_url + 'AddQuote' + client_token
                            req = requests.post(request_url, data=json.dumps(data), headers=headers,
                                                timeout=TIMEOUT, verify=configurations.enable_ssl)
                            req.raise_for_status()
                            try:
                                content = req.json()
                            except IOError:
                                if req.status_code == 200:
                                    return {
                                        'success': 'false',
                                        'errors': [
                                            {
                                                'message': "Sale data successfully send to the system, but response is in wrong format."
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
                            _logger.info('Add Quote API Response of sale %s: %s' %(sale_order.id, content))
                            if content['success'] == "true":
                                sale_order.write({
                                    'quote_id': content['id'] or '',
                                })
                                if content.get('duplicate', '') == "true":
                                    result.update({
                                        "duplicate": "true"
                                    })
                                # if sale_order.appointment_id:
                                #     sale_order.appointment_id.write({
                                #         'state': 'done'
                                #     })
                            if content.get('success', '') == "false":
                                return content
                            elif "Errors" in content:
                                return content.get('Errors', {})
                        if excluded_room_measurement_lines and not sale_order.excluded_quote_id:
                            data = {
                                "AppointmentID": improveit_appointment_id,
                                "QuoteName": quote_name,
                                "Status": status,
                                "Description": sale_order.note or "",
                                "ValidUntilDate": str(validation_date),
                                "SalesTaxRate": sale_tax_rate,
                                "AdditionalComments": sale_order.appointment_id.additional_comments or "",
                                "Excluded": True,

                            }
                            headers = {
                                'Content-type': 'application/json',

                            }
                            end_point_url = configurations.token_url
                            client_token = configurations.client_token
                            _logger.info('Excluded Add Quote API Payload of sale %s: %s'%(sale_order.id, json.dumps(data)))
                            if end_point_url and client_token:
                                request_url = end_point_url + 'AddQuote' + client_token
                            req = requests.post(request_url, data=json.dumps(data), headers=headers,
                                                timeout=TIMEOUT, verify=configurations.enable_ssl)
                            req.raise_for_status()
                            try:
                                content = req.json()
                            except IOError:
                                if req.status_code == 200:
                                    return {
                                        'success': 'false',
                                        'errors': [
                                            {
                                                'message': "Sale data successfully send to the system, but response is in wrong format."
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
                            _logger.info('Excluded Add Quote API Response of sale %s: %s' % (sale_order.id, content))
                            if content['success'] == "true":
                                sale_order.write({
                                    'excluded_quote_id': content['id'] or '',
                                })
                                if content.get('duplicate', '') == "true":
                                    result.update({
                                        "duplicate": "true"
                                    })
                                # if sale_order.appointment_id:
                                #     sale_order.appointment_id.write({
                                #         'state': 'done'
                                #     })
                            if content.get('success', '') == "false":
                                return content
                            elif "Errors" in content:
                                return content.get('Errors', {})
        except IOError:
            pass
            _logger.error('**********Error in add_quote_sales_app***************')
            # error_msg = _(
            #     "Something went wrong during adding quote")
            # raise self.env['res.config.settings'].get_config_warning(error_msg)
            result.update({"success": "false"})
        return result

    def add_sale_api(self):
        result = {
            "success": "true",
            "errors": []
        }
        try:
            configurations = self.env['team.improveit.configuration'].search([('api_type', '=', 'boomi')],limit=1)
            for sale_order in self:
                if sale_order.appointment_id.improveit_appointment_id and not sale_order.quote_id:
                    customer_name = sale_order.appointment_id.customer_name
                    sale_tax_rate = self.env.company.account_sale_tax_id.amount or 0
                    improveit_appointment_id = configurations.test_appointment_id or sale_order.appointment_id.improveit_appointment_id or ''

                    payment_method = ''
                    if sale_order.payment_method:
                        if sale_order.payment_method == 'cash':
                            payment_method = 'Cash'
                        elif sale_order.payment_method == 'check':
                            payment_method = 'Check'
                        else:
                            payment_method = 'Credit Card'
                    balance_payment_method = 'Financing'
                    if sale_order.finance_option_id and sale_order.finance_option_id.name == 'Cash':
                        balance_payment_method = 'Cash'
                    down_payment_amount = 0
                    if payment_method == 'Credit Card':
                        if sale_order.card_transaction_log_line.filtered(lambda x: x.state == 'success'):
                            down_payment_amount = sale_order.down_payment_amount or 0
                    data = {
                        "AppointmentID": improveit_appointment_id,
                        "Name": customer_name,
                        "SoldPrice": sale_order.amount_total,
                        "PaymentType": balance_payment_method or "",
                        "DepositAmount": down_payment_amount,
                        "DepositPaymentType": payment_method or "",
                         "SalesRepID": sale_order.appointment_id.user_id.improveit_user_id or "",
                        "SalesTaxRate": sale_tax_rate,
                        "AuthorizationCode": sale_order.authorize_transaction_id or "",
                        "AdditionalComments": sale_order.appointment_id.additional_comments or "",
                        "SendPhysicalDocument": sale_order.appointment_id.send_physical_document and "true" or "false",
                        "FlexibleInstall": sale_order.appointment_id.flexible_installation and "true" or "false",
                        "FinanceOptionSelected": sale_order.finance_option_id and sale_order.finance_option_id.name or ""
                    }
                    headers = {
                        'Content-type': 'application/json',

                    }
                    end_point_url = configurations.token_url
                    client_token = configurations.client_token
                    _logger.info('Add Sale API Input data of sale %s: %s' % (sale_order.id, json.dumps(data)))
                    if end_point_url and client_token:
                        request_url = end_point_url + 'AddSale' + client_token
                    req = requests.post(request_url, data=json.dumps(data), headers=headers,
                                        timeout=TIMEOUT, verify=configurations.enable_ssl)
                    _logger.info('Add Sale API Response of sale %s: %s' %(sale_order.id, str(req.content)))
                    req.raise_for_status()
                    try:
                        content = req.json()
                    except IOError:
                        if req.status_code == 200:
                            return {
                                'success': 'false',
                                'errors': [
                                    {
                                        'message': "Sale data successfully send to the system, but response is in wrong format."
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
                    _logger.info('Add Sale API Response Json of sale %s: %s'%(sale_order.id, content))
                    if content.get('success', '') == "true":
                        sale_order.write({
                            'quote_id': content['id'] or '',
                        })
                        if content.get('duplicate', '') == "true":
                            result.update({
                                "duplicate": "true"
                            })
                        # if sale_order.appointment_id:
                        #     sale_order.appointment_id.write({
                        #         'state': 'done'
                        #     })
                    if content.get('success', '') == "false":
                        return content
                    elif "Errors" in content:
                        return content.get('Errors', {})
        except IOError:
            pass
            _logger.error("******--------Error in add_sale_api---------********")
            # error_msg = _(
            #     "Something went wrong during adding quote in AddSale")
            # raise self.env['res.config.settings'].get_config_warning(error_msg)
            result.update({"success": "false"})
        return result

    def add_card_decline_note_api(self):
        result = {
            "success": "true",
            "errors": []
        }
        configurations = self.env['team.improveit.configuration'].search([('api_type', '=', 'boomi')],limit=1)
        for sale_order in self:
            appointment = sale_order.appointment_id
            transaction_logs = appointment.card_transaction_log_line.filtered(lambda x: x.state == 'failed' and not x.synced)
            if transaction_logs and (sale_order.quote_id or sale_order.excluded_quote_id):
                headers = {
                    'Content-type': 'application/json',

                }
                quote_id = sale_order.quote_id
                if not quote_id:
                    quote_id = sale_order.excluded_quote_id
                end_point_url = configurations.token_url
                client_token = configurations.client_token
                if end_point_url and client_token:
                    request_url = end_point_url + 'CreateChargeDeclineNotice' + client_token
                    for log in transaction_logs:
                        data = {
                            "SaleId": quote_id,
                            "TransactionTimeStamp": log.date.strftime('%Y-%m-%dT%H:%M:%S.0000000Z'),
                            "ErrorCode": log.error_code or '',
                            "ErrorDescription": log.message or '',
                        }
                        _logger.info('CreateChargeDeclineNotice API Input Payload of sale %s: %s' % (sale_order.id, json.dumps(data)))
                        req = requests.post(request_url, data=json.dumps(data), headers=headers,
                                            timeout=TIMEOUT, verify=configurations.enable_ssl)
                        _logger.info('CreateChargeDeclineNotice API Response of sale %s: %s' %(sale_order.id, str(req.content)))
                        req.raise_for_status()
                        try:
                            content = req.json()
                        except IOError:
                            if req.status_code == 200:
                                return {
                                    'success': 'false',
                                    'errors': [
                                        {
                                            'message': "Sale data successfully send to the system, but response is in wrong format."
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
                        if content.get('success', '') == "true" or content.get('success', '') == True:
                            log.write({'synced': True})
                        if content.get('success', '') == "false" or content.get('success', '') == False:
                            return content
        return result



    # def add_quote_items(self):
    #     try:
    #         configurations = self.env['team.improveit.configuration'].search([('api_type', '=', 'zapier'), ('section', '=', 'quote_item')], limit=1)
    #         for sale_order in self:
    #             if sale_order.appointment_id:
    #                 customer_name = sale_order.appointment_id.customer_name
    #                 lastname = customer_name.split()[1]
    #                 first_name = customer_name.split()[0]
    #                 date_quote_format = sale_order.create_date.strftime('%m%d%H%M%S')
    #                 quote_name = lastname + " ," + first_name + "-" + date_quote_format
    #                 product_name = sale_order.floor_type.name
    #                 improveit_product_id =sale_order.floor_type.improveit_product_id or False
    #                 for room_line in sale_order.room_measurement_line:
    #                     data = {}
    #                     reflect_cost = 0
    #                     data = {
    #
    #                         "QuoteName": quote_name,
    #                         "ProductName": product_name,
    #                         "ProductID": improveit_product_id
    #                     }
    #
    #                     for questions in sale_order.contract_question_line:
    #                         if questions.question_id.reflect_cost and  questions.room_id.id == room_line.room_id.id:
    #                             if questions.question_id.calculation_type == 'fixed':
    #                                 reflect_cost=questions.question_id.amount
    #                             if questions.question_id.calculation_type == 'unit':
    #                                 quantity = 0
    #                                 for answer in questions.answers:
    #                                     quantity = quantity+int(answer.answer)
    #                                 reflect_cost = questions.question_id.amount * quantity
    #                     room_cost=room_line.adjusted_area * sale_order.floor_type.flooring_cost
    #                     unit_price=room_cost+reflect_cost
    #                     discount=sale_order.discount or 0
    #                     discounted_unit_price=unit_price-(unit_price*(discount/100))
    #                     data.update({'Description': room_line.room_id.name})
    #                     data.update({'Taxable':True})
    #                     data.update({'Units': "Room"})
    #                     data.update({'Quantity':1})
    #                     data.update({'UnitOfMeasure':"sqft"})
    #                     data.update({'UnitPrice':discounted_unit_price})
    #                     data.update({'Room Name': room_line.room_id.name})
    #                     data.update({'Room Area SqFt': room_line.adjusted_area})
    #                     attribute_value_ids = room_line.material_id.product_template_attribute_value_ids
    #                     material_colour = False
    #                     for attribute in attribute_value_ids:
    #                         if attribute.attribute_id.name =='colour':
    #                             material_colour=attribute.name
    #                     data.update({'Finish Selected':material_colour})
    #                     transitions = self.env['team.contract.transition.line'].search([('room_id','=',room_line.room_id.id),('appointment_id','=',sale_order.appointment_id.id)])
    #                     count=1
    #                     for transition in transitions:
    #                         transitions_key1='Transition'+ str(count)
    #                         transitions_value_1=transition.name
    #                         data.update({transitions_key1:transitions_value_1})
    #                         transitions_key2='Transition Length'+ str(count)
    #                         transitions_value_2=transition.transition_width
    #                         data.update({transitions_key2: transitions_value_2})
    #                         count=count+1
    #
    #                     contract_questions=self.env['team.contract.question.line'].search([('room_id','=',room_line.room_id.id),('order_id','=',sale_order.id)])
    #                     for contract_question in contract_questions:
    #                         question = contract_question.question_id.code
    #                         answer=""
    #                         for contract_question_answer in contract_question.answers:
    #                             answer = answer + ','+ contract_question_answer.answer
    #
    #                         data.update({question:answer})
    #                     headers = {
    #                         'Content-type': 'application/json',
    #                     }
    #                     request_url = configurations.token_url
    #                     req = requests.post(request_url, data=json.dumps(data), headers=headers,timeout=TIMEOUT)
    #                     req.raise_for_status()
    #                     content = req.json()
    #     except IOError:
    #         error_msg = _(
    #             "Something went wrong during adding quote")
    #         raise self.env['res.config.settings'].get_config_warning(error_msg)

    def add_quote_id_file(self, document):
        result = {
            "success": "true",
            "errors": []
        }
        try:
            configurations = self.env['team.improveit.configuration'].search(
                [('api_type', '=', 'zapier'), ('section', '=', 'QuoteAddAttachment')])
            for sale_order in self:
                if sale_order.quote_id or sale_order.excluded_quote_id:
                    quote_id = sale_order.quote_id
                    excluded_quote_id = sale_order.excluded_quote_id
                    request_url = configurations.token_url
                    if quote_id and document and not document.improveit_id:
                        if document.type == 'binary' and document.store_fname:
                            full_path = document._full_path(document.store_fname)
                            binary_content = open(full_path, 'rb')
                        elif document.type == 'url' and document.url:
                            response = requests.get(document.url)
                            response.raise_for_status()  # Check if the request was successful
                            binary_content = response.content
                        multi_part_data = MultipartEncoder(
                            fields={
                                "QuoteID": quote_id or '',
                                "File": (document.name, binary_content, document.mimetype),
                            }
                        )
                        headers = {
                            'Content-type': multi_part_data.content_type,

                        }
                        _logger.info('Document Upload Input Payload of sale %s : %s '%(sale_order.id, multi_part_data))
                        req = requests.post(request_url, data=multi_part_data, headers=headers,
                                            timeout=TIMEOUT, verify=configurations.enable_ssl)
                        req.raise_for_status()
                        content = req.json()
                        _logger.info('Attaching Contract Document Finished of sale %s: %s' %(sale_order.id, content))
                        if content.get('success', '') == "true":
                            document.sudo().write({'improveit_id': content['id'] or ''})
                        if content.get('success', '') == "false":
                            _logger.info("******--------Error in Contract Document Upload---------********")
                            result.update({"success": "false"})
                    for room_lines in sale_order.room_measurement_line.filtered(lambda x: not x.exclude_from_calculation):
                        if quote_id:
                            _logger.info('Attaching Room line  Data %s' % room_lines.name)
                            if room_lines.shape_image_id:
                                attach = room_lines.shape_image_id
                                if not attach.improveit_id:
                                    extension = attach.name.split(".")[-1]
                                    room_name = room_lines.custom_room_name or ''
                                    if not room_name:
                                        room_name = room_lines.room_id.name
                                    file_name = '%s_Measure.%s' % (room_name, extension)
                                    if attach.type == 'binary' and attach.store_fname:
                                        full_path = attach._full_path(attach.store_fname)
                                        binary_content = open(full_path, 'rb')
                                    elif attach.type == 'url' and attach.url:
                                        response = requests.get(attach.url)
                                        response.raise_for_status()  # Check if the request was successful
                                        binary_content = response.content
                                    multi_part_data = MultipartEncoder(
                                        fields={
                                            "QuoteID": quote_id or '',
                                            "File": (file_name, binary_content, attach.mimetype),
                                        }
                                    )
                                    headers = {
                                        'Content-type': multi_part_data.content_type,
                                    }
                                    _logger.info('Measurement Upload of sale %s: %s' %(sale_order.id, multi_part_data))
                                    _logger.info(multi_part_data)
                                    req = requests.post(request_url, data=multi_part_data, headers=headers, timeout=TIMEOUT, verify=configurations.enable_ssl)
                                    req.raise_for_status()
                                    content = req.json()
                                    _logger.info('Attaching Room Shape Drawing Finished of sale %s: %s' %(sale_order.id, content))
                                    if content.get('success', '') == "true":
                                        attach.sudo().write({'improveit_id': content['id'] or ''})
                                    if content.get('success', '') == "false":
                                        _logger.info("******--------Error in Room Shape Drawing Upload---------********")
                                        result.update({"success": "false"})
                            if room_lines.attachment_ids:
                                count = 0
                                for attachment in room_lines.attachment_ids:
                                    _logger.info('Attaching Room Images')
                                    if not attachment.improveit_id:
                                        count += 1
                                        extension = attachment.name.split(".")[-1]
                                        room_name = room_lines.custom_room_name or ''
                                        if not room_name:
                                            room_name = room_lines.room_id.name
                                        file_name = '%s_%s.%s' % (room_name, count, extension)
                                        if attachment.type == 'binary' and attachment.store_fname:
                                            full_path = attachment._full_path(attachment.store_fname)
                                            binary_content = open(full_path, 'rb')
                                        elif attachment.type == 'url' and attachment.url:
                                            response = requests.get(attachment.url)
                                            response.raise_for_status()  # Check if the request was successful
                                            binary_content = response.content
                                        multi_part_data = MultipartEncoder(
                                            fields={
                                                "QuoteID": quote_id or '',
                                                "File": (file_name, binary_content, attachment.mimetype),
                                            }
                                        )
                                        headers = {
                                            'Content-type': multi_part_data.content_type,
                                        }
                                        _logger.info('Room images Upload of sale %s: %s' %(sale_order.id, multi_part_data))
                                        req = requests.post(request_url, data=multi_part_data, headers=headers,
                                                            timeout=TIMEOUT, verify=configurations.enable_ssl)
                                        req.raise_for_status()
                                        content = req.json()
                                        _logger.info('Attached Image of sale %s: %s' %(sale_order.id, content))
                                        if content.get('success', '') == "true":
                                            attachment.sudo().write({'improveit_id': content['id'] or ''})
                                        if content.get('success', '') == "false":
                                            _logger.info(
                                                "******--------Error in Room Image- %s Upload---------********"%(file_name))
                                            result.update({"success": "false"})
                                _logger.info('%s Room Images upload completed--' % room_lines.name)
                            if room_lines.protrusion_image_ids:
                                count = 0
                                for attachment in room_lines.protrusion_image_ids:
                                    _logger.info('Attaching Room Anomaly Images')
                                    if not attachment.improveit_id:
                                        count += 1
                                        extension = attachment.name.split(".")[-1]
                                        room_name = room_lines.custom_room_name or ''
                                        if not room_name:
                                            room_name = room_lines.room_id.name
                                        file_name = '%s_Anomaly_%s.%s' % (room_name, count, extension)
                                        if attachment.type == 'binary' and attachment.store_fname:
                                            full_path = attachment._full_path(attachment.store_fname)
                                            binary_content = open(full_path, 'rb')
                                        elif attachment.type == 'url' and attachment.url:
                                            response = requests.get(attachment.url)
                                            response.raise_for_status()  # Check if the request was successful
                                            binary_content = response.content
                                        multi_part_data = MultipartEncoder(
                                            fields={
                                                "QuoteID": quote_id or '',
                                                "File": (file_name, binary_content, attachment.mimetype),
                                            }
                                        )
                                        headers = {
                                            'Content-type': multi_part_data.content_type,
                                        }
                                        _logger.info('Room Anomaly images Upload of sale %s: %s' %(sale_order.id, multi_part_data))
                                        _logger.info(multi_part_data)
                                        req = requests.post(request_url, data=multi_part_data, headers=headers,
                                                            timeout=TIMEOUT, verify=configurations.enable_ssl)
                                        req.raise_for_status()
                                        content = req.json()
                                        _logger.info('Attached Image of sale %s: %s' %(sale_order.id, content))
                                        if content.get('success', '') == "true":
                                            attachment.sudo().write({'improveit_id': content['id'] or ''})
                                        if content.get('success', '') == "false":
                                            _logger.info(
                                                "******--------Error in Room Anomaly Image- %s Upload---------********"%(file_name))
                                            result.update({"success": "false"})
                                _logger.info('%s room anomaly images upload completed' % room_lines.name)
                            _logger.info('Attaching Room line Data Finished %s' % room_lines.name)
                    if excluded_quote_id and not quote_id:
                        quote_id = excluded_quote_id
                    for room_lines in sale_order.room_measurement_line.filtered(lambda x: x.exclude_from_calculation):
                        if excluded_quote_id:
                            _logger.info('Attaching Room line  Data %s' % room_lines.name)
                            if room_lines.shape_image_id:
                                attach = room_lines.shape_image_id
                                if not attach.improveit_id:
                                    extension = attach.name.split(".")[-1]
                                    room_name = room_lines.custom_room_name or ''
                                    if not room_name:
                                        room_name = room_lines.room_id.name
                                    file_name = '%s_Measure.%s' % (room_name, extension)
                                    if attach.type == 'binary' and attach.store_fname:
                                        full_path = attach._full_path(attach.store_fname)
                                        binary_content = open(full_path, 'rb')
                                    elif attach.type == 'url' and attach.url:
                                        response = requests.get(attach.url)
                                        response.raise_for_status()  # Check if the request was successful
                                        binary_content = response.content
                                    multi_part_data = MultipartEncoder(
                                        fields={
                                            "QuoteID": excluded_quote_id or '',
                                            "File": (file_name, binary_content, attach.mimetype),
                                        }
                                    )
                                    headers = {
                                        'Content-type': multi_part_data.content_type,
                                    }
                                    _logger.info('Measurement Upload of sale %s: %s' %(sale_order.id, multi_part_data))
                                    req = requests.post(request_url, data=multi_part_data, headers=headers, timeout=TIMEOUT, verify=configurations.enable_ssl)
                                    req.raise_for_status()
                                    content = req.json()
                                    _logger.info('Attaching Room Shape Drawing Finished of sale %s: %s' %(sale_order.id, content))
                                    if content.get('success', '') == "true":
                                        attach.sudo().write({'improveit_id': content['id'] or ''})
                                    if content.get('success', '') == "false":
                                        _logger.info("******--------Error in Room Shape Drawing Upload---------********")
                                        result.update({"success": "false"})
                            if room_lines.attachment_ids:
                                count = 0
                                for attachment in room_lines.attachment_ids:
                                    _logger.info('Attaching Room Images')
                                    if attachment.store_fname and not attachment.improveit_id:
                                        count += 1
                                        extension = attachment.name.split(".")[-1]
                                        room_name = room_lines.custom_room_name or ''
                                        if not room_name:
                                            room_name = room_lines.room_id.name
                                        file_name = '%s_%s.%s' % (room_name, count, extension)
                                        if attachment.type == 'binary' and attachment.store_fname:
                                            full_path = attachment._full_path(attachment.store_fname)
                                            binary_content = open(full_path, 'rb')
                                        elif attachment.type == 'url' and attachment.url:
                                            response = requests.get(attachment.url)
                                            response.raise_for_status()  # Check if the request was successful
                                            binary_content = response.content
                                        multi_part_data = MultipartEncoder(
                                            fields={
                                                "QuoteID": excluded_quote_id or '',
                                                "File": (file_name, binary_content, attachment.mimetype),
                                            }
                                        )
                                        headers = {
                                            'Content-type': multi_part_data.content_type,
                                        }
                                        _logger.info('Room images Upload of sale %s: %s' %(sale_order.id, multi_part_data))
                                        req = requests.post(request_url, data=multi_part_data, headers=headers,
                                                            timeout=TIMEOUT, verify=configurations.enable_ssl)
                                        req.raise_for_status()
                                        content = req.json()
                                        _logger.info('Attached Image of sale %s: %s' %(sale_order.id, content))
                                        if content.get('success', '') == "true":
                                            attachment.sudo().write({'improveit_id': content['id'] or ''})
                                        if content.get('success', '') == "false":
                                            _logger.info(
                                                "******--------Error in Room Image- %s Upload---------********"%(file_name))
                                            result.update({"success": "false"})
                                _logger.info('%s Room Images upload completed--' % room_lines.name)
                            if room_lines.protrusion_image_ids:
                                count = 0
                                for attachment in room_lines.protrusion_image_ids:
                                    _logger.info('Attaching Room Anomaly Images of sale:%s'%sale_order.id)
                                    if attachment.store_fname and not attachment.improveit_id:
                                        count += 1
                                        extension = attachment.name.split(".")[-1]
                                        room_name = room_lines.custom_room_name or ''
                                        if not room_name:
                                            room_name = room_lines.room_id.name
                                        file_name = '%s_Anomaly_%s.%s' % (room_name, count, extension)
                                        if attachment.type == 'binary' and attachment.store_fname:
                                            full_path = attachment._full_path(attachment.store_fname)
                                            binary_content = open(full_path, 'rb')
                                        elif attachment.type == 'url' and attachment.url:
                                            response = requests.get(attachment.url)
                                            response.raise_for_status()  # Check if the request was successful
                                            binary_content = response.content
                                        multi_part_data = MultipartEncoder(
                                            fields={
                                                "QuoteID": excluded_quote_id or '',
                                                "File": (file_name, binary_content, attachment.mimetype),
                                            }
                                        )
                                        headers = {
                                            'Content-type': multi_part_data.content_type,
                                        }
                                        _logger.info('Room Anomaly images Upload of sale %s: %s' %(sale_order.id, multi_part_data))
                                        req = requests.post(request_url, data=multi_part_data, headers=headers,
                                                            timeout=TIMEOUT, verify=configurations.enable_ssl)
                                        req.raise_for_status()
                                        content = req.json()
                                        _logger.info('Attached Image of sale %s: %s' %(sale_order.id, content))
                                        if content.get('success', '') == "true":
                                            attachment.sudo().write({'improveit_id': content['id'] or ''})
                                        if content.get('success', '') == "false":
                                            _logger.info(
                                                "******--------Error in Room Anomaly Image- %s Upload---------********"%(file_name))
                                            result.update({"success": "false"})
                                _logger.info('%s room anomaly images upload completed' % room_lines.name)
                            _logger.info('Attaching Room line Data Finished %s' % room_lines.name)
                    if quote_id and sale_order.appointment_id and sale_order.appointment_id.attachment_ids:
                        attachment_ids = sale_order.appointment_id.attachment_ids
                        count = 0
                        _logger.info('--------------Snapshot Uploading Started--------------')
                        for attachment in attachment_ids:
                            if attachment.store_fname and not attachment.improveit_id:
                                count += 1
                                extension = attachment.name.split(".")[-1]
                                file_name = '%s_%s.%s' % ('Snapshot', count, extension)
                                if attachment.type == 'binary' and attachment.store_fname:
                                    full_path = attachment._full_path(attachment.store_fname)
                                    binary_content = open(full_path, 'rb')
                                elif attachment.type == 'url' and attachment.url:
                                    response = requests.get(attachment.url)
                                    response.raise_for_status()  # Check if the request was successful
                                    binary_content = response.content
                                multi_part_data = MultipartEncoder(
                                    fields={
                                        "QuoteID": quote_id or '',
                                        "File": (file_name, binary_content, attachment.mimetype),
                                    }
                                )
                                headers = {
                                    'Content-type': multi_part_data.content_type,
                                }
                                _logger.info('Snapshot images Upload of sale %s: %s' %(sale_order.id, multi_part_data))
                                req = requests.post(request_url, data=multi_part_data, headers=headers,
                                                    timeout=TIMEOUT, verify=configurations.enable_ssl)
                                req.raise_for_status()
                                content = req.json()
                                _logger.info('Attached Snapshot of sale %s: %s' %(sale_order.id, content))
                                if content.get('success', '') == "true":
                                    attachment.sudo().write({'improveit_id': content['id'] or ''})
                                if content.get('success', '') == "false":
                                    _logger.info(
                                        "******--------Error in Snapshot Image- %s Upload---------********" % (file_name))
                                    result.update({"success": "false"})
                        _logger.info('----------Snapshot Uploading Finished-----------')

        except IOError:
            # error_msg = _(
            #     "Something went wrong during adding quote attachment")
            # raise self.env['res.config.settings'].get_config_warning(error_msg)
            pass
            _logger.error("******--------Error in add_quote_id_file---------********")
            result.update({"success": "false"})
        return result
    
    def action_send_contract_email(self):
        sync_log = self.env['otl.appointment.sync.log']
        for sale_order in self:
            sale_order.email_sent = False
            result = sale_order.add_contract_document_file()
            if result.get('success', '') == 'true':
                sync_log.create({
                    'appointment_id': sale_order.appointment_id.id,
                    'response': result,
                    'name': 'Send Contract Email To Customer',
                })
            else:
                sync_log.create({
                    'appointment_id': sale_order.appointment_id.id,
                    'response': result,
                    'state': 'failed',
                    'name': 'Send Contract Email To Customer',
                })
        return

    def add_contract_document_file(self):
        result = {
            "success": "true",
            "errors": []
        }
        try:
            configurations = self.env['team.improveit.configuration'].search([('api_type', '=', 'contract_doc')])
            for sale_order in self:
                if sale_order.quote_id or sale_order.excluded_quote_id:
                    quote_id = sale_order.quote_id
                    if not quote_id:
                        quote_id = sale_order.excluded_quote_id
                    request_url = configurations.token_url
                    if sale_order.contract_doc_attachment_id:
                        document = sale_order.contract_doc_attachment_id
                        if document and not sale_order.email_sent:
                            if document.type == 'binary' and document.store_fname:
                                full_path = document._full_path(document.store_fname)
                                binary_content = open(full_path, 'rb')
                            elif document.type == 'url' and document.url:
                                response = requests.get(document.url)
                                response.raise_for_status()  # Check if the request was successful
                                binary_content = response.content
                            multi_part_data = MultipartEncoder(
                                fields={
                                    "SaleID": quote_id or '',
                                    "WorkOrderFile": ('WorkOrder.pdf', binary_content, document.mimetype),
                                    "ContractDate": sale_order.date_order.strftime('%m/%d/%Y')
                                }
                            )
                            headers = {
                                'Content-type': multi_part_data.content_type,

                            }
                            _logger.info('Contract Document Upload of sale %s: %s' %(sale_order.id, multi_part_data))
                            req = requests.post(request_url, data=multi_part_data, headers=headers,
                                                timeout=TIMEOUT, verify=configurations.enable_ssl)
                            req.raise_for_status()
                            content = req.json()
                            _logger.info('Document Upload-------content--%s', content)

                            _logger.info('Attaching Contract Document Finished of sale %s: %s' %(sale_order.id, content))
                            if content.get('Result', False) == 'Success':
                                sale_order.write({'email_sent': True})
                                #document.sudo().write({'improveit_id': content.get('Result', False)})
                            else:
                                _logger.info("******--------Error in add_contract_document_file---------********")
                                result.update({"success": "false"})
                                result.update(content)
        except IOError:
            # error_msg = _(
            #     "Something went wrong during adding Sale Contract Document Attachment")
            # raise self.env['res.config.settings'].get_config_warning(error_msg)
            pass
            _logger.error("******--------Error in add_contract_document_file---------********")
            result.update({"success": "false"})
        return result

    def action_sync_contract_doc_on_i360(self):
        sync_log = self.env['otl.appointment.sync.log']
        try:
            for sale_order in self:
                result = {
                    "success": "true",
                    "errors": []
                }
                if sale_order.quote_id or sale_order.excluded_quote_id:
                    quote_id = sale_order.quote_id
                    if not quote_id:
                        quote_id = sale_order.excluded_quote_id
                    configurations = self.env['team.improveit.configuration'].search(
                        [('api_type', '=', 'zapier'), ('section', '=', 'SaleAddAttachment')], limit=1)
                    
                    request_url = configurations.token_url
                    if sale_order.contract_doc_attachment_id:
                        attachment = sale_order.contract_doc_attachment_id
                        if attachment.type == 'binary' and attachment.store_fname:
                            full_path = attachment._full_path(attachment.store_fname)
                            binary_content = open(full_path, 'rb')
                        elif attachment.type == 'url' and attachment.url:
                            response = requests.get(attachment.url)
                            response.raise_for_status()  # Check if the request was successful
                            binary_content = response.content
                        multi_part_data = MultipartEncoder(
                            fields={
                                "SaleId": quote_id or '',
                                "File": ('WorkOrder.pdf', binary_content, attachment.mimetype)
                            }
                        )
                        headers = {
                            'Content-type': multi_part_data.content_type,

                        }
                        _logger.info('Contract Document Upload of sale %s: %s' %(sale_order.id, multi_part_data))
                        req = requests.post(request_url, data=multi_part_data, headers=headers,
                                            timeout=TIMEOUT, verify=configurations.enable_ssl)
                        req.raise_for_status()
                        content = req.json()
                        if isinstance(content, str):
                            content = json.loads(content)
 
                        _logger.info('Uploading Contract Document Finished of sale %s: %s: %s' %(sale_order.id, content ,str(type(content))))
                        if content.get('success', '') == "true":
                            attachment.sudo().write({'improveit_id': content['id'] or ''})
                            _logger.info("Contract Document uploaded Successfully of sale"%sale_order.id)
                            sync_log.create({
                                    'appointment_id': sale_order.appointment_id.id,
                                    'response': content,
                                    'state': 'success',
                                    'name': 'Contract Document Upload To i360 ',
                                })
                        if content.get('success', '') == "false":
                            sync_log.create({
                                'appointment_id': sale_order.appointment_id.id,
                                'response': content,
                                'state': 'failed',
                                'name': 'Contract Document Upload To i360 ',
                            })
                            _logger.info("/n Error during upload Contract Document")
                            result.update({"success": "false"})
        except Exception as e:
            pass
            _logger.error("******--------Error in add_contract_document_file---------********: %s",str(e))
            result.update({"success": "false"})
        return result

    def action_upload_credit_application(self, result):
        for sale_order in self:
            if sale_order.quote_id or sale_order.excluded_quote_id:
                configurations = self.env['team.improveit.configuration'].search(
                    [('api_type', '=', 'zapier'), ('section', '=', 'SaleAddAttachment')])
                quote_id = sale_order.quote_id
                if not quote_id:
                    quote_id = sale_order.excluded_quote_id
                request_url = configurations.token_url
                credit_application = self.env['team.credit.application'].search([
                    ('order_id', '=', sale_order.id)
                ], limit=1, order='id desc')
                if credit_application:
                    if not credit_application.attachment_id:
                        credit_application.generate_link(sale_order)
                    attachment = credit_application.attachment_id
                    if not attachment.improveit_id:
                        if attachment.type == 'binary' and attachment.store_fname:
                            full_path = attachment._full_path(attachment.store_fname)
                            binary_content = open(full_path, 'rb')
                        elif attachment.type == 'url' and attachment.url:
                            response = requests.get(attachment.url)
                            response.raise_for_status()  # Check if the request was successful
                            binary_content = response.content
                        multi_part_data = MultipartEncoder(
                            fields={
                                "SaleID": quote_id or '',
                                "File": (attachment.name, binary_content, attachment.mimetype),
                            }
                        )

                        headers = {
                            'Content-type': multi_part_data.content_type,

                        }
                        _logger.info('Credit Card Document Upload of sale %s: %s' % (sale_order.id, multi_part_data))
                        _logger.info(multi_part_data)
                        req = requests.post(request_url, data=multi_part_data, headers=headers,
                                            timeout=TIMEOUT, verify=configurations.enable_ssl)
                        req.raise_for_status()
                        content = req.json()
                        if isinstance(content, str):
                            content = json.loads(content)
                        _logger.info(
                            'Attaching Credit Card Document Finished of sale %s: %s' % (sale_order.id, content))
                        if content.get('success', '') == "true":
                            attachment.sudo().write({'improveit_id': content['id'] or ''})
                        if content.get('success', '') == "false":
                            _logger.info("******--------Error in Credit Card Document Upload---------********")
                            result.update({"success": "false"})

        return result

    def add_sale_id_file(self, document=None):
        result = {
            "success": "true",
            "errors": []
        }
        try:
            configurations = self.env['team.improveit.configuration'].search(
                [('api_type', '=', 'zapier'), ('section', '=', 'SaleAddAttachment')])
            for sale_order in self:
                if sale_order.quote_id:
                    quote_id = sale_order.quote_id
                    request_url = configurations.token_url
                    # if document and document.store_fname:
                    #     full_path = document._full_path(document.store_fname)
                    #     multi_part_data = MultipartEncoder(
                    #         fields={
                    #             "SaleID": quote_id or '',
                    #             "File": (document.name, open(full_path, 'rb'), document.mimetype),
                    #         }
                    #     )
                    #
                    #     headers = {
                    #         'Content-type': multi_part_data.content_type,
                    #
                    #     }
                    #     _logger.info('Document Upload---------')
                    #     _logger.info(multi_part_data)
                    #     req = requests.post(request_url, data=multi_part_data, headers=headers,
                    #                         timeout=TIMEOUT)
                    #     req.raise_for_status()
                    #     content = req.json()
                    #     _logger.info('Attaching Contract Document Finished %s ' % content)
                    result= sale_order.action_upload_credit_application(result)
                    for room_lines in sale_order.room_measurement_line.filtered(lambda x: not x.exclude_from_calculation):
                        _logger.info('Attaching Room line  Data %s' % room_lines.name)
                        if room_lines.shape_image_id:
                            attach = room_lines.shape_image_id
                            if not attach.improveit_id:
                                extension = attach.name.split(".")[-1]
                                room_name = room_lines.custom_room_name or ''
                                if not room_name:
                                    room_name = room_lines.room_id.name
                                file_name = '%s_Measure.%s'%(room_name, extension)
                                if attach.type == 'binary' and attach.store_fname:
                                    full_path = attach._full_path(attach.store_fname)
                                    binary_content = open(full_path, 'rb')
                                elif attach.type == 'url' and attach.url:
                                    response = requests.get(attach.url)
                                    response.raise_for_status()  # Check if the request was successful
                                    binary_content = response.content
                                multi_part_data = MultipartEncoder(
                                    fields={
                                        "SaleID": quote_id or '',
                                        "File": (file_name, binary_content, attach.mimetype),
                                    }
                                )
                                headers = {
                                    'Content-type': multi_part_data.content_type,
                                }
                                _logger.info('Measurement Upload of sale %s: %s' %(sale_order.id, multi_part_data))
                                req = requests.post(request_url, data=multi_part_data, headers=headers, timeout=TIMEOUT, verify=configurations.enable_ssl)
                                req.raise_for_status()
                                content = req.json()
                                if isinstance(content, str):
                                    content = json.loads(content)
                                _logger.info('Attaching Room Shape Drawing Finished of sale %s: %s' %(sale_order.id, content))
                                if content.get('success', '') == "true":
                                    attach.sudo().write({'improveit_id': content['id'] or ''})
                                if content.get('success', '') == "false":
                                    _logger.info("******--------Error in Room Shape Drawing Upload---------********")
                                    result.update({"success": "false"})
                        if room_lines.attachment_ids:
                            count = 0
                            for attachment in room_lines.attachment_ids:
                                _logger.info('Attaching Room Images')
                                if not attachment.improveit_id:
                                    count += 1
                                    extension = attachment.name.split(".")[-1]
                                    room_name = room_lines.custom_room_name or ''
                                    if not room_name:
                                        room_name = room_lines.room_id.name
                                    file_name = '%s_%s.%s' % (room_name, count, extension)
                                    if attachment.type == 'binary' and attachment.store_fname:
                                        full_path = attachment._full_path(attachment.store_fname)
                                        binary_content = open(full_path, 'rb')
                                    elif attachment.type == 'url' and attachment.url:
                                        response = requests.get(attachment.url)
                                        response.raise_for_status()  # Check if the request was successful
                                        binary_content = response.content
                                    multi_part_data = MultipartEncoder(
                                        fields={
                                            "SaleID": quote_id or '',
                                            "File": (file_name, binary_content, attachment.mimetype),
                                        }
                                    )
                                    headers = {
                                        'Content-type': multi_part_data.content_type,
                                    }
                                    _logger.info('Room images Upload of sale %s: %s' %(sale_order.id, multi_part_data))
                                    req = requests.post(request_url, data=multi_part_data, headers=headers,
                                                        timeout=TIMEOUT, verify=configurations.enable_ssl)
                                    req.raise_for_status()
                                    content = req.json()
                                    if isinstance(content, str):
                                        content = json.loads(content)
                                    _logger.info('Attached Image of sale %s: %s' %(sale_order.id, content))
                                    if content.get('success', '') == "true":
                                        attachment.sudo().write({'improveit_id': content['id'] or ''})
                                    if content.get('success', '') == "false":
                                        _logger.info(
                                            "******--------Error in Room Image- %s Upload---------********"%(file_name))
                                        result.update({"success": "false"})
                        if room_lines.protrusion_image_ids:
                            count = 0
                            for attachment in room_lines.protrusion_image_ids:
                                _logger.info('Attaching Room Anomaly Images')
                                if not attachment.improveit_id:
                                    count += 1
                                    extension = attachment.name.split(".")[-1]
                                    room_name = room_lines.custom_room_name or ''
                                    if not room_name:
                                        room_name = room_lines.room_id.name
                                    file_name = '%s_Anomaly_%s.%s' % (room_name, count, extension)
                                    if attachment.type == 'binary' and attachment.store_fname:
                                        full_path = attachment._full_path(attachment.store_fname)
                                        binary_content = open(full_path, 'rb')
                                    elif attachment.type == 'url' and attachment.url:
                                        response = requests.get(attachment.url)
                                        response.raise_for_status()  # Check if the request was successful
                                        binary_content = response.content
                                    multi_part_data = MultipartEncoder(
                                        fields={
                                            "SaleID": quote_id or '',
                                            "File": (file_name, binary_content, attachment.mimetype),
                                        }
                                    )
                                    headers = {
                                        'Content-type': multi_part_data.content_type,
                                    }
                                    _logger.info('Room Anomaly images Upload of sale %s: %s' %(sale_order.id, multi_part_data))
                                    req = requests.post(request_url, data=multi_part_data, headers=headers,
                                                        timeout=TIMEOUT, verify=configurations.enable_ssl)
                                    req.raise_for_status()
                                    content = req.json()
                                    if isinstance(content, str):
                                        content = json.loads(content)
                                    _logger.info('Attached Image of sale %s: %s' %(sale_order.id, content))
                                    if content.get('success', '') == "true":
                                        attachment.sudo().write({'improveit_id': content['id'] or ''})
                                    if content.get('success', '') == "false":
                                        _logger.info(
                                            "******--------Error in Room Anomaly  Image- %s Upload---------********"%(file_name))
                                        result.update({"success": "false"})
                            _logger.info('%s room anomaly images upload completed' % room_lines.name)
                        _logger.info('Attaching Room line Data Finished %s' % room_lines.name)
                    if sale_order.appointment_id and sale_order.appointment_id.attachment_ids:
                        attachment_ids = sale_order.appointment_id.attachment_ids
                        count = 0
                        _logger.info('--------------Snapshot Uploading Started--------------')
                        for attachment in attachment_ids:
                            if not attachment.improveit_id:
                                count += 1
                                file_name_split = attachment.name.split(".")
                                if len(file_name_split)> 1:
                                    extension = file_name_split[-1]
                                else:
                                    extension='.JPG'
                                file_name = '%s_%s.%s' % ('Snapshot', count, extension)
                                if attachment.type == 'binary' and attachment.store_fname:
                                    full_path = attachment._full_path(attachment.store_fname)
                                    binary_content = open(full_path, 'rb')
                                elif attachment.type == 'url' and attachment.url:
                                    response = requests.get(attachment.url)
                                    response.raise_for_status()  # Check if the request was successful
                                    binary_content = response.content
                                multi_part_data = MultipartEncoder(
                                    fields={
                                        "SaleID": quote_id or '',
                                        "File": (file_name, binary_content, attachment.mimetype),
                                    }
                                )
                                headers = {
                                    'Content-type': multi_part_data.content_type,
                                }
                                _logger.info('Snapshot images Upload of sale %s: %s' %(sale_order.id, multi_part_data))
                                req = requests.post(request_url, data=multi_part_data, headers=headers,
                                                    timeout=TIMEOUT, verify=configurations.enable_ssl)
                                req.raise_for_status()
                                content = req.json()
                                if isinstance(content, str):
                                    content = json.loads(content)
                                _logger.info('Attached Snapshot of sale %s: %s' %(sale_order.id, content))
                                if content.get('success', '') == "true":
                                    attachment.sudo().write({'improveit_id': content['id'] or ''})
                                if content.get('success', '') == "false":
                                    _logger.info(
                                        "******--------Error in Snapshot Image- %s Upload---------********" % (file_name))
                                    result.update({"success": "false"})
                        _logger.info('----------Snapshot Uploading Finished-----------')

        except IOError:
            # error_msg = _(
            #     "Something went wrong during adding Sale Attachment")
            # raise self.env['res.config.settings'].get_config_warning(error_msg)
            pass
            _logger.error("******--------Error in add_sale_id_file---------********")
            result.update({"success": "false"})
        return result

    def add_quote_items_sales_app(self):
        result = {
            "success": "true",
            "errors": []
        }
        try:
            configurations = self.env['team.improveit.configuration'].search(
                [('api_type', '=', 'boomi')], limit=1)
            for sale_order in self:
                if sale_order.appointment_id and (sale_order.quote_id or sale_order.excluded_quote_id):
                    included_room_measurement_lines_to_sync = sale_order.room_measurement_line.filtered(
                        lambda x: not x.exclude_from_calculation and not x.improveit_id)
                    excluded_room_measurement_lines_to_sync = sale_order.room_measurement_line.filtered(
                        lambda x: x.exclude_from_calculation and not x.improveit_id)
                    customer_name = sale_order.appointment_id.customer_name
                    lastname = customer_name.split()[1]
                    first_name = customer_name.split()[0]
                    date_quote_format = sale_order.create_date.strftime('%m%d%H%M%S')
                    quote_name = lastname + " ," + first_name + "-" + date_quote_format
                    floor_type = False
                    if sale_order.floor_type:
                        floor_type = sale_order.floor_type
                    else:
                        payment_plan_id = self.env['ir.config_parameter'].sudo().get_param(
                            'payment_plan_id') or False
                        if payment_plan_id:
                            old_floor_type = self.env['product.template'].browse(int(payment_plan_id))
                            if old_floor_type and old_floor_type.exists() and not old_floor_type.active:
                                floor_type = self.env['product.template'].search([('name', '=', old_floor_type.name)], limit=1)
                            else:
                                floor_type = old_floor_type

                    product_name = floor_type and floor_type.name or ''
                    improveit_product_id = floor_type and floor_type.improveit_product_id or ''
                    category_name = floor_type and floor_type.categ_id and floor_type.categ_id.name or ''
                    # no_of_rooms = len(sale_order.room_measurement_line.filtered(lambda x: not x.exclude_from_calculation))
                    # discount_per_room = sale_order.adjustment and no_of_rooms and sale_order.adjustment/float(no_of_rooms) or 0
                    total_discount_amount = sale_order.get_total_discount()
                    total_sale_amount = sale_order.one_year_price
                    discount_rate = 0
                    if total_sale_amount and total_discount_amount:
                        discount_rate = total_discount_amount / total_sale_amount
                    if included_room_measurement_lines_to_sync and sale_order.quote_id:
                        for room_line in included_room_measurement_lines_to_sync:
                            stair_product_name = ''
                            stair_improveit_product_id = ''
                            stair_category_name = ''
                            stair_product = False
                            if room_line.room_id and room_line.room_id.product_category_id and room_line.room_id.product_category_id.name.upper() == 'VINYL STAIRS' and floor_type:
                                stair_product = self.env['product.template'].search([
                                    ('type', '=', 'product'),
                                    ('product_variant_ids', '!=', False),
                                    ('categ_id.name', 'ilike', 'Stairs'),
                                    ('grade', '=', floor_type.grade)
                                ], order='sequence asc', limit=1)
                                if stair_product:
                                    stair_product_name = stair_product.name or ''
                                    stair_improveit_product_id = stair_product.improveit_product_id or ''
                                    stair_category_name = stair_product.categ_id and stair_product.categ_id.name or ''

                            reflect_cost = 0
                            leveling_solution_included = 0
                            removal_cost = 0
                            color_up_charge_total = room_line.color_up_charge_total or 0
                            molding_total_price = room_line.molding_total_price or 0
                            comments = room_line.comments or ""
                            if room_line.image_comments:
                                if comments:
                                    comments += ', ' + room_line.image_comments or ''
                                else:
                                    comments = room_line.image_comments or ''
                            if comments:
                                comments = comments.replace('&', 'and')
                            data = {

                                "QuoteID": sale_order.quote_id or '',
                                "MoldingType": room_line.molding_type_id and room_line.molding_type_id.name or "",
                                "Comments": comments
                            }
                            if stair_product:
                                data.update({
                                    "ProductName": stair_product_name,
                                    "ProductID": stair_improveit_product_id,
                                    "Category": stair_category_name,
                                })
                                stair_count = 0
                                if room_line.custom_room_name:
                                    contract_questions = self.env['team.contract.question.line'].search([
                                        ('room_name', '=', room_line.custom_room_name),
                                        ('appointment_id', '=', sale_order.appointment_id.id),
                                        ('question_id.code', '=', 'StairCount')
                                    ], limit=1)
                                else:
                                    contract_questions = self.env['team.contract.question.line'].search([
                                        ('room_id', '=', room_line.room_id.id),
                                        ('appointment_id', '=', sale_order.appointment_id.id),
                                        ('question_id.code', '=', 'StairCount')
                                    ], limit=1)
                                if contract_questions:
                                    for answer_obj in contract_questions.answers:
                                        stair_count = float(answer_obj.answer)
                                if sale_order.stair_calc_based_on == 'list_price':
                                    room_cost = stair_count * stair_product.list_price
                                else:
                                    room_cost = stair_count * stair_product.msrp
                            else:
                                data.update({
                                    "ProductName": product_name,
                                    "ProductID": improveit_product_id,
                                    "Category": category_name,
                                })
                                if sale_order.calc_based_on == 'list_price':
                                    room_cost = room_line.adjusted_area * floor_type.list_price
                                else:
                                    room_cost = room_line.adjusted_area * floor_type.msrp
                            if room_line.custom_room_name:
                                contract_question_line = sale_order.contract_question_line.filtered(
                                    lambda x: x.room_name == room_line.custom_room_name)
                            else:
                                contract_question_line = sale_order.contract_question_line.filtered(
                                    lambda x: x.room_id == room_line.room_id.id)
                            for questions in contract_question_line:
                                if questions.room_id.id == room_line.room_id.id and questions.question_id.code != 'StairCount':
                                    if questions.question_id.reflect_cost:
                                        reflect_cost += questions.extra_price or 0
                                    if questions.amount_included and questions.question_id.code == 'LevelingSolutionSqft':
                                        leveling_solution_included = questions.amount_included
                                    if questions.question_id.code == 'RemoveCurrentCovering':
                                        removal_cost = questions.extra_price or 0

                            unit_price = room_cost + reflect_cost + color_up_charge_total + molding_total_price + removal_cost
                            discounted_unit_price = unit_price
                            if discount_rate:
                                discount = unit_price * discount_rate
                                discounted_unit_price = round(unit_price - discount)
                            data.update({"Description": room_line.custom_room_name and room_line.custom_room_name or room_line.room_id.name})
                            data.update({"Taxable": True})
                            data.update({"Units": "Room"})
                            data.update({"Quantity": 1})
                            data.update({"UnitPrice": discounted_unit_price})
                            data.update({"RoomName": room_line.custom_room_name and room_line.custom_room_name or room_line.room_id.name})
                            data.update({"RoomArea": room_line.adjusted_area})
                            data.update({'Perimeter': room_line.room_perimeter})
                            data.update({'ColorUpchargeTotal': color_up_charge_total})
                            data.update({'LevelingSolutionIncluded': leveling_solution_included})
                            data.update({'RemovalCost': removal_cost})
                            attribute_value_ids = room_line.material_id.product_template_attribute_value_ids
                            material_colour = ""
                            for attribute in attribute_value_ids:
                                if attribute.attribute_id.name == 'colour':
                                    material_colour = attribute.name
                            data.update({"ProductSelected": material_colour})
                            transitions = room_line.transition_line_id or []
                            count = 1
                            for transition in transitions:
                                transitions_key1 = 'Transition' + str(count)
                                transitions_value_1 = transition.name
                                transitions_key2 = 'TransitionLength' + str(count)
                                transitions_value_2 = transition.transition_width
                                transitions_key3 = 'TransitionHeight' + str(count)
                                transitions_value_3 = transition.transition_height or ''
                                data.update({
                                    transitions_key1: transitions_value_1,
                                    transitions_key2: transitions_value_2,
                                    transitions_key3: transitions_value_3,

                                })
                                count = count + 1
                            if room_line.custom_room_name:
                                contract_questions = self.env['team.contract.question.line'].search(
                                    [('room_name', '=', room_line.custom_room_name), ('order_id', '=', sale_order.id)])
                            else:
                                contract_questions = self.env['team.contract.question.line'].search(
                                    [('room_id', '=', room_line.room_id.id), ('order_id', '=', sale_order.id)])
                            for contract_question in contract_questions:
                                question = contract_question.question_id.code
                                answer = ""
                                for contract_question_answer in contract_question.answers:
                                    if contract_question.question_id.question_type == 'numerical_box':
                                        answer = eval(contract_question_answer.answer)
                                    else:
                                        answer = contract_question_answer.answer
                                    if question != 'StairCoverRisers':
                                        if answer == 'Yes':
                                            answer = True
                                        elif answer == 'No':
                                            answer = False

                                data.update({question: answer})
                            headers = {
                                'Content-type': 'application/json',
                            }

                            end_point_url = configurations.token_url
                            client_token = configurations.client_token
                            _logger.info('Add Quote Item API Data of sale %s: %s' %(sale_order.id, data))
                            if end_point_url and client_token:
                                request_url = end_point_url + 'AddQuoteItem' + client_token
                            req = requests.post(request_url, data=json.dumps(data), headers=headers, timeout=TIMEOUT, verify=configurations.enable_ssl)
                            _logger.info('Add Quote Item API Response of sale %s: %s' %(sale_order.id, str(req.content)))
                            req.raise_for_status()
                            try:
                                content = req.json()
                            except IOError:
                                if req.status_code == 200:
                                    return {
                                        'success': 'false',
                                        'errors': [
                                            {
                                                'message': "Quote data successfully send to the system, but response is in wrong format."
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
                            _logger.info('Add Quote Items API Response of sale %s: %s' %(sale_order.id, content))
                            if content.get('success', '') == "true":
                                room_line.improveit_id = content['id'] or ''
                            if content.get('success', '') == "false":
                                return content
                    if excluded_room_measurement_lines_to_sync and sale_order.excluded_quote_id:
                        for room_line in excluded_room_measurement_lines_to_sync:
                            stair_product_name = ''
                            stair_improveit_product_id = ''
                            stair_category_name = ''
                            stair_product = False
                            if room_line.room_id and room_line.room_id.product_category_id and room_line.room_id.product_category_id.name.upper() == 'VINYL STAIRS' and floor_type:
                                stair_product = self.env['product.template'].search([
                                    ('type', '=', 'product'),
                                    ('product_variant_ids', '!=', False),
                                    ('categ_id.name', 'ilike', 'Stairs'),
                                    ('grade', '=', floor_type.grade)
                                ], order='sequence asc', limit=1)
                                if stair_product:
                                    stair_product_name = stair_product.name or ''
                                    stair_improveit_product_id = stair_product.improveit_product_id or ''
                                    stair_category_name = stair_product.categ_id and stair_product.categ_id.name or ''

                            reflect_cost = 0
                            leveling_solution_included = 0
                            removal_cost = 0
                            color_up_charge_total = room_line.color_up_charge_total or 0
                            molding_total_price = room_line.molding_total_price or 0
                            comments = room_line.comments or ""
                            if room_line.image_comments:
                                if comments:
                                    comments += ', ' + room_line.image_comments or ''
                                else:
                                    comments = room_line.image_comments or ''
                            if comments:
                                comments = comments.replace('&', 'and')
                            data = {

                                "QuoteID": sale_order.excluded_quote_id or '',
                                "MoldingType": room_line.molding_type_id and room_line.molding_type_id.name or "",
                                "Comments": comments
                            }
                            if stair_product:
                                data.update({
                                    "ProductName": stair_product_name,
                                    "ProductID": stair_improveit_product_id,
                                    "Category": stair_category_name,
                                })
                                stair_count = 0
                                if room_line.custom_room_name:
                                    contract_questions = self.env['team.contract.question.line'].search([
                                        ('room_name', '=', room_line.custom_room_name),
                                        ('appointment_id', '=', sale_order.appointment_id.id),
                                        ('question_id.code', '=', 'StairCount')
                                    ], limit=1)
                                else:
                                    contract_questions = self.env['team.contract.question.line'].search([
                                        ('room_id', '=', room_line.room_id.id),
                                        ('appointment_id', '=', sale_order.appointment_id.id),
                                        ('question_id.code', '=', 'StairCount')
                                    ], limit=1)
                                if contract_questions:
                                    for answer_obj in contract_questions.answers:
                                        stair_count = float(answer_obj.answer)
                                if sale_order.stair_calc_based_on == 'list_price':
                                    room_cost = stair_count * stair_product.list_price
                                else:
                                    room_cost = stair_count * stair_product.msrp
                            else:
                                data.update({
                                    "ProductName": product_name,
                                    "ProductID": improveit_product_id,
                                    "Category": category_name,
                                })
                                if sale_order.calc_based_on == 'list_price':
                                    room_cost = room_line.adjusted_area * floor_type.list_price
                                else:
                                    room_cost = room_line.adjusted_area * floor_type.msrp
                            if room_line.custom_room_name:
                                contract_question_line = sale_order.contract_question_line.filtered(
                                    lambda x: x.room_name == room_line.custom_room_name)
                            else:
                                contract_question_line = sale_order.contract_question_line.filtered(
                                    lambda x: x.room_id == room_line.room_id.id)
                            for questions in contract_question_line:
                                if questions.room_id.id == room_line.room_id.id and questions.question_id.code != 'StairCount':
                                    if questions.question_id.reflect_cost:
                                        reflect_cost += questions.extra_price or 0
                                    if questions.amount_included and questions.question_id.code == 'LevelingSolutionSqft':
                                        leveling_solution_included = questions.amount_included
                                    if questions.question_id.code == 'RemoveCurrentCovering':
                                        removal_cost = questions.extra_price or 0

                            unit_price = room_cost + reflect_cost + color_up_charge_total + molding_total_price + removal_cost
                            discounted_unit_price = unit_price
                            if discount_rate:
                                discount = unit_price * discount_rate
                                discounted_unit_price = round(unit_price - discount)
                            data.update({
                                            "Description": room_line.custom_room_name and room_line.custom_room_name or room_line.room_id.name})
                            data.update({"Taxable": True})
                            data.update({"Units": "Room"})
                            data.update({"Quantity": 1})
                            data.update({"UnitPrice": discounted_unit_price})
                            data.update({
                                            "RoomName": room_line.custom_room_name and room_line.custom_room_name or room_line.room_id.name})
                            data.update({"RoomArea": room_line.adjusted_area})
                            data.update({'Perimeter': room_line.room_perimeter})
                            data.update({'ColorUpchargeTotal': color_up_charge_total})
                            data.update({'LevelingSolutionIncluded': leveling_solution_included})
                            data.update({'RemovalCost': removal_cost})
                            attribute_value_ids = room_line.material_id.product_template_attribute_value_ids
                            material_colour = ""
                            for attribute in attribute_value_ids:
                                if attribute.attribute_id.name == 'colour':
                                    material_colour = attribute.name
                            data.update({"ProductSelected": material_colour})
                            transitions = room_line.transition_line_id or []
                            count = 1
                            for transition in transitions:
                                transitions_key1 = 'Transition' + str(count)
                                transitions_value_1 = transition.name
                                transitions_key2 = 'TransitionLength' + str(count)
                                transitions_value_2 = transition.transition_width
                                transitions_key3 = 'TransitionHeight' + str(count)
                                transitions_value_3 = transition.transition_height or ''
                                data.update({
                                    transitions_key1: transitions_value_1,
                                    transitions_key2: transitions_value_2,
                                    transitions_key3: transitions_value_3,

                                })
                                count = count + 1
                            if room_line.custom_room_name:
                                contract_questions = self.env['team.contract.question.line'].search(
                                    [('room_name', '=', room_line.custom_room_name), ('order_id', '=', sale_order.id)])
                            else:
                                contract_questions = self.env['team.contract.question.line'].search(
                                    [('room_id', '=', room_line.room_id.id), ('order_id', '=', sale_order.id)])
                            for contract_question in contract_questions:
                                question = contract_question.question_id.code
                                answer = ""
                                for contract_question_answer in contract_question.answers:
                                    if contract_question.question_id.question_type == 'numerical_box':
                                        answer = eval(contract_question_answer.answer)
                                    else:
                                        answer = contract_question_answer.answer
                                    if question != 'StairCoverRisers':
                                        if answer == 'Yes':
                                            answer = True
                                        elif answer == 'No':
                                            answer = False

                                data.update({question: answer})
                            headers = {
                                'Content-type': 'application/json',
                            }

                            end_point_url = configurations.token_url
                            client_token = configurations.client_token
                            _logger.info('Add Quote Item API Payload of sale %s: %s' % (sale_order.id, data))
                            if end_point_url and client_token:
                                request_url = end_point_url + 'AddQuoteItem' + client_token
                            req = requests.post(request_url, data=json.dumps(data), headers=headers, timeout=TIMEOUT,
                                                verify=configurations.enable_ssl)
                            _logger.info('Add Quote Item API Response of sale %s: %s' % (sale_order.id, str(req.content)))
                            req.raise_for_status()
                            try:
                                content = req.json()
                            except IOError:
                                if req.status_code == 200:
                                    return {
                                        'success': 'false',
                                        'errors': [
                                            {
                                                'message': "Quote data successfully send to the system, but response is in wrong format."
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
                            _logger.info('Add Quote Items API Response of sale %s: %s' % (sale_order.id, content))
                            if content.get('success', '') == "true":
                                room_line.improveit_id = content['id'] or ''
                            if content.get('success', '') == "false":
                                return content
        except IOError:
            # error_msg = _(
            #     "Something went wrong during adding quote items")
            # raise self.env['res.config.settings'].get_config_warning(error_msg)
            pass
            _logger.error("******--------Error in add_quote_items_sales_app---------********")
            result.update({"success": "false"})
        return result

    def get_total_discount(self):
        discount = 0
        for order in self:
            if order.adjustment or order.promotion_code_id:
                for line in order.order_line.filtered(lambda x: x.price_unit <0):
                    discount += abs(line.price_unit)
        return discount


    def add_sale_items_api(self):
        result = {
            "success": "true",
            "errors": []
        }
        try:
            configurations = self.env['team.improveit.configuration'].search(
                [('api_type', '=', 'boomi')], limit=1)
            for sale_order in self:
                if sale_order.appointment_id and sale_order.quote_id:
                    customer_name = sale_order.appointment_id.customer_name
                    lastname = customer_name.split()[1]
                    first_name = customer_name.split()[0]
                    date_quote_format = sale_order.create_date.strftime('%m%d%H%M%S')
                    quote_name = lastname + " ," + first_name + "-" + date_quote_format
                    product_name = sale_order.floor_type.name
                    improveit_product_id = sale_order.floor_type.improveit_product_id or False
                    category_name = sale_order.floor_type and sale_order.floor_type.categ_id and sale_order.floor_type.categ_id.name or ''
                    room_measurement_lines_to_sync = sale_order.room_measurement_line.filtered(lambda x: not x.exclude_from_calculation and not x.improveit_id)
                    total_discount_amount = sale_order.get_total_discount()
                    total_sale_amount = sale_order.one_year_price
                    discount_rate = 0
                    if total_sale_amount and total_discount_amount:
                        discount_rate = total_discount_amount/total_sale_amount
                    for room_line in room_measurement_lines_to_sync:
                        reflect_cost = 0
                        leveling_solution_included = 0
                        removal_cost = 0
                        color_up_charge_total = room_line.color_up_charge_total or 0
                        molding_total_price = room_line.molding_total_price or 0
                        stair_product_name = ''
                        stair_improveit_product_id = ''
                        stair_category_name = ''
                        stair_product = False
                        if room_line.room_id and room_line.room_id.product_category_id and room_line.room_id.product_category_id.name.upper() == 'VINYL STAIRS' and sale_order.floor_type:
                            stair_product = self.env['product.template'].search([
                                ('type', '=', 'product'),
                                ('product_variant_ids', '!=', False),
                                ('categ_id.name', 'ilike', 'Stairs'),
                                ('grade', '=', sale_order.floor_type.grade)
                            ], order='sequence asc', limit=1)
                            if stair_product:
                                stair_product_name = stair_product.name or ''
                                stair_improveit_product_id = stair_product.improveit_product_id or ''
                                stair_category_name = stair_product.categ_id and stair_product.categ_id.name or ''
                        comments = room_line.comments or ""
                        if room_line.image_comments:
                            if comments:
                                comments += ', ' + room_line.image_comments or ''
                            else:
                                comments= room_line.image_comments or ''
                        if comments:
                            comments = comments.replace('&', 'and')
                        data = {

                            "SaleID": sale_order.quote_id or '',
                            "MoldingType": room_line.molding_type_id and room_line.molding_type_id.name or "",
                            "Comments": comments
                        }
                        if stair_product:
                            data.update({
                                "ProductName": stair_product_name,
                                "ProductID": stair_improveit_product_id,
                                "Category": stair_category_name,
                            })
                            stair_count = 0
                            if room_line.custom_room_name:
                                contract_questions = self.env['team.contract.question.line'].search([
                                    ('room_name', '=', room_line.custom_room_name),
                                    ('appointment_id', '=', sale_order.appointment_id.id),
                                    ('question_id.code', '=', 'StairCount')
                                ], limit=1)
                            else:
                                contract_questions = self.env['team.contract.question.line'].search([
                                    ('room_id', '=', room_line.room_id.id),
                                    ('appointment_id', '=', sale_order.appointment_id.id),
                                    ('question_id.code', '=', 'StairCount')
                                ], limit=1)
                            if contract_questions:
                                for answer_obj in contract_questions.answers:
                                    stair_count = float(answer_obj.answer)
                            if sale_order.stair_calc_based_on == 'list_price':
                                room_cost = stair_count * stair_product.list_price
                            else:
                                room_cost = stair_count * stair_product.msrp
                        else:
                            data.update({
                                "ProductName": product_name,
                                "ProductID": improveit_product_id,
                                "Category": category_name,
                            })
                            if sale_order.calc_based_on == 'list_price':
                                room_cost = room_line.adjusted_area * sale_order.floor_type.list_price
                            else:
                                room_cost = room_line.adjusted_area * sale_order.floor_type.msrp
                        if room_line.custom_room_name:
                            contract_question_line = sale_order.contract_question_line.filtered(lambda x: x.room_name == room_line.custom_room_name)
                        else:
                            contract_question_line = sale_order.contract_question_line.filtered(lambda x: x.room_id == room_line.room_id.id)
                        for questions in contract_question_line:
                            if questions.room_id.id == room_line.room_id.id and questions.question_id.code != 'StairCount':
                                if questions.question_id.reflect_cost:
                                    reflect_cost += questions.extra_price or 0
                                if questions.amount_included and questions.question_id.code == 'LevelingSolutionSqft':
                                    leveling_solution_included = questions.amount_included
                                if questions.question_id.code == 'RemoveCurrentCovering':
                                    removal_cost = questions.extra_price or 0
                        unit_price = room_cost + reflect_cost + color_up_charge_total + molding_total_price + removal_cost
                        discounted_unit_price = unit_price
                        if discount_rate:
                            discount = unit_price*discount_rate
                            discounted_unit_price = round(unit_price - discount)
                        data.update({'Description': room_line.custom_room_name and room_line.custom_room_name or room_line.room_id.name})
                        data.update({'Taxable': True})
                        data.update({'Units': "Room"})
                        data.update({'Quantity': 1})
                        data.update({'UnitPrice': discounted_unit_price})
                        data.update({'RoomName': room_line.custom_room_name and room_line.custom_room_name or room_line.room_id.name})
                        data.update({'RoomArea': room_line.adjusted_area})
                        data.update({'Perimeter': room_line.room_perimeter})
                        data.update({'ColorUpchargeTotal': color_up_charge_total})
                        data.update({'LevelingSolutionIncluded': leveling_solution_included})
                        data.update({'RemovalCost': removal_cost})
                        attribute_value_ids = room_line.material_id.product_template_attribute_value_ids
                        material_colour = ""
                        for attribute in attribute_value_ids:
                            if attribute.attribute_id.name == 'colour':
                                material_colour = attribute.name
                        data.update({'ProductSelected': material_colour})
                        transitions = room_line.transition_line_id or []
                        count = 1
                        for transition in transitions:
                            transitions_key1 = 'Transition' + str(count)
                            transitions_value_1 = transition.name
                            transitions_key2 = 'TransitionLength' + str(count)
                            transitions_value_2 = transition.transition_width
                            transitions_key3 = 'TransitionHeight' + str(count)
                            transitions_value_3 = transition.transition_height or ''
                            data.update({
                                transitions_key1: transitions_value_1,
                                transitions_key2: transitions_value_2,
                                transitions_key3: transitions_value_3,

                            })
                            count = count + 1
                        _logger.info('Add Sale Items API Adding Room Transitions')
                        if room_line.custom_room_name:
                            contract_questions = self.env['team.contract.question.line'].search(
                                [('room_name', '=', room_line.custom_room_name), ('order_id', '=', sale_order.id)])
                        else:
                            contract_questions = self.env['team.contract.question.line'].search(
                                [('room_id', '=', room_line.room_id.id), ('order_id', '=', sale_order.id)])
                        for contract_question in contract_questions:
                            question = contract_question.question_id.code
                            answer = ""
                            for contract_question_answer in contract_question.answers:
                                if contract_question.question_id.question_type == 'numerical_box':
                                    answer = eval(contract_question_answer.answer)
                                else:
                                    answer = contract_question_answer.answer
                                if question != 'StairCoverRisers':
                                    if answer == 'Yes':
                                        answer = True
                                    elif answer == 'No':
                                        answer = False
                            data.update({question: answer})
                        headers = {
                            'Content-type': 'application/json',
                        }
                        _logger.info('Add SaleItem API Payload of sale %s: %s' %(sale_order.id, data))

                        end_point_url = configurations.token_url
                        client_token = configurations.client_token
                        if end_point_url and client_token:
                            request_url = end_point_url + 'AddSaleItem' + client_token
                        req = requests.post(request_url, data=json.dumps(data), headers=headers, timeout=TIMEOUT, verify=configurations.enable_ssl)
                        _logger.info('Add SaleItem API Response of sale %s: %s' %(sale_order.id, str(req.content)))
                        req.raise_for_status()
                        try:
                            content = req.json()
                        except IOError:
                            if req.status_code == 200:
                                return {
                                    'success': 'false',
                                    'errors': [
                                        {
                                            'message': "Sale data successfully send to the system, but response is in wrong format."
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
                        _logger.info('Add Sale Items API Response :%s' % content)
                        if content.get('success', '') == "true":
                            room_line.improveit_id = content['id'] or ''
                        if content.get('success', '') == "false":
                            return content
        except IOError:
            # error_msg = _(
            #     "Something went wrong during adding quote items in AddSaleItem")
            # raise self.env['res.config.settings'].get_config_warning(error_msg)
            pass
            _logger.error("******--------Error in add_sale_items_api---------********")
            result.update({"success": "false"})
        return result

    def set_appointment_result_api(self, status='Sold', notes={}):
        result = {
            "success": "true",
            "errors": []
        }
        try:
            configurations = self.env['team.improveit.configuration'].search(
                [('api_type', '=', 'boomi')], limit=1)
            for sale_order in self:
                _logger.info('--------Starting SetAppointmentResult API of sale %s---------'%sale_order.id)
                _logger.info('--------Appointment ID---------: %s'%(sale_order.appointment_id))
                if sale_order.appointment_id:
                    data = {
                        'AppointmentID': sale_order.appointment_id.improveit_appointment_id or '',
                        'Result': status,
                        'Amount': sale_order.amount_total or 0,
                    }
                    if notes:
                        data.update({
                            "WhatHappenedNotes": notes.get('what_happened_notes', ''),
                            "WhatsNextNotes": notes.get('whats_next_notes', ''),
                            "ResultDetail": notes.get('result_details', ''),
                            "LastPriceQuotedValue": notes.get('last_price_quoted_value', 0),
                        })
                    headers = {
                        'Content-type': 'application/json',
                    }
                    end_point_url = configurations.token_url
                    client_token = configurations.client_token
                    _logger.info('SetAppointmentResult API Response of Appointment %s :%s' %(sale_order.appointment_id.id, data))
                    if end_point_url and client_token:
                        request_url = end_point_url + 'SetAppointmentResult' + client_token
                    req = requests.post(request_url, data=json.dumps(data), headers=headers, timeout=TIMEOUT, verify=configurations.enable_ssl)
                    req.raise_for_status()
                    content = req.json()
                    _logger.info('SetAppointmentResult API Response of Appointment %s :%s' %(sale_order.appointment_id.id, content))
                    if content.get('Result', '') == "Failed":
                        result.update({
                            "success": "false",
                            "errors": [
                                {
                                    "message": content
                                }
                            ]
                        })
                    elif content.get('Result', '') == "Success":
                        sale_order.appointment_id.write({'status_updated_to_i360': True})

        except IOError:
            pass
            _logger.error("******--------Error in set_appointment_result_api---------********")
            result.update({"success": "false"})
            # error_msg = _(
            #     "Something went wrong during in SetAppointmentResult API")
            # raise self.env['res.config.settings'].get_config_warning(error_msg)
        return result

    def get_value(self, vals, field_name, field_key):
        kay_val_dict = dict(vals._fields[field_name].selection)
        for key, val in kay_val_dict.items():
            if key == field_key:
                label = val or ''
                return label



    # def submit_credit_application_to_zapier(self, vals):
    #     try:
    #         configurations = self.env['team.improveit.configuration'].search(
    #             [('api_type', '=', 'zapier'), ('section', '=', 'credit_application')], limit=1)
    #         if configurations:
    #             type_of_loan = self.get_value(vals, 'type_of_loan', vals.type_of_loan)
    #             marital_status = self.get_value(vals, 'marital_status', vals.marital_status)
    #             source_of_other_income = self.get_value(vals, 'source_of_other_income', vals.source_of_other_income)
    #             type_of_property = self.get_value(vals, 'type_of_property', vals.type_of_property)
    #             work_to_be_done = self.get_value(vals, 'work_to_be_done', vals.work_to_be_done)
    #             co_applicant_marital_status = self.get_value(vals, 'co_applicant_marital_status',
    #                                                          vals.co_applicant_marital_status)
    #             property_details = self.get_value(vals, 'property_details', vals.property_details)
    #             co_applicant_sex = self.get_value(vals, 'co_applicant_sex', vals.co_applicant_sex)
    #             sex = self.get_value(vals,'sex', vals.sex)
    #             applicant_ethnicity = self.get_value(vals,'ethnicity', vals.ethnicity)
    #             applicant_race = self.get_value(vals,'race', vals.race)
    #             co_applicant_ethnicity = self.get_value(vals,'co_applicant_ethnicity', vals.co_applicant_ethnicity)
    #             co_applicant_race = self.get_value(vals,'co_applicant_race', vals.co_applicant_race)
    #             data = {"Applicant_Amount_Financed": vals.amount_financed or 0,
    #                     "Applicant_Cell_Phone": vals.cell_phone or '',
    #                     "Applicant_Checking_Account": vals.checking_account_no or '',
    #                     "Applicant_Checking_Account_Bank": vals.name_of_bank or '',
    #                     "Applicant_Checking_Account_Bank_Phone": vals.bank_phone_number or '',
    #                     "Applicant_City": vals.city or '',
    #                     "Applicant_Current_Lender_Address": vals.lender_address or '',
    #                     "Applicant_Current_Lender_Phone": vals.lender_phone or '',
    #                     "Applicant_Current_Mortgage_Balance": vals.present_balance or 0,
    #                     "Applicant_Date_of_Birth": vals.date_of_birth.strftime('%d-%m-%Y') or "",
    #                     "Applicant_Down_Payment": vals.downpayment or 0,
    #                     "Applicant_Drivers_License/State_ID": vals.drivers_license or '',
    #                     "Applicant_Drivers_License_Expiration_Dat": vals.drivers_license_exp_date.strftime('%d-%m-%Y') or "",
    #                     "Applicant_Earning_Period": "Monthly",
    #                     "Applicant_Earnings_per_Month": vals.earnings_from_employment or 0,
    #                     "Applicant_Employer_Phone_Number": vals.employers_phone_number or '',
    #                     "Applicant_Ethnicity": applicant_ethnicity or '',
    #                     "Applicant_Home_Phone": vals.home_phone or '',
    #                     "Applicant_Home_Value": vals.present_value_of_home or 0,
    #                     "Applicant_Insurance_Agent": vals.agent or '',
    #                     "Applicant_Insurance_Agent_Phone": vals.insurance_phone_no or '',
    #                     "Applicant_Insurance_Company": vals.insurance_company or '',
    #                     "Applicant_Insurance_Coverage": vals.coverage or '',
    #                     "Applicant_Lender_Name": vals.lender_name or '',
    #                     "Applicant_Length_of_Time_at_Current_Job": vals.years_on_job or '',
    #                     "Applicant_Marital_Status": marital_status or '',
    #                     "Applicant_Monthly_Mortgage_Payment": vals.monthly_mortage_payment or 0,
    #                     "Applicant_Name": vals.applicant_first_name or '',
    #                     "Applicant_Nearest_Relative": vals.nearest_relative or '',
    #                     "Applicant_Nearest_Relative_Phone": vals.phone_number_relationship or '',
    #                     "Applicant_Nearest_Relative_Relationship": vals.relationship or '',
    #                     "Applicant_Near_Relative_Address": vals.address_relationship,
    #                     "Applicant_Occupation": vals.occupation or '',
    #                     "Applicant_Original_Mortgage_Amount": vals.original_mortage_amount or 0,
    #                     "Applicant_Original_Purchase_Price": vals.original_purchase_price or 0,
    #                     "Applicant_Other_Income_Monthly_Amount": vals.amount_monthly or 0,
    #                     "Applicant_Other_Obligations": vals.other_obligations or '',
    #                     "Applicant_Present_Employer": vals.present_employer or '',
    #                     "Applicant_Present_Employer_Address": vals.present_employers_address or '',
    #                     "Applicant_Previous_City": vals.previous_address_of_applicant_city or '',
    #                     "Applicant_Previous_Employer_Address": vals.previous_employers_address or '',
    #                     "Applicant_Previous_Employer_Occupation": vals.occupation_previous_employer or '',
    #                     "Applicant_Previous_Employer_Phone": vals.previous_employers_phone_number or '',
    #                     "Applicant_Previous_State": vals.previous_address_of_applicant_state or '',
    #                     "Applicant_Previous_Street_Address": vals.previous_address_of_applicant_street or '',
    #                     "Applicant_Previous_Years_on_the_Job": vals.years_on_job_previous_employer or '',
    #                     "Applicant_Previous_ZIP_Code": vals.previous_address_of_applicant_zip or '',
    #                     "Applicant_Property_Acquisition_Date": vals.date_aquired.strftime('%d-%m-%Y') or '',
    #                     "Applicant_Property_Address": vals.address_of_property or '',
    #                     "Applicant_Property_Details": property_details or '',
    #                     "Applicant_Property_Owners": vals.owners or '',
    #                     "Applicant_Race":applicant_race or '',
    #                     "Applicant_Second_Mortgage": vals.second_mortage or '',
    #                     "Applicant_Second_Mortgage_Amount": vals.original_amount or 0,
    #                     "Applicant_Second_Mortgage_Balance": vals.present_balance_second_mortage or 0,
    #                     "Applicant_Second_Mortgage_Lender": vals.lender_name_or_phone or '',
    #                     "Applicant_Second_Mortgage_Payment": vals.monthly_payment or 0,
    #                     "Applicant_Second_Mortgage_Phon": vals.applicant_second_mortage_phone or '',
    #                     "Applicant_Sex": sex or '',
    #                     "Applicant_Signature_Date": vals.applicant_signature_date.strftime('%d-%m-%Y') or "",
    #                     "Applicant_Source_of_Other_Income": source_of_other_income or '',
    #                     "Applicant_SSN": vals.social_security_number or '',
    #                     "Applicant_State": vals.state or '',
    #                     "Applicant_Street_Address": vals.street or '',
    #                     "Applicant_Supervisor_or_Department": vals.supervisor_or_department or '',
    #                     "Applicant_Total_Monthly_Payments": vals.total_monthly_payments or '',
    #                     "Applicant_Total_Price": vals.total_price or '',
    #                     "Applicant_Type_of_Loan": type_of_loan or '',
    #                     "Applicant_Type_of_Property": type_of_property or '',
    #                     "Applicant_Work_to_be_Done": work_to_be_done or '',
    #                     "Applicant_Years_At_Current_Address": vals.how_long or '',
    #                     "Applicant_ZIP_Code": vals.zip or '',
    #                     "Coapp_Date_of_Birth": vals.co_applicant_date_of_birth.strftime('%d-%m-%Y') or '',
    #                     "Coapp_Drivers_License_Expiration": vals.co_applicant_drivers_license_exp_date.strftime(
    #                         '%d-%m-%Y') or "",
    #                     "Coapp_Drivers_License_or_State_ID": vals.co_applicant_drivers_license or '',
    #                     "Coapplicant_Ethnicity": co_applicant_ethnicity or '',
    #                     "Coapplicant_Marital_Status": co_applicant_marital_status or '',
    #                     "Coapplicant_Race": co_applicant_race or '',
    #                     "Coapplicant_Sex": co_applicant_sex or '',
    #                     "Coapplicant_Signature_Date": vals.co_applicant_signature_date.strftime('%d-%m-%Y') or "",
    #                     "Coapp_Monthly_Earnings": vals.co_applicant_earnings_from_employment or '',
    #                     "Coapp_Name": vals.co_applicant_first_name or '',
    #                     "Coapp_Present_Employer_Address": vals.co_applicant_present_employers_address or '',
    #                     "Coapp_Present_Employer_Phone": vals.co_applicant_employers_phone_number or '',
    #                     "Coapp_Present_Occupation": vals.co_applicant_occupation or '',
    #                     "Coapp_Previous_Employer_Address": vals.co_applicant_previous_employers_address or '',
    #                     "Coapp_Previous_Employer_Monthly_Earnings": vals.co_applicant_earnings_per_month or '',
    #                     "Coapp_Previous_Employer_Occupation": vals.co_applicant_occupation_previous_employer or '',
    #                     "Coapp_Previous_Employer_Phone": vals.co_applicant_previous_employers_phone_number or '',
    #                     "Coapp_Previous_Employer_Years_on_Job": vals.co_applicant_years_on_job_previous_employer or '',
    #                     "Coapp_SSN": vals.co_applicant_social_security_number or '',
    #                     "Coapp_Years_on_Job": vals.co_applicant_how_long or 0
    #                     }
    #
    #             headers = {
    #                 'Content-type': 'application/json',
    #             }
    #             request_url = configurations.token_url
    #             req = requests.post(request_url, data=json.dumps(data), headers=headers,timeout=TIMEOUT)
    #             req.raise_for_status()
    #             content = req.json()
    #
    #     except IOError:
    #         error_msg = _(
    #             "Something went wrong while uploading credit application")
    #         raise self.env['res.config.settings'].get_config_warning(error_msg)

    # def submit_credit_application_to_boomi(self, vals):
    #     result = {
    #         "success": "true",
    #         "errors": []
    #     }
    #     try:
    #         configurations = self.env['team.improveit.configuration'].search(
    #             [('api_type', '=', 'boomi')], limit=1)
    #         if configurations:
    #             type_of_loan = self.get_value(vals, 'type_of_loan', vals.type_of_loan)
    #             marital_status = self.get_value(vals, 'marital_status', vals.marital_status)
    #             source_of_other_income = self.get_value(vals, 'source_of_other_income', vals.source_of_other_income)
    #             type_of_property = self.get_value(vals, 'type_of_property', vals.type_of_property)
    #             work_to_be_done = self.get_value(vals, 'work_to_be_done', vals.work_to_be_done)
    #             co_applicant_marital_status = self.get_value(vals, 'co_applicant_marital_status',
    #                                                          vals.co_applicant_marital_status)
    #             property_details = self.get_value(vals, 'property_details', vals.property_details)
    #             co_applicant_sex = self.get_value(vals, 'co_applicant_sex', vals.co_applicant_sex)
    #             sex = self.get_value(vals, 'sex', vals.sex)
    #             applicant_ethnicity = self.get_value(vals, 'ethnicity', vals.ethnicity)
    #             applicant_race = self.get_value(vals, 'race', vals.race)
    #             co_applicant_ethnicity = self.get_value(vals, 'co_applicant_ethnicity', vals.co_applicant_ethnicity)
    #             co_applicant_race = self.get_value(vals, 'co_applicant_race', vals.co_applicant_race)
    #             type_of_credit_requested = self.get_value(vals, 'type_of_credit_requested',
    #                                                       vals.type_of_credit_requested)
    #             applicant_state_name  = ''
    #             if vals.address_of_applicant_state:
    #                 applicant_state = self.env['res.country.state'].search([
    #                     ('country_id', '=', self.env.ref('base.us').id),
    #                     '|', ('name', '=', vals.address_of_applicant_state),
    #                     ('code', '=', vals.address_of_applicant_state),
    #                 ], limit=1)
    #                 if applicant_state:
    #                     applicant_state_name = applicant_state.name
    #
    #             data = {"ApplicantAmountFinanced": vals.amount_financed or 0,
    #                     "ApplicantCellPhone": vals.cell_phone or '',
    #                     "ApplicantCheckingAccount": vals.checking_account_no or '',
    #                     "ApplicantCheckingAccountBank": vals.name_of_bank or '',
    #                     "ApplicantCheckingAccountBankPhone": vals.bank_phone_number or '',
    #                     "ApplicantCity": vals.address_of_applicant_city or '',
    #                     "ApplicantEmail": vals.applicant_email or '',
    #                     "ApplicantCurrentLenderAddress": vals.lender_address or '',
    #                     "ApplicantCurrentLenderPhone": vals.lender_phone or '',
    #                     "ApplicantCurrentMortgageBalance": vals.present_balance or 0,
    #                     "ApplicantDateofBirth": vals.date_of_birth.strftime(
    #                         "%Y%m%d 000000.000") if vals.date_of_birth else '',
    #                     "ApplicantDownPayment": vals.downpayment or 0,
    #                     "ApplicantDriversLicense/StateID": vals.drivers_license or '',
    #                     "ApplicantDriversLicenseExpirationDat": vals.drivers_license_exp_date.strftime(
    #                         "%Y%m%d 000000.000") if vals.drivers_license_exp_date else '',
    #                     "ApplicantEarningPeriod": "Monthly",
    #                     "ApplicantEarningsperMonth": vals.earnings_from_employment or 0,
    #                     "ApplicantEmployerPhoneNumber": vals.employers_phone_number or '',
    #                     "ApplicantEthnicity": applicant_ethnicity or '',
    #                     "ApplicantHomePhone": vals.home_phone or '',
    #                     "ApplicantHomeValue": vals.present_value_of_home or 0,
    #                     "ApplicantInsuranceAgent": vals.agent or '',
    #                     "ApplicantInsuranceAgentPhone": vals.insurance_phone_no or '',
    #                     "ApplicantInsuranceCompany": vals.insurance_company or '',
    #                     "ApplicantInsuranceCoverage": vals.coverage or '',
    #                     "ApplicantLenderName": vals.lender_name or '',
    #                     "ApplicantLengthofTimeatCurrentJob": vals.years_on_job or '',
    #                     "ApplicantMaritalStatus": marital_status or '',
    #                     "ApplicantMonthlyMortgagePayment": vals.monthly_mortage_payment or 0,
    #                     "ApplicantName": (vals.applicant_last_name and '%s, '%(vals.applicant_last_name) or '') + (vals.applicant_first_name or ''),
    #                     "ApplicantNearestRelative": vals.nearest_relative or '',
    #                     "ApplicantNearestRelativePhone": vals.phone_number_relationship or '',
    #                     "ApplicantNearestRelativeRelationship": vals.relationship or '',
    #                     "ApplicantNearRelativeAddress": vals.address_relationship,
    #                     "ApplicantOccupation": vals.occupation or '',
    #                     "ApplicantOriginalMortgageAmount": vals.original_mortage_amount or 0,
    #                     "ApplicantOriginalPurchasePrice": vals.original_purchase_price or 0,
    #                     "ApplicantOtherIncomeMonthlyAmount": vals.amount_monthly or 0,
    #                     "ApplicantOtherObligations": vals.other_obligations or '',
    #                     "ApplicantPresentEmployer": vals.present_employer or '',
    #                     "ApplicantPresentEmployerAddress": vals.present_employers_address or '',
    #                     "ApplicantPreviousCity": vals.previous_address_of_applicant_city or '',
    #                     "ApplicantPreviousEmployerAddress": vals.previous_employers_address or '',
    #                     "ApplicantPreviousEmployerOccupation": vals.occupation_previous_employer or '',
    #                     "ApplicantPreviousEmployerPhone": vals.previous_employers_phone_number or '',
    #                     "ApplicantPreviousState": vals.previous_address_of_applicant_state or '',
    #                     "ApplicantPreviousStreetAddress": vals.previous_address_of_applicant or '',
    #                     "ApplicantPreviousYearsontheJob": vals.years_on_job_previous_employer or '',
    #                     "ApplicantPreviousZIPCode": vals.previous_address_of_applicant_zip or '',
    #                     "ApplicantPropertyAcquisitionDate": vals.date_aquired.strftime(
    #                         "%Y%m%d 000000.000") if vals.date_aquired else '',
    #                     "ApplicantPropertyAddress": vals.address_of_property or '',
    #                     "ApplicantPropertyDetails": property_details or '',
    #                     "ApplicantPropertyOwners": vals.owners or '',
    #                     "ApplicantRace": applicant_race or '',
    #                     "ApplicantSecondMortgage": True if vals.second_mortage == 'Yes' else False,
    #                     "ApplicantSecondMortgageAmount": vals.original_amount or 0,
    #                     "ApplicantSecondMortgageBalance": vals.present_balance_second_mortage or 0,
    #                     "ApplicantSecondMortgageLender": vals.lender_name_or_phone or '',
    #                     "ApplicantSecondMortgagePayment": vals.monthly_payment or 0,
    #                     "ApplicantSecondMortgagePhon": vals.applicant_second_mortage_phone or '',
    #                     "ApplicantSex": sex or '',
    #                     "ApplicantSignatureDate": vals.applicant_signature_date.strftime(
    #                         "%Y%m%d 000000.000") if vals.applicant_signature_date else '',
    #                     "ApplicantSourceofOtherIncome": source_of_other_income or '',
    #                     "ApplicantSSN": vals.social_security_number or '',
    #                     "ApplicantState": applicant_state_name or '',
    #                     "ApplicantStreetAddress": vals.address_of_applicant or '',
    #                     "ApplicantSupervisororDepartment": vals.supervisor_or_department or '',
    #                     "ApplicantTotalMonthlyPayments": vals.total_monthly_payments or '',
    #                     "ApplicantTotalPrice": vals.total_price or '',
    #                     "ApplicantTypeofLoan": type_of_loan or '',
    #                     "ApplicantTypeofProperty": type_of_property or '',
    #                     "ApplicantWorktobeDone": work_to_be_done or '',
    #                     "ApplicantYearsAtCurrentAddress": vals.how_long or '',
    #                     "ApplicantZIPCode": vals.address_of_applicant_zip or '',
    #                     "CoappEmail": vals.co_applicant_email or '',
    #                     "CoappPhone": vals.co_applicant_phone or '',
    #                     "CoappPresentEmployer": vals.co_applicant_present_employer or '',
    #                     "CoappDateofBirth": vals.co_applicant_date_of_birth.strftime(
    #                         "%Y%m%d 000000.000") if vals.co_applicant_date_of_birth else '',
    #                     "CoappDriversLicenseExpiration": vals.co_applicant_drivers_license_exp_date.strftime(
    #                         "%Y%m%d 000000.000") if vals.co_applicant_drivers_license_exp_date else '',
    #                     "CoappDriversLicenseorStateID": vals.co_applicant_drivers_license or '',
    #                     "CoapplicantEthnicity": co_applicant_ethnicity or '',
    #                     "CoapplicantMaritalStatus": co_applicant_marital_status or '',
    #                     "CoapplicantRace": co_applicant_race or '',
    #                     "CoapplicantSex": co_applicant_sex or '',
    #                     "CoapplicantSignatureDate": vals.co_applicant_signature_date.strftime(
    #                         "%Y%m%d 000000.000") if vals.co_applicant_signature_date else '',
    #                     "CoappMonthlyEarnings": vals.co_applicant_earnings_from_employment or 0,
    #                     "CoappName": (vals.co_applicant_last_name or vals.co_applicant_first_name) and '%s, %s'%(vals.co_applicant_last_name or '', vals.co_applicant_first_name or '') or 0,
    #                     "CoappPresentEmployerAddress": vals.co_applicant_present_employers_address or '',
    #                     "CoappPresentEmployerPhone": vals.co_applicant_employers_phone_number or '',
    #                     "CoappPresentOccupation": vals.co_applicant_occupation or '',
    #                     "CoappPreviousEmployerAddress": vals.co_applicant_previous_employers_address or '',
    #                     "CoappPreviousEmployerMonthlyEarnings": vals.co_applicant_earnings_per_month or '',
    #                     "CoappPreviousEmployerOccupation": vals.co_applicant_occupation_previous_employer or '',
    #                     "CoappPreviousEmployerPhone": vals.co_applicant_previous_employers_phone_number or '',
    #                     "CoappPreviousEmployerYearsonJob": vals.co_applicant_years_on_job_previous_employer or '',
    #                     "CoappSSN": vals.co_applicant_social_security_number or '',
    #                     "CoappYearsonJob": vals.co_applicant_years_on_job or 0,
    #                     "PermissionToText": vals.hunter_message_status and True or False,
    #                     "ApplicantRaceOther": '',
    #                     "CoapplicantRaceOther": '',
    #                     "Credit Request Type": 'Individual Credit' if type_of_credit_requested == 'Individual Credit - relying solely on my income or assets' else 'Joint Credit' if type_of_credit_requested == 'Joint Credit - We intend to apply for joint credit' else 'Individual Credit',
    #                     }
    #             if co_applicant_race == 'Other':
    #                 data.update({
    #                     "CoapplicantRaceOther": vals.co_applicant_other_race or '',
    #                 })
    #             if applicant_race == 'Other':
    #                 data.update({
    #                     "ApplicantRaceOther": vals.applicant_other_race or '',
    #                 })
    #
    #             headers = {
    #                 'Content-type': 'application/json',
    #             }
    #             end_point_url = configurations.token_url
    #             client_token = configurations.client_token
    #             _logger.info("----------AddCreditApplication------------")
    #             _logger.info('data: %s'%(json.dumps(data)))
    #             if end_point_url and client_token:
    #                 request_url = end_point_url + 'AddCreditApplication' + client_token
    #             req = requests.post(request_url, data=json.dumps(data), headers=headers, timeout=TIMEOUT)
    #             _logger.error('Add Credit Application API Response : %s' % str(req.content))
    #             req.raise_for_status()
    #             try:
    #                 content = req.json()
    #             except IOError:
    #                 if req.status_code == 200:
    #                     return {
    #                         'success': 'false',
    #                         'errors': [
    #                             {
    #                                 'message': "Loan data successfully send to the system, but response is in wrong format."
    #                             }
    #                         ]
    #                     }
    #                 else:
    #                     return {
    #                         'success': 'false',
    #                         'errors': [
    #                             {
    #                                 'message': "Wrong response format."
    #                             }
    #                         ]
    #                     }
    #             _logger.info('---AddCreditApplication Response: %s'%(content))
    #             if content.get('success', '') == "true":
    #                 vals.write({
    #                     'improveit_id': content['id'] or '',
    #                     # 'social_security_number': '',
    #                     # 'co_applicant_social_security_number': '',
    #                     # 'date_of_birth': '',
    #                     # 'co_applicant_date_of_birth': '',
    #                     # 'drivers_license': '',
    #                 })
    #             else:
    #                 return content
    #     except IOError:
    #         error_msg = _("Something went wrong while uploading credit application")
    #         raise self.env['res.config.settings'].get_config_warning(error_msg)
    #     return result

    def submit_credit_application_to_boomi(self, credit_application):
        result = {
            "success": "true",
            "errors": []
        }
        try:
            configurations = self.env['team.improveit.configuration'].search(
                [('api_type', '=', 'boomi')], limit=1)
            if configurations:
                type_of_loan = self.get_value(credit_application, 'type_of_loan', credit_application.type_of_loan)
                marital_status = self.get_value(credit_application, 'marital_status', credit_application.marital_status)
                source_of_other_income = self.get_value(credit_application, 'source_of_other_income', credit_application.source_of_other_income)
                type_of_property = self.get_value(credit_application, 'type_of_property', credit_application.type_of_property)
                work_to_be_done = self.get_value(credit_application, 'work_to_be_done', credit_application.work_to_be_done)
                co_applicant_marital_status = self.get_value(credit_application, 'co_applicant_marital_status',
                                                             credit_application.co_applicant_marital_status)
                property_details = self.get_value(credit_application, 'property_details', credit_application.property_details)
                co_applicant_sex = self.get_value(credit_application, 'co_applicant_sex', credit_application.co_applicant_sex)
                sex = self.get_value(credit_application, 'sex', credit_application.sex)
                applicant_ethnicity = self.get_value(credit_application, 'ethnicity', credit_application.ethnicity)
                applicant_race = self.get_value(credit_application, 'race', credit_application.race)
                co_applicant_ethnicity = self.get_value(credit_application, 'co_applicant_ethnicity',
                                                        credit_application.co_applicant_ethnicity)
                co_applicant_race = self.get_value(credit_application, 'co_applicant_race',
                                                   credit_application.co_applicant_race)
                type_of_credit_requested = self.get_value(credit_application, 'type_of_credit_requested',
                                                          credit_application.type_of_credit_requested)
                # additional_income = self.get_value(credit_application, 'additional_income',
                #                                    credit_application.additional_income)
                additional_income = False
                if credit_application.additional_income == 'Yes':
                    additional_income = True
                applicant_state_name  = ''
                if credit_application.address_of_applicant_state:
                    applicant_state = self.env['res.country.state'].search([
                        ('country_id', '=', self.env.ref('base.us').id),
                        '|', ('name', '=', credit_application.address_of_applicant_state),
                        ('code', '=', credit_application.address_of_applicant_state),
                    ], limit=1)
                    if applicant_state:
                        applicant_state_name = applicant_state.name

                date_of_birth = ''
                if credit_application.encrypted_date_of_birth:
                    date_of_birth = credit_application.action_decrypt_field('date_of_birth')
                social_security_number = ''
                if credit_application.encrypted_social_security_number:
                    social_security_number = credit_application.action_decrypt_field('social_security_number')
                drivers_license = ''
                if credit_application.encrypted_drivers_license:
                    drivers_license = credit_application.action_decrypt_field('drivers_license')

                co_applicant_date_of_birth = ''
                if credit_application.encrypted_co_applicant_date_of_birth:
                    co_applicant_date_of_birth = credit_application.action_decrypt_field('co_applicant_date_of_birth')
                co_applicant_social_security_number = ''
                if credit_application.encrypted_co_applicant_social_security_number:
                    co_applicant_social_security_number = credit_application.action_decrypt_field('co_applicant_social_security_number')
                co_applicant_drivers_license = ''
                if credit_application.encrypted_co_applicant_drivers_license:
                    co_applicant_drivers_license = credit_application.action_decrypt_field('co_applicant_drivers_license')

                data = {
                    "AppointmentID": credit_application.appointment_id.improveit_appointment_id or '',
                    "SaleTotalPrice": credit_application.total_price or 0,
                    "SaleDownPayment": credit_application.downpayment or 0,
                    "SaleAmountFinanced": credit_application.amount_financed or 0,
                    "ApplicantTypeofLoan": type_of_loan or '',
                    "ApplicantName": (credit_application.applicant_last_name and '%s, ' % (
                        credit_application.applicant_last_name) or '') + (
                                                 credit_application.applicant_first_name or ''),
                    "ApplicantDateofBirth": date_of_birth.strftime(
                        "%Y%m%d 000000.000") if date_of_birth else '',
                    "ApplicantSSN": social_security_number or '',
                    "ApplicantHomePhone": credit_application.home_phone or '',
                    "ApplicantStreetAddress": credit_application.address_of_applicant or '',
                    "ApplicantCity": credit_application.address_of_applicant_city or '',
                    "ApplicantCheckingRoutingNo": credit_application.checking_routing_no or '',
                    "ApplicantCheckingAccount": credit_application.checking_account_no or '',
                    "ApplicantCheckingAccountBank": credit_application.name_of_bank or '',
                    "ApplicantCheckingAccountBankPhone": credit_application.bank_phone_number or '',
                    "ApplicantState": applicant_state_name or '',
                    "ApplicantZIPCode": credit_application.address_of_applicant_zip or '',
                    "ApplicantYearsAtCurrentAddress": credit_application.how_long or '',
                    "ApplicantDriversLicense/StateID": drivers_license or '',
                    "ApplicantDriversLicenseIssueDate": credit_application.drivers_license_issue_date.strftime(
                        "%Y%m%d 000000.000") if credit_application.drivers_license_issue_date else '',
                    "ApplicantDriversLicenseExpirationDat": credit_application.drivers_license_exp_date.strftime(
                        "%Y%m%d 000000.000") if credit_application.drivers_license_exp_date else '',
                    "ApplicantEmail": credit_application.applicant_email or '',
                    "ApplicantPresentEmployer": credit_application.present_employer or '',
                    "ApplicantLengthofTimeatCurrentJob": credit_application.years_on_job or '',
                    "ApplicantOccupation": credit_application.occupation or '',
                    "ApplicantEarningsperMonth": credit_application.earnings_from_employment or 0,
                    "ApplicantRace": applicant_race or '',
                    "ApplicantSex": sex or '',
                    "ApplicantMaritalStatus": marital_status or '',
                    "ApplicantSecondMortgage": True if credit_application.second_mortage == 'Yes' else False,
                    "ApplicantSecondMortgageAmount": credit_application.original_amount or 0,
                    "ApplicantSecondMortgageBalance": credit_application.present_balance_second_mortage or 0,
                    "ApplicantSecondMortgageLender": credit_application.lender_name_or_phone or '',
                    "ApplicantSecondMortgagePayment": credit_application.monthly_payment or 0,
                    "ApplicantSecondMortgagePhon": credit_application.applicant_second_mortage_phone or '',
                    "PermissionToText": credit_application.hunter_message_status and True or False,
                    "CoappName": (credit_application.co_applicant_last_name or credit_application.co_applicant_first_name) and '%s, %s' % (
                                 credit_application.co_applicant_last_name or '',credit_application.co_applicant_first_name or '') or '',
                    "CoappDateofBirth": co_applicant_date_of_birth.strftime("%Y%m%d 000000.000") if co_applicant_date_of_birth else '',
                    "CoappSSN": co_applicant_social_security_number or '',
                    "CoappPhone": credit_application.co_applicant_phone or '',
                    "CoappDriversLicenseorStateID": co_applicant_drivers_license or '',
                    "CoapplicantDriversLicenseIssueDate": credit_application.co_applicant_drivers_license_issue_date.strftime(
                        "%Y%m%d 000000.000") if credit_application.co_applicant_drivers_license_issue_date else '',
                    "CoappDriversLicenseExpiration": credit_application.co_applicant_drivers_license_exp_date.strftime(
                        "%Y%m%d 000000.000") if credit_application.co_applicant_drivers_license_exp_date else '',
                    "CoappEmail": credit_application.co_applicant_email or '',
                    "CoappPresentEmployer": credit_application.co_applicant_present_employer or '',
                    "CoappYearsonJob": credit_application.co_applicant_years_on_job or 0,
                    "CoappPresentOccupation": credit_application.co_applicant_occupation or '',
                    "CoappMonthlyEarnings": credit_application.co_applicant_earnings_from_employment or 0,
                    "CoapplicantRace": co_applicant_race or '',
                    "CoapplicantSex": co_applicant_sex or '',
                    "CoapplicantMaritalStatus": co_applicant_marital_status or '',
                    "ApplicantAdditionalIncome": additional_income or False,
                    "ApplicantAdditionalIncomeSource": source_of_other_income or '',
                    "ApplicantMonthlyEarnings": credit_application.additional_monthly_income or 0,
                    "ApplicantNearestRelative": credit_application.nearest_relative or '',
                    "ApplicantNearestRelativeRelationship": credit_application.relationship or '',
                    "ApplicantNearestRelativePhone": credit_application.phone_number_relationship or '',
                    "ApplicantOriginalPurchasePrice": credit_application.original_purchase_price or 0,
                    "ApplicantMortgageCompany": credit_application.applicant_mortgage_company or '',
                    "ApplicantOriginalMortgageAmount": credit_application.original_mortage_amount or 0,
                    "ApplicantPropertyAddress": credit_application.address_of_property or '',
                    "ApplicantTypeofProperty": type_of_property or '',
                    "ApplicantHomeValue": credit_application.present_value_of_home or 0,
                    "ApplicantCurrentMortgageBalance": credit_application.present_balance or 0,
                    "ApplicantMonthlyMortgagePayment": credit_application.monthly_mortage_payment or 0,
                }
                if co_applicant_race == 'Other':
                    data.update({
                        "CoapplicantRaceOther": credit_application.co_applicant_other_race or '',
                    })
                if applicant_race == 'Other':
                    data.update({
                        "ApplicantRaceOther": credit_application.applicant_other_race or '',
                    })

                headers = {
                    'Content-type': 'application/json',
                }
                end_point_url = configurations.token_url
                client_token = configurations.client_token
                _logger.info("----------AddCreditApplication Input Payload of Appointment %s : %s"%(credit_application.appointment_id.id, data))
                if end_point_url and client_token:
                    request_url = end_point_url + 'AddCreditApplication' + client_token
                req = requests.post(request_url, data=json.dumps(data), headers=headers, timeout=TIMEOUT, verify=configurations.enable_ssl)
                _logger.info('Add Credit Application API Response of Appointment %s : %s'%(credit_application.appointment_id.id, str(req.content)))
                req.raise_for_status()
                try:
                    content = req.json()
                except IOError:
                    if req.status_code == 200:
                        return {
                            'success': 'false',
                            'errors': [
                                {
                                    'message': "Loan data successfully send to the system, but response is in wrong format."
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
                _logger.info('---AddCreditApplication Response of Appointment %s : %s'%(credit_application.appointment_id.id, content))
                if content.get('success', '') == "true":
                    credit_application.write({
                        'improveit_id': content['id'] or '',
                        # 'social_security_number': '',
                        # 'co_applicant_social_security_number': '',
                        # 'date_of_birth': '',
                        # 'co_applicant_date_of_birth': '',
                        # 'drivers_license': '',
                    })
                else:
                    return content
        except IOError:
            error_msg = _("Something went wrong while uploading credit application")
            raise self.env['res.config.settings'].get_config_warning(error_msg)
        return result

    def create_project_in_i360(self, selected_installation):
        result = {
            "success": "true",
            "errors": []
        }
        try:
            configurations = self.env['team.improveit.configuration'].search(
                [('api_type', '=', 'boomi')], limit=1)
            for sale_order in self:
                _logger.info('--------Starting CreateProject API of Appointment ID---------: %s' % (sale_order.appointment_id.id))
                if sale_order.appointment_id:
                    data = {
                        'SaleId': sale_order.quote_id or '',
                        'StartDate': selected_installation.start_date.strftime(DEFAULT_SERVER_DATE_FORMAT),
                        'AssignedTo': selected_installation.crew_id.improveit_id,
                    }
                    headers = {
                        'Content-type': 'application/json',
                    }
                    end_point_url = configurations.token_url
                    client_token = configurations.client_token
                    _logger.info('CreateProject API Input of Appointment %s :%s' % (sale_order.appointment_id.id, data))
                    if end_point_url and client_token:
                        request_url = end_point_url + 'CreateProject' + client_token
                    req = requests.post(request_url, data=json.dumps(data), headers=headers, timeout=TIMEOUT,
                                        verify=configurations.enable_ssl)
                    req.raise_for_status()
                    content = req.json()
                    _logger.info('CreateProject API Response of Appointment %s :%s' % (sale_order.appointment_id.id, content))
                    if content.get('success', '') == "true":
                        selected_installation.write({
                            'project_i360_id': content['id'] or '',
                        })
                        if content.get('duplicate', '') == "true":
                            result.update({
                                "duplicate": "true"
                            })
                    if content.get('success', '') == "false":
                        return content
                    elif "Errors" in content:
                        return content.get('Errors', {})

        except IOError:
            pass
            _logger.error("******--------Error in create_project_in_i360 API---------********")
            result.update({"success": "false"})
        return result

    def create_project_activity_in_i360(self, selected_installation):
        result = {
            "success": "true",
            "errors": []
        }
        try:
            configurations = self.env['team.improveit.configuration'].search(
                [('api_type', '=', 'boomi')], limit=1)
            for sale_order in self:
                _logger.info('--------Starting CreateProjectActivity API Appointment ID---------: %s' % (sale_order.appointment_id.id))
                if selected_installation.project_i360_id:
                    data = {
                        "ProjectId": selected_installation.project_i360_id or '',
                        "Name": "IHS-Install-%s"%(sale_order.appointment_id.applicant_last_name),
                        "StartDate": selected_installation.start_date.strftime('%Y-%m-%dT%H:%M:%S'),
                        "Enddate": selected_installation.end_date.strftime('%Y-%m-%dT%H:%M:%S'),
                        "AssignedTo": selected_installation.crew_id.improveit_id,
                        "Comments": "Submitted On: %s"%(self.get_date_with_tz(fields.Datetime.now()).strftime('%Y-%m-%dT%H:%M:%S'))
                    }
                    headers = {
                        'Content-type': 'application/json',
                    }
                    end_point_url = configurations.token_url
                    client_token = configurations.client_token
                    _logger.info('CreateProjectActivity Data of Appointment %s :%s' % (sale_order.appointment_id.id, data))
                    if end_point_url and client_token:
                        request_url = end_point_url + 'CreateProjectActivity' + client_token
                    req = requests.post(request_url, data=json.dumps(data), headers=headers, timeout=TIMEOUT,
                                        verify=configurations.enable_ssl)
                    req.raise_for_status()
                    content = req.json()
                    _logger.info('CreateProjectActivity API Response of Appointment %s :%s' % (sale_order.appointment_id.id, content))
                    if content.get('success', '') == "true":
                        selected_installation.write({
                            'project_activity_i360_id': content['id'] or '',
                        })
                        if content.get('duplicate', '') == "true":
                            result.update({
                                "duplicate": "true"
                            })
                    if content.get('success', '') == "false":
                        return content
                    elif "Errors" in content:
                        return content.get('Errors', {})
        except IOError:
            pass
            _logger.info("******--------Error in create_project_activity_in_i360 API---------********")
            result.update({"success": "false"})
        return result

    def create_additional_comments_in_i360(self):
        result = {
            "success": "true",
            "errors": []
        }
        try:
            configurations = self.env['team.improveit.configuration'].search(
                [('api_type', '=', 'boomi')], limit=1)
            for sale_order in self:
                appointment = sale_order.appointment_id
                _logger.info('--------Starting AddSaleComments API Appointment ID---------: %s' % (sale_order.appointment_id.id))
                if sale_order.quote_id and appointment:
                    data = {
                        'Id': sale_order.quote_id or '',
                        'AdditionalComments': appointment.additional_comments or "",
                        "FlexibleInstall": appointment.flexible_installation and "true" or "false"
                    }
                    headers = {
                        'Content-type': 'application/json',
                    }
                    end_point_url = configurations.token_url
                    client_token = configurations.client_token
                    _logger.info('AddSaleComments API Input of Appointment %s :%s' % (appointment.id, data))
                    if end_point_url and client_token:
                        request_url = end_point_url + 'AddSaleComments' + client_token
                    req = requests.post(request_url, data=json.dumps(data), headers=headers, timeout=TIMEOUT,
                                        verify=configurations.enable_ssl)
                    req.raise_for_status()
                    content = req.json()
                    _logger.info('AddSaleComments API Response of Appointment %s :%s' % (appointment.id, content))
                    if content.get('success', '') == "true":
                        sale_order.write({
                            'additional_comment_synced': True,
                        })
                    if content.get('success', '') == "false":
                        return content
                    elif "Errors" in content:
                        return content.get('Errors', {})

        except IOError:
            pass
            _logger.error("******--------Error in create_additional_comments_in_i360 API---------********")
            result.update({"success": "false"})
        return result

    def action_sync_ext_loan_data_to_i360(self, ext_credit_application):
        result = {
            "success": "true",
            "errors": []
        }
        try:
            configurations = self.env['team.improveit.configuration'].search(
                [('api_type', '=', 'boomi')], limit=1)
            for sale_order in self:
                appointment = sale_order.appointment_id
                _logger.info('--------Starting SyncLoanData API of Appointment ID---------: %s' % (sale_order.appointment_id.id))
                if sale_order.quote_id and appointment:
                    data = {
                        'Id': sale_order.quote_id or '',
                        'Provider': ext_credit_application.provider or "",
                        "ProviderRefNumber": ext_credit_application.provider_reference or "",
                        "ApprovedAmount": ext_credit_application.approved_amount or 0
                    }
                    headers = {
                        'Content-type': 'application/json',
                    }
                    end_point_url = configurations.token_url
                    client_token = configurations.client_token
                    _logger.info('SyncLoanData API Payload of Appointment %s :%s' % (appointment.id, data))
                    if end_point_url and client_token:
                        request_url = end_point_url + 'SyncLoanData' + client_token
                    req = requests.post(request_url, data=json.dumps(data), headers=headers, timeout=TIMEOUT,
                                        verify=configurations.enable_ssl)
                    req.raise_for_status()
                    content = req.json()
                    _logger.info('SyncLoanData API Response of Appointment %s :%s' % (appointment.id, content))
                    if content.get('success', '') == "true":
                        ext_credit_application.write({
                            'improveit_id': content.get('id', ''),
                        })
                    if content.get('success', '') == "false":
                        return content
                    elif "Errors" in content:
                        return content.get('Errors', {})

        except IOError:
            pass
            _logger.error("******--------Error in action_sync_ext_loan_data_to_i360 API---------********")
            result.update({"success": "false"})
        return result

class Followers(models.Model):
    _inherit = 'mail.followers'

    @api.model
    def create(self, vals):
        if 'res_model' in vals and 'res_id' in vals and 'partner_id' in vals:
            dups = self.env['mail.followers'].sudo().search([('res_model', '=',vals.get('res_model')),
                                           ('res_id', '=', vals.get('res_id')),
                                           ('partner_id', '=', vals.get('partner_id'))])
            if len(dups):
                for p in dups:
                    p.unlink()
        res = super(Followers, self).create(vals)
        return res


class CardTransactionLog(models.Model):
    _name = 'otl.card.transaction.log'
    _description = 'Credit Card Transaction Log'

    name = fields.Char('Transaction ID')
    sale_order_id = fields.Many2one('sale.order', 'Sale Order Ref', required=True, ondelete='cascade')
    appointment_id = fields.Many2one('team.customer.appointment', string='Appointment', related='sale_order_id.appointment_id', store=True)
    state = fields.Selection([('success', 'Success'), ('failed', 'Failed')],
                             string='Status', default='success', required=True)
    message = fields.Text('Message')
    error_code = fields.Char('Error Code')
    type = fields.Selection([('authorize', 'Authorize'), ('capture', 'Capture'), ('authcapture', 'AuthCapture')],
                            string='Process Type', default='capture')
    date = fields.Datetime('Transaction Time', default=fields.Datetime.now)
    synced = fields.Boolean('Synced to i360', default=False)
    void_transaction = fields.Boolean('Is Void Transaction?', default=False)
    void_transaction_id = fields.Char('Void Transaction ID')


class DiscountHistoryLine(models.Model):
    _name = 'otl.discount.history.line'
    _description = 'Progressive Discount History'

    order_id = fields.Many2one('sale.order', string='Sale Order', ondelete='cascade')
    name = fields.Char('Value Applied')
    discount_amount = fields.Float('Discount Amount')
    sale_price = fields.Float('Sale Price After Disc')
    actual_price = fields.Float('Sale Price Before Disc')
    promo_type = fields.Boolean('Promo Code', default=False)
    type = fields.Selection([('amount', 'Amount'), ('percentage', 'Percentage')], string='Discount Type', default='amount')
    excluded_amount_discount = fields.Float('Excluded Amount From Discount')


class AvailableInstallationLine(models.Model):
    _name = 'otl.available.installation.line'
    _description = 'Available Installation Dates'
    _order = 'start_date'

    order_id = fields.Many2one('sale.order', string='Sale Order', ondelete='cascade')
    start_date = fields.Datetime('Start Date')
    end_date = fields.Datetime('End Date')
    crew_id = fields.Many2one('otl.installation.crew', string='Crew')
    selected = fields.Boolean('Selected Date', default=False)
    project_i360_id = fields.Char('I360 Project ID')
    project_activity_i360_id = fields.Char('I360 Project Activity ID')



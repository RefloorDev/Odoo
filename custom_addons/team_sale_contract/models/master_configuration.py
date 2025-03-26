# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields, api, _
from datetime import datetime
from odoo.osv import expression
from odoo.exceptions import ValidationError
from odoo.addons.resource.models.resource import float_to_time
import pytz
from google.oauth2 import service_account
from google.cloud import storage
from dateutil.relativedelta import relativedelta
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT, DEFAULT_SERVER_DATETIME_FORMAT
import os

import logging


_logger = logging.getLogger(__name__)


class AppointmentResult(models.Model):
    _name = 'appointment.result'
    _description = "Appointment Result"
    _rec_name = 'result'

    active = fields.Boolean('Active', default=True)
    result = fields.Char(string="Appointment Result")
    last_available_screen = fields.Char('Last Available Screen')


class FloorMolding(models.Model):
    _name = 'team.floor.molding'
    _description = "Floor Molding"
    _order = 'sequence asc'

    name = fields.Char(string="Molding Type")
    sequence = fields.Integer('Priority',
                              help="Give to the more specialized category, a higher priority to have them in top of the list.")
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)
    active = fields.Boolean('Active', default=True)
    unit_price = fields.Float(string="Unit Price", default=0.0)
    default_delivery = fields.Char('Default Delivery')
    delivery_option_line = fields.One2many('otl.delivery.option.line', 'molding_type_id', string='Delivery Options')


class DeliveryOptionLine(models.Model):
    _name = 'otl.delivery.option.line'
    _description = 'Delivery Options'

    name = fields.Char('Delivery Options', required=True)
    molding_type_id = fields.Many2one('team.floor.molding', 'Molding Type', ondelete='cascade')



class ResCompany(models.Model):
    _inherit = 'res.company'

    default_image = fields.Binary(attachment=True)
    recision_date = fields.Date('Recision Date')
    material_image_attachment_id = fields.Many2one('ir.attachment', 'Default Material Image Attachment')
    material_image = fields.Binary('Default Material Image', related='material_image_attachment_id.datas')
    sales_app_attachment_id = fields.Many2one('ir.attachment', 'SalesApp Logo Attachment')
    sales_app_logo = fields.Binary('SalesApp Logo', related='sales_app_attachment_id.datas')
    contract_logo_attachment_id = fields.Many2one('ir.attachment', 'Contract Document Logo Attachment')
    contract_logo = fields.Binary('Contract Document Logo', related='contract_logo_attachment_id.datas')
    login_logo_attachment_id = fields.Many2one('ir.attachment', 'Login Logo Attachment')
    login_logo = fields.Binary('Login Logo', related='login_logo_attachment_id.datas')
    promo_image_attachment_id = fields.Many2one('ir.attachment', 'Default Promo Image Attachment')
    promo_image = fields.Binary('Default Promo Image', related='promo_image_attachment_id.datas')
    enable_auto_logout = fields.Boolean('Enable Auto Logout', default=False)
    auto_logout_time = fields.Float('Auto Logout Time (24 Hours Format)', help="Enter time in 24 Hrs format")
    logged_in_notify_user_ids = fields.Many2many('res.users', 'logged_in_notify_user_rel', 'company_id', 'user_id', string="Users to Notify")
    attachment_delete_day_limit = fields.Integer('Day limit for Deleting Old Attachments', default= 0)
    versatile_user_id = fields.Many2one('res.users', string="Versatile User")
    versatile_url = fields.Char("Versatile URL")
    versatile_api_key = fields.Char("Versatile API Key")
    versatile_entity_key = fields.Char("Versatile Entity Key")
    external_application_line = fields.One2many('otl.external.application.credentials', 'company_id', string="External Application Credentials")
    pending_order_sync_notify_limit = fields.Integer("Day Limit for Notify Pending Order to Sync")



    @api.onchange('auto_logout_time')
    def onchange_auto_logout_time(self):
        result = {}
        for record in self:
            if record.auto_logout_time and (record.auto_logout_time < 0.0 or record.auto_logout_time >=24.0):
                result['warning'] = {
                    'title': _('Warning'),
                    'message': _('Please enter a valid time.')
                }
                record.auto_logout_time = 0
            cron = self.env.ref('team_api_connection.ir_cron_clear_user_tokens')
            if cron and cron.exists() and record.auto_logout_time:
                auto_logout_time = str(float_to_time(record.auto_logout_time))
                user = self.env.user
                tz = user.tz and pytz.timezone(user.tz) or pytz.utc
                current_time = fields.Datetime.now().replace(tzinfo=pytz.utc)
                hour, minute, seconds = auto_logout_time.split(':')
                auto_logout_date = current_time.replace(hour=int(hour), minute=int(minute), second=int(seconds), tzinfo=None)
                auto_logout_date_local = tz.localize(auto_logout_date).astimezone(pytz.utc)
                if current_time >  auto_logout_date_local:
                    auto_logout_date_local = auto_logout_date_local + relativedelta(days=1)
                cron.write({'nextcall': auto_logout_date_local.strftime(DEFAULT_SERVER_DATETIME_FORMAT)})
        return result

    @api.model
    def cron_delete_ild_attachments(self):
        current_date = fields.Date.today()
        for company in self.search([('attachment_delete_day_limit', '>', 0)]):
            date_delete_appointment = current_date - relativedelta(days=company.attachment_delete_day_limit)
            appointments = self.env['team.customer.appointment'].search([
                ('appointment_date', '<=', date_delete_appointment),
                ('state', '=', 'done'),
            ])
            count = 1
            for appointment in appointments:
                _logger.info('Start Processiing Appointment: %s, %s/%s'%(appointment.id,count, len(appointments)))
                count +=1
                if appointment.attachment_ids:
                    appointment.attachment_ids.unlink()
                if appointment.applicant_signature_id:
                    appointment.applicant_signature_id.unlink()
                if appointment.applicant_initial_id:
                    appointment.applicant_initial_id.unlink()
                if appointment.co_applicant_signature_id:
                    appointment.co_applicant_signature_id.unlink()
                if appointment.co_applicant_initial_id:
                    appointment.co_applicant_initial_id.unlink()
                sale_orders = appointment.sale_order_ids
                credit_applications = self.env['team.credit.application'].search([('appointment_id', '=', appointment.id)])
                for credit_application in credit_applications:
                    if credit_application.attachment_id:
                        credit_application.attachment_id.unlink()
                for order in sale_orders:
                    if order.contract_doc_attachment_id:
                        order.contract_doc_attachment_id.unlink()
                    for room_measure in order.room_measurement_line:
                        if room_measure.attachment_ids:
                            room_measure.attachment_ids.unlink()
                        if room_measure.protrusion_image_ids:
                            room_measure.protrusion_image_ids.unlink()
                        if room_measure.shape_image_id:
                            room_measure.shape_image_id.unlink()
            self.env['ir.autovacuum'].sudo().power_on()

    def get_attachment_file_path(self, attachment_id):
        file_path = ''
        attachment = self.env['ir.attachment'].browse(int(attachment_id))
        if attachment and attachment.store_fname:
            file_path = attachment._full_path(attachment.store_fname)
        return file_path

    def action_upload_file_to_cloud_storage(self, attachment, bucket, destination_blob_name):
        source_file_path = self.get_attachment_file_path(attachment.id)
        _logger.info('Source File %s'%(source_file_path))
        if source_file_path and os.path.exists(source_file_path):
            _logger.info('Cloud File Upload starting: %s' % (source_file_path))
            blob = bucket.blob(destination_blob_name)
            blob.upload_from_filename(source_file_path)
            blob.make_public()
            url = blob.public_url
            if url:
                attachment.write({
                    'datas': False,
                    'type': 'url',
                    'url': url
                })
            attachment._file_delete(source_file_path)
        return True

    @api.model
    def cron_upload_attachments_to_cloud_storage(self):
        google_auth_attachment_id = self.env['ir.config_parameter'].sudo().get_param(
                    'google_auth_attachment_id') or False
        google_bucket_name = self.env['ir.config_parameter'].sudo().get_param(
                    'google_bucket_name') or ''
        signature_path = '{date}/{appointment}/Sign'
        snapshot_path = '{date}/{appointment}/Snapshot'
        document_path = '{date}/{appointment}/Documents'
        room_path = '{date}/{appointment}/Rooms/{room_name}/Images'
        room_measurement_path = '{date}/{appointment}/Rooms/{room_name}/Measurements'
        room_anomaly_path = '{date}/{appointment}/Rooms/{room_name}/Anomaly'
        if google_auth_attachment_id:
            google_auth_file_path = self.get_attachment_file_path(google_auth_attachment_id)
            if google_auth_file_path:
                credentials = service_account.Credentials.from_service_account_file(google_auth_file_path)
                storage_client = storage.Client(credentials=credentials)

                # Get the bucket
                bucket = storage_client.bucket(google_bucket_name)
                for company in self.search([]):
                    orders = self.env['sale.order'].search([
                        ('synced_to_cloud_storage', '=', False),
                        ('is_data_upload_completed', '=', True),
                        ('company_id', '=', company.id)
                    ])
                    for order in orders:
                        appointment = order.appointment_id or False
                        if appointment:
                            appointment_date = appointment.appointment_date.strftime('%d%b%Y')
                            appointment_name = appointment.improveit_appointment_id or appointment.name
                            _logger.info('Start Processing Cloud Upload. Appointment:%s, Sale Order: %s'%(appointment_name, order.name))
                            for attachment in appointment.attachment_ids:
                                destination_blob_name = snapshot_path.format(date=appointment_date, appointment=appointment_name) + '/%s'%attachment.name
                                self.action_upload_file_to_cloud_storage(attachment, bucket, destination_blob_name=destination_blob_name)
                            if appointment.applicant_signature_id:
                                destination_blob_name = signature_path.format(date=appointment_date,
                                                                             appointment=appointment_name) + '/%s' % appointment.applicant_signature_id.name
                                self.action_upload_file_to_cloud_storage(appointment.applicant_signature_id, bucket,
                                                                         destination_blob_name=destination_blob_name)
                            if appointment.applicant_initial_id:
                                destination_blob_name = signature_path.format(date=appointment_date,
                                                                             appointment=appointment_name) + '/%s' % appointment.applicant_initial_id.name
                                self.action_upload_file_to_cloud_storage(appointment.applicant_initial_id, bucket,
                                                                         destination_blob_name=destination_blob_name)
                            if appointment.co_applicant_signature_id:
                                destination_blob_name = signature_path.format(date=appointment_date,
                                                                             appointment=appointment_name) + '/%s' % appointment.co_applicant_signature_id.name
                                self.action_upload_file_to_cloud_storage(appointment.co_applicant_signature_id, bucket,
                                                                         destination_blob_name=destination_blob_name)
                            if appointment.co_applicant_initial_id:
                                destination_blob_name = signature_path.format(date=appointment_date,
                                                                             appointment=appointment_name) + '/%s' % appointment.co_applicant_initial_id.name
                                self.action_upload_file_to_cloud_storage(appointment.co_applicant_initial_id, bucket,
                                                                        destination_blob_name=destination_blob_name)
                            credit_applications = self.env['team.credit.application'].search(
                                [('appointment_id', '=', appointment.id)])
                            for credit_application in credit_applications:
                                if credit_application.attachment_id:
                                    destination_blob_name = document_path.format(date=appointment_date,
                                                                                  appointment=appointment_name) + '/%s' % credit_application.attachment_id.name
                                    self.action_upload_file_to_cloud_storage(credit_application.attachment_id,
                                                                             bucket,
                                                                             destination_blob_name=destination_blob_name)
                            if order.contract_doc_attachment_id:
                                _logger.info('Starting Contract Document Cloud Upload. Appointment:%s, Sale Order: %s' % (appointment_name, order.name))
                                destination_blob_name = document_path.format(date=appointment_date,
                                                                             appointment=appointment_name) + '/%s' % order.contract_doc_attachment_id.name
                                self.action_upload_file_to_cloud_storage(order.contract_doc_attachment_id,
                                                                         bucket,
                                                                         destination_blob_name=destination_blob_name)
                            for room_measure in order.room_measurement_line:
                                room_name = room_measure.custom_room_name and room_measure.custom_room_name or room_measure.room_id.name
                                room_name = room_name.replace(' ', '')
                                _logger.info(
                                    'Starting Room %s Cloud Upload. Appointment:%s, Sale Order: %s' % (
                                    room_name, appointment_name, order.name))
                                if room_measure.attachment_ids:
                                    for attachment in room_measure.attachment_ids:
                                        destination_blob_name = room_path.format(date=appointment_date, room_name= room_name,
                                                                                     appointment=appointment_name) + '/%s' % attachment.name
                                        self.action_upload_file_to_cloud_storage(attachment, bucket,
                                                                                 destination_blob_name=destination_blob_name)

                                if room_measure.protrusion_image_ids:
                                    for attachment in room_measure.protrusion_image_ids:
                                        destination_blob_name = room_anomaly_path.format(date=appointment_date,
                                                                                         room_name=room_name,
                                                                                         appointment=appointment_name) + '/%s' % attachment.name
                                        self.action_upload_file_to_cloud_storage(attachment, bucket,
                                                                                 destination_blob_name=destination_blob_name)
                                if room_measure.shape_image_id:
                                    destination_blob_name = room_measurement_path.format(date=appointment_date, room_name=room_name,
                                                                             appointment=appointment_name) + '/%s' % room_measure.shape_image_id.name
                                    self.action_upload_file_to_cloud_storage(room_measure.shape_image_id, bucket,
                                                                             destination_blob_name=destination_blob_name)
                        order.write({'synced_to_cloud_storage': True})
                        _logger.info('Completed Processing Cloud Upload. Appointment:%s, Sale Order: %s'%(appointment_name, order.name))
        self.env['ir.autovacuum'].sudo().power_on()
        return True


class ExternalApplicationCredentials(models.Model):
    _name = 'otl.external.application.credentials'
    _description = 'External Application Credentials'

    name = fields.Char("Reference")
    user_id = fields.Many2one('res.users', string="User")
    company_id = fields.Many2one('res.company', string="Company")
    url = fields.Char("URL")
    api_key = fields.Char("API Key")
    entity_key = fields.Char("Entity Key")
    provider = fields.Selection([('versatile', 'Versatile'), ('hunter', 'Hunter')], string='Provider',
                                        default='versatile', required=True)
    location_based = fields.Boolean("Location Based Entity Key",default=False)
    location_entity_line = fields.One2many('otl.location.entity.key.line', 'external_application_id', string="Location Based Entity Key")

    def action_generate_versatile_user_token(self):
        for record in self:
            if record.user_id:
                action = self.env.ref('team_sale_contract.action_generate_token').read()[0]
                action['context'] = {
                    "default_user_id": record.user_id.id,
                    "default_token": record.user_id.token_name or "",
                }
                return action


class LocationEntityKeyLine(models.Model):
    _name = 'otl.location.entity.key.line'
    _description = 'Location Based Entity Key'

    external_application_id = fields.Many2one('otl.external.application.credentials', string='External Application', ondelete='cascade')
    office_location_id = fields.Many2one('otl.office.location', string='Location')
    entity_key = fields.Char("Entity Key")


class FloorColor(models.Model):
    _name = 'floor.color'

    name = fields.Char('Name')
    product_line = fields.Char('Product Line')
    thumb_nail = fields.Char('Thumb Nail')
    url = fields.Char('URL')


class TeamRoomRoom(models.Model):
    _name = 'team.room.room'
    _description = "Room Types"
    _order = 'sequence asc'

    name = fields.Char('Room Name')
    image = fields.Binary('Image')
    active = fields.Boolean('Active', default=True)
    is_custom = fields.Boolean('Custom Room')
    note = fields.Text('Internal Notes')
    sequence = fields.Integer('Priority',
                              help="Give to the more specialized category, a higher priority to have them in top of the list.")
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)
    product_category_id = fields.Many2one('product.category', 'Product Category')

    _sql_constraints = [
        ('name_company_uniq', 'unique (name,company_id)', 'The name of room must be unique per company!')
    ]


class TeamFloorLevel(models.Model):
    _name = 'team.floor.level'
    _description = "Floor Level"
    _rec_name = 'complete_name'
    _order = 'sequence asc'

    @api.depends('name', 'prefix', 'superscript_symbol')
    def _compute_complete_name(self):
        for level in self:
            prefix = ''
            if level.prefix:
                prefix = ('%s%s ' % (level.prefix, level.superscript_symbol))
            level.complete_name = ('%s%s' % (prefix, level.name))

    name = fields.Char('Floor Level', required=True)
    prefix = fields.Char('Prefix')
    image = fields.Binary('Image')
    active = fields.Boolean('Active', default=True)
    note = fields.Text('Internal Notes')
    superscript_symbol = fields.Char('Superscript Symbol')
    complete_name = fields.Char(
        'Complete Name', compute='_compute_complete_name',
        store=True)
    sequence = fields.Integer('Priority',
                              help="Give to the more specialized category, a higher priority to have them in top of the list.")
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)

    _sql_constraints = [
        (
        'name_company_uniq', 'unique (complete_name,company_id)', 'The name of floor level must be unique per company!')
    ]


class TeamFloorShape(models.Model):
    _name = 'team.floor.shape'
    _description = "Floor Shapes"
    _order = 'sequence asc'

    name = fields.Char('Shape Name')
    active = fields.Boolean('Active', default=True)
    shape = fields.Binary('Image')
    note = fields.Text('Internal Notes')
    sequence = fields.Integer('Priority',
                              help="Give to the more specialized category, a higher priority to have them in top of the list.")
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)

    _sql_constraints = [
        ('name_company_uniq', 'unique (name,company_id)', 'The name of floor shape must be unique per company!')
    ]


class TeamRoomTransition(models.Model):
    _name = 'team.room.transition'
    _description = "Transition Types"
    _order = 'sequence asc'

    name = fields.Char(' Transition Name')
    active = fields.Boolean('Active', default=True)
    description = fields.Text('Description')
    sequence = fields.Integer('Priority',
                              help="Give to the more specialized category, a higher priority to have them in top of the list.")
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)

    _sql_constraints = [
        ('name_company_uniq', 'unique (name,company_id)', 'The name of transition must be unique per company!')
    ]


class DownPaymentOption(models.Model):
    _name = 'team.downpayment.option'
    _description = "Down Payment Option"

    name = fields.Char('Title', required=True)
    description = fields.Text('Subtitle', required=True)
    active = fields.Boolean('Active', default=True)
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)
    interest_rate = fields.Float('Interest Rate')
    down_payment = fields.Char('Down_Payment__c')
    final_payment = fields.Char('Final_Payment__c')
    payment_factor = fields.Char('Payment_Factor__c')
    secondary_payment_factor = fields.Char('Secondary_Payment_Factor__c')
    balance_due = fields.Char('Balance_Due__c')
    sequence = fields.Float(string="Display_Order__c")
    payment_info = fields.Text('Payment_Info__c')
    down_payment_message = fields.Char('Down Payment Message')
    start_date = fields.Date("Start Date")
    end_date = fields.Date("End Date")


class TeamMonthlyPromo(models.Model):
    _name = 'team.monthly.promo'
    _description = "Discount Codes"
    _rec_name = 'name'

    active = fields.Boolean('Active', default=True)
    code = fields.Char('Code')
    name = fields.Char('Display Name')
    amount = fields.Char('Amount')
    type = fields.Char('Type')
    attachment_id = fields.Many2one('ir.attachment', 'Promo Image Attachment')
    image = fields.Binary('Promo Image', related='attachment_id.datas')
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)


class DownPaymentMethod(models.Model):
    _name = 'team.downpayment.method'
    _description = "Down Payment Method"

    name = fields.Char('Name', required=True)
    active = fields.Boolean('Active', default=True)
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)


class PaymentDownPayment(models.Model):
    _name = 'team.payment.percentage'
    _description = "Down Payment Percentage"

    name = fields.Char(strinng='Name', required=True)
    percentage = fields.Float(string="Percentage", required=True)


class TeamPaymentPlan(models.Model):
    _name = 'team.payment.plan'
    _description = 'Payment Plans'
    _order = 'sequence asc'

    name = fields.Char('Payment Plan Name')
    active = fields.Boolean('Active', default=True)
    description = fields.Text('Description')
    sequence = fields.Integer('Priority',
                              help="Give to the more specialized category, a higher priority to have them in top of the list.")
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)

    _sql_constraints = [
        ('name_company_uniq', 'unique (name,company_id)', 'The name of payment plan must be unique per company!')
    ]


class TeamMaterialList(models.Model):
    _name = 'team.material.list'
    _description = "Material Lists"
    _order = 'sequence asc'

    name = fields.Char('Material Name')
    active = fields.Boolean('Active', default=True)
    material_type = fields.Selection([
        ('single', 'Single'),
        ('multi', 'Multi')
    ], string="Type", required=True)
    image = fields.Binary('Image')
    cost = fields.Float('Cost')
    sequence = fields.Integer('Priority',
                              help="Give to the more specialized category, a higher priority to have them in top of the list.")
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)

    _sql_constraints = [
        ('name_company_uniq', 'unique (name,company_id)', 'The name of materials must be unique per company!')
    ]


class ProductProduct(models.Model):
    _inherit = 'product.product'

    color = fields.Char(string="Color")
    floor_color = fields.Char(string="Floor Color")
    product_line = fields.Char(string="Product Line")
    thumb_nail = fields.Char("Thumb Nail")
    url = fields.Char("Url")
    color_up_charge_price = fields.Float('Color Up Charge Price')
    display_name_in_app = fields.Char(string="Display Name in App")
    color_attachment_id = fields.Many2one('ir.attachment', string='Color Attachment Ref', copy=False)
    in_stock = fields.Boolean('Stock Available', default=False)
    special_order = fields.Boolean('Special Order', default=False)
    office_location_ids = fields.Many2many('otl.office.location', string='Market Segments Where Out Of Stock')


class LaborCost(models.Model):
    _name = 'labor.cost'
    _description = "Labor Cost"

    name = fields.Char('Name')
    from_date = fields.Date('From Date', required=True)
    to_date = fields.Date('To Date')
    labor_cost = fields.Float('Labor Charge')
    company_id = fields.Many2one('res.company')
    note = fields.Text('Internal Notes')

    @api.constrains('from_date', 'to_date')
    def _check_current_labor_cost(self):

        for labor_cost in self:
            domain = [('id', '!=', labor_cost.id), ]
            if not labor_cost.to_date:
                start_domain = []
                end_domain = ['|', ('to_date', '>=', labor_cost.from_date), ('to_date', '=', False)]
            else:
                start_domain = [('from_date', '<=', labor_cost.to_date)]
                end_domain = ['|', ('to_date', '>', labor_cost.from_date), ('to_date', '=', False)]
            domain = expression.AND([domain, start_domain, end_domain])
            if self.search_count(domain):
                raise ValidationError(_(
                    'Can only have one Labor Cost at the same time.'))

    @api.constrains('from_date', 'to_date')
    def _check_dates(self):
        if self.filtered(lambda c: c.to_date and c.from_date > c.to_date):
            raise ValidationError(_('Labor Cost start date must be earlier than the end date.'))


class Product(models.Model):
    _inherit = 'product.template'

    payment_plan = fields.Char('Plan Type')
    is_material = fields.Boolean('Material')
    active = fields.Boolean('Active', default=True)
    description = fields.Text('Description')
    warranty = fields.Selection([
        ('1_year', '1 Year Warranty'),
        ('5_year', '5 Year Warranty'),
        ('lifetime', 'Lifetime Gurarantee')
    ])
    sequence = fields.Integer('Priority',
                              help="Give to the more specialized category, a higher priority to have them in top of the list.")
    room_area = fields.Integer("Room Area")
    installation_assumption = fields.Integer('Installation Assumption')
    labor_factor = fields.Float('Labor Factor')
    discount = fields.Float('Default Discount')
    labor_cost = fields.Float('Labor Charge', compute='_compute_labor_cost')
    labor_cost_with_factor = fields.Float('Labor Cost With Factor', compute='_compute_labor_cost_with_factor')
    cost_per_sqft = fields.Float('Labor Cost With Factor per sq.ft', compute='_compute_cost_per_sqft')
    flooring_cost = fields.Float('Flooring Cost', compute='_compute_flooring_cost')
    discount_minimum = fields.Integer('Minimum Discount  Allowed')
    discount_maximum = fields.Integer('Maximum Discount Allowed')
    monthly_promo = fields.Float('Monthly Promo')

    msrp = fields.Float('MSRP')
    unit_of_measure = fields.Char('UnitOfMeasure')
    eligible_for_discounts = fields.Char('EligibleForAllDiscounts')
    warranty_info = fields.Char('Warranty Info')
    grade = fields.Char('Grade')

    min_sale_price = fields.Float('Minimum Sale Price', default=0)

    @api.depends('list_price', 'cost_per_sqft')
    def _compute_flooring_cost(self):
        for record in self:
            record.flooring_cost = record.list_price + record.cost_per_sqft

    @api.depends('labor_cost_with_factor', 'installation_assumption')
    def _compute_cost_per_sqft(self):
        for record in self:
            if not record.installation_assumption == 0:
                record.cost_per_sqft = record.labor_cost_with_factor / record.installation_assumption
            else:
                record.cost_per_sqft = 0.0

    @api.depends('labor_cost', 'labor_factor')
    def _compute_labor_cost_with_factor(self):
        for record in self:
            record.labor_cost_with_factor = record.labor_cost * record.labor_factor

    def get_current_date(self):
        current_date = fields.Date.today()
        return current_date

    @api.depends('labor_cost')
    def _compute_labor_cost(self):
        for record in self:
            date_today = record.get_current_date()
            labor_cost = self.env['labor.cost'].search(
                ['|', '&', ('from_date', '<=', date_today), ('to_date', '>=', date_today), '&',
                 ('from_date', '<=', date_today), ('to_date', '=', False)])
            if labor_cost:
                record.labor_cost = labor_cost[0].labor_cost
            else:
                record.labor_cost = 0.0


class IRAttachment(models.Model):
    _inherit = 'ir.attachment'

    improveit_id = fields.Char('Improveit Reference ID')


class OfficeLocation(models.Model):
    _name = 'otl.office.location'
    _description = 'Office Locations'

    name = fields.Char('Location', required=True)
    improveit_id = fields.Char(string='i360 ReferenceID')
    active = fields.Boolean('Active', default=True)
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)
    special_price_line = fields.One2many('otl.product.special.price', 'office_location_id', 'Special Price')

    _sql_constraints = [
        ('name_company_uniq', 'unique (name,company_id)', 'The name of materials must be unique per company!')
    ]


class ProductSpecialPrice(models.Model):
    _name = 'otl.product.special.price'
    _description = "Product Special Pricing"

    name = fields.Char('Name')
    office_location_id = fields.Many2one('otl.office.location', 'Office Location')
    product_tmpl_id = fields.Many2one('product.template', 'Product Template')
    start_date = fields.Date('Start Date')
    end_date = fields.Date('End Date')
    list_price = fields.Float('Sale Price')
    msrp = fields.Float('MSRP')
    max_discount = fields.Float('Maximum Discount %')
    active = fields.Boolean('Active', default=True)


class SalesAppVersion(models.Model):
    _name = 'otl.sales.app.version'
    _description = "Sales App Versions"
    _order = 'date desc'

    name = fields.Char('App Version', required=True)
    date = fields.Date('Release Date', required=True, default=fields.Date.context_today)
    description = fields.Text('Description')
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)
    sale_contract_tmpl_id = fields.Many2one('otl_document_sign.template', string='Sign Template')
    sale_contract_tmpl_id_ncp = fields.Many2one('otl_document_sign.template',
                                                string='Sign Template Without Co-Applicant')
    credit_application_tmpl_id = fields.Many2one('otl_document_sign.template', string='Credit Application Template')
    credit_application_tmpl_id_ncp = fields.Many2one('otl_document_sign.template',
                                                     string='Credit Application Template Without Co-Applicant')

    _sql_constraints = [
        ('name_company_uniq', 'unique (name,company_id)', 'App Version must be unique!')
    ]


class PromotionCodes(models.Model):
    _name = 'otl.promotion.code'
    _description = "Promotion Codes"
    _order = 'start_date desc'

    name = fields.Char('Promotion', required=True)
    start_date = fields.Date('Start Date')
    end_date = fields.Date('End Date')
    description = fields.Char('Description')
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)
    discount = fields.Float('Discount')
    active = fields.Boolean('Active', default=True)
    calculation_type = fields.Selection([('sqft', 'SQFT'), ('percentage', 'Percentage'), ('fixed', 'Fixed Amount')],
                                        string='Calculation Type', default='sqft')


class TransitionHeight(models.Model):
    _name = 'otl.transition.height'
    _description = "Transition Height Ranges"
    _order = 'sequence asc'

    name = fields.Char('Range', required=True)
    description = fields.Char('Description')
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)
    active = fields.Boolean('Active', default=True)
    sequence = fields.Integer('Priority',
                          help="Give to the more specialized category, a higher priority to have them in top of the list.",
                          default=10)


class UserAuthenticationLog(models.Model):
    _name = 'otl.user.authentication.log'
    _description = "Users Authentication Logs"
    _order = 'date desc'
    _rec_name = 'user_id'

    user_id = fields.Many2one('res.users', 'User', required=True, ondelete='cascade')
    date = fields.Datetime('Date', required=True, default=fields.Datetime.now)
    action = fields.Selection([('login',  'Login'), ('logout', 'Logout')], string='Action Type',
                              required=True, default='login')
    token = fields.Char('User Token')
    company_id = fields.Many2one('res.company', string='Company', required=False, default=lambda self: self.env.company)
    action_done = fields.Selection([('user', 'User'), ('admin', 'Admin'), ('automated', 'Automated')],
                                   string='Action Done By', default='user', required=True)
    device_name = fields.Char(string='Device Name')
    device_os = fields.Char(string='Device OS')
    app_version = fields.Char(string='App Version')


class Weekdays(models.Model):
    _name = 'otl.weekdays'
    _description = "Weekdays"

    name = fields.Char("Name")


class PaymentRestrictionRule(models.Model):
    _name = 'otl.payment.restriction.rule'
    _description = "Restricting Payment Rules"
    _order = 'start_date desc'

    name = fields.Char("Rule Name")
    start_date = fields.Date("Start Date")
    end_date = fields.Date("End Date")
    location_ids = fields.Many2many("otl.office.location", string='Office Locations')
    payment_option_ids = fields.Many2many("team.downpayment.option", string="Payment Options")
    allowed_days_ids = fields.Many2many('otl.weekdays', string="Weekdays")
    active = fields.Boolean("Active", default=True)
    conditions = fields.Selection([
        ('amount', 'Order Total'),
        ('grade', 'Grade'),
        ('margin', 'Margin'),
        ('promotions', 'Promotions'),
    ])
    min_order_total = fields.Integer("Minimum Order Total")
    grade = fields.Char('Grade')
    min_margin_amount = fields.Integer("Minimum Margin Amount")
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company.id)
    promotion_code_ids = fields.Many2many('otl.promotion.code', string='Restricted Promotions')
    promos_ids = fields.Many2many('otl.promotion.code', relation='conditional_promotion_rel',column1='restriction_rule_id',column2='promotion_id', string='Promotions')
    discount_code_ids = fields.Many2many('team.monthly.promo', string='Restricted Discounts')


class AppointmentResultReason(models.Model):
    _name = 'otl.appointment.result.reason'
    _description = "Appointment Resulting Reasons"
    _order = 'sequence asc'

    name = fields.Char("Reason", required=True)
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company.id)
    active = fields.Boolean("Active", default=True)
    reference_id = fields.Char("i360 Reference ID")
    sequence = fields.Integer('Priority',
                              help="Give to the more specialized category, a higher priority to have them in top of the list.", default = 10)
    appointment_result_ids = fields.Many2many('appointment.result', 'appointment_result_reason_rel', 'result_id', 'result_reason_id', string='Applicable Appointment Results')

    _sql_constraints = [
        ('name_company_uniq', 'unique (name,company_id)', 'Reason must be unique per company!')
    ]


class InstallationCrew(models.Model):
    _name = 'otl.installation.crew'
    _description = 'Installation Crew'

    name = fields.Char('Crew Name', required=True)
    active = fields.Boolean("Active", default=True)
    company_id = fields.Many2one('res.company', string='Company', required=True,
                                 default=lambda self: self.env.company.id)
    improveit_id = fields.Char('Improveit Reference ID')


class FinanceChecklistItems(models.Model):
    _name = 'otl.finance.checklist.items'
    _description = "Finance and Order Checklist Items"
    _order = 'sequence asc'

    name = fields.Char("Checklist", required=True)
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company.id)
    active = fields.Boolean("Active", default=True)
    reference_id = fields.Char("i360 Reference ID")
    sequence = fields.Integer('Priority',
                              help="Give to the more specialized category, a higher priority to have them in top of the list.", default = 10)

    _sql_constraints = [
        ('name_company_uniq', 'unique (name,company_id)', 'Reason must be unique per company!')
    ]



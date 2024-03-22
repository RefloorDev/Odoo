# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields, api, _
from datetime import datetime
from odoo.osv import expression
from odoo.exceptions import ValidationError
from odoo.addons.resource.models.resource import float_to_time
import pytz
from dateutil.relativedelta import relativedelta
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT, DEFAULT_SERVER_DATETIME_FORMAT

import logging


_logger = logging.getLogger(__name__)


class AppointmentResult(models.Model):
    _name = 'appointment.result'
    _description = "Appointment Result"

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

    def action_generate_versatile_user_token(self):
        for record in self:
            if record.user_id:
                action = self.env.ref('team_sale_contract.action_generate_token').read()[0]
                action['context'] = {
                    "default_user_id": record.user_id.id,
                    "default_token": record.user_id.token_name or "",
                }
                return action


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
    description = fields.Char('Description')
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



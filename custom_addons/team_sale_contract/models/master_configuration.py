# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields, api, _
from datetime import datetime
from odoo.osv import expression
from odoo.exceptions import ValidationError


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
    auto_logout_time = fields.Float('Auto Logout Time', help="Enter time in 24 Hrs format")


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
    balance_due = fields.Char('Balance_Due__c')
    sequence = fields.Float(string="Display_Order__c")
    payment_info = fields.Text('Payment_Info__c')


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
    start_date = fields.Datetime('Start Date')
    end_date = fields.Datetime('End Date')
    description = fields.Char('Description')
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)
    discount = fields.Float('Discount')
    active = fields.Boolean('Active', default=True)


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

# -*- coding: utf-8 -*-
import base64
from odoo import models, fields, api, _
from datetime import datetime,date
from odoo.osv import expression
from odoo.exceptions import ValidationError,UserError
from odoo.addons.team_api_configuration.controllers.configurations import URL, DB, API_USER_ID, API_USER_PASSWORD
from odoo.addons.team_api_configuration.jwt.api_jws import encode as JWT_ENCODE
from odoo.addons.team_api_configuration.jwt.api_jws import decode as JWT_DECODE
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT
import ast
import logging
_logger = logging.getLogger(__name__)


JWT_SECRET = 'secretXXXY'
JWT_ALGORITHM = 'HS256'
FIELDS_TO_ENCRYPT = ['drivers_license',
                     'date_of_birth',
                     'social_security_number',
                     'co_applicant_drivers_license',
                     'co_applicant_date_of_birth',
                     'co_applicant_social_security_number'
                     ]


class TeamTransitionLine(models.Model):
    _name = 'team.contract.transition.line'
    _description = "Contract Transition Line"

    name = fields.Text('Description', required=True)
    transition_width = fields.Float('Transition Width', required=True)
    transition_height = fields.Char('Transition Height', default='')
    transition_height_id = fields.Many2one('otl.transition.height', string='Transition Height Ref')
    floor_id = fields.Many2one('team.floor.level', string='Floor Level',required=False)
    room_id = fields.Many2one('team.room.room', string='Room',required=True, ondelete='restrict')
    appointment_id = fields.Many2one('team.customer.appointment', 'Appointment')
    attachment_ids = fields.Many2many('ir.attachment', string="Images")
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)
    order_id = fields.Many2one('sale.order', string="Sale Order")
    room_measurement_id = fields.Many2one('team.contract.room.measurement.line', 'Room Measurement Line Id')


class TeamContractQuestions(models.Model):
    _name = 'team.contract.question.line'
    _description = "Team Contract Question Line"
    _rec_name = 'question_id'

    @api.depends('answers')
    def _compute_answers(self):
        for record in self:
            answer= ''
            for line in record.answers:
                if not answer:
                    answer = line.answer
                else:
                    answer += ', %s'%(line.answer)
            record.answer_data = answer

    @api.depends('question_id', 'room_measurement_id', 'room_measurement_id.adjusted_area')
    def _compute_extra_price(self):
        for record in self:
            extra_price = 0
            if record.question_id and record.room_measurement_id and record.answer_data and not record.calculate_order_wise:
                question = record.question_id
                if question.code == 'CurrentCoveringType':
                    record.extra_price = 0
                    continue
                amount = question.amount or 0
                answer_data = record.answer_data
                amount_included = question.amount_included or 0
                if question.code == 'RemoveCurrentCovering':
                    if answer_data == 'Yes':
                        covering_question = self.search([
                            ('appointment_id', '=', record.appointment_id.id),
                            ('room_measurement_id', '=', record.room_measurement_id.id),
                            ('question_id.code', '=', 'CurrentCoveringType')
                        ], limit=1)
                        if covering_question:
                            covering_question_answer = covering_question.answer_data or False
                            if covering_question_answer and covering_question.question_id:
                                answer_line = covering_question.question_id.labels_ids.filtered(lambda x: x.value == covering_question_answer)
                                if answer_line and answer_line.answer_score:
                                    amount = answer_line.answer_score
                                room_area = record.room_measurement_id.adjusted_area or 0
                                net_room_area = (room_area - amount_included) > 0 and room_area - amount_included or 0
                                extra_price = net_room_area * float(amount)
                else:
                    if question.question_type == 'simple_choice':
                        if answer_data == 'No':
                            record.extra_price = 0
                            continue
                        else:
                            if not amount:
                                answer_line = question.labels_ids.filtered(lambda x: x.value == answer_data)
                                if answer_line and answer_line.answer_score:
                                    amount = answer_line.answer_score
                    elif question.question_type == 'numerical_box':
                        answer_data = answer_data and float(answer_data) or 0
                    if question.calculation_type == 'fixed':
                        extra_price = amount
                    elif question.calculation_type == 'unit':
                        if question.question_type == 'simple_choice'and answer_data == 'Yes':
                            extra_price = amount
                        elif question.question_type == 'numerical_box':
                            extra_price = answer_data * amount
                    elif question.calculation_type == 'sqft':
                        if question.question_type == 'simple_choice':
                            room_area = record.room_measurement_id.adjusted_area or 0
                            net_room_area = (room_area - amount_included) > 0 and room_area - amount_included or 0
                            extra_price = net_room_area * float(amount)
                        elif question.question_type == 'numerical_box' and question.multiply_with_area:
                            room_area = record.room_measurement_id.adjusted_area or 0
                            net_room_area = (room_area - amount_included) > 0 and room_area - amount_included or 0
                            extra_price = net_room_area * float(amount) * answer_data
                        else:
                            net_answer_data = (answer_data - amount_included) > 0 and answer_data - amount_included or 0
                            extra_price = net_answer_data * float(amount)
                
                if question.code == 'StairCoverRisers' and answer_data == 'White Risers':
                    """
                        This part is used for handle White Risers case.
                    """
                    answer_line = question.labels_ids.filtered(lambda x: x.value == answer_data)
                    stair_count = 0
                    if answer_line and answer_line.answer_score:
                        stair_count_line = self.search([
                            ('appointment_id', '=', record.appointment_id.id),
                            ('question_id.code', '=', 'StairCount')
                        ], limit=1)
                        if stair_count_line:
                            stair_count = int(stair_count_line.answer_data)  
                    extra_price = answer_line.answer_score * stair_count
                    

            record.extra_price = extra_price

    name = fields.Text('Description',required=False)
    room_name = fields.Char('Room Name')
    room_id = fields.Many2one('team.room.room', string='Room',required=True)
    floor_id = fields.Many2one('team.floor.level', string='Floor', required=False)
    question_id = fields.Many2one('team.quote.question',string='Question',ondelete='restrict')
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)
    appointment_id = fields.Many2one('team.customer.appointment', 'Appointment',required=True)
    answers = fields.One2many('team.contract.answer.line','question_id', string='Answers', copy=True, ondelete='cascade')
    order_id = fields.Many2one('sale.order', string="Sale Order", ondelete='cascade')
    answer_data = fields.Char('Answer', compute='_compute_answers')
    room_measurement_id = fields.Many2one('team.contract.room.measurement.line', 'Custom room measurement Id')
    extra_price = fields.Float('Extra Price Required', compute='_compute_extra_price')
    amount_included = fields.Float('Included Amount', help='It denotes the amount which already included in the quote')
    calculate_order_wise = fields.Boolean("Calculate Based on Order", default=False,
                                          help='If checked, amount should calculate based on total order not based on room.')
    
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('question_id'):
                question = self.env['team.quote.question'].browse(vals['question_id'])
                vals.update({'amount_included': question.amount_included if question else 0})
        return super(TeamContractQuestions, self).create(vals_list)

    def write(self, vals):
        if vals.get('question_id', False):
            question = self.env['team.quote.question'].browse(vals.get('question_id', False))
            vals.update({'amount_included': question and question.amount_included or 0})
        return super(TeamContractQuestions, self).write(vals)


class TeamContractAnswers(models.Model):
    _name = 'team.contract.answer.line'
    _description = "Team Contract Answer Line"

    question_id = fields.Many2one('team.contract.question.line',string='Question Line',required=True, ondelete='cascade')
    answer = fields.Char('Answer')


class TeamContractRoomMeasurement(models.Model):
    _name = 'team.contract.room.measurement.line'
    _description = "Team Contract Room Measurement Line"

    @api.depends('room_id', 'room_area')
    def _compute_name(self):
        for record in self:
            name= ''
            if record.room_id:
                room_name = record.room_id.name or ''
                if record.room_id.is_custom:
                    room_name = record.custom_room_name or ''
                name = '%s-%s'%(room_name, record.room_area)
            record.name = name

    @api.depends('color_up_charge_price', 'material_id', 'adjusted_area')
    def _compute_color_up_charge_total(self):
        for record in self:
            color_up_charge_total = 0
            if record.adjusted_area and record.color_up_charge_price:
                color_up_charge_total = record.adjusted_area * record.color_up_charge_price
            record.color_up_charge_total = color_up_charge_total

    @api.depends('molding_unit_price', 'molding_type_id', 'room_perimeter')
    def _compute_molding_total_price(self):
        for record in self:
            molding_total_price = 0
            if record.room_perimeter and record.molding_unit_price:
                molding_total_price = record.room_perimeter * record.molding_unit_price
            record.molding_total_price = molding_total_price

    name = fields.Text('Description', compute='_compute_name')
    room_id = fields.Many2one('team.room.room', string='Room', required=True)
    floor_id = fields.Many2one('team.floor.level', string='Floor', required=False)
    appointment_id = fields.Many2one('team.customer.appointment', 'Appointment', required=True)
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)
    room_area = fields.Float(string="Room Area")
    order_id = fields.Many2one('sale.order', string="Sale Order", ondelete='cascade')
    comments = fields.Char(string = "Comments")
    exclude_from_calculation = fields.Boolean(string = "Excluded from Calculation",default=False)
    attachment_ids = fields.Many2many('ir.attachment', string="Room Images")
    protrusion_image_ids = fields.Many2many('ir.attachment', 'protrusion_image_room_rel', 'room_id', 'attachment_id', string="Anomaly Images")
    material_id = fields.Many2one('product.product', string="Color")
    shape_image_id = fields.Many2one('ir.attachment',string="Room Shape Drawing")
    material_comments = fields.Char(string="Comments for Color")
    shape_image = fields.Binary('Room Shape', related='shape_image_id.datas')
    custom_room_name = fields.Char('Custom Room Name')
    adjusted_area = fields.Float(string="Adjusted Area")
    image_comments = fields.Char(string='Comments on Images')
    custom_room_measured = fields.Boolean(string='Is Custom Room?')
    moulding = fields.Char('Molding')
    molding_type_id = fields.Many2one('team.floor.molding', 'Molding Type')
    room_perimeter = fields.Float('Room Perimeter')
    transition_line_id = fields.One2many('team.contract.transition.line', 'room_measurement_id', 'Transitions')
    color_up_charge_price = fields.Float('Color Up Charge Price')
    color_up_charge_total = fields.Float('Color Up Charge Total Amount', compute='_compute_color_up_charge_total', store=True)
    molding_unit_price = fields.Float('Molding Unit Price')
    molding_total_price = fields.Float('Molding Total Amount', compute='_compute_molding_total_price', store=True)
    appointment_result = fields.Char('Appointment Result', related='order_id.appointment_result', store=True)
    misc_charge_comments = fields.Char('Miscellaneous Charge Comments')
    delivery_option = fields.Char("Selected Delivery Option")

    def write(self, vals):
        _logger.info('ContractRoomMeasurement ID: %s, vals: %s'%(self.ids, vals))
        return super(TeamContractRoomMeasurement, self).write(vals)


class TeamPaymentTransaction(models.Model):
    _name = 'team.payment.transaction.line'
    _description = "Team Payment Transaction"

    payment_plan = fields.Many2one('product.template', string='Floor Category')
    payment_option = fields.Many2one('team.downpayment.option', string='Payment Option')
    downpayment_percentage = fields.Many2one('team.payment.percentage', string='Payment Percentage')
    payment_method = fields.Many2one('team.downpayment.method', string='Payment Method')
    total_price = fields.Float('Total Price')
    downpayment = fields.Float('Down payment')
    balance = fields.Float('Balance')
    payment_success = fields.Boolean('Payment Success')
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)
    order_id = fields.Many2one('sale.order', string='Sale Order')


class TeamCreditApplication(models.Model):
    _name = 'team.credit.application'
    _description = "Team Credit Application"

    @api.depends('applicant_first_name', 'applicant_last_name')
    def _compute_applicant_name(self):
        for record in self:
            record.applicant_name = '%s, %s'%(record.applicant_last_name or '', record.applicant_first_name)

    @api.depends('co_applicant_first_name', 'co_applicant_last_name')
    def _compute_co_applicant_name(self):
        for record in self:
            record.co_applicant_name = '%s, %s'%(record.co_applicant_last_name or '', record.co_applicant_first_name)

    total_price = fields.Float('Total Price')
    downpayment = fields.Float('Down Payment')
    amount_financed = fields.Float('Amount Financed')
    type_of_loan = fields.Selection([
        ('Low Payment', 'Low Payment'),
        ('No Interest', 'No Interest'),
        ('One Year no Payments','One Year no Payments')
    ], string='Type of Loan')
    low_payment = fields.Boolean(string='low_payment',default=False)
    no_interest = fields.Boolean(string='no_interest',default=False)
    no_payment = fields.Boolean(string='no_payment',default=False)

    type_of_property = fields.Selection([
        ('Single Family', 'Single Family'),
        ('Mobile Home', 'Mobile Home'),
        ('Condo','Condo')
    ], string='Type of Property')

    single_family = fields.Boolean(string='single_family', default=False)
    mobile_family = fields.Boolean(string='mobile_family', default=False)
    condoo = fields.Boolean(string='condoo', default=False)

    work_to_be_done = fields.Selection([
        ('WINDOWS', 'Windows'),
        ('ROOF', 'Roof'),
        ('SIDING','Siding'),
        ('GUTTERS','Gutters'),
        ('GUTTER GRATE', 'Gutter Grate'),
        ('INSULATION', 'Insulation'),
        ('WALK IN TUBS', 'Walk in Tubs'),
        ('New Floor Installation','New Floor Installation'),

    ], string='Work to be Done')

    windows = fields.Boolean(string='windows', default=False)
    roof = fields.Boolean(string='roof', default=False)
    siding = fields.Boolean(string='siding', default=False)
    gutters = fields.Boolean(string='gutters', default=False)
    gutter_grate = fields.Boolean(string='gutter_grate', default=False)
    insulation = fields.Boolean(string='insulation', default=False)
    walk_in_tubs = fields.Boolean(string='walk_in_tubs', default=False)


    owners = fields.Selection([
        ('SAME AS APPLICANT', 'Same as Below'),
        ('DIFFERENT', 'Owners'),
    ], string='Owner(s) (if Different From Below)')

    same_as_below = fields.Boolean(string='same_as_below', default=False)
    else_owners = fields.Boolean(string='else_owners', default=False)

    owners_if_different = fields.Char('Owners (if Different)')

    address_of_property = fields.Char('Address of Property to be Improved(if Different From Below)')

    same_as_address_of_property = fields.Boolean(string='same_as_address_of_property', default=False)
    else_address_of_property = fields.Boolean(string='else_address_of_property', default=False)


    street = fields.Char('street1')
    street2 = fields.Char('street2')
    city = fields.Char('city')
    state = fields.Char(string="State")
    zip = fields.Char('zip')

    same_property_address = fields.Selection([
        ('SAME AS APPLICANT', 'Same as Below'),
        ('DIFFERENT', 'Owners'),
    ], string='Property Address (if Different From Below)')

    applicant_name = fields.Char('Applicant Name', compute='_compute_applicant_name')
    co_applicant_name = fields.Char('Co Applicant Name', compute='_compute_co_applicant_name')

    applicant_first_name = fields.Char('First Name')
    applicant_middle_name = fields.Char('Second Name')
    applicant_last_name = fields.Char('Last Name')
    drivers_license = fields.Char('Drivers License or state ID')
    drivers_license_issue_date = fields.Date('Applicant Drivers License Issue Date')
    drivers_license_exp_date = fields.Date('Drivers License Exp.Date')
    date_of_birth = fields.Date('Date of Birth')
    social_security_number = fields.Char('Social Security Number')
    encrypted_social_security_number = fields.Char('Encrypted Social Security Number')
    encrypted_drivers_license = fields.Char('Encrypted Drivers License or state ID')
    encrypted_date_of_birth = fields.Char('Encrypted Date of Birth')
    address_of_applicant = fields.Char('Address')
    address_of_applicant_street = fields.Char('Street1')
    address_of_applicant_street2 = fields.Char('Street2')
    address_of_applicant_city = fields.Char('City')
    address_of_applicant_state = fields.Char(string="State")
    address_of_applicant_zip = fields.Char('zip')

    previous_address_of_applicant = fields.Char('Previous Address(if current less than 2 yrs)')
    previous_address_of_applicant_street = fields.Char('Street1')
    previous_address_of_applicant_street2 = fields.Char('Street2')
    previous_address_of_applicant_city = fields.Char('City')
    previous_address_of_applicant_state = fields.Char(string="State")
    previous_address_of_applicant_zip = fields.Char('zip')

    cell_phone = fields.Char('Cell Phone')
    home_phone = fields.Char('Home Phone')
    how_long = fields.Char('How Long?')
    previous_address_how_long = fields.Char('How LONG?')
    present_employer = fields.Char('Present Employer')
    years_on_job = fields.Char('Years on Job')
    occupation = fields.Char('Occupation')

    present_employers_address = fields.Char('Present Employers Address, City, State, zip Code')
    present_employers_address_street = fields.Char('street1')
    present_employers_address_street2 = fields.Char('street2')
    present_employers_address_city = fields.Char('city')
    present_employers_address_state = fields.Char(string="State")
    present_employers_address_zip = fields.Char('zip')
    earnings_from_employment = fields.Float('Earnings From Employment(Monthly)')
    is_earning_from_employment = fields.Boolean('IF Earnings Monthly',default=False)
    supervisor_or_department = fields.Char('Supervisor or Dept')
    employers_phone_number = fields.Char('Employers Phone Number')

    previous_employers_address = fields.Char('Previous Employer Aand Address, City, state, zip Code(if less than 2 years)')
    previous_employers_address_street = fields.Char('street1')
    previous_employers_address_street2 = fields.Char('street2')
    previous_employers_address_city = fields.Char('city')
    previous_employers_address_state = fields.Char(string="State")
    previous_employers_address_zip = fields.Char('zip')
    earnings_per_month = fields.Float('Earnings Per Month')
    years_on_job_previous_employer = fields.Char('Years on job')
    occupation_previous_employer = fields.Char('occupation')
    previous_employers_phone_number = fields.Char('previous employers phone number')

    #co-applicant details

    co_applicant_first_name = fields.Char('First Name')
    co_applicant_middle_name = fields.Char('Second Name')
    co_applicant_last_name = fields.Char('Last Name')
    co_applicant_drivers_license = fields.Char('Co-Applicant Drivers License or State ID')
    co_applicant_drivers_license_issue_date = fields.Date('Co-Applicant Drivers License Issue Date')
    co_applicant_drivers_license_exp_date = fields.Date('Co-Applicant Drivers License Exp Date')
    co_applicant_date_of_birth = fields.Date('Co-Applicant Date of Birth')
    co_applicant_social_security_number = fields.Char('Co-Applicant SSN')
    co_applicant_address_of_applicant = fields.Char('Address')

    encrypted_co_applicant_drivers_license = fields.Char('Encrypted Co-Applicant Drivers License')
    encrypted_co_applicant_date_of_birth = fields.Char('Encrypted Co-Applicant Date of Birth')
    encrypted_co_applicant_social_security_number = fields.Char('Encrypted Co-Applicant SSN')

    co_applicant_street = fields.Char('Street1')
    co_applicant_street2 = fields.Char('Street2')
    co_applicant_city = fields.Char('city')
    co_applicant_state = fields.Char(string="State")
    co_applicant_zip = fields.Char('zip')
    co_applicant_phone = fields.Char(string='Co-Applicant Phone')
    co_applicant_secondary_phone = fields.Char(string="Co-Applicant Secondary Phone")

    co_applicant_previous_address_of_applicant = fields.Char('previous address(if current less than 2 yrs)')
    co_applicant_previous_street = fields.Char('street1')
    co_applicant_previous_street2 = fields.Char('street2')
    co_applicant_previous_city = fields.Char('city')
    co_applicant_previous_state = fields.Char(string="State")
    co_applicant_previous_zip = fields.Char('zip')

    co_applicant_how_long = fields.Char('How Long?')
    co_applicant_present_employer = fields.Char('Present Employer')
    co_applicant_years_on_job = fields.Char('Years on Job')
    co_applicant_occupation = fields.Char('Occupation')

    co_applicant_present_employers_address = fields.Char('Present employers Address, City, state, zip code')
    co_applicant_present_employers_street = fields.Char('Street1')
    co_applicant_present_employers_street2 = fields.Char('Street2')
    co_applicant_present_employers_city = fields.Char('City')
    co_applicant_present_employers_state = fields.Char(string="State")
    co_applicant_present_employers_zip = fields.Char('zip')

    co_applicant_earnings_from_employment = fields.Float('Earnings From Employment(Monthly)')
    co_applicant_supervisor_or_department = fields.Char('Supervisor or Dept')
    co_applicant_employers_phone_number = fields.Char('Employers Phone Number')

    co_applicant_previous_employers_address = fields.Char('Previous Employer and Address, City, State, zip code(if less than 2 years)')
    co_applicant_previous_employers_street = fields.Char('street1')
    co_applicant_previous_employers_street2 = fields.Char('street2')
    co_applicant_previous_employers_city = fields.Char('city')
    co_applicant_previous_employers_state = fields.Char(string="State")
    co_applicant_previoust_employers_zip = fields.Char('zip')

    co_applicant_earnings_per_month = fields.Float('Earnings per Month ')
    co_applicant_years_on_job_previous_employer = fields.Char('Years on Job')
    co_applicant_occupation_previous_employer = fields.Char('Occupation')
    co_applicant_previous_employers_phone_number = fields.Char('Previous Employers Phone  Number')

    #OTHER INCOME AND OBLIGATIONS

    source_of_other_income = fields.Selection([
        ('Social Security', 'Social Security'),
        ('Pension', 'Pension'),
        ('Child Support','Child Support'),
        ('Rental', 'Rental'),
        ('Other','Other')
    ], string='Source of Other Income')

    social_security = fields.Boolean(string='social_security', default=False)
    pension = fields.Boolean(string='pension', default=False)
    child_support = fields.Boolean(string='child_support', default=False)
    rental = fields.Boolean(string='rental', default=False)
    other_source_of_income = fields.Boolean(string='other_source_of_income', default=False)

    amount_monthly = fields.Float('Amount (Monthly)')
    is_amount_monthly = fields.Boolean("IS amount Monthly",default=False)
    nearest_relative = fields.Char('Nearest Relative (Not Living In Household)')
    relationship = fields.Char('Relationship')

    address_relationship = fields.Char('Relationship Address, city, state, zip code')
    address_relationship_street = fields.Char('street1')
    address_relationship_street2 = fields.Char('Street2')
    address_relationship_city = fields.Char('City')
    address_relationship_state = fields.Char(string="State")
    address_relationship_zip = fields.Char('zip')

    phone_number_relationship = fields.Char('Phone Number')

    property_details = fields.Selection([
        ('MORTGAGE', 'MORTGAGE'),
        ('LAND', 'Land'),
        ('CONTRACT','Contract'),
        ('FREE AND CLEAR', 'Free And Clear')
    ], string='Property Details')

    property_details_mortage = fields.Boolean(string='property_details_mortage', default=False)
    property_details_land = fields.Boolean(string='property_details_land', default=False)
    property_details_contract = fields.Boolean(string='property_details_contract', default=False)
    property_details_free_and_clear = fields.Boolean(string='property_details_free_and_clear', default=False)

    lender_name = fields.Char('Lender Name')
    lender_address = fields.Char('Lender Address')
    lender_address_street = fields.Char('street1')
    lender_address_street2 = fields.Char('street2')
    lender_address_city = fields.Char('city')
    lender_address_state = fields.Char(string="State")
    lender_address_zip = fields.Char('zip')

    lender_phone = fields.Char('Lender Phone')
    original_purchase_price = fields.Float('Original Purchase Price')
    original_mortage_amount = fields.Float('Original Mortage Amount')
    monthly_mortage_payment = fields.Float('Monthly Mortage Payment')

    date_aquired = fields.Date('Date Acquired')
    present_balance = fields.Float('Present Balance')
    present_value_of_home = fields.Float('Present Value of Home')

    second_mortage = fields.Selection([
        ('Yes', 'YES'),
        ('No', 'NO'),
    ], string='Second Mortage')

    second_mortage_yes = fields.Boolean(string='second_mortage_yes', default=False)
    second_mortage_no = fields.Boolean(string='second_mortage_no', default=False)

    lender_name_or_phone = fields.Char('Name/Phone Number of Lender')
    applicant_second_mortage_phone = fields.Char('Applicant Second Mortage Phone')
    original_amount = fields.Float('Original Amount')
    present_balance_second_mortage = fields.Float('Present Balance')
    monthly_payment = fields.Float('Monthly Payment')
    other_obligations = fields.Float('Other Obligations')
    total_monthly_payments = fields.Float('Total Monthly Payment')
    checking_account_no = fields.Char('Checking Account Number')
    name_of_bank = fields.Char('Name Of Bank')
    bank_phone_number = fields.Char('Phone Number')
    checking_routing_no = fields.Char('Applicant Checking Routing No')

    #HOME OWNERS INSURANCE INFORMATION
    insurance_company = fields.Char('Insurance Company')
    agent = fields.Char('Agent')
    insurance_phone_no = fields.Char('Phone Number')
    coverage = fields.Char('Coverage')

    #INFORMATION FOR GOVERNMENT MONITORING PURPOSES

    applicant_not_furnish_info = fields.Boolean('I do not wish to furnish this information',default=False)

    ethnicity = fields.Selection([
        ('Not Hispanic', 'Not Hispanic or Latino'),
        ('Hispanic', 'Hispanic or Latino '),('I Do Not Wish To Furnish This Information','I Do Not Wish To Furnish This Information')
    ], string='Ethnicity')

    ethnicity_not_hispanic = fields.Boolean(string='ethnicity_not_hispanic', default=False)
    ethnicity_hispanic = fields.Boolean(string='ethnicity_hispanic', default=False)


    race = fields.Selection([
        ('I do not wish to furnish this information', 'I do not wish to furnish this information'),
        ('American Indian or Alaskan Native', 'American Indian or Alaskan Native'),
        ('White/Caucasian (non Hispanic)', 'White/Caucasian (non Hispanic)'),
        ('Hispanic', 'Hispanic'),
        ('Asian or Pacific Islander', 'Asian or Pacific Islander'),
        ('Black (non Hispanic)', 'Black (non Hispanic)'),
        ('Other', 'Other')
    ], string='Race/National Origin')

    race_dont_furnish = fields.Boolean('I do not wish to furnish this information', default=False)
    race_american_indian = fields.Boolean(string='American Indian or Alaskan Native', default=False)
    race_white = fields.Boolean(string='White/Caucasian (non Hispanic)', default=False)
    race_hispanic = fields.Boolean('Hispanic', default=False)
    race_asian = fields.Boolean(string='Asian or Pacific Islander', default=False)
    race_black = fields.Boolean('Black (non Hispanic)', default=False)
    race_other = fields.Boolean(string='Other', default=False)

    sex = fields.Selection([
        ('Male', 'Male'),
        ('Female', 'Female'),
    ], string='Sex')

    sex_male = fields.Boolean(string='sex_male', default=False)
    sex_female = fields.Boolean(string='sex_female', default=False)


    marital_status =  fields.Selection([
        ('Married', 'Married'),
        ('Unmarried', 'Unmarried'),
        ('Separated','Separated')
    ], string='MARITAL STATUS')

    marital_status_married = fields.Boolean(string='marital_status_married', default = False)
    marital_status_unmarried = fields.Boolean(string='marital_status_unmarried', default = False)
    marital_status_separated = fields.Boolean(string='marital_status_separated', default = False)

    co_applicant_not_furnish_info = fields.Boolean('I do not wish to furnish this information',default=False)

    co_applicant_ethnicity = fields.Selection([
        ('Not Hispanic', 'Not Hispanic or Latino'),
        ('Hispanic', 'Hispanic or Latino '),('I Do Not Wish To Furnish This Information','I Do Not Wish To Furnish This Information')
    ], string='Ethnicity')

    co_applicant_ethnicity_not_hispanic = fields.Boolean(string='ethnicity_not_hispanic', default=False)
    co_applicant_ethnicity_hispanic = fields.Boolean(string='ethnicity_hispanic', default=False)

    co_applicant_race = fields.Selection([
        ('I do not wish to furnish this information', 'I do not wish to furnish this information'),
        ('American Indian or Alaskan Native', 'American Indian or Alaskan Native'),
        ('White/Caucasian (non Hispanic)', 'White/Caucasian (non Hispanic)'),
        ('Hispanic', 'Hispanic'),
        ('Asian or Pacific Islander', 'Asian or Pacific Islander'),
        ('Black (non Hispanic)', 'Black (non Hispanic)'),
        ('Other', 'Other')
    ], string='Co-Applicant Race/National Origin')

    co_applicant_race_dont_furnish = fields.Boolean('I do not wish to furnish this information', default=False)
    co_applicant_race_american_indian = fields.Boolean(string='American Indian or Alaskan Native', default=False)
    co_applicant_race_white = fields.Boolean(string='White/Caucasian (non Hispanic)', default=False)
    co_applicant_race_hispanic = fields.Boolean('Hispanic', default=False)
    co_applicant_race_asian = fields.Boolean(string='Asian or Pacific Islander', default=False)
    co_applicant_race_black = fields.Boolean('Black (non Hispanic)', default=False)
    co_applicant_race_other = fields.Boolean(string='Other', default=False)

    co_applicant_race_american_indian = fields.Boolean(string='race_american_indian', default=False)
    co_applicant_race_asian = fields.Boolean(string='race_asian', default=False)
    co_applicant_race_african_american = fields.Boolean(string='race_african_american', default=False)
    co_applicant_race_native_hawaiian = fields.Boolean(string='race_native_hawaiian', default=False)
    co_applicant_race_white = fields.Boolean(string='race_white', default=False)


    co_applicant_sex = fields.Selection([
        ('Male', 'Male'),
        ('Female', 'Female'),
    ], string='Sex')

    co_applicant_sex_male = fields.Boolean(string='sex_male', default=False)
    co_applicant_sex_female = fields.Boolean(string='sex_female', default=False)

    co_applicant_marital_status = fields.Selection([
        ('Married', 'Married'),
        ('Unmarried', 'Unmarried'),
        ('Separated', 'Separated')
    ], string='MARITAL STATUS')

    co_applicant_marital_status_married = fields.Boolean(string='marital_status_married', default=False)
    co_applicant_marital_status_unmarried = fields.Boolean(string='marital_status_unmarried', default=False)
    co_applicant_marital_status_separated = fields.Boolean(string='marital_status_separated', default=False)

    type_of_credit_requested = fields.Selection([
        ('Individual Credit - relying solely on my income or assets', 'Individual Credit - relying solely on my income or assets'),
        ('Joint Credit - We intend to apply for joint credit', 'Joint Credit - We intend to apply for joint credit'),
        ('Individual Credit - relying on my income or assets as well as income or assets from other sources','Individual Credit - relying on my income or assets as well as income or assets from other sources')
    ], string='TYPE OF CREDIT REQUESTED')

    individual_credit = fields.Boolean(string='individual_credit', default=False)
    joint_credit = fields.Boolean(string='joint_credit', default=False)
    individual_credit_other = fields.Boolean(string='individual_credit_other', default=False)
    joint_credit_initials = fields.Char("Joint Credit Initials")


    applicant_signature = fields.Binary('Applicant Signature')
    applicant_signature_date = fields.Date('Applicant Signature Time')

    co_applicant_signature = fields.Binary('Co-Applicant Signature')
    co_applicant_signature_date = fields.Date('Co-Applicant Signature Time')

    order_id = fields.Many2one('sale.order',string='Sale Order')
    co_applicant_skip = fields.Boolean('Co-Applicant Skip', related='order_id.coapplicant_skip', readonly=True)
    appointment_id = fields.Many2one('team.customer.appointment',string='Appointment ID')
    partner_id = fields.Many2one('res.partner',string="Partner")

    applicant_email = fields.Char('Applicant Email')
    co_applicant_email = fields.Char('Co-Applicant Email')

    improveit_id = fields.Char('Improveit Reference ID')
    attachment_id = fields.Many2one('ir.attachment', string='Attachment')
    applicant_other_race = fields.Char('Applicant Other Race')
    co_applicant_other_race = fields.Char('CoApplicant Other Race')
    hunter_message_status = fields.Boolean('Hunter Message Status', default=False)

    hunter_message_status_yes = fields.Boolean('Hunter Message Status- Yes', compute='_compute_hunter_message_status')
    hunter_message_status_no = fields.Boolean('Hunter Message Status- No', compute='_compute_hunter_message_status')

    additional_income = fields.Selection([('Yes', 'Yes'), ('No', 'No')], 'Additional Income (Yes / No)', default='No')
    additional_monthly_income = fields.Float('Applicant Monthly Earnings')
    applicant_mortgage_company = fields.Char('Applicant Mortgage Company')

    def reverse(self, string):
        return "".join(reversed(string))

    def action_encrypt_field(self, field_name, value):
        token = ''
        payload = {
            field_name: value
        }
        token = JWT_ENCODE(payload, JWT_SECRET, JWT_ALGORITHM)
        token = self.reverse(token.decode("utf-8"))
        return token

    def action_decrypt_field(self, field_name):
        token = self['encrypted_%s' % (field_name)]
        values = {}
        if token:
            token = (self.reverse(token)).encode("utf-8")
            try:
                token_decode = JWT_DECODE(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
                token_decode = token_decode.decode("utf-8")
                values = ast.literal_eval(token_decode)
            except:
                values = {}
        field_value = values.get(field_name, '')
        if field_value and field_name in ['date_of_birth', 'co_applicant_date_of_birth']:
            field_value = datetime.strptime(field_value, '%Y-%m-%d').date()
        return field_value

    def action_update_field_values(self, vals):
        for field_name in FIELDS_TO_ENCRYPT:
            value = vals.get(field_name, False)
            if value:
                field_name_value= ''
                if field_name in ['date_of_birth', 'co_applicant_date_of_birth']:
                    field_name_value = False
                vals.update({
                    field_name:  field_name_value,
                    'encrypted_%s' % (field_name): self.action_encrypt_field(field_name, value)
                })
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [self.action_update_field_values(vals) for vals in vals_list]
        return super(TeamCreditApplication, self).create(vals_list)

    def write(self, vals):
        vals = self.action_update_field_values(vals)
        return super(TeamCreditApplication, self).write(vals)

    @api.depends('hunter_message_status')
    def _compute_hunter_message_status(self):
        for record in self:
            record.hunter_message_status_yes = False
            record.hunter_message_status_no = False
            if record.hunter_message_status:
                record.hunter_message_status_yes=True
            else:
                record.hunter_message_status_no = True

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
        self.write({'attachment_id': Attachment.id})
        url = URL + '/web/image/' + str(Attachment.id) + '?access_token=' + str(Attachment.access_token)
        return url

    def generate_link(self, sale_order=None):
        sign_req_obj = self.env['otl_document_sign.request']
        sign_req_item_obj = self.env['otl_document_sign.request.item']
        for order in self:
            if order.appointment_id.app_version_id:
                if order.co_applicant_skip:
                    document_template_id = order.appointment_id.app_version_id.credit_application_tmpl_id_ncp.id or False
                else:
                    document_template_id = order.appointment_id.app_version_id.credit_application_tmpl_id.id or False
            else:
                if order.co_applicant_skip:
                    document_template_id = self.env['ir.config_parameter'].sudo().get_param(
                        'team_sale_contract.credit_application_tmpl_id_ncp') or False
                else:
                    document_template_id = self.env['ir.config_parameter'].sudo().get_param(
                        'team_sale_contract.credit_application_tmpl_id') or False
            
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
                        current_request_item = sign_request.request_item_ids
                        sign_item_types = self.env['otl_document_sign.item.type'].sudo().search_read([('model_id', '=', template.model_id.id)])
                        if current_request_item:
                            for item_type in sign_item_types:
                                if item_type['auto_field']:
                                    field_list = item_type['auto_field'].split('.')
                                    selected_record = self.env[
                                        current_request_item.model_id.model].sudo().search(
                                        [('id', '=', current_request_item.res_id)], limit=1)
                                    auto_field = selected_record if selected_record else current_request_item.partner_id
                                    for field in field_list:
                                        if auto_field and field in auto_field:
                                            if field in FIELDS_TO_ENCRYPT:
                                                auto_field = auto_field.action_decrypt_field(field)
                                            else:
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
                                    sign_item_ids = sign_request.template_id.sign_item_ids.filtered(lambda r: not r.responsible_id or r.responsible_id.id == request_item.role_id.id)
                                    id_sign_item = False
                                    for sign_item_id in sign_item_ids:
                                        if sign_item_id.type_id.id == int(item_type['id']):
                                            id_sign_item = sign_item_id.id
                                    if id_sign_item:
                                        item_value = SignItemValue.create(
                                            {'sign_item_id': id_sign_item, 'sign_request_id': sign_request.id,
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
                        sign_request.generate_completed_document_credit_card_application()
                        # if sale_order:
                        #     sale_order.add_quote_id_file(sign_request.completed_document)
                        if share_url:
                            if sign_request.completed_document:
                                document_url = self.document_image(sign_request.reference, 'otl_document_sign.request', sign_request.completed_document, sign_request.id)
                                self.appointment_id.credit_application_url = document_url
                            return document_url

            else:
                raise UserError("Please update credit application template in the settings before proceeding.")
        return True


class ExternalCreditApplication(models.Model):
    _name = 'otl.versatile.credit.application'
    _description = "External Credit Application"
    _inherit = "mail.thread"
    _order = "event_date desc"

    @api.depends('approved_amount_cent')
    def _compute_approved_amount(self):
        for record in self:
            approved_amount = 0
            if record.approved_amount_cent:
                approved_amount = record.approved_amount_cent/100.0
            record.approved_amount = approved_amount


    name = fields.Char("Reference", default='/', copy=False)
    appointment_id = fields.Many2one('team.customer.appointment', string='Appointment', tracking=True)
    webhook_event_id = fields.Char('Reference', tracking=True)
    event_type = fields.Char('Event Type', tracking=True)
    event_date = fields.Datetime("Event Time", tracking=True)
    application_id = fields.Char('Application Reference', tracking=True)
    account_id = fields.Char('Account ID', tracking=True)
    provider = fields.Char("Provider", tracking=True)
    session_id = fields.Char("Session ID", tracking=True)
    provider_reference = fields.Char('Provider Reference Number', tracking=True)
    status = fields.Char("Status", tracking=True)
    submitted_date = fields.Datetime("Submitted Time", tracking=True)
    approved_amount_cent = fields.Float("Approved Amount in Cents", tracking=True)
    approved_amount = fields.Monetary("Approved Amount", compute='_compute_approved_amount', store=True)
    ext_customer_id = fields.Char("External Customer ID", tracking=True)
    applicant_first_name = fields.Char("Applicant First Name", tracking=True)
    applicant_last_name = fields.Char("Applicant Last Name", tracking=True)
    co_applicant_first_name = fields.Char("Co-Applicant First Name", tracking=True)
    co_applicant_last_name = fields.Char("Co-Applicant Last Name", tracking=True)
    error_line = fields.One2many('otl.versatile.error.line', 'credit_application_id', string="Errors")
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)
    user_id = fields.Many2one('res.users', string='Sales Person', related='appointment_id.user_id', store=True)
    currency_id = fields.Many2one(related="company_id.currency_id", string="Currency", readonly=True, store=True)
    finance_provider = fields.Selection([('versatile', 'Versatile'), ('hunter', 'Hunter')], string='Finance Provider',
                                        default='versatile', required=True)
    improveit_id = fields.Char(string='i360 ReferenceID', copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                seq_date = None
                if 'submitted_date' in vals:
                    seq_date = fields.Datetime.context_timestamp(self, fields.Datetime.to_datetime(vals['submitted_date']))
                if 'company_id' in vals:
                    vals['name'] = self.env['ir.sequence'].with_context(
                        force_company=vals['company_id']).next_by_code('versatile.credit.application', sequence_date=seq_date) or _('/')
                else:
                    vals['name'] = self.env['ir.sequence'].next_by_code('versatile.credit.application', sequence_date=seq_date) or _('/')
        return super(ExternalCreditApplication, self).create(vals_list)


class VersatileErrorLine(models.Model):
    _name = 'otl.versatile.error.line'
    _description = "Versatile Error Line"

    name = fields.Char('Error')
    credit_application_id = fields.Many2one('otl.versatile.credit.application', 'External Credit Application',
                                            ondelete='cascade')

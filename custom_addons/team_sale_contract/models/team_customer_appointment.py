from odoo import models, fields, api
import time
from datetime import timedelta

_STATES = [
    ('draft', 'New'),
    ('scheduled', 'Scheduled'),
    ('canceled', 'Canceled'),
    ('done', 'Done'),
]


class TeamCustomerAppointment(models.Model):
    _name = 'team.customer.appointment'
    _description = "Customer Appointments"
    _order= 'appointment_date desc'
    _inherit = ['portal.mixin', 'mail.thread', 'mail.activity.mixin', 'utm.mixin']

    @api.onchange('partner_id')
    def _onchange_partner_id_values(self):
        """ returns the new values when partner_id has changed """
        if self.partner_id:
            partner_id = self.partner_id
            self.mobile = partner_id.mobile
            self.customer_name = partner_id.name
            self.phone = partner_id.phone
            self.email = partner_id.email
            self.address = partner_id.type
            self.street = partner_id.street
            self.street2 = partner_id.street2
            self.city = partner_id.city
            self.state_id = partner_id.state_id and partner_id.state_id.id or False
            self.zip = partner_id.zip
            self.country_id = partner_id.country_id and partner_id.country_id.id or False
            self.partner_latitude = partner_id.partner_latitude
            self.partner_longitude = partner_id.partner_longitude
            self.date_localization = partner_id.date_localization

    def _default_company(self):
        return self.env['res.company']._company_default_get('project.details')

    def _compute_measurement_exist(self):
        for record in self:
            record.measurement_exist = False
            if record.state=='scheduled':
                team_contract_room_measurment = self.env['team.contract.room.measurement.line'].search([('appointment_id', '=', record.id)])
                if team_contract_room_measurment:
                    record.measurement_exist = True

    @api.depends('street', 'street2', 'city', 'state_id', 'zip')
    def _compute_property_address(self):
        for record in self:
            customer_address = ''
            if record.street:
                customer_address = record.street
            if record.street2:
                if not customer_address:
                    customer_address = record.street2
                else:
                    customer_address += ' ' + record.street2
            if record.city:
                if not customer_address:
                    customer_address = record.city
                else:
                    customer_address += ', ' + record.city
            if record.state_id:
                if not customer_address:
                    customer_address = record.state_id.name
                else:
                    customer_address += ', ' + record.state_id.name
            elif record.state_code:
                if not customer_address:
                    customer_address = record.state_code
                else:
                    customer_address += ', ' + record.state_code
            if record.zip:
                if not customer_address:
                    customer_address = record.zip
                else:
                    customer_address += ' ' + record.zip
            record.property_address = customer_address

    @api.depends('sale_order_ids')
    def _compute_sale_order_exists(self):
        for record in self:
            sale_order_exists = False
            if record.sale_order_ids:
                sale_order_exists = True
            record.sale_order_exists = sale_order_exists

    @api.depends('card_transaction_log_line')
    def _compute_transaction_log_exists(self):
        for record in self:
            transaction_log_exists = False
            if record.card_transaction_log_line:
                transaction_log_exists = True
            record.transaction_log_exists = transaction_log_exists

    name = fields.Char('Reference', required=True, copy=False, default='/')
    customer_name = fields.Char('Customer Name', required=False, readonly=False)
    phone = fields.Char('Phone Number',  readonly=True, states={'draft': [('readonly', False)]})
    mobile = fields.Char('Secondary Phone Number',  readonly=True, states={'draft': [('readonly', False)]})
    email = fields.Char(string='Email', readonly=True, states={'draft': [('readonly', False)]})
    user_id = fields.Many2one('res.users', string='Sales Person', required=False, default=lambda self: self.env.user,  readonly=True, states={'draft': [('readonly', False)]})
    company_id = fields.Many2one('res.company', string='Company', requires=True, default=_default_company)
    partner_id = fields.Many2one('res.partner', string='Customer',
                                 domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",  readonly=True, states={'draft': [('readonly', False)]})
    street = fields.Char(readonly=True, states={'draft': [('readonly', False)]})
    street2 = fields.Char(readonly=True, states={'draft': [('readonly', False)]})
    city = fields.Char(readonly=True, states={'draft': [('readonly', False)]})
    state_id = fields.Many2one("res.country.state", string="State", readonly=True, states={'draft': [('readonly', False)]})
    zip = fields.Char(readonly=True, states={'draft': [('readonly', False)]})
    country_id = fields.Many2one('res.country', string="Country", readonly=True, states={'draft': [('readonly', False)]})
    partner_latitude = fields.Float(string='Geo Latitude', digits=(16, 5),  readonly=True, states={'draft': [('readonly', False)]})
    partner_longitude = fields.Float(string='Geo Longitude', digits=(16, 5),  readonly=True, states={'draft': [('readonly', False)]})
    date_localization = fields.Date('On',  readonly=True, states={'draft': [('readonly', False)]})
    state = fields.Selection(selection=_STATES, string='Status', index=True, tracking=True, required=True,
                             copy=False, default='draft', readonly=True, states={'draft': [('readonly', False)]})
    appointment_date = fields.Datetime('Appointment Date', required=True, readonly=True, tracking=True, states={'draft': [('readonly', False)]})
    co_applicant = fields.Char(string='Co-Applicant', readonly=True, states={'draft': [('readonly', False)]})
    co_applicant_phone = fields.Char(string='Co-Applicant Phone')
    co_applicant_email = fields.Char(string='Co-Applicant Email')
    co_applicant_address = fields.Char(string='Co-Applicant Address')
    co_applicant_city = fields.Char(string="City")
    co_applicant_zip = fields.Char(string="Co-Applicant ZIP")
    co_applicant_state = fields.Many2one("res.country.state", string="Co-Applicant State", readonly=True, states={'draft': [('readonly', False)]})
    co_applicant_country_id = fields.Many2one('res.country', 'Co-Applicant Country', related='co_applicant_state.country_id', readonly=True)
    co_applicant_secondary_phone = fields.Char(string="Co-Applicant Secondary Phone")

    measurement_exist = fields.Boolean('Room Measurement flag',compute='_compute_measurement_exist')
    appointment_time = fields.Char('Appointment Time')
    appointment_day = fields.Date('Appointment Day')
    applicant_signature_id = fields.Many2one('ir.attachment',string="Applicant Signature")
    co_applicant_signature_id = fields.Many2one('ir.attachment',string="Co-Applicant Signature")
    applicant_initial_id = fields.Many2one('ir.attachment',string="Applicant Initial ID")
    co_applicant_initial_id = fields.Many2one('ir.attachment',string="Co-Applicant Initial ID")
    finance_application = fields.Boolean('Finance Application')
    credit_card = fields.Boolean('Credit Card')
    contract = fields.Boolean('Contract')
    applicant_signature = fields.Binary('Applicant Signature', related='applicant_signature_id.datas')
    co_applicant_signature = fields.Binary('Co-Applicant Signature', related='co_applicant_signature_id.datas')
    applicant_initial = fields.Binary('Applicant Initial', related='applicant_initial_id.datas')
    co_applicant_initial = fields.Binary('Co-Applicant Initial', related='co_applicant_initial_id.datas')

    applicant_first_name = fields.Char("Applicant First Name")
    applicant_middle_name = fields.Char("Applicant Middle Name")
    applicant_last_name = fields.Char("Applicant Last Name")

    co_applicant_first_name = fields.Char("Co-Applicant First Name")
    co_applicant_middle_name = fields.Char("Co-Applicant Middle Name")
    co_applicant_last_name = fields.Char("Co-Applicant Last Name")
    credit_application_url = fields.Char("Credit Application Url")
    sale_order_ids = fields.One2many('sale.order', 'appointment_id', 'Sale Orders')
    appointment_result = fields.Char('Appointment Result')
    what_happened_notes = fields.Char('What Happened Notes')
    whats_next_notes = fields.Char('Whats Next Notes')
    property_address = fields.Char('Property Address', compute='_compute_property_address')
    status_updated_to_i360 = fields.Boolean('Appointment Result Updated to i360', default=False)
    attachment_ids = fields.Many2many('ir.attachment', string="Screen Captures")
    sync_log_line = fields.One2many('otl.appointment.sync.log', 'appointment_id', string='i360 Sync Log')
    app_sync_log_line = fields.One2many('otl.app.appointment.sync.log', 'appointment_id', string='SalesApp Sync Log')
    api_sync_log_line = fields.One2many('otl.api.sync.log', 'appointment_id', string='API Log')
    app_screen_log_line = fields.One2many('otl.app.screen.log', 'appointment_id', string='Screen Completion Time')
    sale_order_exists = fields.Boolean('Exist Sale Order', compute='_compute_sale_order_exists')
    state_code = fields.Char('State Code')
    co_applicant_state_code = fields.Char('Co-Applicant State Code')
    additional_comments = fields.Char('Additional Comments', copy=False)
    send_physical_document = fields.Boolean('Send Physical Document', default=False, copy=False)
    card_transaction_log_line = fields.One2many('otl.card.transaction.log', 'appointment_id',
                                                string='Card Transaction Log Line')
    transaction_log_exists = fields.Boolean('Exist Transaction Logs', compute='_compute_transaction_log_exists')
    office_location_id = fields.Many2one('otl.office.location', 'Office Location', readonly=True, states={'draft': [('readonly', False)]})
    market_segment = fields.Char('Market Segment')
    app_version_id = fields.Many2one('otl.sales.app.version', 'App Version')

    @api.onchange('country_id')
    def _onchange_country_id(self):
        if self.country_id and self.country_id != self.state_id.country_id:
            self.state_id = False

    @api.onchange('state_id')
    def _onchange_state(self):
        if self.state_id.country_id:
            self.country_id = self.state_id.country_id

    @api.model
    def create(self, vals):
        if vals.get('name', '/') == '/':
            seq_date = None
            if 'appointment_date' in vals:
                seq_date = fields.Datetime.context_timestamp(self,
                                                             fields.Datetime.to_datetime(vals['appointment_date']))
            if 'company_id' in vals:
                vals['name'] = self.env['ir.sequence'].with_context(force_company=vals['company_id']).next_by_code(
                    'team.customer.appointment', sequence_date=seq_date) or _('New')
            else:
                vals['name'] = self.env['ir.sequence'].next_by_code('team.customer.appointment', sequence_date=seq_date) or _('New')

        return super(TeamCustomerAppointment, self).create(vals)

    def button_scheduled(self):
        return self.write({'state': 'scheduled'})

    def button_cancel(self):
        return self.write({'state': 'cancelled'})

    def button_done(self):
        return self.write({'state': 'done'})

    def button_draft(self):
        self.write({'state': 'draft'})

    def action_view_sale_quotation(self):
        action = self.env.ref('sale.action_quotations_with_onboarding').read()[0]
        action['context'] = {
            'search_default_partner_id': self.partner_id.id,
            'default_partner_id': self.partner_id.id,
            'default_appointment_id': self.id
        }
        action['domain'] = [('appointment_id', '=', self.id)]
        quotations = self.mapped('sale_order_ids')
        if len(quotations) == 1:
            action['views'] = [(self.env.ref('sale.view_order_form').id, 'form')]
            action['res_id'] = quotations.id
        return action

    @api.model
    def _geo_localize(self, street='', zip='', city='', state='', country=''):
        geo_obj = self.env['base.geocoder']
        search = geo_obj.geo_query_address(street=street, zip=zip, city=city, state=state, country=country)
        result = geo_obj.geo_find(search, force_country=country)
        if result is None:
            search = geo_obj.geo_query_address(city=city, state=state, country=country)
            result = geo_obj.geo_find(search, force_country=country)
        return result

    def geo_localize(self):
        # We need country names in English below
        for partner in self.with_context(lang='en_US'):
            result = self._geo_localize(partner.street,
                                        partner.zip,
                                        partner.city,
                                        partner.state_id.name,
                                        partner.country_id.name)

            if result:
                partner.write({
                    'partner_latitude': result[0],
                    'partner_longitude': result[1],
                    'date_localization': fields.Date.context_today(partner)
                })
        return True


class AppointmentSyncLog(models.Model):
    _name = 'otl.appointment.sync.log'
    _description = "i360 Appointment Sync Log"
    _order= "created_date desc"

    created_date = fields.Datetime('Created Date', default=fields.Datetime.now)
    appointment_id = fields.Many2one('team.customer.appointment', 'Appointment')
    user_id = fields.Many2one('res.users', 'User', default=lambda self: self.env.uid)
    state = fields.Selection([('success', 'Success'), ('failed', 'Failed')], string='Status', default='success')
    response = fields.Text('Sync Response')
    name = fields.Char('API')


class SalesAppAppointmentSyncLog(models.Model):
    _name = 'otl.app.appointment.sync.log'
    _description = "Sales App Appointment Sync Log"
    _order= "sync_date desc"

    sync_date = fields.Datetime('Sync Date', copy=False)
    appointment_id = fields.Many2one('team.customer.appointment', 'Appointment')
    name = fields.Text('Message')


class APISyncLog(models.Model):
    _name = 'otl.api.sync.log'
    _description = "API Sync Log"
    _order = "created_date desc"

    created_date = fields.Datetime('Created Date', default=fields.Datetime.now)
    appointment_id = fields.Many2one('team.customer.appointment', 'Appointment')
    user_id = fields.Many2one('res.users', 'User', default=lambda self: self.env.uid)
    state = fields.Selection([('success', 'Success'), ('failed', 'Failed')], string='Status', default='success')
    response = fields.Text('Sync Response')
    data = fields.Text('API Data')
    name = fields.Char('API')

    def create_api_log(self, url, data, uid, result):
        appointment_id = data.get('appointment_id', False)
        state = 'success'
        if result.get('result', False) == 'Failed':
            state = 'failed'
        if uid and appointment_id and self.env['team.customer.appointment'].browse(int(appointment_id)).exists():
            self.create({
                'name': url,
                'appointment_id': int(appointment_id),
                'user_id': uid,
                'data': data,
                'response': result,
                'state': state,
            })
        return True


class AppScreenLog(models.Model):
    _name = 'otl.app.screen.log'
    _description = "App Screen Completion Log"
    _order = "completion_date desc"

    completion_date = fields.Datetime('Completion Date', default=fields.Datetime.now)
    appointment_id = fields.Many2one('team.customer.appointment', 'Appointment')
    user_id = fields.Many2one('res.users', 'User', default=lambda self: self.env.uid)
    name = fields.Char('Screen Name')

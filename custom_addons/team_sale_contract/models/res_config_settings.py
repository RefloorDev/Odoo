# -*- coding: utf-8 -*-
from odoo import models, fields, api

class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    sale_contract_tmpl_id = fields.Many2one('otl_document_sign.template', string='Sign Template', config_parameter='team_sale_contract.sale_contract_tmpl_id',)
    sale_contract_tmpl_id_ncp = fields.Many2one('otl_document_sign.template',string='Sign Template Without Co-Applicant', config_parameter='team_sale_contract.sale_contract_tmpl_id_ncp')
    credit_application_tmpl_id = fields.Many2one('otl_document_sign.template', string='Credit Application Template', config_parameter='team_sale_contract.credit_application_tmpl_id')
    credit_application_tmpl_id_ncp = fields.Many2one('otl_document_sign.template', string='Credit Application Template Without Co-Applicant', config_parameter='team_sale_contract.credit_application_tmpl_id_ncp')
    google_auth_attachment_id = fields.Many2one('ir.attachment', string='Google Service Auth File', config_parameter='team_sale_contract.google_auth_attachment_id')
    admin_fee = fields.Float("Admin Fee", config_parameter='team_sale_contract.admin_fee')
    min_sale_price = fields.Float("Minimum Sale Price", config_parameter='team_sale_contract.min_sale_price')
    max_no_transitions = fields.Integer("Maximum No. of Transitions Allowed", config_parameter='team_sale_contract.max_no_transitions')
    doc_status_message = fields.Char("Document InCompletion Message", config_parameter='team_sale_contract.doc_status_message')
    doc_completion_message = fields.Char("Document Completion Message", config_parameter='team_sale_contract.doc_completion_message')
    payment_plan_id = fields.Many2one('product.template', string='Default Payment Plan', config_parameter='team_sale_contract.payment_plan_id')
    enable_api_queue_system = fields.Boolean('Enable API Queue System', default=False, config_parameter='team_sale_contract.enable_api_queue_system')
    enable_additional_comment_api = fields.Boolean('Enable Additional Comments API', default=False, config_parameter='team_sale_contract.enable_additional_comment_api')
    installer_date_range_limit = fields.Integer("Installer Date Range Limit", default=30, config_parameter='team_sale_contract.installer_date_range_limit')
    enable_geolocation = fields.Boolean('Enable Geolocation Tracking', default=False, config_parameter='team_sale_contract.enable_geolocation')
    geolocation_radius_limit = fields.Integer("Geolocation Radius Limit", config_parameter='team_sale_contract.geolocation_radius_limit')
    google_bucket_name = fields.Char("Google Bucket Name", config_parameter='team_sale_contract.google_bucket_name')
    max_stair_width = fields.Float('Maximum Stair Width', default=0.0, config_parameter='team_sale_contract.max_stair_width')
    min_down_payment_amount = fields.Float('Minimum Down Payment Amount', default=0.0, config_parameter='team_sale_contract.min_down_payment_amount')
    max_i360_sync_retry_limit = fields.Integer('Maximum Allowed i360 Sync Retry Duration', default=24, config_parameter='team_sale_contract.max_i360_sync_retry_limit')
    send_review_success_message = fields.Char('Send Review Success Message', default='Review link sent successfully.', config_parameter="team_sale_contract.send_review_success_message")
    send_review_failure_message = fields.Char('Send Review Failure Message', default='Something went wrong while sending the review link.', config_parameter="team_sale_contract.send_review_failure_message")
    destination_selection_consent_message = fields.Char('Destination Selection Consent Message', default='By submitting this form and signing up for texts, you consent to receive customer support and informational text messages from Destination Motivation at the number provided. Msg & data rates may apply. Msg frequency varies. Unsubscribe at any time by replying STOP. Reply HELP for help. Privacy Policy & terms based on vacation-type selected: Condo/Resort Terms or Cruise Terms', config_parameter="team_sale_contract.destination_selection_consent_message")
    enable_destination_selection = fields.Boolean("Enable Destination Selection", default=False, config_parameter="team_sale_contract.enable_destination_selection")
    address_visible_time_limit = fields.Integer('Maximum Allowed Time Limit to Show Full Address Prior to Appointment', default=120, config_parameter='team_sale_contract.address_visible_time_limit')
    version_mismatch_message = fields.Char('Version Mismatch Message', default="Please contact your administrator in order to update to the newest version.", config_parameter="team_sale_contract.version_mismatch_message")


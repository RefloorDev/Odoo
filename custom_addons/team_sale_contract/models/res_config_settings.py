# -*- coding: utf-8 -*-

from odoo import fields, models ,api
from ast import literal_eval


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'
    sale_contract_tmpl_id = fields.Many2one('otl_document_sign.template',string='Sign Template')
    sale_contract_tmpl_id_ncp = fields.Many2one('otl_document_sign.template',string='Sign Template Without Co-Applicant')
    credit_application_tmpl_id = fields.Many2one('otl_document_sign.template', string='Credit Application Template')
    credit_application_tmpl_id_ncp = fields.Many2one('otl_document_sign.template', string='Credit Application Template Without Co-Applicant')
    admin_fee = fields.Float("Admin Fee")
    min_sale_price = fields.Float("Minimum Sale Price")
    max_no_transitions = fields.Integer("Maximum No. of Transitions Allowed")
    doc_status_message = fields.Char("Document InCompletion Message")
    doc_completion_message = fields.Char("Document Completion Message")
    payment_plan_id = fields.Many2one('product.template', string='Default Payment Plan')
    enable_api_queue_system = fields.Boolean('Enable API Queue System', default=False)

    @api.model
    def get_values(self):
        res = super(ResConfigSettings, self).get_values()

        params = self.env['ir.config_parameter'].sudo()
        sale_contract_tmpl_id = params.get_param('sale_contract_tmpl_id', default=False)
        sale_contract_tmpl_id_ncp = params.get_param('sale_contract_tmpl_id_ncp', default=False)
        credit_application_tmpl_id = params.get_param('credit_application_tmpl_id',default=False)
        credit_application_tmpl_id_ncp = params.get_param('credit_application_tmpl_id_ncp', default=False)
        admin_fee = params.get_param('admin_fee',default=0.0)
        min_sale_price = params.get_param('min_sale_price',default=0.0)
        max_no_transitions = params.get_param('max_no_transitions',default=0)
        doc_status_message = params.get_param('doc_status_message', default='It seems that you have not filled the required data in the contract. Please ensure all data are updated before proceeding!')
        doc_completion_message = params.get_param('doc_completion_message', default='Your credit/debit card payment is going to process.')
        payment_plan_id = params.get_param('payment_plan_id', default=False)
        enable_api_queue_system = str(params.get_param('enable_api_queue_system', default=False))


        res.update({
            'sale_contract_tmpl_id':int(sale_contract_tmpl_id),
            'sale_contract_tmpl_id_ncp':int(sale_contract_tmpl_id_ncp),
            'credit_application_tmpl_id':int(credit_application_tmpl_id),
            'credit_application_tmpl_id_ncp':int(credit_application_tmpl_id_ncp),
            'admin_fee':float(admin_fee),
            'min_sale_price':float(min_sale_price),
            'max_no_transitions':int(max_no_transitions),
            'doc_status_message':doc_status_message,
            'doc_completion_message':doc_completion_message,
            'payment_plan_id': int(payment_plan_id),
            'enable_api_queue_system': eval(enable_api_queue_system),
        })
        return res

    def set_values(self):
        super(ResConfigSettings, self).set_values()
        self.env['ir.config_parameter'].sudo().set_param("sale_contract_tmpl_id", self.sale_contract_tmpl_id.id)
        self.env['ir.config_parameter'].sudo().set_param("sale_contract_tmpl_id_ncp", self.sale_contract_tmpl_id_ncp.id)
        self.env['ir.config_parameter'].sudo().set_param("credit_application_tmpl_id", self.credit_application_tmpl_id.id)
        self.env['ir.config_parameter'].sudo().set_param("credit_application_tmpl_id_ncp",self.credit_application_tmpl_id_ncp.id)
        self.env['ir.config_parameter'].sudo().set_param("admin_fee",self.admin_fee)
        self.env['ir.config_parameter'].sudo().set_param("min_sale_price",self.min_sale_price)
        self.env['ir.config_parameter'].sudo().set_param("max_no_transitions",self.max_no_transitions)
        self.env['ir.config_parameter'].sudo().set_param("doc_status_message", self.doc_status_message)
        self.env['ir.config_parameter'].sudo().set_param("doc_completion_message", self.doc_completion_message)
        self.env['ir.config_parameter'].sudo().set_param("payment_plan_id", self.payment_plan_id.id)
        self.env['ir.config_parameter'].sudo().set_param("enable_api_queue_system", self.enable_api_queue_system or 'False')


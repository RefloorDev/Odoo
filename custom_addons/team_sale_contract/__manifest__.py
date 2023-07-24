# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Sale Contract',
    'version': '1.1',
    'category': 'Sales/Sales',
    'author': 'One Team US LLC',
    'website': 'https://oneteam.us/',
    'summary': 'Sale Contract Creation & Configurations',
    'description': """
This module customizing sale module to create a sale contract & followups.
    """,
    'depends': ['sale', 'sale_management', 'base_geolocalize','otl_document_sign', 'payment_bancard', 'stock'],
    'data': [
        'security/ir.model.access.csv',
        'security/user_security.xml',
        'data/appointment_sequence_data.xml',
        'data/payment_data.xml',
        'data/cron_data.xml',
        'views/master_configuration_views.xml',
        'views/quote_question_views.xml',
        'views/team_customer_appointment_view.xml',
        'views/sale_contract_views.xml',
        'views/sale_order_contract_views.xml',
        'views/res_config_settings_views.xml',
    ],
    
    'installable': True,
    'auto_install': False
}

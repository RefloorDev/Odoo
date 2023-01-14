# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'API Configurations',
    'version': '1.1',
    'summary': 'Module for setup API Configurations',
    'description': "",
    "author": "One Team US LLC",
    'website': 'https://www.oneteam.us/',
    'depends': ['base', 'base_setup'],
    'data': [
        'security/dashboard_security.xml',
        'security/ir.model.access.csv',
        'views/res_users_views.xml',
        'views/dashboard_icon_views.xml',
        'views/app_versions_views.xml',
        'views/push_configuration_views.xml',
        'views/res_company_view.xml',
    ],
}

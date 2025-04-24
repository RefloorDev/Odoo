# -*- coding: utf-8 -*-
{
    'name': 'API Configurations',
    'version': '1.1',
    'summary': 'Module for setup API Configurations',
    'description': "",
    "author": "Sagar Mokariya",
    'website': 'https://www.xeonglobal.us/',
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
    'license': 'OPL-1',
}

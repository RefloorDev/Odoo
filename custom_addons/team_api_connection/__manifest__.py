# -*- coding: utf-8 -*-
{
    'name': 'Team API Connection ',
    'version': '1.1',
    'summary': 'API',
    'description': "",
    "author": "Sagar Mokariya",
    'website': 'https://www.xeonglobal.com',
    'depends': ['team_api_configuration', 'team_sale_contract', 'otl_user_case_insensitive_login'],
    'data': [
        'security/ir.model.access.csv',
        'data/cron_improveit_api.xml',
        'data/email_template_data.xml',
        'views/appointment_api_configuration.xml',
        'wizard/change_improveit_appointment_wizard_views.xml',
        'views/appointment_view.xml',
    ],
    'qweb': [
        ],
    'installable': True,
    'external_dependencies': {
        'python': ['fusion_refloor'],
    },
    'license': 'OPL-1',
}

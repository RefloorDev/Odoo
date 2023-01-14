# -*- coding: utf-8 -*-
{
    'name': 'Team API Connection ',
    'version': '1.1',
    'summary': 'API',
    'description': "",
    "author": "One Team US LLC",
    'website': 'https://oneteam.us/',
    'depends': ['team_api_configuration', 'team_sale_contract', 'otl_user_case_insensitive_login'],
    'data': [
        'security/ir.model.access.csv',
        'data/cron_improveit_api.xml',
        'views/appointment_api_configuration.xml',
        'views/appointment_view.xml'
    ],
    'qweb': [
        ],
    'installable': True,
}

# Copyright (C) 2020 One Team US LLC
# <https://www.oneteam.us>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    'name': "Default Timezone",
    'summary': "Set Default Timezone for Users and Partners",
    'version': '0.0.1',
    'category': 'Extra Tools',
    'website': 'https://oneteam.us/',
    'author': 'One Team US LLC',
    'application': False,
    'installable': True,
    'depends': [
        'base', 'base_setup'
    ],
    'data': [
        'views/res_config_settings_view.xml',
    ],
}
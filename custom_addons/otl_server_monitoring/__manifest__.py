# Copyright (C) 2024 One Team US LLC
# <https://www.oneteam.us>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    'name': "Server Monitoring",
    'summary': "Tool for Server Memory, CPU and disk space logs",
    'version': '0.0.1',
    'category': 'Extra Tools',
    'website': 'https://oneteam.us/',
    'author': 'One Team US LLC',
    'application': False,
    'installable': True,
    'depends': [
        'base'
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/cron_data.xml',
        'data/sequence_data.xml',
        'views/server_monitor_log_view.xml'

    ],
}
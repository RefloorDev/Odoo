# -*- coding: utf-8 -*-
{
    'name': "Server Monitoring",
    'summary': "Tool for Server Memory, CPU and disk space logs",
    'version': '0.0.1',
    'category': 'Extra Tools',
    'website': 'https://www.xeonglobal.com/',
    'author': 'Sagar Mokariya',
    'depends': ['base'],
    'data': [
        'security/ir.model.access.csv',
        'data/cron_data.xml',
        'data/sequence_data.xml',
        'views/server_monitor_log_view.xml'
    ],
    'license': 'OPL-1',
    'application': False,
    'installable': True,
}

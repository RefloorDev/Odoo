# -*- coding: utf-8 -*-

{
    'name': 'OTL Document Sign',
    'version': '1.0',
    'category': 'Sales',
    'author': 'One Team US LLC',
    'summary': "Send Documents for Signing",
    'description': """
    """,
    'website': '',
    'depends': ['mail', 'attachment_indexation', 'portal', 'sms','base','sale'],
    'data': [
         'security/security.xml',
        'security/ir.model.access.csv',
        'views/sign_template_views_mobile.xml',
        'wizard/sign_send_request_views.xml',
        'wizard/sign_template_share_views.xml',
        'wizard/sign_request_send_copy_views.xml',
        'views/sign_request_templates.xml',
        'views/sign_template_templates.xml',
        'views/sign_request_views.xml',
        'views/sign_template_views.xml',
        'views/sign_log_views.xml',
        'views/res_users_views.xml',
        'views/res_partner_views.xml',
        'wizard/create_sign_template_view.xml',
        'report/sign_log_reports.xml',
        'data/sign_data.xml',
    ],
    'qweb': ['static/src/xml/*.xml'],
    'demo': [
        'data/sign_demo.xml',
    ],
    'application': True,
    'installable': True,
}

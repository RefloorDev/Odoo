# -*- coding: utf-8 -*-

{
    'name': 'Bancard Payment Acquirer',
    'category': 'Accounting/Payment',
    'summary': 'Payment Acquirer: Bancard Implementation',
    'version': '1.0',
    'description': """Bancard Payment Acquirer""",
    'depends': ['payment'],
    'data': [
        'views/payment_views.xml',
        'views/payment_bancard_templates.xml',
        'data/payment_acquirer_data.xml',
    ],
    'installable': True,
    'post_init_hook': 'create_missing_journal_for_acquirers',
}

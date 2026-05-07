# -*- coding: utf-8 -*-
{
    'name': 'Payment Provider: CardPointe',
    'version': '18.0.1.0.0',
    'category': 'Accounting/Payment Providers',
    'summary': 'CardPointe payment gateway integration supporting Credit/Debit Cards and ACH payments',
    'description': """
CardPointe Payment Gateway Integration for Odoo 18
===================================================

This module integrates the CardPointe payment gateway into Odoo 18's payment framework.

Features:
---------
* Credit/Debit Card payments via CardPointe API
* ACH (Bank Transfer) payments via CardPointe API
* Tokenization support for saved payment methods
* Test/Sandbox and Production environment support
* Full transaction lifecycle management (authorize, capture, void, refund)
* Seamless integration with Odoo's accounting and invoicing workflows
* PCI-compliant card data handling via CardSecure tokenization

Configuration:
--------------
1. Go to Accounting > Configuration > Payment Providers
2. Enable CardPointe provider
3. Enter your Merchant ID, API username, and API password
4. Configure the environment (Test or Production)
5. Save and activate the provider

Supported Payment Methods:
---------------------------
* Credit Cards (Visa, MasterCard, American Express, Discover)
* Debit Cards
* ACH / eCheck (Bank Account) transfers
    """,
    'author': 'Custom Development',
    'website': 'https://www.cardconnect.com/cardpointe',
    'depends': [
        'payment',
        'account',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/payment_cardpoint_templates.xml',
        'views/payment_provider_views.xml',
        'views/payment_transaction_views.xml',
        'data/payment_provider_data.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'otl_payment_cardpointe/static/src/css/payment_cardpoint.css',
            'otl_payment_cardpointe/static/src/js/payment_cardpoint_form.js',
        ],
        'web.assets_backend': [
            'otl_payment_cardpointe/static/src/css/payment_cardpoint_backend.css',
        ],
    },
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'license': 'LGPL-3',
    'installable': True,
    'auto_install': False,
    'application': False,
}

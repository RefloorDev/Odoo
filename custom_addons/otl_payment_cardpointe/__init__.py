# -*- coding: utf-8 -*-

from . import controllers
from . import models

from odoo.addons.payment import setup_provider, reset_payment_provider


def post_init_hook(env):
    setup_provider(env, 'cardpoint')
    # Set module_id so that module_state='installed' and the standard
    # Published/Unpublished button, ribbons, and banners appear correctly.
    provider = env['payment.provider'].search([('code', '=', 'cardpoint')], limit=1)
    if provider:
        module = env['ir.module.module'].search(
            [('name', '=', 'otl_payment_cardpointe')], limit=1
        )
        if module:
            provider.write({'module_id': module.id})


def uninstall_hook(env):
    reset_payment_provider(env, 'cardpoint')

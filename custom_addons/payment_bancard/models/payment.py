# coding: utf-8

import json
import logging
from .bancard_request import BancardAPI
from datetime import datetime
import time

import dateutil.parser
import pytz
from werkzeug import urls

from odoo import api, fields, models, _
from odoo.addons.payment.models.payment_acquirer import ValidationError
from odoo.addons.payment_paypal.controllers.main import PaypalController
from odoo.tools.float_utils import float_compare


_logger = logging.getLogger(__name__)


class AcquirerPaypal(models.Model):
    _inherit = 'payment.acquirer'

    provider = fields.Selection(selection_add=[('bancard', 'Bancard')])
    bancard_login_id = fields.Char('API Login Id', required_if_provider='bancard', groups='base.group_user')
    bancard_transaction_key = fields.Char(string='API Transaction Key', groups='base.group_user')

    @api.model
    def bancard_s2s_form_process(self, data):
        values = {
            'cc_number': data.get('cc_number'),
            'cc_holder_name': data.get('cc_holder_name'),
            'cc_expiry': data.get('cc_expiry'),
            'cc_cvc': data.get('cc_cvc'),
            'cc_brand': data.get('cc_brand'),
            'acquirer_id': int(data.get('acquirer_id')),
            'partner_id': int(data.get('partner_id'))
        }
        print(values)
        PaymentMethod = self.env['payment.token'].sudo().create(values)
        return PaymentMethod

    def bancard_s2s_form_validate(self, data):
        error = dict()
        mandatory_fields = ["cc_number", "cc_cvc", "cc_holder_name", "cc_expiry", "cc_brand", "zip"]
        # Validation
        for field_name in mandatory_fields:
            if not data.get(field_name):
                error[field_name] = 'missing'
        if data['cc_expiry']:
            # FIX we split the date into their components and check if there is two components containing only digits
            # this fixes multiples crashes, if there was no space between the '/' and the components the code was crashing
            # the code was also crashing if the customer was proving non digits to the date.
            cc_expiry = [i.strip() for i in data['cc_expiry'].split('/')]
            if len(cc_expiry) != 2 or any(not i.isdigit() for i in cc_expiry):
                return False
            try:
                if datetime.now().strftime('%y%m') > datetime.strptime('/'.join(cc_expiry), '%m/%y').strftime('%y%m'):
                    return False
            except ValueError:
                return False
        return False if error else True


class TxBancard(models.Model):
    _inherit = 'payment.transaction'

    def bancard_s2s_do_transaction(self, **data):
        self.ensure_one()
        transaction = BancardAPI(self.acquirer_id)

        res = transaction.auth_and_capture(self.payment_token_id, round(self.amount, self.currency_id.decimal_places), self.reference, data)
        return self._bancard_s2s_validate_tree(res)

    def bancard_s2s_capture_transaction(self):
        self.ensure_one()
        transaction = BancardAPI(self.acquirer_id)
        tree = transaction.capture(self.acquirer_reference or '', round(self.amount, self.currency_id.decimal_places))
        return self._bancard_s2s_validate_tree(tree)

    def bancard_s2s_void_transaction(self):
        self.ensure_one()
        transaction = BancardAPI(self.acquirer_id)
        tree = transaction.void(self.acquirer_reference or '')
        return self._bancard_s2s_validate_tree(tree)

    def _bancard_s2s_validate_tree(self, tree):
        return self._bancard_s2s_validate(tree)

    def _bancard_s2s_validate(self, tree):
        if self.state == 'done':
            _logger.warning('Bancard: trying to validate an already validated tx (ref %s)' % self.reference)
            return True
        status_code = tree.get('x_response_code', '0')
        if status_code == 'AUTH':
            if tree.get('x_type').lower() in ['auth_capture', 'prior_auth_capture']:
                init_state = self.state
                self.write({
                    'acquirer_reference': tree.get('x_trans_id'),
                    'date': fields.Datetime.now(),
                })

                self._set_transaction_done()

                if init_state != 'authorized':
                    self.execute_callback()
            if tree.get('x_type').lower() == 'auth_only':
                self.write({'acquirer_reference': tree.get('x_trans_id')})
                self._set_transaction_authorized()
                self.execute_callback()
            if tree.get('x_type').lower() == 'void':
                self._set_transaction_cancel()
            return True
        elif status_code in ['CALL', 'RETRY']:
            self.write({'acquirer_reference': tree.get('x_trans_id')})
            self._set_transaction_pending()
            return True
        elif status_code == 'DENY':
            self.write({'acquirer_reference': tree.get('x_trans_id')})
            self._set_transaction_cancel()
            return True
        else:
            error = tree.get('x_response_reason_text')
            _logger.info(error)
            self.write({
                'state_message': error,
                'acquirer_reference': tree.get('x_trans_id'),
            })
            self._set_transaction_cancel()
            return False


class PaymentToken(models.Model):
    _inherit = 'payment.token'

    @api.model
    def bancard_create(self, values):
        if values.get('cc_number'):
            values['cc_number'] = values['cc_number'].replace(' ', '')
            alias = 'ODOO-NEW-ALIAS-%s' % time.time()
            return {
                'acquirer_ref': alias,
                'name': 'XXXXXXXXXXXX%s - %s' % (values['cc_number'][-4:], values['cc_holder_name'])
            }
        return {}

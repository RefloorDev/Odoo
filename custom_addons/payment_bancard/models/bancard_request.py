# -*- coding: utf-8 -*-
import json
import logging
import requests

from uuid import uuid4

from odoo import _
from odoo.exceptions import UserError

from odoo.addons.payment.models.payment_acquirer import _partner_split_name

_logger = logging.getLogger(__name__)


class BancardAPI():
    """International Bancard Gateway API integration.

    This class allows contacting the International Bancard API with simple operation
    requests. It implements a *very limited* subset of the complete API
    (https://developer.internationalbancard.com/); namely:
        - Customer Profile/Payment Profile creation
        - Transaction authorization/capture/voiding
    """

    AUTH_ERROR_STATUS = 3

    def __init__(self, acquirer):
        """Initiate the environment with the acquirer data.

        :param record acquirer: payment.acquirer account that will be contacted
        """
        if acquirer.state == 'test':
            self.url = 'https://cc-sand8.intlbancardgw.com:8665/'
        else:
            self.url = 'https://cc-sand8.intlbancardgw.com:8665/'

        self.state = acquirer.state
        self.name = acquirer.bancard_login_id
        self.transaction_key = acquirer.bancard_transaction_key

    def _authorize_request(self, data):
        _logger.info('_authorize_request: Sending values to URL %s, values:\n%s', self.url, data)
        resp = requests.post(self.url, json.dumps(data))
        resp.raise_for_status()
        resp = json.loads(resp.content)
        _logger.info("_authorize_request: Received response:\n%s", resp)
        response_data = resp.get('MonetraResp', {})
        messages = response_data.get('DataTransferStatus', {})
        if messages and messages.get('code') == 'FAIL':
            return {
                'err_code': messages.get('message')[0].get('code'),
                'err_msg': messages.get('message')[0].get('verbiage')
            }

        return resp

    # Transaction management
    def auth_and_capture(self, token, amount, reference, data):
        """Authorize and capture a payment for the given amount.

        Authorize and immediately capture a payment for the given payment.token
        record for the specified amount with reference as communication.

        :param record token: the payment.token record that must be charged
        :param str amount: transaction amount (up to 15 digits with decimal point)
        :param str reference: used as "invoiceNumber" in the Authorize.net backend

        :return: a dict containing the response code, transaction id and transaction type
        :rtype: dict
        """
        values = {
           "MonetraTrans": {
              "Trans": {
                  "Username": self.name,
                  "Password": self.transaction_key,
                  "Action": "sale",
                  "Account": data.get('cc_number', ''),
                  "cardholdername": data.get('cc_holder_name', ''),
                  "ExpDate": data.get('cc_expiry', ''),
                  # "cv": data.get('cc_cvc', ''),
                  "Amount": str(amount),
                  "Zip": data.get('zip', ''),
                  "Ordernum": reference,
                  "Comments": data.get('comments', '')
                  }
           }
        }
        response = self._authorize_request(values)

        if response and response.get('err_code'):
            return {
                'x_response_code': self.AUTH_ERROR_STATUS,
                'x_response_reason_text': response.get('err_msg')
            }
        trans_data = response.get('MonetraResp', {}).get('Trans', {})
        return {
            'x_response_code': trans_data.get('code', ''),
            'x_trans_id': trans_data.get('ttid', ''),
            'x_type': 'auth_capture'
        }

    def capture(self, transaction_id, amount):
        """Capture a previously authorized payment for the given amount.

        Capture a previsouly authorized payment. Note that the amount is required
        even though we do not support partial capture.

        :param str transaction_id: id of the authorized transaction in the
                                   Authorize.net backend
        :param str amount: transaction amount (up to 15 digits with decimal point)

        :return: a dict containing the response code, transaction id and transaction type
        :rtype: dict
        """
        values = {
            "MonetraTrans": {
                "Trans": {
                    "Username": self.name,
                    "Password": self.transaction_key,
                    "Action": "capture",
                    "ttid": transaction_id,
                    "Amount": str(amount)
                }
            }
        }

        response = self._authorize_request(values)

        if response and response.get('err_code'):
            return {
                'x_response_code': self.AUTH_ERROR_STATUS,
                'x_response_reason_text': response.get('err_msg')
            }
        trans_data = response.get('MonetraResp', {}).get('Trans', {})
        return {
            'x_response_code': trans_data.get('code', ''),
            'x_trans_id': trans_data.get('ttid', ''),
            'x_type': 'prior_auth_capture'
        }

    def void(self, transaction_id):
        """Void a previously authorized payment.

        :param str transaction_id: the id of the authorized transaction in the
                                   Authorize.net backend

        :return: a dict containing the response code, transaction id and transaction type
        :rtype: dict
        """
        values = {
            "MonetraTrans": {
                "Trans": {
                    "Username": self.name,
                    "Password": self.transaction_key,
                    "Action": "void",
                    "ttid": transaction_id
                }
            }
        }

        response = self._authorize_request(values)

        if response and response.get('err_code'):
            return {
                'x_response_code': self.AUTH_ERROR_STATUS,
                'x_response_reason_text': response.get('err_msg')
            }

        trans_data = response.get('MonetraResp', {}).get('Trans', {})
        return {
            'x_response_code': trans_data.get('code', ''),
            'x_trans_id': trans_data.get('ttid', ''),
            'x_type': 'void'
        }

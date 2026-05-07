# -*- coding: utf-8 -*-

import logging
import pprint

from odoo import _, http
from odoo.exceptions import ValidationError
from odoo.http import request

from odoo.addons.payment import utils as payment_utils

_logger = logging.getLogger(__name__)


class CardPointeController(http.Controller):

    @http.route('/payment/cardpoint/payment', type='json', auth='public')
    def cardpoint_payment(
        self, reference, partner_id, access_token,
        payment_method_code='card',
        card_number='', cardholder_name='', expiry='', cvv='',
        routing_number='', account_number='', account_holder_name='',
        account_type='checking', **kwargs
    ):
        """ Make a payment request and handle the response.

        :param str reference: The reference of the transaction
        :param int partner_id: The partner making the transaction, as a `res.partner` id
        :param str access_token: The access token used to verify the provided values
        :return: None
        """
        _logger.info(
            "CardPointe: Verifying security token | Reference: %s | Partner: %s | Token: %s",
            reference, partner_id, access_token,
        )

        # Check that the transaction details have not been altered
        if not payment_utils.check_access_token(access_token, reference, partner_id):
            _logger.warning("CardPointe: Security token verification FAILED")
            raise ValidationError(
                "CardPointe: " + _("Received tampered payment request data.")
            )

        # Retrieve the transaction
        tx_sudo = request.env['payment.transaction'].sudo().search(
            [('reference', '=', reference)]
        )
        if not tx_sudo:
            raise ValidationError(_("Transaction not found."))

        # Lock the transaction row to prevent concurrent updates
        tx_sudo.env.cr.execute(
            "SELECT 1 FROM payment_transaction WHERE id = %s FOR NO KEY UPDATE",
            [tx_sudo.id],
        )

        # Build payment data
        payment_data = {
            'payment_type': payment_method_code,
            'token': card_number,
            'expiry': expiry,
            'cvv': cvv,
            'card_name': cardholder_name,
            'routing_number': routing_number,
            'account_number': account_number,
            'account_name': account_holder_name,
            'account_type': account_type,
        }

        # Process the payment
        tx_sudo._cardpoint_process_payment(payment_data)

        _logger.info(
            "CardPointe payment processed for transaction with reference %s, state: %s",
            reference, tx_sudo.state,
        )

    @http.route(
        '/payment/cardpoint/webhook',
        type='json',
        auth='public',
        methods=['POST'],
        csrf=False,
    )
    def cardpoint_webhook(self, **kwargs):
        """ Handle asynchronous CardPointe webhook notifications. """
        try:
            notification_data = request.get_json_data() or {}
        except Exception:
            notification_data = kwargs

        _logger.info(
            "CardPointe webhook received:\n%s",
            pprint.pformat(notification_data),
        )

        if not notification_data:
            return {'status': 'ok'}

        tx_ref = notification_data.get('orderid') or notification_data.get('retref')
        if not tx_ref:
            _logger.warning("CardPointe webhook: No identifier in notification data.")
            return {'status': 'ok'}

        try:
            tx = request.env['payment.transaction'].sudo()._get_tx_from_notification_data(
                'cardpoint', notification_data,
            )
            if tx:
                tx._handle_notification_data('cardpoint', notification_data)
        except ValidationError as e:
            _logger.warning("CardPointe webhook error: %s", str(e))

        return {'status': 'ok'}

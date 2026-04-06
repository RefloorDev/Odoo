# -*- coding: utf-8 -*-

import logging
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.payment import utils as payment_utils

_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    """
    CardPointe Payment Transaction.

    Extends the base payment.transaction model to handle CardPointe-specific
    transaction data, API calls, and status updates.

    Follows the same pattern as payment_authorize and payment_stripe modules.
    """
    _inherit = 'payment.transaction'

    # ------------------------------------------------------------------
    # CardPointe-specific transaction fields
    # ------------------------------------------------------------------
    cardpoint_retref = fields.Char(
        string='CardPointe Retrieval Ref',
        readonly=True,
        help='CardPointe retrieval reference number (retref) for this transaction.',
    )
    cardpoint_authcode = fields.Char(
        string='Authorization Code',
        readonly=True,
        help='Authorization code returned by the card network.',
    )
    cardpoint_respcode = fields.Char(
        string='Response Code',
        readonly=True,
        help='CardPointe response code (A=Approved, etc.).',
    )
    cardpoint_resptext = fields.Char(
        string='Response Message',
        readonly=True,
        help='Human-readable response message from CardPointe.',
    )
    cardpoint_payment_type = fields.Selection(
        selection=[
            ('card', 'Credit/Debit Card'),
            ('ach_direct_debit', 'ACH / Bank Transfer'),
        ],
        string='Payment Type',
        default='card',
        help='Payment method used for this transaction.',
    )
    cardpoint_account_last4 = fields.Char(
        string='Last 4 Digits',
        readonly=True,
        help='Last 4 digits of the card or bank account.',
    )
    cardpoint_account_type = fields.Char(
        string='Account Type',
        readonly=True,
        help='Card brand or bank account type (e.g., VISA, MC, ECHK).',
    )
    cardpoint_profile_id = fields.Char(
        string='CardPointe Profile ID',
        readonly=True,
        help='Stored profile ID for tokenized payment methods.',
    )
    cardpoint_acct_id = fields.Char(
        string='CardPointe Account ID',
        readonly=True,
        help='Account ID within a stored profile.',
    )
    cardpoint_avs_resp = fields.Char(
        string='AVS Response',
        readonly=True,
        help='Address Verification Service response code.',
    )
    cardpoint_cvv_resp = fields.Char(
        string='CVV Response',
        readonly=True,
        help='CVV verification response code.',
    )
    cardpoint_batch_id = fields.Char(
        string='Batch ID',
        readonly=True,
        help='CardPointe batch ID for settlement tracking.',
    )

    # ------------------------------------------------------------------
    # _get_specific_processing_values - generate HMAC access token
    # ------------------------------------------------------------------
    def _get_specific_processing_values(self, processing_values):
        """ Override of payment to return an access token as provider-specific processing values.

        Note: self.ensure_one() from `_get_processing_values`

        :param dict processing_values: The generic processing values of the transaction
        :return: The dict of provider-specific processing values
        :rtype: dict
        """
        res = super()._get_specific_processing_values(processing_values)
        if self.provider_code != 'cardpoint':
            return res

        return {
            'access_token': payment_utils.generate_access_token(
                processing_values['reference'], processing_values['partner_id']
            )
        }

    # ------------------------------------------------------------------
    # _get_specific_rendering_values - called during checkout
    # ------------------------------------------------------------------
    def _get_specific_rendering_values(self, processing_values):
        """
        Prepare values for rendering the CardPointe payment form.

        Called by Odoo's payment framework when building the checkout page.
        Returns a dict of values passed to the payment form template.

        :param dict processing_values: Base processing values from the framework
        :return: dict with CardPointe-specific rendering values
        """
        res = super()._get_specific_rendering_values(processing_values)
        if self.provider_code != 'cardpoint':
            return res

        provider = self.provider_id

        rendering_values = {
            'tx_ref': self.reference,
            'amount': self.amount,
            'currency_code': self.currency_id.name,
            'merchant_id': provider.cardpoint_merchant_id,
            'show_card': provider.cardpoint_show_card,
            'show_ach': provider.cardpoint_show_ach,
            'require_cvv': provider.cardpoint_require_cvv,
            'require_avs': provider.cardpoint_require_avs,
            'enable_tokenization': provider.cardpoint_enable_tokenization,
            'is_test': provider.state == 'test',
            'partner_name': self.partner_name or '',
            'partner_email': self.partner_email or '',
            'partner_phone': self.partner_phone or '',
            'partner_street': self.partner_address or '',
            'partner_city': self.partner_city or '',
            'partner_zip': self.partner_zip or '',
            'partner_country': self.partner_country_id.code if self.partner_country_id else '',
            'partner_state': self.partner_state_id.code if self.partner_state_id else '',
        }
        return rendering_values

    # ------------------------------------------------------------------
    # _send_payment_request - initiates the transaction with CardPointe
    # ------------------------------------------------------------------
    def _send_payment_request(self):
        """
        Initiate a payment request to CardPointe.

        Called when processing a payment from a stored token or during
        automatic charge flows. For new card/ACH entries, the request
        is sent from the controller after form submission.
        """
        super()._send_payment_request()
        if self.provider_code != 'cardpoint':
            return

        if not self.token_id:
            raise UserError(_('No payment token found. Please complete the payment form.'))

        _logger.info(
            "CardPointe: Sending payment request for tx %s using token %s",
            self.reference,
            self.token_id.id,
        )

        provider = self.provider_id
        token = self.token_id

        # Build customer data from transaction partner info
        customer_data = self._cardpoint_build_customer_data()

        # Use the stored profile/account token
        if token.cardpoint_profile_id and token.cardpoint_acct_id:
            # Use stored profile
            account = f"{token.cardpoint_profile_id}/{token.cardpoint_acct_id}"
        else:
            account = token.provider_ref

        try:
            response = provider._cardpoint_authorize_transaction(
                amount=self.amount,
                currency=self.currency_id.name,
                account=account,
                tx_ref=self.reference,
                customer_data=customer_data,
                payment_type=self.cardpoint_payment_type,
            )
            self._cardpoint_handle_auth_response(response)
        except UserError as e:
            self._set_error(str(e))

    # ------------------------------------------------------------------
    # _send_refund_request
    # ------------------------------------------------------------------
    def _send_refund_request(self, amount_to_refund=None):
        """
        Send a refund request to CardPointe.

        Called by Odoo's payment framework when a refund is initiated.

        :param float amount_to_refund: Amount to refund (None = full refund)
        :return: payment.transaction record for the refund
        """
        refund_tx = super()._send_refund_request(amount_to_refund=amount_to_refund)
        if self.provider_code != 'cardpoint':
            return refund_tx

        if not self.cardpoint_retref:
            raise UserError(_(
                'Cannot issue refund: CardPointe retrieval reference (retref) not found.'
            ))

        _logger.info(
            "CardPointe: Sending refund request for tx %s (retref: %s), amount: %s",
            self.reference,
            self.cardpoint_retref,
            amount_to_refund,
        )

        try:
            response = self.provider_id._cardpoint_refund_transaction(
                retref=self.cardpoint_retref,
                amount=amount_to_refund,
            )

            if response.get('respstat') in ('A',):
                refund_tx.write({
                    'cardpoint_retref': response.get('retref', ''),
                    'cardpoint_authcode': response.get('authcode', ''),
                    'cardpoint_respcode': response.get('respstat', ''),
                    'cardpoint_resptext': response.get('resptext', ''),
                })
                refund_tx._set_done()
                _logger.info("CardPointe: Refund successful for tx %s", self.reference)
            else:
                error_msg = response.get('resptext', 'Refund declined')
                refund_tx._set_error(f"CardPointe refund failed: {error_msg}")
                _logger.warning(
                    "CardPointe: Refund failed for tx %s: %s",
                    self.reference,
                    error_msg,
                )
        except UserError as e:
            refund_tx._set_error(str(e))

        return refund_tx

    # ------------------------------------------------------------------
    # _send_capture_request
    # ------------------------------------------------------------------
    def _send_capture_request(self, amount_to_capture=None):
        """
        Capture a previously authorized transaction.

        Called when manually capturing an authorized transaction.

        :param float amount_to_capture: Amount to capture (None = full amount)
        """
        super()._send_capture_request(amount_to_capture=amount_to_capture)
        if self.provider_code != 'cardpoint':
            return

        if not self.cardpoint_retref:
            raise UserError(_(
                'Cannot capture: CardPointe retrieval reference (retref) not found.'
            ))

        _logger.info(
            "CardPointe: Capturing transaction %s (retref: %s)",
            self.reference,
            self.cardpoint_retref,
        )

        try:
            response = self.provider_id._cardpoint_capture_transaction(
                retref=self.cardpoint_retref,
                amount=amount_to_capture,
            )

            if response.get('respstat') == 'A':
                self.write({
                    'cardpoint_authcode': response.get('authcode', self.cardpoint_authcode),
                    'cardpoint_batch_id': response.get('batchid', ''),
                    'cardpoint_resptext': response.get('resptext', ''),
                })
                self._set_done()
                _logger.info("CardPointe: Capture successful for tx %s", self.reference)
            else:
                error_msg = response.get('resptext', 'Capture failed')
                self._set_error(f"CardPointe capture failed: {error_msg}")
        except UserError as e:
            self._set_error(str(e))

    # ------------------------------------------------------------------
    # _send_void_request
    # ------------------------------------------------------------------
    def _send_void_request(self):
        """Void an authorized transaction before capture."""
        super()._send_void_request()
        if self.provider_code != 'cardpoint':
            return

        if not self.cardpoint_retref:
            raise UserError(_(
                'Cannot void: CardPointe retrieval reference (retref) not found.'
            ))

        _logger.info(
            "CardPointe: Voiding transaction %s (retref: %s)",
            self.reference,
            self.cardpoint_retref,
        )

        try:
            response = self.provider_id._cardpoint_void_transaction(
                retref=self.cardpoint_retref,
            )

            if response.get('authcode') == 'REVERS':
                self._set_canceled()
                _logger.info("CardPointe: Void successful for tx %s", self.reference)
            else:
                error_msg = response.get('resptext', 'Void failed')
                self._set_error(f"CardPointe void failed: {error_msg}")
        except UserError as e:
            self._set_error(str(e))

    # ------------------------------------------------------------------
    # Controller entry point - process form submission
    # ------------------------------------------------------------------
    def _cardpoint_process_payment(self, payment_data, transaction_type=''):
        """
        Process a payment using data submitted from the CardPointe form.

        Called by the CardPointe controller after the frontend submits
        the tokenized card/ACH data.

        :param dict payment_data: Data from payment form containing token, type, etc.
        :return: None (updates transaction state in place)
        """
        self.ensure_one()
        if self.provider_code != 'cardpoint':
            return

        _logger.info(
            "CardPointe: Processing payment for tx %s | Type: %s",
            self.reference,
            payment_data.get('payment_type', 'card'),
        )

        # Extract payment data
        payment_type = payment_data.get('payment_type', 'card')
        token = payment_data.get('token', '')  # CardSecure token
        expiry = payment_data.get('expiry', '')
        cvv = payment_data.get('cvv', '')
        account_number = payment_data.get('account_number', '')  # For ACH
        routing_number = payment_data.get('routing_number', '')  # For ACH

        # Update payment type on transaction
        self.cardpoint_payment_type = payment_type

        # Build customer data
        customer_data = self._cardpoint_build_customer_data()
        customer_data.update({
            'cvv2': cvv,
            'expiry': expiry,
        })

        # For ACH: account is the bank routing/account number formatted for CardSecure
        if payment_type == 'ach_direct_debit':
            # ACH uses routing|account format tokenized via CardSecure
            account = token if token else f"{account_number}"
            customer_data['bank_aba'] = routing_number
        else:
            account = token

        if not account:
            self._set_error('CardPointe: No payment token received. Please try again.')
            return

        try:
            response = self.provider_id._cardpoint_authorize_transaction(
                amount=self.amount,
                currency=self.currency_id.name,
                account=account,
                tx_ref=self.reference,
                customer_data=customer_data,
                payment_type=payment_type,
                transaction_type = transaction_type
            )
			_logger.info('CardPointe: transaction response %s', response)
            self._cardpoint_handle_auth_response(response)

            # Handle tokenization / profile creation
            if (self.provider_id.cardpoint_enable_tokenization
                    and response.get('profileid')
                    and self.operation in ('online_payment', 'validation')):
                self._cardpoint_save_token(response, payment_data)

        except UserError as e:
            self._set_error(str(e))

    # ------------------------------------------------------------------
    # Response handling
    # ------------------------------------------------------------------
    def _cardpoint_handle_auth_response(self, response):
        """
        Parse a CardPointe auth response and update the transaction state.

        :param dict response: Raw JSON response from CardPointe /auth endpoint
        """
        self.ensure_one()

        resp_stat = response.get('respstat', '')
        resp_code = response.get('respcode', '')
        resp_text = response.get('resptext', 'Unknown response')
        retref = response.get('retref', '')
        authcode = response.get('authcode', '')
        accttype = response.get('accttype', '')
        last4 = response.get('account', '')
        profile_id = response.get('profileid', '')
        acct_id = response.get('acctid', '')
        batchid = response.get('batchid', '')
        avs_resp = response.get('avsresp', '')
        cvv_resp = response.get('cvvresp', '')

        # Mask account number to last 4 digits for storage
        if last4 and len(last4) > 4:
            last4 = last4[-4:]

        # Write all CardPointe-specific fields
        write_vals = {
            'cardpoint_retref': retref,
            'cardpoint_authcode': authcode,
            'cardpoint_respcode': resp_stat,
            'cardpoint_resptext': resp_text,
            'cardpoint_account_last4': last4,
            'cardpoint_account_type': accttype,
            'cardpoint_avs_resp': avs_resp,
            'cardpoint_cvv_resp': cvv_resp,
        }
        if batchid:
            write_vals['cardpoint_batch_id'] = batchid
        if profile_id:
            write_vals['cardpoint_profile_id'] = profile_id
        if acct_id:
            write_vals['cardpoint_acct_id'] = acct_id

        self.write(write_vals)

        # Map CardPointe response to Odoo transaction state
        if resp_stat == 'A':
            # Approved
            if self.provider_id.cardpoint_capture_mode == 'immediate':
                _logger.info(
                    "CardPointe: Transaction %s APPROVED & CAPTURED | retref: %s | authcode: %s",
                    self.reference, retref, authcode,
                )
                self._set_done()
            else:
                _logger.info(
                    "CardPointe: Transaction %s AUTHORIZED (pending capture) | retref: %s",
                    self.reference, retref,
                )
                self._set_authorized()

        elif resp_stat == 'B':
            # Retry / pending
            _logger.warning(
                "CardPointe: Transaction %s PENDING | retref: %s | msg: %s",
                self.reference, retref, resp_text,
            )
            self._set_pending()

        else:
            # C, D, F, P, R, E = declined/error
            error_message = f"CardPointe: Payment declined — {resp_text}"
            if resp_code:
                error_message += f" (Code: {resp_code})"
            _logger.warning(
                "CardPointe: Transaction %s DECLINED | respstat: %s | msg: %s",
                self.reference, resp_stat, resp_text,
            )
            self._set_error(error_message)

    # ------------------------------------------------------------------
    # Token saving
    # ------------------------------------------------------------------
    def _cardpoint_save_token(self, response, payment_data):
        """
        Create or update a payment.token record for future use.

        :param dict response: CardPointe auth response containing profile data
        :param dict payment_data: Original payment form data
        """
        self.ensure_one()

        profile_id = response.get('profileid', '')
        acct_id = response.get('acctid', '')
        accttype = response.get('accttype', '')
        last4 = response.get('account', '')[-4:] if response.get('account') else ''

        if not profile_id:
            return

        # Build token display name
        payment_type = payment_data.get('payment_type', 'card')
        if payment_type == 'ach_direct_debit':
            token_name = f"Bank Account ****{last4}"
        else:
            card_type = accttype or 'Card'
            token_name = f"{card_type} ****{last4}"

        # Check for existing token
        existing_token = self.env['payment.token'].search([
            ('provider_id', '=', self.provider_id.id),
            ('partner_id', '=', self.partner_id.id),
            ('cardpoint_profile_id', '=', profile_id),
            ('cardpoint_acct_id', '=', acct_id),
        ], limit=1)

        if existing_token:
            token = existing_token
            _logger.info("CardPointe: Updated existing token %s for partner %s", token.id, self.partner_id.id)
        else:
            token = self.env['payment.token'].create({
                'provider_id': self.provider_id.id,
                'partner_id': self.partner_id.id,
                'payment_method_id': self._get_cardpoint_payment_method_id(payment_type),
                'provider_ref': f"{profile_id}/{acct_id}",
                'cardpoint_profile_id': profile_id,
                'cardpoint_acct_id': acct_id,
                'cardpoint_account_type': accttype,
                'cardpoint_last4': last4,
                'cardpoint_payment_type': payment_type,
            })
            _logger.info("CardPointe: Created new token %s for partner %s", token.id, self.partner_id.id)

        self.token_id = token

    def _get_cardpoint_payment_method_id(self, payment_type):
        """Resolve the payment method record for the given type."""
        code = 'card' if payment_type == 'card' else 'bank_transfer'
        method = self.env['payment.method'].search([('code', '=', code)], limit=1)
        return method.id if method else False

    # ------------------------------------------------------------------
    # Helper: build customer data dict from transaction partner fields
    # ------------------------------------------------------------------
    def _cardpoint_build_customer_data(self):
        """Build customer billing data from the transaction's partner fields."""
        self.ensure_one()
        return {
            'name': self.partner_name or '',
            'email': self.partner_email or '',
            'phone': self.partner_phone or '',
            'street': self.partner_address or '',
            'city': self.partner_city or '',
            'state': self.partner_state_id.code if self.partner_state_id else '',
            'zip': self.partner_zip or '',
            'country': self.partner_country_id.code if self.partner_country_id else '',
        }

    # ------------------------------------------------------------------
    # Notification / webhook processing
    # ------------------------------------------------------------------
    @api.model
    def _get_tx_from_notification_data(self, provider_code, notification_data):
        """
        Find the transaction matching incoming notification data.

        Overrides base method to handle CardPointe-specific lookup.

        :param str provider_code: 'cardpoint'
        :param dict notification_data: Data from CardPointe webhook / return URL
        :return: payment.transaction recordset
        """
        tx = super()._get_tx_from_notification_data(provider_code, notification_data)
        if provider_code != 'cardpoint' or len(tx) == 1:
            return tx

        # Try to find by transaction reference
        reference = notification_data.get('orderid') or notification_data.get('tx_ref')
        if reference:
            tx = self.search([
                ('reference', '=', reference),
                ('provider_code', '=', 'cardpoint'),
            ])
            if tx:
                return tx

        # Try to find by retref
        retref = notification_data.get('retref')
        if retref:
            tx = self.search([
                ('cardpoint_retref', '=', retref),
                ('provider_code', '=', 'cardpoint'),
            ])
            if tx:
                return tx

        raise ValidationError(_(
            'CardPointe: No transaction found matching the notification data. '
            'Reference: %s | RetRef: %s'
        ) % (reference, retref))

    def _process_notification_data(self, notification_data):
        """
        Process notification data received from CardPointe.

        Updates transaction state based on webhook or return-URL data.

        :param dict notification_data: Parsed notification payload
        """
        super()._process_notification_data(notification_data)
        if self.provider_code != 'cardpoint':
            return

        _logger.info(
            "CardPointe: Processing notification data for tx %s: %s",
            self.reference,
            notification_data,
        )

        # If response data is included in notification, process it
        if 'respstat' in notification_data:
            self._cardpoint_handle_auth_response(notification_data)
        elif 'retref' in notification_data:
            # Inquire about the transaction status
            try:
                inquiry = self.provider_id._cardpoint_inquire_transaction(
                    notification_data['retref']
                )
                self._cardpoint_handle_auth_response(inquiry)
            except UserError as e:
                _logger.error(
                    "CardPointe: Failed to inquire transaction %s: %s",
                    notification_data['retref'],
                    str(e),
                )

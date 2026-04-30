# -*- coding: utf-8 -*-

import hashlib
import hmac
import json
import logging
import re
import requests
from datetime import datetime

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CardPointe API endpoint constants
# ---------------------------------------------------------------------------
CARDPOINT_API_VERSION = 'v1'

CARDPOINT_ENDPOINTS = {
    'test': 'https://fts-uat.cardconnect.com/cardconnect/rest',
    'production': 'https://fts.cardconnect.com/cardconnect/rest',
}

# CardPointe REST API paths
CARDPOINT_PATH_AUTH = '/auth'
CARDPOINT_PATH_CAPTURE = '/capture'
CARDPOINT_PATH_VOID = '/void'
CARDPOINT_PATH_REFUND = '/refund'
# CARDPOINT_PATH_INQUIRE = '/inquire'
CARDPOINT_PATH_INQUIRE = '/inquireMerchant'
CARDPOINT_PATH_PROFILE = '/profile'
CARDPOINT_PATH_TOKENIZE = '/v1/ccn/tokenize'

# Payment method type codes
CARDPOINT_PAYMENT_TYPE_CARD = 'card'
CARDPOINT_PAYMENT_TYPE_ACH = 'ach_direct_debit'

# CardPointe response codes
CARDPOINT_APPROVED_CODES = ['A']  # Approved
CARDPOINT_DECLINED_CODES = ['C', 'D', 'F', 'P', 'R']  # Various declined states
CARDPOINT_ERROR_CODES = ['E']

# ACH SEC codes
ACH_SEC_CODE_WEB = 'WEB'   # Internet-initiated entries
ACH_SEC_CODE_PPD = 'PPD'   # Prearranged Payment and Deposit
ACH_SEC_CODE_CCD = 'CCD'   # Corporate Credit or Debit


class PaymentProvider(models.Model):
    """
    CardPointe Payment Provider.

    Extends Odoo's base payment.provider model with CardPointe-specific
    configuration fields and API communication methods.

    Architecture mirrors payment_authorize and payment_stripe modules.
    """
    _inherit = 'payment.provider'

    # ------------------------------------------------------------------
    # Provider identification
    # ------------------------------------------------------------------
    code = fields.Selection(
        selection_add=[('cardpoint', 'CardPointe')],
        ondelete={'cardpoint': 'set default'},
    )

    # ------------------------------------------------------------------
    # CardPointe-specific configuration fields
    # ------------------------------------------------------------------
    cardpoint_merchant_id = fields.Char(
        string='Merchant ID',
        groups='base.group_system',
        help='Your CardPointe Merchant ID (MID) assigned by CardConnect.',
    )
    cardpoint_api_username = fields.Char(
        string='API Username',
        groups='base.group_system',
        help='API username for CardPointe REST API authentication.',
    )
    cardpoint_api_password = fields.Char(
        string='API Password',
        groups='base.group_system',
        help='API password for CardPointe REST API authentication.',
    )
    cardpoint_capture_mode = fields.Selection(
        selection=[
            ('immediate', 'Immediate Capture'),
            ('authorize', 'Authorize Only (Manual Capture)'),
        ],
        string='Capture Mode',
        default='immediate',
        required_if_provider='cardpoint',
        help=(
            'Immediate Capture: Authorize and capture funds in one step.\n'
            'Authorize Only: Reserve funds without capturing — capture manually later.'
        ),
    )
    cardpoint_payment_methods = fields.Selection(
        selection=[
            ('card', 'Credit/Debit Card Only'),
            ('ach', 'ACH / Bank Transfer Only'),
            ('both', 'Both Card and ACH'),
        ],
        string='Accepted Payment Methods',
        default='both',
        required_if_provider='cardpoint',
        help='Choose which payment methods are available to customers.',
    )
    cardpoint_ach_sec_code = fields.Selection(
        selection=[
            (ACH_SEC_CODE_WEB, 'WEB - Internet-initiated'),
            (ACH_SEC_CODE_PPD, 'PPD - Prearranged Payment'),
            (ACH_SEC_CODE_CCD, 'CCD - Corporate Credit/Debit'),
        ],
        string='ACH SEC Code',
        default=ACH_SEC_CODE_WEB,
        help='Standard Entry Class code for ACH transactions.',
    )
    cardpoint_enable_tokenization = fields.Boolean(
        string='Enable Card Tokenization',
        default=True,
        help='Store tokenized card/account references for future payments.',
    )
    cardpoint_require_cvv = fields.Boolean(
        string='Require CVV',
        default=True,
        help='Require customers to enter CVV/CVC for card payments.',
    )
    cardpoint_require_avs = fields.Boolean(
        string='Require AVS (Billing Address)',
        default=False,
        help='Require billing address for AVS verification.',
    )

    # ------------------------------------------------------------------
    # Computed / helper fields
    # ------------------------------------------------------------------
    cardpoint_show_card = fields.Boolean(
        compute='_compute_cardpoint_show_methods',
        string='Show Card Form',
    )
    cardpoint_show_ach = fields.Boolean(
        compute='_compute_cardpoint_show_methods',
        string='Show ACH Form',
    )

    # ------------------------------------------------------------------
    # Compute methods
    # ------------------------------------------------------------------
    @api.depends('cardpoint_payment_methods', 'code')
    def _compute_cardpoint_show_methods(self):
        for provider in self:
            if provider.code == 'cardpoint':
                provider.cardpoint_show_card = provider.cardpoint_payment_methods in ('card', 'both')
                provider.cardpoint_show_ach = provider.cardpoint_payment_methods in ('ach', 'both')
            else:
                provider.cardpoint_show_card = False
                provider.cardpoint_show_ach = False

    # ------------------------------------------------------------------
    # Onchange / constraints
    # ------------------------------------------------------------------
    @api.onchange('state')
    def _onchange_cardpoint_state(self):
        """Warn admin when switching environments."""
        if self.code == 'cardpoint' and self.state == 'enabled':
            return {
                'warning': {
                    'title': _('Production Environment'),
                    'message': _(
                        'You are activating CardPointe in PRODUCTION mode. '
                        'Real transactions will be processed. Please verify your credentials.'
                    ),
                }
            }

    @api.constrains('cardpoint_merchant_id', 'code')
    def _check_cardpoint_merchant_id(self):
        for provider in self:
            if provider.code == 'cardpoint' and provider.cardpoint_merchant_id:
                mid = provider.cardpoint_merchant_id.strip()
                if not mid.isdigit():
                    raise ValidationError(_('CardPointe Merchant ID must contain only digits.'))

    # ------------------------------------------------------------------
    # API communication helpers
    # ------------------------------------------------------------------
    def _cardpoint_get_base_url(self):
        """Return the appropriate CardPointe API base URL based on environment."""
        self.ensure_one()
        if self.state == 'test':
            return CARDPOINT_ENDPOINTS['test']
        return CARDPOINT_ENDPOINTS['production']

    def _cardpoint_get_auth_header(self):
        """Build HTTP Basic Auth header from stored credentials."""
        self.ensure_one()
        import base64
        credentials = f"{self.cardpoint_api_username}:{self.cardpoint_api_password}"
        encoded = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')
        return {
            'Authorization': f'Basic {encoded}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }

    def _cardpoint_make_request(self, path, payload=None, method='POST'):
        """
        Make an authenticated HTTP request to the CardPointe API.

        :param str path: API endpoint path (e.g., '/auth')
        :param dict payload: Request body data
        :param str method: HTTP method ('GET', 'POST', 'PUT', 'DELETE')
        :return: dict with parsed JSON response
        :raises UserError: On connection or API errors
        """
        self.ensure_one()
        if not self.cardpoint_merchant_id or not self.cardpoint_api_username:
            raise UserError(_(
                'CardPointe is not fully configured. '
                'Please set the Merchant ID and API credentials.'
            ))

        base_url = self._cardpoint_get_base_url()
        url = f"{base_url}{path}"
        headers = self._cardpoint_get_auth_header()

        _logger.info(
            "CardPointe API request | Method: %s | URL: %s | Payload keys: %s Values: %s",
            method,
            url,
            list(payload.keys()) if payload else '[]',
            str(payload)
        )

        try:
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
        except requests.exceptions.Timeout:
            _logger.error("CardPointe API timeout for URL: %s", url)
            raise UserError(_('CardPointe API request timed out. Please try again.'))
        except requests.exceptions.ConnectionError as e:
            _logger.error("CardPointe API connection error: %s", str(e))
            raise UserError(_('Unable to connect to CardPointe API. Please check your internet connection.'))
        except requests.exceptions.HTTPError as e:
            _logger.error("CardPointe API HTTP error %s: %s", response.status_code, response.text)
            raise UserError(_(
                'CardPointe API returned an error (HTTP %s). '
                'Please check your credentials and try again.'
            ) % response.status_code)

        try:
            result = response.json()
        except ValueError:
            _logger.error("CardPointe API returned non-JSON response: %s", response.text)
            raise UserError(_('CardPointe API returned an unexpected response format.'))

        _logger.info(
            "CardPointe API response | Status: %s | Response keys: %s",
            response.status_code,
            list(result.keys()) if isinstance(result, dict) else 'list',
        )
        return result

    # ------------------------------------------------------------------
    # Payment initiation
    # ------------------------------------------------------------------
    def _cardpoint_authorize_transaction(self, amount, currency, account, tx_ref,
                                          customer_data=None, payment_type='card', transaction_type=''):
        """
        Authorize (and optionally capture) a transaction via the CardPointe API.

        :param float amount: Transaction amount
        :param str currency: ISO currency code (e.g., 'USD')
        :param str account: Tokenized card/account number or raw token
        :param str tx_ref: Unique transaction reference (Odoo tx reference)
        :param dict customer_data: Customer billing/contact information
        :param str payment_type: 'card' or 'ach'
        :return: API response dict
        """
        self.ensure_one()

        # Convert amount to cents (CardPointe expects amount in dollars with decimals)
        amount_str = f"{amount:.2f}"

        # Determine capture mode
        capture_flag = 'Y' if self.cardpoint_capture_mode == 'immediate' else 'N'
        if capture_flag == 'Y' and transaction_type and transaction_type != 'authCaptureTransaction':
            capture_flag = 'N'

        payload = {
            'merchid': self.cardpoint_merchant_id,
            'amount': amount_str,
            'currency': currency.upper(),
            'account': account,
            'orderid': tx_ref,
            'capture': capture_flag,
            'ecomind': 'E',  # E = eCommerce transaction
        }

        # Payment-type specific fields
        if payment_type == CARDPOINT_PAYMENT_TYPE_ACH:
            payload.update({
                'accttype': customer_data.get('acct_type', '') if customer_data else '',  # Electronic Check
                'bankaba': customer_data.get('bank_aba', '') if customer_data else '',
                'ssnl4': customer_data.get('ssnl4', '') if customer_data else '',
                'achEntryCode': customer_data.get('ach_entry_code', '') if customer_data else '',
                'achDescription': customer_data.get('ach_description', '') if customer_data else '',
            })
        else:
            # Card-specific fields
            if customer_data and customer_data.get('cvv2'):
                payload['cvv2'] = customer_data['cvv2']
            if customer_data and customer_data.get('expiry'):
                payload['expiry'] = customer_data['expiry']

        # Billing address for AVS
        if customer_data:
            payload.update({
                'name': customer_data.get('name', ''),
                'email': customer_data.get('email', ''),
                'address': customer_data.get('street', ''),
                'city': customer_data.get('city', ''),
                'region': customer_data.get('state', ''),
                'country': customer_data.get('country', ''),
                'postal': customer_data.get('zip', ''),
                'phone': customer_data.get('phone', ''),
            })

        # Tokenization: request profile creation
        if self.cardpoint_enable_tokenization:
            payload['profile'] = 'Y'

        return self._cardpoint_make_request(CARDPOINT_PATH_AUTH, payload)

    def _cardpoint_capture_transaction(self, retref, amount=None):
        """
        Capture a previously authorized transaction.

        :param str retref: CardPointe retrieval reference number
        :param float amount: Optional partial capture amount
        :return: API response dict
        """
        self.ensure_one()
        payload = {'retref': retref}
        if amount is not None:
            payload['amount'] = f"{amount:.2f}"
        return self._cardpoint_make_request(CARDPOINT_PATH_CAPTURE, payload)

    def _cardpoint_void_transaction(self, retref):
        """
        Void an authorized or captured transaction.

        :param str retref: CardPointe retrieval reference number
        :return: API response dict
        """
        self.ensure_one()
        payload = {'retref': retref}
        return self._cardpoint_make_request(CARDPOINT_PATH_VOID, payload)

    def _cardpoint_refund_transaction(self, retref, amount=None):
        """
        Issue a refund for a captured transaction.

        :param str retref: CardPointe retrieval reference number
        :param float amount: Partial refund amount (None = full refund)
        :return: API response dict
        """
        self.ensure_one()
        payload = {'retref': retref}
        if amount is not None:
            payload['amount'] = f"{amount:.2f}"
        return self._cardpoint_make_request(CARDPOINT_PATH_REFUND, payload)

    def _cardpoint_inquire_transaction(self, retref):
        """
        Inquire about the status of a transaction.

        :param str retref: CardPointe retrieval reference number
        :return: API response dict
        """
        self.ensure_one()
        url_path = f"{CARDPOINT_PATH_INQUIRE}/{self.cardpoint_merchant_id}/{retref}"
        return self._cardpoint_make_request(url_path, method='GET')

    def _cardpoint_create_profile(self, account, name, defaultacct='Y'):
        """
        Store a tokenized card profile for future use.

        :param str account: CardSecure token
        :param str name: Cardholder/account holder name
        :param str defaultacct: 'Y' to set as default account
        :return: API response dict with profileid and acctid
        """
        self.ensure_one()
        payload = {
            'account': account,
            'name': name,
            'defaultacct': defaultacct,
        }
        return self._cardpoint_make_request(CARDPOINT_PATH_PROFILE, payload, method='PUT')

    def _cardpoint_delete_profile(self, profile_id, acct_id=None):
        """Delete a stored card profile."""
        self.ensure_one()
        path = f"{CARDPOINT_PATH_PROFILE}/{self.cardpoint_merchant_id}/{profile_id}"
        if acct_id:
            path += f"/{acct_id}"
        return self._cardpoint_make_request(path, method='DELETE')

    def _cardpointe_tokenize(self, payload, method='POST'):
        """Tokenize card/account data."""
        base_url = self._cardpoint_get_base_url()
        base_url = base_url.replace('cardconnect/rest', 'cardsecure/api')
        url = f"{base_url}{CARDPOINT_PATH_TOKENIZE}"
        headers = self._cardpoint_get_auth_header()

        _logger.info(
            "CardPointe API request | Method: %s | URL: %s | Payload keys: %s Values",
            method,
            url,
            list(payload.keys()) if payload else '[]',
            str(payload)
        )

        try:
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
        except requests.exceptions.Timeout:
            _logger.error("CardPointe API timeout for URL: %s", url)
            raise UserError(_('CardPointe API request timed out. Please try again.'))
        except requests.exceptions.ConnectionError as e:
            _logger.error("CardPointe API connection error: %s", str(e))
            raise UserError(_('Unable to connect to CardPointe API. Please check your internet connection.'))
        except requests.exceptions.HTTPError as e:
            _logger.error("CardPointe API HTTP error %s: %s", response.status_code, response.text)
            raise UserError(_(
                'CardPointe API returned an error (HTTP %s). '
                'Please check your credentials and try again.'
            ) % response.status_code)

        try:
            result = response.json()
        except ValueError:
            _logger.error("CardPointe API returned non-JSON response: %s", response.text)
            raise UserError(_('CardPointe API returned an unexpected response format.'))

        _logger.info(
            "CardPointe API response | Status: %s | Response keys: %s",
            response.status_code,
            list(result.keys()) if isinstance(result, dict) else 'list',
        )
        return result

    # ------------------------------------------------------------------
    # Response interpretation helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _cardpoint_is_approved(response_code):
        """Check if a CardPointe response code indicates approval."""
        return response_code in CARDPOINT_APPROVED_CODES

    @staticmethod
    def _cardpoint_parse_amount(amount_str):
        """Parse CardPointe amount string to float."""
        if not amount_str:
            return 0.0
        try:
            return float(amount_str)
        except (ValueError, TypeError):
            return 0.0

    # ------------------------------------------------------------------
    # Odoo payment.provider override methods
    # ------------------------------------------------------------------
    def _get_supported_payment_methods(self):
        """Return supported payment method types for frontend display."""
        supported = super()._get_supported_payment_methods()
        if self.code == 'cardpoint':
            methods = []
            if self.cardpoint_payment_methods in ('card', 'both'):
                methods.append('card')
            if self.cardpoint_payment_methods in ('ach', 'both'):
                methods.append('ach_direct_debit')
            return methods
        return supported

    def _get_compatible_payment_methods(self, *args, **kwargs):
        """Filter compatible payment methods for the checkout flow."""
        methods = super()._get_compatible_payment_methods(*args, **kwargs)
        return methods

    def _get_specific_rendering_values(self, processing_values):
        """ Include the access token in the processing values. """
        res = super()._get_specific_rendering_values(processing_values)
        if self.code != 'cardpoint':
            return res

        # We need the access token on the frontend to verify the direct payment request
        reference = processing_values.get('reference')
        _logger.info("CardPointe: Fetching access token for reference %s", reference)
        
        tx_sudo = self.env['payment.transaction'].sudo().search([
            ('reference', '=', reference)
        ], limit=1)
        
        if tx_sudo:
            res['access_token'] = tx_sudo.access_token
            _logger.info("CardPointe: Access token found for %s: %s", reference, tx_sudo.access_token)
        else:
            _logger.warning("CardPointe: No transaction found for reference %s", reference)
            
        return res

    def _should_build_inline_form(self, is_validation=False):
        """CardPointe uses inline form rendering."""
        return self.code == 'cardpoint' or super()._should_build_inline_form(is_validation=is_validation)

    def action_cardpoint_test_connection(self):
        """ Test the connection to CardPointe using currently entered credentials. """
        self.ensure_one()
        try:
            # We use the 'inquire' endpoint or similar for a ping.
            # But just calling any endpoint with correct credentials works.
            # Here we just try to authorize a $0 transaction or check status.
            url = f"{CARDPOINT_ENDPOINTS[self.state]}{CARDPOINT_PATH_AUTH}"
            payload = {
                "merchid": self.cardpoint_merchant_id,
                "account": "4444333322221111", # Dummy test card
                "expiry": "1226", 
                "amount": "0",
                "currency": "USD"
            }
            response = self._cardpoint_make_request(url, payload)
            if response.get('respstat') in ('A', 'B', 'C'):
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _("Success"),
                        'message': _("CardPointe Connection Successful!"),
                        'sticky': False,
                        'type': 'success',
                    }
                }
            else:
                error_msg = response.get('resptext', 'Unknown Error')
                raise ValidationError(_("Connection Failed: %s", error_msg))
        except Exception as e:
            raise ValidationError(_("Connection Failed: %s", str(e)))

    def _get_cardpoint_inline_form_values(self):
        """Return the values to be used in the inline form template."""
        self.ensure_one()
        return json.dumps({
            'merchant_id': self.cardpoint_merchant_id,
            'require_cvv': self.cardpoint_require_cvv,
            'require_avs': self.cardpoint_require_avs,
            'enable_tokenization': self.cardpoint_enable_tokenization,
            'state': self.state,
        })

    def _get_default_payment_method_codes(self):
        """Return default payment method codes for CardPointe."""
        default_codes = super()._get_default_payment_method_codes()
        if self.code == 'cardpoint':
            return ['card', 'ach_direct_debit']
        return default_codes

    def _cardpoint_setup_provider(self):
        """Called by post_init_hook to finalize provider setup."""
        self.ensure_one()
        _logger.info('CardPointe provider setup completed for MID: %s', self.cardpoint_merchant_id)

    # ------------------------------------------------------------------
    # Test connection
    # ------------------------------------------------------------------
    def action_cardpoint_test_connection(self):
        """
        Test API connectivity with the configured credentials.
        Triggered from the backend configuration form.
        """
        self.ensure_one()
        if self.code != 'cardpoint':
            raise UserError(_('This action is only available for CardPointe providers.'))

        if not self.cardpoint_merchant_id or not self.cardpoint_api_username:
            raise UserError(_('Please configure Merchant ID and API credentials before testing.'))

        try:
            # Use inquire endpoint with a dummy retref to test connectivity
            # (will fail gracefully with "no record" rather than auth error)
            base_url = self._cardpoint_get_base_url()
            url = f"{base_url}{CARDPOINT_PATH_INQUIRE}/{self.cardpoint_merchant_id}"
            headers = self._cardpoint_get_auth_header()
            response = requests.get(url, headers=headers, timeout=10)

            if response.status_code in (200, 404, 400):
                # 200/400/404 all indicate successful authentication
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Connection Successful'),
                        'message': _('Successfully connected to CardPointe API (%s environment).') % (
                            'TEST' if self.state == 'test' else 'PRODUCTION'
                        ),
                        'type': 'success',
                        'sticky': False,
                    },
                }
            else:
                raise UserError(_(
                    'CardPointe API returned status %s. '
                    'Please verify your credentials.'
                ) % response.status_code)

        except requests.exceptions.ConnectionError:
            raise UserError(_('Cannot connect to CardPointe API. Please check your network connection.'))
        except requests.exceptions.Timeout:
            raise UserError(_('CardPointe API connection timed out.'))

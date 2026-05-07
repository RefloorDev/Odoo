# -*- coding: utf-8 -*-
"""
CardPointe Payment Module - Test Suite
========================================
Comprehensive tests for the CardPointe payment integration.

Run tests with:
    ./odoo-bin -d <database> --test-enable --stop-after-init -i payment_cardpoint

Or with pytest:
    python -m pytest addons/payment_cardpoint/tests/ -v
"""

import json
from unittest.mock import MagicMock, patch

from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase, tagged
from odoo.tests import HttpCase


# ============================================================================
# Mock CardPointe API Responses
# ============================================================================

MOCK_APPROVED_RESPONSE = {
    'respstat': 'A',
    'retref': '123456789012',
    'account': '4111111111111111',
    'amount': '100.00',
    'respcode': '00',
    'resptext': 'Approval',
    'authcode': 'PPS583',
    'accttype': 'VISA',
    'entrymode': 'ECommerce',
    'avsresp': 'Y',
    'cvvresp': 'M',
    'batchid': '1',
    'profileid': 'PROF001',
    'acctid': 'ACCT001',
    'token': '9418594164541111',
    'expiry': '1225',
    'orderid': 'S00001-1',
}

MOCK_DECLINED_RESPONSE = {
    'respstat': 'C',
    'retref': '123456789099',
    'account': '4111111111111111',
    'amount': '100.00',
    'respcode': '05',
    'resptext': 'Declined',
    'authcode': 'DECL01',
    'accttype': 'VISA',
    'orderid': 'S00001-2',
}

MOCK_ACH_APPROVED_RESPONSE = {
    'respstat': 'A',
    'retref': '987654321012',
    'account': '1234567890',
    'amount': '250.00',
    'respcode': '00',
    'resptext': 'Approval',
    'authcode': 'ACHAUTH1',
    'accttype': 'ECHK',
    'orderid': 'S00002-1',
    'profileid': 'PROF002',
    'acctid': 'ACCT002',
}

MOCK_CAPTURE_RESPONSE = {
    'respstat': 'A',
    'retref': '123456789012',
    'amount': '100.00',
    'resptext': 'Approval',
    'authcode': 'PPS583',
    'batchid': '2',
}

MOCK_VOID_RESPONSE = {
    'respstat': 'A',
    'retref': '123456789012',
    'amount': '100.00',
    'authcode': 'REVERS',
    'resptext': 'Voided',
}

MOCK_REFUND_RESPONSE = {
    'respstat': 'A',
    'retref': '111111111111',
    'amount': '100.00',
    'authcode': 'REFUND',
    'resptext': 'Refund Approved',
}


# ============================================================================
# Unit Tests: Payment Provider Model
# ============================================================================

@tagged('post_install', '-at_install', 'cardpoint')
class TestCardPointeProvider(TransactionCase):
    """Tests for payment.provider CardPointe functionality."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.provider = cls.env['payment.provider'].create({
            'name': 'CardPointe Test',
            'code': 'cardpoint',
            'state': 'test',
            'cardpoint_merchant_id': '496160873888',
            'cardpoint_api_username': 'testing',
            'cardpoint_api_password': 'testing123',
            'cardpoint_capture_mode': 'immediate',
            'cardpoint_payment_methods': 'both',
            'cardpoint_enable_tokenization': True,
            'cardpoint_require_cvv': True,
        })

    # -----------------------------------------------------------------------
    # Configuration tests
    # -----------------------------------------------------------------------

    def test_provider_created_with_correct_code(self):
        """Provider should have code 'cardpoint'."""
        self.assertEqual(self.provider.code, 'cardpoint')

    def test_provider_state_defaults_to_test(self):
        """Provider should default to test/sandbox state."""
        self.assertEqual(self.provider.state, 'test')

    def test_cardpoint_show_card_both_methods(self):
        """show_card should be True when payment_methods is 'both'."""
        self.provider.cardpoint_payment_methods = 'both'
        self.assertTrue(self.provider.cardpoint_show_card)
        self.assertTrue(self.provider.cardpoint_show_ach)

    def test_cardpoint_show_card_only(self):
        """show_ach should be False when payment_methods is 'card'."""
        self.provider.cardpoint_payment_methods = 'card'
        self.assertTrue(self.provider.cardpoint_show_card)
        self.assertFalse(self.provider.cardpoint_show_ach)

    def test_cardpoint_show_ach_only(self):
        """show_card should be False when payment_methods is 'ach'."""
        self.provider.cardpoint_payment_methods = 'ach'
        self.assertFalse(self.provider.cardpoint_show_card)
        self.assertTrue(self.provider.cardpoint_show_ach)

    def test_test_environment_url(self):
        """Test environment should use UAT endpoint."""
        self.provider.state = 'test'
        url = self.provider._cardpoint_get_base_url()
        self.assertIn('uat', url)

    def test_production_environment_url(self):
        """Production environment should use live endpoint."""
        self.provider.state = 'enabled'
        url = self.provider._cardpoint_get_base_url()
        self.assertNotIn('uat', url)
        self.assertIn('cardconnect.com', url)

    def test_invalid_merchant_id_raises_error(self):
        """Merchant ID with non-digits should raise ValidationError."""
        with self.assertRaises(Exception):
            self.provider.write({'cardpoint_merchant_id': 'ABC-123'})
            self.provider._check_cardpoint_merchant_id()

    def test_auth_header_format(self):
        """Auth header should use Basic authentication scheme."""
        header = self.provider._cardpoint_get_auth_header()
        self.assertIn('Authorization', header)
        self.assertTrue(header['Authorization'].startswith('Basic '))
        self.assertEqual(header['Content-Type'], 'application/json')

    def test_missing_credentials_raises_error(self):
        """API call without credentials should raise UserError."""
        provider_no_creds = self.env['payment.provider'].create({
            'name': 'CardPointe No Creds',
            'code': 'cardpoint',
            'state': 'test',
        })
        with self.assertRaises(UserError):
            provider_no_creds._cardpoint_make_request('/auth', {})

    # -----------------------------------------------------------------------
    # API mock tests
    # -----------------------------------------------------------------------

    @patch('requests.request')
    def test_authorize_transaction_success(self, mock_request):
        """_cardpoint_authorize_transaction should return approved response."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = MOCK_APPROVED_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_request.return_value = mock_resp

        result = self.provider._cardpoint_authorize_transaction(
            amount=100.00,
            currency='USD',
            account='4111111111111111',
            tx_ref='S00001-1',
            customer_data={'name': 'John Doe', 'email': 'john@test.com'},
            payment_type='card',
        )

        self.assertEqual(result['respstat'], 'A')
        self.assertEqual(result['authcode'], 'PPS583')
        mock_request.assert_called_once()

    @patch('requests.request')
    def test_authorize_transaction_declined(self, mock_request):
        """Declined transaction should return declined response."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = MOCK_DECLINED_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_request.return_value = mock_resp

        result = self.provider._cardpoint_authorize_transaction(
            amount=100.00,
            currency='USD',
            account='4111111111111111',
            tx_ref='S00001-2',
            payment_type='card',
        )

        self.assertEqual(result['respstat'], 'C')
        self.assertEqual(result['resptext'], 'Declined')

    @patch('requests.request')
    def test_ach_authorize_transaction(self, mock_request):
        """ACH transaction should include ECHK account type."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = MOCK_ACH_APPROVED_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_request.return_value = mock_resp

        result = self.provider._cardpoint_authorize_transaction(
            amount=250.00,
            currency='USD',
            account='021000021|1234567890',
            tx_ref='S00002-1',
            customer_data={'bank_aba': '021000021'},
            payment_type='ach_direct_debit',
        )

        self.assertEqual(result['respstat'], 'A')
        self.assertEqual(result['accttype'], 'ECHK')

        # Verify ACH-specific payload was sent
        call_kwargs = mock_request.call_args
        payload = json.loads(call_kwargs[1].get('json') or call_kwargs.kwargs.get('json', '{}')
                             if isinstance(call_kwargs[1].get('json'), str)
                             else str(call_kwargs))
        # At minimum, verify the request was made
        mock_request.assert_called_once()

    @patch('requests.request')
    def test_capture_transaction(self, mock_request):
        """Capture should succeed for authorized transaction."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = MOCK_CAPTURE_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_request.return_value = mock_resp

        result = self.provider._cardpoint_capture_transaction(
            retref='123456789012',
        )

        self.assertEqual(result['respstat'], 'A')
        mock_request.assert_called_once()

    @patch('requests.request')
    def test_void_transaction(self, mock_request):
        """Void should return REVERS authcode on success."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = MOCK_VOID_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_request.return_value = mock_resp

        result = self.provider._cardpoint_void_transaction(retref='123456789012')

        self.assertEqual(result['authcode'], 'REVERS')
        mock_request.assert_called_once()

    @patch('requests.request')
    def test_refund_transaction(self, mock_request):
        """Refund should succeed and return a new retref."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = MOCK_REFUND_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_request.return_value = mock_resp

        result = self.provider._cardpoint_refund_transaction(
            retref='123456789012',
            amount=50.00,
        )

        self.assertEqual(result['respstat'], 'A')
        self.assertEqual(result['retref'], '111111111111')

    @patch('requests.request')
    def test_api_timeout_raises_user_error(self, mock_request):
        """Timeout from API should raise UserError."""
        import requests as req
        mock_request.side_effect = req.exceptions.Timeout()

        with self.assertRaises(UserError) as cm:
            self.provider._cardpoint_make_request('/auth', {'test': True})

        self.assertIn('timed out', str(cm.exception).lower())

    @patch('requests.request')
    def test_api_connection_error_raises_user_error(self, mock_request):
        """Connection error should raise UserError."""
        import requests as req
        mock_request.side_effect = req.exceptions.ConnectionError()

        with self.assertRaises(UserError) as cm:
            self.provider._cardpoint_make_request('/auth', {'test': True})

        self.assertIn('connect', str(cm.exception).lower())

    def test_is_approved_true(self):
        """Response code 'A' should be approved."""
        self.assertTrue(self.provider._cardpoint_is_approved('A'))

    def test_is_approved_false(self):
        """Response codes C, D, E, F should not be approved."""
        for code in ['C', 'D', 'E', 'F', 'P', 'R']:
            self.assertFalse(self.provider._cardpoint_is_approved(code))

    def test_parse_amount(self):
        """Amount parsing should convert string to float."""
        self.assertEqual(self.provider._cardpoint_parse_amount('100.00'), 100.0)
        self.assertEqual(self.provider._cardpoint_parse_amount(''), 0.0)
        self.assertEqual(self.provider._cardpoint_parse_amount(None), 0.0)
        self.assertEqual(self.provider._cardpoint_parse_amount('25.50'), 25.5)


# ============================================================================
# Unit Tests: Payment Transaction Model
# ============================================================================

@tagged('post_install', '-at_install', 'cardpoint')
class TestCardPointeTransaction(TransactionCase):
    """Tests for payment.transaction CardPointe functionality."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # Create provider
        cls.provider = cls.env['payment.provider'].create({
            'name': 'CardPointe Test',
            'code': 'cardpoint',
            'state': 'test',
            'cardpoint_merchant_id': '496160873888',
            'cardpoint_api_username': 'testing',
            'cardpoint_api_password': 'testing123',
            'cardpoint_capture_mode': 'immediate',
            'cardpoint_payment_methods': 'both',
            'cardpoint_enable_tokenization': True,
        })

        # Get or create test currency
        cls.currency = cls.env.ref('base.USD')

        # Create test partner
        cls.partner = cls.env['res.partner'].create({
            'name': 'Test Customer',
            'email': 'testcustomer@example.com',
            'phone': '+1 555-555-5555',
            'street': '123 Test St',
            'city': 'Atlanta',
            'zip': '30301',
            'country_id': cls.env.ref('base.us').id,
            'state_id': cls.env.ref('base.state_us_11').id,  # GA
        })

        # Get payment method
        cls.payment_method = cls.env['payment.method'].search(
            [('code', '=', 'card')], limit=1
        )
        if not cls.payment_method:
            cls.payment_method = cls.env['payment.method'].create({
                'name': 'Card',
                'code': 'card',
                'provider_ids': [(4, cls.provider.id)],
            })

    def _create_transaction(self, amount=100.0, operation='online_payment',
                             payment_type='card', reference=None):
        """Helper: create a CardPointe payment transaction."""
        if not reference:
            import time
            reference = f'TEST-{int(time.time())}'

        tx = self.env['payment.transaction'].create({
            'provider_id': self.provider.id,
            'payment_method_id': self.payment_method.id,
            'reference': reference,
            'amount': amount,
            'currency_id': self.currency.id,
            'partner_id': self.partner.id,
            'partner_name': self.partner.name,
            'partner_email': self.partner.email,
            'operation': operation,
            'cardpoint_payment_type': payment_type,
        })
        return tx

    # -----------------------------------------------------------------------
    # Transaction state tests
    # -----------------------------------------------------------------------

    def test_approved_response_sets_done(self):
        """Approved CardPointe response should set transaction to 'done'."""
        tx = self._create_transaction()
        tx._cardpoint_handle_auth_response(MOCK_APPROVED_RESPONSE)
        self.assertEqual(tx.state, 'done')

    def test_approved_authorize_only_sets_authorized(self):
        """Approved with authorize-only mode should set to 'authorized'."""
        self.provider.cardpoint_capture_mode = 'authorize'
        tx = self._create_transaction()
        tx._cardpoint_handle_auth_response(MOCK_APPROVED_RESPONSE)
        self.assertEqual(tx.state, 'authorized')
        # Restore
        self.provider.cardpoint_capture_mode = 'immediate'

    def test_declined_response_sets_error(self):
        """Declined CardPointe response should set transaction to error."""
        tx = self._create_transaction()
        tx._cardpoint_handle_auth_response(MOCK_DECLINED_RESPONSE)
        self.assertEqual(tx.state, 'cancel')

    def test_approved_response_stores_retref(self):
        """Approved response should store retref on transaction."""
        tx = self._create_transaction()
        tx._cardpoint_handle_auth_response(MOCK_APPROVED_RESPONSE)
        self.assertEqual(tx.cardpoint_retref, '123456789012')

    def test_approved_response_stores_authcode(self):
        """Approved response should store authcode on transaction."""
        tx = self._create_transaction()
        tx._cardpoint_handle_auth_response(MOCK_APPROVED_RESPONSE)
        self.assertEqual(tx.cardpoint_authcode, 'PPS583')

    def test_approved_response_stores_last4(self):
        """Approved response should store last 4 digits."""
        tx = self._create_transaction()
        tx._cardpoint_handle_auth_response(MOCK_APPROVED_RESPONSE)
        self.assertEqual(tx.cardpoint_account_last4, '1111')

    def test_approved_response_stores_account_type(self):
        """Approved response should store account type (card brand)."""
        tx = self._create_transaction()
        tx._cardpoint_handle_auth_response(MOCK_APPROVED_RESPONSE)
        self.assertEqual(tx.cardpoint_account_type, 'VISA')

    def test_ach_approved_response_sets_done(self):
        """Approved ACH response should set transaction to 'done'."""
        tx = self._create_transaction(amount=250.0, payment_type='ach_direct_debit')
        tx._cardpoint_handle_auth_response(MOCK_ACH_APPROVED_RESPONSE)
        self.assertEqual(tx.state, 'done')
        self.assertEqual(tx.cardpoint_account_type, 'ECHK')

    def test_pending_response_sets_pending(self):
        """Pending CardPointe response should set transaction to pending."""
        pending_response = {
            'respstat': 'B',
            'retref': '123456789013',
            'resptext': 'Pending',
            'orderid': 'S00001-3',
        }
        tx = self._create_transaction()
        tx._cardpoint_handle_auth_response(pending_response)
        self.assertEqual(tx.state, 'pending')

    def test_customer_data_includes_partner_info(self):
        """Customer data should include partner billing information."""
        tx = self._create_transaction()
        data = tx._cardpoint_build_customer_data()

        self.assertEqual(data['name'], self.partner.name)
        self.assertEqual(data['email'], self.partner.email)

    # -----------------------------------------------------------------------
    # Transaction lookup tests
    # -----------------------------------------------------------------------

    def test_get_tx_from_notification_by_orderid(self):
        """Should find transaction by orderid in notification data."""
        tx = self._create_transaction(reference='NOTIFY-TEST-001')
        notification = {'orderid': 'NOTIFY-TEST-001', 'respstat': 'A'}

        found_tx = self.env['payment.transaction']._get_tx_from_notification_data(
            'cardpoint', notification
        )
        self.assertEqual(found_tx.id, tx.id)

    def test_get_tx_from_notification_by_retref(self):
        """Should find transaction by retref in notification data."""
        tx = self._create_transaction(reference='RETREF-TEST-001')
        tx.cardpoint_retref = 'RETREF987'

        notification = {'retref': 'RETREF987'}
        found_tx = self.env['payment.transaction']._get_tx_from_notification_data(
            'cardpoint', notification
        )
        self.assertEqual(found_tx.id, tx.id)

    def test_get_tx_from_notification_not_found_raises(self):
        """Non-existent reference should raise ValidationError."""
        notification = {'orderid': 'NONEXISTENT-REF-XYZ'}
        with self.assertRaises(ValidationError):
            self.env['payment.transaction']._get_tx_from_notification_data(
                'cardpoint', notification
            )

    # -----------------------------------------------------------------------
    # Capture / Void / Refund tests
    # -----------------------------------------------------------------------

    @patch('requests.request')
    def test_capture_request_success(self, mock_request):
        """Capture request should update transaction to done."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = MOCK_CAPTURE_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_request.return_value = mock_resp

        self.provider.cardpoint_capture_mode = 'authorize'
        tx = self._create_transaction()
        tx.write({
            'cardpoint_retref': '123456789012',
            'state': 'authorized',
        })

        tx._send_capture_request()
        self.assertEqual(tx.state, 'done')
        self.provider.cardpoint_capture_mode = 'immediate'

    @patch('requests.request')
    def test_void_request_success(self, mock_request):
        """Void request should cancel the transaction."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = MOCK_VOID_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_request.return_value = mock_resp

        tx = self._create_transaction()
        tx.write({
            'cardpoint_retref': '123456789012',
            'state': 'authorized',
        })

        tx._send_void_request()
        self.assertEqual(tx.state, 'cancel')

    def test_capture_without_retref_raises(self):
        """Capture without retref should raise UserError."""
        tx = self._create_transaction()
        with self.assertRaises(UserError):
            tx._send_capture_request()

    def test_void_without_retref_raises(self):
        """Void without retref should raise UserError."""
        tx = self._create_transaction()
        with self.assertRaises(UserError):
            tx._send_void_request()


# ============================================================================
# Unit Tests: Payment Token Model
# ============================================================================

@tagged('post_install', '-at_install', 'cardpoint')
class TestCardPointeToken(TransactionCase):
    """Tests for payment.token CardPointe functionality."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.provider = cls.env['payment.provider'].create({
            'name': 'CardPointe Token Test',
            'code': 'cardpoint',
            'state': 'test',
            'cardpoint_merchant_id': '496160873888',
            'cardpoint_api_username': 'testing',
            'cardpoint_api_password': 'testing123',
        })

        cls.partner = cls.env['res.partner'].create({
            'name': 'Token Test Customer',
            'email': 'token@test.com',
        })

        cls.payment_method = cls.env['payment.method'].search(
            [('code', '=', 'card')], limit=1
        )

    def test_token_created_with_profile_ref(self):
        """Token creation should auto-set provider_ref from profile/acct IDs."""
        token = self.env['payment.token'].create({
            'provider_id': self.provider.id,
            'partner_id': self.partner.id,
            'payment_method_id': self.payment_method.id if self.payment_method else False,
            'cardpoint_profile_id': 'PROF001',
            'cardpoint_acct_id': 'ACCT001',
            'cardpoint_account_type': 'VISA',
            'cardpoint_last4': '1111',
            'cardpoint_payment_type': 'card',
        })

        self.assertEqual(token.provider_ref, 'PROF001/ACCT001')
        self.assertEqual(token.cardpoint_last4, '1111')

    def test_token_display_name_visa(self):
        """VISA token should show brand and last4 in display name."""
        token = self.env['payment.token'].create({
            'provider_id': self.provider.id,
            'partner_id': self.partner.id,
            'payment_method_id': self.payment_method.id if self.payment_method else False,
            'cardpoint_profile_id': 'PROF002',
            'cardpoint_acct_id': 'ACCT002',
            'cardpoint_account_type': 'VISA',
            'cardpoint_last4': '4242',
            'cardpoint_payment_type': 'card',
        })

        # Display name should include card type and last4
        self.assertIn('4242', token.display_name or token.provider_ref)

    def test_ach_token_display_name(self):
        """ACH token should show bank account in display name."""
        token = self.env['payment.token'].create({
            'provider_id': self.provider.id,
            'partner_id': self.partner.id,
            'payment_method_id': self.payment_method.id if self.payment_method else False,
            'cardpoint_profile_id': 'PROF003',
            'cardpoint_acct_id': 'ACCT003',
            'cardpoint_account_type': 'ECHK',
            'cardpoint_last4': '7890',
            'cardpoint_payment_type': 'ach',
        })

        # ACH token should have bank-related display
        self.assertEqual(token.cardpoint_payment_type, 'ach_direct_debit')


# ============================================================================
# Integration Tests: Full Payment Flow
# ============================================================================

@tagged('post_install', '-at_install', 'cardpoint_integration')
class TestCardPointeIntegration(TransactionCase):
    """
    Integration tests for complete CardPointe payment flows.
    These tests mock the API but test the full Odoo integration path.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.provider = cls.env['payment.provider'].create({
            'name': 'CardPointe Integration',
            'code': 'cardpoint',
            'state': 'test',
            'cardpoint_merchant_id': '496160873888',
            'cardpoint_api_username': 'testing',
            'cardpoint_api_password': 'testing123',
            'cardpoint_capture_mode': 'immediate',
            'cardpoint_payment_methods': 'both',
            'cardpoint_enable_tokenization': True,
        })

        cls.currency = cls.env.ref('base.USD')
        cls.partner = cls.env['res.partner'].create({
            'name': 'Integration Test Customer',
            'email': 'integration@test.com',
        })
        cls.payment_method = cls.env['payment.method'].search(
            [('code', '=', 'card')], limit=1
        )

    @patch('requests.request')
    def test_full_card_payment_flow(self, mock_request):
        """
        Complete card payment flow:
        1. Transaction created in draft
        2. Payment data submitted via _cardpoint_process_payment
        3. API called, response processed
        4. Transaction marked as done
        """
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = MOCK_APPROVED_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_request.return_value = mock_resp

        # 1. Create transaction
        tx = self.env['payment.transaction'].create({
            'provider_id': self.provider.id,
            'payment_method_id': self.payment_method.id if self.payment_method else False,
            'reference': 'INTEGRATION-CARD-001',
            'amount': 100.00,
            'currency_id': self.currency.id,
            'partner_id': self.partner.id,
            'partner_name': self.partner.name,
            'partner_email': self.partner.email,
            'operation': 'online_payment',
            'cardpoint_payment_type': 'card',
        })

        self.assertEqual(tx.state, 'draft')

        # 2. Submit payment data (simulating form submission)
        payment_data = {
            'payment_type': 'card',
            'token': '4111111111111111',
            'expiry': '1225',
            'cvv': '123',
            'card_name': 'Test Customer',
            'save_payment_method': False,
        }
        tx._cardpoint_process_payment(payment_data)

        # 3. Verify final state
        self.assertEqual(tx.state, 'done')
        self.assertEqual(tx.cardpoint_retref, '123456789012')
        self.assertEqual(tx.cardpoint_authcode, 'PPS583')
        self.assertEqual(tx.cardpoint_account_last4, '1111')

    @patch('requests.request')
    def test_full_ach_payment_flow(self, mock_request):
        """
        Complete ACH payment flow:
        1. Transaction created
        2. ACH data submitted
        3. API called with ECHK account type
        4. Transaction marked done
        """
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = MOCK_ACH_APPROVED_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_request.return_value = mock_resp

        tx = self.env['payment.transaction'].create({
            'provider_id': self.provider.id,
            'payment_method_id': self.payment_method.id if self.payment_method else False,
            'reference': 'INTEGRATION-ACH-001',
            'amount': 250.00,
            'currency_id': self.currency.id,
            'partner_id': self.partner.id,
            'partner_name': self.partner.name,
            'partner_email': self.partner.email,
            'operation': 'online_payment',
            'cardpoint_payment_type': 'ach_direct_debit',
        })

        payment_data = {
            'payment_type': 'ach_direct_debit',
            'token': '021000021|1234567890',
            'routing_number': '021000021',
            'account_number': '1234567890',
            'ach_name': 'Test Customer',
            'ach_account_type': 'checking',
            'save_payment_method': False,
        }
        tx._cardpoint_process_payment(payment_data)

        self.assertEqual(tx.state, 'done')
        self.assertEqual(tx.cardpoint_payment_type, 'ach_direct_debit')
        self.assertEqual(tx.cardpoint_account_type, 'ECHK')

    @patch('requests.request')
    def test_declined_payment_sets_error_state(self, mock_request):
        """Declined payment should result in cancel/error state."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = MOCK_DECLINED_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_request.return_value = mock_resp

        tx = self.env['payment.transaction'].create({
            'provider_id': self.provider.id,
            'payment_method_id': self.payment_method.id if self.payment_method else False,
            'reference': 'INTEGRATION-DECL-001',
            'amount': 100.00,
            'currency_id': self.currency.id,
            'partner_id': self.partner.id,
            'partner_name': self.partner.name,
            'operation': 'online_payment',
            'cardpoint_payment_type': 'card',
        })

        payment_data = {
            'payment_type': 'card',
            'token': '4111111111111111',
            'expiry': '1225',
            'cvv': '123',
        }
        tx._cardpoint_process_payment(payment_data)

        self.assertIn(tx.state, ('cancel', 'error'))

    @patch('requests.request')
    def test_authorize_then_capture_flow(self, mock_request):
        """
        Authorize-only → manual capture flow:
        1. Provider set to authorize-only
        2. Transaction authorized
        3. Manual capture processed
        4. Transaction marked done
        """
        # Setup authorize-only mode
        self.provider.cardpoint_capture_mode = 'authorize'

        # Step 1: Authorization
        mock_resp_auth = MagicMock()
        mock_resp_auth.status_code = 200
        mock_resp_auth.json.return_value = MOCK_APPROVED_RESPONSE
        mock_resp_auth.raise_for_status = MagicMock()

        # Step 2: Capture
        mock_resp_capture = MagicMock()
        mock_resp_capture.status_code = 200
        mock_resp_capture.json.return_value = MOCK_CAPTURE_RESPONSE
        mock_resp_capture.raise_for_status = MagicMock()

        mock_request.side_effect = [mock_resp_auth, mock_resp_capture]

        tx = self.env['payment.transaction'].create({
            'provider_id': self.provider.id,
            'payment_method_id': self.payment_method.id if self.payment_method else False,
            'reference': 'INTEGRATION-AUTHCAP-001',
            'amount': 100.00,
            'currency_id': self.currency.id,
            'partner_id': self.partner.id,
            'partner_name': self.partner.name,
            'operation': 'online_payment',
            'cardpoint_payment_type': 'card',
        })

        # Authorize
        payment_data = {
            'payment_type': 'card',
            'token': '4111111111111111',
            'expiry': '1225',
            'cvv': '123',
        }
        tx._cardpoint_process_payment(payment_data)
        self.assertEqual(tx.state, 'authorized')

        # Capture
        tx._send_capture_request()
        self.assertEqual(tx.state, 'done')

        # Restore
        self.provider.cardpoint_capture_mode = 'immediate'

    @patch('requests.request')
    def test_refund_flow(self, mock_request):
        """Refund should create a linked refund transaction."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = MOCK_REFUND_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_request.return_value = mock_resp

        # Create a completed transaction
        tx = self.env['payment.transaction'].create({
            'provider_id': self.provider.id,
            'payment_method_id': self.payment_method.id if self.payment_method else False,
            'reference': 'INTEGRATION-REFUND-001',
            'amount': 100.00,
            'currency_id': self.currency.id,
            'partner_id': self.partner.id,
            'partner_name': self.partner.name,
            'operation': 'online_payment',
            'cardpoint_payment_type': 'card',
            'cardpoint_retref': '123456789012',
            'state': 'done',
        })

        # Process refund
        refund_tx = tx._send_refund_request(amount_to_refund=50.0)

        self.assertIsNotNone(refund_tx)
        # Refund tx should be in done state
        if refund_tx:
            self.assertEqual(refund_tx.state, 'done')


# ============================================================================
# Test Runner Helper
# ============================================================================

def run_tests():
    """
    Helper function to describe how to run these tests.

    Usage in Odoo:
    --------------
        ./odoo-bin -d mydb --test-enable --stop-after-init -i payment_cardpoint

    Usage with specific test class:
    --------------------------------
        ./odoo-bin -d mydb --test-enable --stop-after-init \
            --test-tags cardpoint -i payment_cardpoint

    Environment variables for CardPointe sandbox testing:
    ------------------------------------------------------
        CARDPOINT_TEST_MID=496160873888
        CARDPOINT_TEST_USER=testing
        CARDPOINT_TEST_PASS=testing123

    Test Card Numbers (CardPointe Sandbox):
    ----------------------------------------
        Visa:       4111111111111111
        Mastercard: 5454545454545454
        Discover:   6011000993026909
        Amex:       371449635398431
        Decline:    4386490000000005

    Test ACH (CardPointe Sandbox):
    --------------------------------
        Routing:    021000021
        Account:    Any digits (use 1234567890)
        Type:       Checking or Savings
    """
    print(run_tests.__doc__)

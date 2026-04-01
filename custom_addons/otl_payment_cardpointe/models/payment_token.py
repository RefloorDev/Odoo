# -*- coding: utf-8 -*-

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class PaymentToken(models.Model):
    """
    CardPointe Payment Token.

    Extends payment.token to store CardPointe profile/account identifiers
    for tokenized card and ACH payment methods.

    CardPointe uses a two-level identifier:
    - profileid: Identifies the customer's profile
    - acctid: Identifies a specific payment account within the profile

    Together, these enable the stored profile flow:
    account = "<profileid>/<acctid>"
    """
    _inherit = 'payment.token'

    # ------------------------------------------------------------------
    # CardPointe-specific token fields
    # ------------------------------------------------------------------
    cardpoint_profile_id = fields.Char(
        string='CardPointe Profile ID',
        readonly=True,
        help='CardPointe stored profile identifier.',
    )
    cardpoint_acct_id = fields.Char(
        string='CardPointe Account ID',
        readonly=True,
        help='Account ID within the CardPointe profile.',
    )
    cardpoint_account_type = fields.Char(
        string='Account Type',
        readonly=True,
        help='Card brand or account type (e.g., VISA, MC, DISC, AMEX, ECHK).',
    )
    cardpoint_last4 = fields.Char(
        string='Last 4 Digits',
        readonly=True,
        help='Last 4 digits of the stored card or bank account.',
    )
    cardpoint_payment_type = fields.Selection(
        selection=[
            ('card', 'Credit/Debit Card'),
            ('ach_direct_debit', 'ACH / Bank Transfer'),
        ],
        string='Payment Type',
        readonly=True,
        default='card',
        help='Type of payment method stored in this token.',
    )
    cardpoint_expiry = fields.Char(
        string='Expiry (MMYY)',
        readonly=True,
        help='Card expiry date in MMYY format.',
    )

    # ------------------------------------------------------------------
    # Display name computation
    # ------------------------------------------------------------------
    @api.depends('cardpoint_account_type', 'cardpoint_last4', 'cardpoint_payment_type')
    def _compute_display_name(self):
        """Override display name to show card/account info for CardPointe tokens."""
        for token in self:
            if token.provider_code == 'cardpoint':
                acct_type = token.cardpoint_account_type or ''
                last4 = token.cardpoint_last4 or '????'
                if token.cardpoint_payment_type == 'ach_direct_debit':
                    token.display_name = f"Bank Account ****{last4}"
                elif acct_type:
                    # Map CardPointe account type codes to friendly names
                    type_names = {
                        'VISA': 'Visa',
                        'MC': 'Mastercard',
                        'DISC': 'Discover',
                        'AMEX': 'Amex',
                        'DINERS': 'Diners',
                        'JCB': 'JCB',
                        'ECHK': 'eCheck',
                    }
                    friendly_type = type_names.get(acct_type.upper(), acct_type)
                    token.display_name = f"{friendly_type} ****{last4}"
                else:
                    token.display_name = f"Card ****{last4}"
            else:
                super()._compute_display_name()

    # ------------------------------------------------------------------
    # Deletion / unlink - remove profile from CardPointe
    # ------------------------------------------------------------------
    def _handle_archival(self):
        """
        Called when a token is archived. Removes the profile from CardPointe
        if the provider is active.
        """
        super()._handle_archival()

        cardpoint_tokens = self.filtered(lambda t: t.provider_code == 'cardpoint')
        for token in cardpoint_tokens:
            if (token.cardpoint_profile_id
                    and token.provider_id.state != 'disabled'):
                try:
                    token.provider_id._cardpoint_delete_profile(
                        profile_id=token.cardpoint_profile_id,
                        acct_id=token.cardpoint_acct_id,
                    )
                    _logger.info(
                        "CardPointe: Deleted profile %s/%s for token %s",
                        token.cardpoint_profile_id,
                        token.cardpoint_acct_id,
                        token.id,
                    )
                except UserError as e:
                    _logger.warning(
                        "CardPointe: Failed to delete profile for token %s: %s",
                        token.id,
                        str(e),
                    )

    # ------------------------------------------------------------------
    # Provider ref override
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        """Ensure provider_ref is set from profile/account IDs."""
        for vals in vals_list:
            if (vals.get('cardpoint_profile_id') and vals.get('cardpoint_acct_id')
                    and not vals.get('provider_ref')):
                vals['provider_ref'] = f"{vals['cardpoint_profile_id']}/{vals['cardpoint_acct_id']}"
        return super().create(vals_list)

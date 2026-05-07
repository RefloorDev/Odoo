/** @odoo-module **/

import { _t } from '@web/core/l10n/translation';
import paymentForm from '@payment/js/payment_form';
import { rpc, RPCError } from '@web/core/network/rpc';

paymentForm.include({

    cardpointData: undefined,

    // #=== DOM MANIPULATION ===#

    /**
     * Prepare the inline form of CardPointe for direct payment.
     * Mirrors the Authorize.Net structure for Odoo 18 compatibility.
     *
     * @override method from payment.payment_form
     * @private
     */
    async _prepareInlineForm(providerId, providerCode, paymentOptionId, paymentMethodCode, flow) {
        if (providerCode !== 'cardpoint') {
            await this._super(...arguments);
            return;
        }

        // Initialize data store
        this.cardpointData ??= {};
        if (flow === 'token') {
            return;
        } else if (this.cardpointData[paymentOptionId]) {
            this._setPaymentFlow('direct');
            return;
        }

        // Set the payment flow to 'direct'
        this._setPaymentFlow('direct');

        // Find the inline form exactly like Authorize.Net does it
        const radio = document.querySelector('input[name="o_payment_radio"]:checked');
        const inlineForm = this._getInlineForm(radio);
        if (!inlineForm) {
            console.warn('CardPointe: Inline form not found for option', paymentOptionId);
            return;
        }

        const cardpointForm = inlineForm.querySelector('[name="o_cardpoint_form"]');
        if (!cardpointForm) {
            console.warn('CardPointe: o_cardpoint_form element not found inside inline form');
            return;
        }

        const rawValues = cardpointForm.dataset['cardpointInlineFormValues'];
        this.cardpointData[paymentOptionId] = {
            form: cardpointForm,
            ...(rawValues ? JSON.parse(rawValues) : {}),
        };

        // Toggle Card vs ACH sections
        const cardSection = cardpointForm.querySelector('#o_cardpoint_card_container');
        const achSection = cardpointForm.querySelector('#o_cardpoint_ach_container');
        if (cardSection && achSection) {
            if (paymentMethodCode === 'card') {
                cardSection.classList.remove('d-none');
                achSection.classList.add('d-none');
            } else {
                cardSection.classList.add('d-none');
                achSection.classList.remove('d-none');
            }
        }
    },

    // #=== PAYMENT FLOW ===#

    /**
     * Process the direct payment flow.
     *
     * @override method from payment.payment_form
     * @private
     */
    async _processDirectFlow(providerCode, paymentOptionId, paymentMethodCode, processingValues) {
        if (providerCode !== 'cardpoint') {
            this._super(...arguments);
            return;
        }

        if (!this.cardpointData || !this.cardpointData[paymentOptionId]) {
            this._displayErrorDialog(
                _t("Error"),
                _t("Could not find payment fields. Please refresh the page.")
            );
            this._enableButton();
            return;
        }

        const inputs = this._cardpointGetInlineFormInputs(paymentOptionId, paymentMethodCode);
        if (!inputs) {
            this._displayErrorDialog(
                _t("Error"),
                _t("Could not read payment input fields. Please refresh.")
            );
            this._enableButton();
            return;
        }

        const paymentData = {
            'reference': processingValues.reference,
            'partner_id': processingValues.partner_id,
            'access_token': processingValues.access_token,
            'payment_method_code': paymentMethodCode,
            ...this._cardpointGetPaymentDetails(inputs, paymentMethodCode),
        };

        return rpc('/payment/cardpoint/payment', paymentData).then(() => {
            window.location = '/payment/status';
        }).catch((error) => {
            if (error instanceof RPCError) {
                this._displayErrorDialog(_t("Payment processing failed"), error.data.message);
                this._enableButton();
            } else {
                return Promise.reject(error);
            }
        });
    },

    // #=== GETTERS ===#

    _cardpointGetInlineFormInputs(paymentOptionId, paymentMethodCode) {
        const data = this.cardpointData[paymentOptionId];
        if (!data || !data.form) {
            return null;
        }
        const form = data.form;
        if (paymentMethodCode === 'card') {
            return {
                cardNumber: form.querySelector('#o_cardpoint_card_number'),
                cardName: form.querySelector('#o_cardpoint_card_name'),
                expiry: form.querySelector('#o_cardpoint_expiry'),
                cvv: form.querySelector('#o_cardpoint_cvv'),
            };
        } else {
            return {
                routing: form.querySelector('#o_cardpoint_routing'),
                account: form.querySelector('#o_cardpoint_account'),
                accountName: form.querySelector('#o_cardpoint_ach_name'),
                accountType: form.querySelector('#o_cardpoint_account_type'),
            };
        }
    },

    _cardpointGetPaymentDetails(inputs, paymentMethodCode) {
        if (paymentMethodCode === 'card') {
            return {
                'card_number': inputs.cardNumber ? inputs.cardNumber.value.replace(/ /g, '') : '',
                'cardholder_name': inputs.cardName ? inputs.cardName.value : '',
                'expiry': inputs.expiry ? this._cardpointParseExpiry(inputs.expiry.value) : '',
                'cvv': inputs.cvv ? inputs.cvv.value : '',
            };
        } else {
            return {
                'routing_number': inputs.routing ? inputs.routing.value : '',
                'account_number': inputs.account ? inputs.account.value : '',
                'account_holder_name': inputs.accountName ? inputs.accountName.value : '',
                'account_type': inputs.accountType ? inputs.accountType.value : 'checking',
            };
        }
    },

    _cardpointParseExpiry(value) {
        const parts = value.split('/').map(p => p.trim());
        if (parts.length === 2) {
            let month = parts[0];
            if (month.length === 1) month = '0' + month;
            return month + parts[1] ;
        }
        return value.replace(/\D/g, '');
    },

});

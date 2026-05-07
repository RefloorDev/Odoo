# CardPointe Payment Gateway Integration for Odoo 18

## Overview

`payment_cardpoint` is a fully-featured Odoo 18 payment provider module that integrates the **CardPointe** (CardConnect) payment gateway into Odoo's standard payment framework. It supports both **Credit/Debit Card** and **ACH (Bank Transfer)** payments within a single provider configuration.

### Architecture

This module follows the same architecture used by Odoo's official payment providers (`payment_authorize`, `payment_stripe`):

```
payment_cardpoint/
├── __manifest__.py                   # Module definition
├── __init__.py                       # Module init + post/uninstall hooks
├── models/
│   ├── payment_provider.py           # Provider config + API communication
│   ├── payment_transaction.py        # Transaction lifecycle management
│   └── payment_token.py              # Stored payment method tokens
├── controllers/
│   └── main.py                       # HTTP endpoints (process, return, webhook)
├── views/
│   ├── payment_cardpoint_templates.xml   # Frontend payment form (QWeb)
│   ├── payment_provider_views.xml        # Backend config views
│   └── payment_transaction_views.xml     # Transaction detail views
├── data/
│   └── payment_provider_data.xml         # Default provider record
├── static/
│   └── src/
│       ├── js/payment_cardpoint_form.js  # Frontend JS (form + tokenization)
│       ├── css/payment_cardpoint.css     # Frontend styles
│       └── css/payment_cardpoint_backend.css
├── security/
│   └── ir.model.access.csv               # Access control
└── tests/
    └── test_cardpoint.py                 # Comprehensive test suite
```

---

## Features

| Feature | Supported |
|---------|-----------|
| Credit/Debit Card payments | ✅ |
| ACH / eCheck / Bank Transfer | ✅ |
| Card tokenization (stored cards) | ✅ |
| ACH tokenization (stored accounts) | ✅ |
| Immediate capture | ✅ |
| Authorize-only + manual capture | ✅ |
| Void transactions | ✅ |
| Full & partial refunds | ✅ |
| CVV verification | ✅ |
| AVS (billing address verification) | ✅ |
| Webhook / IPN support | ✅ |
| Test / Sandbox environment | ✅ |
| Multi-currency | ✅ (USD primary) |

---

## Requirements

- **Odoo**: Version 18.0
- **Python packages**: `requests` (included in Odoo's dependencies)
- **CardPointe Account**: Merchant ID, API credentials from CardConnect

---

## Installation

### 1. Copy Module to Odoo Addons

```bash
cp -r payment_cardpoint /path/to/odoo/addons/
# or
cp -r payment_cardpoint /path/to/odoo/custom_addons/
```

### 2. Update Odoo Addons Path

In your `odoo.conf`:
```ini
addons_path = /path/to/odoo/addons,/path/to/custom_addons
```

### 3. Install the Module

**Via Odoo UI:**
1. Go to **Settings → Apps**
2. Search for "CardPointe"
3. Click **Install**

**Via Command Line:**
```bash
./odoo-bin -d your_database -i payment_cardpoint --stop-after-init
```

---

## Configuration

### Step 1: Access Payment Providers

Navigate to: **Accounting → Configuration → Payment Providers**

(Or: **Website → Configuration → Payment Providers** for eCommerce)

### Step 2: Configure CardPointe

Click on the **CardPointe** provider and fill in:

#### API Credentials Tab

| Field | Description | Where to Find |
|-------|-------------|---------------|
| **Merchant ID** | Your CardPointe MID | CardPointe merchant portal |
| **API Username** | API auth username | CardConnect support / portal |
| **API Password** | API auth password | CardConnect support / portal |
| **Site ID** | Optional site routing | Only if using multi-site routing |

#### Payment Options

| Setting | Options | Description |
|---------|---------|-------------|
| **Capture Mode** | Immediate / Authorize Only | Immediate charges card right away; Authorize holds funds for manual capture |
| **Payment Methods** | Card / ACH / Both | Which methods customers can use |
| **ACH SEC Code** | WEB / PPD / CCD | Standard Entry Class for ACH |
| **Enable Tokenization** | Yes/No | Save cards/accounts for repeat customers |
| **Require CVV** | Yes/No | Enforce CVV entry on card payments |
| **Require AVS** | Yes/No | Collect billing address for verification |

#### Environment

- Set to **Test** for sandbox testing
- Set to **Enabled** (Production) for live transactions

### Step 3: Test Connection

Click **"Test API Connection"** button to verify credentials.

### Step 4: Configure Webhook (Optional but Recommended)

In your CardPointe merchant dashboard, set the webhook/notification URL to:
```
https://yourodoo.com/payment/cardpoint/webhook
```

This enables real-time transaction status updates, essential for ACH processing.

---

## Payment Flow

### Credit/Debit Card Flow

```
Customer Checkout
    ↓
Odoo renders CardPointe inline form (QWeb template)
    ↓
Customer enters: Card Number, Name, Expiry, CVV
    ↓
JavaScript validates + formats data
    ↓
POST /payment/cardpoint/process
    ↓
CardPointe controller → payment.transaction._cardpoint_process_payment()
    ↓
API call → POST https://fts.cardconnect.com/cardconnect/rest/auth/{MID}
    ↓
Response: Approved (A) / Declined (C) / Pending (B)
    ↓
Transaction state updated: done / cancel / pending
    ↓
Customer redirected to /payment/status
```

### ACH / Bank Transfer Flow

```
Customer selects "Bank Transfer (ACH)" tab
    ↓
Enters: Account holder name, Routing #, Account #, Account type
    ↓
JavaScript validates routing number (ABA checksum) + account match
    ↓
POST /payment/cardpoint/process (payment_type=ach_direct_debit)
    ↓
API call with accttype=ECHK
    ↓
ACH response: Approved immediately or Pending (processes in 1-3 days)
    ↓
Webhook notification when ACH settles
```

---

## API Endpoints

### CardPointe REST API

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/auth/{MID}` | POST | Authorize + optionally capture |
| `/capture/{MID}` | POST | Capture authorized transaction |
| `/void/{MID}` | POST | Void authorized/captured transaction |
| `/refund/{MID}` | POST | Issue refund |
| `/inquire/{MID}/{retref}` | GET | Query transaction status |
| `/profile/{MID}` | PUT | Create/update stored profile |
| `/profile/{MID}/{profileid}` | DELETE | Delete stored profile |

### Odoo Controller Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/payment/cardpoint/process` | POST JSON | Process payment form submission |
| `/payment/cardpoint/return` | GET/POST | Return URL callback |
| `/payment/cardpoint/webhook` | POST JSON | CardPointe webhook receiver |
| `/payment/cardpoint/status` | POST JSON | Poll transaction status |

---

## CardPointe Response Codes

| Code | Meaning | Odoo State |
|------|---------|-----------|
| `A` | Approved | `done` (or `authorized` if capture_mode=authorize) |
| `B` | Retry / Pending | `pending` |
| `C` | Declined | `cancel` |
| `D` | Declined – Pick Up Card | `cancel` |
| `F` | Declined – Do Not Honor | `cancel` |
| `P` | Pending (ACH) | `pending` |
| `R` | Referral | `cancel` |
| `E` | Error | `cancel` |

---

## Testing

### Run Tests

```bash
# All CardPointe tests
./odoo-bin -d test_db --test-enable --stop-after-init \
    --test-tags cardpoint -i payment_cardpoint

# Integration tests only
./odoo-bin -d test_db --test-enable --stop-after-init \
    --test-tags cardpoint_integration -i payment_cardpoint
```

### Test Card Numbers (CardPointe Sandbox)

| Card Type | Number | Notes |
|-----------|--------|-------|
| Visa | `4111111111111111` | Approved |
| Mastercard | `5454545454545454` | Approved |
| Discover | `6011000993026909` | Approved |
| Amex | `371449635398431` | Approved |
| Decline | `4386490000000005` | Always declined |

- **Expiry**: Any future date (e.g., `12/25`)
- **CVV**: Any 3 digits (e.g., `123`)
- **Amount**: Any amount under $500 for test

### Test ACH (Sandbox)

| Field | Value |
|-------|-------|
| Routing Number | `021000021` |
| Account Number | Any digits (e.g., `1234567890`) |
| Account Type | Checking or Savings |

### Sandbox Credentials

Contact CardConnect support for sandbox (`fts-uat.cardconnect.com`) credentials.
Sandbox MID format: typically all digits like `496160873888`.

---

## Tokenization

When **Enable Tokenization** is on, a `payment.token` record is created after successful payment, storing:

- `cardpoint_profile_id` — CardPointe profile identifier
- `cardpoint_acct_id` — Account within the profile
- `cardpoint_last4` — Last 4 digits for display
- `cardpoint_account_type` — VISA, MC, ECHK, etc.

Subsequent payments use the stored profile:
```python
account = f"{token.cardpoint_profile_id}/{token.cardpoint_acct_id}"
```

---

## Security

- **PCI Compliance**: CardPointe handles all card data. Card numbers should be tokenized via CardSecure before reaching Odoo servers.
- **API Credentials**: Stored with `groups='base.group_system'` — only visible to system administrators.
- **HTTPS**: All API communications use HTTPS to CardConnect servers.
- **CardSecure**: For production PCI DSS compliance, integrate CardSecure.js hosted fields (client-side tokenization) so raw card data never touches your server.

### Production CardSecure Integration

For full PCI compliance, replace the client-side card number submission with CardSecure tokenization:

```javascript
// Using CardSecure.js
const token = await CardSecure.tokenize({
    account: cardNumber,
    expiry: expiry,
    cvv: cvv,
});
// Submit token (not raw card data) to /payment/cardpoint/process
```

Obtain CardSecure integration details from your CardConnect account representative.

---

## Troubleshooting

### Common Issues

**"Connection refused" / "Cannot connect to API"**
- Verify Odoo server has internet access to `fts.cardconnect.com`
- Check firewall rules for outbound HTTPS (port 443)

**HTTP 401 Unauthorized**
- Verify API Username and Password are correct
- Check that credentials match the environment (test vs production)

**HTTP 400 Bad Request**
- Verify Merchant ID is correct (digits only)
- Ensure amount format is correct (e.g., "100.00" not "100")

**ACH transactions pending too long**
- ACH is inherently asynchronous; check webhook configuration
- Use `/payment/cardpoint/webhook` URL in CardPointe dashboard

**"Transaction not found" errors**
- Ensure the `orderid` field is being sent correctly in auth requests
- Check Odoo transaction reference format

### Debug Logging

Enable CardPointe debug logging in Odoo:
```python
# In odoo.conf or via UI
log_level = debug
# Or set specific logger:
logging.getLogger('odoo.addons.payment_cardpoint').setLevel('DEBUG')
```

---

## CardPointe API Reference

- **CardPointe Developer Docs**: https://developer.cardconnect.com/cardconnect-api
- **CardSecure Tokenization**: https://developer.cardconnect.com/cardsecure-api
- **Sandbox Environment**: https://fts-uat.cardconnect.com/
- **Production Environment**: https://fts.cardconnect.com/

---

## License

LGPL-3 — See LICENSE file for details.

---

## Support

For CardPointe API issues, contact CardConnect support.
For Odoo integration issues, check the module's test suite and logs.

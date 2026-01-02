# -*- coding: utf-8 -*-
"""Refresh Token Model for Pitch API.

This module implements secure refresh token storage with:
- PBKDF2-SHA256 token hashing (200k iterations)
- Device-bound tokens for session management
- Automatic token rotation on use
- Reuse detection and family revocation
- Automatic garbage collection of expired tokens
"""

import os
import hmac
import base64
import hashlib
import datetime
import logging
import time

from odoo import models, fields, api

_logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================

PBKDF2_ITERATIONS = 200000
MAX_TOKENS_PER_DEVICE = 5
GC_THRESHOLD_DAYS = 30
JWT_SECRET_PARAM_KEY = 'pitch_api.jwt_secret'


# =============================================================================
# JWT Secret Utilities
# =============================================================================

def get_jwt_secret(env):
    """Get or create the JWT secret from system parameters.

    This is the single source of truth for JWT secret management.
    The secret is created on first use and stored persistently.
    Uses cryptographically secure random bytes for key generation.

    Args:
        env: Odoo environment object.

    Returns:
        str: The JWT secret key (64-character hex string).
    """
    params = env['ir.config_parameter'].sudo()
    secret = params.get_param(JWT_SECRET_PARAM_KEY)

    if not secret:
        secret = os.urandom(64).hex()
        params.set_param(JWT_SECRET_PARAM_KEY, secret)
        _logger.info("Generated new JWT secret for Pitch API")

    return secret


# =============================================================================
# Token Hashing Utilities
# =============================================================================

def hash_token(token: str, salt: bytes = None) -> str:
    """Hash a refresh token using PBKDF2-HMAC-SHA256.

    Args:
        token: Plaintext token to hash.
        salt: Optional salt bytes (generated if not provided).

    Returns:
        str: Hashed token in format '<salt_hex>$<derived_key_hex>'.
    """
    if salt is None:
        salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", token.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"{salt.hex()}${dk.hex()}"


def verify_token_hash(stored_hash: str, token: str) -> bool:
    """Verify a plaintext token against a stored hash.

    Args:
        stored_hash: Hash in format '<salt_hex>$<derived_key_hex>'.
        token: Plaintext token to verify.

    Returns:
        bool: True if token matches, False otherwise.
    """
    try:
        salt_hex, dk_hex = stored_hash.split("$", 1)
        salt = bytes.fromhex(salt_hex)
        dk = hashlib.pbkdf2_hmac("sha256", token.encode("utf-8"), salt, PBKDF2_ITERATIONS)
        return hmac.compare_digest(dk.hex(), dk_hex)
    except (ValueError, AttributeError) as e:
        _logger.debug("Token hash verification failed: %s", e)
        return False
    except Exception as e:
        _logger.debug("Unexpected error verifying token hash: %s", e)
        return False


# Legacy aliases for backward compatibility
_hash_token = hash_token
_verify_token = verify_token_hash


# =============================================================================
# Refresh Token Model
# =============================================================================

class AuthRefreshToken(models.Model):
    """Secure refresh token storage with device binding.

    Security Features:
        - Tokens are stored as PBKDF2-SHA256 hashes
        - Device-bound tokens prevent cross-device use
        - Token families enable cascade revocation
        - Use count tracking detects token reuse attacks
        - Automatic cleanup of expired tokens

    Token Format:
        <token_id>.<random_bytes>.<checksum>.<timestamp>.<user_signature>
        - token_id: Unique identifier for direct database lookup (12 chars)
        - random_bytes: 32 bytes of cryptographic random data
        - checksum: HMAC-SHA256 of random_bytes
        - timestamp: Unix timestamp of generation
        - user_signature: HMAC-SHA256 binding token to user/device
    """

    _name = "auth.refresh.token"
    _description = "API Refresh Token"
    _order = "created_on desc"

    # =========================================================================
    # Fields
    # =========================================================================

    token_id = fields.Char(
        string="Token ID",
        required=False,  # Not required for backward compatibility with old tokens
        copy=False,
        index=True,
        help="Unique token identifier for O(1) lookup (new format tokens only)"
    )

    token_hash = fields.Char(
        string="Token Hash",
        required=True,
        copy=False,
        index=True,
        help="PBKDF2-SHA256 hash of the refresh token"
    )

    user_id = fields.Many2one(
        'res.users',
        string="User",
        required=True,
        ondelete='cascade',
        index=True,
        help="User who owns this token"
    )

    device_id = fields.Char(
        string="Device ID",
        required=True,
        index=True,
        help="Unique identifier for the client device"
    )

    device_name = fields.Char(
        string="Device Name",
        help="Human-readable device name"
    )

    client_info = fields.Text(
        string="Client Info",
        help="User agent and client metadata"
    )

    ip_address = fields.Char(
        string="IP Address",
        help="Last known IP address"
    )

    token_family = fields.Char(
        string="Token Family",
        required=True,
        index=True,
        help="Groups tokens from same login session"
    )

    created_on = fields.Datetime(
        string="Created",
        required=True,
        default=lambda self: fields.Datetime.now()
    )

    expires_on = fields.Datetime(
        string="Expires",
        required=True
    )

    last_used = fields.Datetime(
        string="Last Used",
        help="Last time this token was used"
    )

    use_count = fields.Integer(
        string="Use Count",
        default=0,
        help="Number of times token has been used"
    )

    revoked = fields.Boolean(
        string="Revoked",
        default=False,
        index=True
    )

    revocation_reason = fields.Selection(
        selection=[
            ('rotated', 'Token Rotated'),
            ('reuse_detected', 'Reuse Attempt Detected'),
            ('user_logout', 'User Logged Out'),
            ('admin_revoke', 'Administrative Revocation'),
            ('suspicious_activity', 'Suspicious Activity'),
            ('new_login', 'New Login on Device'),
            ('expired', 'Token Expired'),
        ],
        string="Revocation Reason",
        help="Why the token was revoked"
    )

    # =========================================================================
    # Token Generation
    # =========================================================================

    def _get_jwt_secret(self):
        """Get or create the JWT secret from system parameters."""
        return get_jwt_secret(self.env)

    def _get_token_family(self, user_id, device_id):
        """Get or create a token family ID for user+device combination.

        Token families group all refresh tokens from the same login session,
        enabling cascade revocation when reuse is detected.
        """
        existing = self.search([
            ('user_id', '=', user_id),
            ('device_id', '=', device_id),
            ('revoked', '=', False)
        ], limit=1)

        if existing:
            return existing.token_family

        return os.urandom(16).hex()

    def _generate_token(self, user_id, device_id):
        """Generate a structured refresh token with unique ID for fast lookup.

        Format: <token_id>.<random>.<checksum>.<timestamp>.<signature>

        The token_id is a 12-character unique identifier that allows O(1)
        database lookup without expensive hash comparisons.

        Returns:
            tuple: (plaintext_token, token_id) - store hash and token_id, return token once.
        """
        secret = self._get_jwt_secret()

        # Generate unique token_id for fast lookup (12 chars = 72 bits of entropy)
        token_id = base64.urlsafe_b64encode(os.urandom(9)).rstrip(b'=').decode()

        # Generate random component
        random_bytes = os.urandom(32)
        timestamp = str(int(time.time()))

        # Create checksum
        checksum = hmac.new(
            secret.encode(),
            random_bytes,
            hashlib.sha256
        ).digest()

        # Create user signature (includes token_id for binding)
        user_data = f"{token_id}{random_bytes.hex()}{timestamp}{user_id}{device_id}".encode()
        signature = hmac.new(
            secret.encode(),
            user_data,
            hashlib.sha256
        ).digest()

        # Encode components
        random_b64 = base64.urlsafe_b64encode(random_bytes).rstrip(b'=').decode()
        checksum_b64 = base64.urlsafe_b64encode(checksum).rstrip(b'=').decode()
        signature_b64 = base64.urlsafe_b64encode(signature).rstrip(b'=').decode()

        token_plain = f"{token_id}.{random_b64}.{checksum_b64}.{timestamp}.{signature_b64}"
        return token_plain, token_id

    # =========================================================================
    # Token Verification
    # =========================================================================

    def _extract_token_id(self, token_plain):
        """Extract token_id from a refresh token for fast lookup.

        Token format: <token_id>.<random>.<checksum>.<timestamp>.<signature>

        Returns:
            str or None: The token_id if valid format, None otherwise.
        """
        try:
            parts = token_plain.split('.')
            # New format has 5 parts, old format has 4
            if len(parts) == 5:
                return parts[0]  # token_id is first part
            return None  # Old format tokens don't have token_id
        except (AttributeError, TypeError) as e:
            _logger.debug("Failed to extract token_id: %s", e)
            return None

    def _verify_token_structure(self, token_plain):
        """Verify token structure and cryptographic components.

        Supports both old format (4 parts) and new format (5 parts with token_id).

        Returns:
            tuple: (is_valid, error_message)
        """
        try:
            parts = token_plain.split('.')

            # Support both old (4 parts) and new (5 parts) format
            if len(parts) == 5:
                # New format: <token_id>.<random>.<checksum>.<timestamp>.<signature>
                token_id, random_b64, checksum_b64, timestamp, signature_b64 = parts
            elif len(parts) == 4:
                # Old format: <random>.<checksum>.<timestamp>.<signature>
                random_b64, checksum_b64, timestamp, signature_b64 = parts
            else:
                return False, "Invalid token format"

            # Add padding helper
            def add_padding(b64):
                return b64 + '=' * (-len(b64) % 4)

            # Decode components
            random_bytes = base64.urlsafe_b64decode(add_padding(random_b64))
            checksum = base64.urlsafe_b64decode(add_padding(checksum_b64))

            # Verify checksum
            secret = self._get_jwt_secret()
            expected_checksum = hmac.new(
                secret.encode(),
                random_bytes,
                hashlib.sha256
            ).digest()

            if not hmac.compare_digest(checksum, expected_checksum):
                return False, "Invalid token checksum"

            # Validate timestamp (reject tokens from far future)
            now = int(time.time())
            token_time = int(timestamp)
            if token_time - now > 600:  # 10 minutes tolerance
                return False, "Token timestamp invalid"

            return True, None

        except Exception as e:
            return False, f"Token verification failed: {e}"

    @api.model
    def verify_token(self, token_plain, device_id, ip_address=None):
        """Verify a refresh token and check for reuse.

        Uses O(1) token_id lookup instead of expensive hash scanning.

        Args:
            token_plain: Plaintext refresh token.
            device_id: Device ID (must match token's device).
            ip_address: Optional IP for audit logging.

        Returns:
            tuple: (token_record, is_valid) or (False, False)
        """
        now = fields.Datetime.now()

        # Verify structure first (cheap)
        is_valid, error = self._verify_token_structure(token_plain)
        if not is_valid:
            _logger.warning("Token structure verification failed: %s", error)
            return False, False

        # Try O(1) lookup by token_id (new format tokens)
        token_id = self._extract_token_id(token_plain)
        matching = None

        if token_id:
            # Fast path: Direct lookup by token_id (indexed, O(1))
            matching = self.search([
                ('token_id', '=', token_id),
                ('device_id', '=', device_id),
                ('revoked', '=', False),
                ('expires_on', '>', now)
            ], limit=1)

            # Verify hash matches (single token, very fast)
            if matching and not verify_token_hash(matching.token_hash, token_plain):
                _logger.warning("Token hash mismatch for token_id=%s", token_id)
                matching = None
        else:
            # Fallback for old format tokens (no token_id)
            # This is slow but only needed for legacy tokens
            _logger.debug("Old format token detected, using hash scan")
            candidates = self.search([
                ('device_id', '=', device_id),
                ('revoked', '=', False),
                ('expires_on', '>', now),
                ('token_id', '=', False)  # Only old tokens without token_id
            ], limit=50)  # Limit to prevent extreme slowness

            for candidate in candidates:
                if verify_token_hash(candidate.token_hash, token_plain):
                    matching = candidate
                    break

        if not matching:
            return False, False

        # Reuse detection: token should only be used once before rotation
        if matching.use_count > 0:
            _logger.warning(
                "Token reuse detected: user_id=%s device=%s family=%s",
                matching.user_id.id, device_id, matching.token_family
            )
            # Revoke entire token family
            family_tokens = self.search([
                ('token_family', '=', matching.token_family)
            ])
            family_tokens.write({
                'revoked': True,
                'revocation_reason': 'reuse_detected'
            })
            return False, False

        # Update usage tracking
        matching.sudo().write({
            'last_used': now,
            'use_count': matching.use_count + 1,
            'ip_address': ip_address or matching.ip_address
        })

        return matching, True

    # =========================================================================
    # Token Creation
    # =========================================================================

    @api.model
    def create_for_user(self, user, device_id=None, device_name=None,
                        client_info=None, ip_address=None,
                        expires_seconds=None):
        """Create a new refresh token for a user.

        Args:
            user: res.users record.
            device_id: Unique device identifier.
            device_name: Human-readable device name.
            client_info: User agent string.
            ip_address: Client IP address.
            expires_seconds: Token lifetime in seconds (required).

        Returns:
            tuple: (token_record, plaintext_token)
        
        Raises:
            ValueError: If expires_seconds is not provided.
        """
        if not expires_seconds:
            raise ValueError("expires_seconds is required")

        # Generate token with unique ID for fast lookup
        token_plain, token_id = self._generate_token(user.id, device_id)
        token_hashed = hash_token(token_plain)

        # Calculate expiry
        expires = fields.Datetime.to_string(
            fields.Datetime.from_string(fields.Datetime.now()) +
            datetime.timedelta(seconds=expires_seconds)
        )

        # Get token family
        token_family = self._get_token_family(user.id, device_id)

        # Create record with token_id for O(1) lookup
        record = self.sudo().create({
            'token_id': token_id,
            'token_hash': token_hashed,
            'user_id': user.id,
            'device_id': device_id,
            'device_name': device_name,
            'client_info': client_info,
            'ip_address': ip_address,
            'expires_on': expires,
            'token_family': token_family,
        })

        _logger.info(
            "Created refresh token: user_id=%s device=%s",
            user.id, device_id
        )

        return record, token_plain

    # =========================================================================
    # Token Revocation
    # =========================================================================

    def revoke(self, reason='user_logout'):
        """Revoke this refresh token.

        Args:
            reason: Revocation reason selection value.

        Returns:
            bool: True on success.
        """
        self.sudo().write({
            'revoked': True,
            'revocation_reason': reason
        })
        _logger.info(
            "Revoked token: id=%s user_id=%s reason=%s",
            self.id, self.user_id.id, reason
        )
        return True

    @api.model
    def revoke_all_for_user(self, user_id, reason='admin_revoke'):
        """Revoke all refresh tokens for a user.

        Args:
            user_id: User ID to revoke tokens for.
            reason: Revocation reason.

        Returns:
            int: Number of tokens revoked.
        """
        tokens = self.search([
            ('user_id', '=', user_id),
            ('revoked', '=', False)
        ])
        tokens.write({
            'revoked': True,
            'revocation_reason': reason
        })
        _logger.info(
            "Revoked %s tokens for user_id=%s reason=%s",
            len(tokens), user_id, reason
        )
        return len(tokens)

    # =========================================================================
    # Cleanup
    # =========================================================================

    def _cleanup_old_tokens(self, user_id, device_id):
        """Cleanup old and expired tokens for a user/device.

        Keeps only the most recent tokens per device.
        """
        now = fields.Datetime.now()

        # Revoke expired tokens
        expired = self.search([
            ('user_id', '=', user_id),
            ('revoked', '=', False),
            ('expires_on', '<', now)
        ])
        if expired:
            expired.write({
                'revoked': True,
                'revocation_reason': 'expired'
            })

        # Keep only last N tokens per device
        active = self.search([
            ('user_id', '=', user_id),
            ('device_id', '=', device_id),
            ('revoked', '=', False)
        ], order='created_on desc')

        if len(active) > MAX_TOKENS_PER_DEVICE:
            to_revoke = active[MAX_TOKENS_PER_DEVICE:]
            to_revoke.write({
                'revoked': True,
                'revocation_reason': 'rotated'
            })

    @api.autovacuum
    def _gc_expired_tokens(self):
        """Garbage collect old revoked tokens.

        Removes tokens revoked more than 30 days ago.
        """
        threshold = fields.Datetime.to_string(
            fields.Datetime.from_string(fields.Datetime.now()) -
            datetime.timedelta(days=GC_THRESHOLD_DAYS)
        )

        old_tokens = self.search([
            ('revoked', '=', True),
            ('created_on', '<', threshold)
        ])

        if old_tokens:
            count = len(old_tokens)
            old_tokens.unlink()
            _logger.info("Garbage collected %s expired refresh tokens", count)

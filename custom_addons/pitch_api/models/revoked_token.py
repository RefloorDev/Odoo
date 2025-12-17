import hashlib
import os
import datetime
import logging
from odoo import models, fields, api

_logger = logging.getLogger(__name__)


def _hash_token(token: str, salt: bytes = None) -> str:
    """Hash a token using PBKDF2-HMAC-SHA256."""
    if salt is None:
        salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", token.encode("utf-8"), salt, 200000)
    return "%s$%s" % (salt.hex(), dk.hex())


def _verify_token(stored: str, token: str) -> bool:
    """Verify a plaintext token against the stored hash."""
    try:
        salt_hex, dk_hex = stored.split("$", 1)
    except Exception:
        return False
    salt = bytes.fromhex(salt_hex)
    dk = hashlib.pbkdf2_hmac("sha256", token.encode("utf-8"), salt, 200000)
    return dk.hex() == dk_hex


class AuthRevokedToken(models.Model):
    _name = "auth.revoked.token"
    _description = "Revoked API Tokens"

    jti = fields.Char(string="Token ID", required=True, index=True, 
                     help="Unique identifier for the token")
    token_hash = fields.Char(string="Token Hash", index=True,
                          help="Hashed value of access token (optional; refresh tokens managed elsewhere)")
    token_type = fields.Selection([
        ('access', 'Access Token'),
        ('refresh', 'Refresh Token')
    ], required=True, default='access')
    user_id = fields.Many2one('res.users', string="User")
    revoked_on = fields.Datetime(default=lambda self: fields.Datetime.now())
    expires_on = fields.Datetime()

    @api.model
    def is_revoked(self, jti: str) -> bool:
        """Check if an access token is revoked by its JTI."""
        return bool(self.search([
            ("jti", "=", jti),
            ("token_type", "=", "access")
        ], limit=1))

    @api.model
    def revoke_access_token(self, jti, expires_on=None):
        """Revoke an access token.

        Args:
            jti (str): JWT ID of the access token
            expires_on (datetime|str|None): Optional expiry timestamp of the token; used for GC
        """
        vals = {
            'jti': jti,
            'token_type': 'access'
        }
        if expires_on:
            try:
                # Accept both datetime and string
                vals['expires_on'] = expires_on
            except Exception:
                pass
        return self.sudo().create(vals)

    @api.autovacuum
    def _gc_revoked_tokens(self):
        """Garbage collect old revoked access tokens.

        Deletes records that expired over 30 days ago or were revoked over 90 days ago.
        """
        now = fields.Datetime.from_string(fields.Datetime.now())
        # 30 days past expiry
        threshold_expired = fields.Datetime.to_string(
            now - datetime.timedelta(days=30)
        )
        # 90 days past revocation
        threshold_revoked = fields.Datetime.to_string(
            now - datetime.timedelta(days=90)
        )
        domain = ['|',
                  ('expires_on', '!=', False), ('expires_on', '<', threshold_expired),
                  ('revoked_on', '<', threshold_revoked)]
        old = self.search(domain)
        if old:
            old.unlink()

    # NOTE: This model is intentionally limited to tracking revoked access tokens.
    # Refresh-token lifecycle lives entirely in `auth.refresh.token`.

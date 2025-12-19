# -*- coding: utf-8 -*-
{
    'name': 'Pitch API',
    'version': '1.1',
    'category': 'Sales/Sales',
    'author': 'Sagar Mokariya',
    'website': 'https://www.xeonglobal.com',
    'summary': 'Pitch API - JWT authentication for external integrations',
    'description': """Pitch API provides a small authentication service for external
systems to authenticate against Odoo. It issues JWT access tokens and
rotating refresh tokens after validating Odoo username/password using
Odoo's standard authentication flow. The implementation keeps all code in
the `pitch_api` module and avoids schema changes to core models.

Features:
- /api/auth/login: exchange username/password for access + refresh tokens
- /api/auth/refresh: rotate refresh token and issue new access token
- /api/auth/logout: revoke access and/or refresh tokens
- /api/auth/introspect: validate token and return claims/active

Security notes: tokens are signed using a server secret stored in
`ir.config_parameter` (key: pitch_api.jwt_secret). Refresh tokens are
stored hashed using PBKDF2-SHA256.
""",
    'depends': ['team_api_connection'],
    'data': [
        'security/ir.model.access.csv',
        'views/refresh_token_views.xml',
        'views/revoked_token_views.xml',
        'views/res_users_views.xml',

        # Wizard
        'wizard/pitch_api_access_wizard_views.xml',
    ],
    'external_dependencies': {
        'python': ['PyJWT'],
    },
    'installable': True,
    'auto_install': False,
    'license': 'OPL-1',
}

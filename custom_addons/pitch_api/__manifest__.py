# -*- coding: utf-8 -*-
{
    'name': 'Pitch API',
    'version': '18.0.1.0.0',
    'category': 'Technical/API',
    'author': 'Xeon Global',
    'website': 'https://www.xeonglobal.com',
    'summary': 'JWT-based REST API for external system integration',
    'description': """
Pitch API - JWT Authentication & REST API for Odoo
===================================================

A comprehensive REST API module providing JWT-based authentication
and secure data access for external system integration.

Features
--------
* **JWT Authentication**: Secure token-based authentication
* **Token Rotation**: Automatic refresh token rotation for security
* **Device Management**: Multi-device session tracking and control
* **Role-Based Access**: Admin and user-level API endpoints
* **Appointment API**: Full CRUD access to appointments data
* **User Management**: Admin endpoints for user management

API Endpoints
-------------
**Authentication** (/api/auth/...):
    * POST /login - Exchange credentials for tokens
    * POST /refresh - Rotate refresh token
    * POST /logout - Revoke tokens
    * POST /introspect - Validate token
    * GET /me - Current user profile
    * GET /devices - List active sessions

**User Appointments** (/api/appointments/...):
    * GET / - List appointments
    * GET /today - Today's appointments
    * GET /<id> - Single appointment

**Admin Appointments** (/api/admin/appointments/...):
    * Full access to all appointments with advanced filtering

**User Management** (/api/users/...):
    * Admin-only user listing and lookup

Security
--------
* JWT tokens signed with HMAC-SHA256
* Refresh tokens hashed with PBKDF2-SHA256 (200k iterations)
* Device-bound refresh tokens
* Automatic token revocation tracking

Configuration
-------------
System Parameters (ir.config_parameter):
    * pitch_api.jwt_secret - JWT signing secret (auto-generated)
    * pitch_api.jwt_expiration - Access token lifetime (default: 3600s)
    * pitch_api.refresh_token_expiration - Refresh token lifetime (default: 30 days)
""",
    'depends': ['team_api_connection'],
    'data': [
        'security/ir.model.access.csv',
        'views/refresh_token_views.xml',
        'views/revoked_token_views.xml',
        'views/res_users_views.xml',
    ],
    'external_dependencies': {
        'python': ['PyJWT'],
    },
    'installable': True,
    'auto_install': False,
    'application': False,
    'license': 'OPL-1',
}

# -*- coding: utf-8 -*-
"""Pitch API Module.

A comprehensive JWT-based REST API authentication and data access layer
for external system integration with Odoo.

Architecture:
    - Controllers: REST API endpoints for authentication and data access
    - Models: Token storage and user extensions
    - Security: Role-based access control with admin privileges

Authentication Flow:
    1. Client sends username/password to /api/auth/login
    2. Server validates credentials and returns JWT access + refresh tokens
    3. Client uses access token (Bearer) for API requests
    4. When access token expires, use refresh token at /api/auth/refresh
    5. Refresh tokens rotate on each use for enhanced security

API Endpoints:
    Authentication (/api/auth/...):
        - POST /login     - Get tokens with credentials
        - POST /refresh   - Rotate tokens
        - POST /logout    - Revoke tokens
        - POST /introspect - Validate token
        - GET  /me        - Current user profile
        - GET  /devices   - List active sessions

    User Appointments (/api/appointments/...):
        - GET /           - List user's appointments
        - GET /today      - Today's appointments
        - GET /<id>       - Single appointment
        - GET /<id>/app_screen_logs - Screen logs
        - GET /<id>/app_live_screen_logs - Live logs

    Admin Appointments (/api/admin/appointments/...):
        - GET /           - List all appointments
        - GET /today      - Today's appointments
        - GET /<id>       - Single appointment
        - GET /<id>/app_screen_logs - Screen logs
        - GET /<id>/app_live_screen_logs - Live logs

    Admin Users (/api/users/...):
        - GET /           - List all users
        - GET /<id>       - Get user by ID
        - GET /lookup     - Lookup by login
        - GET /exists     - Check if user exists
        - GET /<id>/groups - Get user groups

    Market Segments (/api/admin/market-segments):
        - GET /           - List distinct market segments

Security Notes:
    - JWT tokens signed with HMAC-SHA256 using server secret
    - Refresh tokens hashed with PBKDF2-SHA256 (200k iterations)
    - Device-bound refresh tokens for session management
    - Automatic token rotation to prevent reuse attacks
    - Admin endpoints require is_pitch_admin=True flag
"""

from . import controllers
from . import models

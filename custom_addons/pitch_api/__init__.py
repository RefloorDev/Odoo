# -*- coding: utf-8 -*-
"""Pitch API package

This package contains models and controllers that implement a JWT-based
authentication service for external systems to integrate with Odoo.

Design goals:
- Reuse Odoo's `res.users` for authentication (username/password).
- Issue short-lived JWT access tokens and long-lived refresh tokens.
- Store only hashed refresh tokens in the database.
- Provide introspect/revoke/logout endpoints to manage tokens.

All implementation lives inside the `pitch_api` module to keep integration
concerns together and to avoid touching core Odoo code.
"""

from . import controllers
from . import models
from . import wizard

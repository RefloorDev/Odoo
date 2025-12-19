## Pitch API — Full Reference

This document describes the HTTP API exposed by the `pitch_api` module. It includes authentication endpoints (token issuance, rotation, introspection, revocation, device management) and appointment endpoints used by the mobile/web clients. The documentation lists every route, required headers and request body fields, optional parameters, expected responses, common error codes, and examples.

Note: This API is designed to run inside Odoo. The examples show JSON bodies and curl commands; replace <HOST>, <USER>, <PASS>, and token placeholders with real values for your environment.

---

## Table of Contents
- Overview
- Conventions
- Authentication
  - Token types and formats
  - Required headers (device binding)
  - `POST /api/auth/login`
  - `POST /api/auth/refresh`
  - `POST /api/auth/logout`
  - `POST /api/auth/introspect`
  - `POST /api/auth/revoke_refresh`
  - `GET  /api/auth/devices`
  - `GET  /api/auth/me`
- Appointments API
  - `GET /api/appointments/{appointment_id}`
  - `GET /api/appointments`
  - `GET /api/appointments/paginated`
  - `GET /api/appointments/today`
  - `GET /api/appointments/{appointment_id}/app_screen_logs`
- Users API (admin)
  - `GET /api/users`
  - `GET /api/users/{user_id}`
  - `GET /api/users/lookup`
  - `GET /api/users/exists`
  - `GET /api/users/{user_id}/groups`
  - `GET /api/users/groups`
- Common error codes and shapes
- Example flows (login → refresh → use)
- Notes and operational guidance

---

## Overview

Authentication is based on short-lived access tokens (JWT, HS256) and longer-lived refresh tokens which are device-bound and stored hashed in the DB. Clients should:

- Keep refresh tokens private and stored securely on the client (they are presented to rotate to a new access token).
- Present the access token in the `Authorization` request header as `Bearer <access_token>` for protected endpoints (appointments, devices, etc.).
- Include `X-Device-ID` in device-bound endpoints (login, refresh). Device ID is mandatory for device-aware operations.

Server responses follow a standard shape for errors: a JSON object with `error` and `error_description` keys. Success responses vary by route and are documented per endpoint. All responses are delivered with the JSON content type.

Security note: Logs are instrumented to mask tokens; production logs should be collected in a secure aggregator and rotated appropriately.

## Conventions

- Path parameters are shown in braces, for example `{appointment_id}`. Unless stated otherwise, IDs are integers.
- All request/response bodies are JSON. When sending a body, set `Content-Type: application/json`.
- Authorization header format is `Authorization: Bearer <token>`.
- All active Odoo users can authenticate and obtain/refresh tokens.

## Authentication — Token types and formats

1. Access token (JWT, HS256): three parts separated by `.` (two `.` characters). It contains claims such as:
   - `iss` (issuer)
   - `sub` (subject; user id)
   - `uid` (user id)
   - `exp` (expiration timestamp)
   - `jti` (JWT ID)
   - `device_id` (device id used at login)

  Usage: set `Authorization: Bearer <access_token>` on protected endpoints.

2. Refresh token (device-bound): custom token encoded as a dot-separated string. The server stores a hashed representation and only returns the plaintext once (at issuance). Refresh tokens:
   - Are bound to a `device_id` (header `X-Device-ID`) where required.
   - Are rotated on use (old refresh token revoked and a new one issued).

Always treat refresh tokens as highly sensitive. When the client uses a refresh token to obtain a new access token, the refresh token is revoked and replaced.

## Required headers (global, per-route notes)

- Authorization: `Bearer <access_token>` — required for protected endpoints (appointments, devices, me). Some auth endpoints accept token in body/query as fallback.
- X-Device-ID: string. Required in routes that create or verify device-bound refresh tokens such as `/api/auth/login`, `/api/auth/refresh`, and `/api/auth/logout`. If missing in `login` the request will fail.
- X-Device-Name: optional, human-readable device name for login.
- X-App-Version: optional, client version string.

All endpoints accept and return JSON. For `POST` endpoints, send `Content-Type: application/json` and a JSON body as declared below.

---

## POST /api/auth/login

Exchange username/password for an access token and device-bound refresh token.

- URL: `/api/auth/login`
- Method: POST
- Auth: none (external clients)
- Required headers:
  - `X-Device-ID`: string (required)
  - `Content-Type: application/json`
- Optional headers: `X-Device-Name`, `X-App-Version`

Request body (JSON):

Required fields:
- `username` or `login` (string) — required
- `password` (string) — required

Optional fields:
- `device_name` (string) — overrides header `X-Device-Name` when present

Successful response (200):

{
  "access_token": "<jwt-token>",
  "token_type": "bearer",
  "expires_in": 3600,            // seconds until access token expiry
  "refresh_token": "<refresh_plaintext>",
  "user_id": 123,                 // Odoo user ID
  "improveit_user_id": "I360-456" // i360/improveit user ID (nullable)
}

Errors:
- 400 Invalid request — missing device id or required body fields.
- 401 invalid_grant — invalid credentials.
- 403 access_denied — user is not authorized for Pitch API (contact an administrator).
- 500 server_error — internal issue (e.g. missing PyJWT or JWT generation failure).

Example curl:

```bash
curl -X POST https://<HOST>/api/auth/login \
  -H 'Content-Type: application/json' \
  -H 'X-Device-ID: device-uuid-123' \
  -d '{"username":"user@example.com","password":"Secret!","device_name":"Sagar Phone"}'
```

Notes:
- If there is an existing non-revoked refresh token record for the same `user_id` + `device_id`, it is revoked and replaced.

---

## POST /api/auth/refresh

Rotate a refresh token and issue a new access token + refresh token.

- URL: `/api/auth/refresh`
- Method: POST
- Auth: none
- Required headers:
  - `X-Device-ID`: string (required) — refresh tokens are device-bound
  - `Content-Type: application/json`

Request body (JSON):

Required fields:
- `refresh_token` (string) — plaintext refresh token obtained from login or a prior refresh

Successful response (200):

{
  "access_token": "<jwt-token>",
  "token_type": "bearer",
  "expires_in": 3600,
  "refresh_token": "<new_refresh_plaintext>"
}

Note: Unlike `/api/auth/login`, this endpoint does NOT return `user_id` or `improveit_user_id` fields.

Errors:
- 400 invalid_request — missing device id or refresh_token
- 401 invalid_grant — invalid or revoked refresh token
- 403 access_denied — user is not authorized for Pitch API; the presented refresh token will be revoked.
- 500 server_error — unexpected server error

Notes:
- Rotation: the supplied refresh token will be revoked if valid and a new refresh token will be created for the same device.
- The endpoint uses model-level verification; the controller accepts a refresh token and verifies the hashed record stored in DB.

Example curl:

```bash
curl -X POST https://<HOST>/api/auth/refresh \
  -H 'Content-Type: application/json' \
  -H 'X-Device-ID: device-uuid-123' \
  -d '{"refresh_token":"<OLD_REFRESH_TOKEN>"}'
```

---

## POST /api/auth/logout

Logout and revoke tokens. Supports single-device logout or all-devices logout.

- URL: `/api/auth/logout`
- Method: POST
- Auth: none (token supplied via Authorization header)
- Required headers:
  - `Authorization: Bearer <access_token|refresh_token>` — header must contain either the access or refresh token
  - `X-Device-ID`: string (required) — used to identify the device when revoking refresh tokens for the current device

Request body (JSON):

Optional fields:
- `logout_all` (boolean) — if true, revoke all non-revoked refresh tokens for the user across devices

Behavior:
- If `logout_all` is `true`, the server will identify the user from the provided Authorization header (access or refresh) and revoke all non-revoked refresh tokens for that user. The current access token `jti` (if present) will also be revoked.
- If `logout_all` is omitted or `false`, the server tries to revoke the refresh token associated with the provided header (when header contains a refresh token) or revoke the access token `jti` (when header contains an access token).

Responses:
- Success (single-device): {"revoked": true, "device_id": "<device>"}, 200
- Success (all-devices): {"revoked": true, "all_devices": true, "device_count": <n>}, 200
- 400 invalid_request — missing authorization, malformed header, or missing X-Device-ID when required

Example curl (single-device, using access token):

```bash
curl -X POST https://<HOST>/api/auth/logout \
  -H 'Authorization: Bearer <ACCESS_TOKEN>' \
  -H 'X-Device-ID: device-uuid-123'
```

Example curl (all-devices):

```bash
curl -X POST https://<HOST>/api/auth/logout \
  -H 'Authorization: Bearer <ACCESS_TOKEN_OR_REFRESH>' \
  -H 'X-Device-ID: device-uuid-123' \
  -d '{"logout_all":true}'
```

---

## POST /api/auth/introspect

Introspect an access or refresh token. Returns a JSON object describing whether the token is active and metadata.

- URL: `/api/auth/introspect`
- Method: POST
- Auth: none
- Content-Type: application/json

Request body (JSON):

Preferred fields (explicit):
- `access_token` (string) — optional, when provided introspection treats the token as access token
- `refresh_token` (string) — optional, when provided introspection treats the token as refresh token

If neither explicit key is present, the controller will look for an Authorization header `Bearer <token>` and auto-detect by format: tokens with 2 dots are treated as access tokens, others as refresh tokens.

Successful response (200):

- Access token active example:

{
  "active": true,
  "token_type": "access_token",
  "token_use": "access",
  // additional claims may be included depending on token payload
}

- Refresh token active example:

{
  "active": true,
  "token_type": "refresh_token",
  "token_use": "refresh",
  "device_id": "device-uuid-123",
  "expires_at": "2025-11-12 10:00:00",
  "created_at": "2025-10-10 09:00:00"
}

Error responses (examples):
- 400 missing_token — no token provided
- 200 with {"active": false, "reason": "expired|revoked|invalid_signature|not_found|invalid_format"} when token is not valid

Example curl:

```bash
curl -X POST https://<HOST>/api/auth/introspect \
  -H 'Content-Type: application/json' \
  -d '{"access_token":"<ACCESS_TOKEN>"}'
```

---

## POST /api/auth/revoke_refresh

Client-initiated revocation of a refresh token.

- URL: `/api/auth/revoke_refresh`
- Method: POST
- Auth: none
- Content-Type: application/json
- Preferred: Send refresh token in JSON body `refresh_token` but Authorization header `Bearer <refresh_token>` is also accepted as fallback.
- If `X-Device-ID` header is present, it will be used to validate device binding.

Request body:
- `refresh_token` (string) — required (or present in Authorization header)

Success response (200):

{
  "revoked": true,
  "device_id": "device-uuid-123",
  "user_id": 123
}

Errors:
- 400 invalid_request — missing token
- 404 invalid_token — token not found (already revoked or unknown)

Example curl:

```bash
curl -X POST https://<HOST>/api/auth/revoke_refresh \
  -H 'Content-Type: application/json' \
  -d '{"refresh_token":"<REFRESH_TOKEN>"}'
```

---

## GET /api/auth/devices

List active (non-revoked) device sessions (refresh-token records) for a user.

- URL: `/api/auth/devices`
- Method: GET
- Auth: none (Authorization header recommended)
- Authorization: `Bearer <access_token>` preferred. Alternatively, `token` query param or body keys are accepted but not recommended.

Query parameters (optional):
- `token` — token string fallback (less secure)
- `token_type_hint` — `access_token` or `refresh_token` (helps server detect type)

Response (200):

{
  "user_id": 123,
  "device_count": 2,
  "devices": [
    {
      "id": 321,
      "device_id": "device-uuid-123",
      "device_name": "Sagar Phone",
      "created_on": "2025-10-10 09:00:00",
      "expires_on": "2025-11-10 09:00:00",
      "last_used": "2025-11-05 10:00:00",
      "ip_address": "1.2.3.4",
      "revoked": false,
      "revocation_reason": null,
      "token_family": "<family-id>",
      "use_count": 5
    }
  ]
}

Errors:
- 400 invalid_request — missing token or could not determine user
- 401 invalid_token — token invalid when introspection fails

---

## GET /api/auth/me

Return basic profile for the user identified by the provided token.

- URL: `/api/auth/me`
- Method: GET
- Auth: none (Authorization header preferred)

Header: `Authorization: Bearer <access_token>` is preferred. If no header, `token` query parameter may be used.

---

## GET /api/users (admin-only)

List all users with key profile fields. The caller must be a Pitch API Admin (`is_pitch_admin=True`).

- URL: `/api/users`
- Method: GET
- Auth: `Authorization: Bearer <access_token>` (access token for a Pitch API Admin)
- Query params (optional):
  - `active` (`true` | `false` | not provided)
    - `active=true`: only active users
    - `active=false`: only inactive users
    - If param not provided: returns ALL users (both active and inactive)

Response (200):

```
{
  "admin_user_id": 1,
  "count": 2,
  "active_filter": "all",  // Shows 'all' if no param provided, or the actual value if provided
  "users": [
    {
      "id": 7,
      "name": "Demo User",
      "login": "demo@example.com",
      "active": true,
      "tz": "UTC",
      "company_id": 1,
      "company_name": "Your Company",
      "login_date": "2025-11-12 10:00:00",
      "is_pitch_admin": false,
      "improveit_user_id": "I360-456"
    }
  ]
}
```

Important Implementation Notes:
- When no `active` parameter is provided, the endpoint uses `with_context(active_test=False)` to bypass Odoo's default active filtering, ensuring both active and inactive users are returned.
- The `active_filter` field in the response shows 'all' when no parameter is provided.
- Groups information has been moved to dedicated endpoints. Use `/api/users/{user_id}/groups` or `/api/users/groups` to fetch group memberships.

Errors:
- 400 invalid_request — missing or malformed Authorization header
- 401 invalid_token — token invalid or expired
- 403 forbidden — caller is not a Pitch API Admin

Example curl:

```bash
curl -X GET https://<HOST>/api/users \
  -H 'Authorization: Bearer <ACCESS_TOKEN>'
```

---
### GET /api/users/{user_id} (admin-only)

Get a single user's profile (without groups).

- URL: `/api/users/{user_id}`
- Method: GET
- Auth: Pitch API Admin access token

Path parameters:
- `user_id` (integer)

Response (200):
```
{
  "id": 7,
  "name": "Demo User",
  "login": "demo@example.com",
  "active": true,
  "tz": "UTC",
  "company_id": 1,
  "company_name": "Your Company",
  "login_date": "2025-11-12 10:00:00",
  "is_pitch_admin": false,
  "improveit_user_id": "I360-456"
}
```

Errors:
- 403 — forbidden (not admin)
- 404 — not_found (user does not exist)

Example:
```bash
curl -X GET https://<HOST>/api/users/42 \
  -H 'Authorization: Bearer <ADMIN_ACCESS_TOKEN>'
```

---

### GET /api/users/lookup (admin-only)

Lookup a user by id or login.

- URL: `/api/users/lookup`
- Method: GET
- Auth: Pitch API Admin access token
- Query params (one required):
  - `user_id` (integer) OR `login` (string)

Responses:
- 200 — serialized user object
- 400 — invalid_request (neither user_id nor login provided)
- 403 — forbidden (not admin)
- 404 — not_found (no matching user)

Example:
```bash
curl -X GET 'https://<HOST>/api/users/lookup?login=demo@example.com' \
  -H 'Authorization: Bearer <ADMIN_ACCESS_TOKEN>'
```

---

### GET /api/users/exists (admin-only)

Check if a user exists by id or login.

- URL: `/api/users/exists`
- Method: GET
- Auth: Pitch API Admin access token
- Query params (one required):
  - `user_id` (integer) OR `login` (string)

Response (200):
```
{ "exists": true }
```

Errors:
- 400 invalid_request — missing both user_id and login
- 403 forbidden — not admin

Example:
```bash
curl -X GET 'https://<HOST>/api/users/exists?user_id=42' \
  -H 'Authorization: Bearer <ADMIN_ACCESS_TOKEN>'
```

---

### GET /api/users/{user_id}/groups (admin-only)

Get detailed group information for a single user.

- URL: `/api/users/{user_id}/groups`
- Method: GET
- Auth: Pitch API Admin access token

Path parameters:
- `user_id` (integer)

Response (200):
```
{
  "user_id": 7,
  "user_login": "demo@example.com",
  "user_name": "Demo User",
  "groups_count": 3,
  "groups": [
    {
      "id": 10,
      "name": "Settings",
      "xml_id": "base.group_system",
      "category_id": 1,
      "category_name": "Administration"
    },
    {
      "id": 15,
      "name": "User",
      "xml_id": "base.group_user",
      "category_id": 1,
      "category_name": "Administration"
    }
  ]
}
```

Errors:
- 403 — forbidden (not admin)
- 404 — not_found (user does not exist)

Example:
```bash
curl -X GET 'https://<HOST>/api/users/7/groups' \
  -H 'Authorization: Bearer <ADMIN_ACCESS_TOKEN>'
```

---

### GET /api/users/groups (admin-only)

Get detailed group information for multiple users.

- URL: `/api/users/groups`
- Method: GET
- Auth: Pitch API Admin access token
- Query params (required):
  - `user_ids` (string) — comma-separated user IDs (e.g., "1,2,3")

Response (200):
```
{
  "count": 2,
  "users": [
    {
      "user_id": 7,
      "user_login": "demo@example.com",
      "user_name": "Demo User",
      "groups_count": 3,
      "groups": [
        {"id": 10, "name": "Settings", "xml_id": "base.group_system", "category_id": 1, "category_name": "Administration"}
      ]
    },
    {
      "user_id": 8,
      "user_login": "admin@example.com",
      "user_name": "Admin User",
      "groups_count": 5,
      "groups": [...]
    }
  ]
}
```

Errors:
- 400 — invalid_request (missing or invalid user_ids parameter)
- 403 — forbidden (not admin)

Example:
```bash
curl -X GET 'https://<HOST>/api/users/groups?user_ids=7,8,9' \
  -H 'Authorization: Bearer <ADMIN_ACCESS_TOKEN>'
```

Note: Only existing users will be included in the response. Non-existent user IDs are silently skipped.

---

Response (200):

{
  "user": {
    "id": 123,
    "name": "Full Name",
    "login": "user@example.com",
    "email": "user@example.com",
    "tz": "America/Chicago",
    "active": true
  }
}

Errors:
- 400 invalid_request — missing token or cannot determine user
- 401 invalid_token — token introspection returned inactive
- 404 not_found — user record not found

---

## Appointments API (requires access token)

All appointment endpoints require a valid access token presented in the `Authorization` header as `Bearer <access_token>`.

### GET /api/appointments/{appointment_id}

Return a single appointment if the requesting user is authorized.

- URL: `/api/appointments/{appointment_id}`

Path parameters:
- `appointment_id` (integer) — appointment record ID
- Method: GET
- Required header: `Authorization: Bearer <access_token>`

Responses:
- 200 — appointment object (see serialization below)
- 403 — user not authorized to view this appointment
- 404 — appointment not found

Appointment serialization fields:
- `id` — appointment record id
- `improveit_appointment_id`, `name`, `state` — common fields
- `partner_id` — partner id
- `customer_name` — string
- `applicant_data` — object with applicant fields (first/middle/last, address, phone, email)
- `co_applicant_data` — object with co-applicant fields
- `appointment_date`, `arrival_date`, `departure_date`, `manual_arrival_date` — ISO datetime strings
- `app_screen_logs` — list of simple objects {completion_date, name}
- `user_id` and `user_data` — owner information
- and many additional boolean and relational fields.

(This serialization follows the `_serialize_appointment` helper in the controller.)

### GET /api/appointments

List appointments scoped to the authenticated user.

- URL: `/api/appointments`
- Method: GET
- Query parameters:
  - `limit` (optional, integer) — maximum number of results to return (default 100)

Response (200):

{
  "user_id": 123,
  "count": 5,
  "appointments": [ ...serialized appointments... ]
}

### GET /api/appointments/paginated

Paginated listing.

- URL: `/api/appointments/paginated`
- Method: GET
- Query params:
  - `page` (1-based, default 1)
  - `per_page` (default 50; max 1000)

Response (200):

{
  "user_id": 123,
  "page": 1,
  "per_page": 50,
  "total": 1234,
  "count": 50,
  "appointments": [ ... ]
}

### GET /api/appointments/today

Return appointments whose `appointment_date` falls within 'today' in a supplied timezone.

- URL: `/api/appointments/today`
- Method: GET
- Query params:
  - `tz` (optional IANA tz string, e.g. `America/Chicago`). If not provided, the user's `tz` is used; fallback is `UTC`.
  - `limit` (optional integer)

Response (200): same shape as list routes.

### GET /api/appointments/{appointment_id}/app_screen_logs

Return the `app_screen_log_line` entries for a given appointment. Requires the same authorization as `GET /api/appointments/{appointment_id}`.

Path parameters:
- `appointment_id` (integer) — appointment record ID

Response (200):

{
  "appointment_id": <id>,
  "count": <n>,
  "app_screen_logs": [ {"id":..., "name":..., "completion_date": ...}, ... ]
}

---

## Common error codes and shapes

All error responses are JSON objects. Common shapes and meanings:

- 400 Bad Request
  - Example: {"error": "invalid_request", "error_description": "username and password required"}
  - When required parameters or headers are missing or malformed.

- 401 Unauthorized
  - Example: {"error": "invalid_grant", "error_description": "invalid credentials"}
  - When credentials are invalid or tokens are expired / invalid.

- 403 Forbidden
  - Example: {"error": "forbidden", "error_description": "user not authorized to view this appointment"}
  - When a user is authenticated but not authorized for the requested resource.

- 403 Access Denied (authentication endpoints)
  - Example: {"error": "access_denied", "error_description": "Pitch API access is disabled for this user. Please contact an administrator."}
  - When a valid user lacks Pitch API access; occurs on login/refresh.

- 404 Not Found
  - Example: {"error": "not_found", "error_description": "appointment not found"}

- 500 Server Error
  - Example: {"error": "server_error", "error_description": "error details"}
  - Internal failures (token signing, DB errors). Server logs contain details (safely masked tokens in logs).

Introspection-specific shape:

- The introspection endpoint returns `{ "active": false, "reason": "..." }` for invalid tokens. Reasons can include:
  - `expired` — token lifetime expired
  - `revoked` — token has been revoked
  - `invalid_signature` — access token signature doesn't match
  - `invalid_checksum` — refresh token checksum failed
  - `not_found` — refresh token not found in DB
  - `invalid_format` — token parsing failed

---

## Example flows

1) Login and fetch appointment list

- Login

```bash
curl -X POST https://<HOST>/api/auth/login \
  -H 'Content-Type: application/json' \
  -H 'X-Device-ID: device-uuid-123' \
  -d '{"username":"user@example.com","password":"Secret"}'
```

- Use access token

```bash
curl -X GET https://<HOST>/api/appointments \
  -H 'Authorization: Bearer <ACCESS_TOKEN>'
```

2) Refreshing access and handling rotation

```bash
curl -X POST https://<HOST>/api/auth/refresh \
  -H 'Content-Type: application/json' \
  -H 'X-Device-ID: device-uuid-123' \
  -d '{"refresh_token":"<OLD_REFRESH_TOKEN>"}'
```

3) Revoke a refresh token (client-driven)

```bash
curl -X POST https://<HOST>/api/auth/revoke_refresh \
  -H 'Content-Type: application/json' \
  -d '{"refresh_token":"<REFRESH_TOKEN>"}'
```

---

## Operational notes and recommendations

- Always use TLS (HTTPS) for production traffic.
- Store refresh tokens securely on the client (encrypted storage). Treat them like passwords.
- Rotate server signing secret when needed; ensure `pitch_api.jwt_secret` (ir.config_parameter) is managed in your deployment.
- Monitor logs for repeated invalid refresh attempts (possible token theft) and consider rate-limiting or automatic revocation.
- If you add a 3rd-party integration that uses these APIs, register a unique `X-Device-ID` per integration instance.

---

If you want, I can:

- Add an OpenAPI (Swagger) specification file (JSON/YAML) generated from this documentation so you can host interactive docs.
- Add concrete curl or Python examples per endpoint placed into a test script under `pitch_api/tests` for local verification.

Tell me which of those you prefer next and I will implement it.

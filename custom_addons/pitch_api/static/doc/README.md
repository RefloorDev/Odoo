Pitch API — Quick connection guide and examples

This directory contains the OpenAPI spec and a minimal Swagger UI for the `pitch_api` addon.
Use the examples below to connect, authenticate, and call endpoints.

Base URLs
- Odoo local (example): http://localhost:8069
- Swagger UI served from the addon static path (recommended):
  http://<odoo-host>:<port>/pitch_api/static/doc/swagger-ui.html

Important headers
- X-Device-ID: A required device identifier for login and refresh operations.
- X-Device-Name: Optional human-readable device name.
- Authorization: Bearer <access_token> for endpoints that require authentication.

1) Login — exchange username/password for access + refresh tokens
- Endpoint: POST /api/auth/login
- Required headers:
  - X-Device-ID: device-<uuid>
  - Content-Type: application/json

Example request JSON:
{
  "username": "agent.smith@example.com",
  "password": "CorrectHorseBatteryStaple",
  "device_name": "iPhone 15 Pro"
}

Curl example:

```bash
curl -v -X POST "http://localhost:8069/api/auth/login" \
  -H "Content-Type: application/json" \
  -H "X-Device-ID: device-9a8b7c6d" \
  -d '{"username":"agent.smith@example.com","password":"CorrectHorseBatteryStaple","device_name":"iPhone 15 Pro"}'
```

Example response (HTTP 200):
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 3600,
  "refresh_token": "rfr_3f5b7a1c-plaintext-token-example"
}

Notes:
- Save the refresh token securely. It is only returned in plaintext on creation.
- Use the access token in the Authorization header for further calls: `Authorization: Bearer <access_token>`

2) Refresh — rotate refresh token and obtain a new access token
- Endpoint: POST /api/auth/refresh
- Required headers:
  - X-Device-ID: same device id used at login
  - Content-Type: application/json

Request JSON:
{
  "refresh_token": "rfr_3f5b7a1c-plaintext-token-example"
}

Curl example:
```bash
curl -v -X POST "http://localhost:8069/api/auth/refresh" \
  -H "Content-Type: application/json" \
  -H "X-Device-ID: device-9a8b7c6d" \
  -d '{"refresh_token":"rfr_3f5b7a1c-plaintext-token-example"}'
```

Response (HTTP 200): new access_token and rotated refresh_token.

3) Introspect — check token validity and metadata
- Endpoint: POST /api/auth/introspect
- Body can include `access_token` or `refresh_token`.

Request example:
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}

Curl example:
```bash
curl -v -X POST "http://localhost:8069/api/auth/introspect" \
  -H "Content-Type: application/json" \
  -d '{"access_token":"<paste_access_token_here>"}'
```

Response example:
{
  "active": true,
  "token_type": "access",
  "token_use": "access_token",
  "reason": "valid",
  "device_id": "device-9a8b7c6d",
  "expires_at": "2025-11-08T12:34:56Z",
  "created_at": "2025-11-01T09:00:00Z"
}

4) Revoke refresh — client-initiated revocation of a refresh token
- Endpoint: POST /api/auth/revoke_refresh
- Body:
{
  "refresh_token": "rfr_7c9d2e4b-newly-rotated-refresh"
}

Curl example:
```bash
curl -v -X POST "http://localhost:8069/api/auth/revoke_refresh" \
  -H "Content-Type: application/json" \
  -d '{"refresh_token":"rfr_7c9d2e4b-newly-rotated-refresh"}'
```

5) Devices — list active device sessions for the authenticated user
- Endpoint: GET /api/auth/devices
- Provide an access token via Authorization header OR pass `token` and `token_type_hint` as query params.

Curl example (Authorization header):
```bash
curl -v "http://localhost:8069/api/auth/devices" \
  -H "Authorization: Bearer <access_token>"
```

6) Me — fetch basic profile for token owner
- Endpoint: GET /api/auth/me
- Provide Authorization: Bearer <access_token> or token query param.

7) Appointments — example: GET single appointment
- Endpoint: GET /api/appointments/{appointment_id}
- Required: Authorization header with access token.

Curl example:
```bash
curl -v "http://localhost:8069/api/appointments/555" \
  -H "Authorization: Bearer <access_token>"
```

Response example (appointment object is returned):
{
  "id": 555,
  "improveit_appointment_id": "IMP-2025-0001",
  "name": "Kitchen Measurement",
  "state": "confirmed",
  "partner_id": 300,
  "customer_name": "John Doe",
  "appointment_date": "2025-11-10T09:00:00+01:00",
  "app_screen_logs": [],
  "user_id": 42,
  "user_data": { "id": 42, "name": "Agent Smith", "login": "agent.smith@example.com" }
}

Using Swagger UI
- Serve the `swagger-ui.html` and `openapi.yaml` from the addon static path so the browser and Odoo are same-origin to avoid CORS:
  http://<odoo-host>:<port>/pitch_api/static/doc/swagger-ui.html
- In the UI, click Authorize and paste the `access_token` value as `Bearer <token>` (without quotes).
- For endpoints that need `X-Device-ID` (login/refresh), add the header using the "Headers" section in the Try-it-out UI.

Troubleshooting
- If Swagger UI reports CORS or OPTIONS errors, ensure the UI is loaded from the same origin (serve from Odoo static) or configure a reverse proxy to handle CORS.
- If you see TLS ClientHello errors when calling the API, make sure you are using http:// for the Odoo dev server or configure HTTPS properly with a reverse proxy.

If you want, I can:
- Add curl examples directly into the OpenAPI `example` fields for each operation (so Swagger UI populates "Example Value" for request bodies).
- Add a tiny `docs_controller` that redirects to `/pitch_api/static/doc/swagger-ui.html` at `/pitch_api/docs` for convenience.

*** End of quick guide ***

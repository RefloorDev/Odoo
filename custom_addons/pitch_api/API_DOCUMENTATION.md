# Pitch API Documentation v2.0

REST API for the Pitch mobile/web application.

---

## Table of Contents

- [Overview](#overview)
- [Authentication](#authentication)
  - [POST /api/auth/login](#post-apiauthlogin)
  - [POST /api/auth/refresh](#post-apiauthrefresh)
  - [POST /api/auth/logout](#post-apiauthlogout)
  - [POST /api/auth/introspect](#post-apiauthintrospect)
  - [POST /api/auth/revoke_refresh](#post-apiauthrevoke_refresh)
  - [GET /api/auth/me](#get-apiauthme)
  - [GET /api/auth/devices](#get-apiauthdevices)
- [Appointments (User)](#appointments-user)
  - [GET /api/appointments](#get-apiappointments)
  - [GET /api/appointments/{id}](#get-apiappointmentsid)
  - [GET /api/appointments/today](#get-apiappointmentstoday)
  - [GET /api/appointments/{id}/app_screen_logs](#get-apiappointmentsidapp_screen_logs)
  - [GET /api/appointments/{id}/app_live_screen_logs](#get-apiappointmentsidapp_live_screen_logs)
- [Appointments (Admin)](#appointments-admin)
  - [GET /api/admin/appointments](#get-apiadminappointments)
  - [GET /api/admin/appointments/today](#get-apiadminappointmentstoday)
  - [GET /api/admin/appointments/{id}](#get-apiadminappointmentsid)
  - [GET /api/admin/appointments/{id}/app_screen_logs](#get-apiadminappointmentsidapp_screen_logs)
  - [GET /api/admin/appointments/{id}/app_live_screen_logs](#get-apiadminappointmentsidapp_live_screen_logs)
  - [GET /api/admin/market-segments](#get-apiadminmarket-segments)
- [Users (Admin)](#users-admin)
  - [GET /api/users](#get-apiusers)
  - [GET /api/users/{id}](#get-apiusersid)
  - [GET /api/users/lookup](#get-apiuserslookup)
  - [GET /api/users/exists](#get-apiusersexists)
  - [GET /api/users/{id}/groups](#get-apiusersidgroups)
  - [GET /api/users/groups](#get-apiusersgroups)
- [Error Responses](#error-responses)

---

## Overview

- **Base URL**: `https://<HOST>`
- **Content-Type**: All requests and responses use `application/json`
- **Authentication**: Bearer token in `Authorization` header

### Common Headers

| Header | Required | Description |
|--------|----------|-------------|
| `Authorization` | Yes (protected endpoints) | `Bearer <access_token>` |
| `Content-Type` | Yes (POST requests) | `application/json` |
| `X-Device-ID` | Yes (auth endpoints) | Unique device identifier |
| `X-Device-Name` | No | Human-readable device name |

---

## Authentication

### POST /api/auth/login

Exchange username/password for access and refresh tokens.

**Headers:**
| Header | Required | Description |
|--------|----------|-------------|
| `Content-Type` | Yes | `application/json` |
| `X-Device-ID` | Yes | Unique device identifier |
| `X-Device-Name` | No | Human-readable device name |

**Request Body:**
```json
{
  "username": "user@example.com",
  "password": "secret",
  "device_name": "iPhone 15 Pro"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `username` | string | Yes | User login (email). Also accepts `login` as alias |
| `password` | string | Yes | User password |
| `device_name` | string | No | Overrides X-Device-Name header |

**Success Response (200):**
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "token_type": "bearer",
  "expires_in": 3600,
  "refresh_token": "abc123def456...",
  "user_id": 123,
  "improveit_user_id": "I360-456"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `access_token` | string | JWT access token for API calls |
| `token_type` | string | Always `bearer` |
| `expires_in` | integer | Token lifetime in seconds (default: 3600) |
| `refresh_token` | string | Refresh token for obtaining new access tokens |
| `user_id` | integer | Odoo user ID |
| `improveit_user_id` | string/null | ImproveitCRM user ID (nullable) |

**Error Responses:**
| Status | Error | Description |
|--------|-------|-------------|
| 400 | `invalid_request` | Missing X-Device-ID or required fields |
| 401 | `invalid_grant` | Invalid credentials |

---

### POST /api/auth/refresh

Exchange refresh token for new access and refresh tokens (token rotation).

**Headers:**
| Header | Required | Description |
|--------|----------|-------------|
| `Content-Type` | Yes | `application/json` |
| `X-Device-ID` | Yes | Must match original device |

**Request Body:**
```json
{
  "refresh_token": "abc123def456..."
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `refresh_token` | string | Yes | Current refresh token |

**Success Response (200):**
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "token_type": "bearer",
  "expires_in": 3600,
  "refresh_token": "xyz789abc123..."
}
```

| Field | Type | Description |
|-------|------|-------------|
| `access_token` | string | New JWT access token |
| `token_type` | string | Always `bearer` |
| `expires_in` | integer | Token lifetime in seconds |
| `refresh_token` | string | New refresh token (old one is revoked) |

**Error Responses:**
| Status | Error | Description |
|--------|-------|-------------|
| 400 | `invalid_request` | Missing X-Device-ID or refresh_token |
| 401 | `invalid_grant` | Invalid or revoked refresh token |
| 401 | `refresh_token_expired` | **Refresh token expired - user must login again** |

---

### POST /api/auth/logout

Logout and revoke tokens. Supports single-device or all-devices logout.

**Headers:**
| Header | Required | Description |
|--------|----------|-------------|
| `Authorization` | Yes | `Bearer <access_token>` |
| `X-Device-ID` | Yes | Device identifier |

**Request Body (optional):**
```json
{
  "logout_all": true
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `logout_all` | boolean | No | If true, logout from all devices |

**Success Response - Single Device (200):**
```json
{
  "revoked": true,
  "device_id": "device-uuid-123"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `revoked` | boolean | Always `true` on success |
| `device_id` | string | Device that was logged out |

**Success Response - All Devices (200):**
```json
{
  "revoked": true,
  "all_devices": true,
  "device_count": 3
}
```

| Field | Type | Description |
|-------|------|-------------|
| `revoked` | boolean | Always `true` on success |
| `all_devices` | boolean | Indicates all devices were logged out |
| `device_count` | integer | Number of devices/tokens revoked |

**Error Responses:**
| Status | Error | Description |
|--------|-------|-------------|
| 400 | `invalid_request` | Missing authorization or X-Device-ID |

---

### POST /api/auth/introspect

Validate a token and return its status.

**Headers:**
| Header | Required | Description |
|--------|----------|-------------|
| `Content-Type` | Yes | `application/json` |

**Request Body:**
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `access_token` | string | No* | Access token to validate |
| `refresh_token` | string | No* | Refresh token to validate |

*Provide one of `access_token` or `refresh_token`. Alternatively, use `Authorization: Bearer <token>` header.

**Success Response - Active Access Token (200):**
```json
{
  "active": true,
  "token_type": "access_token",
  "token_use": "access"
}
```

**Success Response - Active Refresh Token (200):**
```json
{
  "active": true,
  "token_type": "refresh_token",
  "token_use": "refresh",
  "device_id": "device-uuid-123",
  "user_id": 123,
  "expires_at": "2025-01-31 10:00:00",
  "created_at": "2025-01-01 10:00:00"
}
```

**Success Response - Inactive Token (200):**
```json
{
  "active": false,
  "reason": "expired"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `active` | boolean | Whether token is valid and usable |
| `token_type` | string | `access_token` or `refresh_token` |
| `token_use` | string | `access` or `refresh` |
| `reason` | string | Reason for inactive status (when `active` is false) |
| `device_id` | string | Device bound to refresh token |
| `user_id` | integer | User ID (refresh tokens only) |
| `expires_at` | string | Expiration datetime (refresh tokens only) |
| `created_at` | string | Creation datetime (refresh tokens only) |

**Inactive Token Reasons:**
| Reason | Description |
|--------|-------------|
| `expired` | Token has expired |
| `revoked` | Token was revoked (logout) |
| `invalid_signature` | Token signature invalid |
| `not_found` | Refresh token not found in database |
| `invalid_format` | Token format is invalid |

**Error Responses:**
| Status | Error | Description |
|--------|-------|-------------|
| 400 | `missing_token` | No token provided |

---

### POST /api/auth/revoke_refresh

Revoke a specific refresh token.

**Headers:**
| Header | Required | Description |
|--------|----------|-------------|
| `Content-Type` | Yes | `application/json` |
| `X-Device-ID` | No | Device identifier (optional) |

**Request Body:**
```json
{
  "refresh_token": "abc123def456..."
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `refresh_token` | string | Yes | Token to revoke |

**Success Response (200):**
```json
{
  "revoked": true,
  "device_id": "device-uuid-123",
  "user_id": 123
}
```

| Field | Type | Description |
|-------|------|-------------|
| `revoked` | boolean | Always `true` on success |
| `device_id` | string | Device the token was bound to |
| `user_id` | integer | User ID the token belonged to |

**Error Responses:**
| Status | Error | Description |
|--------|-------|-------------|
| 400 | `invalid_request` | Missing refresh_token |
| 404 | `invalid_token` | Token not found |

---

### GET /api/auth/me

Get current user profile.

**Headers:**
| Header | Required | Description |
|--------|----------|-------------|
| `Authorization` | Yes | `Bearer <access_token>` |

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `token` | string | Alternative to Authorization header |

**Success Response (200):**
```json
{
  "user": {
    "id": 123,
    "name": "John Doe",
    "login": "john@example.com",
    "email": "john@example.com",
    "tz": "America/New_York",
    "active": true
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `user.id` | integer | User ID |
| `user.name` | string | Full name |
| `user.login` | string | Login email |
| `user.email` | string | Email address |
| `user.tz` | string | IANA timezone |
| `user.active` | boolean | Whether user is active |

**Error Responses:**
| Status | Error | Description |
|--------|-------|-------------|
| 400 | `invalid_request` | Token required |
| 401 | `invalid_token` | Token invalid or revoked |
| 401 | `token_expired` | **Access token expired - call refresh endpoint** |
| 404 | `not_found` | User not found |

---

### GET /api/auth/devices

List active login devices for current user.

**Headers:**
| Header | Required | Description |
|--------|----------|-------------|
| `Authorization` | Yes | `Bearer <access_token>` |

**Success Response (200):**
```json
{
  "user_id": 123,
  "device_count": 2,
  "devices": [
    {
      "id": 456,
      "device_id": "device-uuid-123",
      "device_name": "iPhone 15 Pro",
      "created_on": "2025-01-01 10:00:00",
      "expires_on": "2025-01-31 10:00:00",
      "last_used": "2025-01-15 14:30:00",
      "ip_address": "192.168.1.1",
      "token_family": "abc123def456",
      "use_count": 5
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `user_id` | integer | User ID |
| `device_count` | integer | Number of active devices |
| `devices` | array | List of device sessions |
| `devices[].id` | integer | Database record ID |
| `devices[].device_id` | string | Unique device identifier |
| `devices[].device_name` | string | Human-readable device name |
| `devices[].created_on` | string | Session creation datetime |
| `devices[].expires_on` | string | Session expiration datetime |
| `devices[].last_used` | string | Last activity datetime |
| `devices[].ip_address` | string | Last known IP address |
| `devices[].token_family` | string | Token family identifier |
| `devices[].use_count` | integer | Number of times token was used |

**Error Responses:**
| Status | Error | Description |
|--------|-------|-------------|
| 400 | `invalid_request` | Token required |
| 401 | `invalid_token` | Token invalid or revoked |
| 401 | `token_expired` | **Access token expired - call refresh endpoint** |

---

## Appointments (User)

Endpoints for accessing appointments assigned to the authenticated user.

### GET /api/appointments

List all appointments for the authenticated user.

**Headers:**
| Header | Required | Description |
|--------|----------|-------------|
| `Authorization` | Yes | `Bearer <access_token>` |

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `status` | string | - | Filter by status: `draft`, `scheduled`, `canceled`, `done` |
| `date_from` | string | - | Filter from date: `YYYY-MM-DD` or `YYYY-MM-DD HH:MM:SS` |
| `date_to` | string | - | Filter to date: `YYYY-MM-DD` or `YYYY-MM-DD HH:MM:SS` |
| `tz` | string | User's tz | IANA timezone for date conversion |
| `page` | integer | 1 | Page number (1-based) |
| `per_page` | integer | 200 | Items per page (max: 2000) |
| `order` | string | `id_desc` | Sort order: `id_desc`, `id_asc`, `date_desc`, `date_asc` |

**Success Response (200):**
```json
{
  "count": 50,
  "page": 1,
  "per_page": 200,
  "total_pages": 1,
  "order": "id_desc",
  "filters": {
    "status": null,
    "date_from": null,
    "date_to": null
  },
  "appointments": [
    {
      "id": 123,
      "improveit_appointment_id": "APT-12345",
      "name": "APT/2025/001",
      "state": "scheduled",
      "partner_id": 456,
      "customer_name": "Jane Smith",
      "applicant_data": {
        "applicant_first_name": "Jane",
        "applicant_middle_name": null,
        "applicant_last_name": "Smith",
        "applicant_address": {
          "street": "123 Main St",
          "street2": "Apt 4B",
          "city": "New York",
          "state_id": 10,
          "state_code": "NY",
          "state_name": "New York",
          "country_id": 233,
          "country_code": "US",
          "country_name": "United States",
          "zip": "10001"
        },
        "phone": "555-1234",
        "mobile": "555-5678",
        "email": "jane@example.com"
      },
      "co_applicant_data": {
        "co_applicant": true,
        "co_applicant_first_name": "John",
        "co_applicant_middle_name": null,
        "co_applicant_last_name": "Smith",
        "co_applicant_address": {
          "co_applicant_address": "123 Main St",
          "co_applicant_city": "New York",
          "co_applicant_state_id": 10,
          "co_applicant_state_code": "NY",
          "co_applicant_state_name": "New York",
          "co_applicant_country_id": 233,
          "co_applicant_country_code": "US",
          "co_applicant_country_name": "United States",
          "co_applicant_zip": "10001",
          "co_applicant_state_code_2": "NY"
        },
        "co_applicant_phone": "555-4321",
        "co_applicant_secondary_phone": null,
        "co_applicant_email": "john@example.com"
      },
      "appointment_date": "2025-01-15 14:00:00",
      "what_happened_notes": "Customer was very interested",
      "appointment_result": "sold",
      "office_location_id": 5,
      "office_location_name": "New York Office",
      "app_data": {
        "id": 12,
        "app_version": "2.5.0",
        "app_release_date": "2025-01-01"
      },
      "credit_application_url": "https://apply.example.com/12345",
      "appointment_result_details": {
        "id": 3,
        "reason": "Price accepted",
        "tags": ["sold", "financing"]
      },
      "user_id": 789,
      "user_data": {
        "id": 789,
        "name": "Sales Rep",
        "login": "rep@example.com"
      },
      "measurement_exist": true,
      "send_physical_document": false,
      "flexible_installation": true,
      "whats_next_notes": "Schedule installation",
      "last_price_quoted_value": 5999.99,
      "market_segment": "residential",
      "both_parties_present": true,
      "sent_review_link": true,
      "make_payment_failure": false,
      "destination_selection_id": 2,
      "destination_selection_name": "Kitchen",
      "additional_comments": "Customer prefers morning installation",
      "geolocation_data": {
        "date_localization": "2025-01-15 14:05:00",
        "partner_latitude": 40.7128,
        "partner_longitude": -74.0060
      },
      "arrival_date": "2025-01-15 13:55:00",
      "departure_date": "2025-01-15 16:30:00",
      "manual_arrival_date": null
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `count` | integer | Total appointments in current page |
| `page` | integer | Current page number |
| `per_page` | integer | Items per page |
| `total_pages` | integer | Total number of pages |
| `order` | string | Applied sort order |
| `filters` | object | Applied filters |
| `appointments` | array | List of appointments |

**Appointment Object Fields:**
| Field | Type | Description |
|-------|------|-------------|
| `id` | integer | Appointment ID |
| `improveit_appointment_id` | string | External appointment ID |
| `name` | string | Appointment reference number |
| `state` | string | Status: `draft`, `scheduled`, `canceled`, `done` |
| `partner_id` | integer | Customer partner ID |
| `customer_name` | string | Customer full name |
| `applicant_data` | object | Primary applicant information |
| `co_applicant_data` | object | Co-applicant information |
| `appointment_date` | string | Scheduled datetime |
| `what_happened_notes` | string | Notes about the appointment |
| `appointment_result` | string | Result of appointment |
| `office_location_id` | integer | Office location ID |
| `office_location_name` | string | Office location name |
| `app_data` | object | App version information |
| `credit_application_url` | string | Credit application URL |
| `appointment_result_details` | object | Detailed result information |
| `user_id` | integer | Assigned user ID |
| `user_data` | object | Assigned user information |
| `measurement_exist` | boolean | Whether measurements exist |
| `send_physical_document` | boolean | Send physical document flag |
| `flexible_installation` | boolean | Flexible installation flag |
| `whats_next_notes` | string | Next steps notes |
| `last_price_quoted_value` | number | Last quoted price |
| `market_segment` | string | Market segment |
| `both_parties_present` | boolean | Both parties were present |
| `sent_review_link` | boolean | Review link was sent |
| `make_payment_failure` | boolean | Payment failure occurred |
| `destination_selection_id` | integer | Destination selection ID |
| `destination_selection_name` | string | Destination selection name |
| `additional_comments` | string | Additional comments |
| `geolocation_data` | object | GPS location data |
| `arrival_date` | string | Arrival datetime |
| `departure_date` | string | Departure datetime |
| `manual_arrival_date` | string | Manual arrival datetime |

**Error Responses:**
| Status | Error | Description |
|--------|-------|-------------|
| 400 | `invalid_request` | Invalid parameters or per_page > 2000 |
| 401 | `invalid_token` | Token invalid |
| 401 | `token_expired` | **Access token expired - call refresh endpoint** |

---

### GET /api/appointments/{id}

Get a single appointment by ID.

**Headers:**
| Header | Required | Description |
|--------|----------|-------------|
| `Authorization` | Yes | `Bearer <access_token>` |

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `id` | integer | Appointment ID |

**Success Response (200):**
Returns a single appointment object with the same structure as shown in [GET /api/appointments](#get-apiappointments).

**Error Responses:**
| Status | Error | Description |
|--------|-------|-------------|
| 401 | `invalid_token` | Token invalid |
| 401 | `token_expired` | **Access token expired - call refresh endpoint** |
| 403 | `forbidden` | User not authorized for this appointment |
| 404 | `not_found` | Appointment not found |

---

### GET /api/appointments/today

Get today's appointments for the authenticated user.

**Headers:**
| Header | Required | Description |
|--------|----------|-------------|
| `Authorization` | Yes | `Bearer <access_token>` |

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `tz` | string | User's tz | IANA timezone for determining "today" |
| `status` | string | - | Filter by status |
| `page` | integer | 1 | Page number |
| `per_page` | integer | 200 | Items per page (max: 2000) |
| `order` | string | `id_desc` | Sort order |

**Success Response (200):**
```json
{
  "date": "2025-01-15",
  "timezone": "America/New_York",
  "count": 3,
  "page": 1,
  "per_page": 200,
  "total_pages": 1,
  "order": "id_desc",
  "appointments": [...]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `date` | string | Today's date in YYYY-MM-DD format |
| `timezone` | string | Timezone used |
| `count` | integer | Number of appointments |
| `page` | integer | Current page |
| `per_page` | integer | Items per page |
| `total_pages` | integer | Total pages |
| `order` | string | Sort order |
| `appointments` | array | List of appointments |

---

### GET /api/appointments/{id}/app_screen_logs

Get screen logs for an appointment.

**Headers:**
| Header | Required | Description |
|--------|----------|-------------|
| `Authorization` | Yes | `Bearer <access_token>` |

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `id` | integer | Appointment ID |

**Success Response (200):**
```json
{
  "appointment_id": 123,
  "count": 5,
  "app_screen_logs": [
    {
      "id": 1,
      "name": "Welcome Screen",
      "completion_date": "2025-01-15 14:05:00",
      "user_id": 789
    },
    {
      "id": 2,
      "name": "Product Selection",
      "completion_date": "2025-01-15 14:15:00",
      "user_id": 789
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `appointment_id` | integer | Appointment ID |
| `count` | integer | Number of log entries |
| `app_screen_logs` | array | List of screen logs |
| `app_screen_logs[].id` | integer | Log entry ID |
| `app_screen_logs[].name` | string | Screen name |
| `app_screen_logs[].completion_date` | string | Completion datetime |
| `app_screen_logs[].user_id` | integer | User who completed |

**Error Responses:**
| Status | Error | Description |
|--------|-------|-------------|
| 401 | `invalid_token` | Token invalid |
| 401 | `token_expired` | **Access token expired - call refresh endpoint** |
| 403 | `forbidden` | User not authorized |
| 404 | `not_found` | Appointment not found |

---

### GET /api/appointments/{id}/app_live_screen_logs

Get live screen logs for an appointment. Returns full details including `id` and `user_id`.

**Headers:**
| Header | Required | Description |
|--------|----------|-------------|
| `Authorization` | Yes | `Bearer <access_token>` |

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `id` | integer | Appointment ID |

**Success Response (200):**
```json
{
  "appointment_id": 123,
  "count": 3,
  "app_live_screen_logs": [
    {
      "id": 1,
      "name": "Welcome Screen",
      "screen_entry_date": "2025-01-15 14:05:00",
      "user_id": 789
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `appointment_id` | integer | Appointment ID |
| `count` | integer | Number of log entries |
| `app_live_screen_logs` | array | List of live screen logs |
| `app_live_screen_logs[].id` | integer | Log entry ID |
| `app_live_screen_logs[].name` | string | Screen name |
| `app_live_screen_logs[].screen_entry_date` | string | Screen entry datetime |
| `app_live_screen_logs[].user_id` | integer | User ID |

**Error Responses:**
| Status | Error | Description |
|--------|-------|-------------|
| 401 | `invalid_token` | Token invalid |
| 401 | `token_expired` | **Access token expired - call refresh endpoint** |
| 403 | `forbidden` | User not authorized |
| 404 | `not_found` | Appointment not found |

---

## Appointments (Admin)

Admin-only endpoints for accessing all appointments. Requires `is_pitch_admin=True`.

### GET /api/admin/appointments

List all appointments (admin access).

**Headers:**
| Header | Required | Description |
|--------|----------|-------------|
| `Authorization` | Yes | `Bearer <access_token>` (admin) |

**Query Parameters:**
Same as [GET /api/appointments](#get-apiappointments) plus:

| Parameter | Type | Description |
|-----------|------|-------------|
| `user_id` | integer | Filter by assigned user ID |

**Success Response (200):**
Same structure as [GET /api/appointments](#get-apiappointments)

**Error Responses:**
| Status | Error | Description |
|--------|-------|-------------|
| 401 | `invalid_token` | Token invalid |
| 401 | `token_expired` | **Access token expired - call refresh endpoint** |
| 403 | `forbidden` | Caller is not a Pitch Admin |

---

### GET /api/admin/appointments/today

Get today's appointments (admin access).

**Headers:**
| Header | Required | Description |
|--------|----------|-------------|
| `Authorization` | Yes | `Bearer <access_token>` (admin) |

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `tz` | string | IANA timezone |
| `user_id` | integer | Filter by assigned user ID |
| `status` | string | Filter by status |
| `page` | integer | Page number |
| `per_page` | integer | Items per page |
| `order` | string | Sort order |

**Success Response (200):**
Same structure as [GET /api/appointments/today](#get-apiappointmentstoday)

---

### GET /api/admin/appointments/{id}

Get a single appointment by ID (admin access).

**Headers:**
| Header | Required | Description |
|--------|----------|-------------|
| `Authorization` | Yes | `Bearer <access_token>` (admin) |

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `id` | integer | Appointment ID |

**Success Response (200):**
Same structure as single appointment object.

---

### GET /api/admin/appointments/{id}/app_screen_logs

Get screen logs for an appointment (admin access).

Same as [GET /api/appointments/{id}/app_screen_logs](#get-apiappointmentsidapp_screen_logs) but accessible by admin for any appointment.

---

### GET /api/admin/appointments/{id}/app_live_screen_logs

Get live screen logs for an appointment (admin access).

Same as [GET /api/appointments/{id}/app_live_screen_logs](#get-apiappointmentsidapp_live_screen_logs) but accessible by admin for any appointment.

---

### GET /api/admin/market-segments

Get all market segments.

**Headers:**
| Header | Required | Description |
|--------|----------|-------------|
| `Authorization` | Yes | `Bearer <access_token>` (admin) |

**Success Response (200):**
```json
{
  "count": 3,
  "market_segments": [
    {
      "id": 1,
      "name": "Residential",
      "active": true
    },
    {
      "id": 2,
      "name": "Commercial",
      "active": true
    },
    {
      "id": 3,
      "name": "Industrial",
      "active": false
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `count` | integer | Number of market segments |
| `market_segments` | array | List of market segments |
| `market_segments[].id` | integer | Market segment ID |
| `market_segments[].name` | string | Market segment name |
| `market_segments[].active` | boolean | Whether active |

---

## Users (Admin)

Admin-only endpoints for user management. Requires `is_pitch_admin=True`.

### GET /api/users

List all users.

**Headers:**
| Header | Required | Description |
|--------|----------|-------------|
| `Authorization` | Yes | `Bearer <access_token>` (admin) |

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `active` | string | `all` | Filter: `true`, `false`, or `all` |

**Success Response (200):**
```json
{
  "admin_user_id": 691,
  "count": 50,
  "active_filter": "all",
  "users": [
    {
      "id": 123,
      "name": "John Doe",
      "login": "john@example.com",
      "active": true,
      "tz": "America/New_York",
      "company_id": 1,
      "company_name": "Refloor LLC",
      "login_date": "2025-01-15 10:00:00",
      "is_pitch_admin": false,
      "improveit_user_id": "I360-456"
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `admin_user_id` | integer | ID of admin making request |
| `count` | integer | Number of users returned |
| `active_filter` | string | Applied active filter |
| `users` | array | List of users |
| `users[].id` | integer | User ID |
| `users[].name` | string | Full name |
| `users[].login` | string | Login email |
| `users[].active` | boolean | Whether user is active |
| `users[].tz` | string | User timezone |
| `users[].company_id` | integer | Company ID |
| `users[].company_name` | string | Company name |
| `users[].login_date` | string | Last login datetime |
| `users[].is_pitch_admin` | boolean | Whether user is Pitch admin |
| `users[].improveit_user_id` | string | ImproveitCRM user ID |

**Error Responses:**
| Status | Error | Description |
|--------|-------|-------------|
| 401 | `invalid_token` | Token invalid |
| 401 | `token_expired` | **Access token expired - call refresh endpoint** |
| 403 | `forbidden` | Caller is not a Pitch Admin |

---

### GET /api/users/{id}

Get a single user by ID.

**Headers:**
| Header | Required | Description |
|--------|----------|-------------|
| `Authorization` | Yes | `Bearer <access_token>` (admin) |

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `id` | integer | User ID |

**Success Response (200):**
```json
{
  "id": 123,
  "name": "John Doe",
  "login": "john@example.com",
  "active": true,
  "tz": "America/New_York",
  "company_id": 1,
  "company_name": "Refloor LLC",
  "login_date": "2025-01-15 10:00:00",
  "is_pitch_admin": false,
  "improveit_user_id": "I360-456"
}
```

**Error Responses:**
| Status | Error | Description |
|--------|-------|-------------|
| 401 | `invalid_token` | Token invalid |
| 401 | `token_expired` | **Access token expired - call refresh endpoint** |
| 403 | `forbidden` | Caller is not a Pitch Admin |
| 404 | `not_found` | User not found |

---

### GET /api/users/lookup

Lookup a user by ID or login.

**Headers:**
| Header | Required | Description |
|--------|----------|-------------|
| `Authorization` | Yes | `Bearer <access_token>` (admin) |

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `user_id` | integer | User ID to lookup |
| `login` | string | User login to lookup |

*Provide one of `user_id` or `login`.*

**Success Response (200):**
Same as [GET /api/users/{id}](#get-apiusersid)

**Error Responses:**
| Status | Error | Description |
|--------|-------|-------------|
| 401 | `invalid_token` | Token invalid |
| 401 | `token_expired` | **Access token expired - call refresh endpoint** |
| 404 | `not_found` | User not found |

---

### GET /api/users/exists

Check if a user exists.

**Headers:**
| Header | Required | Description |
|--------|----------|-------------|
| `Authorization` | Yes | `Bearer <access_token>` (admin) |

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `user_id` | integer | User ID to check |
| `login` | string | User login to check |

*Provide one of `user_id` or `login`.*

**Success Response (200):**
```json
{
  "exists": true
}
```

| Field | Type | Description |
|-------|------|-------------|
| `exists` | boolean | Whether user exists |

**Error Responses:**
| Status | Error | Description |
|--------|-------|-------------|
| 400 | `invalid_request` | Neither user_id nor login provided |
| 401 | `invalid_token` | Token invalid |
| 401 | `token_expired` | **Access token expired - call refresh endpoint** |

---

### GET /api/users/{id}/groups

Get groups for a single user.

**Headers:**
| Header | Required | Description |
|--------|----------|-------------|
| `Authorization` | Yes | `Bearer <access_token>` (admin) |

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `id` | integer | User ID |

**Success Response (200):**
```json
{
  "user_id": 123,
  "user_login": "john@example.com",
  "user_name": "John Doe",
  "groups_count": 5,
  "groups": [
    {
      "id": 1,
      "name": "Sales / User",
      "xml_id": "sales_team.group_sale_salesman",
      "category_id": 10,
      "category_name": "Sales"
    },
    {
      "id": 2,
      "name": "Internal User",
      "xml_id": "base.group_user",
      "category_id": 1,
      "category_name": "User types"
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `user_id` | integer | User ID |
| `user_login` | string | User login |
| `user_name` | string | User name |
| `groups_count` | integer | Number of groups |
| `groups` | array | List of groups |
| `groups[].id` | integer | Group ID |
| `groups[].name` | string | Group name |
| `groups[].xml_id` | string | Group XML ID |
| `groups[].category_id` | integer | Category ID |
| `groups[].category_name` | string | Category name |

**Error Responses:**
| Status | Error | Description |
|--------|-------|-------------|
| 401 | `invalid_token` | Token invalid |
| 401 | `token_expired` | **Access token expired - call refresh endpoint** |
| 404 | `not_found` | User not found |

---

### GET /api/users/groups

Get groups for multiple users.

**Headers:**
| Header | Required | Description |
|--------|----------|-------------|
| `Authorization` | Yes | `Bearer <access_token>` (admin) |

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `user_ids` | string | Comma-separated user IDs (e.g., `1,2,3`) |

**Success Response (200):**
```json
{
  "count": 2,
  "users": [
    {
      "user_id": 123,
      "user_login": "john@example.com",
      "user_name": "John Doe",
      "groups_count": 5,
      "groups": [
        {
          "id": 1,
          "name": "Sales / User",
          "xml_id": "sales_team.group_sale_salesman",
          "category_id": 10,
          "category_name": "Sales"
        }
      ]
    },
    {
      "user_id": 456,
      "user_login": "jane@example.com",
      "user_name": "Jane Smith",
      "groups_count": 3,
      "groups": [...]
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `count` | integer | Number of users returned |
| `users` | array | List of users with their groups |

**Error Responses:**
| Status | Error | Description |
|--------|-------|-------------|
| 400 | `invalid_request` | user_ids parameter required or invalid format |
| 401 | `invalid_token` | Token invalid |
| 401 | `token_expired` | **Access token expired - call refresh endpoint** |

---

## Error Responses

All error responses follow this format:

```json
{
  "error": "error_code",
  "error_description": "Human-readable description of the error"
}
```

### Common Error Codes

| Status | Error Code | Description |
|--------|------------|-------------|
| 400 | `invalid_request` | Missing or invalid parameters |
| 401 | `invalid_grant` | Invalid credentials (login only) |
| 401 | `invalid_token` | Token invalid or revoked |
| 401 | `token_expired` | **Access token has expired - call refresh endpoint** |
| 401 | `refresh_token_expired` | **Refresh token has expired - user must login again** |
| 403 | `forbidden` | User not authorized for this resource |
| 404 | `not_found` | Resource not found |
| 500 | `server_error` | Internal server error |

### Token Expired Response (Trigger Refresh Flow)

When an access token expires, the API returns a **standardized response** that clients should use to trigger the token refresh flow.

**Response (401):**
```json
{
  "error": "token_expired",
  "error_description": "The access token has expired. Use refresh token to obtain a new access token.",
  "error_code": "TOKEN_EXPIRED"
}
```

**Client Implementation:**

When you receive this response:
1. Check if `error === "token_expired"` (or `error_code === "TOKEN_EXPIRED"`)
2. Call `POST /api/auth/refresh` with your stored refresh token
3. Store the new access and refresh tokens
4. Retry the original request with the new access token

**Example Client Code (JavaScript):**
```javascript
async function apiRequest(url, options) {
  const response = await fetch(url, options);
  const data = await response.json();
  
  // Check for expired token
  if (response.status === 401 && data.error === 'token_expired') {
    // Trigger refresh flow
    const newTokens = await refreshTokens();
    if (newTokens) {
      // Retry with new access token
      options.headers['Authorization'] = `Bearer ${newTokens.access_token}`;
      return fetch(url, options);
    }
  }
  
  return response;
}
```

### Refresh Token Expired Response (Force Re-Login)

When a refresh token expires, the API returns a **standardized response** that clients should use to force the user to login again.

**Response (401):**
```json
{
  "error": "refresh_token_expired",
  "error_description": "The refresh token has expired. Please login again.",
  "error_code": "REFRESH_TOKEN_EXPIRED"
}
```

**Client Implementation:**

When you receive this response from `POST /api/auth/refresh`:
1. Check if `error === "refresh_token_expired"` (or `error_code === "REFRESH_TOKEN_EXPIRED"`)
2. Clear all stored tokens
3. Redirect user to login screen

### Example Error Response (Invalid Token)

```json
{
  "error": "invalid_token",
  "error_description": "invalid_signature"
}
```

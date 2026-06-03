# Pitch API Documentation v2.5

REST API for the Pitch mobile/web application.

**Last Updated:** 2026-05-29

**Changes in v2.5:**
- Added derived `progress_status` (`not_started`, `in_progress`, `completed`) and `progress_status_updated_at` on all appointment list/get responses
- Added optional `progress_status` query filter on `GET /api/appointments`, `GET /api/appointments/today`, `GET /api/admin/appointments`, and `GET /api/admin/appointments/today`
- `progress_status` is derived from Odoo `state` and sales-app live screen logs (`otl.app.live.screen.log`): `done` → `completed`; not `done` with ≥1 log → `in_progress`; otherwise `not_started`

**Changes in v2.4:**
- Added `POST /api/admin/appointments/app_live_screen_logs` endpoint for bulk live screen logs retrieval with time spent calculation
- Added `GET /api/admin/appointments/analytics` endpoint for time analytics and metrics

**Changes in v2.3:**
- Removed `tz` parameter from all endpoints - all dates are now in UTC
- User endpoints (`/api/appointments`, `/api/appointments/today`) now use UTC only
- Added `admin_user_id` to `/api/admin/market-segments` response for consistency
- Added complete Admin Appointment Object documentation with all fields
- Added `GET /api/admin/salespersons` endpoint to list salespersons by market segment

**Changes in v2.2:**
- Replaced `q` and `search_in` parameters with direct search parameters (`customer`, `co_applicant`, `name`, `id`)
- Removed `filter_logic` parameter - all filters now use AND logic only
- Removed `tz` parameter from admin endpoints - all dates are in UTC
- Date filters (`date_from`, `date_to`) now use UTC directly
- `/api/admin/appointments/today` now determines "today" in UTC

**Changes in v2.1:**
- Added search functionality to admin appointments endpoints
- Added priority-based name matching for customer and co-applicant searches
- Added detailed nested object documentation for appointment responses
- Fixed response field types to indicate nullable fields
- Corrected `co_applicant` field type (string, not boolean)

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
  - [POST /api/admin/appointments/app_live_screen_logs](#post-apiadminappointmentsapp_live_screen_logs)
  - [GET /api/admin/appointments/analytics](#get-apiadminappointmentsanalytics)
  - [GET /api/admin/market-segments](#get-apiadminmarket-segments)
  - [GET /api/admin/salespersons](#get-apiadminsalespersons)
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
All date/datetime values are treated as UTC.

**Headers:**
| Header | Required | Description |
|--------|----------|-------------|
| `Authorization` | Yes | `Bearer <access_token>` |

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `status` | string | - | Filter by status: `draft`, `scheduled`, `canceled`, `done` |
| `progress_status` | string | - | Filter by derived progress: `not_started`, `in_progress`, `completed` |
| `date_from` | string | - | Filter from date in UTC: `YYYY-MM-DD` or `YYYY-MM-DD HH:MM:SS` |
| `date_to` | string | - | Filter to date in UTC: `YYYY-MM-DD` or `YYYY-MM-DD HH:MM:SS` |
| `page` | integer | 1 | Page number (1-based) |
| `per_page` | integer | 200 | Items per page (max: 2000) |
| `order` | string | `id_desc` | Sort order: `id_desc`, `id_asc`, `date_desc`, `date_asc` |

**Progress status derivation:** `state == done` → `completed`; not `done` with at least one live screen log row → `in_progress`; otherwise `not_started`. Distinct from analytics `with_logs` (which requires ≥2 log entries).

**Success Response (200):**
```json
{
  "user_id": 789,
  "total": 50,
  "count": 50,
  "page": 1,
  "per_page": 200,
  "order": "id_desc",
  "filters": {
    "status": "scheduled",
    "date_from": "2025-01-01",
    "date_to": "2025-01-31"
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
        "co_applicant": "John Smith",
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
      "manual_arrival_date": null,
      "progress_status": "in_progress",
      "progress_status_updated_at": "2025-01-15 14:10:00"
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `user_id` | integer | Authenticated user ID |
| `total` | integer | Total matching appointments |
| `count` | integer | Appointments in current page |
| `page` | integer | Current page number |
| `per_page` | integer | Items per page |
| `order` | string | Applied sort order |
| `filters` | object | Applied filters (only present if filters applied) |
| `appointments` | array | List of appointments |

**Appointment Object Fields:**
| Field | Type | Description |
|-------|------|-------------|
| `id` | integer | Appointment ID |
| `improveit_appointment_id` | string/null | External appointment ID (Salesforce) |
| `name` | string/null | Appointment reference number (e.g., `CAP/2025/001`) |
| `state` | string/null | Status: `draft`, `scheduled`, `canceled`, `done` |
| `partner_id` | integer/null | Customer partner ID |
| `customer_name` | string/null | Customer full name |
| `applicant_data` | object | Primary applicant information (see below) |
| `co_applicant_data` | object | Co-applicant information (see below) |
| `appointment_date` | string/null | Scheduled datetime (UTC) |
| `what_happened_notes` | string/null | Notes about the appointment |
| `appointment_result` | string/null | Result of appointment |
| `office_location_id` | integer/null | Office location ID |
| `office_location_name` | string/null | Office location name |
| `app_data` | object | App version information (see below) |
| `credit_application_url` | string/null | Credit application URL |
| `appointment_result_details` | object | Detailed result information (see below) |
| `user_id` | integer/null | Assigned user ID |
| `user_data` | object | Assigned user information (see below) |
| `measurement_exist` | boolean | Whether measurements exist |
| `send_physical_document` | boolean | Send physical document flag |
| `flexible_installation` | boolean | Flexible installation flag |
| `whats_next_notes` | string/null | Next steps notes |
| `last_price_quoted_value` | number/null | Last quoted price |
| `market_segment` | string/null | Market segment |
| `both_parties_present` | boolean | Both parties were present |
| `sent_review_link` | boolean | Review link was sent |
| `make_payment_failure` | boolean | Payment failure occurred |
| `destination_selection_id` | integer/null | Destination selection ID |
| `destination_selection_name` | string/null | Destination selection name |
| `additional_comments` | string/null | Additional comments |
| `geolocation_data` | object | GPS location data (see below) |
| `arrival_date` | string/null | Arrival datetime (UTC) |
| `departure_date` | string/null | Departure datetime (UTC) |
| `manual_arrival_date` | string/null | Manual arrival datetime (UTC) |
| `progress_status` | string | Derived progress: `not_started`, `in_progress`, `completed` |
| `progress_status_updated_at` | string/null | Latest live screen log `screen_entry_date` (UTC), or null |

**Nested Object: `applicant_data`**
| Field | Type | Description |
|-------|------|-------------|
| `applicant_first_name` | string/null | First name |
| `applicant_middle_name` | string/null | Middle name |
| `applicant_last_name` | string/null | Last name |
| `applicant_address` | object | Address object with `street`, `street2`, `city`, `state_id`, `state_code`, `state_name`, `country_id`, `country_code`, `country_name`, `zip` |
| `phone` | string/null | Phone number |
| `mobile` | string/null | Mobile number |
| `email` | string/null | Email address |

**Nested Object: `co_applicant_data`**
| Field | Type | Description |
|-------|------|-------------|
| `co_applicant` | string/null | Co-applicant full name |
| `co_applicant_first_name` | string/null | First name |
| `co_applicant_middle_name` | string/null | Middle name |
| `co_applicant_last_name` | string/null | Last name |
| `co_applicant_address` | object | Address object with `co_applicant_address`, `co_applicant_city`, `co_applicant_state_id`, `co_applicant_state_code`, `co_applicant_state_name`, `co_applicant_country_id`, `co_applicant_country_code`, `co_applicant_country_name`, `co_applicant_zip`, `co_applicant_state_code_2` |
| `co_applicant_phone` | string/null | Phone number |
| `co_applicant_secondary_phone` | string/null | Secondary phone number |
| `co_applicant_email` | string/null | Email address |

**Nested Object: `app_data`**
| Field | Type | Description |
|-------|------|-------------|
| `id` | integer/null | App version ID |
| `app_version` | string/null | App version name |
| `app_release_date` | string/null | App release date |

**Nested Object: `appointment_result_details`**
| Field | Type | Description |
|-------|------|-------------|
| `id` | integer/null | Result reason ID |
| `reason` | string/null | Result reason text |
| `tags` | array/null | List of result tag names |

**Nested Object: `user_data`**
| Field | Type | Description |
|-------|------|-------------|
| `id` | integer/null | User ID |
| `name` | string/null | User full name |
| `login` | string/null | User login (email) |

**Nested Object: `geolocation_data`**
| Field | Type | Description |
|-------|------|-------------|
| `date_localization` | string/null | Localization datetime (UTC) |
| `partner_latitude` | number/null | Latitude |
| `partner_longitude` | number/null | Longitude |

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
Returns the appointment object directly (not wrapped in a container).

```json
{
  "id": 123,
  "improveit_appointment_id": "APT-12345",
  "name": "CAP/2025/001",
  "state": "scheduled",
  "partner_id": 456,
  "customer_name": "Jane Smith",
  "applicant_data": {...},
  "co_applicant_data": {...},
  "appointment_date": "2025-01-15 14:00:00",
  "..."
}
```

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
Today is determined in UTC.

**Headers:**
| Header | Required | Description |
|--------|----------|-------------|
| `Authorization` | Yes | `Bearer <access_token>` |

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `status` | string | - | Filter by status |
| `progress_status` | string | - | Filter by derived progress: `not_started`, `in_progress`, `completed` |
| `page` | integer | 1 | Page number |
| `per_page` | integer | 200 | Items per page (max: 2000) |
| `order` | string | `id_desc` | Sort order |

**Success Response (200):**
```json
{
  "user_id": 789,
  "date": "2025-01-15",
  "total": 3,
  "count": 3,
  "page": 1,
  "per_page": 200,
  "order": "id_desc",
  "filters": {
    "status": "scheduled"
  },
  "appointments": [...]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `user_id` | integer | Authenticated user ID |
| `date` | string | Today's date in UTC (`YYYY-MM-DD`) |
| `total` | integer | Total matching appointments |
| `count` | integer | Appointments in current page |
| `page` | integer | Current page |
| `per_page` | integer | Items per page |
| `order` | string | Sort order |
| `filters` | object | Applied filters (only if status filter applied) |
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

*Note: User endpoints do NOT include `admin_user_id` in response.*

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

*Note: User endpoints do NOT include `admin_user_id` in response.*

| Field | Type | Description |
|-------|------|-------------|
| `appointment_id` | integer | Appointment ID |
| `count` | integer | Number of log entries |
| `app_live_screen_logs` | array | List of live screen logs |
| `app_live_screen_logs[].id` | integer | Log entry ID |
| `app_live_screen_logs[].name` | string | Screen name |
| `app_live_screen_logs[].screen_entry_date` | string | Screen entry datetime (UTC) |
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

List all appointments with optional filters, search, and pagination.

**Headers:**
| Header | Required | Description |
|--------|----------|-------------|
| `Authorization` | Yes | `Bearer <access_token>` (admin) |

**Query Parameters:**

**Filter Parameters (AND logic):**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `market_segment` | string | - | Filter by market segment. Comma-separated for multiple (OR within field) |
| `user_id` | integer | - | Filter by assigned Odoo user ID |
| `improveit_user_id` | string | - | Filter by Salesforce user ID (used if `user_id` not provided) |
| `status` | string | - | Filter by status: `draft`, `scheduled`, `canceled`, `done` |
| `progress_status` | string | - | Filter by derived progress: `not_started`, `in_progress`, `completed` |
| `date_from` | string | - | Start date in UTC: `YYYY-MM-DD` or `YYYY-MM-DD HH:MM:SS` |
| `date_to` | string | - | End date in UTC: `YYYY-MM-DD` or `YYYY-MM-DD HH:MM:SS` |

**Search Parameters (AND logic with filters):**
| Parameter | Type | Description |
|-----------|------|-------------|
| `customer` | string | Search in customer name fields (partial match, priority-based) |
| `co_applicant` | string | Search in co-applicant name fields (partial match, priority-based) |
| `name` | string | Search in appointment reference (partial match) |
| `id` | integer | Search by appointment ID (exact match) |

**Pagination Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `page` | integer | `1` | Page number (1-indexed) |
| `per_page` | integer | `200` | Items per page (max: 2000) |
| `order` | string | `id_desc` | Sort: `id_desc`, `id_asc`, `date_desc`, `date_asc` |

*Note: If both `user_id` and `improveit_user_id` are provided, `user_id` takes priority.*

**Progress status:** Same derivation as user appointments. Optional `progress_status` filter is applied server-side (SQL) with existing filters.

**Priority-Based Name Matching (for `customer` and `co_applicant`):**

When searching customer or co-applicant names, results are prioritized:
1. **Priority 1**: Exact match on full name
2. **Priority 2**: Reversed format ("john doe" matches "doe, john")
3. **Priority 3**: First word = first_name AND last word = last_name
4. **Priority 4**: First word = last_name AND last word = first_name (swapped)
5. **Priority 5**: Partial match (ilike) on any field
6. **Priority 6**: Individual word matches on any field

**Examples:**
```
# Search by customer name
GET /api/admin/appointments?customer=john%20doe

# Search by co-applicant name
GET /api/admin/appointments?co_applicant=jane%20smith

# Search by appointment ID (exact match)
GET /api/admin/appointments?id=12345

# Search by appointment reference
GET /api/admin/appointments?name=CAP/2025/96361

# Combined filters and search (all AND)
GET /api/admin/appointments?customer=john&status=scheduled&market_segment=Residential

# Multiple market segments (OR within field)
GET /api/admin/appointments?market_segment=Residential,Commercial

# Date range filter (UTC)
GET /api/admin/appointments?date_from=2025-01-01&date_to=2025-01-31

# Progress status filter (server-side)
GET /api/admin/appointments?progress_status=in_progress&date_from=2026-05-01&date_to=2026-05-31
```

**Success Response (200):**
```json
{
  "admin_user_id": 123,
  "total": 500,
  "count": 200,
  "page": 1,
  "per_page": 200,
  "order": "id_desc",
  "filters": {
    "market_segment": "Residential",
    "user_id": 45,
    "status": "scheduled",
    "progress_status": "in_progress",
    "date_from": "2025-01-01",
    "date_to": "2025-01-31",
    "order": "id_desc",
    "customer": "john doe",
    "co_applicant": "jane"
  },
  "appointments": [...]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `admin_user_id` | integer | Authenticated admin user ID |
| `total` | integer | Total matching appointments |
| `count` | integer | Appointments in current page |
| `page` | integer | Current page number |
| `per_page` | integer | Items per page |
| `order` | string | Applied sort order |
| `filters` | object | Applied filters (echoed back) |
| `appointments` | array | List of appointment objects (see [Admin Appointment Object](#admin-appointment-object)) |

**Error Responses:**
| Status | Error | Description |
|--------|-------|-------------|
| 400 | `invalid_request` | Invalid `status` value. Allowed: `draft`, `scheduled`, `canceled`, `done` |
| 400 | `invalid_request` | Invalid `progress_status` value. Allowed: `not_started`, `in_progress`, `completed` |
| 400 | `invalid_request` | Conflicting `progress_status` and `status` (e.g. `completed` + `scheduled`, or `in_progress` + `done`) |
| 400 | `invalid_request` | Invalid `order` value. Allowed: `id_desc`, `id_asc`, `date_desc`, `date_asc` |
| 400 | `invalid_request` | Invalid `id` value. Must be a valid integer |
| 400 | `invalid_request` | Invalid `page` or `per_page` value |
| 401 | `invalid_token` | Token invalid |
| 401 | `token_expired` | **Access token expired - call refresh endpoint** |
| 403 | `forbidden` | Caller is not a Pitch Admin |
| 404 | `user_not_found` | No user found with provided `improveit_user_id` |

---

### GET /api/admin/appointments/today

Get today's appointments with optional filters, search, and pagination.
Today is determined in UTC.

**Headers:**
| Header | Required | Description |
|--------|----------|-------------|
| `Authorization` | Yes | `Bearer <access_token>` (admin) |

**Query Parameters:**

**Filter Parameters (AND logic):**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `market_segment` | string | - | Filter by market segment. Comma-separated for multiple (OR within field) |
| `user_id` | integer | - | Filter by assigned Odoo user ID |
| `improveit_user_id` | string | - | Filter by Salesforce user ID (used if `user_id` not provided) |
| `status` | string | - | Filter by status: `draft`, `scheduled`, `canceled`, `done` |
| `progress_status` | string | - | Filter by derived progress: `not_started`, `in_progress`, `completed` |

**Search Parameters (AND logic with filters):**
| Parameter | Type | Description |
|-----------|------|-------------|
| `customer` | string | Search in customer name fields (partial match, priority-based) |
| `co_applicant` | string | Search in co-applicant name fields (partial match, priority-based) |
| `name` | string | Search in appointment reference (partial match) |
| `id` | integer | Search by appointment ID (exact match) |

**Pagination Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `page` | integer | `1` | Page number (1-indexed) |
| `per_page` | integer | `200` | Items per page (max: 2000) |
| `order` | string | `id_desc` | Sort: `id_desc`, `id_asc`, `date_desc`, `date_asc` |

*Note: `date_from` and `date_to` are ignored - today's date (UTC) is automatically applied.*

*Note: If both `user_id` and `improveit_user_id` are provided, `user_id` takes priority.*

**Success Response (200):**
```json
{
  "admin_user_id": 123,
  "date": "2025-01-15",
  "total": 25,
  "count": 25,
  "page": 1,
  "per_page": 200,
  "order": "id_desc",
  "filters": {
    "status": "scheduled",
    "customer": "john"
  },
  "appointments": [...]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `admin_user_id` | integer | Authenticated admin user ID |
| `date` | string | Today's date in UTC (`YYYY-MM-DD`) |
| `total` | integer | Total matching appointments |
| `count` | integer | Appointments in current page |
| `page` | integer | Current page number |
| `per_page` | integer | Items per page |
| `order` | string | Applied sort order |
| `filters` | object | Applied filters (echoed back) |
| `appointments` | array | List of appointment objects (see [Admin Appointment Object](#admin-appointment-object)) |

**Error Responses:**
| Status | Error | Description |
|--------|-------|-------------|
| 400 | `invalid_request` | Invalid `status` value. Allowed: `draft`, `scheduled`, `canceled`, `done` |
| 400 | `invalid_request` | Invalid `progress_status` value. Allowed: `not_started`, `in_progress`, `completed` |
| 400 | `invalid_request` | Conflicting `progress_status` and `status` |
| 400 | `invalid_request` | Invalid `order` value. Allowed: `id_desc`, `id_asc`, `date_desc`, `date_asc` |
| 400 | `invalid_request` | Invalid `id` value. Must be a valid integer |
| 400 | `invalid_request` | Invalid `page` or `per_page` value |
| 401 | `invalid_token` | Token invalid |
| 401 | `token_expired` | **Access token expired - call refresh endpoint** |
| 403 | `forbidden` | Caller is not a Pitch Admin |
| 404 | `user_not_found` | No user found with provided `improveit_user_id` |

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
```json
{
  "admin_user_id": 123,
  "appointment": {
    "id": 456,
    "improveit_appointment_id": "APT-12345",
    "name": "CAP/2025/001",
    "state": "scheduled",
    "partner_id": 789,
    "customer_name": "Jane Smith",
    "applicant_data": {...},
    "co_applicant_data": {...},
    "appointment_date": "2025-01-15 14:00:00",
    "..."
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `admin_user_id` | integer | Authenticated admin user ID |
| `appointment` | object | Full appointment object (see [Admin Appointment Object](#admin-appointment-object)) |

**Error Responses:**
| Status | Error | Description |
|--------|-------|-------------|
| 401 | `invalid_token` | Token invalid |
| 401 | `token_expired` | **Access token expired - call refresh endpoint** |
| 403 | `forbidden` | Caller is not a Pitch Admin |
| 404 | `not_found` | Appointment not found |

---

### GET /api/admin/appointments/{id}/app_screen_logs

Get screen logs for an appointment (admin access).

**Headers:**
| Header | Required | Description |
|--------|----------|-------------|
| `Authorization` | Yes | `Bearer <access_token>` (admin) |

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `id` | integer | Appointment ID |

**Success Response (200):**
```json
{
  "admin_user_id": 123,
  "appointment_id": 456,
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
| `admin_user_id` | integer | Authenticated admin user ID |
| `appointment_id` | integer | Appointment ID |
| `count` | integer | Number of log entries |
| `app_screen_logs` | array | List of screen logs |
| `app_screen_logs[].id` | integer | Log entry ID |
| `app_screen_logs[].name` | string | Screen name |
| `app_screen_logs[].completion_date` | string | Completion datetime (UTC) |
| `app_screen_logs[].user_id` | integer | User who completed |

**Error Responses:**
| Status | Error | Description |
|--------|-------|-------------|
| 401 | `invalid_token` | Token invalid |
| 401 | `token_expired` | **Access token expired - call refresh endpoint** |
| 403 | `forbidden` | Caller is not a Pitch Admin |
| 404 | `not_found` | Appointment not found |

---

### GET /api/admin/appointments/{id}/app_live_screen_logs

Get live screen logs for an appointment (admin access).

**Headers:**
| Header | Required | Description |
|--------|----------|-------------|
| `Authorization` | Yes | `Bearer <access_token>` (admin) |

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `id` | integer | Appointment ID |

**Success Response (200):**
```json
{
  "admin_user_id": 123,
  "appointment_id": 456,
  "count": 3,
  "app_live_screen_logs": [
    {
      "id": 1,
      "name": "Welcome Screen",
      "screen_entry_date": "2025-01-15 14:05:00",
      "user_id": 789
    },
    {
      "id": 2,
      "name": "Product Selection",
      "screen_entry_date": "2025-01-15 14:10:00",
      "user_id": 789
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `admin_user_id` | integer | Authenticated admin user ID |
| `appointment_id` | integer | Appointment ID |
| `count` | integer | Number of log entries |
| `app_live_screen_logs` | array | List of live screen logs |
| `app_live_screen_logs[].id` | integer | Log entry ID |
| `app_live_screen_logs[].name` | string | Screen name |
| `app_live_screen_logs[].screen_entry_date` | string | Screen entry datetime (UTC) |
| `app_live_screen_logs[].user_id` | integer | User ID |

**Error Responses:**
| Status | Error | Description |
|--------|-------|-------------|
| 401 | `invalid_token` | Token invalid |
| 401 | `token_expired` | **Access token expired - call refresh endpoint** |
| 403 | `forbidden` | Caller is not a Pitch Admin |
| 404 | `not_found` | Appointment not found |

---

### POST /api/admin/appointments/app_live_screen_logs

Get live screen logs for multiple appointments in a single request. Supports pagination for handling large numbers of appointments. Calculates time spent per appointment based on earliest and latest screen entry times.

**Headers:**
| Header | Required | Description |
|--------|----------|-------------|
| `Authorization` | Yes | `Bearer <access_token>` (admin) |
| `Content-Type` | Yes | `application/json` |

**Request Body:**
```json
{
  "appointment_ids": [123, 456, 789, ...],
  "page": 1,
  "per_page": 200
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `appointment_ids` | array | Yes | - | List of appointment IDs to fetch logs for |
| `page` | integer | No | 1 | Page number (1-based) for appointment list pagination |
| `per_page` | integer | No | 200 | Appointments per page (max: 2000) |

**Success Response (200):**
```json
{
  "admin_user_id": 123,
  "total_appointments": 5000,
  "count": 200,
  "page": 1,
  "per_page": 200,
  "total_logs": 1547,
  "total_time_spent_seconds": 86400,
  "average_time_spent_seconds": 432.5,
  "appointments": [
    {
      "appointment_id": 456,
      "logs_count": 5,
      "time_spent_seconds": 300,
      "app_live_screen_logs": [
        {
          "id": 1,
          "name": "Welcome Screen",
          "screen_entry_date": "2025-01-15 14:05:00",
          "user_id": 789
        },
        {
          "id": 2,
          "name": "Product Selection",
          "screen_entry_date": "2025-01-15 14:10:00",
          "user_id": 789
        }
      ]
    },
    {
      "appointment_id": 789,
      "logs_count": 0,
      "time_spent_seconds": 0,
      "app_live_screen_logs": []
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `admin_user_id` | integer | Authenticated admin user ID |
| `total_appointments` | integer | Total number of appointment IDs provided |
| `count` | integer | Number of appointments in current page |
| `page` | integer | Current page number |
| `per_page` | integer | Appointments per page |
| `total_logs` | integer | Total logs returned across all appointments in this page |
| `total_time_spent_seconds` | integer | Sum of time spent across all appointments in this page |
| `average_time_spent_seconds` | number | Average time spent per appointment (only counts appointments with 2+ logs) |
| `appointments` | array | List of appointments with their logs |
| `appointments[].appointment_id` | integer | Appointment ID |
| `appointments[].logs_count` | integer | Number of logs for this appointment |
| `appointments[].time_spent_seconds` | integer | Time spent on appointment (earliest to latest `screen_entry_date`) |
| `appointments[].app_live_screen_logs` | array | List of live screen logs |
| `appointments[].app_live_screen_logs[].id` | integer | Log entry ID |
| `appointments[].app_live_screen_logs[].name` | string | Screen name |
| `appointments[].app_live_screen_logs[].screen_entry_date` | string | Screen entry datetime (UTC) |
| `appointments[].app_live_screen_logs[].user_id` | integer | User ID |

**Notes:**
- Appointments that don't exist are included in the response with empty `app_live_screen_logs: []` and `time_spent_seconds: 0`
- `time_spent_seconds` is calculated as the difference between earliest and latest `screen_entry_date` in seconds
- Appointments with 0 or 1 log have `time_spent_seconds: 0` (need at least 2 entries to calculate time)
- `average_time_spent_seconds` only includes appointments that have time data (2+ logs)
- Pagination applies to the list of appointment IDs, not the logs themselves
- Designed to handle tens of thousands of appointment IDs efficiently

**Error Responses:**
| Status | Error | Description |
|--------|-------|-------------|
| 400 | `invalid_request` | `appointment_ids` is required, must be a non-empty list of integers |
| 401 | `invalid_token` | Token invalid |
| 401 | `token_expired` | **Access token expired - call refresh endpoint** |
| 403 | `forbidden` | Caller is not a Pitch Admin |

---

### GET /api/admin/appointments/analytics

Get aggregated time analytics and metrics for appointments. Calculates total time spent, average time, min/max times based on live screen logs. All filters are optional - if not provided, analyzes all appointments.

**Headers:**
| Header | Required | Description |
|--------|----------|-------------|
| `Authorization` | Yes | `Bearer <access_token>` (admin) |

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `market_segment` | string | No | Comma-separated list of market segments |
| `user_id` | string | No | Comma-separated list of Odoo user IDs |
| `improveit_user_id` | string | No | Comma-separated list of Salesforce user IDs (resolved to Odoo user IDs) |
| `date_from` | string | No | Start date in UTC: `YYYY-MM-DD` or `YYYY-MM-DD HH:MM:SS` |
| `date_to` | string | No | End date in UTC: `YYYY-MM-DD` or `YYYY-MM-DD HH:MM:SS` |

*Note: If both `user_id` and `improveit_user_id` are provided, `user_id` takes priority.*

**Example Requests:**
```
GET /api/admin/appointments/analytics
GET /api/admin/appointments/analytics?market_segment=Residential,Commercial
GET /api/admin/appointments/analytics?user_id=45,67,89
GET /api/admin/appointments/analytics?improveit_user_id=I360-123,I360-456
GET /api/admin/appointments/analytics?date_from=2025-01-01&date_to=2025-01-31
GET /api/admin/appointments/analytics?market_segment=Residential&user_id=45&date_from=2025-01-01
```

**Success Response (200):**
```json
{
  "admin_user_id": 123,
  "total_appointments": 500,
  "appointments_with_logs": 450,
  "appointments_without_logs": 50,
  "total_time_spent_seconds": 162000,
  "average_time_spent_seconds": 360.0,
  "min_time_spent_seconds": 60,
  "max_time_spent_seconds": 3600,
  "filters": {
    "market_segments": ["Residential", "Commercial"],
    "user_ids": [45, 67],
    "date_from": "2025-01-01",
    "date_to": "2025-01-31"
  }
}
```

**Success Response with improveit_user_id (200):**
```json
{
  "admin_user_id": 123,
  "total_appointments": 100,
  "appointments_with_logs": 95,
  "appointments_without_logs": 5,
  "total_time_spent_seconds": 36000,
  "average_time_spent_seconds": 378.95,
  "min_time_spent_seconds": 120,
  "max_time_spent_seconds": 1800,
  "filters": {
    "user_ids": [45, 67],
    "improveit_user_ids": ["I360-123", "I360-456"]
  }
}
```

**Success Response with no filters (200):**
```json
{
  "admin_user_id": 123,
  "total_appointments": 10000,
  "appointments_with_logs": 9500,
  "appointments_without_logs": 500,
  "total_time_spent_seconds": 3420000,
  "average_time_spent_seconds": 360.0,
  "min_time_spent_seconds": 30,
  "max_time_spent_seconds": 7200
}
```

| Field | Type | Description |
|-------|------|-------------|
| `admin_user_id` | integer | Authenticated admin user ID |
| `total_appointments` | integer | Total number of appointments matching filters |
| `appointments_with_logs` | integer | Appointments with 2+ logs (time can be calculated) |
| `appointments_without_logs` | integer | Appointments with 0-1 logs (time cannot be calculated) |
| `total_time_spent_seconds` | integer | Sum of time spent across all appointments with logs |
| `average_time_spent_seconds` | number | Average time spent per appointment (only counts appointments with 2+ logs) |
| `min_time_spent_seconds` | integer | Minimum time spent on a single appointment |
| `max_time_spent_seconds` | integer | Maximum time spent on a single appointment |
| `filters` | object | Applied filters (only present if any filter was applied) |
| `filters.market_segments` | array | Market segments filter |
| `filters.user_ids` | array | Odoo user IDs filter |
| `filters.improveit_user_ids` | array | Original Salesforce user IDs (when resolved to Odoo IDs) |
| `filters.date_from` | string | Start date filter |
| `filters.date_to` | string | End date filter |

**Notes:**
- Time spent is calculated as the difference between earliest and latest `screen_entry_date` for each appointment
- Appointments with 0 or 1 log are counted as `appointments_without_logs` (need at least 2 entries to calculate time)
- When `improveit_user_id` is provided, the system resolves it to Odoo user IDs and filters by those
- If no matching users are found for `improveit_user_id`, returns empty results with count 0

**Error Responses:**
| Status | Error | Description |
|--------|-------|-------------|
| 401 | `invalid_token` | Token invalid |
| 401 | `token_expired` | **Access token expired - call refresh endpoint** |
| 403 | `forbidden` | Caller is not a Pitch Admin |

---

### GET /api/admin/market-segments

Get all distinct market segment values from appointments.

**Headers:**
| Header | Required | Description |
|--------|----------|-------------|
| `Authorization` | Yes | `Bearer <access_token>` (admin) |

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `user_id` | integer | - | Filter by salesperson/user ID (optional) |

**Success Response (200):**
```json
{
  "admin_user_id": 123,
  "count": 5,
  "market_segments": ["Commercial", "Government", "Residential", "Retail", "Wholesale"]
}
```

**Success Response with `user_id` filter (200):**
```json
{
  "admin_user_id": 123,
  "count": 2,
  "market_segments": ["Residential", "Commercial"],
  "user_id": 45
}
```

| Field | Type | Description |
|-------|------|-------------|
| `admin_user_id` | integer | Authenticated admin user ID |
| `count` | integer | Number of distinct market segments |
| `market_segments` | array | Sorted list of market segment names (strings) |
| `user_id` | integer | User ID filter (only present if filter was applied) |

**Error Responses:**
| Status | Error | Description |
|--------|-------|-------------|
| 401 | `invalid_token` | Token invalid |
| 401 | `token_expired` | **Access token expired - call refresh endpoint** |
| 403 | `forbidden` | Caller is not a Pitch Admin |

---

### GET /api/admin/salespersons

List salespersons who have appointments. Returns unique salespersons, optionally filtered by market segment(s). If no `market_segment` is provided, returns all salespersons from all appointments.

**Headers:**
| Header | Required | Description |
|--------|----------|-------------|
| `Authorization` | Yes | `Bearer <access_token>` (admin) |

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `market_segment` | string | No | Comma-separated list of market segments to filter by. If omitted, returns all salespersons. |

**Example Requests:**
```
GET /api/admin/salespersons
GET /api/admin/salespersons?market_segment=Residential
GET /api/admin/salespersons?market_segment=Residential,Commercial
```

**Success Response with filter (200):**
```json
{
  "count": 3,
  "market_segments": ["Residential", "Commercial"],
  "salespersons": [
    {
      "id": 45,
      "improveit_user_id": "I360-123",
      "name": "Jane Smith",
      "login": "jane@example.com"
    },
    {
      "id": 67,
      "improveit_user_id": "I360-456",
      "name": "John Doe",
      "login": "john@example.com"
    },
    {
      "id": 89,
      "improveit_user_id": null,
      "name": "Bob Johnson",
      "login": "bob@example.com"
    }
  ]
}
```

**Success Response without filter (200):**
```json
{
  "count": 50,
  "market_segments": ["Commercial", "Government", "Residential", "Retail", "Wholesale"],
  "salespersons": [
    {
      "id": 45,
      "improveit_user_id": "I360-123",
      "name": "Jane Smith",
      "login": "jane@example.com"
    }
  ]
}
```

**Empty Result Response (200):**
```json
{
  "count": 0,
  "market_segments": ["NonExistent"],
  "salespersons": []
}
```

| Field | Type | Description |
|-------|------|-------------|
| `count` | integer | Number of unique salespersons |
| `market_segments` | array | Market segments used for filtering, or all available market segments if no filter applied |
| `salespersons` | array | List of unique salespersons (sorted by name) |
| `salespersons[].id` | integer | User ID |
| `salespersons[].improveit_user_id` | string/null | External user ID (Salesforce) |
| `salespersons[].name` | string/null | User full name |
| `salespersons[].login` | string/null | User login (email) |

**Error Responses:**
| Status | Error | Description |
|--------|-------|-------------|
| 401 | `invalid_token` | Token invalid |
| 401 | `token_expired` | **Access token expired - call refresh endpoint** |
| 403 | `forbidden` | Caller is not a Pitch Admin |

---

## Admin Appointment Object

All admin appointment endpoints return appointments with the following structure.
All datetime values are in UTC.

**Appointment Object Fields:**
| Field | Type | Description |
|-------|------|-------------|
| `id` | integer | Appointment ID |
| `improveit_appointment_id` | string/null | External appointment ID (Salesforce) |
| `name` | string/null | Appointment reference number (e.g., `CAP/2025/001`) |
| `state` | string/null | Status: `draft`, `scheduled`, `canceled`, `done` |
| `partner_id` | integer/null | Customer partner ID |
| `customer_name` | string/null | Customer full name |
| `applicant_data` | object | Primary applicant information (see below) |
| `co_applicant_data` | object | Co-applicant information (see below) |
| `appointment_date` | string/null | Scheduled datetime (UTC) |
| `what_happened_notes` | string/null | Notes about the appointment |
| `appointment_result` | string/null | Result of appointment |
| `office_location_id` | integer/null | Office location ID |
| `office_location_name` | string/null | Office location name |
| `app_data` | object | App version information (see below) |
| `credit_application_url` | string/null | Credit application URL |
| `appointment_result_details` | object | Detailed result information (see below) |
| `user_id` | integer/null | Assigned user ID |
| `user_data` | object | Assigned user information (see below) |
| `measurement_exist` | boolean | Whether measurements exist |
| `send_physical_document` | boolean | Send physical document flag |
| `flexible_installation` | boolean | Flexible installation flag |
| `whats_next_notes` | string/null | Next steps notes |
| `last_price_quoted_value` | number/null | Last quoted price |
| `market_segment` | string/null | Market segment |
| `both_parties_present` | boolean | Both parties were present |
| `sent_review_link` | boolean | Review link was sent |
| `make_payment_failure` | boolean | Payment failure occurred |
| `destination_selection_id` | integer/null | Destination selection ID |
| `destination_selection_name` | string/null | Destination selection name |
| `additional_comments` | string/null | Additional comments |
| `geolocation_data` | object | GPS location data (see below) |
| `arrival_date` | string/null | Arrival datetime (UTC) |
| `departure_date` | string/null | Departure datetime (UTC) |
| `manual_arrival_date` | string/null | Manual arrival datetime (UTC) |
| `progress_status` | string | Derived progress: `not_started`, `in_progress`, `completed` |
| `progress_status_updated_at` | string/null | Latest live screen log `screen_entry_date` (UTC), or null |

**Nested Object: `applicant_data`**
| Field | Type | Description |
|-------|------|-------------|
| `applicant_first_name` | string/null | First name |
| `applicant_middle_name` | string/null | Middle name |
| `applicant_last_name` | string/null | Last name |
| `applicant_address` | object | Address object with `street`, `street2`, `city`, `state_id`, `state_code`, `state_name`, `country_id`, `country_code`, `country_name`, `zip` |
| `phone` | string/null | Phone number |
| `mobile` | string/null | Mobile number |
| `email` | string/null | Email address |

**Nested Object: `co_applicant_data`**
| Field | Type | Description |
|-------|------|-------------|
| `co_applicant` | string/null | Co-applicant full name |
| `co_applicant_first_name` | string/null | First name |
| `co_applicant_middle_name` | string/null | Middle name |
| `co_applicant_last_name` | string/null | Last name |
| `co_applicant_address` | object | Address object with `co_applicant_address`, `co_applicant_city`, `co_applicant_state_id`, `co_applicant_state_code`, `co_applicant_state_name`, `co_applicant_country_id`, `co_applicant_country_code`, `co_applicant_country_name`, `co_applicant_zip`, `co_applicant_state_code_2` |
| `co_applicant_phone` | string/null | Phone number |
| `co_applicant_secondary_phone` | string/null | Secondary phone number |
| `co_applicant_email` | string/null | Email address |

**Nested Object: `app_data`**
| Field | Type | Description |
|-------|------|-------------|
| `id` | integer/null | App version ID |
| `app_version` | string/null | App version name |
| `app_release_date` | string/null | App release date |

**Nested Object: `appointment_result_details`**
| Field | Type | Description |
|-------|------|-------------|
| `id` | integer/null | Result reason ID |
| `reason` | string/null | Result reason text |
| `tags` | array/null | List of result tag names |

**Nested Object: `user_data`**
| Field | Type | Description |
|-------|------|-------------|
| `id` | integer/null | User ID |
| `name` | string/null | User full name |
| `login` | string/null | User login (email) |

**Nested Object: `geolocation_data`**
| Field | Type | Description |
|-------|------|-------------|
| `date_localization` | string/null | Localization datetime (UTC) |
| `partner_latitude` | number/null | Latitude |
| `partner_longitude` | number/null | Longitude |

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

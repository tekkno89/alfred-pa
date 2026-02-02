# Phase 3: Authentication

**Status:** ✅ Complete
**Started:** 2026-02-01
**Completed:** 2026-02-01

---

## Goal

Implement email/password authentication with JWT tokens. Replace the placeholder `X-User-Id` header authentication with proper JWT-based authentication.

---

## Scope

**In Scope:**
- Email/password registration and login
- JWT access token generation and validation
- Password hashing with bcrypt
- Protected route middleware
- User profile endpoint

**Out of Scope (Future):**
- Google OAuth integration
- Password reset / forgot password
- Email verification
- Token expiration + refresh tokens
- KMS integration for JWT signing

---

## Tasks

### Security Utilities
- [x] Create `app/core/security.py` module
- [x] Implement `hash_password()` using bcrypt
- [x] Implement `verify_password()` for password checking
- [x] Implement `create_access_token()` for JWT generation
- [x] Implement `decode_access_token()` for JWT validation

### Pydantic Schemas
- [x] Create `app/schemas/auth.py` module
- [x] Create `UserRegister` schema (email, password with min 8 chars)
- [x] Create `UserLogin` schema (email, password)
- [x] Create `TokenResponse` schema (access_token, token_type)
- [x] Create `UserResponse` schema (id, email, created_at)

### User Repository
- [x] Create `app/db/repositories/user.py` module
- [x] Implement `get_by_email()` method
- [x] Implement `create_user()` method
- [x] Export from repositories `__init__.py`

### Auth API Endpoints
- [x] Create `app/api/auth.py` router
- [x] `POST /api/auth/register` - Create new user, return JWT
- [x] `POST /api/auth/login` - Authenticate, return JWT
- [x] `GET /api/auth/me` - Get current user profile
- [x] Include auth router in API `__init__.py`

### Update Authentication Middleware
- [x] Update `app/api/deps.py` to use JWT Bearer tokens
- [x] Replace `X-User-Id` header with `Authorization: Bearer <token>`
- [x] Use `HTTPBearer` security scheme
- [x] Maintain `CurrentUser` and `OptionalUser` type aliases

### Testing
- [x] Create `tests/test_auth.py` with comprehensive tests
- [x] Test registration success and validation errors
- [x] Test login success and authentication failures
- [x] Test protected endpoint access with/without tokens
- [x] Update existing session tests to use JWT auth
- [x] Update existing message tests to use JWT auth
- [x] Add `auth_headers()` helper to conftest.py

### Dependencies
- [x] Add `email-validator` package for EmailStr support

---

## API Specification

### Registration

```
POST /api/auth/register
Request:  { "email": "user@example.com", "password": "securepass123" }
Response: { "access_token": "eyJ...", "token_type": "bearer" }
Status:   201 Created

Errors:
- 400: Email already registered
- 422: Invalid email format or password too short
```

### Login

```
POST /api/auth/login
Request:  { "email": "user@example.com", "password": "securepass123" }
Response: { "access_token": "eyJ...", "token_type": "bearer" }
Status:   200 OK

Errors:
- 401: Invalid email or password
```

### Get Current User

```
GET /api/auth/me
Headers:  Authorization: Bearer eyJ...
Response: { "id": "uuid", "email": "user@example.com", "created_at": "..." }
Status:   200 OK

Errors:
- 401: Not authenticated (missing or invalid token)
```

---

## JWT Token Structure

```json
{
  "sub": "user-uuid"
}
```

- Algorithm: HS256
- Secret: Configured via `JWT_SECRET` environment variable
- No expiration (for now) - refresh tokens planned for future

---

## Files Created

```
backend/app/
├── core/
│   └── security.py          # NEW: Password hashing + JWT utilities
├── schemas/
│   └── auth.py              # NEW: Auth request/response schemas
├── api/
│   └── auth.py              # NEW: Auth endpoints
└── db/
    └── repositories/
        └── user.py          # NEW: User repository

backend/tests/
└── test_auth.py             # NEW: Auth tests (15 tests)
```

## Files Modified

```
backend/app/api/deps.py          # JWT Bearer authentication
backend/app/api/__init__.py      # Include auth router
backend/app/schemas/__init__.py  # Export auth schemas
backend/app/db/repositories/__init__.py  # Export UserRepository
backend/tests/conftest.py        # auth_headers() helper
backend/tests/test_sessions.py   # Use JWT auth
backend/tests/test_messages.py   # Use JWT auth
backend/pyproject.toml           # email-validator dependency
```

---

## Verification

1. Start services: `docker-compose -f docker-compose.dev.yml up`
2. Register a user:
   ```bash
   curl -X POST http://localhost:8000/api/auth/register \
     -H "Content-Type: application/json" \
     -d '{"email": "test@example.com", "password": "securepassword123"}'
   ```
3. Login:
   ```bash
   curl -X POST http://localhost:8000/api/auth/login \
     -H "Content-Type: application/json" \
     -d '{"email": "test@example.com", "password": "securepassword123"}'
   ```
4. Get profile with token:
   ```bash
   curl http://localhost:8000/api/auth/me \
     -H "Authorization: Bearer <token>"
   ```
5. Test protected sessions endpoint:
   ```bash
   curl http://localhost:8000/api/sessions \
     -H "Authorization: Bearer <token>"
   ```
6. Run tests: `docker-compose exec backend pytest tests/test_auth.py -v`
7. Verify all tests pass: `docker-compose exec backend pytest` (44 tests)

---

## Test Results

```
tests/test_auth.py::TestRegister::test_register_success PASSED
tests/test_auth.py::TestRegister::test_register_duplicate_email PASSED
tests/test_auth.py::TestRegister::test_register_invalid_email PASSED
tests/test_auth.py::TestRegister::test_register_short_password PASSED
tests/test_auth.py::TestLogin::test_login_success PASSED
tests/test_auth.py::TestLogin::test_login_wrong_password PASSED
tests/test_auth.py::TestLogin::test_login_nonexistent_user PASSED
tests/test_auth.py::TestLogin::test_login_oauth_user_no_password PASSED
tests/test_auth.py::TestGetCurrentUser::test_get_me_success PASSED
tests/test_auth.py::TestGetCurrentUser::test_get_me_no_token PASSED
tests/test_auth.py::TestGetCurrentUser::test_get_me_invalid_token PASSED
tests/test_auth.py::TestGetCurrentUser::test_get_me_nonexistent_user PASSED
tests/test_auth.py::TestProtectedEndpoints::test_sessions_with_jwt PASSED
tests/test_auth.py::TestProtectedEndpoints::test_sessions_without_token PASSED
tests/test_auth.py::TestProtectedEndpoints::test_create_session_with_jwt PASSED

======================== 15 passed ========================
```

Total project tests: **44 passed**

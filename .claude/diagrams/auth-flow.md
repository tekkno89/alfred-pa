# Authentication Flow

## JWT Authentication Flow

```mermaid
sequenceDiagram
    participant C as Client
    participant A as Auth API
    participant D as Database
    participant S as Sessions API

    Note over C,S: Registration Flow
    C->>A: POST /auth/register {email, password}
    A->>A: Validate email format & password length
    A->>D: Check if email exists
    D-->>A: Not found
    A->>A: Hash password (bcrypt)
    A->>D: Create user
    D-->>A: User created
    A->>A: Generate JWT token
    A-->>C: {access_token, token_type: "bearer"}

    Note over C,S: Login Flow
    C->>A: POST /auth/login {email, password}
    A->>D: Find user by email
    D-->>A: User found
    A->>A: Verify password (bcrypt)
    A->>A: Generate JWT token
    A-->>C: {access_token, token_type: "bearer"}

    Note over C,S: Protected Request Flow
    C->>S: GET /sessions (Authorization: Bearer <token>)
    S->>S: Extract token from header
    S->>S: Decode & validate JWT
    S->>D: Fetch user by ID from token
    D-->>S: User found
    S->>D: Fetch user's sessions
    D-->>S: Sessions list
    S-->>C: {items: [...], total: N}
```

## JWT Token Structure

```mermaid
graph LR
    subgraph JWT Token
        H[Header<br/>alg: HS256<br/>typ: JWT]
        P[Payload<br/>sub: user-uuid]
        S[Signature<br/>HMAC-SHA256]
    end
    H --> P --> S
```

## Authentication Middleware

```mermaid
flowchart TD
    A[Incoming Request] --> B{Has Authorization Header?}
    B -->|No| C[Return None / 401]
    B -->|Yes| D{Valid Bearer Format?}
    D -->|No| C
    D -->|Yes| E[Extract Token]
    E --> F{Decode JWT Valid?}
    F -->|No| C
    F -->|Yes| G[Get user_id from 'sub' claim]
    G --> H{User exists in DB?}
    H -->|No| C
    H -->|Yes| I[Return User object]
    I --> J[Continue to endpoint]
```

## Components

- **Auth API** (`/api/auth/`): Registration, login, profile endpoints
- **Security Module** (`app/core/security.py`): Password hashing, JWT encode/decode
- **Dependencies** (`app/api/deps.py`): `CurrentUser`, `OptionalUser` injection
- **HTTPBearer**: FastAPI security scheme for Swagger UI integration

# Token Encryption Flow

## Envelope Encryption Architecture

```mermaid
graph TD
    subgraph "KEK Layer (Key Encryption Key)"
        KEK_LOCAL[Local Fernet Key<br/>ENCRYPTION_KEK_LOCAL_KEY]
        KEK_GCP[GCP KMS Key<br/>ENCRYPTION_GCP_KMS_KEY_NAME]
        KEK_AWS[AWS KMS Key<br/>ENCRYPTION_AWS_KMS_KEY_ID]
    end

    subgraph "DEK Layer (Data Encryption Key)"
        DEK[DEK<br/>Fernet key generated per-app]
        DEK_ENC[Encrypted DEK<br/>stored in encryption_keys table]
    end

    subgraph "Data Layer"
        TOKEN[Plaintext Token<br/>e.g. xoxp-..., ghp_...]
        CIPHERTEXT[Encrypted Token<br/>stored in user_oauth_tokens]
    end

    KEK_LOCAL -->|encrypts/decrypts| DEK_ENC
    KEK_GCP -->|encrypts/decrypts| DEK_ENC
    KEK_AWS -->|encrypts/decrypts| DEK_ENC
    DEK_ENC -->|decrypted to| DEK
    DEK -->|encrypts/decrypts| TOKEN
    TOKEN -->|encrypted to| CIPHERTEXT
```

## Token Storage Flow

```mermaid
sequenceDiagram
    participant S as Service<br/>(SlackUserService, GitHubService)
    participant TES as TokenEncryptionService
    participant ES as EncryptionService
    participant DB as PostgreSQL

    S->>TES: store_encrypted_token(user_id, provider, access_token)
    TES->>DB: Look up active DEK (oauth_tokens_dek_v1)
    alt DEK exists
        DB-->>TES: Return encryption_key record
    else No DEK yet
        TES->>ES: generate_dek()
        ES->>ES: Generate Fernet key
        ES->>ES: Encrypt DEK with KEK provider
        ES-->>TES: (encrypted_dek, plaintext_dek)
        TES->>DB: Store encryption_key record
    end
    TES->>ES: encrypt(access_token, encrypted_dek)
    ES->>ES: Decrypt DEK (cache hit or KEK decrypt)
    ES->>ES: Fernet encrypt with plaintext DEK
    ES-->>TES: ciphertext
    TES->>DB: Store UserOAuthToken with encrypted fields
```

## Token Retrieval Flow

```mermaid
sequenceDiagram
    participant S as Service
    participant TES as TokenEncryptionService
    participant ES as EncryptionService
    participant DB as PostgreSQL
    participant Cache as In-Memory DEK Cache

    S->>TES: get_decrypted_access_token(token)
    alt Has encrypted_access_token
        TES->>DB: Look up encryption_key by ID
        DB-->>TES: encryption_key record
        TES->>ES: decrypt(ciphertext, encrypted_dek)
        ES->>Cache: Check DEK cache (5 min TTL)
        alt Cache hit
            Cache-->>ES: plaintext DEK
        else Cache miss
            ES->>ES: Decrypt DEK via KEK provider
            ES->>Cache: Cache plaintext DEK
        end
        ES->>ES: Fernet decrypt with plaintext DEK
        ES-->>TES: plaintext access_token
    else No encrypted fields (legacy)
        TES-->>S: Return plaintext access_token column
    end
```

## Components

### KEK Providers (`app/core/encryption/kek_provider.py`)
- **LocalKEKProvider**: Uses a Fernet key from env var or file. Auto-generates ephemeral key if none configured (dev only).
- **GCPKMSKEKProvider**: Uses Google Cloud KMS. Requires `google-cloud-kms` package.
- **AWSKMSKEKProvider**: Uses AWS KMS. Requires `boto3` package.

### EncryptionService (`app/core/encryption/service.py`)
- Singleton via `get_encryption_service()` (lru_cache)
- Provider selected by `ENCRYPTION_KEK_PROVIDER` setting
- In-memory DEK cache with 5-minute TTL to avoid repeated KMS calls

### TokenEncryptionService (`app/services/token_encryption.py`)
- Wraps EncryptionService for token-specific operations
- Manages DEK lifecycle (get or create `oauth_tokens_dek_v1`)
- Fallback: reads plaintext `access_token` column for un-migrated tokens

### Database Tables
- **encryption_keys**: Stores encrypted DEKs with provider metadata
- **user_oauth_tokens**: New columns `encrypted_access_token`, `encrypted_refresh_token`, `encryption_key_id`

## Known Limitations

- **No automatic re-encryption on provider switch**: Changing `ENCRYPTION_KEK_PROVIDER` after tokens are encrypted requires a manual re-encryption migration
- **Single provider at a time**: The decrypt path uses the currently configured provider, not the `kek_provider` recorded on each DEK
- **Ephemeral key warning**: Without `ENCRYPTION_KEK_LOCAL_KEY` set, encrypted tokens won't survive process restarts

# System diagrams

These Mermaid diagrams are editable design sources. GitHub renders Mermaid blocks directly. The Word report also includes generated architecture, upload-flow and database figures.

## System architecture

```mermaid
flowchart LR
    B[Browser with HTML forms] -->|HTTP locally or HTTPS through proxy| W[Waitress]
    W --> A[Flask routes and security controls]
    A --> V[Validation and normalization]
    V --> C[Optional local ClamAV process]
    V --> E[Fernet encryption]
    E --> F[(Private encrypted vault)]
    A <--> D[(SQLite metadata and sessions)]
    A --> L[HMAC audit chain]
    L --> D
    K[Protected key files] --> E
    K --> L
```

## Context DFD

```mermaid
flowchart LR
    U[Registered user] -->|Credentials, upload, file operation| S((Secure File Upload System))
    S -->|Status, file attachment, activity| U
    O[System operator] -->|Environment, keys and scanner policy| S
    S -->|Normalized content| C[Optional ClamAV]
    C -->|Clean, detected or error| S
```

## Level 1 DFD

```mermaid
flowchart TD
    U[User] --> P1((1 Authenticate))
    P1 <--> D1[(Users and sessions)]
    U --> P2((2 Validate upload))
    P1 -->|Authorized session| P2
    P2 --> P3((3 Normalize and optionally scan))
    P3 --> P4((4 Check quota and encrypt))
    P4 --> D2[(File metadata)]
    P4 --> D3[(Encrypted blobs)]
    U --> P5((5 Retrieve or delete))
    P5 <--> D2
    P5 <--> D3
    P5 -->|Verified attachment or status| U
    P1 --> P6((6 Record audit event))
    P2 --> P6
    P4 --> P6
    P5 --> P6
    P6 --> D4[(HMAC-linked events)]
```

## Entity relationship diagram

```mermaid
erDiagram
    USERS ||--o{ FILES : owns
    USERS ||--o{ SESSIONS : authenticates
    USERS |o--o{ EVENTS : generates
    USERS {
        integer id PK
        text username UK
        text password_hash
        blob totp_secret
        blob totp_pending
        integer totp_last
        text created_at
    }
    FILES {
        text id PK
        integer owner_id FK
        text name
        integer size
        text mime
        text sha256
        text scan
        text created_at
    }
    SESSIONS {
        text token_hash PK
        integer user_id FK
        integer expires_at
    }
    EVENTS {
        integer id PK
        integer user_id FK
        text action
        text detail
        text created_at
        text chain_mac
    }
```

## Upload sequence

```mermaid
sequenceDiagram
    actor User
    participant App as Flask application
    participant Validator
    participant Scanner as Optional ClamAV
    participant DB as SQLite
    participant Vault as Encrypted filesystem
    User->>App: POST file and CSRF token
    App->>DB: Check session and expiry
    App->>Validator: Name, MIME and bounded bytes
    Validator->>Validator: Signature, decode, dimensions, normalize
    alt Configured scanner
        Validator->>Scanner: Scan normalized content
        Scanner-->>Validator: Result or timeout
    end
    alt Any validation or scanning error
        App->>DB: Audit rejection
        App-->>User: Explain rejection
    else Accepted content
        App->>DB: Begin immediate transaction and check quota
        App->>Vault: Write encrypted bytes under random ID
        App->>DB: Insert metadata and commit
        App->>DB: Append HMAC-linked event
        App-->>User: Redirect to updated file list
    end
```

## Use cases

```mermaid
flowchart LR
    U[User] --> R([Register])
    U --> L([Sign in])
    U --> F([Upload supported file])
    U --> D([Download owned file])
    U --> X([Delete owned file])
    U --> A([View activity])
    U --> M([Configure TOTP])
    U --> S([Revoke sessions])
    F -. includes .-> V([Validate and normalize])
    D -. includes .-> I([Verify ownership and integrity])
```

## File life cycle

```mermaid
stateDiagram-v2
    [*] --> Received
    Received --> Rejected: Invalid request or content
    Received --> Normalized: Valid content
    Normalized --> Rejected: Scanner or quota failure
    Normalized --> Stored: Encrypt and commit
    Stored --> Stored: Authorized verified download
    Stored --> Unavailable: Integrity check fails
    Stored --> Deleted: Authorized POST deletion
    Rejected --> [*]
    Deleted --> [*]
```

The life-cycle states describe control flow; they are not a persistent quarantine state machine. Uploads are processed synchronously and only accepted files are entered in the files table.

## Sharing sequence

```mermaid
sequenceDiagram
    participant Owner
    participant App
    participant DB as SQLite
    participant Recipient
    Owner->>App: Create code for owned file
    App->>App: Verify file, generate 96 random bits
    App->>DB: Store hash and 15-minute expiry
    App-->>Owner: Show code once
    Recipient->>App: Submit code and CSRF token
    App->>DB: Check hash, expiry and unused state
    App->>App: Verify ciphertext and SHA-256
    App->>DB: Atomically mark used
    App-->>Recipient: Download attachment
    Recipient->>App: Reuse code
    App-->>Recipient: Reject
```

## Document processing

```mermaid
flowchart LR
    A[Validated image] --> B[Bound to 2000-pixel side]
    B --> C[Edges and convex quadrilateral]
    C --> D{Page found?}
    D -->|Yes| E[Perspective correction]
    D -->|No| F[Preserve full frame]
    E --> G[Grayscale CLAHE]
    F --> G
    G --> H[Antivirus policy then encrypted storage]
```

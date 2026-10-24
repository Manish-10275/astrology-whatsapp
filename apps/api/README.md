# Astrology Platform Backend API (`apps/api`)

Production-ready FastAPI backend, PostgreSQL persistence layer, field-level encryption, privacy lifecycle management (GDPR/DPDP Right-to-Erasure), and admin authentication for the Astrology WhatsApp AI Platform.

---

## 1. Architecture & Capabilities

- **Framework:** FastAPI with Python 3.12 (asynchronous routing, typed Pydantic v2 schemas).
- **ORM & Migrations:** SQLAlchemy 2.0 (asyncpg driver) and Alembic 1.13+ (sync psycopg driver).
- **Database:** PostgreSQL 16+ (compatible with local PostgreSQL 18).
- **Field-Level Encryption:** AES-256-GCM authenticated encryption for sensitive birth data and PII (`{version}:{base64(12B_nonce + ciphertext + 16B_tag)}`).
- **Pseudonymization:** Deterministic HMAC-SHA256 salted phone hash for indexable user lookups without storing plaintext phone numbers in queryable columns.
- **Admin Authentication:** Argon2id password hashing (`argon2-cffi`), JWT session access tokens with UUID `jti`, and brute-force lockout after 5 failed attempts for 15 minutes.
- **Role-Based Access Control (RBAC):** Strict permission checks for `super_admin`, `support`, `astrology_qa`, and `compliance` roles.
- **Privacy & Erasure (GDPR / DPDP):** Consent capture, consent revocation, and atomic Right-to-Erasure cascading deletions.

---

## 2. Environment Variables Configuration

Create a local `.env` file in `apps/api/.env` (or configure system environment variables):

```bash
# Core Environment
ENVIRONMENT=development
LOG_LEVEL=INFO

# Database Connection URLs
DATABASE_URL=postgresql+asyncpg://postgres@localhost:5432/astrology_dev
DATABASE_SYNC_URL=postgresql+psycopg://postgres@localhost:5432/astrology_dev

# Connection Pooling
DATABASE_POOL_SIZE=10
DATABASE_MAX_OVERFLOW=20
DATABASE_POOL_TIMEOUT=30

# Security: Field-Level Encryption (AES-256-GCM)
# 64 hex characters (32 bytes / 256 bits)
ENCRYPTION_PRIMARY_KEY=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
ENCRYPTION_KEY_VERSION=v1
# Keyring of historical versions for decryption during key rotation transitions
ENCRYPTION_SECONDARY_KEYS={"v0": "fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210"}

# Security: Admin JWT Secret (Minimum 32 characters)
JWT_SECRET_KEY=super-secret-jwt-key-with-minimum-32-characters-required-here
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60

# Identity Pseudonymization Salt (Minimum 16 characters)
PHONE_HASH_SALT=default-phone-hash-salt-32-chars-long-minimum

# Brute Force Lockout
AUTH_MAX_FAILED_ATTEMPTS=5
AUTH_LOCKOUT_MINUTES=15
```

---

## 3. Database Setup & Migrations

### Prerequisites
PostgreSQL 16+ running locally on port 5432. Create the development and test databases:
```sql
CREATE DATABASE astrology_dev;
CREATE DATABASE astrology_test;
```

### Apply Migrations
From `apps/api/`:
```bash
# Upgrade to latest migration revision
alembic upgrade head

# Downgrade one revision (reproducibility testing)
alembic downgrade -1
```

### Autogenerate New Migration
```bash
alembic revision --autogenerate -m "describe_changes"
```

---

## 4. Bootstrapping Initial Administrator

Use the CLI bootstrap tool to create an initial super admin account without hardcoding credentials:

```bash
uv run --python ../../.venv/Scripts/python.exe -m api.bootstrap_admin --username admin --email admin@example.com --role super_admin --password "SecureAdminPassword123!"
```

---

## 5. Running the API Server

```bash
# From workspace root
uv run --python .venv/Scripts/python.exe -m uvicorn api.main:app --app-dir apps/api/src --host 0.0.0.0 --port 8000 --reload
```

Interactive documentation is available at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- Liveness Probe: `http://localhost:8000/health/live`
- Readiness Probe: `http://localhost:8000/health/ready`

---

## 6. Running Tests

Run the full persistence and security test suite against disposable PostgreSQL:

```bash
$env:PYTHONPATH='apps/api/src'
uv run --python .venv/Scripts/python.exe pytest apps/api/tests/ -v
```


## Curated Astrology Knowledge RAG (feature-flagged)

The initial retrieval layer lives under src/api/rag/. It provides heading-aware Markdown chunking, an OpenAI embedding adapter, reviewed-source metadata, PostgreSQL/pgvector retrieval filtered by language and astrology tradition, bounded source-attributed context, and transactional ingestion primitives.

Review source accuracy, rights/licensing, language and astrology tradition before ingestion. Draft and rejected sources are never retrieved. The migration creates the PostgreSQL vector extension and HNSW cosine index; the database server must have pgvector installed and the migration role must be permitted to create the extension.

RAG is disabled by default (RAG_ENABLED=false). When explicitly enabled, educational astrology questions in an established reading conversation can use the curated retrieval path; existing personalized calculation commands continue through the deterministic handlers. MEMORY_ENABLED is reserved and must remain false until consent checks, memory controls and deletion lifecycle integration are implemented. User birth details remain in the existing encrypted profile and must never be placed in the public knowledge index.

See the RAG implementation plan at ../../docs/rag-architecture-implementation.md for rollout, privacy boundaries and evaluation requirements.

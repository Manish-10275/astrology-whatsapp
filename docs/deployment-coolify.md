# Coolify Deployment Runbook — Astrology WhatsApp Platform

This guide provides step-by-step instructions for deploying the Astrology WhatsApp AI Platform through **Coolify** on an existing server using your custom domain.

- **Repository:** `https://github.com/Manish-10275/astrology-whatsapp.git`
- **Default Branch:** `main`
- **Recommended Coolify Architecture:** Coolify Managed PostgreSQL Resource (`pgvector/pgvector:pg16`) + Coolify Application (`Dockerfile` build pack).

---

## 1. Prerequisites & Sizing

| Component | Minimum | Recommended |
| :--- | :--- | :--- |
| **Coolify Version** | v4.x | Latest stable |
| **Server CPU / RAM** | 2 vCPU / 2 GB RAM | 2–4 vCPU / 4 GB RAM |
| **Network** | Dedicated IPv4 | Public static IPv4 |
| **Reverse Proxy** | Coolify built-in Traefik | Let's Encrypt automated TLS |

---

## 2. Step 1: Provision PostgreSQL with pgvector

The platform utilizes Alembic migration `7e2c9a4b6d10` which activates `CREATE EXTENSION IF NOT EXISTS vector` and creates `Vector(1536)` HNSW indexes.

1. In Coolify: Navigate to your **Project** → **Environment** → Click **+ New Resource**.
2. Select **Database** → **PostgreSQL**.
3. In Database Configuration:
   - **Docker Image:** Change `postgres:16-alpine` to:
     ```text
     pgvector/pgvector:pg16
     ```
   - **Database Name:** `astrology_prod`
   - **Database User:** `astrology_user`
   - **Password:** Generate a strong random password (32+ characters).
   - **Make it publicly available:** **Unchecked (Off)** (ensures the database is only reachable internally on the private Docker bridge network).
4. Click **Save** and then **Start Database**.
5. Note the **Internal Database Hostname** (e.g. `astrology-postgres` or the generated service UUID).

---

## 3. Step 2: Configure DNS at Your Registrar

Before adding the domain in Coolify, verify DNS resolution to ensure automated Let's Encrypt certificate generation succeeds without challenge failures.

1. Add an **`A` Record** at your domain registrar/DNS provider:
   - **Name / Host:** `astrology` (for subdomain `astrology.yourdomain.com`) or `@` (for apex root domain).
   - **Target / Value:** `<YOUR_COOLIFY_SERVER_IPV4>`
   - **TTL:** 300 seconds (or Automatic).
   - *If using Cloudflare:* Temporarily set Proxy status to **DNS Only** (grey cloud) during initial SSL issuance.
2. Confirm propagation from your terminal:
   ```bash
   nslookup astrology.yourdomain.com
   ```

---

## 4. Step 3: Deploy the Application

1. In Coolify: Click **+ New Resource** → **Application** → **Public/Private Git Repository**.
2. **Repository URL:** `https://github.com/Manish-10275/astrology-whatsapp.git`
3. **Branch:** `main`
4. **Build Pack:** **Dockerfile** (Coolify automatically detects the root `Dockerfile`).
5. In Application Settings:
   - **Ports Exposes:** `8000`
   - **Domains:** `https://astrology.yourdomain.com`
   - **Health Check Path:** `/health/live`
   - **Health Check Port:** `8000`

---

## 5. Step 4: Configure Environment Variables

In Coolify Application → **Environment Variables**, add the following:

```ini
# Core Environment
ENVIRONMENT=production
LOG_LEVEL=INFO

# Database Connection (Replace <password> and <db_internal_host> with your Coolify PostgreSQL credentials)
DATABASE_URL=postgresql+asyncpg://astrology_user:<password>@<db_internal_host>:5432/astrology_prod
DATABASE_SYNC_URL=postgresql+psycopg://astrology_user:<password>@<db_internal_host>:5432/astrology_prod

# Cryptography & Security (Generate locally using python -c "import secrets; print(secrets.token_hex(32))")
ENCRYPTION_PRIMARY_KEY=<64_hex_character_secret>
ENCRYPTION_KEY_VERSION=v1
JWT_SECRET_KEY=<32_plus_character_secret>
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60
PHONE_HASH_SALT=<64_hex_character_salt>
SCHEDULER_SECRET_TOKEN=<32_plus_character_secret>

# Concurrency & Scheduler Safety
ENABLE_BACKGROUND_SCHEDULER=false

# OpenAI LLM Integration (Inbound birth-chart interpretation)
OPENAI_API_KEY=sk-...your-actual-openai-key...
OPENAI_MODEL=gpt-4o-mini

# Deferred WhatsApp Integration (Leave unconfigured)
WHATSAPP_PHONE_NUMBER_ID=
WHATSAPP_ACCESS_TOKEN=
WHATSAPP_VERIFY_TOKEN=astrology-verify-token-change-me

# Curated Knowledge RAG (Disabled until corpus ingested)
RAG_ENABLED=false
```

Click **Save**.

---

## 6. Step 5: Initial Deploy, Migrations & Admin Seeding

1. Click **Deploy** in Coolify.
2. Monitor build logs. The container compiles `pysweph` dependencies and creates user `astrology:10001`.
3. Once the container is healthy (`/health/live` returns HTTP 200), open Coolify Application → **Terminal (Exec)**:
4. **Run Alembic Migrations:**
   ```bash
   # Container WORKDIR is /app/apps/api (or pass --config explicitly from any directory):
   python -m alembic upgrade head
   # Alternatively:
   python -m alembic --config /app/apps/api/alembic.ini upgrade head
   ```
5. **Provision Initial Super Admin:**
   ```bash
   python /app/deploy/scripts/seed_admin.py
   ```
   Follow the prompts for username, email, and password (minimum 12 characters).
6. Access your Admin Dashboard at `https://astrology.yourdomain.com/admin` and log in.

---

## 7. Verification & Upgrades

### Verification
- **Liveness Probe:** `curl https://astrology.yourdomain.com/health/live` → `{"status":"live"}`
- **Readiness Probe:** `curl https://astrology.yourdomain.com/health/ready` → `{"status":"ready","database":"connected"}`
- **Admin Dashboard Diagnostics:** Navigate to `/admin` → System Health to verify database connectivity and OpenAI configuration status.

### Upgrades
When new commits are pushed to `main`, trigger **Deploy** in Coolify (or configure Coolify Webhooks for automatic git push deployments). Run `python -m alembic upgrade head` in the Terminal if new migrations are present.

# Implementation Roadmap & Engineering Plan

**Document Version:** 1.0.0  
**Phase:** Phase 0 (Planning & Architecture)  
**Status:** Approved for Architectural Baseline  

---

## 1. Repository Structure (Production Monorepo)

The project is structured as a modular monorepo to ensure clean separation of concerns, shared type contracts, and independent scaling of services.

```
astrology-whatsapp-platform/
├── .github/
│   └── workflows/
│       ├── backend-ci.yml             # Pytest, Ruff lint, mypy typecheck
│       ├── frontend-ci.yml            # Next.js build, ESLint, Prettier
│       ├── ephemeris-benchmarks.yml   # Astronomical tolerance test suite
│       └── security-audit.yml         # Bandit, Semgrep, Trivy container scan
├── apps/
│   ├── api/                           # FastAPI Backend & Webhook Gateway
│   │   ├── src/
│   │   │   ├── core/                  # Config, logging, security, KMS
│   │   │   ├── db/                    # SQLAlchemy models, sessions
│   │   │   ├── ingress/               # WhatsApp webhook routes & HMAC guards
│   │   │   ├── llm/                   # Provider gateway, prompt templates
│   │   │   ├── state/                 # Conversation FSM & slot extractors
│   │   │   └── admin/                 # Admin API endpoints & RBAC guards
│   │   ├── tests/
│   │   ├── alembic/                   # Database migrations
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   ├── worker/                        # Background Task & Scheduler Engine
│   │   ├── src/
│   │   │   ├── jobs/                  # Inbound message processor, DLQ handler
│   │   │   ├── scheduler/             # Daily horoscope timezone scheduler
│   │   │   └── outbound/              # Meta Graph API sender & rate-limiter
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   └── dashboard/                     # Next.js Administrative Dashboard
│       ├── src/
│       │   ├── app/                   # App Router pages (Overview, Inspector, etc.)
│       │   ├── components/            # UI components (Shadcn UI, TraceModal)
│       │   ├── lib/                   # API client, auth, query hooks
│       │   └── types/                 # Frontend interfaces
│       ├── package.json
│       └── Dockerfile
├── packages/
│   ├── astrology-engine/              # Deterministic Calculation Engine
│   │   ├── src/
│   │   │   ├── ephemeris/             # pyswisseph wrapper & .se1 file loader
│   │   │   ├── vedic/                 # Lahiri, D1, D9, Nakshatras, Ashtakoota
│   │   │   ├── western/               # Tropical, Placidus, Synastry, Transits
│   │   │   ├── geo/                   # Geocoding & timezone resolution
│   │   │   └── models/                # Pydantic schemas (Contracts)
│   │   ├── ephem_data/                # Swiss Ephemeris data files (.se1)
│   │   ├── tests/                     # Astronomical precision unit tests
│   │   └── pyproject.toml
│   └── shared-types/                  # Shared JSON schemas & TypeScript types
├── deploy/
│   ├── docker-compose.yml             # Local multi-service environment
│   ├── docker-compose.override.yml
│   └── k8s/                           # Production Kubernetes manifests
├── docs/                              # Architectural documentation (Phase 0 deliverables)
├── .env.example
├── README.md
└── Makefile
```

---

## 2. Environment Configuration & Toolchain

### 2.1 Toolchain Standards
- **Python Backend & Worker:** Python 3.12+ (managed with `pyproject.toml` or `uv`).
- **Calculation Core:** `pyswisseph` (compiled with Swiss Ephemeris 2.10+).
- **Node.js Frontend:** Node.js 22+ LTS with `pnpm` or `npm`.
- **Database:** PostgreSQL 16 with `pgvector` extension.
- **Cache & Message Broker:** Redis 7.2 (with persistence enabled).
- **Formatting & Linting:** `ruff` (Python linting/formatting) and `biome` / `eslint` (TypeScript).
- **Static Typing:** `mypy --strict` (Python) and `tsc --noEmit` (TypeScript).

### 2.2 Environment Variables Matrix (`.env.example`)
```ini
# Application Core
ENVIRONMENT=development
LOG_LEVEL=INFO
SECRET_KEY=change-me-to-a-secure-random-string-in-production

# Meta WhatsApp Business Platform
META_APP_ID=your_meta_app_id
META_APP_SECRET=your_meta_app_secret
META_WEBHOOK_VERIFY_TOKEN=your_secure_verify_token
META_PHONE_NUMBER_ID=your_meta_phone_id
META_GRAPH_API_TOKEN=your_meta_system_user_token
META_API_VERSION=v19.0

# Database & Broker
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/astrology_platform
REDIS_URL=redis://localhost:6379/0

# LLM Providers
PRIMARY_LLM_PROVIDER=gemini # or anthropic / openai
GEMINI_API_KEY=your_gemini_api_key
ANTHROPIC_API_KEY=your_anthropic_api_key
OPENAI_API_KEY=your_openai_api_key

# Geocoding & Ephemeris
GOOGLE_MAPS_API_KEY=your_google_maps_key
EPHEMERIS_DATA_PATH=/app/packages/astrology-engine/ephem_data

# Admin Security
ADMIN_JWT_SECRET=admin-jwt-secret-key-32-bytes
ADMIN_SESSION_TTL_MINUTES=480
```

---

## 3. Implementation Phases & Completion Criteria

```mermaid
gantt
    title Astrology WhatsApp Platform — Development Phases
    dateFormat  YYYY-MM-DD
    section Phase 0
    Architecture & Planning       :done,    p0, 2026-10-23, 2026-10-24
    section Phase 1
    Deterministic Astro Engine    :active,  p1, 2026-10-25, 2026-11-04
    section Phase 2
    Data Layer & Admin Auth       :         p2, 2026-11-05, 2026-11-12
    section Phase 3
    LLM Orchestrator & FSM        :         p3, 2026-11-13, 2026-11-22
    section Phase 4
    WhatsApp Gateway & Webhook    :         p4, 2026-11-23, 2026-12-02
    section Phase 5
    Scheduled Horoscope Worker    :         p5, 2026-12-03, 2026-12-10
    section Phase 6
    Admin Dashboard (Next.js)     :         p6, 2026-12-11, 2026-12-20
    section Phase 7
    QA, Security & E2E Validation :         p7, 2026-12-21, 2026-12-30
```

### Phase 1: Core Astrological Calculation Engine (`packages/astrology-engine`)
- **Dependencies:** Swiss Ephemeris data files (`.se1`), Python 3.12, C-compiler.
- **Deliverables:**
  - `pyswisseph` integration module with thread-safe lock.
  - Vedic calculation module: Sidereal zodiac (Lahiri), D1 Rashi, D9 Navamsha, Vimshottari Dasha, Ashtakoota 36 Gunas, Manglik Dosha.
  - Western calculation module: Tropical zodiac, Placidus/Whole Sign houses, Ptolemaic cross-aspects, transit comparisons.
  - Geocoding and timezone resolution module (`timezonefinder` + `zoneinfo` + caching).
  - Pydantic models for all 4 core skill contracts.
- **Completion Criteria:** $100\%$ pass rate on astronomical benchmark test suite with $< 0.001$ arcsecond tolerance against Astrodienst references.

### Phase 2: Persistence Layer, Data Models & Admin Auth (`apps/api`)
- **Dependencies:** PostgreSQL 16, Redis 7.2.
- **Deliverables:**
  - SQLAlchemy async models matching `docs/data-model.md`.
  - Alembic migration scripts initializing tables, indices, and constraints.
  - PII encryption helper (AES-256-GCM envelope encryption).
  - Admin authentication API with JWT tokens and RBAC middleware.
- **Completion Criteria:** Migration scripts run cleanly up/down; PII encryption verifies that plain phone numbers never exist in database tables.

### Phase 3: Conversational State Machine & LLM Orchestrator
- **Dependencies:** Phase 1 (Engine), Phase 2 (DB), LLM API keys.
- **Deliverables:**
  - Finite State Machine (FSM) managing user lifecycle: Onboarding -> System Selection -> Birth Data Collection -> Ready.
  - Dynamic language detector and code-switching handler.
  - Tool routing engine executing Phase 1 astrology functions via structured JSON.
  - Anti-hallucination verification prompt and output assertion validator.
- **Completion Criteria:** Synthetic conversation simulator successfully extracts dates, executes calculations, and produces culturally accurate interpretations across English, Hindi, and Spanish.

### Phase 4: WhatsApp Ingress & Outbound Integration
- **Dependencies:** Phase 3 (Orchestrator), Meta WhatsApp Developer Account.
- **Deliverables:**
  - FastAPI webhook route receiving Meta events.
  - HMAC-SHA256 signature verification and fast HTTP 200 acknowledgment.
  - Redis-based `wamid` idempotency deduplication gate.
  - Meta Graph API outbound client supporting text, quick-reply buttons, and interactive lists.
- **Completion Criteria:** Successfully completes Meta webhook verification challenge; handles duplicate webhooks without duplicate messages; message delivery turnaround $< 4.0\text{s}$.

### Phase 5: Scheduled Background Workers & Horoscope Push Pipeline
- **Dependencies:** Phase 4, Redis Broker, ARQ / Celery worker.
- **Deliverables:**
  - Distributed background worker pool.
  - Timezone-aware morning horoscope scheduler (evaluates user local time 08:00 AM).
  - Meta Utility/Marketing Template dispatch for users outside 24h window.
  - Dead-Letter Queue (DLQ) and exponential backoff retry handler.
- **Completion Criteria:** Successfully processes 1,000 scheduled horoscope jobs across simulated timezones with zero duplicate dispatches and automatic DLQ routing for intentional failures.

### Phase 6: Internal Admin Dashboard (`apps/dashboard`)
- **Dependencies:** Phase 2 (Admin API), Node.js, Next.js 15.
- **Deliverables:**
  - System Health & Executive Overview screen.
  - Conversation Inspector with live trace viewer (Inbound message -> Intent -> Calc JSON -> LLM prompt -> Outbound text).
  - User & Birth Profile Management with GDPR/DPDP data wipe trigger.
  - Scheduled Horoscope Delivery Monitor.
  - Operational Error Console & Dead-Letter Queue viewer with one-click retry.
- **Completion Criteria:** Admin dashboard allows inspecting conversations and retrying failed jobs with zero manual database intervention.

### Phase 7: End-to-End Validation, Security & Soft Launch
- **Dependencies:** All preceding phases.
- **Deliverables:**
  - Full end-to-end integration tests (synthetic webhook to simulated WhatsApp client).
  - Security review (OWASP Top 10, prompt injection resistance, PII audit).
  - Load testing (50 concurrent webhook requests/sec sustained).
  - Astrological domain validation with 100 diverse birth charts reviewed by professional astrologers.
- **Completion Criteria:** Zero critical vulnerabilities, sub-second webhook ack, 100% calculation accuracy, approved for production deployment.

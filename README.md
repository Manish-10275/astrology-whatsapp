# Astrology WhatsApp AI Platform

A production-oriented, privacy-preserving astrological assistant operating over WhatsApp with an internal administration dashboard and deterministic astronomical calculation engine.

Designed from first principles to combine **high-precision deterministic astronomical calculations** (Vedic Jyotish and Western Tropical) with grounded conversational intelligence, privacy-by-design compliance (GDPR/DPDP), and zero-hallucination astrological outputs.

---

## 🌟 Key Capabilities

### 1. High-Precision Calculation Engine (`packages/astrology-engine`)
- **Deterministic Ephemeris Engine:** Powered by the Swiss Ephemeris (`pyswisseph`) with analytical Moshier fallback.
- **Vedic Astrology (Jyotish):**
  - Sidereal zodiac calculations with configurable Ayanamsas (Lahiri / Chitrapaksha, Raman, KP).
  - Whole Sign and Equal house systems.
  - Complete 27 Nakshatras and 108 Pada boundary allocations.
  - **Vimshottari Dasha:** 120-year cycle breakdown starting from natal Moon Nakshatra balance, with real-time active Mahadasha and Antardasha lookup.
  - **Vedic Panchang:** Real-time calculation of the 5 limbs: Tithi (30), Vara (Day + planetary lord), Nakshatra (27), Yoga (27), and Karana (60, including Vishti/Bhadra detection).
  - **Planetary Transits (Gochara):** Real-time Gochara positions relative to natal Moon and Ascendant, with active **Shani Sade Sati** phase identification (Rising, Peak, Setting) and Jupiter blessings.
  - **Navamsa (D9) Chart:** Continuous 108-step divisional chart computation with classical element-trikona starting rules and **Vargottama** planet detection.
  - **Ashtakoota (36-Guna) Compatibility:** Classical marriage matching across 8 Kootas (Varna, Vashya, Tara, Yoni, Graha Maitri, Gana, Bhakoot, Nadi) with classical dosha cancellations.
- **Western Astrology:**
  - Tropical zodiac positions and Placidus / Whole Sign houses.
  - Ptolemaic major aspects (Conjunction, Sextile, Square, Trine, Opposition) with harmonic orbs.
  - Elemental (Fire, Earth, Air, Water) and Modality (Cardinal, Fixed, Mutable) weighting.

### 2. Conversational WhatsApp Assistant (`apps/api`)
- **System Selection & Switching:** Users choose either Vedic or Western astrology during onboarding and can switch dynamically anytime (`/system western` or `switch to vedic`).
- **Interactive Multi-Turn Flows:**
  - **Onboarding:** Consent capture -> Date of Birth -> Time of Birth (with `UNKNOWN` handling) -> Place of Birth.
  - **Kundli Milan:** Multi-turn dialog collecting partner's birth date, time, and city, computing 36-Guna compatibility, doshas, and relationship guidance.
- **On-Demand Astrological Inquiries:**
  - Daily Horoscope ("daily horoscope", "aaj ka rashifal")
  - Active Dasha ("what is my current dasha")
  - Transits & Sade Sati ("current transits", "sade sati status")
  - Today's Panchang ("aaj ka panchang", "tithi today")
- **Multilingual Support:** Automatic language detection for English, Hindi (Devanagari script), and Hinglish (code-switching).
- **Daily Horoscope Scheduling & Proactive WhatsApp Templates:**
  - Conversational opt-in ("subscribe horoscope") and pause ("unsubscribe horoscope").
  - Idempotent batch runner (`dispatch_daily_horoscopes`) guaranteeing zero duplicate sends on the same calendar day.
  - Timezone-aware local delivery hour matching and concurrency locking.
  - Pre-approved Meta Message Templates support (`daily_horoscope_update`) for proactive 24-hr customer care window compliance.
  - Dual endpoint authentication: pre-shared `X-Scheduler-Token` or Admin JWT with `dashboard:trigger`.
  - Built-in async worker daemon toggle (`ENABLE_BACKGROUND_SCHEDULER`).

### 3. Privacy-by-Design & Security (`api.security`)
- **Zero Raw PII Storage:** Phone numbers are pseudonymized with HMAC-SHA256 (`phone_hash`) and encrypted at rest with AES-256-GCM.
- **Encrypted Birth Profiles & Messages:** Birth dates, times, coordinates, and conversation message histories are encrypted at rest with versioned keys and key-rotation support.
- **GDPR & DPDP Compliance:**
  - Affirmative consent tracking (`ConsentRecord`).
  - Right-to-Erasure atomic cascade deletion.
  - PII masking on all administrative views and log redaction.

### 4. Internal Admin Web Dashboard & Operational Controls (`/admin`)
- **Visual Web Dashboard (`/admin`):** Fully integrated, lightweight single-page operational dashboard served directly by FastAPI.
- **Role-Based Access Control (RBAC):** Super Admin, Support, Astrology QA, and Compliance roles with granular permissions.
- **Operational Metrics (`/api/v1/admin/dashboard/stats`):** Total users, active users, opt-in horoscope count, conversation/message volumes, astrology system and language distributions.
- **Conversation Traces (`/api/v1/admin/dashboard/conversations/{id}/trace`):** Authorized diagnostic inspection with decrypted previews and masked phone hashes.
- **Subsystem Diagnostics (`/api/v1/admin/dashboard/diagnostics`):** Real-time health status for PostgreSQL, Swiss Ephemeris, OpenAI, and WhatsApp.
- **Manual Batch Trigger (`/api/v1/schedules/daily-horoscopes/dispatch`):** Super Admin / secret-token endpoint for triggering daily horoscope dispatch batches.

---

## 🏗️ Architecture

```
astrology-whatsapp/
├── apps/
│   └── api/                         # FastAPI Backend Application
│       ├── alembic/                 # Database migrations (PostgreSQL 16)
│       ├── src/api/
│       │   ├── config.py            # Environment validation (fail-closed)
│       │   ├── db/                  # SQLAlchemy 2.0 async models
│       │   ├── routers/             # API routes
│       │   │   ├── admin_dashboard.py # Admin metrics, traces & diagnostics
│       │   │   ├── admin_users.py   # Admin user management
│       │   │   ├── auth.py          # Admin JWT authentication
│       │   │   ├── health.py        # Health & readiness probes
│       │   │   ├── privacy.py       # Consent & GDPR erasure
│       │   │   ├── schedules.py     # Horoscope dispatch endpoints
│       │   │   └── webhook_whatsapp.py # Meta webhook & state machine
│       │   ├── security/            # AES-256-GCM encryption, HMAC, RBAC, JWT
│       │   ├── services/            # WhatsApp templates, scheduler & grounding
│       │   └── static/admin/        # Built-in internal admin web dashboard SPA
│       └── tests/                   # 77 async API, template, scheduler & UI tests
├── packages/
│   └── astrology-engine/            # Deterministic Astronomical Package
│       ├── src/astrology_engine/
│       │   ├── adapter.py           # Thread-safe Swiss Ephemeris adapter
│       │   ├── chart.py             # D1 Chart calculation & hashing
│       │   ├── compatibility.py     # Ashtakoota 36-Guna matching
│       │   ├── dasha.py             # Vimshottari Mahadasha/Antardasha engine
│       │   ├── houses.py            # Placidus & Whole Sign house algorithms
│       │   ├── navamsa.py           # D9 Navamsa & Vargottama calculator
│       │   ├── panchang.py          # 5-limb Vedic Panchang calculator
│       │   ├── sidereal.py          # Sidereal planetary positions & Ayanamsas
│       │   ├── time_utils.py        # Julian Day & timezone resolution
│       │   ├── transits.py          # Gochara & Sade Sati analyzer
│       │   ├── tropical.py          # Tropical planetary positions
│       │   └── western.py           # Western Ptolemaic aspects & elements
│       └── tests/                   # 58 astronomical unit & benchmark tests
└── docs/                            # Specification & architecture documents
```

---

## 🚀 Getting Started

### Prerequisites
- **Python 3.12+**
- **PostgreSQL 16+**
- **Git**

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/Manish-10275/astrology-whatsapp.git
   cd astrology-whatsapp
   ```

2. **Create and activate virtual environment:**
   ```bash
   python -m venv .venv
   # Windows PowerShell:
   .venv\Scripts\Activate.ps1
   # Linux/macOS:
   source .venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -e packages/astrology-engine
   pip install -e apps/api
   ```

4. **Environment Configuration:**
   Copy the example environment file and configure local credentials:
   ```bash
   cp .env.example .env
   ```
   Required variables:
   ```env
   ENVIRONMENT=development
   DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/astrology_dev
   DATABASE_SYNC_URL=postgresql+psycopg://postgres:postgres@localhost:5432/astrology_dev
   ENCRYPTION_PRIMARY_KEY=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
   ENCRYPTION_KEY_VERSION=v1
   JWT_SECRET_KEY=your-jwt-secret-key-minimum-32-chars-long
   PHONE_HASH_SALT=your-phone-hash-salt-32-chars-long
   WHATSAPP_VERIFY_TOKEN=your-meta-verify-token
   WHATSAPP_APP_SECRET=your-meta-app-secret
   ```

5. **Run Database Migrations:**
   ```bash
   cd apps/api
   alembic upgrade head
   cd ../..
   ```

6. **Start the API Server:**
   ```bash
   uvicorn api.main:app --reload --port 8000
   ```
   Interactive Swagger API docs available at `http://localhost:8000/docs`.

---

## 🧪 Testing & Verification

The test suite runs against an isolated PostgreSQL test database (`astrology_test`) and tests all astronomical calculations, state machines, and API security.

### Run Calculation Engine Tests (58 tests)
```bash
pytest packages/astrology-engine/tests/ -v
```

### Run API & Integration Tests (60 tests)
```bash
pytest apps/api/tests/ -v
```

### Run Full Test Suite (118 tests)
```bash
pytest packages/astrology-engine/tests/ apps/api/tests/ -q
```
**Status: 118 passed in 100% clean test runs.**

---

## 🔒 Security & Privacy Standard
- **Fail-Closed Principle:** Application startup and request pipelines fail immediately if encryption keys, database connections, or HMAC tokens are invalid.
- **Zero Ephemeral LLM Inventions:** All signs, nakshatras, houses, dashas, transits, and compatibility scores are mathematically generated by `astrology_engine` before any language generation takes place.
- **Log Hygiene:** Plaintext phone numbers, passwords, JWT secrets, and birth details are permanently redacted from application logs.

---

## 📜 License
Internal & Proprietary — All rights reserved.

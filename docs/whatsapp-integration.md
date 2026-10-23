# WhatsApp Cloud API Integration & Live Testing Guide

This guide describes how to configure, verify, test, and run the WhatsApp Cloud API integration for the Astrology WhatsApp AI Platform.

---

## 1. Architecture & Security Overview

```
                                  +──────────────────────────────+
                                  | Meta WhatsApp Cloud Platform |
                                  +──────────────┬───────────────+
                                                 │
                        1. Inbound POST webhook  │ 4. Outbound Graph API POST
                        (X-Hub-Signature-256)    │ (/v21.0/{phone_id}/messages)
                                                 ▼
+────────────────────────────────────────────────────────────────────────────+
| FastAPI Application (apps/api)                                              |
|                                                                            |
| 1. Webhook Signature Check: HMAC-SHA256(raw_body, WHATSAPP_APP_SECRET)     |
| 2. Idempotency Check: In-memory + DB message ID deduplication              |
| 3. Conversational State Machine:                                            |
|    ONBOARDING_CONSENT ──► AWAITING_BIRTH_DATE ──► AWAITING_BIRTH_TIME ──►  |
|    ──► AWAITING_BIRTH_PLACE ──► READING_READY (Active Reading)             |
|                                                                            |
| 4. Astrology Calculation Engine (packages/astrology-engine):               |
|    Deterministic planetary calculations (Swiss/Moshier ephemeris, Lahiri)  |
|                                                                            |
| 5. AI Grounding & Interpretation (api.services.astrology_service):         |
|    Strict prompt grounding on verified facts; zero planetary hallucinations|
|    Deterministic template fallback when OPENAI_API_KEY is not configured   |
|                                                                            |
| 6. Encrypted Persistence (api.security.encryption):                        |
|    AES-256-GCM authenticated encryption for all conversation messages     |
|    and birth profiles; SHA-256 phone pseudonymization.                     |
+────────────────────────────────────────────────────────────────────────────+
```

---

## 2. Meta App Dashboard Configuration

### Step 1: Create or Open Your Meta App
1. Navigate to [Meta for Developers](https://developers.facebook.com/).
2. Open your Business App with the **WhatsApp** product added.
3. Under **WhatsApp > API Setup**:
   - Note the **Phone number ID**.
   - Generate or obtain a **Permanent System User Access Token** with permissions:
     - `whatsapp_business_messaging`
     - `whatsapp_business_management`

### Step 2: Configure Webhook
1. Under **WhatsApp > Configuration**:
   - Click **Edit** next to Webhook.
   - **Callback URL**: `https://<your-public-domain>/api/v1/webhook/whatsapp`
   - **Verify Token**: Must match your `WHATSAPP_VERIFY_TOKEN` (configured in `.env`).
   - Click **Verify and save**. Meta will immediately send a `GET` request with `hub.mode=subscribe` and `hub.challenge`.
2. Under **Webhook fields**:
   - Click **Manage**.
   - Subscribe to the **`messages`** field.

### Step 3: Retrieve App Secret
1. In Meta Developer Dashboard, go to **App settings > Basic**.
2. Click **Show** next to **App secret**.
3. Set this value as `WHATSAPP_APP_SECRET` in your environment.

---

## 3. Environment Variables Configuration

In `apps/api/.env`:

```bash
# Environment Mode
ENVIRONMENT=development
LOG_LEVEL=INFO

# PostgreSQL (Persistence Layer)
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/astrology_dev
DATABASE_SYNC_URL=postgresql+psycopg://postgres:postgres@localhost:5432/astrology_dev

# Cryptographic Keys (AES-256-GCM)
ENCRYPTION_PRIMARY_KEY=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
ENCRYPTION_KEY_VERSION=v1
JWT_SECRET_KEY=your-secure-jwt-secret-min-32-chars-long-here
PHONE_HASH_SALT=your-phone-hash-salt-min-32-chars-long-here

# WhatsApp Cloud API Credentials
WHATSAPP_PHONE_NUMBER_ID=100000000000000
WHATSAPP_ACCESS_TOKEN=EAAB...your_system_user_token_here
WHATSAPP_VERIFY_TOKEN=your_custom_webhook_verify_token_here
WHATSAPP_APP_SECRET=your_meta_app_secret_hex_here
WHATSAPP_API_VERSION=v21.0

# LLM / AI Orchestration (Optional for local testing; fallback template used if unset)
OPENAI_API_KEY=sk-proj-...
OPENAI_MODEL=gpt-4o-mini
```

---

## 4. Local Testing with ngrok or Cloudflare Tunnel

Because Meta requires a public HTTPS URL to deliver webhooks, use a tunnel for local development:

### Using ngrok:
```bash
# 1. Start the FastAPI backend
.venv\Scripts\python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload --app-dir apps/api/src

# 2. In a separate terminal, expose port 8000
ngrok http 8000
```

Copy the HTTPS forwarding address (e.g., `https://abc1-23-45.ngrok-free.app`) and configure it in the Meta Dashboard:
`https://abc1-23-45.ngrok-free.app/api/v1/webhook/whatsapp`

### Using Cloudflare Tunnel (Alternative):
```bash
cloudflared tunnel --url http://localhost:8000
```

---

## 5. End-to-End Conversational Flow Walkthrough

Once configured, send a WhatsApp message to your WhatsApp Business phone number:

1. **Turn 1 (Greeting & Affirmative Consent Prompt)**:
   - *User*: "Hi, I'd like an astrology reading"
   - *Assistant*: "Welcome to the Astrology Assistant! 🌟 I provide personalized astrological readings grounded in high-precision astronomical calculations (Vedic and Western). Before we begin, do you consent to the secure storage and processing of your birth details (date, time, place) to calculate your astrological chart? Please reply *YES* to agree and begin, or *NO* to decline."
2. **Turn 2 (Consent Granted)**:
   - *User*: "YES"
   - *Assistant*: "Thank you! Your consent has been recorded securely under GDPR/DPDP guidelines. 🔒 Let's create your authentic birth chart: 1️⃣ What is your date of birth? (Please reply in YYYY-MM-DD format, e.g., 1995-10-24)"
3. **Turn 3 (Birth Date)**:
   - *User*: "1995-10-24"
   - *Assistant*: "Got it! Date of birth: 24 October 1995. 2️⃣ What time were you born? (Please reply in 24-hour HH:MM format like 14:30 or 08:15 AM. If you do not know your exact birth time, simply reply *UNKNOWN*)."
4. **Turn 4 (Birth Time)**:
   - *User*: "14:30" (or "UNKNOWN")
   - *Assistant*: "Noted! Birth time: 02:30 PM. 3️⃣ Where were you born? (Please reply with the city and country, for example: Mumbai, India or London, UK)"
5. **Turn 5 (Birthplace & Reading)**:
   - *User*: "New Delhi, India"
   - *Assistant*: Delivers the authentic Kundli reading containing:
     - Ascendant (Lagna) sign, degree, and Nakshatra
     - Moon sign (Chandra Rashi), Nakshatra, and Pada
     - Sun sign (Surya Rashi)
     - Key planetary signatures and strengths
     - *(If birth time was UNKNOWN, Lagna and houses are withheld with clear explanation, while planetary signs remain 100% accurate).*

---

## 6. Privacy & Consent Revocation

- **Revocation at Any Time**: The user can message `"revoke consent"`, `"delete my data"`, or `"delete data"` at any point during or after onboarding. The system immediately:
  - Sets `revoked_at` timestamp on active `ConsentRecord`.
  - Resets the conversational state back to `ONBOARDING_CONSENT`.
  - Refuses further birth data processing until affirmative consent is re-granted.
- **Right to Erasure (GDPR Article 17 / DPDP Section 12)**: The user or admin can invoke the erasure endpoint `/api/v1/privacy/users/{user_id}/erasure` to atomically delete all associated records, conversations, and birth profiles.

---

## 7. Running Automated Verification

To run all 46 API tests (including Meta challenge verification, HMAC signature validation, deduplication, and multi-turn conversational flow):

```bash
.venv\Scripts\python -m pytest apps/api/tests/ -v
```

To run all 32 calculation engine verification tests:

```bash
.venv\Scripts\python -m pytest packages/astrology-engine/tests/ -v
```

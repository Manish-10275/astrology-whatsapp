# Technical Risks, Architectural Decisions & Technology Evaluation

**Document Version:** 1.0.0  
**Phase:** Phase 0 (Planning & Architecture)  
**Status:** Approved for Architectural Baseline  

---

## 1. Evaluation of Initial Technology Proposal

We have critically reviewed the initial technology proposal rather than accepting it unconditionally:

| Proposed Component | Architectural Verdict | Detailed Assessment & Recommendations |
| :--- | :--- | :--- |
| **Frontend: Next.js & TypeScript** | **APPROVED WITH CLARIFICATIONS** | **Strengths:** Next.js (App Router) provides server-side rendering, strong TypeScript typing, and fast developer velocity with UI component libraries (Tailwind / Shadcn UI). Perfect for an internal administrative dashboard.<br>**Trade-off/Guardrail:** The end-user never touches this frontend (they use WhatsApp). Keep the dashboard lightweight and isolated in `apps/dashboard`. Avoid over-engineering complex SSR features for internal tools. |
| **Backend: Python & FastAPI** | **APPROVED UNANIMOUSLY** | **Strengths:** FastAPI offers native async/await for high-throughput webhook handling, Pydantic v2 for sub-millisecond serialization and strict schema contracts, and direct in-process access to astronomical C-libraries (`pyswisseph`) and AI/LLM SDKs without inter-process IPC overhead. |
| **Database: PostgreSQL 16** | **APPROVED UNANIMOUSLY** | **Strengths:** The industry gold standard for ACID transactional integrity, relational joins across users, birth charts, and message traces, rich JSONB support for calculation payloads, and rock-solid indexing. |
| **Semantic Retrieval: pgvector** | **CONDITIONALLY APPROVED (Measured Scope)** | **Strengths:** Enables semantic similarity searches for astrological reference interpretations directly inside Postgres without requiring an external vector DB (Pinecone/Milvus).<br>**Caution/Decision:** For the MVP, deterministic calculations and prompt context are the primary drivers. Avoid premature over-indexing on RAG. Use `pgvector` specifically for retrieving curated interpretations of complex planetary combinations rather than general conversation recall. |
| **Background Jobs: Durable Solution** | **APPROVED: Redis + ARQ / Celery** | **Strengths:** Redis with persistent append-only file (AOF) paired with **ARQ** (asyncio-native, lightweight) or **Celery** handles webhook offloading and scheduled morning horoscope queues.<br>**Recommendation:** Prefer **ARQ** for native Python async concurrency and lower overhead than Celery, with a dedicated APScheduler / cron container for triggering timezone-aware morning batches. |
| **WhatsApp: Official Cloud API** | **APPROVED WITH POLICY CONTROLS** | **Strengths:** Meta WhatsApp Cloud API provides direct access, lowest per-conversation fees, rich interactive buttons, and high message throughput.<br>**Critical Caveat:** Strictly enforce the 24-hour customer service window rule. Scheduled daily horoscopes outside this window **must** use pre-approved Meta Utility/Marketing templates. |
| **Astrology: Validated Ephemeris** | **APPROVED: Swiss Ephemeris (`pyswisseph`)** | **Strengths:** Swiss Ephemeris is the undisputed international standard for planetary computation, used by Astrodienst, Astro-Seek, and professional astrologers worldwide.<br>**License Notice:** Swiss Ephemeris is dual-licensed under AGPLv2 or a commercial license from Astrodienst. For closed-source commercial deployments, purchasing an Astrodienst commercial license (~CHF 700) or isolating the calculation module behind a network boundary is mandatory. |
| **LLM: Provider-Independent Gateway** | **APPROVED: Clean Gateway Pattern** | **Strengths:** Decoupling via LiteLLM or an internal Provider Gateway prevents vendor lock-in and enables intelligent fallbacks (e.g., Gemini 2.5 Flash as primary high-speed router with Claude 3.5 Sonnet for deep synthesis, and GPT-4o-mini as failover). |
| **Testing Strategy** | **APPROVED WITH EXPANSION** | **Requirement:** Standard unit/integration testing must be augmented with **Astronomical Tolerance Tests** (asserting degrees match reference ephemerides within 0.001 arcseconds) and a **Synthetic Webhook Replay Suite** simulating Meta webhook delivery and network retries. |

---

## 2. Technical Risk Matrix & Mitigation Strategies

```
+----------------------------------------------------------------------------------------------------+
|                                    RISK SEVERITY & IMPACT MATRIX                                   |
+---------------------+-------------------+-------------------+--------------------------------------+
| RISK IDENTIFIER     | PROBABILITY       | IMPACT            | MITIGATION STRATEGY                  |
+---------------------+-------------------+-------------------+--------------------------------------+
| R-01: 24h Window    | HIGH              | HIGH              | Enforce template fallback for all    |
| Blockage (Meta)     |                   | (Failed Delivery) | morning pushes; prompt user reply.   |
+---------------------+-------------------+-------------------+--------------------------------------+
| R-02: LLM Hallucina-| MEDIUM            | CRITICAL          | Zero LLM calculation rule; automated |
| tion of Placements  |                   | (User Trust Loss) | verification guardrail against JSON. |
+---------------------+-------------------+-------------------+--------------------------------------+
| R-03: Webhook Storm | MEDIUM            | HIGH              | Fast 200 OK (<500ms) + Redis queue;  |
| & Duplicate Retries |                   | (Double Messages) | atomic wamid idempotency gate.       |
+---------------------+-------------------+-------------------+--------------------------------------+
| R-04: Ephemeris C-  | LOW               | CRITICAL          | Pre-built Docker container with      |
| Extension Platform  |                   | (Build Failure)   | compiled C-extensions & test suite.  |
+---------------------+-------------------+-------------------+--------------------------------------+
| R-05: PII & Data    | LOW               | CRITICAL          | AES-256 field encryption, pseudonym- |
| Privacy Violations  |                   | (Legal / GDPR)    | ization, 1-click atomic data wipe.   |
+---------------------+-------------------+-------------------+--------------------------------------+
```

### Risk Details & Actionable Pre-Implementation Validation:

#### Risk 1: WhatsApp 24-Hour Messaging Window & Template Rejections
- **The Danger:** If a user doesn't message the bot for 24 hours, the free-form window closes. If the scheduled morning horoscope is sent as free-form text, Meta returns error code `131026` or drops the message. If the template is rejected by Meta reviewers, daily deliveries fail.
- **Validation Before Code:** Submit 2 candidate WhatsApp templates (`daily_horoscope_update`) to Meta Business Manager during Phase 1 to verify approval and category classification (*Utility* vs *Marketing*).

#### Risk 2: Astrological Hallucinations (Placing Planets in Wrong Signs/Houses)
- **The Danger:** LLMs tend to generate convincing astrological prose but will fabricate degrees, signs, or compatibility scores if given latitude.
- **Validation Before Code:** The prompt architecture must inject the verified Swiss Ephemeris calculation JSON as an immutable system artifact. Implement a strict post-generation AST/regex parser in Python that verifies mentioned planet-sign pairings match the JSON before outbound dispatch.

#### Risk 3: Ephemeris License & Binary Compilation
- **The Danger:** `pyswisseph` wraps Astrodienst C code. Compiling on diverse OS environments (Windows vs Linux vs macOS ARM) can introduce compilation hurdles, and AGPLv2 licensing has strict copyleft terms.
- **Validation Before Code:** Validate `pyswisseph` installation and `.se1` ephemeris file access in the Linux Docker runtime immediately in Phase 1; confirm Astrodienst commercial license requirements with legal counsel.

#### Risk 4: Geocoding Ambiguities & Timezone DST Shifts
- **The Danger:** A user enters "Springfield" without state, or a historic birth in 1944 occurred during War Time Daylight Saving in the US or historic British Double Summer Time. Incorrect timezone offsets cause a 1-hour error, altering the Ascendant by ~15 degrees (often changing the Rising Sign).
- **Validation Before Code:** Use IANA `zoneinfo` and Python `timezonefinder` validated against historic benchmarks. When location resolution yields multiple matches, the conversation state machine must trigger a disambiguation prompt.

---

## 3. Cost Analysis & Driver Estimates

| Cost Driver | Monthly Unit Cost | Expected MVP Scale (1,000 MAU) | Optimization Strategy |
| :--- | :--- | :--- | :--- |
| **Meta WhatsApp Conversations** | Service: Free (1,000 free service convos/mo). Utility: ~$0.015 - $0.035 / convo. Marketing: ~$0.04 - $0.08 / convo. | ~$30 - $75 / month | Prioritize user-initiated interactions; bundle daily horoscope into utility category. |
| **LLM Inference** | Gemini 2.5 Flash: $0.075 / 1M input tokens, $0.30 / 1M output tokens.<br>Claude 3.5 Sonnet: $3.00 / 1M input, $15.00 / 1M output. | ~$15 - $50 / month | Use fast, low-cost model (Gemini 2.5 Flash / GPT-4o-mini) for intent routing; reserve high-reasoning model for complex synthesis; cache system prompts. |
| **Geocoding API** | Photon/Geonames: Free self-hosted.<br>Google Maps: $5.00 per 1,000 requests (after $200 free tier). | $0.00 (within free tiers) | Aggressively cache resolved coordinates and timezones in Postgres `birth_profiles` and Redis. |
| **Infrastructure Hosting** | Cloud VPS (PostgreSQL, Redis, Worker, FastAPI) | ~$40 - $80 / month | Single-box Docker Compose deployment for staging; managed Postgres (AWS RDS / Supabase) for production. |
| **TOTAL ESTIMATED MVP OPEX** | — | **~$85 – $205 / month** | Extremely lean and cost-effective. |

---

## 4. Prioritized List of Questions Requiring Stakeholder Decision

The following decisions require your confirmation before Phase 1 implementation begins:

### Priority 1: Meta WhatsApp Business Account (WABA) Access
- **Question:** Do you currently have a verified Meta Business Account with WhatsApp Cloud API access, or should we prepare local webhook simulation tooling (e.g., ngrok + WhatsApp mock runner) for Phase 1 development?
- **Impact:** Decides whether Phase 1 tests against live Meta phone numbers or automated synthetic webhook harness.

### Priority 2: Swiss Ephemeris Commercial License vs Microservice Boundary
- **Question:** Astrodienst Swiss Ephemeris is AGPLv2 open-source or commercial license (~CHF 700). Should we purchase an Astrodienst commercial license, or architect the calculation module as an isolated, standalone microservice?
- **Impact:** Ensures intellectual property compliance for commercial distribution.

### Priority 3: Primary LLM Provider Preference
- **Question:** Do you have a preferred primary LLM provider (Google Gemini, Anthropic Claude, or OpenAI), or should we configure the provider gateway to default to **Gemini 2.5 Flash** for its exceptional speed and cost efficiency, with Claude 3.5 Sonnet as fallback for complex synthesis?
- **Impact:** Establishes default API keys and prompt tuning benchmarks.

### Priority 4: Geocoding Service Selection
- **Question:** Would you prefer using Google Maps Geocoding API (highest accuracy, paid with monthly credit) or an open-source solution (Photon / OpenStreetMap / Geonames cache) with Google as a secondary fallback?
- **Impact:** Geocoding latency, external billing dependency, and accuracy on smaller towns.

### Priority 5: Default House System for Western Astrology
- **Question:** Should Western astrology default to **Placidus** (standard modern Western practice) or **Whole Sign** (popular in Hellenistic and traditional astrology)?
- **Recommendation:** Default to Placidus with an instant setting toggle to Whole Sign.

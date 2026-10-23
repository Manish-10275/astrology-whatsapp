# Requirements Specification — Astrology WhatsApp AI Platform

**Document Version:** 1.0.0  
**Phase:** Phase 0 (Planning & Architecture)  
**Status:** Approved for Architectural Baseline  

---

## 1. Executive Summary & Product Vision

The Astrology WhatsApp AI Platform is an enterprise-grade, automated, multilingual astrological consultation service delivered through WhatsApp. The platform combines mathematically exact, verified astronomical ephemeris computations with modern Large Language Model (LLM) orchestration to provide culturally nuanced, personalized astrological insights.

The platform supports both **Vedic (Jyotish)** and **Western (Tropical)** astrological traditions, automatically adapts to the user's conversational language (including code-switching such as Hinglish or Spanglish), operates under strict data-privacy standards (GDPR, India DPDP Act), and provides operational observability through an internal administrative dashboard.

---

## 2. Product Requirements Baseline

### 2.1 Functional Requirements (FR)

| ID | Capability | Description | Priority |
| :--- | :--- | :--- | :--- |
| **FR-01** | **WhatsApp Conversational Interface** | Users interact exclusively with the platform via WhatsApp Business Platform (Cloud API), supporting text, interactive buttons, list messages, and media (chart diagrams). | P0 (MVP) |
| **FR-02** | **Astrology System Onboarding** | During onboarding, users select either **Vedic** or **Western** astrology. The choice is stored in their profile and configures all downstream calculations. | P0 (MVP) |
| **FR-03** | **System Preference Switching** | Users can change their preferred astrology system at any time via conversational intent ("Switch to Western", "Use Vedic from now on") or menu command. | P0 (MVP) |
| **FR-04** | **Automatic Language Detection & Code-Switching** | The system automatically detects incoming message language and dialect, responding in the matching language. It handles code-switching (e.g., mixing English and Hindi, English and Spanish) naturally. | P0 (MVP) |
| **FR-05** | **Explicit Language Override** | Users can explicitly specify their preferred language (e.g., "Reply in Spanish", "Hindi please") which overrides automatic detection. | P1 (MVP) |
| **FR-06** | **Birth Profile Capture & Resolution** | Collects Date of Birth (YYYY-MM-DD), Time of Birth (HH:MM 12/24h), and Place of Birth (City, Country). Resolves location to geographic coordinates (Lat/Long) and historical IANA Timezone. | P0 (MVP) |
| **FR-07** | **Birth-Time Uncertainty Handling** | If exact birth time is unknown, the platform provides fallback interpretations (Solar chart in Western, Chandra Kundali/Surya Kundali in Vedic) and informs the user about limitations (houses/ascendant unavailable). | P0 (MVP) |
| **FR-08** | **Privacy Consent & Data Controls** | Requires explicit user consent before storing birth profile and conversational data. Provides commands for instant data export and full profile deletion ("DELETE MY DATA"). | P0 (MVP) |
| **FR-09** | **Core Skill: Birth-Chart Generation & Interpretation** | Computes deterministic natal planetary coordinates, houses, signs, and aspects/dashas. Generates personalized interpretations explaining personality, strengths, life path, and challenges. | P0 (MVP) |
| **FR-10** | **Core Skill: Daily Horoscopes** | Delivers daily astrological insights. Supports two modes: (a) Personalized daily transits against the user's natal chart, and (b) General Moon/Sun sign horoscope if birth details are incomplete. | P0 (MVP) |
| **FR-11** | **Scheduled Horoscope Delivery** | Allows users to subscribe to daily scheduled horoscopes delivered at their preferred local morning time. Requires WhatsApp-compliant template messaging when outside the 24h window. | P0 (MVP) |
| **FR-12** | **Core Skill: Compatibility Matching** | Calculates relationship compatibility between two birth profiles: (a) Vedic Ashtakoota (36 Gunas) + Manglik Dosha, or (b) Western Synastry cross-aspects + element/modality balance. | P0 (MVP) |
| **FR-13** | **Core Skill: Transit-Based Interpretations** | Calculates current or future planetary transits relative to the natal chart (Vedic Gochara & Sade Sati; Western outer-planet transits to natal points). | P0 (MVP) |
| **FR-14** | **Deterministic Astrology Engine** | All planetary coordinates, houses, nakshatras, dashas, aspects, and synastry scores must be computed by a verified astronomical engine (Swiss Ephemeris). The LLM is strictly prohibited from calculating or hallucinating coordinates. | P0 (MVP) |
| **FR-15** | **LLM Semantic Orchestration** | An LLM is used exclusively for intent routing, slot extraction (birth dates/places), synthesizing astrological calculations into natural prose, answering follow-up questions, and managing conversation tone. | P0 (MVP) |
| **FR-16** | **Internal Administrative Dashboard** | A secure web portal for operators to monitor system health, inspect conversation traces (prompt, calculation JSON, response), view errors, manage users, and review feedback. | P0 (MVP) |
| **FR-17** | **Fail-Safe Fallbacks & Observability** | Automatic error isolation. If an LLM or calculation fails, the user receives an empathetic fallback response while an alert and dead-letter trace are recorded in the admin dashboard. | P0 (MVP) |

---

### 2.2 Non-Functional Requirements (NFR)

| ID | Category | Requirement | Target Metric |
| :--- | :--- | :--- | :--- |
| **NFR-01** | **Webhook Latency** | Initial acknowledgment of WhatsApp webhook requests. | `< 2.0s` (Meta timeout is 15s; 2s ensures no duplicate webhooks) |
| **NFR-02** | **End-to-End Response Time** | Time from user message arrival to WhatsApp response delivery. | Simple query: `< 3.5s`<br>Complex chart/transit synthesis: `< 7.0s` |
| **NFR-03** | **Calculation Accuracy** | Planetary positions and house cusps must match Swiss Ephemeris reference calculations. | `< 0.001` arcsecond error tolerance |
| **NFR-04** | **Availability** | Webhook listener and database availability. | `99.9%` uptime outside planned maintenance |
| **NFR-05** | **Idempotency** | Duplicate WhatsApp webhook deliveries (same `wamid`) must be suppressed. | 100% duplicate suppression via distributed cache/DB constraint |
| **NFR-06** | **Data Minimization & Encryption** | Phone numbers encrypted or hashed; PII encrypted at rest using AES-256; TLS 1.3 in transit. | Zero raw PII in operational logs |
| **NFR-07** | **Privacy Compliance** | Full compliance with EU GDPR, UK GDPR, and India Digital Personal Data Protection Act (DPDP) 2023. | Deletion SLA `< 24 hours` upon user request |
| **NFR-08** | **Language Support** | Full fluency in English, Hindi, Spanish, French, German, and Portuguese, plus common code-switched dialects (Hinglish). | Language detection accuracy `> 95%` |
| **NFR-09** | **Scalability** | Asynchronous worker architecture capable of scaling horizontally. | Baseline: 50 concurrent messages/sec; 10,000 scheduled morning pushes over 30 mins |
| **NFR-10** | **Rate Limiting** | Protection against bot flooding and abuse on WhatsApp webhook endpoints. | Max 10 messages/minute per phone number; Global API rate limiting |

---

## 3. Scope Definition

```
+-----------------------------------------------------------------------------------+
|                                  PROJECT SCOPE                                    |
+---------------------------------------------------+-------------------------------+
|                    IN SCOPE                       |         OUT OF SCOPE          |
|                     (MVP)                         |        (MVP EXCLUSIONS)       |
+---------------------------------------------------+-------------------------------+
| - WhatsApp Cloud API text & interactive messages  | - Payment processing & tiers  |
| - Vedic (Lahiri/Chitrapaksha) & Western (Placidus)| - Monetization / Subscriptions|
| - Swiss Ephemeris deterministic calculation engine| - Voice note transcription/TTS|
| - Auto language detection & code-switching        | - Live human astrologer chat  |
| - 4 core skills (Chart, Horoscope, Matching, Tr.) | - Secondary progressions /    |
| - Location geocoding & historical timezone lookup |   Solar Arc directions        |
| - Daily scheduled horoscope delivery (worker)     | - Third-party mobile/web apps |
| - Internal Next.js admin dashboard & trace viewer | - Astrological gem / talisman |
| - Data consent, profile management, and deletion  |   e-commerce integration      |
+---------------------------------------------------+-------------------------------+
```

### 3.1 Future Enhancements (Post-MVP Roadmap)
- **Phase 2 (Monetization & Voice):** Stripe/Razorpay integration for premium in-depth readings; WhatsApp audio message support (Whisper input + ElevenLabs/Gemini speech synthesis).
- **Phase 3 (Advanced Astrology):** KP Astrology (Krishnamurti Paddhati), Jaimini Chara Dasha, Western Secondary Progressions, Composite charts, Astro-cartography.
- **Phase 4 (Live Consultation):** Seamless human astrologer handoff queue in the admin dashboard for complex life queries.

---

## 4. Measurable Acceptance Criteria

### AC-01: Onboarding & Astrology System Selection
- **Scenario:** First-time user sends "Hi".
- **Given** an unregistered phone number sends any inbound greeting.
- **When** the message is processed by the webhook.
- **Then** the system must reply within 3 seconds with a welcoming message and interactive selection buttons: `[ Vedic (Jyotish) ]` and `[ Western ]`.
- **And** prompt the user to confirm consent for birth data storage according to privacy policy.

### AC-02: Preference Switching
- **Scenario:** Existing Vedic user requests Western reading.
- **Given** a user configured with Vedic astrology sends "Can I switch to Western astrology?"
- **When** the intent router processes the message.
- **Then** the user's `astrology_system` setting in the database is updated to `western`.
- **And** the bot confirms the switch and briefly highlights the difference (e.g., Tropical zodiac vs Sidereal zodiac).

### AC-03: Language Detection & Code-Switching
- **Scenario:** Multilingual query.
- **Given** an existing user sends "Mera aaj ka horoscope kaisa rahega? Career me koi problem toh nahi aayegi?" (Hinglish).
- **When** the LLM orchestrator processes the intent and calculation.
- **Then** the response must be generated in natural Hinglish matching the tone and phrasing of the user.
- **And** astrological concepts must be contextualized (e.g., using terms like "shani", "career", "dasha").

### AC-04: Core Skill 1 — Birth Chart Generation & Interpretation
- **Scenario:** Valid birth data provided.
- **Given** birth input `1992-08-15`, `14:30`, `Mumbai, India`.
- **When** the birth chart tool executes.
- **Then** the deterministic engine must resolve Mumbai to `18.9388° N, 72.8354° E`, timezone `Asia/Kolkata` (UTC+5:30).
- **And** return exact planetary positions: Sun in Leo/Cancer (depending on Western/Vedic), Moon sign, Ascendant/Lagna, and Nakshatra/House cusps.
- **And** the LLM must synthesize these calculated placements into a readable summary (Core strengths, emotional disposition, career inclination) without hallucinating uncalculated placements.

### AC-05: Core Skill 2 — Daily Horoscopes & Scheduled Delivery
- **Scenario:** On-demand and scheduled daily delivery.
- **Given** a user with a verified birth profile requests "What does today look like for me?"
- **When** the daily horoscope tool executes.
- **Then** the engine computes the transiting planets for current date relative to the user's natal placements (e.g., Moon transit house, major aspects).
- **And** if the user opts into daily delivery at 08:00 AM, a background scheduler creates a recurring job.
- **And** if outside the 24-hour WhatsApp messaging window, the message is dispatched using an approved WhatsApp Utility/Marketing template.

### AC-06: Core Skill 3 — Compatibility Matching
- **Scenario:** Two birth profiles compared.
- **Given** User Profile A (`1990-05-12, Delhi`) and Partner Profile B (`1992-11-20, Pune`) in Vedic mode.
- **When** compatibility matching runs.
- **Then** the engine executes the 8 Kootas (Varna, Vashya, Tara, Yoni, Graha Maitri, Gana, Bhakoot, Nadi) computing a score out of 36.
- **And** checks for Manglik Dosha for both profiles.
- **And** the LLM formats the breakdown with constructive relationship guidance.
- **And** in Western mode, computes cross-aspects (Synastry: Sun-Moon, Venus-Mars, Saturn ties) with orb tolerances.

### AC-07: Core Skill 4 — Transit Interpretation
- **Scenario:** Specific planetary query ("When does my Sade Sati end?" or "How is Saturn transit affecting my career?").
- **Given** a user birth chart and a transit query.
- **When** the transit tool executes.
- **Then** the engine calculates Saturn's current sidereal/tropical position relative to the natal Moon/Sun.
- **And** provides precise start/peak/end dates based on ephemeris transit dates, with zero fabricated dates.

### AC-08: Data Deletion & Privacy Compliance
- **Scenario:** User requests data wipe.
- **Given** an active user sends "Delete all my data" or "Remove my account".
- **When** the intent router identifies the deletion request.
- **Then** the system requests confirmation ("Are you sure? This will delete your birth chart and conversation history.").
- **And** upon user confirmation ("Yes, delete"), all birth profiles, message history, and subscriptions are hard-deleted or anonymized within 60 seconds.
- **And** a final confirmation message is sent to WhatsApp before terminating the session.

---

## 5. Unresolved Product Decisions & External Dependencies

| Category | Item | Options / Trade-offs | Required Decision Owner |
| :--- | :--- | :--- | :--- |
| **WhatsApp Provider** | Meta Cloud API Direct vs BSP (Twilio / MessageBird / Gupshup) | **Option A: Direct Meta Cloud API.** Lower cost per conversation, requires handling raw webhooks, template approvals, and WABA setup.<br>**Option B: BSP.** Higher cost per message, simpler onboarding and SDKs. *Recommendation: Direct Meta Cloud API for long-term margins.* | Product / Engineering Lead |
| **Ephemeris Library** | Swiss Ephemeris (`pyswisseph`) Licensing | Swiss Ephemeris is AGPLv2 or requires a commercial license from Astrodienst for closed-source commercial deployments. *Recommendation: Purchase Astrodienst commercial license or run as an isolated calculation microservice.* | Legal / Executive Lead |
| **Geocoding Provider** | Google Maps Geocoding API vs Photon / OpenStreetMap Nominatim | **Option A: Google Maps.** High accuracy, global coverage, paid per request.<br>**Option B: Geonames Cache + Photon/Nominatim.** Open-source, free/self-hostable, slightly lower coverage for obscure villages. *Recommendation: Photon/Geonames with Google Maps fallback.* | Engineering Lead |
| **LLM Provider Strategy** | Anthropic Claude vs OpenAI GPT-4o vs Google Gemini | Provider-agnostic abstraction (via LiteLLM or clean gateway interface). *Recommendation: Fast model (Gemini 2.5 Flash / GPT-4o-mini) for routing; High-reasoning model (Claude 3.5 Sonnet / GPT-4o) for complex chart synthesis.* | AI Systems Engineer |
| **Vedic Ayanamsa Default** | Lahiri vs Krishnamurti (KP) vs Raman | Lahiri (Chitrapaksha) is standard across 85% of Indian practitioners and Indian government ephemeris. *Recommendation: Default to Lahiri (Swiss Ephemeris ID 1).* | Astrology Domain Specialist |
| **Western House System** | Placidus vs Whole Sign | Placidus is standard in modern Western astrology; Whole Sign is preferred in Hellenistic. *Recommendation: Default to Placidus with Whole Sign toggle.* | Astrology Domain Specialist |
| **Out-of-Window Messaging** | Scheduled morning horoscope template costs | Meta charges for Utility/Marketing templates initiated outside the 24h user window. *Decision: Require explicit opt-in and budget for Meta conversation fees.* | Product / Finance Lead |

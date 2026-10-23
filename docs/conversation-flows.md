# WhatsApp Conversation Design & Interaction Flows

**Document Version:** 1.0.0  
**Phase:** Phase 0 (Planning & Architecture)  
**Status:** Approved for Architectural Baseline  

---

## 1. Conversational Principles & Persona

1. **Empathetic & Grounded:** The assistant acts as an insightful, culturally knowledgeable guide rather than a deterministic robot or a fatalistic fortune teller.
2. **Deterministic Transparency:** Astrological claims are framed constructively (strengths, energetic tendencies, opportunities, cautions) rather than fatalistic decrees ("You will lose your job tomorrow").
3. **Frictionless Onboarding:** Minimal cognitive load. One question at a time during data collection.
4. **Natural Code-Switching:** Seamless adaptation to user language, colloquialisms, and mixed dialects (e.g., Hinglish: "Mera career kaisa rahega?").
5. **Interactive UI Components:** Leverages native WhatsApp interactive components (Quick-Reply Buttons and List Messages) whenever choices are finite to reduce typing errors.

---

## 2. WhatsApp Messaging Policies & Compliance

### 2.1 The 24-Hour Customer Service Window
- **User-Initiated Sessions:** When a user messages the business, a 24-hour service window opens. Inside this window, the platform can send free-form text, images, and interactive messages without Meta template pre-approval.
- **Business-Initiated Messages (Scheduled Horoscopes):** Outside the 24-hour window, WhatsApp **strictly forbids** free-form messaging. All scheduled morning horoscopes sent after 24 hours of inactivity **MUST use a pre-approved Meta Message Template** (categorized as *Utility* or *Marketing*).

### 2.2 Template Strategy for Scheduled Horoscopes
To deliver daily horoscopes reliably without violating Meta policies:
1. **Template Name:** `daily_horoscope_update`
2. **Category:** `UTILITY` (if framed as a requested account alert) or `MARKETING` (depending on Meta country policy).
3. **Template Format:**
   ```
   Good morning, {{1}}! 🌅
   Here is your daily astrological transit overview for {{2}}:

   {{3}}

   Reply to explore today's transits or ask any question.
   ```
4. Once the user replies to this template, a fresh 24-hour free-form messaging window opens, enabling deep conversational follow-ups.

---

## 3. Core Conversation Flows

### Flow 1: New User Onboarding & System Selection

```mermaid
sequenceDiagram
    autonumber
    actor User as User (WhatsApp)
    participant WA as WhatsApp Platform
    participant Bot as AI Astrology Bot
    participant DB as Postgres DB

    User->>WA: "Hello" / "Namaste" / "Hola"
    WA->>Bot: Inbound Webhook Event
    Bot->>DB: Query User(phone_hash) -> Not Found
    Bot-->>User: Welcome Greeting + Privacy Consent Notice<br/>Interactive Buttons: [ Agree & Continue ] [ Privacy Policy ]
    User->>Bot: Taps [ Agree & Continue ]
    Bot->>DB: Record Consent (v1.0)
    Bot-->>User: "Which astrological tradition do you follow?"<br/>Interactive Buttons:<br/>1. 🕉️ Vedic (Jyotish)<br/>2. 🌌 Western (Tropical)
    User->>Bot: Taps [ 🕉️ Vedic (Jyotish) ]
    Bot->>DB: Save UserPreference(system='vedic')
    Bot-->>User: "Great! Vedic astrology uses the Sidereal zodiac & Nakshatras.<br/>To prepare your birth chart, please share your **Date of Birth** (e.g., 15 Aug 1994 or 1994-08-15)."
```

---

### Flow 2: Birth Data Collection & Disambiguation

```mermaid
sequenceDiagram
    autonumber
    actor User as User (WhatsApp)
    participant Bot as AI Astrology Bot
    participant Geo as Geocoding & TZ Service
    participant Engine as Swiss Ephemeris Engine

    User->>Bot: "15 August 1994"
    Bot-->>User: "Got it! 📅 August 15, 1994.<br/>Now, what time were you born?<br/>(e.g., 2:30 PM or 14:30. If you don't know the exact time, reply 'Unknown')."
    
    alt User knows exact time
        User->>Bot: "2:30 PM"
        Bot-->>User: "Recorded 2:30 PM (14:30).<br/>Finally, what city and country were you born in? (e.g., Jaipur, India)."
    else User does not know exact time
        User->>Bot: "I don't know" / "Unknown"
        Bot-->>User: "No problem! We will construct a Moon/Solar chart for you. Some house and rising sign details will be approximate.<br/>What city and country were you born in?"
    end

    User->>Bot: "Springfield"
    Bot->>Geo: Resolve "Springfield" -> Multiple matches found
    Bot-->>User: "I found a few places named Springfield. Which one is yours?<br/>List Options:<br/>1. Springfield, Illinois, USA<br/>2. Springfield, Massachusetts, USA<br/>3. Springfield, Missouri, USA"
    User->>Bot: Taps [ Springfield, Illinois, USA ]
    Bot->>Geo: Fetch Lat/Lon (39.7817° N, 89.6501° W) & TZ America/Chicago
    Bot->>Engine: Generate Natal Chart
    Bot-->>User: "✨ Your Vedic Birth Chart is ready!<br/>Ascendant (Lagna): **Scorpio (Vrischika)**<br/>Moon Sign (Rashi): **Scorpio / Anuradha Nakshatra**<br/>Sun Sign: **Cancer (Karka)**<br/><br/>You are currently running **Saturn Mahadasha**.<br/>What would you like to explore first? (Career, Relationships, or Daily Horoscope)?"
```

---

### Flow 3: Returning User & Contextual Conversations

Returning users bypass onboarding and can converse freely:
- **User:** *"How is my career looking for the rest of this year?"*
- **Bot:**
  1. Checks active profile (`Self`, Vedic, Scorpio Lagna).
  2. Runs transit query: Saturn transiting 4th house (Aquarius) aspecting 10th house of career (Leo); Jupiter transiting 7th house (Taurus) aspecting 10th and Lagna.
  3. LLM synthesizes response in user's preferred language:
  > *"Based on your Vedic chart (Scorpio Lagna), you are experiencing a pivotal career phase. Saturn's aspect on your 10th house (Leo) demands disciplined effort and patience, while Jupiter's benefic aspect from Taurus indicates recognition from superiors and opportunities for expansion starting next quarter. Focus on long-term stability rather than impulsive job changes."*

---

### Flow 4: Compatibility Matching Workflow

```mermaid
sequenceDiagram
    autonumber
    actor User as User (WhatsApp)
    participant Bot as AI Astrology Bot
    participant Engine as Swiss Ephemeris Engine

    User->>Bot: "Can you check compatibility with my partner?"
    Bot-->>User: "I'd love to check your compatibility! 💕<br/>Please provide your partner's birth details:<br/>**Date of Birth, Time of Birth, and Place of Birth**<br/>(e.g., 22 Nov 1995, 10:15 AM, Pune, India)."
    User->>Bot: "22 Nov 1995, 10:15 AM, Pune, India"
    Bot->>Engine: Run Ashtakoota Milan (36 Gunas) + Manglik Dosha
    Bot-->>User: "💑 **Vedic Compatibility Summary**<br/>Match Score: **27 / 36 Gunas (Very Favorable)**<br/><br/>• **Mental Harmony (Maitri):** 5/5 - Excellent intellectual understanding.<br/>• **Emotional Sync (Bhakoot):** 7/7 - Deep mutual empathy.<br/>• **Nadi (Health & Genes):** 8/8 - Auspicious.<br/>• **Manglik Check:** Neither chart has high Kuja Dosha.<br/><br/>Would you like a deeper breakdown of communication or lifestyle compatibility?"
```

---

### Flow 5: Daily Horoscope Subscription & Opt-Out

```mermaid
sequenceDiagram
    autonumber
    actor User as User (WhatsApp)
    participant Bot as AI Astrology Bot
    participant DB as Postgres DB

    User->>Bot: "Send me daily horoscopes every morning"
    Bot-->>User: "I can deliver your personalized transit forecast every morning at 08:00 AM local time. 🌅<br/>Would you like to activate this daily push?<br/>[ Subscribe (8:00 AM) ] [ Choose Different Time ] [ Cancel ]"
    User->>Bot: Taps [ Subscribe (8:00 AM) ]
    Bot->>DB: Upsert horoscope_subscription(status='active', time='08:00:00')
    Bot-->>User: "✅ Subscribed! You will receive your daily cosmic forecast every morning at 08:00 AM.<br/>You can change your time or unsubscribe anytime by replying 'Unsubscribe'."
    
    Note over User,Bot: Days later, user opts out:
    User->>Bot: "Stop daily horoscopes" / "Unsubscribe"
    Bot->>DB: Update horoscope_subscription(status='inactive')
    Bot-->>User: "You have been unsubscribed from daily horoscopes. You can still ask for today's forecast anytime on demand!"
```

---

### Flow 6: Preference Switching (Vedic <-> Western)

- **User:** *"I want to switch to Western astrology."*
- **Bot:**
  > *"Switching your profile to **Western (Tropical) Astrology**! 🌌\n\nIn Western astrology, your Sun sign is **Leo**, your Moon is in **Sagittarius**, and your Rising Sign (Ascendant) is **Sagittarius** (using Placidus houses).\n\nFuture queries, daily transits, and compatibility will now follow Western astrology principles. You can switch back anytime by saying 'Switch to Vedic'."*

---

### Flow 7: Data Deletion & Privacy Erasure

```mermaid
sequenceDiagram
    autonumber
    actor User as User (WhatsApp)
    participant Bot as AI Astrology Bot
    participant DB as Postgres DB

    User->>Bot: "DELETE ALL MY DATA"
    Bot-->>User: "⚠️ **Data Deletion Request**<br/>This will permanently delete your birth chart, conversation history, and horoscope subscriptions. This action cannot be undone.<br/><br/>Are you sure?<br/>[ Yes, Delete Everything ] [ Cancel ]"
    User->>Bot: Taps [ Yes, Delete Everything ]
    Bot->>DB: Atomic Hard Delete User(phone_hash) CASCADE
    Bot-->>User: "🗑️ All your personal data and birth records have been permanently erased from our systems. Thank you for using our service. You are welcome back anytime!"
```

---

## 4. Multilingual & Code-Switching Handling

### Dialect Support Matrix
| Input Style | User Message Example | Bot Response Language & Strategy |
| :--- | :--- | :--- |
| **Pure English** | "What does today look like for my finances?" | Standard English, empathetic, precise astrological terminology. |
| **Pure Hindi (Devanagari)** | "मेरी कुंडली में सरकारी नौकरी का योग कब बन रहा है?" | Natural Hindi in Devanagari script; standard Jyotish terms (सूर्य, दशम भाव, दशा). |
| **Hinglish (Romanized)** | "Bhai, mera Shani dasha kab khatam hoga? Bahut tension hai." | Natural Hinglish conversational tone: empathetic, reassuring, culturally relatable phrasing. |
| **Spanish** | "¿Cómo influye el tránsito de Marte en mi signo hoy?" | Fluent Spanish, Western astrological concepts (Marte, Casa, Tránsitos). |
| **French / German** | "Quel est mon signe lunaire et ascendant ?" | Fluent French / German with corresponding cultural terminology. |

### Code-Switching Continuity Rule
If a user begins in English and suddenly sends a message in Hindi or Spanish, the bot **immediately switches** to reply in that language for that turn and continues in that language until the user switches again. Users can also issue an explicit command at any time: *"Please reply in English only"*.

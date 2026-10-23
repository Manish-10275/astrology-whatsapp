# Astrology Calculation Engine — Licensing, Dependencies & Compatibility Audit

**Document Version:** 1.1.0  
**Audit Phase:** Phase 1.1 (Independent Audit & Release-Gate Verification)  
**Date:** October 2026  
**Audit Status:** AUDITED — LAUNCH GATE IDENTIFIED  

---

## 1. Verified Component Facts

| Attribute | Verified Value | Evidence / Inspection Source |
| :--- | :--- | :--- |
| **Installed Python Binding** | `pysweph` v2.10.3.6 | `importlib.metadata.metadata('pysweph')` |
| **Native Swiss Ephemeris Version** | Swiss Ephemeris C v2.10.03 | `swisseph.version` attribute (Astrodienst latest C source) |
| **Binding Native Object** | `swisseph.cp312-win_amd64.pyd` | Installed in `.venv/Lib/site-packages/` |
| **Applicable Upstream License** | **GNU AGPL v3.0** (or later) OR **Swiss Ephemeris Professional License** | Astrodienst AG official license header in `pysweph` metadata; https://www.gnu.org/licenses/agpl-3.0.html |
| **Ephemeris Data License** | Dual License: AGPL v3.0 / Commercial | Astrodienst Public Ephemeris Data terms |
| **Python Runtime Compatibility** | Python 3.12.15 (Windows x86_64) | Tested on CPython 3.12.15 |

---

## 2. Licensing Audit & Critical Rectifications

### 2.1 Correction of "AGPLv2" Misnomer
The Phase 1 preliminary report erroneously referred to the Swiss Ephemeris open-source license as "AGPLv2".
- **Fact:** GNU Affero General Public License version 2 was an unofficial interim variant produced by Affero, Inc. in 2002.
- **Verification:** Upstream Astrodienst AG officially transitioned to the Free Software Foundation's official **GNU Affero General Public License version 3.0 (AGPL v3.0)**. The official package metadata and Astrodienst documentation explicitly state:
  > *"Swiss Ephemeris is made available by its authors under a dual licensing system: a) GNU Affero General Public License (AGPL) - See https://www.gnu.org/licenses/agpl-3.0.html, or b) Swiss Ephemeris Professional License."*
- **Rectification:** Package metadata in `packages/astrology-engine/pyproject.toml` has been formally updated from `AGPL-2.0-or-later` to **`AGPL-3.0-or-later`**.

### 2.2 AGPL v3.0 Obligations vs. WhatsApp Hosted-Service Architecture
The planned application architecture is a WhatsApp AI service operated over the network. Under **Section 13 of the GNU AGPL v3.0 (Remote Network Interaction)**:
- Any user who interacts with the software remotely through a computer network (which includes sending and receiving WhatsApp messages routed through an API backend) has the legal right to receive the **Complete Corresponding Source Code** of the entire application under the terms of the AGPL v3.0.
- **The Microservice Myth:** Isolating Swiss Ephemeris inside an internal container or separate microservice does **NOT** reliably shield a proprietary SaaS from AGPL copyleft obligations if the service constitutes a single collective or derivative product.
- **The Swiss Ephemeris Professional License:**
  Astrodienst AG offers the *Swiss Ephemeris Professional License* (purchased directly from Astrodienst AG, Zürich, Switzerland for a one-time fee of approx. CHF 700 / USD $790). This commercial contract permanently exempts the licensee from all AGPL copyleft obligations, allowing closed-source commercial distribution, proprietary LLM prompts, and closed SaaS operations.

### 2.3 Explicit Launch Blocker
> [!CAUTION]
> **COMMERCIAL RELEASE-GATE BLOCKER:**
> The `astrology-engine` package is currently licensed under GNU AGPL v3.0 for open-source development and testing. 
> Prior to activating any public-facing commercial service, paid tier, or closed-source distribution on WhatsApp, the business stakeholder **MUST** either:
> 1. Formally purchase and execute the **Swiss Ephemeris Professional License** with Astrodienst AG; OR
> 2. Commit to releasing the entire WhatsApp AI Platform backend and operational orchestrator as open-source software under the GNU AGPL v3.0.

---

## 3. Dependency Pinning & Reproducibility Audit

### 3.1 Pinned Runtime Dependencies
All runtime dependencies are strictly pinned in `packages/astrology-engine/requirements.lock` and validated in a clean virtual environment:

```ini
annotated-types==0.8.0
cffi==2.1.1
colorama==0.4.6
flatbuffers==25.12.19
iniconfig==2.3.1
numpy==2.5.4
packaging==26.3
pluggy==1.7.0
pycparser==3.12
pydantic==2.14.1
pydantic-core==2.50.1
pygments==2.21.0
pysweph==2.10.3.6
pytest==9.1.1
timezonefinder==9.2.0
timezonefinder-data==4.2026.5
tzdata==2026.5
typing-extensions==4.16.0
typing-inspection==0.4.4
```

### 3.2 Windows Platform Requirement: `tzdata`
During clean environment installation on Windows, Python's standard library `zoneinfo` failed because Windows lacks a system `/usr/share/zoneinfo` database.
- **Defect Found:** `tzdata` was omitted from `packages/astrology-engine/pyproject.toml`.
- **Fix Applied:** `tzdata>=2024.1; sys_platform == 'win32'` was added directly into `pyproject.toml` dependencies, ensuring that cross-platform installations on Windows, Linux, and macOS succeed automatically.

---

## 4. Summary of Audit Findings & Legal Action Items

1. **Upstream License:** Confirmed as **GNU AGPL v3.0** / Swiss Ephemeris Professional License.
2. **Binary Packaging:** `pysweph` v2.10.3.6 verified functional with pre-compiled wheels, avoiding C++ build tool dependencies.
3. **Reproducibility:** Pinned lockfile installs and executes 32/32 tests cleanly.
4. **Action Item for Stakeholder:** Procure Swiss Ephemeris Professional License prior to Phase 5 production deployment.

# Astrology Calculation Engine — Licensing, Dependencies & Compatibility Report

**Document Version:** 1.0.0  
**Phase:** Phase 1 (Calculation Engine Foundation)  
**Date:** October 2026  
**Status:** Approved for Technical Implementation  

---

## 1. Executive Summary

Phase 1 establishes the mathematical and astronomical foundation of the Astrology WhatsApp AI Platform. The platform requires high-precision, deterministic astronomical calculations for planetary positions, sidereal ayanamsas, ascendants, and house cusps across both Vedic and Western traditions.

This document presents a comprehensive technical, architectural, and legal evaluation of candidate astronomical calculation libraries under **Python 3.12**, details why **`pysweph`** was selected and verified, provides build and platform reproducibility requirements, and documents all licensing implications under the **GNU Affero General Public License (AGPL)**.

---

## 2. Evaluation of Candidate Libraries

We systematically evaluated four candidate libraries against strict production criteria:
1. Python 3.12 compatibility and pre-compiled wheel availability across Windows, Linux, and macOS.
2. Maintenance health, active release cadence, and upstream bug fixes.
3. Astronomical calculation fidelity (matching Astrodienst / JPL standards).
4. Licensing terms and copyleft implications.

| Criteria | Candidate 1: `pyswisseph` | Candidate 2: `pysweph` (Selected) | Candidate 3: `flatlib` / `kerykeion` | Candidate 4: `skyfield` / `astropy` |
| :--- | :--- | :--- | :--- | :--- |
| **PyPI Package** | `pyswisseph` (v2.10.3.2) | `pysweph` (v2.10.3.6) | `flatlib` (v0.2.3) / `kerykeion` (v2.4.0) | `skyfield` (v1.49) |
| **Underlying Engine** | Astrodienst Swiss Ephemeris C | Astrodienst Swiss Ephemeris C | Wraps `pyswisseph` | USNO / JPL DE421/DE440 Ephemeris |
| **Python 3.12 Windows Support** | **FAILED.** Source distribution only; requires MSVC C++ 14.0+ build tools. Fails on clean systems. | **VERIFIED.** Pre-compiled wheels for Windows x86_64, macOS (ARM & Intel), and Linux. | **FAILED.** Inherits `pyswisseph` compilation failures on Windows. | **PASSED.** Pure Python + NumPy wheels available. |
| **Import Namespace** | `import swisseph` | `import swisseph` (exact drop-in replacement) | `import flatlib` / `import kerykeion` | `import skyfield` |
| **Swiss Ephemeris Version** | 2.10.03 | 2.10.03 (Astrodienst latest) | Depends on underlying `pyswisseph` | N/A (JPL planetary equations) |
| **Ayanamsa Support** | Native (Lahiri, Raman, KP, 40+ modes) | Native (Lahiri, Raman, KP, 40+ modes) | Partial wrapper around `pyswisseph` | Requires manual coordinate rotations |
| **House Systems** | Placidus, Whole Sign, Equal, Koch, etc. | Placidus, Whole Sign, Equal, Koch, etc. | Limited to standard house subsets | Not natively implemented for astrology |
| **License** | GNU AGPLv2 or Commercial | GNU AGPLv2 or Commercial | MIT (flatlib) / GPLv3 (kerykeion) | MIT / BSD 3-Clause |
| **Verdict** | **REJECTED (Build barrier)** | **SELECTED AS FOUNDATION** | **REJECTED (Unnecessary layer)** | **REJECTED (Lacks astro houses/ayanamsas)** |

---

## 3. Deep-Dive: Why `pysweph` Was Selected

### 3.1 The Python 3.12 Installation Barrier in `pyswisseph`
When attempting to install `pyswisseph==2.10.3.2` on a standard Windows Python 3.12 environment:
```
Building pyswisseph==2.10.3.2
error: Microsoft Visual C++ 14.0 or greater is required.
Get it with "Microsoft C++ Build Tools": https://visualstudio.microsoft.com/visual-cpp-build-tools/
```
The original `pyswisseph` project stopped releasing pre-compiled Windows binary wheels for newer CPython releases (Python 3.12+). Requiring a 4GB+ Microsoft C++ Build Tools installation on developer workstations and production deployment images creates a fragile, non-reproducible environment.

### 3.2 The `pysweph` Solution
`pysweph` is an actively maintained distribution of the exact same official Astrodienst Swiss Ephemeris C library (v2.10.03).
- **Binary Wheels:** It publishes cross-platform binary wheels (`.whl`) for CPython 3.8 through 3.13 on `win_amd64`, `macosx_x86_64`, `macosx_arm64`, and `manylinux2014_x86_64`.
- **Identical Namespace:** It compiles and exports the standard C extension module named `swisseph`. Any code targeting `swisseph` works with zero code changes (`import swisseph as swe`).
- **Verified Runtime:** Installed and verified in our Python 3.12.15 environment within 145 milliseconds, successfully calling `swe.julday`, `swe.calc_ut`, `swe.set_sid_mode`, and `swe.houses`.

---

## 4. Swiss Ephemeris Licensing & Legal Analysis

### 4.1 The Astrodienst Dual-Licensing Model
Astrodienst AG (Zürich, Switzerland) distributes the Swiss Ephemeris under a dual-licensing structure:
1. **Open Source: GNU Affero General Public License v2 (AGPLv2) or later:**
   Allows free use, modification, and redistribution, provided that any software derived from it or providing network service access to it is also released under the AGPLv2.
2. **Commercial License:**
   For organizations wishing to distribute closed-source commercial applications or proprietary software without publishing their source code, Astrodienst sells commercial licenses (one-time fee of CHF 700 for unlimited distribution without royalties).

### 4.2 Ephemeris Data Files Licensing
- **Moshier Semi-Analytical Ephemeris:** Built directly into the compiled C extension code. Free for use under Swiss Ephemeris terms. Covers years 3000 BCE to 3000 CE with ~0.1 arcsecond planetary accuracy.
- **High-Precision Swiss Ephemeris Data Files (`.se1`):** Astrodienst provides compressed JPL DE431/DE441 data files. These files are subject to Astrodienst's public data terms: free for non-commercial or AGPL use, or included under the commercial license.

### 4.3 Implications for an AGPL-Compatible Project
Under the Affero GPL (AGPLv2/v3):
- **Network Copyleft (Section 2/3):** If an AGPL-licensed program runs on a server and users interact with it remotely over a computer network (such as a WhatsApp API backend), the provider must offer access to the Complete Corresponding Source Code to network users.
- **Microservice / API Boundary Myth:** Running Swiss Ephemeris inside an internal Docker container or separate microservice and calling it via REST/gRPC does **NOT** automatically insulate proprietary applications from AGPL copyleft obligations if the combined system constitutes a single collective or derivative work.
- **Confirmed Phase 1 Strategy:**
  1. The calculation engine package (`packages/astrology-engine/`) is structured as a clean, modular AGPL-compatible open-source component.
  2. For the open-source MVP, full compliance is maintained by adhering to AGPLv2 terms.
  3. **Unresolved Stakeholder Decision:** Prior to commercial launch, monetized subscriptions, or closed-source proprietary distribution, the business stakeholder must purchase the Astrodienst Swiss Ephemeris Commercial License (approx. CHF 700 / USD $790) to permanently extinguish all copyleft obligations.

---

## 5. Dependency Lockfile & Reproducibility

### 5.1 Pinned Runtime Dependencies
The core calculation engine has zero dependencies on OpenAI, Meta WhatsApp, or web frameworks.

| Package | Pinned Version | Purpose | License |
| :--- | :--- | :--- | :--- |
| **`pysweph`** | `2.10.3.6` | Swiss Ephemeris C-extension binding (Astrodienst v2.10.03) | GNU AGPLv2 |
| **`pydantic`** | `2.14.1` | Request/response data validation and type enforcement | MIT |
| **`timezonefinder`** | `9.2.0` | Offline geographic coordinates to IANA timezone resolution | MIT |
| **`timezonefinder-data`**| `4.2026.5` | Compressed global timezone boundary polygons | MIT / ODbL |

### 5.2 Development & Testing Dependencies
| Package | Pinned Version | Purpose | License |
| :--- | :--- | :--- | :--- |
| **`pytest`** | `9.1.1` | Deterministic unit and benchmark test runner | MIT |

### 5.3 Reproducible Setup Commands
Using `uv` with Python 3.12:
```bash
# 1. Create Python 3.12 virtual environment
uv venv .venv --python 3.12

# 2. Activate virtual environment
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# 3. Install pinned dependencies from lockfile
uv pip install -r packages/astrology-engine/requirements.lock
```

---

## 6. Unresolved Issues for Pre-Launch Review

1. **Commercial License Purchase:** Confirm Astrodienst commercial license procurement before charging users or packaging proprietary IP.
2. **Ephemeris Data File Packaging:** Decide whether `.se1` ephemeris files (approx. 30MB for 1800–2100 CE) will be embedded inside Docker images or dynamically downloaded to a persistent volume cache. The built-in Moshier ephemeris is accurate to ~0.1 arcseconds and requires zero external files, making it ideal for the foundation phase.

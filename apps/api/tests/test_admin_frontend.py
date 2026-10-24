"""Tests for internal admin frontend static file serving, DOM elements, and security headers."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_admin_dashboard_html_served(client: AsyncClient):
    """Verifies that /admin serves the HTML dashboard with essential DOM containers."""
    resp = await client.get("/admin")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")

    html = resp.text
    # Verify core application containers exist
    assert "Admin Dashboard — Astrology WhatsApp Assistant" in html
    assert 'id="login-view"' in html
    assert 'id="dashboard-view"' in html
    assert 'id="conversations-table"' in html
    assert 'id="trace-modal"' in html
    assert 'id="trigger-scheduler-btn"' in html
    assert 'id="confirm-modal"' in html
    assert 'id="conversation-search"' in html
    assert 'data-section="overview"' in html
    assert 'data-section="users"' in html
    assert 'data-section="conversations"' in html
    assert 'data-section="horoscopes"' in html
    assert 'data-section="compatibility"' in html
    assert 'data-section="diagnostics"' in html
    assert 'data-section="settings"' in html


@pytest.mark.asyncio
async def test_admin_dashboard_security_headers(client: AsyncClient):
    """Verifies that the admin dashboard sets defensive security headers."""
    resp = await client.get("/admin")
    assert resp.status_code == 200

    # Anti-clickjacking
    assert resp.headers.get("x-frame-options") == "DENY"
    # Anti-MIME confusion
    assert resp.headers.get("x-content-type-options") == "nosniff"
    # Referrer privacy
    assert resp.headers.get("referrer-policy") == "strict-origin-when-cross-origin"


@pytest.mark.asyncio
async def test_admin_static_assets_served(client: AsyncClient):
    """Verifies that CSS and JS assets are served correctly from /admin/assets/."""
    # 1. CSS asset
    resp_css = await client.get("/admin/assets/admin.css")
    assert resp_css.status_code == 200
    assert "text/css" in resp_css.headers.get("content-type", "")
    assert ".login-card" in resp_css.text
    assert "--color-sky: #78B9E8" in resp_css.text
    assert "--color-cream: #FAF7F0" in resp_css.text
    assert "--color-slate: #243746" in resp_css.text
    assert "prefers-reduced-motion" in resp_css.text

    # 2. JS asset
    resp_js = await client.get("/admin/assets/admin.js")
    assert resp_js.status_code == 200
    assert ("javascript" in resp_js.headers.get("content-type", "") or
            "application/javascript" in resp_js.headers.get("content-type", "") or
            "text/plain" in resp_js.headers.get("content-type", ""))
    assert "TOKEN_KEY" in resp_js.text
    assert "/admin/auth/login" in resp_js.text
    assert "/admin/auth/me" in resp_js.text
    assert "/admin/dashboard/stats" in resp_js.text
    assert "/admin/dashboard/diagnostics" in resp_js.text

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

    # 2. JS asset
    resp_js = await client.get("/admin/assets/admin.js")
    assert resp_js.status_code == 200
    assert ("javascript" in resp_js.headers.get("content-type", "") or
            "application/javascript" in resp_js.headers.get("content-type", "") or
            "text/plain" in resp_js.headers.get("content-type", ""))
    assert "TOKEN_KEY" in resp_js.text

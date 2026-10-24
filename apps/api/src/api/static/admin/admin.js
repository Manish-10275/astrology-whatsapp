/**
 * Admin Dashboard Client Logic - Astrology WhatsApp Assistant
 * Minimalist Sky Blue & Warm Cream Flat 2D Interface
 * 
 * Interacts with authenticated backend APIs:
 * - POST /api/v1/admin/auth/login
 * - GET  /api/v1/admin/auth/me
 * - GET  /api/v1/admin/dashboard/stats
 * - GET  /api/v1/admin/dashboard/diagnostics
 * - GET  /api/v1/admin/dashboard/conversations
 * - GET  /api/v1/admin/dashboard/conversations/{id}/trace
 * - POST /api/v1/admin/dashboard/schedules/trigger
 */

const API_BASE = '/api/v1';
const TOKEN_KEY = 'astrology_admin_jwt';

// State
let currentUser = null;
let autoRefreshTimer = null;

// DOM Elements: Views
const loginView = document.getElementById('login-view');
const dashboardView = document.getElementById('dashboard-view');

// DOM Elements: Authentication
const loginForm = document.getElementById('login-form');
const loginBtn = document.getElementById('login-btn');
const loginError = document.getElementById('login-error');
const logoutBtn = document.getElementById('logout-btn');
const refreshBtn = document.getElementById('refresh-btn');
const adminUsername = document.getElementById('admin-username');
const adminRoleBadge = document.getElementById('admin-role-badge');
const toastEl = document.getElementById('toast');
const togglePasswordBtn = document.getElementById('toggle-password-btn');
const passwordInput = document.getElementById('password');

// DOM Elements: Sidebar & Navigation
const sidebar = document.getElementById('sidebar');
const sidebarToggleBtn = document.getElementById('sidebar-toggle-btn');
const sidebarCloseBtn = document.getElementById('sidebar-close-btn');
const sidebarBackdrop = document.getElementById('sidebar-backdrop');
const breadcrumbCurrent = document.getElementById('breadcrumb-current');
const navItems = document.querySelectorAll('.nav-item');
const sections = document.querySelectorAll('.dashboard-section');

// DOM Elements: Trace Modal
const traceModal = document.getElementById('trace-modal');
const closeModalBtn = document.getElementById('close-modal-btn');
const traceModalTitle = document.getElementById('trace-modal-title');
const traceModalSubtitle = document.getElementById('trace-modal-subtitle');
const traceLoading = document.getElementById('trace-loading');
const traceEmpty = document.getElementById('trace-empty');
const traceMessagesList = document.getElementById('trace-messages-list');

// DOM Elements: Confirmation Modal
const confirmModal = document.getElementById('confirm-modal');
const confirmModalDate = document.getElementById('confirm-modal-date');
const confirmCancelBtn = document.getElementById('confirm-cancel-btn');
const confirmOkBtn = document.getElementById('confirm-ok-btn');
const confirmCloseBtn = document.getElementById('confirm-close-btn');

// DOM Elements: Scheduler Controls
const triggerSchedulerBtn = document.getElementById('trigger-scheduler-btn');
const scheduleDateInput = document.getElementById('schedule-date-input');
const schedulerResultBox = document.getElementById('scheduler-result');
const schedulerResultPre = document.getElementById('scheduler-result-pre');

// DOM Elements: Search Filter
const conversationSearch = document.getElementById('conversation-search');

// ── Utility: Toast Notifications ─────────────────────────────────────────────
function showToast(message, duration = 3000) {
  toastEl.textContent = message;
  toastEl.classList.remove('hidden');
  setTimeout(() => {
    toastEl.classList.add('hidden');
  }, duration);
}

// ── Navigation & Section Switching ───────────────────────────────────────────
navItems.forEach(item => {
  item.addEventListener('click', () => {
    const sectionName = item.getAttribute('data-section');
    switchSection(sectionName);
    closeMobileSidebar();
  });
});

function switchSection(sectionName) {
  navItems.forEach(btn => {
    const isTarget = btn.getAttribute('data-section') === sectionName;
    btn.classList.toggle('active', isTarget);
  });
  sections.forEach(sec => {
    const isTarget = sec.id === `section-${sectionName}`;
    sec.classList.toggle('active', isTarget);
    sec.classList.toggle('hidden', !isTarget);
  });
  if (breadcrumbCurrent) {
    const labels = {
      overview: 'Overview',
      users: 'Users',
      conversations: 'Conversations',
      horoscopes: 'Horoscopes',
      compatibility: 'Compatibility',
      diagnostics: 'System Health',
      settings: 'Settings'
    };
    breadcrumbCurrent.textContent = labels[sectionName] || 'Overview';
  }
}

// Mobile Sidebar Drawer
function openMobileSidebar() {
  if (sidebar) sidebar.classList.add('open');
  if (sidebarBackdrop) sidebarBackdrop.classList.remove('hidden');
}

function closeMobileSidebar() {
  if (sidebar) sidebar.classList.remove('open');
  if (sidebarBackdrop) sidebarBackdrop.classList.add('hidden');
}

if (sidebarToggleBtn) sidebarToggleBtn.addEventListener('click', openMobileSidebar);
if (sidebarCloseBtn) sidebarCloseBtn.addEventListener('click', closeMobileSidebar);
if (sidebarBackdrop) sidebarBackdrop.addEventListener('click', closeMobileSidebar);

// Password Visibility Toggle
if (togglePasswordBtn && passwordInput) {
  togglePasswordBtn.addEventListener('click', () => {
    const isPassword = passwordInput.type === 'password';
    passwordInput.type = isPassword ? 'text' : 'password';
    togglePasswordBtn.setAttribute('aria-label', isPassword ? 'Hide password' : 'Show password');
  });
}

// ── Utility: Authenticated Fetch Wrapper ──────────────────────────────────────
async function apiRequest(endpoint, options = {}) {
  const token = sessionStorage.getItem(TOKEN_KEY);
  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {})
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers
  });

  if (response.status === 401) {
    handleUnauthorized();
    throw new Error('Session expired or unauthorized.');
  }

  if (response.status === 403) {
    throw new Error('Action prohibited: Insufficient permissions for this operation.');
  }

  if (!response.ok) {
    let errMsg = `Request failed: ${response.status} ${response.statusText}`;
    try {
      const errJson = await response.json();
      if (errJson.detail) errMsg = typeof errJson.detail === 'string' ? errJson.detail : JSON.stringify(errJson.detail);
    } catch (_) {}
    throw new Error(errMsg);
  }

  return response.json();
}

function handleUnauthorized() {
  sessionStorage.removeItem(TOKEN_KEY);
  currentUser = null;
  dashboardView.classList.add('hidden');
  loginView.classList.remove('hidden');
  if (autoRefreshTimer) clearInterval(autoRefreshTimer);
}

// ── Authentication ────────────────────────────────────────────────────────────
loginForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  loginError.classList.add('hidden');
  loginBtn.disabled = true;
  loginBtn.querySelector('.spinner').classList.remove('hidden');
  loginBtn.querySelector('.btn-text').textContent = 'Authenticating...';

  const username = document.getElementById('username').value.trim();
  const password = document.getElementById('password').value;

  try {
    const res = await fetch(`${API_BASE}/admin/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password })
    });

    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || 'Login failed. Please check credentials.');
    }

    sessionStorage.setItem(TOKEN_KEY, data.access_token);
    await initDashboard();
  } catch (err) {
    loginError.textContent = err.message;
    loginError.classList.remove('hidden');
  } finally {
    loginBtn.disabled = false;
    loginBtn.querySelector('.spinner').classList.add('hidden');
    loginBtn.querySelector('.btn-text').textContent = 'Sign In';
  }
});

logoutBtn.addEventListener('click', () => {
  handleUnauthorized();
  showToast('Signed out successfully.');
});

// ── Dashboard Initialization ──────────────────────────────────────────────────
async function initDashboard() {
  try {
    // 1. Fetch current admin profile
    currentUser = await apiRequest('/admin/auth/me');
    adminUsername.textContent = currentUser.username;
    adminRoleBadge.textContent = currentUser.role.toUpperCase();

    const avatarInitial = document.querySelector('.user-avatar-initial');
    if (avatarInitial && currentUser.username) {
      avatarInitial.textContent = currentUser.username.charAt(0).toUpperCase();
    }

    // Permissions check for Scheduler trigger
    const canTrigger = currentUser.permissions && currentUser.permissions.includes('dashboard:trigger');
    triggerSchedulerBtn.disabled = !canTrigger;
    if (!canTrigger) {
      triggerSchedulerBtn.title = "Requires 'dashboard:trigger' permission.";
    }

    loginView.classList.add('hidden');
    dashboardView.classList.remove('hidden');

    // Default to Overview section
    switchSection('overview');

    // 2. Load Dashboard Data
    await refreshAllData();

    // 3. Set auto-refresh every 30s
    if (autoRefreshTimer) clearInterval(autoRefreshTimer);
    autoRefreshTimer = setInterval(refreshAllData, 30000);

  } catch (err) {
    handleUnauthorized();
    showToast(err.message);
  }
}

async function refreshAllData() {
  await Promise.allSettled([
    loadStats(),
    loadDiagnostics(),
    loadConversations()
  ]);
}

refreshBtn.addEventListener('click', async () => {
  refreshBtn.disabled = true;
  const originalHtml = refreshBtn.innerHTML;
  refreshBtn.innerHTML = `<span>Refreshing...</span>`;
  await refreshAllData();
  refreshBtn.disabled = false;
  refreshBtn.innerHTML = originalHtml;
  showToast('Dashboard data refreshed.');
});

// ── Section 1: Load Operational Metrics ───────────────────────────────────────
async function loadStats() {
  try {
    const stats = await apiRequest('/admin/dashboard/stats');

    document.getElementById('metric-total-users').textContent = stats.total_users;
    document.getElementById('metric-active-users').textContent = stats.active_users;
    document.getElementById('metric-opt-in-users').textContent = stats.opt_in_horoscopes;
    document.getElementById('metric-total-conversations').textContent = stats.total_conversations;
    document.getElementById('metric-total-messages').textContent = stats.total_messages;

    // Breakdown
    const vedic = stats.astrology_systems.vedic || 0;
    const western = stats.astrology_systems.western || 0;
    const totalSys = vedic + western || 1;

    document.getElementById('vedic-count').textContent = vedic;
    document.getElementById('western-count').textContent = western;
    document.getElementById('vedic-progress').style.width = `${Math.round((vedic / totalSys) * 100)}%`;
    document.getElementById('western-progress').style.width = `${Math.round((western / totalSys) * 100)}%`;

    // Languages
    const langContainer = document.getElementById('languages-breakdown');
    langContainer.innerHTML = '';
    const languages = stats.languages || {};
    if (Object.keys(languages).length === 0) {
      langContainer.innerHTML = '<span class="tag">No language data recorded</span>';
    } else {
      for (const [lang, count] of Object.entries(languages)) {
        const tag = document.createElement('span');
        tag.className = 'tag';
        tag.textContent = `${lang.toUpperCase()}: ${count}`;
        langContainer.appendChild(tag);
      }
    }
  } catch (err) {
    loggerError('Error loading stats:', err);
  }
}

// ── Section 2: Load Diagnostics & Subsystems ──────────────────────────────────
async function loadDiagnostics() {
  try {
    const diag = await apiRequest('/admin/dashboard/diagnostics');

    const dbOk = diag.database === 'connected';
    const ephOk = diag.swiss_ephemeris === 'ready';
    const openaiOk = !!diag.openai_configured;
    const whatsappOk = !!diag.whatsapp_configured;
    const encOk = !!diag.encryption_ready;

    setDiagBadge('diag-db', dbOk, diag.database);
    setDiagBadge('diag-eph', ephOk, `${diag.swiss_ephemeris} (${diag.ephemeris_mode})`);
    setDiagBadge('diag-openai', openaiOk, openaiOk ? 'Configured' : 'Fallback / Offline');
    setDiagBadge('diag-whatsapp', whatsappOk, whatsappOk ? 'Ready' : 'Mock Mode');
    setDiagBadge('diag-encryption', encOk, encOk ? 'AES-GCM Ready' : 'Key Error');

    // Quick status indicator dots on Overview section
    setQuickIndicator('indicator-db', dbOk);
    setQuickIndicator('indicator-eph', ephOk);
    setQuickIndicator('indicator-openai', openaiOk);
    setQuickIndicator('indicator-whatsapp', whatsappOk);
    setQuickIndicator('indicator-encryption', encOk);

    // Display scheduler status if available
    if (diag.scheduler_status && diag.scheduler_status.last_run_stats) {
      schedulerResultBox.classList.remove('hidden');
      schedulerResultPre.textContent = JSON.stringify(diag.scheduler_status.last_run_stats, null, 2);
    }
  } catch (err) {
    loggerError('Error loading diagnostics:', err);
  }
}

function setDiagBadge(elementId, isSuccess, label) {
  const el = document.getElementById(elementId);
  if (el) {
    el.textContent = label;
    el.className = isSuccess ? 'badge badge-success' : 'badge badge-warning';
  }
}

function setQuickIndicator(indicatorId, isOk) {
  const el = document.getElementById(indicatorId);
  if (el) {
    el.className = isOk ? 'status-indicator indicator-ok' : 'status-indicator indicator-warn';
  }
}

// ── Section 3: Daily Horoscope Scheduler Trigger ─────────────────────────────
triggerSchedulerBtn.addEventListener('click', () => {
  const selectedDate = scheduleDateInput.value || null;
  if (selectedDate) {
    confirmModalDate.textContent = `Target Date: ${selectedDate}`;
    confirmModalDate.classList.remove('hidden');
  } else {
    confirmModalDate.classList.add('hidden');
  }
  confirmModal.classList.remove('hidden');
});

function closeConfirmModal() {
  if (confirmModal) confirmModal.classList.add('hidden');
}

if (confirmCancelBtn) confirmCancelBtn.addEventListener('click', closeConfirmModal);
if (confirmCloseBtn) confirmCloseBtn.addEventListener('click', closeConfirmModal);
if (confirmModal) {
  const backdrop = confirmModal.querySelector('.modal-backdrop');
  if (backdrop) backdrop.addEventListener('click', closeConfirmModal);
}

if (confirmOkBtn) {
  confirmOkBtn.addEventListener('click', async () => {
    closeConfirmModal();
    await executeBatchDispatch();
  });
}

async function executeBatchDispatch() {
  const selectedDate = scheduleDateInput.value || null;
  triggerSchedulerBtn.disabled = true;
  triggerSchedulerBtn.querySelector('.spinner').classList.remove('hidden');

  try {
    const endpoint = selectedDate
      ? `/admin/dashboard/schedules/trigger?target_date=${selectedDate}`
      : `/admin/dashboard/schedules/trigger`;

    const res = await apiRequest(endpoint, { method: 'POST' });
    schedulerResultBox.classList.remove('hidden');
    schedulerResultPre.textContent = JSON.stringify(res, null, 2);
    showToast(`Scheduler batch dispatched: ${res.sent} sent, ${res.errors} errors.`);
    await loadStats();
  } catch (err) {
    showToast(`Scheduler dispatch failed: ${err.message}`);
  } finally {
    triggerSchedulerBtn.disabled = false;
    triggerSchedulerBtn.querySelector('.spinner').classList.add('hidden');
  }
}

// ── Section 4: Load Conversations & Traces ────────────────────────────────────
async function loadConversations() {
  const tableLoading = document.getElementById('table-loading');
  const tableEmpty = document.getElementById('table-empty');
  const tableEl = document.getElementById('conversations-table');
  const tbody = document.getElementById('conversations-tbody');

  tableLoading.classList.remove('hidden');
  tableEmpty.classList.add('hidden');
  tableEl.classList.add('hidden');

  try {
    const conversations = await apiRequest('/admin/dashboard/conversations');
    tbody.innerHTML = '';

    if (!conversations || conversations.length === 0) {
      tableLoading.classList.add('hidden');
      tableEmpty.classList.remove('hidden');
      return;
    }

    conversations.forEach(conv => {
      const tr = document.createElement('tr');
      const formattedDate = new Date(conv.last_activity_at).toLocaleString();

      tr.innerHTML = `
        <td><code>${conv.id.substring(0, 8)}...</code></td>
        <td><code>${conv.user_id_prefix}</code></td>
        <td>${escapeHtml(conv.channel || 'whatsapp')}</td>
        <td><span class="badge badge-info">${escapeHtml(conv.current_state)}</span></td>
        <td><span class="badge ${conv.status === 'active' ? 'badge-success' : 'badge-warning'}">${escapeHtml(conv.status)}</span></td>
        <td>${conv.message_count}</td>
        <td>${formattedDate}</td>
        <td><button class="btn btn-secondary btn-sm" onclick="openTraceModal('${conv.id}', '${conv.user_id_prefix}')">View Trace</button></td>
      `;
      tbody.appendChild(tr);
    });

    tableLoading.classList.add('hidden');
    tableEl.classList.remove('hidden');
  } catch (err) {
    tableLoading.classList.add('hidden');
    tableEmpty.classList.remove('hidden');
    loggerError('Error loading conversations:', err);
  }
}

// Conversation Search Filter
if (conversationSearch) {
  conversationSearch.addEventListener('input', (e) => {
    const query = e.target.value.toLowerCase().trim();
    const rows = document.querySelectorAll('#conversations-tbody tr');
    rows.forEach(row => {
      const text = row.textContent.toLowerCase();
      row.style.display = text.includes(query) ? '' : 'none';
    });
  });
}

// ── Modal: Conversation Trace Viewer ──────────────────────────────────────────
window.openTraceModal = async function(convId, userPrefix) {
  traceModalTitle.textContent = `Conversation: ${convId.substring(0, 8)}...`;
  traceModalSubtitle.textContent = `User Identity: ${userPrefix}`;
  traceModal.classList.remove('hidden');

  traceLoading.classList.remove('hidden');
  traceEmpty.classList.add('hidden');
  traceMessagesList.classList.add('hidden');
  traceMessagesList.innerHTML = '';

  try {
    const trace = await apiRequest(`/admin/dashboard/conversations/${convId}/trace`);
    traceLoading.classList.add('hidden');

    if (!trace.messages || trace.messages.length === 0) {
      traceEmpty.classList.remove('hidden');
      return;
    }

    trace.messages.forEach(msg => {
      const bubble = document.createElement('div');
      const isInbound = msg.direction === 'inbound';
      bubble.className = `msg-bubble ${isInbound ? 'msg-inbound' : 'msg-outbound'}`;

      const senderLabel = isInbound ? 'User' : 'Assistant';
      const timeStr = new Date(msg.created_at).toLocaleTimeString();

      bubble.innerHTML = `
        <div class="msg-text">${escapeHtml(msg.content_preview)}</div>
        <span class="msg-meta">${senderLabel} • ${timeStr}</span>
      `;
      traceMessagesList.appendChild(bubble);
    });

    traceMessagesList.classList.remove('hidden');
  } catch (err) {
    traceLoading.classList.add('hidden');
    traceEmpty.classList.remove('hidden');
    traceEmpty.textContent = `Failed to load trace: ${err.message}`;
  }
};

closeModalBtn.addEventListener('click', () => {
  traceModal.classList.add('hidden');
});

traceModal.querySelector('.modal-backdrop').addEventListener('click', () => {
  traceModal.classList.add('hidden');
});

function escapeHtml(str) {
  if (!str) return '';
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function loggerError(msg, err) {
  console.error(msg, err);
}

// Initial Boot: Check if session token exists
document.addEventListener('DOMContentLoaded', () => {
  const token = sessionStorage.getItem(TOKEN_KEY);
  if (token) {
    initDashboard();
  }
});

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
      'bot-controls': 'Bot Controls & Messages',
      'message-center': 'Message Center',
      'business-profile': 'Business Profile',
      settings: 'Settings'
    };
    breadcrumbCurrent.textContent = labels[sectionName] || 'Overview';
  }

  // Section lazy data loading
  if (sectionName === 'bot-controls') loadBotSettings();
  if (sectionName === 'message-center') { loadEligibleRecipients(); loadRecentDirectMessages(); }
  if (sectionName === 'business-profile') loadBusinessProfile();
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


// ── Section 5: Bot Controls & Custom Message Manager ─────────────────────────
async function loadBotSettings() {
  const badge = document.getElementById('bot-state-badge');
  const info = document.getElementById('bot-state-info');
  try {
    const data = await apiRequest('/admin/control/settings');

    // Update state badge
    if (data.is_paused) {
      if (data.maintenance_mode) {
        if (badge) {
          badge.textContent = 'Maintenance Mode';
          badge.className = 'badge badge-warning';
        }
        if (info) info.textContent = 'Maintenance active: incoming messages receive scheduled maintenance reply.';
      } else {
        if (badge) {
          badge.textContent = 'Paused';
          badge.className = 'badge badge-warning';
        }
        if (info) info.textContent = 'Assistant paused: replies suppressed, incoming messages recorded.';
      }
    } else {
      if (badge) {
        badge.textContent = 'Operational';
        badge.className = 'badge badge-success';
      }
      if (info) info.textContent = 'Live automated replies active grounded in verified astronomical math.';
    }

    // Populate message textareas
    setSettingVal('setting-welcome', 'count-welcome', data.welcome_message, 2000);
    setSettingVal('setting-fallback', 'count-fallback', data.fallback_message, 2000);
    setSettingVal('setting-instructions', 'count-instructions', data.general_instructions, 4000);
    setSettingVal('setting-horoscope-intro', 'count-horoscope-intro', data.horoscope_intro, 1000);
    setSettingVal('setting-maintenance', 'count-maintenance', data.maintenance_message, 2000);
  } catch (err) {
    loggerError('Error loading bot settings:', err);
    showToast(`Failed to load bot settings: ${err.message}`);
  }
}

function setSettingVal(inputId, counterId, val, maxLen) {
  const el = document.getElementById(inputId);
  const countEl = document.getElementById(counterId);
  if (el) {
    el.value = val || '';
    if (countEl) countEl.textContent = `${(val || '').length} / ${maxLen}`;
  }
}

// Bind live counters
['welcome', 'fallback', 'instructions', 'horoscope-intro', 'maintenance'].forEach(name => {
  const el = document.getElementById(`setting-${name}`);
  const countEl = document.getElementById(`count-${name}`);
  const max = name === 'instructions' ? 4000 : (name === 'horoscope-intro' ? 1000 : 2000);
  if (el && countEl) {
    el.addEventListener('input', () => {
      countEl.textContent = `${el.value.length} / ${max}`;
    });
  }
});

// Bot Control Actions: Pause, Maint, Resume
const btnPauseBot = document.getElementById('btn-pause-bot');
const btnMaintBot = document.getElementById('btn-maint-bot');
const btnResumeBot = document.getElementById('btn-resume-bot');
const btnReloadSettings = document.getElementById('btn-reload-settings');
const botSettingsForm = document.getElementById('bot-settings-form');
const btnSaveSettings = document.getElementById('btn-save-settings');

if (btnPauseBot) {
  btnPauseBot.addEventListener('click', async () => {
    try {
      await apiRequest('/admin/control/bot/pause', {
        method: 'POST',
        body: JSON.stringify({ maintenance_mode: false })
      });
      showToast('Bot successfully paused.');
      await loadBotSettings();
    } catch (err) {
      showToast(`Pause failed: ${err.message}`);
    }
  });
}

if (btnMaintBot) {
  btnMaintBot.addEventListener('click', async () => {
    try {
      await apiRequest('/admin/control/bot/pause', {
        method: 'POST',
        body: JSON.stringify({ maintenance_mode: true })
      });
      showToast('Maintenance mode activated.');
      await loadBotSettings();
    } catch (err) {
      showToast(`Maintenance mode failed: ${err.message}`);
    }
  });
}

if (btnResumeBot) {
  btnResumeBot.addEventListener('click', async () => {
    try {
      await apiRequest('/admin/control/bot/resume', { method: 'POST' });
      showToast('Bot operations resumed.');
      await loadBotSettings();
    } catch (err) {
      showToast(`Resume failed: ${err.message}`);
    }
  });
}

if (btnReloadSettings) {
  btnReloadSettings.addEventListener('click', async (e) => {
    e.preventDefault();
    await loadBotSettings();
    showToast('Settings reloaded.');
  });
}

if (botSettingsForm) {
  botSettingsForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (btnSaveSettings) {
      btnSaveSettings.disabled = true;
      btnSaveSettings.querySelector('.spinner')?.classList.remove('hidden');
      btnSaveSettings.querySelector('.btn-text').textContent = 'Saving...';
    }

    const payload = {
      welcome_message: document.getElementById('setting-welcome')?.value,
      fallback_message: document.getElementById('setting-fallback')?.value,
      general_instructions: document.getElementById('setting-instructions')?.value,
      horoscope_intro: document.getElementById('setting-horoscope-intro')?.value,
      maintenance_message: document.getElementById('setting-maintenance')?.value,
    };

    try {
      await apiRequest('/admin/control/settings', {
        method: 'PUT',
        body: JSON.stringify(payload)
      });
      showToast('Custom message settings saved successfully.');
      await loadBotSettings();
    } catch (err) {
      showToast(`Save failed: ${err.message}`);
    } finally {
      if (btnSaveSettings) {
        btnSaveSettings.disabled = false;
        btnSaveSettings.querySelector('.spinner')?.classList.add('hidden');
        btnSaveSettings.querySelector('.btn-text').textContent = 'Save Message Settings';
      }
    }
  });
}

// ── Section 6: Message Center (Direct Outbound & 24h Window) ─────────────────
let cachedRecipients = [];
const directRecipientSelect = document.getElementById('direct-recipient-select');
const directWindowBadge = document.getElementById('direct-window-badge');
const directWindowDesc = document.getElementById('direct-window-desc');
const directPolicyAlert = document.getElementById('direct-policy-alert');
const directFreeformSection = document.getElementById('direct-freeform-section');
const directTemplateSection = document.getElementById('direct-template-section');
const btnSendTemplate = document.getElementById('btn-send-template');
const directMessageInput = document.getElementById('direct-message-input');
const directCharCount = document.getElementById('direct-char-count');
const directPreviewText = document.getElementById('direct-preview-text');
const directPreviewTime = document.getElementById('direct-preview-time');
const btnOpenSendModal = document.getElementById('btn-open-send-modal');

// Modal Elements
const directSendModal = document.getElementById('direct-send-modal');
const directSendCloseBtn = document.getElementById('direct-send-close-btn');
const directSendCancelBtn = document.getElementById('direct-send-cancel-btn');
const directSendConfirmBtn = document.getElementById('direct-send-confirm-btn');
const modalRecipientName = document.getElementById('modal-recipient-name');
const modalRecipientPhone = document.getElementById('modal-recipient-phone');
const modalRecipientWindow = document.getElementById('modal-recipient-window');
const modalMessagePreview = document.getElementById('modal-message-preview');
const modalWindowWarning = document.getElementById('modal-window-warning');

async function loadEligibleRecipients() {
  if (!directRecipientSelect) return;
  try {
    const data = await apiRequest('/admin/messages/recipients');
    cachedRecipients = data.recipients || [];
    directRecipientSelect.innerHTML = '<option value="">Select an active opted-in user...</option>';

    cachedRecipients.forEach(r => {
      const opt = document.createElement('option');
      opt.value = r.id;
      const windowStr = r.window_active ? `[24h Window: ${r.hours_remaining}h left]` : '[24h Expired]';
      opt.textContent = `${r.whatsapp_name} (${r.masked_phone}) ${windowStr}`;
      directRecipientSelect.appendChild(opt);
    });
  } catch (err) {
    loggerError('Error loading recipients:', err);
  }
}

if (directRecipientSelect) {
  directRecipientSelect.addEventListener('change', () => {
    const userId = directRecipientSelect.value;
    const recipient = cachedRecipients.find(r => r.id === userId);

    if (!recipient) {
      if (directWindowBadge) {
        directWindowBadge.textContent = 'None Selected';
        directWindowBadge.className = 'badge';
      }
      if (directWindowDesc) directWindowDesc.textContent = 'Select a recipient to verify window status.';
      if (directPolicyAlert) directPolicyAlert.classList.add('hidden');
      if (directFreeformSection) directFreeformSection.classList.remove('hidden');
      if (directTemplateSection) directTemplateSection.classList.add('hidden');
      return;
    }

    if (recipient.window_active) {
      if (directWindowBadge) {
        directWindowBadge.textContent = `Active (${recipient.hours_remaining}h left)`;
        directWindowBadge.className = 'badge badge-success';
      }
      if (directWindowDesc) directWindowDesc.textContent = `Within 24h Meta Customer Service Window. Free-form text permitted until ${new Date(recipient.window_expires_at).toLocaleTimeString()}.`;
      if (directPolicyAlert) directPolicyAlert.classList.add('hidden');
      if (directFreeformSection) directFreeformSection.classList.remove('hidden');
      if (directTemplateSection) directTemplateSection.classList.add('hidden');
    } else {
      if (directWindowBadge) {
        directWindowBadge.textContent = 'Window Expired';
        directWindowBadge.className = 'badge badge-warning';
      }
      if (directWindowDesc) directWindowDesc.textContent = 'The 24-hour Meta service window has elapsed. Free-form text is blocked. Send an approved template below to re-engage.';
      if (directPolicyAlert) directPolicyAlert.classList.remove('hidden');
      if (directFreeformSection) directFreeformSection.classList.add('hidden');
      if (directTemplateSection) directTemplateSection.classList.remove('hidden');

      // Autofill defaults for template form
      const greetingInput = document.getElementById('template-param-greeting');
      if (greetingInput && !greetingInput.value) greetingInput.value = recipient.whatsapp_name || 'Seeker';
      const dateInput = document.getElementById('template-param-date');
      if (dateInput && !dateInput.value) dateInput.value = new Date().toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
    }
  });
}

// Live message preview and character count
if (directMessageInput) {
  directMessageInput.addEventListener('input', () => {
    const text = directMessageInput.value;
    if (directCharCount) directCharCount.textContent = `${text.length} / 2000`;
    if (directPreviewText) {
      directPreviewText.textContent = text.trim() ? text : 'Your message preview will appear here...';
    }
    if (directPreviewTime) {
      directPreviewTime.textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }
  });
}

// Open confirmation modal for free-form send
if (btnOpenSendModal) {
  btnOpenSendModal.addEventListener('click', () => {
    const userId = directRecipientSelect?.value;
    const recipient = cachedRecipients.find(r => r.id === userId);
    const text = directMessageInput?.value.trim();

    if (!recipient) {
      showToast('Please select a recipient first.');
      return;
    }
    if (!recipient.window_active) {
      showToast('24h window expired. Under Meta policy, free-form text is blocked. Use the template sender.');
      return;
    }
    if (!text) {
      showToast('Please enter a message to send.');
      return;
    }

    if (modalRecipientName) modalRecipientName.textContent = recipient.whatsapp_name;
    if (modalRecipientPhone) modalRecipientPhone.textContent = recipient.masked_phone;
    if (modalRecipientWindow) {
      modalRecipientWindow.textContent = `Active (${recipient.hours_remaining}h left)`;
      modalRecipientWindow.className = 'badge badge-success';
    }
    if (modalMessagePreview) modalMessagePreview.textContent = text;
    modalWindowWarning?.classList.add('hidden');

    directSendModal?.classList.remove('hidden');
  });
}

function closeDirectSendModal() {
  if (directSendModal) directSendModal.classList.add('hidden');
}

if (directSendCloseBtn) directSendCloseBtn.addEventListener('click', closeDirectSendModal);
if (directSendCancelBtn) directSendCancelBtn.addEventListener('click', closeDirectSendModal);
if (directSendModal) {
  const backdrop = directSendModal.querySelector('.modal-backdrop');
  if (backdrop) backdrop.addEventListener('click', closeDirectSendModal);
}

if (directSendConfirmBtn) {
  directSendConfirmBtn.addEventListener('click', async () => {
    const userId = directRecipientSelect?.value;
    const recipient = cachedRecipients.find(r => r.id === userId);
    const text = directMessageInput?.value.trim();

    directSendConfirmBtn.disabled = true;
    directSendConfirmBtn.textContent = 'Sending...';

    try {
      const res = await apiRequest('/admin/messages/send', {
        method: 'POST',
        body: JSON.stringify({
          user_id: userId,
          message_text: text,
          confirmed: true
        })
      });

      closeDirectSendModal();
      showToast(`Message sent successfully! (Status: ${res.delivery_status})`);
      if (directMessageInput) directMessageInput.value = '';
      if (directPreviewText) directPreviewText.textContent = 'Your message preview will appear here...';
      if (directCharCount) directCharCount.textContent = '0 / 2000';
      await loadRecentDirectMessages();
    } catch (err) {
      showToast(`Send failed: ${err.message}`);
    } finally {
      directSendConfirmBtn.disabled = false;
      directSendConfirmBtn.textContent = 'Send WhatsApp Message';
    }
  });
}

// Send Approved Template Handler
if (btnSendTemplate) {
  btnSendTemplate.addEventListener('click', async () => {
    const userId = directRecipientSelect?.value;
    const recipient = cachedRecipients.find(r => r.id === userId);
    if (!recipient) {
      showToast('Please select a recipient first.');
      return;
    }

    const templateName = document.getElementById('template-name-select')?.value;
    const lang = document.getElementById('template-lang-select')?.value || 'en';
    const p1 = document.getElementById('template-param-greeting')?.value.trim();
    const p2 = document.getElementById('template-param-date')?.value.trim();
    const p3 = document.getElementById('template-param-summary')?.value.trim();
    const p4 = document.getElementById('template-param-body')?.value.trim();

    if (!p1 || !p2 || !p3 || !p4) {
      showToast('All 4 template parameters are required for delivery.');
      return;
    }

    btnSendTemplate.disabled = true;
    btnSendTemplate.querySelector('.spinner')?.classList.remove('hidden');
    btnSendTemplate.querySelector('.btn-text').textContent = 'Sending Template...';

    try {
      const res = await apiRequest('/admin/messages/send-template', {
        method: 'POST',
        body: JSON.stringify({
          user_id: userId,
          template_name: templateName,
          language_code: lang,
          body_parameters: [p1, p2, p3, p4],
          confirmed: true
        })
      });

      showToast(`Template dispatched successfully! (Status: ${res.delivery_status})`);
      if (document.getElementById('template-param-body')) document.getElementById('template-param-body').value = '';
      await loadRecentDirectMessages();
    } catch (err) {
      showToast(`Template send failed: ${err.message}`);
    } finally {
      btnSendTemplate.disabled = false;
      btnSendTemplate.querySelector('.spinner')?.classList.add('hidden');
      btnSendTemplate.querySelector('.btn-text').textContent = 'Review & Send Approved Template';
    }
  });
}

async function loadRecentDirectMessages() {
  const tbody = document.getElementById('direct-history-tbody');
  const loading = document.getElementById('direct-history-loading');
  const empty = document.getElementById('direct-history-empty');
  if (!tbody) return;

  loading?.classList.remove('hidden');
  empty?.classList.add('hidden');
  tbody.innerHTML = '';

  try {
    const data = await apiRequest('/admin/messages/recent');
    const messages = data.messages || [];
    loading?.classList.add('hidden');

    if (messages.length === 0) {
      empty?.classList.remove('hidden');
      return;
    }

    messages.forEach(msg => {
      const tr = document.createElement('tr');
      const timeStr = new Date(msg.created_at).toLocaleString();

      let badgeClass = 'badge badge-info';
      if (msg.delivery_status === 'delivered') badgeClass = 'badge badge-primary';
      if (msg.delivery_status === 'read') badgeClass = 'badge badge-success';
      if (msg.delivery_status === 'failed') badgeClass = 'badge badge-danger';

      const errorTip = msg.error_code ? `<span title="${escapeHtml(msg.error_message || '')}"> (Code ${msg.error_code})</span>` : '';

      tr.innerHTML = `
        <td><strong>${escapeHtml(msg.whatsapp_name)}</strong><br><code class="text-muted">${escapeHtml(msg.masked_phone)}</code></td>
        <td><div style="max-width: 300px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${escapeHtml(msg.content_preview)}</div></td>
        <td><span class="${badgeClass}">${escapeHtml(msg.delivery_status || 'sent')}</span>${errorTip}</td>
        <td>${msg.status_timestamp ? new Date(msg.status_timestamp).toLocaleTimeString() : '—'}</td>
        <td>${timeStr}</td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    loading?.classList.add('hidden');
    empty?.classList.remove('hidden');
    loggerError('Error loading outbound history:', err);
  }
}

const btnRefreshDirectHistory = document.getElementById('btn-refresh-direct-history');
if (btnRefreshDirectHistory) {
  btnRefreshDirectHistory.addEventListener('click', loadRecentDirectMessages);
}

// ── Section 7: WhatsApp Business Profile Management ─────────────────────────
const profileAvatarImg = document.getElementById('profile-avatar-img');
const profileAvatarPlaceholder = document.getElementById('profile-avatar-placeholder');
const profilePhotoInput = document.getElementById('profile-photo-input');
const btnSelectPhoto = document.getElementById('btn-select-photo');
const btnUploadPhoto = document.getElementById('btn-upload-photo');
const photoUploadFeedback = document.getElementById('photo-upload-feedback');
const profileEditForm = document.getElementById('profile-edit-form');
const btnSaveProfile = document.getElementById('btn-save-profile');

let selectedPhotoFile = null;

async function loadBusinessProfile() {
  try {
    const prof = await apiRequest('/admin/whatsapp/profile');

    const syncBadge = document.getElementById('profile-sync-badge');
    if (syncBadge) {
      if (prof.live_meta) {
        syncBadge.textContent = 'Live Meta Cloud';
        syncBadge.className = 'badge badge-success';
      } else {
        syncBadge.textContent = 'Mock / Diagnostic Mode';
        syncBadge.className = 'badge badge-warning';
      }
    }

    if (prof.profile_picture_url && profileAvatarImg) {
      profileAvatarImg.src = prof.profile_picture_url;
      profileAvatarImg.classList.remove('hidden');
      profileAvatarPlaceholder?.classList.add('hidden');
    }

    if (document.getElementById('profile-about')) document.getElementById('profile-about').value = prof.about || '';
    if (document.getElementById('profile-vertical')) document.getElementById('profile-vertical').value = prof.vertical || 'ENTERTAINMENT';
    if (document.getElementById('profile-description')) document.getElementById('profile-description').value = prof.description || '';
    if (document.getElementById('profile-email')) document.getElementById('profile-email').value = prof.email || '';
    if (document.getElementById('profile-address')) document.getElementById('profile-address').value = prof.address || '';

    const websites = prof.websites || [];
    if (document.getElementById('profile-website1')) document.getElementById('profile-website1').value = websites[0] || '';
    if (document.getElementById('profile-website2')) document.getElementById('profile-website2').value = websites[1] || '';
  } catch (err) {
    loggerError('Error loading business profile:', err);
    showToast(`Failed to load business profile: ${err.message}`);
  }
}

if (btnSelectPhoto && profilePhotoInput) {
  btnSelectPhoto.addEventListener('click', () => profilePhotoInput.click());
  profilePhotoInput.addEventListener('change', () => {
    if (profilePhotoInput.files && profilePhotoInput.files[0]) {
      selectedPhotoFile = profilePhotoInput.files[0];
      if (selectedPhotoFile.size > 5 * 1024 * 1024) {
        if (photoUploadFeedback) {
          photoUploadFeedback.textContent = 'Error: Image exceeds 5 MB limit.';
          photoUploadFeedback.style.color = 'var(--color-danger)';
        }
        if (btnUploadPhoto) btnUploadPhoto.classList.add('hidden');
        return;
      }
      if (photoUploadFeedback) {
        photoUploadFeedback.textContent = `Selected: ${selectedPhotoFile.name} (${Math.round(selectedPhotoFile.size / 1024)} KB)`;
        photoUploadFeedback.style.color = 'var(--color-success)';
      }
      if (btnUploadPhoto) btnUploadPhoto.classList.remove('hidden');

      // Local preview
      const reader = new FileReader();
      reader.onload = (e) => {
        if (profileAvatarImg) {
          profileAvatarImg.src = e.target.result;
          profileAvatarImg.classList.remove('hidden');
          profileAvatarPlaceholder?.classList.add('hidden');
        }
      };
      reader.readAsDataURL(selectedPhotoFile);
    }
  });
}

if (btnUploadPhoto) {
  btnUploadPhoto.addEventListener('click', async () => {
    if (!selectedPhotoFile) return;

    btnUploadPhoto.disabled = true;
    btnUploadPhoto.querySelector('.spinner')?.classList.remove('hidden');
    btnUploadPhoto.querySelector('.btn-text').textContent = 'Uploading to Meta...';

    const formData = new FormData();
    formData.append('file', selectedPhotoFile);

    const token = sessionStorage.getItem(TOKEN_KEY);
    try {
      const resp = await fetch(`${API_BASE}/admin/whatsapp/profile/photo`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`
        },
        body: formData
      });

      if (!resp.ok) {
        const errJson = await resp.json().catch(() => ({}));
        throw new Error(errJson.detail || 'Photo upload failed');
      }

      const data = await resp.json().catch(() => ({}));
      const isMock = data?.result?.mocked || data?.mocked;
      if (isMock) {
        showToast('Diagnostic Mode: Profile photo upload simulated (Meta credentials unset).');
        if (photoUploadFeedback) photoUploadFeedback.textContent = 'Simulated photo upload (Meta credentials not configured).';
      } else {
        showToast('Profile photo updated successfully on Meta Cloud!');
        if (photoUploadFeedback) photoUploadFeedback.textContent = 'Photo uploaded and synced with live Meta Cloud.';
      }
      btnUploadPhoto.classList.add('hidden');
      await loadBusinessProfile();
    } catch (err) {
      showToast(`Upload failed: ${err.message}`);
      if (photoUploadFeedback) {
        photoUploadFeedback.textContent = `Upload failed: ${err.message}`;
        photoUploadFeedback.style.color = 'var(--color-danger)';
      }
    } finally {
      btnUploadPhoto.disabled = false;
      btnUploadPhoto.querySelector('.spinner')?.classList.add('hidden');
      btnUploadPhoto.querySelector('.btn-text').textContent = 'Upload to Meta Cloud';
    }
  });
}

if (profileEditForm) {
  profileEditForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (btnSaveProfile) {
      btnSaveProfile.disabled = true;
      btnSaveProfile.querySelector('.spinner')?.classList.remove('hidden');
      btnSaveProfile.querySelector('.btn-text').textContent = 'Saving...';
    }

    const websites = [];
    const w1 = document.getElementById('profile-website1')?.value.trim();
    const w2 = document.getElementById('profile-website2')?.value.trim();
    if (w1) websites.push(w1);
    if (w2) websites.push(w2);

    const payload = {
      about: document.getElementById('profile-about')?.value.trim(),
      vertical: document.getElementById('profile-vertical')?.value,
      description: document.getElementById('profile-description')?.value.trim(),
      email: document.getElementById('profile-email')?.value.trim(),
      address: document.getElementById('profile-address')?.value.trim(),
      websites: websites,
    };

    try {
      const res = await apiRequest('/admin/whatsapp/profile', {
        method: 'POST',
        body: JSON.stringify(payload)
      });
      const isMock = res?.result?.mocked || res?.mocked;
      if (isMock) {
        showToast('Diagnostic Mode: Profile saved locally (Meta credentials unset).');
      } else {
        showToast('WhatsApp Business profile saved successfully to Meta!');
      }
      await loadBusinessProfile();
    } catch (err) {
      showToast(`Profile save failed: ${err.message}`);
    } finally {
      if (btnSaveProfile) {
        btnSaveProfile.disabled = false;
        btnSaveProfile.querySelector('.spinner')?.classList.add('hidden');
        btnSaveProfile.querySelector('.btn-text').textContent = 'Save Profile to Meta';
      }
    }
  });
}

const API_BASE = import.meta.env.VITE_API_BASE || "";
const USE_FIXTURES = import.meta.env.VITE_DEMO === "true";

export const XERO_LOGIN_URL = `${API_BASE}/auth/login`;

export function statementUrl(contactId) {
  return `${API_BASE}/api/statements/${encodeURIComponent(contactId)}`;
}

let localState;

const DEFAULT_RESEARCH = { generated_at: null, sources: {}, files: [] };
const DEFAULT_APP_STORE_READINESS = {
  status: "unknown",
  ready_count: 0,
  total_count: 0,
  source_url: "",
  items: []
};
const DEFAULT_AI_STATUS = {
  enabled: false,
  provider: null,
  model: "",
  mode: "disabled",
  detail: "AI draft polishing is disabled."
};
const DEFAULT_XERO_STATUS = {
  connected: false,
  tenant_id: null,
  expires_at: null,
  expired: false,
  needs_tenant: false,
  demo_mode: false,
  client_credentials_configured: false,
  env_tokens_configured: false,
  env_refresh_token_configured: false,
  redirect_uri: ""
};
const DEFAULT_XERO_TENANTS = { active_tenant_id: null, tenants: [] };
const DEFAULT_BILLS = { bills: [], summary: { total_count: 0, upcoming_count: 0, due_next_30_amount: 0, next_bill: null, categories: [] } };

async function ensureLocalState() {
  if (localState) return localState;
  const [contactsModule, invoicesModule, forecastModule, proposalsModule, actionLogModule] = await Promise.all([
    import("../../fixtures/contacts.json"),
    import("../../fixtures/invoices.json"),
    import("../../fixtures/forecast.json"),
    import("../../fixtures/proposals.json"),
    import("../../fixtures/action_log.json")
  ]);
  const fixtureForecast = forecastModule.default;
  localState = {
    contacts: structuredClone(contactsModule.default),
    invoices: structuredClone(invoicesModule.default),
    forecast: structuredClone(fixtureForecast),
    proposals: structuredClone(proposalsModule.default),
    action_log: structuredClone(actionLogModule.default),
    outbox: [],
    metrics: {
      cash_accelerated_dollars: 0,
      avg_days_accelerated: 0,
      approved_actions_count: 0,
      pending_impact_dollars: 0,
      pending_avg_days_accelerated: 0,
      pending_actions_count: 0,
      aged_receivables: null
    },
    research: { generated_at: null, sources: {}, files: [] },
    settings: { cash_floor: fixtureForecast.cash_floor },
    dataSource: {
      mode: "fixture",
      label: "Offline portfolio",
      detail: "Offline data is loaded because the backend is unavailable.",
      generated_at: null
    },
    appStoreReadiness: {
      status: "draft",
      ready_count: 5,
      total_count: 9,
      source_url: "https://developer.xero.com/documentation/best-practices/overview/cert-matrix/",
      items: [
        {
          id: "sign-up-with-xero",
          label: "Sign Up with Xero",
          status: "blocked",
          detail: "Add XERO_CLIENT_ID and XERO_CLIENT_SECRET."
        },
        {
          id: "connection",
          label: "Connection management",
          status: "demo",
          detail: "Local connection check is active."
        },
        {
          id: "scopes",
          label: "OAuth scopes",
          status: "ready",
          detail: "openid profile email accounting.invoices accounting.contacts accounting.payments accounting.settings offline_access"
        },
        {
          id: "data-integrity",
          label: "Data integrity",
          status: "ready",
          detail: "Reads contacts, invoices and payments; customer emails stay in Outbox, while approved actions can add internal Xero invoice notes."
        },
        {
          id: "api-efficiency",
          label: "API efficiency",
          status: "ready",
          detail: "Xero sync uses pagination and retries 429 responses using Retry-After."
        },
        {
          id: "listing",
          label: "App Store listing",
          status: "ready",
          detail: "Submission notes are drafted in docs/xero-app-store-submission.md."
        },
        {
          id: "webhook-receiver",
          label: "Webhook receiver",
          status: "todo",
          detail: "Signed receiver exists at /webhooks/xero; add XERO_WEBHOOK_KEY before enabling Xero webhooks."
        },
        {
          id: "app-store-subscriptions",
          label: "App Store subscriptions",
          status: "todo",
          detail: "Configure App Store subscription/webhook categories in Xero Developer Centre for the production HTTPS URL, then set XERO_APP_STORE_SUBSCRIPTIONS_CONFIGURED=true."
        },
        {
          id: "support-security",
          label: "Support and security",
          status: "ready",
          detail: "Support, privacy, retention and security notes are drafted in docs/support.md and docs/privacy-security.md."
        }
      ]
    },
    aiStatus: {
      ...DEFAULT_AI_STATUS
    },
    xeroStatus: {
      ...DEFAULT_XERO_STATUS,
      demo_mode: true,
      redirect_uri: "http://localhost:8000/auth/callback"
    },
    xeroTenants: { ...DEFAULT_XERO_TENANTS },
    bills: { ...DEFAULT_BILLS }
  };
  return localState;
}

function nowIso() {
  return new Date().toISOString();
}

function money(value) {
  return Number(value || 0).toLocaleString("en-US");
}

const AGING_BUCKETS = [
  { id: "current", label: "Not overdue" },
  { id: "1_30", label: "1-30 days late" },
  { id: "31_60", label: "31-60 days late" },
  { id: "61_90", label: "61-90 days late" },
  { id: "90_plus", label: "90+ days late" }
];

function agingBucketId(daysLate) {
  if (daysLate <= 0) return "current";
  if (daysLate <= 30) return "1_30";
  if (daysLate <= 60) return "31_60";
  if (daysLate <= 90) return "61_90";
  return "90_plus";
}

function buildAgedReceivables(invoices, asOf = nowIso().slice(0, 10)) {
  const buckets = AGING_BUCKETS.map((bucket) => ({ ...bucket, invoice_count: 0, amount_due: 0 }));
  const byId = new Map(buckets.map((bucket) => [bucket.id, bucket]));
  const asOfDate = new Date(`${asOf}T00:00:00Z`);
  let openTotal = 0;
  let overdueTotal = 0;

  for (const invoice of invoices || []) {
    const dueDate = new Date(`${invoice.due_date}T00:00:00Z`);
    if (Number.isNaN(dueDate.getTime())) continue;
    const amount = Math.round(Number(invoice.amount_due || 0));
    const daysLate = Math.round((asOfDate - dueDate) / 86400000);
    const bucket = byId.get(agingBucketId(daysLate));
    bucket.invoice_count += 1;
    bucket.amount_due += amount;
    openTotal += amount;
    if (daysLate > 0) overdueTotal += amount;
  }

  return {
    as_of: asOf,
    open_total: openTotal,
    overdue_total: overdueTotal,
    buckets
  };
}

async function request(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers
  });
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const payload = await response.json();
      if (typeof payload.detail === "string") message = payload.detail;
      else if (typeof payload.message === "string") message = payload.message;
    } catch {
      // Keep the HTTP fallback when the backend does not return JSON.
    }
    throw new Error(message);
  }
  if (response.status === 204) return null;
  return response.json();
}

async function optionalRequest(path, fallback) {
  try {
    return await request(path);
  } catch {
    return fallback;
  }
}

function buildLocalForecast(state) {
  const cashFloor = state.settings.cash_floor;
  return {
    ...state.forecast,
    as_of: state.forecast.as_of || "2026-07-04",
    cash_floor: cashFloor,
    buckets: state.forecast.buckets.map((bucket) => ({
      ...bucket,
      below_floor: bucket.cumulative_predicted < cashFloor
    }))
  };
}

function proposalRollup(state, status) {
  const proposalsForStatus = state.proposals.filter((proposal) => proposal.status === status);
  const dollars = proposalsForStatus.reduce((sum, proposal) => sum + proposal.expected_impact_dollars, 0);
  const weightedDays = proposalsForStatus.reduce(
    (sum, proposal) => sum + proposal.expected_impact_dollars * proposal.expected_days_accelerated,
    0
  );
  return {
    actions_count: proposalsForStatus.length,
    impact_dollars: dollars,
    avg_days_accelerated: dollars ? Math.round((weightedDays / dollars) * 10) / 10 : 0
  };
}

function proposalActionLabel(proposal) {
  const labels = {
    reminder: "payment reminder",
    escalation: "firmer payment reminder",
    deposit_recommendation: "deposit recommendation",
    terms_recommendation: "payment terms recommendation"
  };
  return labels[proposal?.type] || "suggestion";
}

function recomputeLocalMetrics(state) {
  const approved = proposalRollup(state, "approved");
  const pending = proposalRollup(state, "pending");
  state.metrics = {
    cash_accelerated_dollars: approved.impact_dollars,
    avg_days_accelerated: approved.avg_days_accelerated,
    approved_actions_count: approved.actions_count,
    pending_impact_dollars: pending.impact_dollars,
    pending_avg_days_accelerated: pending.avg_days_accelerated,
    pending_actions_count: pending.actions_count,
    aged_receivables: buildAgedReceivables(state.invoices, state.forecast.as_of || nowIso().slice(0, 10))
  };
}

export async function fetchAll() {
  if (USE_FIXTURES) {
    const state = await ensureLocalState();
    recomputeLocalMetrics(state);
    return {
      contacts: state.contacts,
      invoices: state.invoices,
      forecast: buildLocalForecast(state),
      proposals: state.proposals,
      actionLog: state.action_log,
      outbox: state.outbox,
      metrics: state.metrics,
      research: state.research,
      settings: state.settings,
      dataSource: state.dataSource,
      appStoreReadiness: state.appStoreReadiness,
      aiStatus: state.aiStatus,
      xeroStatus: state.xeroStatus,
      xeroTenants: state.xeroTenants,
      bills: state.bills
    };
  }

  const [
    contactsData,
    invoicesData,
    forecastData,
    proposalsData,
    logData,
    outboxData,
    metricsData,
    researchData,
    settingsData,
    dataSourceData,
    appStoreReadinessData,
    aiStatusData,
    xeroStatusData,
    billsData
  ] =
    await Promise.all([
      request("/api/contacts"),
      request("/api/invoices"),
      request("/api/forecast"),
      request("/api/proposals"),
      request("/api/action_log"),
      request("/api/outbox"),
      request("/api/metrics"),
      optionalRequest("/api/research/status", DEFAULT_RESEARCH),
      request("/api/settings"),
      request("/api/data_source"),
      optionalRequest("/api/app_store/readiness", DEFAULT_APP_STORE_READINESS),
      optionalRequest("/api/ai/status", DEFAULT_AI_STATUS),
      optionalRequest("/api/xero/status", DEFAULT_XERO_STATUS),
      optionalRequest("/api/bills", DEFAULT_BILLS)
    ]);
  const shouldLoadTenants = xeroStatusData.connected && !xeroStatusData.demo_mode && !xeroStatusData.expired && !xeroStatusData.refresh_error;
  const xeroTenantsData = shouldLoadTenants
    ? await optionalRequest("/api/xero/tenants", DEFAULT_XERO_TENANTS)
    : DEFAULT_XERO_TENANTS;

  return {
    contacts: contactsData,
    invoices: invoicesData,
    forecast: forecastData,
    proposals: proposalsData,
    actionLog: logData,
    outbox: outboxData,
    metrics: metricsData,
    research: researchData,
    settings: settingsData,
    dataSource: dataSourceData,
    appStoreReadiness: appStoreReadinessData,
    aiStatus: aiStatusData,
    xeroStatus: xeroStatusData,
    xeroTenants: xeroTenantsData,
    bills: billsData
  };
}

export async function approveProposal(id) {
  if (!USE_FIXTURES) return request(`/api/proposals/${id}/approve`, { method: "POST" });
  const state = await ensureLocalState();
  const proposal = state.proposals.find((item) => item.id === id);
  if (!proposal || proposal.status !== "pending") return null;
  proposal.status = "approved";
  if (proposal.type === "reminder" || proposal.type === "escalation") {
    state.outbox.unshift({
      id: `outbox-${id}`,
      timestamp: nowIso(),
      to: proposal.contact_name,
      to_email: proposal.contact_email || "",
      subject: proposal.draft_subject,
      body: proposal.draft_body,
      invoice_id: proposal.invoice_id,
      proposal_id: id
    });
  }
  state.action_log.unshift({
    id: `log-${id}`,
    timestamp: nowIso(),
    actor: "You",
    event:
      proposal.type === "reminder" || proposal.type === "escalation"
        ? `Approved a ${proposalActionLabel(proposal)} for ${proposal.contact_name}. The draft is waiting in Outbox.`
        : `Approved a ${proposalActionLabel(proposal)} for ${proposal.contact_name}.`
  });
  recomputeLocalMetrics(state);
  return { proposal };
}

export async function dismissProposal(id) {
  if (!USE_FIXTURES) return request(`/api/proposals/${id}/dismiss`, { method: "POST" });
  const state = await ensureLocalState();
  const proposal = state.proposals.find((item) => item.id === id);
  if (proposal) {
    proposal.status = "dismissed";
    state.action_log.unshift({
      id: `dismiss-${id}`,
      timestamp: nowIso(),
      actor: "You",
      event: `Dismissed the suggestion for ${proposal.contact_name}.`
    });
  }
  return proposal;
}

export async function editProposal(id, draftBody) {
  if (!USE_FIXTURES) {
    return request(`/api/proposals/${id}/edit`, {
      method: "POST",
      body: JSON.stringify({ draft_body: draftBody })
    });
  }
  const state = await ensureLocalState();
  const proposal = state.proposals.find((item) => item.id === id);
  if (proposal) {
    proposal.draft_body = draftBody;
    state.action_log.unshift({
      id: `edit-${id}`,
      timestamp: nowIso(),
      actor: "You",
      event: `Edited the draft message for ${proposal.contact_name}.`
    });
  }
  return proposal;
}

export async function polishProposal(id, draftBody) {
  if (!USE_FIXTURES) {
    return request(`/api/proposals/${id}/polish`, {
      method: "POST",
      body: JSON.stringify({ draft_body: draftBody })
    });
  }
  const state = await ensureLocalState();
  const proposal = state.proposals.find((item) => item.id === id);
  return { proposal, ai: { status: "skipped", reason: "AI draft polishing is disabled in fixture mode." } };
}

export async function findActions() {
  if (!USE_FIXTURES) return request("/api/agent/run", { method: "POST" });
  const state = await ensureLocalState();
  state.action_log.unshift({
    id: `agent-${Date.now()}`,
    timestamp: nowIso(),
    actor: "Nero",
    event: "No new actions needed right now."
  });
  return { created: [], pending_count: state.proposals.filter((item) => item.status === "pending").length };
}

export async function markPaid(invoiceId) {
  if (!USE_FIXTURES) {
    return request("/api/demo/mark_paid", {
      method: "POST",
      body: JSON.stringify({ invoice_id: invoiceId })
    });
  }
  const state = await ensureLocalState();
  const invoice = state.invoices.find((item) => item.id === invoiceId);
  state.invoices = state.invoices.filter((item) => item.id !== invoiceId);
  state.action_log.unshift({
    id: `paid-${invoiceId}`,
    timestamp: nowIso(),
    actor: "You",
    event: invoice ? `Payment received - ${invoice.invoice_number}` : "Payment received"
  });
  return { invoice };
}

export async function scanResearch() {
  if (!USE_FIXTURES) return request("/api/research/scan", { method: "POST" });
  const state = await ensureLocalState();
  return state.research;
}

export async function syncXero() {
  if (!USE_FIXTURES) {
    let response;
    try {
      response = await fetch(`${API_BASE}/api/sync`, { method: "POST" });
    } catch {
      return {
        status: "sync_failed",
        detail: "Nero could not reach the sync service."
      };
    }
    let payload = {};
    try {
      payload = await response.json();
    } catch {
      payload = {};
    }
    if (!response.ok) {
      const retryAfter = Number.parseInt(response.headers.get("Retry-After") || "", 10);
      return {
        status: response.status === 503 ? "rate_limited" : "sync_failed",
        detail: payload.detail || payload.message || `${response.status} ${response.statusText}`,
        http_status: response.status,
        retry_after_seconds: Number.isFinite(retryAfter) ? retryAfter : null
      };
    }
    return payload;
  }
  const state = await ensureLocalState();
  return {
    status: "demo",
    contacts: state.contacts.length,
    invoices: state.invoices.length,
    proposals: state.proposals.length,
    detail: "Local data is active."
  };
}

export async function disconnectXero() {
  if (!USE_FIXTURES) return request("/auth/connection", { method: "DELETE" });
  const state = await ensureLocalState();
  state.xeroStatus = {
    ...state.xeroStatus,
    connected: false,
    tenant_id: null,
    expires_at: null,
    needs_tenant: false
  };
  return {
    status: "disconnected",
    detail: "Local Xero OAuth tokens were removed. Reconnect Xero before syncing again.",
    xero: state.xeroStatus
  };
}

export async function selectXeroTenant(tenantId) {
  if (!USE_FIXTURES) {
    return request("/api/xero/tenant", {
      method: "POST",
      body: JSON.stringify({ tenant_id: tenantId })
    });
  }
  const state = await ensureLocalState();
  state.xeroTenants.active_tenant_id = tenantId;
  return { status: "selected", tenant: { tenant_id: tenantId } };
}

export async function updateCashFloor(cashFloor, mode = "manual") {
  const payload = { cash_floor_mode: mode };
  if (mode === "manual") payload.cash_floor = Math.max(0, Number(cashFloor || 0));
  if (!USE_FIXTURES) {
    return request("/api/settings", {
      method: "PATCH",
      body: JSON.stringify(payload)
    });
  }
  const state = await ensureLocalState();
  const nextFloor = mode === "suggested" ? Number(state.settings.suggested_cash_floor || state.settings.cash_floor || 0) : payload.cash_floor;
  state.settings.cash_floor = nextFloor;
  state.settings.cash_floor_mode = mode;
  state.action_log.unshift({
    id: `cash-floor-${Date.now()}`,
    timestamp: nowIso(),
    actor: "You",
    event: `Minimum cash changed to £${money(nextFloor)}.`
  });
  return state.settings;
}

export async function seedSyntheticPortfolio() {
  if (!USE_FIXTURES) return request("/api/synthetic/seed", { method: "POST" });
  const state = await ensureLocalState();
  state.action_log.unshift({
    id: `seed-${Date.now()}`,
    timestamp: nowIso(),
    actor: "System",
    event: "Synthetic portfolio seed is available in live backend mode."
  });
  return {
    status: "seeded",
    contacts: state.contacts.length,
    invoices: state.invoices.length,
    proposals: state.proposals.length,
    source: state.dataSource
  };
}

export { money };

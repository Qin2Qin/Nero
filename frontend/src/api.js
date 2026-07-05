import contacts from "../../fixtures/contacts.json";
import invoices from "../../fixtures/invoices.json";
import forecast from "../../fixtures/forecast.json";
import proposals from "../../fixtures/proposals.json";
import actionLog from "../../fixtures/action_log.json";

const API_BASE = import.meta.env.VITE_API_BASE || "";
const USE_FIXTURES = import.meta.env.VITE_DEMO === "true";

export const XERO_LOGIN_URL = `${API_BASE}/auth/login`;

export function statementUrl(contactId) {
  return `${API_BASE}/api/statements/${encodeURIComponent(contactId)}`;
}

const localState = {
  contacts: structuredClone(contacts),
  invoices: structuredClone(invoices),
  forecast: structuredClone(forecast),
  proposals: structuredClone(proposals),
  action_log: structuredClone(actionLog),
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
  settings: { cash_floor: forecast.cash_floor },
  dataSource: {
    mode: "fixture",
    label: "Offline portfolio",
    detail: "Offline data is loaded because the backend is unavailable.",
    generated_at: null
  },
  appStoreReadiness: {
    status: "draft",
    ready_count: 4,
    total_count: 6,
    source_url: "https://developer.xero.com/documentation/xero-app-store/app-partner-guides/certification-checkpoints/",
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
        detail: "Reads contacts, invoices and payments before queuing approved messages for review."
      },
      {
        id: "listing",
        label: "App Store listing",
        status: "ready",
        detail: "Submission notes are drafted in docs/xero-app-store-submission.md."
      },
      {
        id: "support-security",
        label: "Support and security",
        status: "ready",
        detail: "Support, privacy, retention and security notes are drafted in docs/support.md and docs/privacy-security.md."
      }
    ]
  },
  xeroStatus: {
    connected: false,
    tenant_id: null,
    expires_at: null,
    needs_tenant: false,
    demo_mode: true,
    client_credentials_configured: false,
    env_tokens_configured: false,
    env_refresh_token_configured: false,
    redirect_uri: "http://localhost:8000/auth/callback"
  },
  xeroTenants: { active_tenant_id: null, tenants: [] }
};

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

function buildAgedReceivables(invoices, asOf = localState.forecast.as_of || nowIso().slice(0, 10)) {
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
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options
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

function buildLocalForecast() {
  const cashFloor = localState.settings.cash_floor;
  return {
    ...localState.forecast,
    as_of: localState.forecast.as_of || "2026-07-04",
    cash_floor: cashFloor,
    buckets: localState.forecast.buckets.map((bucket) => ({
      ...bucket,
      below_floor: bucket.cumulative_predicted < cashFloor
    }))
  };
}

function proposalRollup(status) {
  const proposalsForStatus = localState.proposals.filter((proposal) => proposal.status === status);
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

function recomputeLocalMetrics() {
  const approved = proposalRollup("approved");
  const pending = proposalRollup("pending");
  localState.metrics = {
    cash_accelerated_dollars: approved.impact_dollars,
    avg_days_accelerated: approved.avg_days_accelerated,
    approved_actions_count: approved.actions_count,
    pending_impact_dollars: pending.impact_dollars,
    pending_avg_days_accelerated: pending.avg_days_accelerated,
    pending_actions_count: pending.actions_count,
    aged_receivables: buildAgedReceivables(localState.invoices)
  };
}

export async function fetchAll() {
  if (USE_FIXTURES) {
    recomputeLocalMetrics();
    return {
      contacts: localState.contacts,
      invoices: localState.invoices,
      forecast: buildLocalForecast(),
      proposals: localState.proposals,
      actionLog: localState.action_log,
      outbox: localState.outbox,
      metrics: localState.metrics,
      research: localState.research,
      settings: localState.settings,
      dataSource: localState.dataSource,
      appStoreReadiness: localState.appStoreReadiness,
      xeroStatus: localState.xeroStatus,
      xeroTenants: localState.xeroTenants
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
    xeroStatusData,
    xeroTenantsData
  ] =
    await Promise.all([
      request("/api/contacts"),
      request("/api/invoices"),
      request("/api/forecast"),
      request("/api/proposals"),
      request("/api/action_log"),
      request("/api/outbox"),
      request("/api/metrics"),
      request("/api/research/status"),
      request("/api/settings"),
      request("/api/data_source"),
      request("/api/app_store/readiness"),
      request("/api/xero/status"),
      optionalRequest("/api/xero/tenants", { active_tenant_id: null, tenants: [] })
    ]);

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
    xeroStatus: xeroStatusData,
    xeroTenants: xeroTenantsData
  };
}

export async function approveProposal(id) {
  if (!USE_FIXTURES) return request(`/api/proposals/${id}/approve`, { method: "POST" });
  const proposal = localState.proposals.find((item) => item.id === id);
  if (!proposal || proposal.status !== "pending") return null;
  proposal.status = "approved";
  if (proposal.type === "reminder" || proposal.type === "escalation") {
    localState.outbox.unshift({
      id: `outbox-${id}`,
      timestamp: nowIso(),
      to: proposal.contact_name,
      subject: proposal.draft_subject,
      body: proposal.draft_body,
      invoice_id: proposal.invoice_id,
      proposal_id: id
    });
  }
  localState.action_log.unshift({
    id: `log-${id}`,
    timestamp: nowIso(),
    actor: "You",
    event:
      proposal.type === "reminder" || proposal.type === "escalation"
        ? `Approved a ${proposalActionLabel(proposal)} for ${proposal.contact_name}. The draft is waiting in Outbox.`
        : `Approved a ${proposalActionLabel(proposal)} for ${proposal.contact_name}.`
  });
  recomputeLocalMetrics();
  return { proposal };
}

export async function dismissProposal(id) {
  if (!USE_FIXTURES) return request(`/api/proposals/${id}/dismiss`, { method: "POST" });
  const proposal = localState.proposals.find((item) => item.id === id);
  if (proposal) {
    proposal.status = "dismissed";
    localState.action_log.unshift({
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
  const proposal = localState.proposals.find((item) => item.id === id);
  if (proposal) {
    proposal.draft_body = draftBody;
    localState.action_log.unshift({
      id: `edit-${id}`,
      timestamp: nowIso(),
      actor: "You",
      event: `Edited the draft message for ${proposal.contact_name}.`
    });
  }
  return proposal;
}

export async function runAgent() {
  if (!USE_FIXTURES) return request("/api/agent/run", { method: "POST" });
  localState.action_log.unshift({
    id: `agent-${Date.now()}`,
    timestamp: nowIso(),
    actor: "Nero",
    event: "No new actions needed right now."
  });
  return { created: [], pending_count: localState.proposals.filter((item) => item.status === "pending").length };
}

export async function markPaid(invoiceId) {
  if (!USE_FIXTURES) {
    return request("/api/demo/mark_paid", {
      method: "POST",
      body: JSON.stringify({ invoice_id: invoiceId })
    });
  }
  const invoice = localState.invoices.find((item) => item.id === invoiceId);
  localState.invoices = localState.invoices.filter((item) => item.id !== invoiceId);
  localState.action_log.unshift({
    id: `paid-${invoiceId}`,
    timestamp: nowIso(),
    actor: "You",
    event: invoice ? `Payment received - ${invoice.invoice_number}` : "Payment received"
  });
  return { invoice };
}

export async function scanResearch() {
  if (!USE_FIXTURES) return request("/api/research/scan", { method: "POST" });
  return localState.research;
}

export async function syncXero() {
  if (!USE_FIXTURES) return request("/api/sync", { method: "POST" });
  return {
    status: "demo",
    contacts: localState.contacts.length,
    invoices: localState.invoices.length,
    proposals: localState.proposals.length,
    detail: "Local data is active."
  };
}

export async function selectXeroTenant(tenantId) {
  if (!USE_FIXTURES) {
    return request("/api/xero/tenant", {
      method: "POST",
      body: JSON.stringify({ tenant_id: tenantId })
    });
  }
  localState.xeroTenants.active_tenant_id = tenantId;
  return { status: "selected", tenant: { tenant_id: tenantId } };
}

export async function updateCashFloor(cashFloor) {
  const payload = { cash_floor: Math.max(0, Number(cashFloor || 0)) };
  if (!USE_FIXTURES) {
    return request("/api/settings", {
      method: "PATCH",
      body: JSON.stringify(payload)
    });
  }
  localState.settings.cash_floor = payload.cash_floor;
  localState.action_log.unshift({
    id: `cash-floor-${Date.now()}`,
    timestamp: nowIso(),
    actor: "You",
    event: `Cash floor changed to £${money(payload.cash_floor)}.`
  });
  return localState.settings;
}

export async function seedSyntheticPortfolio() {
  if (!USE_FIXTURES) return request("/api/synthetic/seed", { method: "POST" });
  localState.action_log.unshift({
    id: `seed-${Date.now()}`,
    timestamp: nowIso(),
    actor: "System",
    event: "Synthetic portfolio seed is available in live backend mode."
  });
  return {
    status: "seeded",
    contacts: localState.contacts.length,
    invoices: localState.invoices.length,
    proposals: localState.proposals.length,
    source: localState.dataSource
  };
}

export { money };

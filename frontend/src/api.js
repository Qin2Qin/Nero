import contacts from "../../fixtures/contacts.json";
import invoices from "../../fixtures/invoices.json";
import forecast from "../../fixtures/forecast.json";
import proposals from "../../fixtures/proposals.json";
import actionLog from "../../fixtures/action_log.json";

const API_BASE = import.meta.env.VITE_API_BASE || "";
const USE_FIXTURES = import.meta.env.VITE_DEMO === "true";

const localState = {
  contacts: structuredClone(contacts),
  invoices: structuredClone(invoices),
  forecast: structuredClone(forecast),
  proposals: structuredClone(proposals),
  action_log: structuredClone(actionLog),
  outbox: [],
  metrics: { cash_accelerated_dollars: 0, avg_days_accelerated: 0 },
  research: { generated_at: null, sources: {}, files: [] },
  settings: { cash_floor: forecast.cash_floor, cash_floor_mode: "manual", suggested_cash_floor: forecast.cash_floor },
  dataSource: {
    mode: "fixture",
    label: "Offline portfolio",
    detail: "Offline data is loaded because the backend is unavailable.",
    generated_at: null
  },
  appStoreReadiness: {
    status: "draft",
    ready_count: 3,
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
        status: "todo",
        detail: "Prepare category, screenshots, pricing, support URL, privacy URL and advisor-facing recommendation copy."
      },
      {
        id: "support-security",
        label: "Support and security",
        status: "todo",
        detail: "Add support docs, data retention notes, error recovery copy and security self-assessment evidence."
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

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options
  });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
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
    cash_floor: cashFloor,
    buckets: localState.forecast.buckets.map((bucket) => ({
      ...bucket,
      below_floor: bucket.cumulative_predicted < cashFloor
    }))
  };
}

function recomputeLocalMetrics() {
  const approved = localState.proposals.filter((proposal) => proposal.status === "approved");
  const dollars = approved.reduce((sum, proposal) => sum + proposal.expected_impact_dollars, 0);
  const weightedDays = approved.reduce(
    (sum, proposal) => sum + proposal.expected_impact_dollars * proposal.expected_days_accelerated,
    0
  );
  localState.metrics = {
    cash_accelerated_dollars: dollars,
    avg_days_accelerated: dollars ? Math.round((weightedDays / dollars) * 10) / 10 : 0
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
        ? `Approved ${proposal.type} for ${proposal.contact_name} and queued message for review`
        : `Recommendation accepted - apply on next quote for ${proposal.contact_name}`
  });
  recomputeLocalMetrics();
  return { proposal };
}

export async function dismissProposal(id) {
  if (!USE_FIXTURES) return request(`/api/proposals/${id}/dismiss`, { method: "POST" });
  const proposal = localState.proposals.find((item) => item.id === id);
  if (proposal) proposal.status = "dismissed";
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
  if (proposal) proposal.draft_body = draftBody;
  return proposal;
}

export async function runAgent() {
  if (!USE_FIXTURES) return request("/api/agent/run", { method: "POST" });
  localState.action_log.unshift({
    id: `agent-${Date.now()}`,
    timestamp: nowIso(),
    actor: "Agent",
    event: "Agent run complete - existing proposals reviewed"
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

export async function updateCashFloor(cashFloor, mode = "manual") {
  const payload =
    mode === "suggested"
      ? { cash_floor_mode: "suggested" }
      : { cash_floor: Math.max(0, Number(cashFloor || 0)), cash_floor_mode: "manual" };
  if (!USE_FIXTURES) {
    return request("/api/settings", {
      method: "PATCH",
      body: JSON.stringify(payload)
    });
  }
  const value = mode === "suggested" ? localState.settings.suggested_cash_floor : payload.cash_floor;
  localState.settings.cash_floor = value;
  localState.settings.cash_floor_mode = mode;
  localState.action_log.unshift({
    id: `cash-floor-${Date.now()}`,
    timestamp: nowIso(),
    actor: "You",
    event: `Cash floor changed to GBP ${money(value)} (${mode})`
  });
  return localState.settings;
}

export async function approveProposalsBatch(ids) {
  if (!USE_FIXTURES) {
    return request("/api/proposals/approve_batch", {
      method: "POST",
      body: JSON.stringify({ ids })
    });
  }
  const results = [];
  for (const id of ids) {
    results.push({ proposal_id: id, ...(await approveProposal(id)) });
  }
  return { results, pending_count: localState.proposals.filter((item) => item.status === "pending").length };
}

export async function undoProposal(id) {
  if (!USE_FIXTURES) return request(`/api/proposals/${id}/undo`, { method: "POST" });
  const proposal = localState.proposals.find((item) => item.id === id);
  if (!proposal) return null;
  if (proposal.status === "approved") {
    localState.outbox = localState.outbox.filter((entry) => entry.proposal_id !== id);
  }
  proposal.status = "pending";
  localState.action_log.unshift({
    id: `undo-${id}`,
    timestamp: nowIso(),
    actor: "You",
    event: `Undid ${proposal.type} for ${proposal.contact_name}`
  });
  recomputeLocalMetrics();
  return proposal;
}

export async function createManualProposal(contactId, kind) {
  if (!USE_FIXTURES) {
    return request("/api/proposals/manual", {
      method: "POST",
      body: JSON.stringify({ contact_id: contactId, kind })
    });
  }
  const contact = localState.contacts.find((item) => item.id === contactId);
  if (!contact) return null;
  const id = `manual-${kind}-${contactId}-${Date.now()}`;
  let proposal;
  if (kind === "reminder") {
    const invoice = localState.invoices.find((item) => item.contact_id === contactId);
    proposal = {
      id,
      type: "reminder",
      contact_id: contactId,
      contact_name: contact.name,
      invoice_id: invoice?.id || null,
      reasoning_text: `Manually drafted from Customers for ${contact.name}.`,
      draft_subject: invoice ? `Reminder: ${invoice.invoice_number} due ${invoice.due_date}` : `Checking in, ${contact.name}`,
      draft_body: invoice
        ? `Hi ${contact.name},\n\nJust checking in on ${invoice.invoice_number} for $${money(invoice.amount_due)}. Let me know if you have any questions.\n\nThanks,\nHarbour & Co`
        : `Hi ${contact.name},\n\nChecking in on your account with us. Let me know if you have any questions.\n\nThanks,\nHarbour & Co`,
      recommendation_detail: null,
      expected_impact_dollars: invoice ? invoice.amount_due : 0,
      expected_days_accelerated: 7,
      status: "pending"
    };
  } else {
    const exposure = localState.invoices
      .filter((item) => item.contact_id === contactId)
      .reduce((sum, item) => sum + Number(item.amount_due || 0), 0);
    proposal = {
      id,
      type: "deposit_recommendation",
      contact_id: contactId,
      contact_name: contact.name,
      invoice_id: null,
      reasoning_text: `Manually drafted from Customers. ${contact.name} pays about ${Math.max(0, Math.round(contact.avg_days_late))} days late on average.`,
      draft_subject: null,
      draft_body: null,
      recommendation_detail: `Add a 30% deposit on the next quote for ${contact.name} before work begins.`,
      expected_impact_dollars: Math.round(exposure * 0.3),
      expected_days_accelerated: 14,
      status: "pending"
    };
  }
  localState.proposals.unshift(proposal);
  localState.action_log.unshift({
    id: `log-${id}`,
    timestamp: nowIso(),
    actor: "You",
    event: `Drafted ${kind === "reminder" ? "reminder" : "deposit recommendation"} for ${contact.name}`
  });
  return proposal;
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

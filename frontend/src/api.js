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
  research: { generated_at: null, sources: {}, files: [] }
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

function buildLocalForecast() {
  return localState.forecast;
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
      research: localState.research
    };
  }

  const [contactsData, invoicesData, forecastData, proposalsData, logData, outboxData, metricsData, researchData] =
    await Promise.all([
      request("/api/contacts"),
      request("/api/invoices"),
      request("/api/forecast"),
      request("/api/proposals"),
      request("/api/action_log"),
      request("/api/outbox"),
      request("/api/metrics"),
      request("/api/research/status")
    ]);

  return {
    contacts: contactsData,
    invoices: invoicesData,
    forecast: forecastData,
    proposals: proposalsData,
    actionLog: logData,
    outbox: outboxData,
    metrics: metricsData,
    research: researchData
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
        ? `Approved ${proposal.type} for ${proposal.contact_name} and queued sandbox email`
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
    event: "Agent run complete - fixture proposals already loaded"
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

export { money };

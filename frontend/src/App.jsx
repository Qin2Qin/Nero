import {
  BookOpen,
  Bot,
  Check,
  ChevronDown,
  ChevronUp,
  ClipboardList,
  Database,
  ExternalLink,
  FileText,
  HelpCircle,
  LayoutDashboard,
  LogOut,
  Minus,
  Play,
  RefreshCw,
  Search,
  Send,
  Sparkles,
  TrendingDown,
  TrendingUp,
  Users,
  X
} from "lucide-react";
import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import {
  approveProposal,
  disconnectXero,
  dismissProposal,
  editProposal,
  fetchAll,
  findActions,
  markPaid,
  money,
  polishProposal,
  scanResearch,
  seedSyntheticPortfolio,
  selectXeroTenant,
  statementUrl,
  syncXero,
  updateCashFloor,
  XERO_LOGIN_URL
} from "./api.js";

const ForecastChart = lazy(() => import("./ForecastChart.jsx"));

const TABS = [
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
  { id: "payers", label: "Payers", icon: Users },
  { id: "queue", label: "Actions", icon: Bot },
  { id: "outbox", label: "Outbox", icon: Send }
];

const SUPPORT_EMAIL = import.meta.env.VITE_SUPPORT_EMAIL || "support@nero.cash";
const MOBILE_INVOICE_PREVIEW_COUNT = 8;
const DEV_TOOLS_ENABLED = import.meta.env.VITE_ENABLE_DEV_TOOLS === "true";

function parseDate(value) {
  return new Date(`${value}T00:00:00Z`);
}

function forecastAsOfValue(forecast) {
  return forecast?.as_of || new Date().toISOString().slice(0, 10);
}

function todayForForecast(forecast) {
  return parseDate(forecastAsOfValue(forecast));
}

function addDays(date, days) {
  const next = new Date(date);
  next.setUTCDate(next.getUTCDate() + days);
  return next;
}

function formatCurrency(value) {
  return `£${money(Math.round(Number(value || 0)))}`;
}

function formatHeroCurrency(value) {
  return `£${money(Math.round(Number(value || 0) / 1000) * 1000)}`;
}

function formatDateTime(value) {
  if (!value) return "";
  return new Intl.DateTimeFormat("en-GB", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date(value));
}

function formatDate(value) {
  if (!value) return "Not saved";
  return new Intl.DateTimeFormat("en-GB", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date(value));
}

function formatWeekLabel(value) {
  if (!value || value === "later") return "Later";
  return new Intl.DateTimeFormat("en-GB", {
    month: "short",
    day: "numeric"
  }).format(parseDate(value));
}

function formatShortDate(value) {
  return new Intl.DateTimeFormat("en-GB", {
    month: "short",
    day: "numeric"
  }).format(parseDate(value));
}

function daysBetween(start, end) {
  return Math.round((parseDate(end) - parseDate(start)) / 86400000);
}

function invoiceTimingText(dateValue, asOfValue) {
  const days = daysBetween(asOfValue, dateValue);
  if (days < 0) {
    const count = Math.abs(days);
    return `${count} ${plural(count, "day")} overdue`;
  }
  if (days === 0) return "Due today";
  return `Due in ${days} ${plural(days, "day")}`;
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

function agedReceivablesFromInvoices(invoices, asOfValue) {
  const buckets = AGING_BUCKETS.map((bucket) => ({ ...bucket, invoice_count: 0, amount_due: 0 }));
  const byId = new Map(buckets.map((bucket) => [bucket.id, bucket]));
  let openTotal = 0;
  let overdueTotal = 0;

  for (const invoice of invoices || []) {
    const dueDate = parseDate(invoice.due_date);
    if (Number.isNaN(dueDate.getTime())) continue;
    const amount = Math.round(Number(invoice.amount_due || 0));
    const daysLate = daysBetween(invoice.due_date, asOfValue);
    const bucket = byId.get(agingBucketId(daysLate));
    bucket.invoice_count += 1;
    bucket.amount_due += amount;
    openTotal += amount;
    if (daysLate > 0) overdueTotal += amount;
  }

  return {
    as_of: asOfValue,
    open_total: openTotal,
    overdue_total: overdueTotal,
    buckets
  };
}

function gradeClass(grade) {
  return `grade grade-${String(grade).charAt(0).toLowerCase()}`;
}

function reliabilityLabel(contact) {
  const grade = String(contact?.grade || "").toUpperCase();
  if (grade.includes("LOW DATA")) return "Low history";
  if (grade.startsWith("A")) return "Reliable";
  if (grade.startsWith("B")) return "Mostly on time";
  if (grade.startsWith("C")) return "Watch";
  if (grade.startsWith("D")) return "Often late";
  if (grade.startsWith("E")) return "High risk";
  return "Unknown";
}

function TrendCell({ slope }) {
  if (slope > 1) return <span className="trend-cell trend-up"><TrendingUp size={15} /> worsening</span>;
  if (slope < -1) return <span className="trend-cell trend-down"><TrendingDown size={15} /> improving</span>;
  return <span className="trend-cell trend-flat"><Minus size={15} /> steady</span>;
}

// Cash currently tied up with a payer: the sum of their open invoices.
function exposureFor(contactId, invoices) {
  return invoices
    .filter((invoice) => invoice.contact_id === contactId)
    .reduce((sum, invoice) => sum + Number(invoice.amount_due || 0), 0);
}

function useCountUp(value) {
  const [display, setDisplay] = useState(value);

  useEffect(() => {
    const start = display;
    const delta = value - start;
    if (delta === 0) return;
    let frame = 0;
    const frames = 24;
    const timer = window.setInterval(() => {
      frame += 1;
      const progress = 1 - Math.pow(1 - frame / frames, 3);
      setDisplay(Math.round(start + delta * progress));
      if (frame >= frames) window.clearInterval(timer);
    }, 16);
    return () => window.clearInterval(timer);
  }, [value]);

  return display;
}

function compactMoney(value) {
  const v = Number(value || 0);
  if (Math.abs(v) >= 1000) return `£${Math.round(v / 1000)}k`;
  return `£${Math.round(v)}`;
}

function plural(count, singular, pluralForm = `${singular}s`) {
  return Number(count) === 1 ? singular : pluralForm;
}

function trendText(slope) {
  if (Number(slope || 0) > 1) return "and it's getting slower";
  if (Number(slope || 0) < -1) return "and it's getting better";
  return "and that's been steady";
}

function paymentTimingText(daysLate) {
  const rounded = Math.round(Number(daysLate || 0));
  if (rounded < 0) {
    const days = Math.abs(rounded);
    return `${days} ${plural(days, "day")} early`;
  }
  if (rounded === 0) return "on time";
  return `${rounded} ${plural(rounded, "day")} late`;
}

function averagePaymentTimingText(daysLate) {
  const rounded = Math.round(Number(daysLate || 0));
  if (rounded < 0) {
    const days = Math.abs(rounded);
    return `${days} ${plural(days, "day")} early`;
  }
  return `${rounded} ${plural(rounded, "day")} late`;
}

function payerTimingSentence(contact) {
  const invoiceCount = Number(contact.invoice_count || 0);
  const unpredictable = Number(contact.stdev_days_late || 0) >= 10 ? ", though timing can be unpredictable" : "";
  const timing = averagePaymentTimingText(contact.avg_days_late);
  if (contact.low_confidence || invoiceCount < 3) {
    return `Based on ${invoiceCount} paid ${plural(invoiceCount, "invoice")}, Nero estimates ${contact.name} pays on average ${timing} until more payment history comes in${unpredictable}, ${trendText(contact.trend_slope)}.`;
  }
  return `Based on ${invoiceCount} paid ${plural(invoiceCount, "invoice")}, ${contact.name} pays on average ${timing}${unpredictable}, ${trendText(contact.trend_slope)}.`;
}

function proposalActionCopy(proposal) {
  const hasDraft = Boolean(proposal.draft_subject);
  const labels = {
    reminder: "Send reminder",
    escalation: "Send firmer reminder",
    deposit_recommendation: "Ask for deposit",
    terms_recommendation: "Change payment terms"
  };
  const reasons = {
    reminder: `Nero has prepared a payment reminder for ${proposal.contact_name}. Review the wording before it goes out.`,
    escalation: `${proposal.contact_name} needs a firmer payment nudge. Nero has drafted one for you to approve first.`,
    deposit_recommendation: `${proposal.contact_name} is creating cash pressure. Ask for a deposit before starting the next job.`,
    terms_recommendation: `${proposal.contact_name} is slowing cash down. Tighten the payment terms before the next invoice.`
  };

  return {
    label: labels[proposal.type] || "Review suggestion",
    reason: reasons[proposal.type] || proposal.reasoning_text,
    approveLabel: hasDraft ? "Approve draft" : "Approve recommendation"
  };
}

function proposalActionPriority(proposal) {
  if (proposal.draft_subject && proposal.contact_email) return 0;
  if (!proposal.draft_subject) return 1;
  return 2;
}

function approvalOutcomeText(proposal, dataSource) {
  if (!proposal.draft_subject) return "Approve to record this decision in Activity. Nothing is sent automatically.";
  if (dataSource?.mode === "xero" && proposal.invoice_id) {
    return "Approve to keep the email in Outbox and add an internal note to the Xero invoice. Nothing is sent automatically.";
  }
  return "Approve to keep the draft in Outbox. Nothing is sent automatically.";
}

function compareSortValues(a, b) {
  const aMissing = a === null || a === undefined || a === "";
  const bMissing = b === null || b === undefined || b === "";
  if (aMissing && bMissing) return 0;
  if (aMissing) return 1;
  if (bMissing) return -1;
  if (typeof a === "number" && typeof b === "number") return a - b;
  return String(a).localeCompare(String(b), undefined, { numeric: true, sensitivity: "base" });
}

function sortRows(rows, sort, accessors) {
  const accessor = accessors[sort.key];
  if (!accessor) return rows;
  const direction = sort.direction === "desc" ? -1 : 1;
  return [...rows].sort((a, b) => compareSortValues(accessor(a), accessor(b)) * direction);
}

function useSort(defaultKey, defaultDirection = "asc") {
  const [sort, setSort] = useState({ key: defaultKey, direction: defaultDirection });
  function requestSort(key, firstDirection = "asc") {
    setSort((current) => {
      if (current.key !== key) return { key, direction: firstDirection };
      return { key, direction: current.direction === "asc" ? "desc" : "asc" };
    });
  }
  return [sort, requestSort];
}

function useDebouncedValue(value, delayMs = 200) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(timer);
  }, [value, delayMs]);
  return debounced;
}

function SortableHeader({ label, sortKey, sort, onSort, align = "left", defaultDirection = "asc" }) {
  const active = sort.key === sortKey;
  const Icon = active && sort.direction === "asc" ? ChevronUp : ChevronDown;
  return (
    <th className={align === "right" ? "right sortable-th" : "sortable-th"}>
      <button
        className={active ? "sort-button active" : "sort-button"}
        type="button"
        onClick={() => onSort(sortKey, defaultDirection)}
      >
        <span>{label}</span>
        <Icon className={active ? "sort-icon active" : "sort-icon"} size={13} aria-hidden="true" />
      </button>
    </th>
  );
}

function businessNameFor(source) {
  if (source?.business?.name) return source.business.name;
  if (source?.mode === "xero" && source?.label) return source.label.replace(/^Xero:\s*/i, "");
  return "Your business";
}

function selectedXeroTenantId(status, tenants) {
  return tenants?.active_tenant_id || status?.tenant_id || "";
}

function xeroDashboardNeedsSync(source, status, tenants) {
  const selectedTenantId = selectedXeroTenantId(status, tenants);
  return Boolean(source?.mode === "xero" && source?.tenant_id && selectedTenantId && source.tenant_id !== selectedTenantId);
}

function xeroConnectedNeedsInitialSync(source, status) {
  return Boolean(status?.connected && !status?.demo_mode && !xeroNeedsReconnect(status) && source?.mode !== "xero");
}

function xeroActionBlockReason(source, status, tenants) {
  if (source?.mode !== "xero") return "";
  if (!status?.connected || xeroNeedsReconnect(status)) {
    return "Reconnect Xero before changing actions for this organisation.";
  }
  if (status?.needs_tenant || !selectedXeroTenantId(status, tenants)) return "Select a Xero organisation before changing actions.";
  if (!xeroDashboardNeedsSync(source, status, tenants)) return "";
  return "Sync Xero before changing actions for this organisation.";
}

function xeroBadge(status) {
  if (xeroNeedsReconnect(status)) return { className: "badge badge-error danger", label: "Reconnect Xero" };
  if (status?.connected) return { className: "badge badge-success success", label: "Connected" };
  if (status?.demo_mode) return { className: "badge badge-neutral neutral", label: "Demo mode" };
  return { className: "badge badge-error danger", label: "Not connected" };
}

function xeroNeedsReconnect(status) {
  return Boolean(status?.refresh_error || (status?.connected && status?.expired));
}

function retryAfterCopy(seconds) {
  const numericSeconds = Number(seconds || 0);
  if (!Number.isFinite(numericSeconds) || numericSeconds <= 0) return "";
  if (numericSeconds < 60) return `Try again in about ${Math.ceil(numericSeconds)} seconds.`;
  if (numericSeconds < 3600) {
    const minutes = Math.ceil(numericSeconds / 60);
    return `Try again in about ${minutes} ${plural(minutes, "minute")}.`;
  }
  if (numericSeconds < 86400) {
    const hours = Math.ceil(numericSeconds / 3600);
    return `Try again in about ${hours} ${plural(hours, "hour")}.`;
  }
  const days = Math.ceil(numericSeconds / 86400);
  return `Try again in about ${days} ${plural(days, "day")}.`;
}

function syncSummary(result) {
  if (!result) return "";
  if (result.status === "rate_limited") {
    const retryCopy = retryAfterCopy(result.retry_after_seconds);
    const retrySentence = retryCopy ? ` ${retryCopy}` : "";
    return `${result.detail || "Xero is asking Nero to wait before syncing again."}${retrySentence} Nero is still showing the last successful Xero snapshot.`;
  }
  if (result.status === "sync_failed") {
    return `${result.detail || "Sync could not finish."} Nero is still showing the last saved dashboard.`;
  }
  if (result.status === "connected") {
    return result.detail || "Xero connected. Click Sync Xero to pull the latest records.";
  }
  if (result.status === "error") {
    return result.detail || "Xero connection could not be completed. Try Connect Xero again.";
  }
  if (result.status === "disconnected") {
    return result.detail || "Disconnected Xero locally. Reconnect before syncing again.";
  }
  if (result.status === "synced") {
    const base = `Synced ${result.fetched?.contacts ?? 0} contacts, ${result.fetched?.invoices ?? 0} invoices, ${result.fetched?.payments ?? 0} payments.`;
    if (result.detail) return `${base} ${result.detail}`;
    if (result.materialized) {
      const linkCount = Number(result.materialized.online_invoice_links || 0);
      const linkCopy = linkCount ? ` and ${linkCount} Xero invoice ${plural(linkCount, "link")}` : "";
      return `${base} Dashboard updated with ${result.materialized.contacts ?? 0} payers, ${result.materialized.invoices ?? 0} open invoices${linkCopy}.`;
    }
    return base;
  }
  if (result.status === "demo") {
    return `Demo sync checked ${result.contacts ?? 0} contacts and ${result.invoices ?? 0} invoices.`;
  }
  if (result.status === "seeded") {
    const business = result.source?.business?.name;
    const prefix = business ? `${business}: ` : "";
    return `Seeded ${prefix}${result.contacts ?? 0} companies, ${result.invoices ?? 0} invoices and ${result.proposals ?? 0} proposed actions.`;
  }
  if (result.status === "selected") {
    return `Selected ${result.tenant?.tenant_name || "Xero organisation"}. Run Sync Xero to pull its records.`;
  }
  return result.detail || result.status || "Sync checked.";
}

function syncResultClass(result) {
  if (["rate_limited", "sync_failed"].includes(result?.status)) return "sync-result warning";
  if (result?.status === "error") return "sync-result warning";
  if (result?.empty || result?.materialized === null) return "sync-result warning";
  return "sync-result";
}

function mailtoDraftHref(entry) {
  const subject = encodeURIComponent(entry.subject || "");
  const body = encodeURIComponent(entry.body || "");
  const recipient = encodeURIComponent(entry.to_email || "");
  return `mailto:${recipient}?subject=${subject}&body=${body}`;
}

function outboxSendDisabledReason(entry) {
  if (entry.send_disabled_reason) return entry.send_disabled_reason;
  if (!entry.to_email) return "Add this customer's email address in Xero, then sync Nero.";
  return "";
}

async function copyToClipboard(text) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand("copy");
  document.body.removeChild(textarea);
}

function readinessBadge(status) {
  if (status === "ready") return "badge badge-success success";
  if (status === "blocked") return "badge badge-error danger";
  if (status === "demo") return "badge badge-info";
  return "badge badge-outline neutral";
}

function AppStoreReadiness({ readiness }) {
  const items = readiness?.items || [];

  return (
    <section className="signal-section app-store-readiness">
      <div className="panel-head compact">
        <h2>Xero App Store</h2>
        <span className="badge badge-outline neutral">
          {readiness?.ready_count ?? 0}/{readiness?.total_count ?? items.length} ready
        </span>
      </div>
      <div className="readiness-list">
        {items.map((item) => (
          <div className="readiness-item" key={item.id}>
            <div>
              <strong>{item.label}</strong>
              <p>{item.detail}</p>
            </div>
            <span className={readinessBadge(item.status)}>{item.status}</span>
          </div>
        ))}
      </div>
      {readiness?.source_url && (
        <a className="readiness-link" href={readiness.source_url} target="_blank" rel="noreferrer">
          <ExternalLink size={14} /> Certification checkpoints
        </a>
      )}
    </section>
  );
}

function CashFloorControl({ value, forecast, suggestedCashFloor, billsSummary, onUpdateCashFloor, busy }) {
  const [draft, setDraft] = useState(value || 0);
  const warningCount = forecast?.buckets?.filter((bucket) => bucket.cumulative_predicted < draft).length || 0;
  const isChanged = Number(draft) !== Number(value || 0);
  const suggested = Number(suggestedCashFloor || 0);
  const hasSuggestion = suggested > 0 && suggested !== Number(value || 0);
  const dueNext30 = Number(billsSummary?.due_next_30_amount || 0);
  const maxForecast = Math.max(...(forecast?.buckets || []).map((bucket) => bucket.cumulative_predicted || 0), 15000);
  const maxFloor = Math.max(15000, Math.ceil(Math.max(maxForecast, suggested) / 5000) * 5000);
  const presets = [...new Set([5000, Math.round(maxFloor * 0.45 / 5000) * 5000, Math.round(maxFloor * 0.7 / 5000) * 5000])]
    .filter((preset) => preset > 0 && preset <= maxFloor)
    .slice(0, 3);

  useEffect(() => {
    setDraft(value || 0);
  }, [value]);

  function setPreset(nextValue) {
    setDraft(nextValue);
  }

  return (
    <section className="signal-section cash-floor-control">
      <div className="panel-head compact">
        <h2>Minimum cash</h2>
        <span className={warningCount ? "badge badge-error danger" : "badge badge-success success"}>
          {warningCount ? `${warningCount} weeks below` : "Covered"}
        </span>
      </div>
      <div className="cash-floor-readout">
        <strong>{formatCurrency(draft)}</strong>
        <span>Keep at least this much available</span>
      </div>
      {suggested > 0 && (
        <div className="cash-floor-suggestion">
          <span>Nero suggests {formatCurrency(suggested)} from upcoming bills{dueNext30 ? `, including ${formatCurrency(dueNext30)} due in the next 30 days` : ""}.</span>
          {hasSuggestion && (
            <button className="button ghost btn btn-ghost btn-xs" type="button" onClick={() => onUpdateCashFloor(suggested, "suggested")} disabled={busy}>
              Use suggestion
            </button>
          )}
        </div>
      )}
      <input
        className="range range-primary range-sm range-input"
        type="range"
        min="0"
        max={maxFloor}
        step="500"
        value={draft}
        onChange={(event) => setDraft(Number(event.target.value))}
        aria-label="Minimum cash"
      />
      <div className="preset-row" aria-label="Minimum cash presets">
        {presets.map((preset) => (
          <button
            className={draft === preset ? "preset-chip btn btn-xs active" : "preset-chip btn btn-xs"}
            key={preset}
            type="button"
            onClick={() => setPreset(preset)}
          >
            {compactMoney(preset)}
          </button>
        ))}
      </div>
      <button className="button primary btn btn-primary btn-sm block" onClick={() => onUpdateCashFloor(draft, "manual")} disabled={busy || !isChanged}>
        Apply minimum
      </button>
    </section>
  );
}

function LateInvoicesByAge({ agedReceivables }) {
  const buckets = agedReceivables?.buckets || [];
  const openTotal = Number(agedReceivables?.open_total || 0);
  const overdueTotal = Number(agedReceivables?.overdue_total || 0);

  return (
    <section className="aging-strip" aria-label="Aged receivables">
      <div className="aging-head">
        <span>Late invoices by age</span>
        <strong>{formatCurrency(overdueTotal)} overdue</strong>
      </div>
      <div className="aging-buckets">
        {buckets.map((bucket) => {
          const amount = Number(bucket.amount_due || 0);
          const invoiceCount = Number(bucket.invoice_count || 0);
          const share = openTotal ? Math.round((amount / openTotal) * 100) : 0;
          const width = amount > 0 ? Math.max(6, share) : 0;
          return (
            <div className={bucket.id === "current" ? "aging-bucket" : "aging-bucket late"} key={bucket.id}>
              <div className="aging-bucket-top">
                <span>{bucket.label}</span>
                <strong>{formatCurrency(amount)}</strong>
              </div>
              <div className="aging-bar" aria-hidden="true">
                <span style={{ width: `${width}%` }} />
              </div>
              <em>{invoiceCount} {plural(invoiceCount, "invoice")}</em>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function XeroConnection({ status, source, tenants, syncResult, onSyncXero, onSelectTenant, onDisconnectXero, busy }) {
  const badge = xeroBadge(status);
  const needsReconnect = xeroNeedsReconnect(status);
  const canSync = status?.demo_mode || (status?.connected && !needsReconnect);
  const tenantOptions = tenants?.tenants || [];
  const activeTenant = tenantOptions.find((tenant) => tenant.is_active);
  const credentialState = status?.client_credentials_configured ? "Ready" : "Missing";
  const tokenState = status?.connected
    ? needsReconnect
      ? "Reconnect needed"
      : "Stored"
    : status?.env_tokens_configured || status?.env_refresh_token_configured
      ? "Available in env"
      : "Missing";

  return (
    <section className="signal-section">
      <div className="panel-head compact">
        <h2>Xero connection</h2>
        <span className={badge.className}>{badge.label}</span>
      </div>
      <dl className="status-list">
        <div><dt>Credentials</dt><dd>{credentialState}</dd></div>
        <div><dt>OAuth token</dt><dd>{tokenState}</dd></div>
        <div><dt>Tenant</dt><dd>{activeTenant?.tenant_name || status?.tenant_id || "Not selected"}</dd></div>
        <div><dt>Expires</dt><dd>{formatDate(status?.expires_at)}</dd></div>
        <div><dt>Dashboard data</dt><dd>{source?.label || "Unknown"}</dd></div>
      </dl>
      {tenantOptions.length > 1 && (
        <label className="tenant-picker">
          <span>Xero organisation</span>
          <select
            className="select select-bordered select-sm"
            value={tenants.active_tenant_id || ""}
            onChange={(event) => onSelectTenant(event.target.value)}
            disabled={busy}
          >
            {tenantOptions.map((tenant) => (
              <option key={tenant.tenant_id} value={tenant.tenant_id}>
                {tenant.is_demo ? "Demo - " : ""}{tenant.tenant_name}
              </option>
            ))}
          </select>
        </label>
      )}
      <div className="mini-actions">
        <button className="button primary btn btn-primary btn-sm" onClick={onSyncXero} disabled={busy || !canSync}>
          <RefreshCw size={16} /> {status?.demo_mode ? "Check demo sync" : "Sync Xero"}
        </button>
        {status?.connected && onDisconnectXero && (
          <button className="button ghost btn btn-ghost btn-sm" type="button" onClick={onDisconnectXero} disabled={busy}>
            <LogOut size={16} /> Disconnect
          </button>
        )}
        {needsReconnect && status?.client_credentials_configured && (
          <a className="button ghost btn btn-ghost btn-sm" href={XERO_LOGIN_URL}>
            <ExternalLink size={16} /> Reconnect Xero
          </a>
        )}
        {!status?.demo_mode && !status?.connected && status?.client_credentials_configured && (
          <a className="button ghost btn btn-ghost btn-sm" href={XERO_LOGIN_URL}>
            <ExternalLink size={16} /> Connect
          </a>
        )}
      </div>
      {syncResult && <p className={syncResultClass(syncResult)}>{syncSummary(syncResult)}</p>}
      {needsReconnect && <p className="muted compact-note">{status?.refresh_error || "Reconnect Xero to continue syncing."}</p>}
      {source?.detail && <p className="muted compact-note">{source.detail}</p>}
      {!status?.demo_mode && !status?.connected && !status?.client_credentials_configured && (
        <p className="muted compact-note">Live credentials missing.</p>
      )}
    </section>
  );
}

function ResearchSignals({ sources, onScanResearch, busy }) {
  return (
    <section className="signal-section">
      <div className="panel-head compact">
        <h2>Opportunity monitor</h2>
        <button className="icon-button btn btn-square btn-ghost btn-sm" onClick={onScanResearch} disabled={busy} title="Scan research">
          <RefreshCw size={16} />
        </button>
      </div>
      <div className="research-list">
        {sources.length === 0 && <p className="muted">No raw research files indexed.</p>}
        {sources.map(([source, summary]) => (
          <div className="research-row" key={source}>
            <strong>{source}</strong>
            <span>{summary.files} files</span>
            <span>{summary.records} records</span>
            <em>{summary.changed_files} changed</em>
          </div>
        ))}
      </div>
    </section>
  );
}

function DataSourceBanner({ source, xeroStatus, xeroTenants }) {
  const needsTenantSync = xeroDashboardNeedsSync(source, xeroStatus, xeroTenants);
  const needsInitialXeroSync = xeroConnectedNeedsInitialSync(source, xeroStatus);
  const liveConnected = source?.mode === "xero" && xeroStatus?.connected && !xeroStatus?.demo_mode && !xeroNeedsReconnect(xeroStatus) && !needsTenantSync;
  const business = source?.business;
  const updatedAt = source?.generated_at ? formatDateTime(source.generated_at) : "";
  const detail = needsTenantSync
    ? "Xero organisation changed. Sync Xero to update this dashboard before reviewing actions."
    : needsInitialXeroSync
    ? "Xero is connected. Sync Xero to replace this dashboard with live accounting data."
    : business
    ? `${business.sector} / ${business.country} / ${business.base_currency}`
    : "Cash timing and payer behaviour from your accounting data.";
  return (
    <section className="source-banner">
      <div className="source-copy">
        <strong>{businessNameFor(source)}</strong>
        <p>{detail}</p>
        <div className="source-badges">
          {liveConnected && <span className="badge badge-success success">Xero connected</span>}
          {needsInitialXeroSync && <span className="badge attention">Sync Xero</span>}
          {needsTenantSync && <span className="badge attention">Sync needed</span>}
          {updatedAt && <span className="badge badge-outline neutral">Updated {updatedAt}</span>}
        </div>
      </div>
      <figure className="source-visual-frame">
        <img src="/visuals/nero-cashflow-preview.png" alt="Nero cash forecast board preview" />
      </figure>
    </section>
  );
}

function LiveXeroControls({ status, tenants, source, busy, onSyncXero, onSelectTenant, onDisconnectXero }) {
  if (!status || status.demo_mode) return null;

  if (!status.connected) {
    if (!status.client_credentials_configured) {
      return <span className="badge badge-error danger live-xero-badge">Xero setup needed</span>;
    }
    return (
      <a className="button ghost btn btn-ghost btn-sm" href={XERO_LOGIN_URL}>
        <ExternalLink size={16} /> Connect Xero
      </a>
    );
  }

  if (xeroNeedsReconnect(status)) {
    return (
      <>
        <a className="button ghost btn btn-ghost btn-sm" href={XERO_LOGIN_URL} title={status.refresh_error || "Reconnect Xero to continue syncing."}>
          <ExternalLink size={16} /> Reconnect Xero
        </a>
        {onDisconnectXero && (
          <button
            className="button ghost btn btn-ghost btn-sm"
            type="button"
            onClick={onDisconnectXero}
            disabled={busy}
            title="Remove the local Xero connection from this device"
          >
            <LogOut size={16} /> Disconnect
          </button>
        )}
      </>
    );
  }

  const tenantOptions = tenants?.tenants || [];
  const selectedTenantId = tenants?.active_tenant_id || status.tenant_id || "";
  const shouldPickTenant = status.needs_tenant || tenantOptions.length > 1;
  const syncedAt = source?.mode === "xero" && source?.generated_at ? formatDateTime(source.generated_at) : "";
  const selectedTenant = tenantOptions.find((tenant) => tenant.tenant_id === selectedTenantId);
  const tenantLabel = selectedTenant?.tenant_name || source?.label?.replace(/^Xero:\s*/i, "") || "Xero";

  return (
    <>
      {shouldPickTenant && (
        <select
          className="select select-bordered select-sm live-tenant-select"
          value={selectedTenantId}
          onChange={(event) => onSelectTenant(event.target.value)}
          disabled={busy}
          aria-label="Xero organisation"
        >
          <option value="" disabled>
            Choose organisation
          </option>
          {tenantOptions.map((tenant) => (
            <option key={tenant.tenant_id} value={tenant.tenant_id}>
              {tenant.is_demo ? "Demo - " : ""}{tenant.tenant_name}
            </option>
          ))}
        </select>
      )}
      <button className="button ghost btn btn-ghost btn-sm" type="button" onClick={onSyncXero} disabled={busy || status.needs_tenant}>
        <RefreshCw size={16} /> Sync Xero
      </button>
      {onDisconnectXero && (
        <button
          className="button ghost btn btn-ghost btn-sm"
          type="button"
          onClick={onDisconnectXero}
          disabled={busy}
          title="Remove the local Xero connection from this device"
        >
          <LogOut size={16} /> Disconnect
        </button>
      )}
      {syncedAt && (
        <span className="live-sync-meta" title={`${tenantLabel} last synced from Xero`}>
          Last synced {syncedAt}
        </span>
      )}
    </>
  );
}

function Dashboard({
  data,
  cashDisplay,
  onFindActions,
  onSyncXero,
  onSelectTenant,
  onDisconnectXero,
  onUpdateCashFloor,
  onReviewActions,
  onViewActivity,
  syncResult,
  busy
}) {
  const businessName = businessNameFor(data.dataSource);
  const actionBlockReason = xeroActionBlockReason(data.dataSource, data.xeroStatus, data.xeroTenants);
  const [invoiceSort, requestInvoiceSort] = useSort("due_date", "asc");
  const [showAllMobileInvoices, setShowAllMobileInvoices] = useState(false);
  const forecastAsOf = forecastAsOfValue(data.forecast);
  const cutoff = addDays(todayForForecast(data.forecast), 30);
  const dueNext30 = data.invoices
    .filter((invoice) => parseDate(invoice.due_date) <= cutoff)
    .reduce((sum, invoice) => sum + invoice.amount_due, 0);
  const predictedNext30 = data.invoices
    .filter((invoice) => parseDate(invoice.predicted_paid_date) <= cutoff)
    .reduce((sum, invoice) => sum + invoice.amount_due, 0);
  const warningBuckets = data.forecast.buckets.filter((bucket) => bucket.cumulative_predicted < data.forecast.cash_floor);
  const firstWarning = warningBuckets.find((bucket) => bucket.week_start !== "later");
  const pendingProposals = data.proposals.filter((proposal) => proposal.status === "pending");
  const proposalByInvoice = useMemo(() => {
    const indexed = new Map();
    for (const proposal of data.proposals) {
      if (proposal.status === "pending" && proposal.invoice_id) {
        indexed.set(proposal.invoice_id, proposal);
      }
    }
    return indexed;
  }, [data.proposals]);
  const pendingActions = Number(data.metrics?.pending_actions_count ?? pendingProposals.length);
  const pendingImpactFallback = pendingProposals.reduce(
    (sum, proposal) => sum + Number(proposal.expected_impact_dollars || 0),
    0
  );
  const pendingWeightedDays = pendingProposals.reduce(
    (sum, proposal) =>
      sum + Number(proposal.expected_impact_dollars || 0) * Number(proposal.expected_days_accelerated || 0),
    0
  );
  const pendingAverageFallback = pendingImpactFallback ? pendingWeightedDays / pendingImpactFallback : 0;
  const pendingImpact = Number(data.metrics?.pending_impact_dollars ?? pendingImpactFallback);
  const pendingAverageDays = Math.round(Number(data.metrics?.pending_avg_days_accelerated ?? pendingAverageFallback));
  const approvedImpact = Number(data.metrics?.cash_accelerated_dollars || 0);
  const hasApprovedImpact = approvedImpact > 0;
  const cashActionMetricLabel = hasApprovedImpact
    ? "Brought forward"
    : pendingImpact > 0
      ? "Ready to bring forward"
      : "Cash impact";
  const cashActionMetricValue = hasApprovedImpact ? cashDisplay : pendingImpact;
  const pendingDaysPhrase =
    pendingAverageDays > 0 ? ` about ${pendingAverageDays} ${plural(pendingAverageDays, "day")} sooner` : " sooner";
  const pendingValueText =
    pendingImpact > 0
      ? `${formatCurrency(pendingImpact)} waiting for review`
      : "No suggested cash actions waiting";
  const pendingSummary =
    pendingImpact > 0 && pendingActions > 0
      ? `Review ${pendingActions} suggested ${plural(pendingActions, "action")} to bring ${formatCurrency(pendingImpact)} forward${pendingDaysPhrase}. Nothing is sent without your OK.`
      : "When new invoices arrive, find actions and review each suggestion before anything is sent.";
  const openInvoiceCount = data.invoices.length;
  const agedReceivables = data.metrics?.aged_receivables || agedReceivablesFromInvoices(data.invoices, forecastAsOf);
  const sortedInvoices = useMemo(
    () =>
      sortRows(data.invoices, invoiceSort, {
        invoice_number: (invoice) => invoice.invoice_number,
        contact_name: (invoice) => invoice.contact_name,
        due_date: (invoice) => Date.parse(`${invoice.due_date}T00:00:00Z`),
        predicted_paid_date: (invoice) => Date.parse(`${invoice.accelerated_paid_date || invoice.predicted_paid_date}T00:00:00Z`),
        next_step: (invoice) => (proposalByInvoice.has(invoice.id) ? 0 : 1),
        amount_due: (invoice) => Number(invoice.amount_due || 0)
      }),
    [data.invoices, invoiceSort, proposalByInvoice]
  );
  const mobileInvoices = showAllMobileInvoices ? sortedInvoices : sortedInvoices.slice(0, MOBILE_INVOICE_PREVIEW_COUNT);
  const hasMoreMobileInvoices = sortedInvoices.length > MOBILE_INVOICE_PREVIEW_COUNT;

  return (
    <main className="content">
      <div className="topbar">
        <div>
          <p className="eyebrow">{businessName}</p>
          <h1>Nero</h1>
        </div>
        <div className="topbar-actions">
          <LiveXeroControls
            status={data.xeroStatus}
            tenants={data.xeroTenants}
            source={data.dataSource}
            busy={busy}
            onSyncXero={onSyncXero}
            onSelectTenant={onSelectTenant}
            onDisconnectXero={onDisconnectXero}
          />
          <button
            className="button primary btn btn-primary btn-sm"
            onClick={onFindActions}
            disabled={busy || Boolean(actionBlockReason)}
            title={actionBlockReason || "Find suggested actions"}
          >
            <Play size={16} /> Find actions
          </button>
        </div>
      </div>

      <DataSourceBanner source={data.dataSource} xeroStatus={data.xeroStatus} xeroTenants={data.xeroTenants} />

      <section className="command-strip" aria-label="Cash control summary">
        <div>
          <span>Live cash room</span>
          <strong>{openInvoiceCount} invoices under watch</strong>
        </div>
        <div>
          <span>To review</span>
          <strong>{pendingActions} suggested actions</strong>
        </div>
        <div>
          <span>Minimum cash</span>
          <strong>{formatCurrency(data.settings?.cash_floor ?? data.forecast.cash_floor)}</strong>
        </div>
      </section>

      <section className="metrics">
        <article>
          <span>Due now or soon</span>
          <strong>{formatHeroCurrency(dueNext30)}</strong>
        </article>
        <article className="metric-primary">
          <span>Likely by then</span>
          <strong>{formatHeroCurrency(predictedNext30)}</strong>
        </article>
        <article className="metric-teal">
          <span>{cashActionMetricLabel}</span>
          <strong>{formatCurrency(cashActionMetricValue)}</strong>
        </article>
      </section>

      <LateInvoicesByAge agedReceivables={agedReceivables} />

      <section className={pendingImpact > 0 ? "roi-strip" : "roi-strip quiet"} aria-label="Cash action summary">
        <div>
          <span>Cash to bring forward</span>
          <strong>{pendingValueText}</strong>
          <p>{pendingSummary}</p>
        </div>
        <button className="button ghost btn btn-ghost btn-sm" type="button" onClick={onReviewActions}>
          <Bot size={16} /> Review actions
        </button>
      </section>

      <section className="split">
        <div className="main-stack">
          <div className="panel chart-panel">
            <div className="panel-head">
              <div>
                <h2>Cash forecast</h2>
                {firstWarning && (
                  <span className="badge badge-error danger">{formatWeekLabel(firstWarning.week_start)} below floor</span>
                )}
              </div>
            </div>
            <Suspense fallback={<div className="chart-wrap"><div className="chart-renderer chart-loading">Loading forecast</div></div>}>
              <ForecastChart forecast={data.forecast} />
            </Suspense>
          </div>

          <section className="panel">
            <div className="panel-head">
              <h2>Open invoices</h2>
            </div>
            <div className="table-wrap invoice-table-wrap">
              <table className="table table-sm">
                <thead>
                  <tr>
                    <SortableHeader label="Invoice" sortKey="invoice_number" sort={invoiceSort} onSort={requestInvoiceSort} />
                    <SortableHeader label="Customer" sortKey="contact_name" sort={invoiceSort} onSort={requestInvoiceSort} />
                    <SortableHeader label="Due" sortKey="due_date" sort={invoiceSort} onSort={requestInvoiceSort} />
                    <SortableHeader label="Predicted" sortKey="predicted_paid_date" sort={invoiceSort} onSort={requestInvoiceSort} />
                    <SortableHeader label="Next step" sortKey="next_step" sort={invoiceSort} onSort={requestInvoiceSort} />
                    <SortableHeader
                      label="Amount"
                      sortKey="amount_due"
                      sort={invoiceSort}
                      onSort={requestInvoiceSort}
                      align="right"
                      defaultDirection="desc"
                    />
                  </tr>
                </thead>
                <tbody>
                  {sortedInvoices.map((invoice) => {
                    const predictedDate = invoice.accelerated_paid_date || invoice.predicted_paid_date;
                    const proposal = proposalByInvoice.get(invoice.id);
                    return (
                      <tr key={invoice.id}>
                        <td>
                          <div className="invoice-ref-cell">
                            <strong>{invoice.invoice_number}</strong>
                            {data.dataSource?.mode === "xero" && invoice.online_invoice_url && (
                              <a href={invoice.online_invoice_url} target="_blank" rel="noreferrer">
                                <ExternalLink size={12} /> Open in Xero
                              </a>
                            )}
                          </div>
                        </td>
                        <td>{invoice.contact_name}</td>
                        <td>
                          <div className="date-cell">
                            <strong>{formatShortDate(invoice.due_date)}</strong>
                            <span>{invoiceTimingText(invoice.due_date, forecastAsOf)}</span>
                          </div>
                        </td>
                        <td>
                          <div className="date-cell">
                            <strong>{formatShortDate(predictedDate)}</strong>
                            <span>{invoiceTimingText(predictedDate, forecastAsOf)}</span>
                          </div>
                        </td>
                        <td>
                          {proposal ? (
                            <button className="invoice-step-button" type="button" onClick={onReviewActions}>
                              <Bot size={14} /> Review action
                            </button>
                          ) : (
                            <span className="invoice-step-muted">Watch</span>
                          )}
                        </td>
                        <td className="right">{formatCurrency(invoice.amount_due)}</td>
                      </tr>
                    );
                  })}
                  {data.invoices.length === 0 && (
                    <tr>
                      <td colSpan="6">
                        <div className="empty inline-empty">No open invoices. Sync Xero to pull the latest records.</div>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
            <div className="mobile-invoice-list">
              {mobileInvoices.map((invoice) => {
                const predictedDate = invoice.accelerated_paid_date || invoice.predicted_paid_date;
                const proposal = proposalByInvoice.get(invoice.id);
                return (
                  <article className="mobile-invoice-card" key={invoice.id}>
                    <header>
                      <div>
                        <strong>{invoice.invoice_number}</strong>
                        <span>{invoice.contact_name}</span>
                      </div>
                      <em>{formatCurrency(invoice.amount_due)}</em>
                    </header>
                    <div className="mobile-invoice-meta">
                      <div>
                        <span>Due</span>
                        <strong>{formatShortDate(invoice.due_date)}</strong>
                        <small>{invoiceTimingText(invoice.due_date, forecastAsOf)}</small>
                      </div>
                      <div>
                        <span>Expected</span>
                        <strong>{formatShortDate(predictedDate)}</strong>
                        <small>{invoiceTimingText(predictedDate, forecastAsOf)}</small>
                      </div>
                    </div>
                    <footer>
                      {data.dataSource?.mode === "xero" && invoice.online_invoice_url ? (
                        <a href={invoice.online_invoice_url} target="_blank" rel="noreferrer">
                          <ExternalLink size={12} /> Open in Xero
                        </a>
                      ) : (
                        <span />
                      )}
                      {proposal ? (
                        <button className="invoice-step-button" type="button" onClick={onReviewActions}>
                          <Bot size={14} /> Review action
                        </button>
                      ) : (
                        <span className="invoice-step-muted">Watch</span>
                      )}
                    </footer>
                  </article>
                );
              })}
              {hasMoreMobileInvoices && (
                <button
                  className="button ghost btn btn-ghost btn-sm mobile-invoice-toggle"
                  type="button"
                  onClick={() => setShowAllMobileInvoices((current) => !current)}
                >
                  {showAllMobileInvoices ? "Show fewer invoices" : `Show all ${sortedInvoices.length} invoices`}
                </button>
              )}
              {sortedInvoices.length === 0 && (
                <div className="empty inline-empty">No open invoices. Sync Xero to pull the latest records.</div>
              )}
            </div>
          </section>
        </div>

        <aside className="panel signal-panel">
          <CashFloorControl
            value={data.settings?.cash_floor ?? data.forecast.cash_floor}
            forecast={data.forecast}
            suggestedCashFloor={data.settings?.suggested_cash_floor}
            billsSummary={data.bills?.summary}
            onUpdateCashFloor={onUpdateCashFloor}
            busy={busy}
          />
          <RecentActivity entries={data.actionLog} onViewAll={onViewActivity} />
          {syncResult && <p className={syncResultClass(syncResult)}>{syncSummary(syncResult)}</p>}
        </aside>
      </section>
    </main>
  );
}

function Payers({ contacts, invoices = [] }) {
  const [search, setSearch] = useState("");
  const debouncedSearch = useDebouncedValue(search, 200).trim().toLowerCase();
  const [payerSort, requestPayerSort] = useSort("exposure", "desc");

  // Rank by cash at risk: the money in open invoices, weighted by how late this
  // payer runs. Reliable payers (avg late <= 0) drop to the bottom.
  const ranked = useMemo(
    () =>
      contacts
        .map((contact) => {
          const exposure = exposureFor(contact.id, invoices);
          const risk = exposure * Math.max(contact.avg_days_late, 0);
          return { ...contact, exposure, risk };
        }),
    [contacts, invoices]
  );

  const filtered = useMemo(
    () => ranked.filter((contact) => contact.name.toLowerCase().includes(debouncedSearch)),
    [ranked, debouncedSearch]
  );

  const sorted = useMemo(
    () =>
      sortRows(filtered, payerSort, {
        name: (contact) => contact.name,
        grade: (contact) => contact.grade,
        exposure: (contact) => Number(contact.exposure || 0),
        avg_days_late: (contact) => Number(contact.avg_days_late || 0),
        trend_slope: (contact) => Number(contact.trend_slope || 0),
        invoice_count: (contact) => Number(contact.invoice_count || 0)
      }),
    [filtered, payerSort]
  );

  const [selectedId, setSelectedId] = useState(sorted[0]?.id);
  const selected = sorted.find((contact) => contact.id === selectedId) || sorted[0];

  useEffect(() => {
    if (!sorted.find((contact) => contact.id === selectedId) && sorted.length) {
      setSelectedId(sorted[0].id);
    }
  }, [sorted, selectedId]);

  function selectWithKeyboard(event, contactId) {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    setSelectedId(contactId);
  }

  return (
    <main className="content payers-layout">
      <section className="panel">
        <div className="panel-head">
          <div>
            <h2>Payment performance</h2>
            <p className="panel-sub">Sorted by what customers owe you now; click a header to change it</p>
          </div>
        </div>
        <label className="search-field">
          <Search size={16} aria-hidden="true" />
          <input
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search customers..."
            aria-label="Search customers"
          />
        </label>
        <div className="table-wrap payer-table-wrap">
          <table className="table table-sm">
            <thead>
              <tr>
                <SortableHeader label="Name" sortKey="name" sort={payerSort} onSort={requestPayerSort} />
                <SortableHeader label="Reliability" sortKey="grade" sort={payerSort} onSort={requestPayerSort} />
                <SortableHeader
                  label="Currently owes"
                  sortKey="exposure"
                  sort={payerSort}
                  onSort={requestPayerSort}
                  align="right"
                  defaultDirection="desc"
                />
                <SortableHeader
                  label="Usually pays"
                  sortKey="avg_days_late"
                  sort={payerSort}
                  onSort={requestPayerSort}
                  align="right"
                  defaultDirection="desc"
                />
                <SortableHeader
                  label="Direction"
                  sortKey="trend_slope"
                  sort={payerSort}
                  onSort={requestPayerSort}
                  defaultDirection="desc"
                />
                <SortableHeader
                  label="Paid invoices"
                  sortKey="invoice_count"
                  sort={payerSort}
                  onSort={requestPayerSort}
                  align="right"
                  defaultDirection="desc"
                />
              </tr>
            </thead>
            <tbody>
              {sorted.map((contact) => (
                <tr
                  key={contact.id}
                  className={selected?.id === contact.id ? "selected-row" : ""}
                  tabIndex={0}
                  aria-selected={selected?.id === contact.id}
                  onClick={() => setSelectedId(contact.id)}
                  onKeyDown={(event) => selectWithKeyboard(event, contact.id)}
                >
                  <td>{contact.name}</td>
                  <td><span className={gradeClass(contact.grade)}>{reliabilityLabel(contact)}</span></td>
                  <td className="right exposure-cell">{formatCurrency(contact.exposure)}</td>
                  <td className="right">{paymentTimingText(contact.avg_days_late)}</td>
                  <td><TrendCell slope={contact.trend_slope} /></td>
                  <td className="right">{contact.invoice_count}</td>
                </tr>
              ))}
              {sorted.length === 0 && (
                <tr>
                  <td colSpan="6">
                    <div className="empty inline-empty">No matching customers. Clear the search or sync Xero history.</div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="mobile-payer-list" aria-label="Customers">
          {sorted.map((contact) => (
            <button
              type="button"
              key={contact.id}
              className={selected?.id === contact.id ? "mobile-payer-card is-selected" : "mobile-payer-card"}
              aria-pressed={selected?.id === contact.id}
              onClick={() => setSelectedId(contact.id)}
            >
              <span className="payer-card-head">
                <strong>{contact.name}</strong>
                <span className={gradeClass(contact.grade)}>{reliabilityLabel(contact)}</span>
              </span>
              <span className="payer-card-metrics">
                <span>
                  <small>Owes now</small>
                  <b>{formatCurrency(contact.exposure)}</b>
                </span>
                <span>
                  <small>Usually pays</small>
                  <b>{paymentTimingText(contact.avg_days_late)}</b>
                </span>
                <span>
                  <small>Direction</small>
                  <TrendCell slope={contact.trend_slope} />
                </span>
                <span>
                  <small>Paid invoices</small>
                  <b>{contact.invoice_count}</b>
                </span>
              </span>
            </button>
          ))}
          {sorted.length === 0 && (
            <div className="empty inline-empty">No matching customers. Clear the search or sync Xero history.</div>
          )}
        </div>
      </section>

      <aside className="panel side-panel">
        {selected && (
          <>
            <div className="payer-title">
              <h2>{selected.name}</h2>
              <span className={gradeClass(selected.grade)}>{reliabilityLabel(selected)}</span>
            </div>
            <dl className="stats-list">
              <div><dt>What they currently owe you</dt><dd>{formatCurrency(selected.exposure)}</dd></div>
              <div><dt>How much business you've done with them (past year)</dt><dd>{formatCurrency(selected.revenue_12m)}</dd></div>
            </dl>
            <p className="payer-summary">{payerTimingSentence(selected)}</p>
            {selected.exposure > 0 && (
              <a className="button ghost btn btn-ghost btn-sm statement-link" href={statementUrl(selected.id)} target="_blank" rel="noreferrer">
                <FileText size={16} /> Open statement
              </a>
            )}
          </>
        )}
      </aside>
    </main>
  );
}

function AgentQueue({ proposals, dataSource, aiStatus, approvalBlockedReason = "", onApprove, onDismiss, onEdit, onPolish, busy }) {
  const [drafts, setDrafts] = useState({});
  const pending = useMemo(
    () =>
      proposals
        .filter((proposal) => proposal.status === "pending")
        .sort((a, b) => {
          const priorityDiff = proposalActionPriority(a) - proposalActionPriority(b);
          if (priorityDiff !== 0) return priorityDiff;
          const impactDiff = Number(b.expected_impact_dollars || 0) - Number(a.expected_impact_dollars || 0);
          if (impactDiff !== 0) return impactDiff;
          const daysDiff = Number(b.expected_days_accelerated || 0) - Number(a.expected_days_accelerated || 0);
          if (daysDiff !== 0) return daysDiff;
          return String(a.contact_name || "").localeCompare(String(b.contact_name || ""), undefined, {
            numeric: true,
            sensitivity: "base"
          });
        }),
    [proposals]
  );
  const queueSummary = useMemo(
    () => ({
      withEmail: pending.filter((proposal) => proposal.draft_subject && proposal.contact_email).length,
      needsEmail: pending.filter((proposal) => proposal.draft_subject && !proposal.contact_email).length,
      recommendations: pending.filter((proposal) => !proposal.draft_subject).length
    }),
    [pending]
  );

  function approveCurrentDraft(proposal, draftBody) {
    const savedDraft = proposal.draft_body ?? "";
    const changedDraft = proposal.draft_subject && draftBody !== savedDraft ? draftBody : undefined;
    onApprove(proposal.id, changedDraft);
  }

  async function polishCurrentDraft(proposal, draftBody) {
    const result = await onPolish(proposal.id, draftBody);
    const polished = result?.proposal?.draft_body;
    if (polished) {
      setDrafts((current) => ({ ...current, [proposal.id]: polished }));
    }
  }

  return (
    <main className="content">
      <div className="panel-head page-head">
        <h1>Actions to review</h1>
      </div>
      {approvalBlockedReason && (
        <div className="queue-warning">
          <RefreshCw size={16} />
          <span>{approvalBlockedReason}</span>
        </div>
      )}
      {pending.length > 0 && (
        <div className="queue-summary" aria-label="Action queue summary">
          <span><strong>{queueSummary.withEmail}</strong> {plural(queueSummary.withEmail, "draft")} with customer email</span>
          {queueSummary.needsEmail > 0 && (
            <span><strong>{queueSummary.needsEmail}</strong> need customer email in Xero</span>
          )}
          {queueSummary.recommendations > 0 && (
            <span><strong>{queueSummary.recommendations}</strong> {plural(queueSummary.recommendations, "recommendation")}</span>
          )}
        </div>
      )}
      <div className="proposal-grid">
        {pending.map((proposal) => {
          const draftBody = drafts[proposal.id] ?? proposal.draft_body ?? "";
          const copy = proposalActionCopy(proposal);
          return (
            <article className="proposal-card" key={proposal.id} data-priority={proposalActionPriority(proposal)}>
              <div className="proposal-top">
                <span className="badge badge-neutral">{copy.label}</span>
                <strong>{proposal.contact_name}</strong>
              </div>
              <p className="proposal-reason">{copy.reason}</p>
              <div className="impact">
                Could bring {formatCurrency(proposal.expected_impact_dollars)} forward about {proposal.expected_days_accelerated} {plural(proposal.expected_days_accelerated, "day")} sooner.
              </div>
              {proposal.draft_subject && (
                <details className="email-preview">
                  <summary>{proposal.draft_subject}</summary>
                  <textarea
                    value={draftBody}
                    onChange={(event) => setDrafts((current) => ({ ...current, [proposal.id]: event.target.value }))}
                    readOnly={Boolean(approvalBlockedReason)}
                    title={approvalBlockedReason || "Edit draft wording"}
                  />
                </details>
              )}
              {proposal.draft_subject && !proposal.contact_email && (
                <p className="contact-warning">
                  No customer email found in Xero. Approving keeps the draft in Outbox so you can copy it or add the email in Xero.
                </p>
              )}
              <p className="approval-note">{approvalOutcomeText(proposal, dataSource)}</p>
              {proposal.recommendation_detail && <p className="recommendation">{proposal.recommendation_detail}</p>}
              <div className="actions">
                <button
                  className="button primary btn btn-primary btn-sm"
                  disabled={busy || Boolean(approvalBlockedReason)}
                  onClick={() => approveCurrentDraft(proposal, draftBody)}
                  title={approvalBlockedReason || copy.approveLabel}
                >
                  <Check size={16} /> {copy.approveLabel}
                </button>
                {proposal.draft_subject && (
                  <button
                    className="button ghost btn btn-ghost btn-sm"
                    disabled={busy || Boolean(approvalBlockedReason)}
                    onClick={() => onEdit(proposal.id, draftBody)}
                    title={approvalBlockedReason || "Save wording"}
                  >
                    Save wording
                  </button>
                )}
                {proposal.draft_subject && proposal.contact_email && aiStatus?.enabled && (
                  <button
                    className="button ghost btn btn-ghost btn-sm"
                    disabled={busy || Boolean(approvalBlockedReason)}
                    onClick={() => polishCurrentDraft(proposal, draftBody)}
                    title={approvalBlockedReason || "Polish wording with review-only AI"}
                  >
                    <Sparkles size={16} /> Polish wording
                  </button>
                )}
                <button
                  className="button ghost danger-icon danger-button btn btn-ghost btn-sm"
                  disabled={busy || Boolean(approvalBlockedReason)}
                  onClick={() => onDismiss(proposal.id)}
                  title={approvalBlockedReason || "Dismiss"}
                >
                  <X size={16} /> Dismiss
                </button>
              </div>
            </article>
          );
        })}
        {pending.length === 0 && <div className="empty">No suggested actions waiting</div>}
      </div>
    </main>
  );
}

function Outbox({ outbox }) {
  const [outboxSort, requestOutboxSort] = useSort("timestamp", "desc");
  const [copiedId, setCopiedId] = useState(null);
  const sorted = useMemo(
    () =>
      sortRows(outbox, outboxSort, {
        timestamp: (entry) => Date.parse(entry.timestamp),
        to: (entry) => entry.to,
        to_email: (entry) => entry.to_email || "",
        subject: (entry) => entry.subject
      }),
    [outbox, outboxSort]
  );

  async function copyDraft(entry) {
    await copyToClipboard(`Subject: ${entry.subject || ""}\n\n${entry.body || ""}`);
    setCopiedId(entry.id);
    window.setTimeout(() => setCopiedId((current) => (current === entry.id ? null : current)), 1600);
  }

  return (
    <main className="content">
      <div className="panel-head page-head">
        <div>
          <h1>Outbox</h1>
          <span className="badge badge-outline muted-badge">Approved messages</span>
        </div>
      </div>
      <div className="panel">
        <div className="table-wrap">
          <table className="table table-sm">
            <thead>
              <tr>
                <SortableHeader
                  label="Date"
                  sortKey="timestamp"
                  sort={outboxSort}
                  onSort={requestOutboxSort}
                  defaultDirection="desc"
                />
                <SortableHeader label="Customer" sortKey="to" sort={outboxSort} onSort={requestOutboxSort} />
                <SortableHeader label="Email" sortKey="to_email" sort={outboxSort} onSort={requestOutboxSort} />
                <SortableHeader label="Subject" sortKey="subject" sort={outboxSort} onSort={requestOutboxSort} />
                <th className="right">Draft</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((entry) => {
                const disabledReason = outboxSendDisabledReason(entry);
                const staleDraft = entry.status === "stale";
                return (
                  <tr className={staleDraft ? "outbox-row-stale" : ""} key={entry.id}>
                    <td>{formatDateTime(entry.timestamp)}</td>
                    <td>{entry.to}</td>
                    <td className="recipient-cell">
                      {entry.to_email ? (
                        <span className="recipient-email">{entry.to_email}</span>
                      ) : (
                        <span className="badge attention">No email in Xero</span>
                      )}
                    </td>
                    <td>
                      <details className="message-preview">
                        <summary>{entry.subject}</summary>
                        <pre>{entry.body}</pre>
                      </details>
                    </td>
                    <td className="right">
                      <div className="outbox-actions">
                        <button
                          className="button primary btn btn-primary btn-xs"
                          type="button"
                          onClick={() => copyDraft(entry)}
                          disabled={staleDraft}
                          title={staleDraft ? disabledReason : "Copy draft wording"}
                        >
                          {copiedId === entry.id ? "Copied" : "Copy"}
                        </button>
                        {disabledReason ? (
                          <span className="draft-disabled" title={disabledReason}>
                            {staleDraft ? "Closed in Xero" : "Add email first"}
                          </span>
                        ) : (
                          <a className="button ghost btn btn-ghost btn-xs outbox-draft-link" href={mailtoDraftHref(entry)}>
                            <ExternalLink size={14} /> Open mail app
                          </a>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
              {sorted.length === 0 && (
                <tr>
                  <td colSpan="5">
                    <div className="empty inline-empty">No approved messages yet</div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </main>
  );
}

function RecentActivity({ entries, onViewAll }) {
  const recent = (entries || []).slice(0, 3);
  return (
    <section className="signal-section recent-activity">
      <div className="panel-head compact">
        <h2>Recent activity</h2>
        <button className="button ghost btn btn-ghost btn-xs" type="button" onClick={onViewAll}>
          View all
        </button>
      </div>
      <div className="activity-mini-list">
        {recent.map((entry) => (
          <div className="activity-mini-row" key={entry.id}>
            <span>{formatDateTime(entry.timestamp)}</span>
            <p>{entry.event}</p>
          </div>
        ))}
        {recent.length === 0 && <p className="muted compact-note">No activity yet.</p>}
      </div>
    </section>
  );
}

// Product decision: activity stays available for accountability, but it is not
// a primary tab because owners usually need outcomes before audit trails.
function ActivityHistory({ entries }) {
  return (
    <main className="content">
      <div className="panel-head page-head">
        <div>
          <h1>Activity</h1>
          <p className="panel-sub">A plain record of approved actions and changes.</p>
        </div>
      </div>
      <div className="timeline">
        {entries.map((entry) => (
          <div className="timeline-row" key={entry.id}>
            <span>{formatDateTime(entry.timestamp)}</span>
            <strong>{entry.actor}</strong>
            <p>{entry.event}</p>
          </div>
        ))}
        {entries.length === 0 && <div className="empty">No actions yet</div>}
      </div>
    </main>
  );
}

function ModalShell({ title, onClose, children }) {
  useEffect(() => {
    function closeOnEscape(event) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section className="modal-panel" role="dialog" aria-modal="true" aria-label={title} onMouseDown={(event) => event.stopPropagation()}>
        <div className="panel-head">
          <h2>{title}</h2>
          <button className="icon-button btn btn-square btn-ghost btn-sm" type="button" onClick={onClose} title="Close" aria-label="Close">
            <X size={16} />
          </button>
        </div>
        {children}
      </section>
    </div>
  );
}

function SupportModal({ onClose }) {
  return (
    <ModalShell title="Help & Support" onClose={onClose}>
      <p className="modal-lede">Need help? We're here.</p>
      <a className="support-link" href={`mailto:${SUPPORT_EMAIL}`}>
        {SUPPORT_EMAIL}
      </a>
      <p className="muted compact-note">For billing, Xero connection, privacy, or data deletion questions, include your business name.</p>
    </ModalShell>
  );
}

function GuideModal({ onClose }) {
  const steps = [
    "See who owes you money and when they're likely to actually pay.",
    "Check the Payers tab to see which customers tend to pay late.",
    "Use Nero's minimum-cash suggestion to keep enough money aside for upcoming bills.",
    "Open Actions to review suggested reminders or smarter payment terms.",
    "Review and approve; nothing is sent without your OK.",
    "Watch your forecast improve as payments come in."
  ];
  return (
    <ModalShell title="How to use Nero" onClose={onClose}>
      <ol className="guide-list">
        {steps.map((step) => (
          <li key={step}>{step}</li>
        ))}
      </ol>
    </ModalShell>
  );
}

function InitialLoadError({ message, onRetry, busy }) {
  return (
    <main className="content">
      <section className="panel initial-error">
        <div>
          <h1>Nero could not load</h1>
          <p>{message || "Something interrupted the first dashboard load."}</p>
        </div>
        <button className="button primary btn btn-primary btn-sm" type="button" onClick={onRetry} disabled={busy}>
          <RefreshCw size={16} /> Try again
        </button>
      </section>
    </main>
  );
}

function DevToolsPanel({
  data,
  syncResult,
  busy,
  onClose,
  onSyncXero,
  onSeedPortfolio,
  onSelectTenant,
  onDisconnectXero,
  onMarkFirstPaid,
  onScanResearch
}) {
  const researchSources = Object.entries(data?.research?.sources || {});
  const firstInvoice = data?.invoices?.[0];
  return (
    <ModalShell title="Developer tools" onClose={onClose}>
      {/* demo-only, not user-facing: requires VITE_ENABLE_DEV_TOOLS=true, then opens with Ctrl+Shift+D. */}
      <p className="modal-lede">Demo-only controls for reset, seeded data, and integration checks.</p>
      <div className="dev-action-row">
        <button className="button ghost btn btn-ghost btn-sm" type="button" onClick={onSeedPortfolio} disabled={busy}>
          <Database size={16} /> Seed portfolio
        </button>
        <button className="button ghost btn btn-ghost btn-sm" type="button" onClick={onMarkFirstPaid} disabled={busy || !firstInvoice}>
          <Check size={16} /> Mark first invoice paid
        </button>
        <button className="button ghost btn btn-ghost btn-sm" type="button" onClick={onScanResearch} disabled={busy}>
          <RefreshCw size={16} /> Scan research
        </button>
      </div>
      {data && (
        <div className="dev-grid">
          <XeroConnection
            status={data.xeroStatus}
            source={data.dataSource}
            tenants={data.xeroTenants}
            syncResult={syncResult}
            onSyncXero={onSyncXero}
            onSelectTenant={onSelectTenant}
            onDisconnectXero={onDisconnectXero}
            busy={busy}
          />
          <ResearchSignals sources={researchSources} onScanResearch={onScanResearch} busy={busy} />
          <AppStoreReadiness readiness={data.appStoreReadiness} />
        </div>
      )}
    </ModalShell>
  );
}

export function App() {
  const [activeTab, setActiveTab] = useState("dashboard");
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [syncResult, setSyncResult] = useState(null);
  const [modal, setModal] = useState(null);

  async function refresh() {
    setError("");
    const next = await fetchAll();
    setData(next);
  }

  useEffect(() => {
    refresh().catch((err) => setError(err.message));
  }, []);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const xeroReturn = params.get("xero");
    if (!["connected", "error"].includes(xeroReturn)) return;
    const detail =
      xeroReturn === "connected"
        ? "Xero connected. Click Sync Xero to pull the latest records."
        : params.get("message") || "Xero connection could not be completed. Try Connect Xero again.";
    setSyncResult({ status: xeroReturn, detail });
    params.delete("xero");
    params.delete("message");
    const query = params.toString();
    const nextUrl = `${window.location.pathname}${query ? `?${query}` : ""}${window.location.hash}`;
    window.history.replaceState({}, "", nextUrl || "/");
  }, []);

  useEffect(() => {
    function openDevTools(event) {
      if (!DEV_TOOLS_ENABLED) return;
      if (event.ctrlKey && event.shiftKey && event.key.toLowerCase() === "d") {
        event.preventDefault();
        setModal("dev");
      }
    }
    window.addEventListener("keydown", openDevTools);
    return () => window.removeEventListener("keydown", openDevTools);
  }, []);

  const cashDisplay = useCountUp(data?.metrics?.cash_accelerated_dollars || 0);

  async function act(fn) {
    setBusy(true);
    setError("");
    try {
      const result = await fn();
      await refresh();
      return result;
    } catch (err) {
      setError(err.message);
      return null;
    } finally {
      setBusy(false);
    }
  }

  function confirmDisconnectXero() {
    const confirmed = window.confirm(
      "Disconnect Xero on this computer? Nero will keep the current dashboard snapshot, but it will not sync again until you reconnect."
    );
    if (!confirmed) return;
    act(async () => setSyncResult(await disconnectXero()));
  }

  async function retryInitialLoad() {
    setBusy(true);
    try {
      await refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  const activeContent = useMemo(() => {
    if (!data && error) return <InitialLoadError message={error} onRetry={retryInitialLoad} busy={busy} />;
    if (!data) return <main className="content"><div className="empty">Loading Nero</div></main>;
    if (activeTab === "dashboard") {
      return (
        <Dashboard
          data={data}
          cashDisplay={cashDisplay}
          busy={busy}
          onFindActions={() => act(findActions)}
          onSyncXero={() => act(async () => setSyncResult(await syncXero()))}
          onSelectTenant={(tenantId) => act(async () => setSyncResult(await selectXeroTenant(tenantId)))}
          onDisconnectXero={confirmDisconnectXero}
          onUpdateCashFloor={(cashFloor, mode) => act(() => updateCashFloor(cashFloor, mode))}
          onReviewActions={() => setActiveTab("queue")}
          onViewActivity={() => setActiveTab("activity")}
          syncResult={syncResult}
        />
      );
    }
    if (activeTab === "payers") return <Payers contacts={data.contacts} invoices={data.invoices} />;
    if (activeTab === "queue") {
      return (
        <AgentQueue
          proposals={data.proposals}
          dataSource={data.dataSource}
          aiStatus={data.aiStatus}
          approvalBlockedReason={xeroActionBlockReason(data.dataSource, data.xeroStatus, data.xeroTenants)}
          busy={busy}
          onApprove={(id, draftBody) =>
            act(async () => {
              if (typeof draftBody === "string") await editProposal(id, draftBody);
              await approveProposal(id);
            })
          }
          onDismiss={(id) => act(() => dismissProposal(id))}
          onEdit={(id, body) => act(() => editProposal(id, body))}
          onPolish={(id, body) => act(() => polishProposal(id, body))}
        />
      );
    }
    if (activeTab === "outbox") return <Outbox outbox={data.outbox} />;
    return <ActivityHistory entries={data.actionLog} />;
  }, [activeTab, data, cashDisplay, busy, syncResult, error]);

  return (
    <div className="app-shell" data-theme="corporate">
      <aside className="sidebar">
        <div className="brand">
          <span>N</span>
          <div>
            <strong>Nero</strong>
            <small>Cash accelerator</small>
          </div>
        </div>
        <nav>
          {TABS.map((tab) => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                className={activeTab === tab.id ? "nav-item active" : "nav-item"}
                onClick={() => setActiveTab(tab.id)}
              >
                <Icon size={18} />
                {tab.label}
              </button>
            );
          })}
        </nav>
        <div className="sidebar-footer">
          <button className="nav-item secondary" type="button" onClick={() => setModal("guide")}>
            <BookOpen size={18} />
            Guide
          </button>
          <button className="nav-item secondary" type="button" onClick={() => setModal("support")}>
            <HelpCircle size={18} />
            Help & Support
          </button>
          <button
            className={activeTab === "activity" ? "nav-item secondary active" : "nav-item secondary"}
            type="button"
            onClick={() => setActiveTab("activity")}
          >
            <ClipboardList size={18} />
            Activity
          </button>
        </div>
        {error && <div className="error-box">{error}</div>}
      </aside>
      {activeContent}
      {modal === "support" && <SupportModal onClose={() => setModal(null)} />}
      {modal === "guide" && <GuideModal onClose={() => setModal(null)} />}
      {modal === "dev" && (
        <DevToolsPanel
          data={data}
          busy={busy}
          syncResult={syncResult}
          onClose={() => setModal(null)}
          onSyncXero={() => act(async () => setSyncResult(await syncXero()))}
          onSeedPortfolio={() => act(async () => setSyncResult(await seedSyntheticPortfolio()))}
          onSelectTenant={(tenantId) => act(async () => setSyncResult(await selectXeroTenant(tenantId)))}
          onDisconnectXero={confirmDisconnectXero}
          onMarkFirstPaid={() => data?.invoices?.[0] && act(() => markPaid(data.invoices[0].id))}
          onScanResearch={() => act(scanResearch)}
        />
      )}
    </div>
  );
}

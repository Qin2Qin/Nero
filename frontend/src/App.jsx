import {
  BookOpen,
  Bot,
  Check,
  ChevronDown,
  ChevronUp,
  ClipboardList,
  Database,
  ExternalLink,
  HelpCircle,
  LayoutDashboard,
  Minus,
  Play,
  RefreshCw,
  Search,
  Send,
  TrendingDown,
  TrendingUp,
  Users,
  X
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import {
  approveProposal,
  dismissProposal,
  editProposal,
  fetchAll,
  markPaid,
  money,
  runAgent,
  scanResearch,
  seedSyntheticPortfolio,
  selectXeroTenant,
  syncXero,
  updateCashFloor,
  XERO_LOGIN_URL
} from "./api.js";

const TABS = [
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
  { id: "payers", label: "Payers", icon: Users },
  { id: "queue", label: "Agent Queue", icon: Bot },
  { id: "outbox", label: "Outbox", icon: Send }
];

const TODAY = new Date("2026-07-04T00:00:00Z");
const SUPPORT_EMAIL = import.meta.env.VITE_SUPPORT_EMAIL || "support@nero.cash";

function parseDate(value) {
  return new Date(`${value}T00:00:00Z`);
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

function gradeClass(grade) {
  return `grade grade-${String(grade).charAt(0).toLowerCase()}`;
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

function payerTimingSentence(contact) {
  const invoiceCount = Number(contact.invoice_count || 0);
  const avgLate = Math.max(0, Math.round(Number(contact.avg_days_late || 0)));
  const unpredictable = Number(contact.stdev_days_late || 0) >= 10 ? ", though timing can be unpredictable" : "";
  return `Based on ${invoiceCount} paid ${plural(invoiceCount, "invoice")}, ${contact.name} pays on average ${avgLate} ${plural(avgLate, "day")} late${unpredictable}, ${trendText(contact.trend_slope)}.`;
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

function xeroBadge(status) {
  if (status?.connected) return { className: "badge badge-success success", label: "Connected" };
  if (status?.demo_mode) return { className: "badge badge-neutral neutral", label: "Demo mode" };
  return { className: "badge badge-error danger", label: "Not connected" };
}

function syncSummary(result) {
  if (!result) return "";
  if (result.status === "synced") {
    const base = `Synced ${result.fetched?.contacts ?? 0} contacts, ${result.fetched?.invoices ?? 0} invoices, ${result.fetched?.payments ?? 0} payments.`;
    if (result.detail) return `${base} ${result.detail}`;
    if (result.materialized) {
      return `${base} Dashboard updated with ${result.materialized.contacts ?? 0} payers and ${result.materialized.invoices ?? 0} open invoices.`;
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
  if (result?.empty || result?.materialized === null) return "sync-result warning";
  return "sync-result";
}

function mailtoDraftHref(entry) {
  const subject = encodeURIComponent(entry.subject || "");
  const body = encodeURIComponent(entry.body || "");
  return `mailto:?subject=${subject}&body=${body}`;
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

function CashFloorControl({ value, forecast, onUpdateCashFloor, busy }) {
  const [draft, setDraft] = useState(value || 0);
  const warningCount = forecast?.buckets?.filter((bucket) => bucket.cumulative_predicted < draft).length || 0;
  const isChanged = Number(draft) !== Number(value || 0);
  const maxForecast = Math.max(...(forecast?.buckets || []).map((bucket) => bucket.cumulative_predicted || 0), 15000);
  const maxFloor = Math.max(15000, Math.ceil(maxForecast / 5000) * 5000);
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
        <h2>Cash floor</h2>
        <span className={warningCount ? "badge badge-error danger" : "badge badge-success success"}>
          {warningCount ? `${warningCount} weeks below` : "Covered"}
        </span>
      </div>
      <div className="cash-floor-readout">
        <strong>{formatCurrency(draft)}</strong>
        <span>Operating minimum</span>
      </div>
      <input
        className="range range-primary range-sm range-input"
        type="range"
        min="0"
        max={maxFloor}
        step="500"
        value={draft}
        onChange={(event) => setDraft(Number(event.target.value))}
        aria-label="Cash floor"
      />
      <div className="preset-row" aria-label="Cash floor presets">
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
      <button className="button primary btn btn-primary btn-sm block" onClick={() => onUpdateCashFloor(draft)} disabled={busy || !isChanged}>
        Apply floor
      </button>
    </section>
  );
}

function ForecastChart({ forecast }) {
  const buckets = forecast?.buckets?.filter((bucket) => bucket.week_start !== "later") || [];
  if (!buckets.length) return <div className="empty">No forecast data</div>;
  const chartColors = {
    grid: "rgba(255,255,255,0.08)",
    tick: "#cbd5e1",
    due: "#94a3b8",
    predicted: "#818cf8",
    accelerated: "#34d399",
    floor: "#fb7185",
    area: "#818cf8"
  };

  const data = buckets.map((bucket) => ({
    week: formatWeekLabel(bucket.week_start),
    due: bucket.cumulative_due,
    predicted: bucket.cumulative_predicted,
    accelerated: bucket.cumulative_accelerated ?? bucket.cumulative_predicted,
    cashFloor: forecast.cash_floor
  }));

  return (
    <div className="chart-wrap">
      <div className="chart-renderer" role="img" aria-label="Cash forecast">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 14, right: 16, bottom: 8, left: 8 }}>
            <CartesianGrid stroke={chartColors.grid} vertical={false} />
            <XAxis dataKey="week" tick={{ fill: chartColors.tick, fontSize: 12 }} tickLine={false} axisLine={false} />
            <YAxis
              tickFormatter={compactMoney}
              tick={{ fill: chartColors.tick, fontSize: 12 }}
              tickLine={false}
              axisLine={false}
              width={54}
            />
            <Tooltip
              formatter={(value) => formatCurrency(value)}
              labelFormatter={(label) => `Week of ${label}`}
              contentStyle={{
                background: "rgba(15, 23, 42, 0.96)",
                border: "1px solid rgba(255,255,255,0.16)",
                borderRadius: 12,
                color: "#f8fafc",
                boxShadow: "0 18px 44px rgba(0,0,0,0.32)"
              }}
            />
            <Legend wrapperStyle={{ color: chartColors.tick, fontSize: 13 }} />
            <ReferenceLine
              y={forecast.cash_floor}
              stroke={chartColors.floor}
              strokeDasharray="4 5"
              label={{ value: `Cash floor ${compactMoney(forecast.cash_floor)}`, fill: chartColors.floor, fontSize: 12 }}
            />
            <Area
              name="Due envelope"
              type="monotone"
              dataKey="due"
              fill={chartColors.area}
              fillOpacity={0.12}
              stroke={chartColors.due}
              strokeOpacity={0}
              activeDot={false}
              legendType="none"
            />
            <Line
              className="forecast-line due-line"
              name="By due dates"
              type="monotone"
              dataKey="due"
              stroke={chartColors.due}
              strokeWidth={2.5}
              strokeDasharray="7 6"
              dot={false}
            />
            <Line
              className="forecast-line predicted-line"
              name="Predicted (Nero)"
              type="monotone"
              dataKey="predicted"
              stroke={chartColors.predicted}
              strokeWidth={2.8}
              dot={{ r: 3, fill: chartColors.predicted, strokeWidth: 0 }}
              activeDot={{ r: 5 }}
            />
            <Line
              className="forecast-line accelerated-line"
              name="After Nero actions"
              type="monotone"
              dataKey="accelerated"
              stroke={chartColors.accelerated}
              strokeWidth={2.8}
              dot={{ r: 3, fill: chartColors.accelerated, strokeWidth: 0 }}
              activeDot={{ r: 5 }}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function XeroConnection({ status, source, tenants, syncResult, onSyncXero, onSeedPortfolio, onSelectTenant, busy }) {
  const badge = xeroBadge(status);
  const canSync = status?.demo_mode || status?.connected;
  const tenantOptions = tenants?.tenants || [];
  const activeTenant = tenantOptions.find((tenant) => tenant.is_active);
  const credentialState = status?.client_credentials_configured ? "Ready" : "Missing";
  const tokenState = status?.connected
    ? "Stored"
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
        <button className="button ghost btn btn-ghost btn-sm" onClick={onSeedPortfolio} disabled={busy}>
          <Database size={16} /> Seed portfolio
        </button>
        {!status?.demo_mode && !status?.connected && status?.client_credentials_configured && (
          <a className="button ghost btn btn-ghost btn-sm" href={XERO_LOGIN_URL}>
            <ExternalLink size={16} /> Connect
          </a>
        )}
      </div>
      {syncResult && <p className={syncResultClass(syncResult)}>{syncSummary(syncResult)}</p>}
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

function DataSourceBanner({ source, xeroStatus }) {
  const liveConnected = xeroStatus?.connected && !xeroStatus?.demo_mode;
  const business = source?.business;
  const updatedAt = source?.generated_at ? formatDateTime(source.generated_at) : "";
  const detail = business
    ? `${business.sector} / ${business.country} / ${business.base_currency}`
    : "Cash timing and payer behaviour from your accounting data.";
  return (
    <section className="source-banner">
      <div className="source-copy">
        <strong>{businessNameFor(source)}</strong>
        <p>{detail}</p>
        <div className="source-badges">
          {liveConnected && <span className="badge badge-success success">Xero connected</span>}
          {updatedAt && <span className="badge badge-outline neutral">Updated {updatedAt}</span>}
        </div>
      </div>
      <figure className="source-visual-frame">
        <img src="/visuals/nero-cashflow-preview.png" alt="Nero cash forecast board preview" />
      </figure>
    </section>
  );
}

function LiveXeroControls({ status, tenants, busy, onSyncXero, onSelectTenant }) {
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

  const tenantOptions = tenants?.tenants || [];
  const selectedTenantId = tenants?.active_tenant_id || status.tenant_id || "";
  const shouldPickTenant = status.needs_tenant || tenantOptions.length > 1;

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
    </>
  );
}

function Dashboard({
  data,
  cashDisplay,
  onRunAgent,
  onSyncXero,
  onSelectTenant,
  onUpdateCashFloor,
  onReviewActions,
  onViewActivity,
  syncResult,
  busy
}) {
  const businessName = businessNameFor(data.dataSource);
  const [invoiceSort, requestInvoiceSort] = useSort("due_date", "asc");
  const cutoff = addDays(TODAY, 30);
  const dueNext30 = data.invoices
    .filter((invoice) => parseDate(invoice.due_date) <= cutoff)
    .reduce((sum, invoice) => sum + invoice.amount_due, 0);
  const predictedNext30 = data.invoices
    .filter((invoice) => parseDate(invoice.predicted_paid_date) <= cutoff)
    .reduce((sum, invoice) => sum + invoice.amount_due, 0);
  const warningBuckets = data.forecast.buckets.filter((bucket) => bucket.cumulative_predicted < data.forecast.cash_floor);
  const firstWarning = warningBuckets.find((bucket) => bucket.week_start !== "later");
  const pendingProposals = data.proposals.filter((proposal) => proposal.status === "pending");
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
  const pendingDaysPhrase =
    pendingAverageDays > 0 ? ` about ${pendingAverageDays} ${plural(pendingAverageDays, "day")} sooner` : " sooner";
  const pendingValueText =
    pendingImpact > 0
      ? `${formatCurrency(pendingImpact)} waiting for review`
      : "No suggested cash actions waiting";
  const pendingSummary =
    pendingImpact > 0 && pendingActions > 0
      ? `Review ${pendingActions} suggested ${plural(pendingActions, "action")} to bring ${formatCurrency(pendingImpact)} forward${pendingDaysPhrase}. Nothing is sent without your OK.`
      : "Run the agent when new invoices arrive, then review each suggestion before anything is sent.";
  const openInvoiceCount = data.invoices.length;
  const sortedInvoices = useMemo(
    () =>
      sortRows(data.invoices, invoiceSort, {
        invoice_number: (invoice) => invoice.invoice_number,
        contact_name: (invoice) => invoice.contact_name,
        due_date: (invoice) => Date.parse(`${invoice.due_date}T00:00:00Z`),
        predicted_paid_date: (invoice) => Date.parse(`${invoice.accelerated_paid_date || invoice.predicted_paid_date}T00:00:00Z`),
        amount_due: (invoice) => Number(invoice.amount_due || 0)
      }),
    [data.invoices, invoiceSort]
  );

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
            busy={busy}
            onSyncXero={onSyncXero}
            onSelectTenant={onSelectTenant}
          />
          <button className="button primary btn btn-primary btn-sm" onClick={onRunAgent} disabled={busy}>
            <Play size={16} /> Run agent
          </button>
        </div>
      </div>

      <DataSourceBanner source={data.dataSource} xeroStatus={data.xeroStatus} />

      <section className="command-strip" aria-label="Cash control summary">
        <div>
          <span>Live cash room</span>
          <strong>{openInvoiceCount} invoices under watch</strong>
        </div>
        <div>
          <span>Agent queue</span>
          <strong>{pendingActions} suggested actions</strong>
        </div>
        <div>
          <span>Forecast floor</span>
          <strong>{formatCurrency(data.settings?.cash_floor ?? data.forecast.cash_floor)}</strong>
        </div>
      </section>

      <section className="metrics">
        <article>
          <span>Due next 30 days</span>
          <strong>{formatHeroCurrency(dueNext30)}</strong>
        </article>
        <article className="metric-primary">
          <span>Actually arriving</span>
          <strong>{formatHeroCurrency(predictedNext30)}</strong>
        </article>
        <article className="metric-teal">
          <span>Cash Accelerated</span>
          <strong>{formatCurrency(cashDisplay)}</strong>
        </article>
      </section>

      <section className={pendingImpact > 0 ? "roi-strip" : "roi-strip quiet"} aria-label="Cash action summary">
        <div>
          <span>Cash to bring forward</span>
          <strong>{pendingValueText}</strong>
          <p>{pendingSummary}</p>
        </div>
        <button className="button ghost btn btn-ghost btn-sm" type="button" onClick={onReviewActions}>
          <Bot size={16} /> Open queue
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
            <ForecastChart forecast={data.forecast} />
          </div>

          <section className="panel">
            <div className="panel-head">
              <h2>Open invoices</h2>
            </div>
            <div className="table-wrap">
              <table className="table table-sm">
                <thead>
                  <tr>
                    <SortableHeader label="Invoice" sortKey="invoice_number" sort={invoiceSort} onSort={requestInvoiceSort} />
                    <SortableHeader label="Customer" sortKey="contact_name" sort={invoiceSort} onSort={requestInvoiceSort} />
                    <SortableHeader label="Due" sortKey="due_date" sort={invoiceSort} onSort={requestInvoiceSort} />
                    <SortableHeader label="Predicted" sortKey="predicted_paid_date" sort={invoiceSort} onSort={requestInvoiceSort} />
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
                  {sortedInvoices.map((invoice) => (
                    <tr key={invoice.id}>
                      <td>{invoice.invoice_number}</td>
                      <td>{invoice.contact_name}</td>
                      <td>{invoice.due_date}</td>
                      <td>{invoice.accelerated_paid_date || invoice.predicted_paid_date}</td>
                      <td className="right">{formatCurrency(invoice.amount_due)}</td>
                    </tr>
                  ))}
                  {data.invoices.length === 0 && (
                    <tr>
                      <td colSpan="5">
                        <div className="empty inline-empty">No open invoices. Sync Xero to pull the latest records.</div>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>
        </div>

        <aside className="panel signal-panel">
          <CashFloorControl
            value={data.settings?.cash_floor ?? data.forecast.cash_floor}
            forecast={data.forecast}
            onUpdateCashFloor={onUpdateCashFloor}
            busy={busy}
          />
          <RecentActivity entries={data.actionLog} onViewAll={onViewActivity} />
          {syncResult?.status === "synced" && <p className={syncResultClass(syncResult)}>{syncSummary(syncResult)}</p>}
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
        <div className="table-wrap">
          <table className="table table-sm">
            <thead>
              <tr>
                <SortableHeader label="Name" sortKey="name" sort={payerSort} onSort={requestPayerSort} />
                <SortableHeader label="Grade" sortKey="grade" sort={payerSort} onSort={requestPayerSort} />
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
                  onClick={() => setSelectedId(contact.id)}
                >
                  <td>{contact.name}</td>
                  <td><span className={gradeClass(contact.grade)}>{contact.grade}</span></td>
                  <td className="right exposure-cell">{formatCurrency(contact.exposure)}</td>
                  <td className="right">{Math.max(0, Math.round(Number(contact.avg_days_late || 0)))} days late</td>
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
      </section>

      <aside className="panel side-panel">
        {selected && (
          <>
            <div className="payer-title">
              <h2>{selected.name}</h2>
              <span className={gradeClass(selected.grade)}>{selected.grade}</span>
            </div>
            <dl className="stats-list">
              <div><dt>What they currently owe you</dt><dd>{formatCurrency(selected.exposure)}</dd></div>
              <div><dt>How much business you've done with them (past year)</dt><dd>{formatCurrency(selected.revenue_12m)}</dd></div>
            </dl>
            <p className="payer-summary">{payerTimingSentence(selected)}</p>
          </>
        )}
      </aside>
    </main>
  );
}

function AgentQueue({ proposals, onApprove, onDismiss, onEdit, busy }) {
  const [drafts, setDrafts] = useState({});
  const pending = proposals.filter((proposal) => proposal.status === "pending");

  return (
    <main className="content">
      <div className="panel-head page-head">
        <h1>Agent Queue</h1>
      </div>
      <div className="proposal-grid">
        {pending.map((proposal) => {
          const draftBody = drafts[proposal.id] ?? proposal.draft_body ?? "";
          return (
            <article className="proposal-card" key={proposal.id}>
              <div className="proposal-top">
                <span className="badge badge-neutral">{proposal.type.replaceAll("_", " ")}</span>
                <strong>{proposal.contact_name}</strong>
              </div>
              <blockquote>{proposal.reasoning_text}</blockquote>
              <div className="impact">
                +{formatCurrency(proposal.expected_impact_dollars)} · {proposal.expected_days_accelerated} days sooner
              </div>
              {proposal.draft_subject && (
                <details className="email-preview">
                  <summary>{proposal.draft_subject}</summary>
                  <textarea
                    value={draftBody}
                    onChange={(event) => setDrafts((current) => ({ ...current, [proposal.id]: event.target.value }))}
                  />
                </details>
              )}
              {proposal.recommendation_detail && <p className="recommendation">{proposal.recommendation_detail}</p>}
              <div className="actions">
                <button className="button primary btn btn-primary btn-sm" disabled={busy} onClick={() => onApprove(proposal.id)}>
                  <Check size={16} /> Approve
                </button>
                {proposal.draft_subject && (
                  <button className="button ghost btn btn-ghost btn-sm" disabled={busy} onClick={() => onEdit(proposal.id, draftBody)}>
                    Edit
                  </button>
                )}
                <button className="icon-button danger-icon btn btn-square btn-ghost btn-sm" disabled={busy} onClick={() => onDismiss(proposal.id)} title="Dismiss">
                  <X size={16} />
                </button>
              </div>
            </article>
          );
        })}
        {pending.length === 0 && <div className="empty">No pending proposals</div>}
      </div>
    </main>
  );
}

function Outbox({ outbox }) {
  const [outboxSort, requestOutboxSort] = useSort("timestamp", "desc");
  const sorted = useMemo(
    () =>
      sortRows(outbox, outboxSort, {
        timestamp: (entry) => Date.parse(entry.timestamp),
        to: (entry) => entry.to,
        subject: (entry) => entry.subject
      }),
    [outbox, outboxSort]
  );

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
                <SortableHeader label="Subject" sortKey="subject" sort={outboxSort} onSort={requestOutboxSort} />
                <th className="right">Draft</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((entry) => (
                <tr key={entry.id}>
                  <td>{formatDateTime(entry.timestamp)}</td>
                  <td>{entry.to}</td>
                  <td>
                    <details className="message-preview">
                      <summary>{entry.subject}</summary>
                      <pre>{entry.body}</pre>
                    </details>
                  </td>
                  <td className="right">
                    <a className="button ghost btn btn-ghost btn-xs outbox-draft-link" href={mailtoDraftHref(entry)}>
                      <ExternalLink size={14} /> Open draft
                    </a>
                  </td>
                </tr>
              ))}
              {sorted.length === 0 && (
                <tr>
                  <td colSpan="4">
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
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section className="modal-panel" role="dialog" aria-modal="true" aria-label={title} onMouseDown={(event) => event.stopPropagation()}>
        <div className="panel-head">
          <h2>{title}</h2>
          <button className="icon-button btn btn-square btn-ghost btn-sm" type="button" onClick={onClose} title="Close">
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
    "Look in Agent Queue for suggested actions like reminders or smarter payment terms.",
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

function DevToolsPanel({
  data,
  syncResult,
  busy,
  onClose,
  onSyncXero,
  onSeedPortfolio,
  onSelectTenant,
  onMarkFirstPaid,
  onScanResearch
}) {
  const researchSources = Object.entries(data?.research?.sources || {});
  const firstInvoice = data?.invoices?.[0];
  return (
    <ModalShell title="Developer tools" onClose={onClose}>
      {/* demo-only, not user-facing: open with Ctrl+Shift+D for hackathon resets and admin checks. */}
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
            onSeedPortfolio={onSeedPortfolio}
            onSelectTenant={onSelectTenant}
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
    const next = await fetchAll();
    setData(next);
  }

  useEffect(() => {
    refresh().catch((err) => setError(err.message));
  }, []);

  useEffect(() => {
    function openDevTools(event) {
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
      await fn();
      await refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  const activeContent = useMemo(() => {
    if (!data) return <main className="content"><div className="empty">Loading Nero</div></main>;
    if (activeTab === "dashboard") {
      return (
        <Dashboard
          data={data}
          cashDisplay={cashDisplay}
          busy={busy}
          onRunAgent={() => act(runAgent)}
          onSyncXero={() => act(async () => setSyncResult(await syncXero()))}
          onSelectTenant={(tenantId) => act(async () => setSyncResult(await selectXeroTenant(tenantId)))}
          onUpdateCashFloor={(cashFloor) => act(() => updateCashFloor(cashFloor))}
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
          busy={busy}
          onApprove={(id) => act(() => approveProposal(id))}
          onDismiss={(id) => act(() => dismissProposal(id))}
          onEdit={(id, body) => act(() => editProposal(id, body))}
        />
      );
    }
    if (activeTab === "outbox") return <Outbox outbox={data.outbox} />;
    return <ActivityHistory entries={data.actionLog} />;
  }, [activeTab, data, cashDisplay, busy, syncResult]);

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
          onMarkFirstPaid={() => data?.invoices?.[0] && act(() => markPaid(data.invoices[0].id))}
          onScanResearch={() => act(scanResearch)}
        />
      )}
    </div>
  );
}

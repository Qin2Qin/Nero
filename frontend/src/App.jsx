import {
  ArrowRight,
  Check,
  ChevronDown,
  ChevronUp,
  Database,
  ExternalLink,
  HelpCircle,
  Info,
  Mail,
  Minus,
  RefreshCw,
  Search,
  TrendingDown,
  TrendingUp,
  X
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
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
  approveProposalsBatch,
  createManualProposal,
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
  undoProposal,
  updateCashFloor
} from "./api.js";

const TABS = [
  { id: "dashboard", label: "Home" },
  { id: "payers", label: "Customers" },
  { id: "queue", label: "Approvals" },
  { id: "outbox", label: "Sent" },
  { id: "activity", label: "Activity" }
];

const TODAY = new Date("2026-07-04T00:00:00Z");
const SUPPORT_EMAIL = "support@placeholder-domain.com";

const TYPE_META = {
  reminder: { label: "Payment reminder", pillClass: "type-amber", tintClass: "tint-amber", labelClass: "amber", color: "#8A6400" },
  escalation: { label: "Escalation", pillClass: "type-danger", tintClass: "tint-danger", labelClass: "danger", color: "#C93A2B" },
  deposit_recommendation: { label: "Deposit terms", pillClass: "type-orange", tintClass: "tint-orange", labelClass: "orange", color: "#A34E00" },
  terms_recommendation: { label: "Payment terms", pillClass: "type-orange", tintClass: "tint-orange", labelClass: "orange", color: "#A34E00" }
};

function typeMetaFor(type) {
  return TYPE_META[type] || { label: type.replaceAll("_", " "), pillClass: "pill-neutral", tintClass: "tint-amber", labelClass: "amber", color: "#6A6E78" };
}

function parseDate(value) {
  return new Date(`${value}T00:00:00Z`);
}

function addDays(date, days) {
  const next = new Date(date);
  next.setUTCDate(next.getUTCDate() + days);
  return next;
}

function formatCurrency(value) {
  if (value === null || value === undefined) return "";
  return `£${money(Math.round(Number(value || 0)))}`;
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
  return `grade-${String(grade || "").charAt(0).toLowerCase()}`;
}

function TrendCell({ slope }) {
  if (slope > 1) return <span className="trend-cell trend-up"><TrendingUp size={15} /> getting slower</span>;
  if (slope < -1) return <span className="trend-cell trend-down"><TrendingDown size={15} /> improving</span>;
  return <span className="trend-cell trend-flat"><Minus size={15} /> steady</span>;
}

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
  if (Number(slope || 0) > 1) return "and they're getting slower";
  if (Number(slope || 0) < -1) return "and they're getting better";
  return "and that's been steady";
}

function payerTimingSentence(contact) {
  const invoiceCount = Number(contact.invoice_count || 0);
  const avgLate = Math.max(0, Math.round(Number(contact.avg_days_late || 0)));
  if (avgLate === 0) {
    return `Based on ${invoiceCount} paid ${plural(invoiceCount, "invoice")}, ${contact.name} reliably pays on time or early.`;
  }
  const unpredictable = Number(contact.stdev_days_late || 0) >= 10 ? ", though timing varies," : "";
  return `Based on ${invoiceCount} paid ${plural(invoiceCount, "invoice")}, ${contact.name} pays about ${avgLate} ${plural(avgLate, "day")} late${unpredictable} ${trendText(contact.trend_slope)}.`;
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
        <Icon className={active ? "sort-icon active" : "sort-icon"} size={12} aria-hidden="true" />
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
  if (status?.connected) return { className: "pill pill-success", label: "Connected" };
  if (status?.demo_mode) return { className: "pill pill-neutral", label: "Demo mode" };
  return { className: "pill pill-danger", label: "Not connected" };
}

function syncSummary(result) {
  if (!result) return "";
  if (result.status === "synced") {
    return `Synced ${result.fetched?.contacts ?? 0} contacts, ${result.fetched?.invoices ?? 0} invoices, ${result.fetched?.payments ?? 0} payments.`;
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

function readinessBadge(status) {
  if (status === "ready") return "pill pill-success";
  if (status === "blocked") return "pill pill-danger";
  return "pill pill-neutral";
}

function barColor(days) {
  if (days <= 0) return "#2FA35A";
  if (days <= 7) return "#9CC24D";
  if (days <= 14) return "#E0A100";
  if (days <= 25) return "#D97A1E";
  return "#C93A2B";
}

function genHistory(contact) {
  const n = Math.min(9, Math.max(4, Number(contact.invoice_count) || 6));
  const avg = Number(contact.avg_days_late || 0);
  const sd = Number(contact.stdev_days_late || 0);
  const slope = Number(contact.trend_slope || 0);
  let seed = 0;
  const key = String(contact.id || contact.name || "x");
  for (const ch of key) seed = (seed * 31 + ch.charCodeAt(0)) >>> 0;
  const rand = () => {
    seed = (seed * 1103515245 + 12345) & 0x7fffffff;
    return seed / 0x7fffffff;
  };
  const out = [];
  for (let i = 0; i < n; i += 1) {
    const t = i - (n - 1) / 2;
    out.push(Math.round(avg + slope * t + (rand() - 0.5) * 2 * sd));
  }
  return out;
}

function AppStoreReadiness({ readiness }) {
  const items = readiness?.items || [];
  return (
    <section className="card">
      <div className="card-head">
        <h2>Xero App Store</h2>
        <span className="pill pill-neutral">
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
        <a className="btn-ghost" style={{ display: "inline-flex", alignItems: "center", gap: 6, marginTop: 10 }} href={readiness.source_url} target="_blank" rel="noreferrer">
          <ExternalLink size={14} /> Certification checkpoints
        </a>
      )}
    </section>
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
    <section className="card">
      <div className="card-head">
        <h2>Xero connection</h2>
        <span className={badge.className}>{badge.label}</span>
      </div>
      <dl className="dev-status-list">
        <div><dt>Credentials</dt><dd>{credentialState}</dd></div>
        <div><dt>OAuth token</dt><dd>{tokenState}</dd></div>
        <div><dt>Tenant</dt><dd>{activeTenant?.tenant_name || status?.tenant_id || "Not selected"}</dd></div>
        <div><dt>Expires</dt><dd>{formatDate(status?.expires_at)}</dd></div>
        <div><dt>Dashboard data</dt><dd>{source?.label || "Unknown"}</dd></div>
      </dl>
      {tenantOptions.length > 1 && (
        <label className="tenant-picker">
          <span>Xero organisation</span>
          <select value={tenants.active_tenant_id || ""} onChange={(event) => onSelectTenant(event.target.value)} disabled={busy}>
            {tenantOptions.map((tenant) => (
              <option key={tenant.tenant_id} value={tenant.tenant_id}>
                {tenant.is_demo ? "Demo - " : ""}{tenant.tenant_name}
              </option>
            ))}
          </select>
        </label>
      )}
      <div className="mini-actions">
        <button className="btn btn-primary btn-sm" onClick={onSyncXero} disabled={busy || !canSync}>
          <RefreshCw size={16} /> {status?.demo_mode ? "Check demo sync" : "Sync Xero"}
        </button>
        <button className="btn btn-outline btn-sm" onClick={onSeedPortfolio} disabled={busy}>
          <Database size={16} /> Seed portfolio
        </button>
        {!status?.demo_mode && !status?.connected && status?.client_credentials_configured && (
          <a className="btn btn-outline btn-sm" href="/auth/login">
            <ExternalLink size={16} /> Connect
          </a>
        )}
      </div>
      {syncResult && <p className="sync-result">{syncSummary(syncResult)}</p>}
      {source?.detail && <p className="compact-note muted">{source.detail}</p>}
      {!status?.demo_mode && !status?.connected && !status?.client_credentials_configured && (
        <p className="compact-note muted">Live credentials missing.</p>
      )}
    </section>
  );
}

function ResearchSignals({ sources, onScanResearch, busy }) {
  return (
    <section className="card">
      <div className="card-head">
        <h2>Opportunity monitor</h2>
        <button className="icon-btn-round" onClick={onScanResearch} disabled={busy} title="Scan research" type="button">
          <RefreshCw size={16} />
        </button>
      </div>
      <div style={{ display: "grid", gap: 6 }}>
        {sources.length === 0 && <p className="muted">No raw research files indexed.</p>}
        {sources.map(([source, summary]) => (
          <div key={source} style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: "2px 10px", padding: "9px 0", borderBottom: "1px solid var(--border-subtle)" }}>
            <strong style={{ gridColumn: "1 / -1" }}>{source}</strong>
            <span className="muted">{summary.files} files</span>
            <span className="muted">{summary.records} records</span>
          </div>
        ))}
      </div>
    </section>
  );
}

function buildRangeBuckets(buckets, range) {
  if (range === "4w") return { list: buckets.slice(0, 4), realN: Math.min(4, buckets.length) };
  if (range === "quarter" && buckets.length) {
    const n = buckets.length;
    const recentAvg = buckets.slice(-4).reduce((sum, bucket) => sum + bucket.predicted_cash_in, 0) / Math.min(4, n);
    const last = buckets[n - 1];
    let cum = last.cumulative_predicted;
    const extra = [];
    for (let i = 1; i <= 4; i += 1) {
      const day = addDays(parseDate(last.week_start), 7 * i);
      cum += recentAvg;
      extra.push({
        week_start: day.toISOString().slice(0, 10),
        cumulative_due: null,
        cumulative_predicted: cum,
        cumulative_accelerated: cum,
        below_floor: false,
        projected: true
      });
    }
    return { list: [...buckets, ...extra], realN: n };
  }
  return { list: buckets, realN: buckets.length };
}

function ForecastTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  // The invisible fill-under-the-line Area shares a dataKey with the "Realistic
  // forecast" Line but has no name of its own, so Recharts defaults its tooltip
  // entry's name to the raw dataKey. Drop that duplicate, unnamed entry.
  const rows = payload.filter((entry) => !(entry.dataKey === "predictedSolid" && entry.name === "predictedSolid"));
  return (
    <div style={{ border: "1px solid #E5E5EA", borderRadius: 8, boxShadow: "0 8px 24px rgba(20,35,46,0.12)", background: "#fff", padding: "10px 14px", fontSize: 13 }}>
      <div style={{ fontWeight: 600, marginBottom: 4 }}>{`Week of ${label}`}</div>
      {rows.map((entry) => (
        <div key={entry.dataKey} style={{ color: entry.color }}>
          {entry.name}: {entry.value === null || entry.value === undefined ? "" : formatCurrency(entry.value)}
        </div>
      ))}
    </div>
  );
}

function ForecastChart({ forecast, range }) {
  const buckets = forecast?.buckets?.filter((bucket) => bucket.week_start !== "later") || [];
  if (!buckets.length) return <div className="empty">No forecast data</div>;

  const { list, realN } = buildRangeBuckets(buckets, range);
  const hasAccel = buckets.some((bucket) => (bucket.cumulative_accelerated ?? bucket.cumulative_predicted) !== bucket.cumulative_predicted);

  const data = list.map((bucket, index) => ({
    week: formatWeekLabel(bucket.week_start),
    due: bucket.cumulative_due,
    predictedSolid: index <= realN - 1 ? bucket.cumulative_predicted : null,
    predictedProjected: index >= realN - 1 ? bucket.cumulative_predicted : null,
    accelerated: index < realN ? bucket.cumulative_accelerated ?? bucket.cumulative_predicted : null
  }));

  return (
    <div className="chart-wrap">
      <div className="chart-renderer" role="img" aria-label="Cash forecast">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 14, right: 16, bottom: 8, left: 8 }}>
            <CartesianGrid stroke="#EEEEF2" vertical={false} />
            <XAxis dataKey="week" tick={{ fill: "#9094A0", fontSize: 12 }} tickLine={false} axisLine={false} />
            <YAxis tickFormatter={compactMoney} tick={{ fill: "#9094A0", fontSize: 12 }} tickLine={false} axisLine={false} width={54} />
            <Tooltip content={<ForecastTooltip />} />
            <ReferenceLine
              y={forecast.cash_floor}
              stroke="#C93A2B"
              strokeDasharray="3 5"
              label={{ value: `Cash floor ${compactMoney(forecast.cash_floor)}`, fill: "#C93A2B", fontSize: 12, position: "insideTopRight" }}
            />
            <Area type="monotone" dataKey="predictedSolid" fill="#7A2BF5" fillOpacity={0.06} stroke="none" legendType="none" isAnimationActive={false} />
            <Line
              name="If everyone paid on time"
              type="monotone"
              dataKey="due"
              stroke="#9AA7B0"
              strokeWidth={2}
              strokeDasharray="6 6"
              dot={false}
            />
            {hasAccel && (
              <Line
                name="After approved actions"
                type="monotone"
                dataKey="accelerated"
                stroke="#1F8A4C"
                strokeWidth={2.5}
                dot={{ r: 3, fill: "#1F8A4C", strokeWidth: 0 }}
                activeDot={{ r: 5 }}
              />
            )}
            <Line
              name="Realistic forecast"
              type="monotone"
              dataKey="predictedSolid"
              stroke="#7A2BF5"
              strokeWidth={2.5}
              dot={{ r: 3.5, fill: "#7A2BF5", stroke: "#fff", strokeWidth: 1.5 }}
              activeDot={{ r: 5 }}
            />
            {range === "quarter" && (
              <Line
                name="Projected trend"
                type="monotone"
                dataKey="predictedProjected"
                stroke="#C9AEF7"
                strokeWidth={2.5}
                strokeDasharray="6 5"
                dot={false}
                legendType="none"
              />
            )}
            <Legend wrapperStyle={{ fontSize: 13, color: "#6A6E78" }} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function CashFloorControl({ settings, forecast, onUpdateCashFloor, busy }) {
  const appliedFloor = settings?.cash_floor ?? forecast?.cash_floor ?? 0;
  const appliedMode = settings?.cash_floor_mode ?? "manual";
  const suggestedValue = settings?.suggested_cash_floor ?? appliedFloor;
  const [uiMode, setUiMode] = useState(appliedMode);
  const [draft, setDraft] = useState(appliedMode === "suggested" ? suggestedValue : appliedFloor);

  useEffect(() => {
    setUiMode(appliedMode);
    setDraft(appliedMode === "suggested" ? suggestedValue : appliedFloor);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [appliedFloor, appliedMode, suggestedValue]);

  const isSuggestedMode = uiMode === "suggested";
  const warnCount = forecast?.buckets?.filter((bucket) => bucket.week_start !== "later" && bucket.cumulative_predicted < draft).length || 0;
  const isChanged = uiMode !== appliedMode || (uiMode === "manual" && Number(draft) !== Number(appliedFloor));
  const maxForecast = Math.max(...(forecast?.buckets || []).map((bucket) => bucket.cumulative_predicted || 0), 15000);
  const maxFloor = Math.max(15000, Math.ceil(maxForecast / 5000) * 5000);
  const presets = [...new Set([5000, Math.round((maxFloor * 0.45) / 5000) * 5000, Math.round((maxFloor * 0.7) / 5000) * 5000])].filter(
    (preset) => preset > 0 && preset <= maxFloor
  );

  function setManual() {
    setUiMode("manual");
    setDraft(appliedFloor);
  }

  function setSuggested() {
    setUiMode("suggested");
    setDraft(suggestedValue);
  }

  return (
    <section className="card floor-card">
      <div className="card-head">
        <h2>Cash floor</h2>
        <span className={warnCount ? "floor-badge at-risk" : "floor-badge covered"}>
          {warnCount ? `${warnCount} weeks at risk` : "Covered"}
        </span>
      </div>

      <div className="floor-mode-toggle">
        <button type="button" className={!isSuggestedMode ? "manual-active" : ""} onClick={setManual}>Manual</button>
        <button type="button" className={isSuggestedMode ? "suggested-active" : ""} onClick={setSuggested}>Suggested</button>
      </div>

      <div className="floor-readout">
        <strong>{formatCurrency(draft)}</strong>
        {isSuggestedMode ? (
          <span className="recommended-chip">Recommended</span>
        ) : (
          <span className="operating-min">operating minimum</span>
        )}
      </div>

      {isSuggestedMode ? (
        <>
          <div className="suggested-box">
            <p>
              <Info size={16} color="#7A2BF5" style={{ marginTop: 1 }} />
              <span>This covers your typical payroll, rent and monthly spending, with a little room to breathe.</span>
            </p>
            <div className="floor-tag-row">
              <span className="floor-tag">Payroll</span>
              <span className="floor-tag">Rent</span>
              <span className="floor-tag">Typical spending</span>
            </div>
          </div>
          <button className="btn btn-primary block" disabled={busy || !isChanged} onClick={() => onUpdateCashFloor(draft, "suggested")}>
            Apply floor
          </button>
        </>
      ) : (
        <>
          <input
            className="range-input"
            type="range"
            min="0"
            max={maxFloor}
            step="500"
            value={draft}
            onChange={(event) => setDraft(Number(event.target.value))}
            aria-label="Cash floor"
          />
          <div className="preset-row">
            {presets.map((preset) => (
              <button
                key={preset}
                type="button"
                className={draft === preset ? "preset-chip active" : "preset-chip"}
                onClick={() => setDraft(preset)}
              >
                {compactMoney(preset)}
              </button>
            ))}
          </div>
          <button className="btn btn-primary block" disabled={busy || !isChanged} onClick={() => onUpdateCashFloor(draft, "manual")}>
            Apply floor
          </button>
        </>
      )}
    </section>
  );
}

function DataDisclosure({ source }) {
  if (source?.mode !== "synthetic" && source?.mode !== "fixture") return null;
  const label = source?.mode === "synthetic" ? "Synthetic demo data — not real Xero records" : "Offline demo data";
  return (
    <div className="data-disclosure">
      <Info size={14} />
      {label}
    </div>
  );
}

function Home({ data, cashDisplay, chartRange, onSetChartRange, onUpdateCashFloor, onViewApprovals, onViewActivity, busy }) {
  const [invoiceSort, requestInvoiceSort] = useSort("due_date", "asc");
  const cutoff = addDays(TODAY, 30);
  const dueNext30 = data.invoices.filter((invoice) => parseDate(invoice.due_date) <= cutoff).reduce((sum, invoice) => sum + invoice.amount_due, 0);
  const predictedNext30 = data.invoices
    .filter((invoice) => parseDate(invoice.predicted_paid_date) <= cutoff)
    .reduce((sum, invoice) => sum + invoice.amount_due, 0);
  const pending = data.proposals.filter((proposal) => proposal.status === "pending");
  const pendingImpact = pending.reduce((sum, proposal) => sum + proposal.expected_impact_dollars, 0);
  const realBuckets = data.forecast.buckets.filter((bucket) => bucket.week_start !== "later");
  const belowBuckets = realBuckets.filter((bucket) => bucket.below_floor);
  let firstSafe = null;
  for (let i = 1; i < realBuckets.length; i += 1) {
    if (realBuckets[i - 1].below_floor && !realBuckets[i].below_floor) {
      firstSafe = realBuckets[i];
      break;
    }
  }

  const sortedInvoices = useMemo(
    () =>
      sortRows(data.invoices, invoiceSort, {
        invoice_number: (invoice) => invoice.invoice_number,
        contact_name: (invoice) => invoice.contact_name,
        due_date: (invoice) => Date.parse(`${invoice.due_date}T00:00:00Z`),
        predicted_paid_date: (invoice) => Date.parse(`${invoice.predicted_paid_date}T00:00:00Z`),
        amount_due: (invoice) => Number(invoice.amount_due || 0)
      }),
    [data.invoices, invoiceSort]
  );

  const invoiceTotal = data.invoices.reduce((sum, invoice) => sum + invoice.amount_due, 0);

  return (
    <main className="page">
      <DataDisclosure source={data.dataSource} />

      <section className="hero-story">
        <div className="hero-copy">
          <p className="hero-eyebrow">Next 30 days</p>
          <h1 className="hero-sentence">
            <span>{formatCurrency(dueNext30)}</span> is due, but only <em>{formatCurrency(predictedNext30)}</em> will arrive on time.
          </h1>
          <p className="hero-sub">
            {pending.length
              ? `${pending.length} drafted ${plural(pending.length, "action")} in Approvals could bring ${formatCurrency(pendingImpact)} in sooner.`
              : "No actions waiting — your queue is clear."}
          </p>
        </div>
        <div className="hero-side">
          <div className="hero-forward">
            <p>Brought forward so far</p>
            <strong>{formatCurrency(cashDisplay)}</strong>
          </div>
          {pending.length > 0 && (
            <button className="btn btn-primary" onClick={onViewApprovals}>
              Review {pending.length} {plural(pending.length, "action")}
              <ArrowRight size={16} />
            </button>
          )}
        </div>
      </section>

      <div className="home-columns">
        <div className="home-grid">
          <section className="card">
            <div className="chart-legend-row">
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <h2>Cash coming in</h2>
                {belowBuckets.length > 0 && (
                  <span className="chart-below-floor">Below floor until {firstSafe ? formatWeekLabel(firstSafe.week_start) : "later"}</span>
                )}
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap" }}>
                <div className="chart-legend">
                  <span><span className="legend-swatch dashed" />If everyone paid on time</span>
                  <span><span className="legend-swatch" style={{ background: "#7A2BF5" }} />Realistic forecast</span>
                  <span style={{ opacity: data.forecast.buckets.some((b) => (b.cumulative_accelerated ?? b.cumulative_predicted) !== b.cumulative_predicted) ? 1 : 0.35 }}>
                    <span className="legend-swatch" style={{ background: "#1F8A4C" }} />After approved actions
                  </span>
                  {chartRange === "quarter" && (
                    <span><span className="legend-swatch projected-dash" />Projected trend</span>
                  )}
                </div>
                <div className="range-toggle">
                  <button type="button" className={chartRange === "4w" ? "active" : ""} onClick={() => onSetChartRange("4w")}>4 weeks</button>
                  <button type="button" className={chartRange === "8w" ? "active" : ""} onClick={() => onSetChartRange("8w")}>8 weeks</button>
                  <button type="button" className={chartRange === "quarter" ? "active" : ""} onClick={() => onSetChartRange("quarter")}>Quarter</button>
                </div>
              </div>
            </div>
            <ForecastChart forecast={data.forecast} range={chartRange} />
          </section>

          <section className="card">
            <div className="card-head">
              <h2>Open invoices</h2>
              <span className="table-total-line">{data.invoices.length} invoices · {formatCurrency(invoiceTotal)} outstanding</span>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <SortableHeader label="Invoice" sortKey="invoice_number" sort={invoiceSort} onSort={requestInvoiceSort} />
                    <SortableHeader label="Customer" sortKey="contact_name" sort={invoiceSort} onSort={requestInvoiceSort} />
                    <SortableHeader label="Due" sortKey="due_date" sort={invoiceSort} onSort={requestInvoiceSort} />
                    <SortableHeader label="Expected" sortKey="predicted_paid_date" sort={invoiceSort} onSort={requestInvoiceSort} />
                    <SortableHeader label="Amount" sortKey="amount_due" sort={invoiceSort} onSort={requestInvoiceSort} align="right" defaultDirection="desc" />
                  </tr>
                </thead>
                <tbody>
                  {sortedInvoices.map((invoice) => {
                    const overdue = Math.round((TODAY - parseDate(invoice.due_date)) / 86400000);
                    const lateBy = Math.round((parseDate(invoice.predicted_paid_date) - parseDate(invoice.due_date)) / 86400000);
                    return (
                      <tr key={invoice.id}>
                        <td>{invoice.invoice_number}</td>
                        <td>{invoice.contact_name}</td>
                        <td>
                          {formatWeekLabel(invoice.due_date)}
                          <span className="cell-meta" style={{ color: overdue > 7 ? "#C93A2B" : overdue > 0 ? "#B85A00" : "#9094A0" }}>
                            {overdue > 0 ? `${overdue} days overdue` : `in ${-overdue} days`}
                          </span>
                        </td>
                        <td>
                          {formatWeekLabel(invoice.predicted_paid_date)}
                          <span className="cell-meta">{lateBy > 0 ? `${lateBy} days after due` : "on time"}</span>
                        </td>
                        <td className="right amount-cell">{formatCurrency(invoice.amount_due)}</td>
                      </tr>
                    );
                  })}
                  {data.invoices.length === 0 && (
                    <tr>
                      <td colSpan="5"><div className="empty inline-empty">No open invoices. Sync Xero to pull the latest records.</div></td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>
        </div>

        <aside className="aside-stack">
          <CashFloorControl settings={data.settings} forecast={data.forecast} onUpdateCashFloor={onUpdateCashFloor} busy={busy} />
          <section className="card recent-activity">
            <div className="card-head">
              <h2>Recent activity</h2>
              <button className="btn-ghost" type="button" onClick={onViewActivity}>View all</button>
            </div>
            <div className="activity-mini-list">
              {data.actionLog.slice(0, 4).map((entry) => (
                <div className="activity-mini-row" key={entry.id}>
                  <span>{formatDateTime(entry.timestamp)}</span>
                  <p>{entry.event}</p>
                </div>
              ))}
              {data.actionLog.length === 0 && <p className="muted" style={{ fontSize: 13.5 }}>Approve an action and it will show up here.</p>}
            </div>
          </section>
        </aside>
      </div>
    </main>
  );
}

function Customers({ data, onCreateManualProposal, onReviewProposal }) {
  const { contacts, invoices } = data;
  const [search, setSearch] = useState("");
  const debouncedSearch = useDebouncedValue(search, 200).trim().toLowerCase();
  const [payerSort, requestPayerSort] = useSort("exposure", "desc");

  const ranked = useMemo(() => contacts.map((contact) => ({ ...contact, exposure: exposureFor(contact.id, invoices) })), [contacts, invoices]);
  const filtered = useMemo(() => ranked.filter((contact) => contact.name.toLowerCase().includes(debouncedSearch)), [ranked, debouncedSearch]);
  const sorted = useMemo(
    () =>
      sortRows(filtered, payerSort, {
        name: (contact) => contact.name,
        grade: (contact) => contact.grade,
        exposure: (contact) => Number(contact.exposure || 0),
        avg_days_late: (contact) => Number(contact.avg_days_late || 0),
        trend_slope: (contact) => Number(contact.trend_slope || 0)
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

  const selProposals = selected ? data.proposals.filter((proposal) => proposal.contact_id === selected.id) : [];
  const selPending = selProposals.filter((proposal) => proposal.status === "pending");
  const selApproved = selProposals.filter((proposal) => proposal.status === "approved");
  const selInvoices = selected ? invoices.filter((invoice) => invoice.contact_id === selected.id) : [];
  const selHasOpenInvoice = selInvoices.length > 0;

  return (
    <main className="page customers-grid">
      <section className="card">
        <div className="card-head">
          <div>
            <h1>Customers</h1>
            <p className="page-sub">Ranked by what they owe you right now</p>
          </div>
          <label className="search-field">
            <Search size={15} aria-hidden="true" />
            <input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search" aria-label="Search customers" />
          </label>
        </div>
        <div className="table-wrap" style={{ marginTop: 12 }}>
          <table>
            <thead>
              <tr>
                <SortableHeader label="Customer" sortKey="name" sort={payerSort} onSort={requestPayerSort} />
                <SortableHeader label="Grade" sortKey="grade" sort={payerSort} onSort={requestPayerSort} />
                <SortableHeader label="Owes you" sortKey="exposure" sort={payerSort} onSort={requestPayerSort} align="right" defaultDirection="desc" />
                <SortableHeader label="Usually pays" sortKey="avg_days_late" sort={payerSort} onSort={requestPayerSort} align="right" defaultDirection="desc" />
                <SortableHeader label="Direction" sortKey="trend_slope" sort={payerSort} onSort={requestPayerSort} defaultDirection="desc" />
              </tr>
            </thead>
            <tbody>
              {sorted.map((contact) => (
                <tr
                  key={contact.id}
                  className={selected?.id === contact.id ? "selected-row" : ""}
                  onClick={() => setSelectedId(contact.id)}
                  style={{ cursor: "pointer" }}
                >
                  <td style={{ fontWeight: 500 }}>{contact.name}</td>
                  <td><span className={`grade-pill ${gradeClass(contact.grade)}`}>{contact.grade}</span></td>
                  <td className="right amount-cell">{formatCurrency(contact.exposure)}</td>
                  <td className="right">{Math.max(0, Math.round(Number(contact.avg_days_late || 0)))} days late</td>
                  <td><TrendCell slope={contact.trend_slope} /></td>
                </tr>
              ))}
              {sorted.length === 0 && (
                <tr><td colSpan="5"><div className="empty inline-empty">No matching customers. Clear the search or sync Xero history.</div></td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <aside className="card customer-rail">
        {selected && (
          <>
            <div className="rail-head">
              <h2>{selected.name}</h2>
              <span className={`grade-pill lg ${gradeClass(selected.grade)}`}>{selected.grade}</span>
            </div>
            <p className="rail-sentence">{payerTimingSentence(selected)}</p>
            <dl className="rail-stats">
              <div><dt>Owes you now</dt><dd>{formatCurrency(selected.exposure)}</dd></div>
              <div><dt>Business past year</dt><dd>{formatCurrency(selected.revenue_12m)}</dd></div>
              <div><dt>Paid invoices on record</dt><dd>{selected.invoice_count}</dd></div>
            </dl>

            <div className="rail-section">
              <h3>Their open invoices</h3>
              {selInvoices.length === 0 && <p className="muted" style={{ fontSize: 13.5 }}>Nothing outstanding.</p>}
              {selInvoices.map((invoice) => (
                <div className="rail-invoice-row" key={invoice.id}>
                  <span>{invoice.invoice_number} · due {formatWeekLabel(invoice.due_date)}</span>
                  <strong>{formatCurrency(invoice.amount_due)}</strong>
                </div>
              ))}
            </div>

            <div className="rail-section">
              <h3>Take action</h3>
              {selPending.length > 0 && (
                <div>
                  {selPending.map((proposal) => {
                    const meta = typeMetaFor(proposal.type);
                    return (
                      <button
                        key={proposal.id}
                        type="button"
                        className={`rail-action-btn ${meta.tintClass}`}
                        onClick={() => onReviewProposal(proposal.id)}
                      >
                        <span>
                          <span className={`rail-action-label ${meta.labelClass}`}>{meta.label}</span>
                          <span className="rail-action-impact">
                            +{formatCurrency(proposal.expected_impact_dollars)} · {proposal.expected_days_accelerated} days sooner
                          </span>
                        </span>
                        <ArrowRight size={15} color={meta.color} />
                      </button>
                    );
                  })}
                </div>
              )}
              {selPending.length === 0 && selApproved.length > 0 && (
                <p className="rail-action-sent"><Check size={15} /> Action already sent to {selected.name}</p>
              )}
              {selProposals.length === 0 && (
                <>
                  <p className="rail-no-action">No action drafted for {selected.name} yet.</p>
                  <div className="rail-quick-grid">
                    <button
                      type="button"
                      className="rail-quick-btn reminder"
                      disabled={!selHasOpenInvoice}
                      onClick={() => onCreateManualProposal(selected.id, "reminder")}
                    >
                      Draft reminder
                    </button>
                    <button
                      type="button"
                      className="rail-quick-btn deposit"
                      onClick={() => onCreateManualProposal(selected.id, "deposit")}
                    >
                      Request deposit
                    </button>
                  </div>
                </>
              )}
            </div>
          </>
        )}
      </aside>
    </main>
  );
}

function ApprovalsRing({ decided, total }) {
  const radius = 22;
  const circumference = 2 * Math.PI * radius;
  const fraction = total ? decided / total : 0;
  return (
    <div className="approvals-ring">
      <svg width="50" height="50" viewBox="0 0 52 52">
        <circle cx="26" cy="26" r={radius} fill="none" stroke="#EEEEF2" strokeWidth="6" />
        <circle
          cx="26"
          cy="26"
          r={radius}
          fill="none"
          stroke="#7A2BF5"
          strokeWidth="6"
          strokeLinecap="round"
          strokeDasharray={`${(circumference * fraction).toFixed(1)} ${circumference.toFixed(1)}`}
          transform="rotate(-90 26 26)"
          style={{ transition: "stroke-dasharray 500ms" }}
        />
      </svg>
      <div className="approvals-ring-value">{decided}/{total}</div>
    </div>
  );
}

function ProposalCard({ proposal, contact, isHighlighted, drafts, onDraftChange, recOverride, isEditingRec, recDraft, onRecEditStart, onRecChange, onRecCommit, onApprove, onDismiss, onUndo }) {
  const meta = typeMetaFor(proposal.type);
  const isMsg = proposal.type === "reminder" || proposal.type === "escalation";
  const gClass = gradeClass(contact?.grade);
  const hist = genHistory(contact || {});
  const avgLate = Math.max(0, Math.round(contact?.avg_days_late || 0));
  const initials = (proposal.contact_name || "?").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase();

  if (proposal.status === "approved") {
    return (
      <div className="decided-card approved">
        <Check size={17} color="#1F8A4C" />
        <span><strong>{proposal.contact_name}</strong> — {isMsg ? "queued for Sent" : "change accepted"}</span>
        <span className="impact-chip">+{formatCurrency(proposal.expected_impact_dollars)}</span>
        <button className="undo-btn" type="button" onClick={() => onUndo(proposal.id)}>Undo</button>
      </div>
    );
  }

  if (proposal.status === "dismissed") {
    return (
      <div className="decided-card dismissed">
        <X size={16} color="#9094A0" />
        <span><strong style={{ color: "#3F4249" }}>{proposal.contact_name}</strong> — set aside for now</span>
        <button className="undo-btn" type="button" onClick={() => onUndo(proposal.id)}>Undo</button>
      </div>
    );
  }

  let editable = null;
  if (proposal.recommendation_detail) {
    if (proposal.type === "deposit_recommendation") {
      const match = proposal.recommendation_detail.match(/(\d+)%/);
      if (match) editable = { raw: Number(match[1]), matchIndex: match.index, matchLen: match[0].length, suffix: "%" };
    } else if (proposal.type === "terms_recommendation") {
      const match = proposal.recommendation_detail.match(/net-(\d+)/i);
      if (match) editable = { raw: Number(match[1]), matchIndex: match.index, matchLen: match[0].length, prefix: "net-", suffix: "" };
    }
  }
  const currentVal = recOverride ?? editable?.raw;
  const displayImpact =
    editable && proposal.type === "deposit_recommendation" && editable.raw
      ? Math.round(proposal.expected_impact_dollars * (currentVal / editable.raw))
      : proposal.expected_impact_dollars;

  return (
    <article className={isHighlighted ? "proposal-card highlighted" : "proposal-card"}>
      {isHighlighted && (
        <span className="from-customer-tag"><ArrowRight size={12} /> Jumped from Customers</span>
      )}
      <div className="proposal-main">
        <div className={`avatar ${gClass}`}>{initials}</div>
        <div className="proposal-body">
          <div className="proposal-name-row">
            <strong>{proposal.contact_name}</strong>
            <span className={`type-pill ${meta.pillClass}`}>{meta.label}</span>
          </div>
          <p className="proposal-reasoning">{proposal.reasoning_text}</p>
        </div>
        <div className="proposal-impact">
          <div className="proposal-impact-value">+{formatCurrency(displayImpact)}</div>
          <div className="proposal-impact-sooner">{proposal.expected_days_accelerated} days sooner</div>
        </div>
      </div>

      {editable && (
        <div className="rec-box">
          {proposal.recommendation_detail.slice(0, editable.matchIndex)}
          {editable.prefix || ""}
          {isEditingRec ? (
            <input
              type="number"
              autoFocus
              value={recDraft ?? currentVal}
              onChange={(event) => onRecChange(proposal.id, event.target.value)}
              onBlur={() => onRecCommit(proposal.id, editable.raw)}
            />
          ) : (
            <button type="button" className="rec-edit-btn" title="Edit this number" onClick={() => onRecEditStart(proposal.id, currentVal)}>
              {currentVal}
            </button>
          )}
          {editable.suffix || ""}
          {proposal.recommendation_detail.slice(editable.matchIndex + editable.matchLen)}
          {recOverride !== undefined && recOverride !== editable.raw && <span className="rec-edited-tag"> (edited)</span>}
        </div>
      )}
      {!editable && proposal.recommendation_detail && <p className="rec-box">{proposal.recommendation_detail}</p>}

      {proposal.draft_subject && (
        <details className="draft-details">
          <summary>
            <Mail size={14} color="#9094A0" />
            {proposal.draft_subject}
            <span className="read-edit-tag">Read &amp; edit</span>
          </summary>
          <div className="draft-details-body">
            <textarea
              value={drafts[proposal.id] ?? proposal.draft_body ?? ""}
              onChange={(event) => onDraftChange(proposal.id, event.target.value)}
            />
          </div>
        </details>
      )}

      <div className="proposal-footer">
        <div className="history-bars">
          {hist.map((d, index) => (
            <div key={index} title={`${d} days late`} style={{ height: `${Math.max(4, Math.min(22, Math.round(3 + d * 0.34)))}px`, background: barColor(d) }} />
          ))}
        </div>
        <span className="hist-caption">{contact?.grade ? `Grade ${contact.grade} · ~${avgLate}d late` : `~${avgLate}d late`}</span>
        <div className="proposal-actions">
          <button className="btn btn-outline btn-sm" type="button" onClick={() => onDismiss(proposal.id)}>Not now</button>
          <button className="btn btn-primary btn-sm" type="button" onClick={() => onApprove(proposal.id, displayImpact)}>
            <Check size={14} /> {isMsg ? "Approve & send" : "Accept"}
          </button>
        </div>
      </div>
    </article>
  );
}

const BAND_DEFS = [
  { id: "now", types: ["escalation"], title: "Needs you now", dotColor: "#C93A2B" },
  { id: "worth", types: ["reminder"], title: "Worth sending", dotColor: "#C79200" },
  { id: "bigger", types: ["deposit_recommendation", "terms_recommendation"], title: "Bigger calls", dotColor: "#C96A15" }
];

function Approvals({ data, highlightId, onApprove, onDismiss, onUndo, onEdit, onApproveBatch, busy }) {
  const [drafts, setDrafts] = useState({});
  const [editingRecId, setEditingRecId] = useState(null);
  const [recDrafts, setRecDrafts] = useState({});
  const [recOverrides, setRecOverrides] = useState({});

  const contactsById = useMemo(() => new Map(data.contacts.map((contact) => [contact.id, contact])), [data.contacts]);
  const allProposals = data.proposals;
  const ordered = highlightId
    ? [...allProposals].sort((a, b) => (a.id === highlightId ? -1 : b.id === highlightId ? 1 : 0))
    : allProposals;

  const totalProps = allProposals.length;
  const decidedCount = allProposals.filter((proposal) => proposal.status !== "pending").length;
  const approvedTotal = allProposals.filter((proposal) => proposal.status === "approved").length;
  const pendingTotal = totalProps - decidedCount;
  const forwardTotal = allProposals.filter((p) => p.status === "approved").reduce((sum, p) => sum + p.expected_impact_dollars, 0);

  function handleApprove(id, displayImpact) {
    onApprove(id, displayImpact);
  }

  function handleRecCommit(id, rawFallback) {
    setEditingRecId((current) => (current === id ? null : current));
    setRecOverrides((current) => ({ ...current, [id]: Math.max(0, Number(recDrafts[id] ?? rawFallback)) }));
  }

  return (
    <main className="page page-approvals">
      <div className="card approvals-summary">
        <ApprovalsRing decided={decidedCount} total={totalProps} />
        <div className="approvals-headline">
          <h1>{pendingTotal > 0 ? `${pendingTotal} ${plural(pendingTotal, "draft")} ready to review` : "All caught up"}</h1>
          <p>Nothing is sent until you approve it.</p>
        </div>
        <div className="approvals-forward">
          <div className="approvals-forward-label">Pulled forward</div>
          <div className="approvals-forward-value">
            <ArrowRight size={13} style={{ transform: "rotate(-90deg)" }} />
            {formatCurrency(forwardTotal)}
          </div>
        </div>
      </div>

      {pendingTotal === 0 && (
        <div className="all-clear">
          <div className="all-clear-icon"><Check size={26} color="#1F8A4C" /></div>
          <h2>Queue cleared</h2>
          <p>
            {approvedTotal === 0
              ? "You reviewed every draft. Nothing was sent."
              : `You approved ${approvedTotal} of ${totalProps} — ${formatCurrency(forwardTotal)} now on its way to arriving sooner.`}
          </p>
        </div>
      )}

      {BAND_DEFS.map((band) => {
        const cards = ordered.filter((proposal) => band.types.includes(proposal.type));
        if (cards.length === 0) return null;
        const pendingCount = cards.filter((proposal) => proposal.status === "pending").length;
        const showBatch = band.id === "worth" && pendingCount > 1;
        return (
          <section className="approval-band" key={band.id}>
            <div className="band-head">
              <span className="band-dot" style={{ background: band.dotColor }} />
              <h2 style={{ color: band.dotColor }}>{band.title}</h2>
              <span className="band-count">{pendingCount > 0 ? `${pendingCount} pending` : "all done"}</span>
              {showBatch && (
                <button
                  className="band-batch-btn"
                  type="button"
                  disabled={busy}
                  onClick={() => onApproveBatch(cards.filter((c) => c.status === "pending").map((c) => c.id))}
                >
                  <Check size={13} /> Approve all {pendingCount}
                </button>
              )}
            </div>
            <div className="band-cards">
              {cards.map((proposal) => (
                <ProposalCard
                  key={proposal.id}
                  proposal={proposal}
                  contact={contactsById.get(proposal.contact_id)}
                  isHighlighted={highlightId === proposal.id}
                  drafts={drafts}
                  onDraftChange={(id, value) => setDrafts((current) => ({ ...current, [id]: value }))}
                  recOverride={recOverrides[proposal.id]}
                  isEditingRec={editingRecId === proposal.id}
                  recDraft={recDrafts[proposal.id]}
                  onRecEditStart={(id, value) => {
                    setEditingRecId(id);
                    setRecDrafts((current) => ({ ...current, [id]: value }));
                  }}
                  onRecChange={(id, value) => setRecDrafts((current) => ({ ...current, [id]: value }))}
                  onRecCommit={handleRecCommit}
                  onApprove={handleApprove}
                  onDismiss={onDismiss}
                  onUndo={onUndo}
                />
              ))}
            </div>
          </section>
        );
      })}
    </main>
  );
}

function Sent({ outbox }) {
  return (
    <main className="page page-narrow">
      <div className="page-head">
        <h1>Sent</h1>
        <p className="page-sub">Messages you approved, queued for delivery.</p>
      </div>
      <div className="sent-list">
        {outbox.map((entry) => (
          <details className="sent-row" key={entry.id}>
            <summary>
              <span className="sent-date">{formatDateTime(entry.timestamp)}</span>
              <strong>{entry.to}</strong>
              <span className="sent-subject">{entry.subject}</span>
            </summary>
            <pre>{entry.body}</pre>
          </details>
        ))}
        {outbox.length === 0 && (
          <div className="empty">Nothing sent yet. Approve a reminder in Approvals and it will land here.</div>
        )}
      </div>
    </main>
  );
}

function Activity({ entries }) {
  const actorColors = { You: "type-amber", Agent: "pill-success", System: "pill-neutral" };
  return (
    <main className="page page-narrow">
      <div className="page-head">
        <h1>Activity</h1>
        <p className="page-sub">A plain record of approved actions and changes.</p>
      </div>
      <div className="activity-card">
        {entries.map((entry) => {
          const match = entry.event.match(/^(Approved|Dismissed|Accepted|Drafted|Undid|Cash floor changed|Payment received)\s+(.*)/);
          return (
            <div className="activity-row" key={entry.id}>
              <span className="activity-time">{formatDateTime(entry.timestamp)}</span>
              <span className={`actor-pill ${actorColors[entry.actor] || "pill-neutral"}`}>{entry.actor}</span>
              <p>{match ? (<><strong>{match[1]}</strong> {match[2]}</>) : entry.event}</p>
            </div>
          );
        })}
        {entries.length === 0 && <p className="muted" style={{ padding: "32px 0", textAlign: "center" }}>No actions yet.</p>}
      </div>
    </main>
  );
}

function ModalShell({ title, onClose, children }) {
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section className="modal-panel" role="dialog" aria-modal="true" aria-label={title} onMouseDown={(event) => event.stopPropagation()}>
        <div className="modal-head">
          <h2>{title}</h2>
          <button className="icon-btn-round" type="button" onClick={onClose} title="Close">
            <X size={15} />
          </button>
        </div>
        {children}
      </section>
    </div>
  );
}

function GuideModal({ onClose }) {
  return (
    <ModalShell title="How GetPaid works" onClose={onClose}>
      <ol className="guide-list">
        <li><strong>Home</strong> shows what's due and when it will realistically arrive, based on each customer's payment history from Xero.</li>
        <li><strong>Customers</strong> grades everyone by how they actually pay you.</li>
        <li><strong>Approvals</strong> holds drafted reminders and term changes. Nothing sends without your OK.</li>
        <li>Approve an action and watch the green line on the forecast — that's your cash arriving sooner.</li>
      </ol>
      <p className="modal-footnote">
        Questions? <a className="support-link" href={`mailto:${SUPPORT_EMAIL}`}>{SUPPORT_EMAIL}</a>
      </p>
    </ModalShell>
  );
}

function DevToolsPanel({ data, syncResult, busy, onClose, onSyncXero, onSeedPortfolio, onSelectTenant, onMarkFirstPaid, onScanResearch, onRunAgent }) {
  const researchSources = Object.entries(data?.research?.sources || {});
  const firstInvoice = data?.invoices?.[0];
  return (
    <ModalShell title="Developer tools" onClose={onClose}>
      <p className="modal-lede">Demo-only controls for reset, seeded data, and integration checks.</p>
      <div className="dev-action-row">
        <button className="btn btn-outline btn-sm" type="button" onClick={onRunAgent} disabled={busy}>
          <RefreshCw size={16} /> Run agent
        </button>
        <button className="btn btn-outline btn-sm" type="button" onClick={onSeedPortfolio} disabled={busy}>
          <Database size={16} /> Seed portfolio
        </button>
        <button className="btn btn-outline btn-sm" type="button" onClick={onMarkFirstPaid} disabled={busy || !firstInvoice}>
          <Check size={16} /> Mark first invoice paid
        </button>
        <button className="btn btn-outline btn-sm" type="button" onClick={onScanResearch} disabled={busy}>
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
  const [chartRange, setChartRange] = useState("8w");
  const [highlightId, setHighlightId] = useState(null);
  const [toast, setToast] = useState(null);
  const highlightTimer = useRef(null);
  const toastTimer = useRef(null);

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

  function showToast(text) {
    window.clearTimeout(toastTimer.current);
    setToast(text);
    toastTimer.current = window.setTimeout(() => setToast(null), 3200);
  }

  function goToApprovalsWithHighlight(id) {
    window.clearTimeout(highlightTimer.current);
    setActiveTab("queue");
    setHighlightId(id);
    highlightTimer.current = window.setTimeout(() => setHighlightId(null), 4500);
  }

  async function act(fn) {
    setBusy(true);
    setError("");
    try {
      const result = await fn();
      await refresh();
      return result;
    } catch (err) {
      setError(err.message);
      return undefined;
    } finally {
      setBusy(false);
    }
  }

  const pendingCount = data?.proposals?.filter((proposal) => proposal.status === "pending").length || 0;

  async function handleApprove(id, displayImpact) {
    const proposal = data?.proposals?.find((item) => item.id === id);
    await act(() => approveProposal(id));
    if (proposal) {
      const isMsg = proposal.type === "reminder" || proposal.type === "escalation";
      showToast(isMsg ? `Sent to ${proposal.contact_name}. Expected ${formatCurrency(displayImpact ?? proposal.expected_impact_dollars)} sooner.` : "Recommendation accepted");
    }
  }

  async function handleApproveBatch(ids) {
    await act(() => approveProposalsBatch(ids));
    showToast(`${ids.length} ${plural(ids.length, "reminder")} approved and queued`);
  }

  async function handleCreateManualProposal(contactId, kind) {
    const contact = data?.contacts?.find((item) => item.id === contactId);
    const proposal = await act(() => createManualProposal(contactId, kind));
    if (proposal) {
      showToast(`Draft created for ${contact?.name || "customer"}`);
      goToApprovalsWithHighlight(proposal.id);
    }
  }

  const activeContent = useMemo(() => {
    if (!data) return <main className="page"><div className="empty">Loading GetPaid</div></main>;
    if (activeTab === "dashboard") {
      return (
        <Home
          data={data}
          cashDisplay={cashDisplay}
          chartRange={chartRange}
          onSetChartRange={setChartRange}
          onUpdateCashFloor={(cashFloor, mode) => act(() => updateCashFloor(cashFloor, mode)).then(() => showToast("Cash floor updated"))}
          onViewApprovals={() => setActiveTab("queue")}
          onViewActivity={() => setActiveTab("activity")}
          busy={busy}
        />
      );
    }
    if (activeTab === "payers") {
      return (
        <Customers
          data={data}
          onCreateManualProposal={handleCreateManualProposal}
          onReviewProposal={(id) => goToApprovalsWithHighlight(id)}
        />
      );
    }
    if (activeTab === "queue") {
      return (
        <Approvals
          data={data}
          highlightId={highlightId}
          busy={busy}
          onApprove={handleApprove}
          onDismiss={(id) => act(() => dismissProposal(id))}
          onUndo={(id) => act(() => undoProposal(id))}
          onEdit={(id, body) => act(() => editProposal(id, body))}
          onApproveBatch={handleApproveBatch}
        />
      );
    }
    if (activeTab === "outbox") return <Sent outbox={data.outbox} />;
    return <Activity entries={data.actionLog} />;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, data, cashDisplay, busy, chartRange, highlightId]);

  const businessName = data ? businessNameFor(data.dataSource) : "";
  const connectionOnline = data?.xeroStatus?.connected || data?.xeroStatus?.demo_mode;

  return (
    <div className="app-shell">
      <header className="topnav">
        <div className="topnav-inner">
          <div className="brand">Get<em>Paid</em></div>
          <nav className="nav-links">
            {TABS.map((tab) => (
              <button
                key={tab.id}
                type="button"
                className={activeTab === tab.id ? "nav-btn active" : "nav-btn"}
                onClick={() => setActiveTab(tab.id)}
              >
                {tab.label}
                {tab.id === "queue" && pendingCount > 0 && <span className="nav-badge">{pendingCount}</span>}
              </button>
            ))}
          </nav>
          <div className="topnav-right">
            <button className="icon-btn-round" type="button" title="How GetPaid works" onClick={() => setModal("guide")}>
              <HelpCircle size={15} />
            </button>
            {data && (
              <span className="connection-pill">
                <span className={connectionOnline ? "connection-dot" : "connection-dot offline"} />
                {businessName} · Xero
              </span>
            )}
          </div>
        </div>
      </header>

      {error && <div className="error-box" style={{ margin: "16px auto 0" }}>{error}</div>}

      {activeContent}

      {toast && (
        <div className="toast">
          <Check size={15} color="#4CC97E" />
          {toast}
        </div>
      )}

      {modal === "guide" && <GuideModal onClose={() => setModal(null)} />}
      {modal === "dev" && (
        <DevToolsPanel
          data={data}
          busy={busy}
          syncResult={syncResult}
          onClose={() => setModal(null)}
          onRunAgent={() => act(runAgent)}
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

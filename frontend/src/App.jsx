import {
  Bot,
  Check,
  ClipboardList,
  Database,
  ExternalLink,
  LayoutDashboard,
  Minus,
  Play,
  RefreshCw,
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
  syncXero,
  updateCashFloor
} from "./api.js";

const TABS = [
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
  { id: "payers", label: "Payers", icon: Users },
  { id: "queue", label: "Agent Queue", icon: Bot },
  { id: "outbox", label: "Outbox", icon: Send },
  { id: "log", label: "Action Log", icon: ClipboardList }
];

const TODAY = new Date("2026-07-04T00:00:00Z");

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

function xeroBadge(status) {
  if (status?.connected) return { className: "badge badge-success success", label: "Connected" };
  if (status?.demo_mode) return { className: "badge badge-neutral neutral", label: "Demo mode" };
  return { className: "badge badge-error danger", label: "Not connected" };
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
    return `Seeded ${result.contacts ?? 0} companies, ${result.invoices ?? 0} invoices and ${result.proposals ?? 0} proposed actions.`;
  }
  return result.detail || result.status || "Sync checked.";
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
            <CartesianGrid stroke="#eaeef2" vertical={false} />
            <XAxis dataKey="week" tick={{ fill: "#59636e", fontSize: 12 }} tickLine={false} axisLine={false} />
            <YAxis
              tickFormatter={compactMoney}
              tick={{ fill: "#59636e", fontSize: 12 }}
              tickLine={false}
              axisLine={false}
              width={54}
            />
            <Tooltip
              formatter={(value) => formatCurrency(value)}
              labelFormatter={(label) => `Week of ${label}`}
              contentStyle={{
                border: "1px solid #d0d7de",
                borderRadius: 6,
                boxShadow: "0 8px 24px rgba(140, 149, 159, 0.2)"
              }}
            />
            <Legend wrapperStyle={{ color: "#59636e", fontSize: 13 }} />
            <ReferenceLine
              y={forecast.cash_floor}
              stroke="#cf222e"
              strokeDasharray="4 5"
              label={{ value: `Cash floor ${compactMoney(forecast.cash_floor)}`, fill: "#cf222e", fontSize: 12 }}
            />
            <Area
              name="Due envelope"
              type="monotone"
              dataKey="due"
              fill="#ddf4ff"
              fillOpacity={0.45}
              stroke="#59636e"
              strokeOpacity={0}
              activeDot={false}
              legendType="none"
            />
            <Line
              name="By due dates"
              type="monotone"
              dataKey="due"
              stroke="#6e7781"
              strokeWidth={2.5}
              strokeDasharray="7 6"
              dot={false}
            />
            <Line
              name="Predicted (Nero)"
              type="monotone"
              dataKey="predicted"
              stroke="#0969da"
              strokeWidth={2.8}
              dot={{ r: 3, fill: "#0969da", strokeWidth: 0 }}
              activeDot={{ r: 5 }}
            />
            <Line
              name="After Nero actions"
              type="monotone"
              dataKey="accelerated"
              stroke="#1a7f37"
              strokeWidth={2.8}
              dot={{ r: 3, fill: "#1a7f37", strokeWidth: 0 }}
              activeDot={{ r: 5 }}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function XeroConnection({ status, source, syncResult, onSyncXero, onSeedPortfolio, busy }) {
  const badge = xeroBadge(status);
  const canSync = status?.demo_mode || status?.connected;
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
        <div><dt>Tenant</dt><dd>{status?.tenant_id || "Not selected"}</dd></div>
        <div><dt>Expires</dt><dd>{formatDate(status?.expires_at)}</dd></div>
        <div><dt>Dashboard data</dt><dd>{source?.label || "Unknown"}</dd></div>
      </dl>
      <div className="mini-actions">
        <button className="button primary btn btn-primary btn-sm" onClick={onSyncXero} disabled={busy || !canSync}>
          <RefreshCw size={16} /> {status?.demo_mode ? "Check demo sync" : "Sync Xero"}
        </button>
        <button className="button ghost btn btn-ghost btn-sm" onClick={onSeedPortfolio} disabled={busy}>
          <Database size={16} /> Seed portfolio
        </button>
        {!status?.demo_mode && !status?.connected && status?.client_credentials_configured && (
          <a className="button ghost btn btn-ghost btn-sm" href="/auth/login">
            <ExternalLink size={16} /> Connect
          </a>
        )}
      </div>
      {syncResult && <p className="sync-result">{syncSummary(syncResult)}</p>}
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
  const synthetic = source?.mode === "synthetic";
  const liveConnected = xeroStatus?.connected && !xeroStatus?.demo_mode;
  return (
    <section className={synthetic ? "source-banner synthetic-source" : "source-banner"}>
      <div>
        <strong>{source?.label || "Dashboard data"}</strong>
        <p>{source?.detail || "No source metadata available."}</p>
      </div>
      <span className={liveConnected ? "badge badge-success success" : "badge badge-outline neutral"}>
        {liveConnected ? "Xero live" : "Local"}
      </span>
    </section>
  );
}

function Dashboard({
  data,
  cashDisplay,
  onRunAgent,
  onMarkPaid,
  onScanResearch,
  onSyncXero,
  onSeedPortfolio,
  onUpdateCashFloor,
  syncResult,
  busy
}) {
  const cutoff = addDays(TODAY, 30);
  const dueNext30 = data.invoices
    .filter((invoice) => parseDate(invoice.due_date) <= cutoff)
    .reduce((sum, invoice) => sum + invoice.amount_due, 0);
  const predictedNext30 = data.invoices
    .filter((invoice) => parseDate(invoice.predicted_paid_date) <= cutoff)
    .reduce((sum, invoice) => sum + invoice.amount_due, 0);
  const warningBuckets = data.forecast.buckets.filter((bucket) => bucket.cumulative_predicted < data.forecast.cash_floor);
  const firstWarning = warningBuckets.find((bucket) => bucket.week_start !== "later");
  const researchSources = Object.entries(data.research?.sources || {});

  return (
    <main className="content">
      <div className="topbar">
        <div>
          <p className="eyebrow">Harbour & Co</p>
          <h1>Nero</h1>
        </div>
        <button className="button primary btn btn-primary btn-sm" onClick={onRunAgent} disabled={busy}>
          <Play size={16} /> Run agent
        </button>
      </div>

      <DataSourceBanner source={data.dataSource} xeroStatus={data.xeroStatus} />

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
                    <th>Invoice</th>
                    <th>Customer</th>
                    <th>Due</th>
                    <th>Predicted</th>
                    <th>Amount</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {data.invoices.map((invoice) => (
                    <tr key={invoice.id}>
                      <td>{invoice.invoice_number}</td>
                      <td>{invoice.contact_name}</td>
                      <td>{invoice.due_date}</td>
                      <td>{invoice.accelerated_paid_date || invoice.predicted_paid_date}</td>
                      <td>{formatCurrency(invoice.amount_due)}</td>
                      <td className="right">
                        <button className="button ghost btn btn-ghost btn-sm" onClick={() => onMarkPaid(invoice.id)}>Mark paid</button>
                      </td>
                    </tr>
                  ))}
                  {data.invoices.length === 0 && (
                    <tr>
                      <td colSpan="6">
                        <div className="empty inline-empty">No open invoices. Sync Xero or seed the synthetic portfolio.</div>
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
          <XeroConnection
            status={data.xeroStatus}
            source={data.dataSource}
            syncResult={syncResult}
            onSyncXero={onSyncXero}
            onSeedPortfolio={onSeedPortfolio}
            busy={busy}
          />
          <ResearchSignals sources={researchSources} onScanResearch={onScanResearch} busy={busy} />
          <AppStoreReadiness readiness={data.appStoreReadiness} />
        </aside>
      </section>
    </main>
  );
}

function Payers({ contacts, invoices = [] }) {
  // Rank by cash at risk: the money in open invoices, weighted by how late this
  // payer runs. Reliable payers (avg late <= 0) drop to the bottom.
  const ranked = useMemo(() => {
    return contacts
      .map((contact) => {
        const exposure = exposureFor(contact.id, invoices);
        const risk = exposure * Math.max(contact.avg_days_late, 0);
        return { ...contact, exposure, risk };
      })
      .sort((a, b) => b.risk - a.risk || b.exposure - a.exposure);
  }, [contacts, invoices]);

  const [selectedId, setSelectedId] = useState(ranked[0]?.id);
  const selected = ranked.find((contact) => contact.id === selectedId) || ranked[0];

  useEffect(() => {
    if (!ranked.find((contact) => contact.id === selectedId) && ranked.length) {
      setSelectedId(ranked[0].id);
    }
  }, [ranked, selectedId]);

  return (
    <main className="content payers-layout">
      <section className="panel">
        <div className="panel-head">
          <div>
            <h2>Payment performance</h2>
            <p className="panel-sub">Ranked by cash at risk: who to chase first</p>
          </div>
        </div>
        <div className="table-wrap">
          <table className="table table-sm">
            <thead>
              <tr>
                <th>Name</th>
                <th>Grade</th>
                <th className="right">Open exposure</th>
                <th className="right">Avg late</th>
                <th>Trend</th>
                <th className="right">Invoices</th>
              </tr>
            </thead>
            <tbody>
              {ranked.map((contact) => (
                <tr
                  key={contact.id}
                  className={selected?.id === contact.id ? "selected-row" : ""}
                  onClick={() => setSelectedId(contact.id)}
                >
                  <td>{contact.name}</td>
                  <td><span className={gradeClass(contact.grade)}>{contact.grade}</span></td>
                  <td className="right exposure-cell">{formatCurrency(contact.exposure)}</td>
                  <td className="right">{contact.avg_days_late}d</td>
                  <td><TrendCell slope={contact.trend_slope} /></td>
                  <td className="right">{contact.invoice_count}</td>
                </tr>
              ))}
              {ranked.length === 0 && (
                <tr>
                  <td colSpan="6">
                    <div className="empty inline-empty">No payer profiles yet. Seed a portfolio or sync Xero history.</div>
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
            <p>{selected.explanation}</p>
            <dl className="stats-list">
              <div><dt>Open exposure</dt><dd>{formatCurrency(selected.exposure)}</dd></div>
              <div><dt>Revenue (12m)</dt><dd>{formatCurrency(selected.revenue_12m)}</dd></div>
              <div><dt>Average days late</dt><dd>{selected.avg_days_late}d</dd></div>
              <div><dt>Variance</dt><dd>{selected.stdev_days_late}d</dd></div>
              <div><dt>Trend</dt><dd><TrendCell slope={selected.trend_slope} /></dd></div>
            </dl>
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
  return (
    <main className="content">
      <div className="panel-head page-head">
        <div>
          <h1>Outbox</h1>
          <span className="badge badge-outline muted-badge">Sandbox mode: no real emails sent</span>
        </div>
      </div>
      <div className="list-stack">
        {outbox.map((entry) => (
          <details className="list-row" key={entry.id}>
            <summary>
              <span>{formatDateTime(entry.timestamp)}</span>
              <strong>{entry.to}</strong>
              <em>{entry.subject}</em>
            </summary>
            <pre>{entry.body}</pre>
          </details>
        ))}
        {outbox.length === 0 && <div className="empty">No sandbox emails sent</div>}
      </div>
    </main>
  );
}

function ActionLog({ entries }) {
  return (
    <main className="content">
      <div className="panel-head page-head">
        <h1>Action Log</h1>
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

export function App() {
  const [activeTab, setActiveTab] = useState("dashboard");
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [syncResult, setSyncResult] = useState(null);

  async function refresh() {
    const next = await fetchAll();
    setData(next);
  }

  useEffect(() => {
    refresh().catch((err) => setError(err.message));
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
          onMarkPaid={(id) => act(() => markPaid(id))}
          onScanResearch={() => act(scanResearch)}
          onSyncXero={() => act(async () => setSyncResult(await syncXero()))}
          onSeedPortfolio={() => act(async () => setSyncResult(await seedSyntheticPortfolio()))}
          onUpdateCashFloor={(cashFloor) => act(() => updateCashFloor(cashFloor))}
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
    return <ActionLog entries={data.actionLog} />;
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
        {error && <div className="error-box">{error}</div>}
      </aside>
      {activeContent}
    </div>
  );
}

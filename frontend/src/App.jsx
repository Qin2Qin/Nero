import {
  Bot,
  Check,
  ClipboardList,
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
  approveProposal,
  dismissProposal,
  editProposal,
  fetchAll,
  markPaid,
  money,
  runAgent,
  scanResearch,
  syncXero
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
  return `$${money(Math.round(Number(value || 0)))}`;
}

function formatHeroCurrency(value) {
  return `$${money(Math.round(Number(value || 0) / 1000) * 1000)}`;
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
  if (Math.abs(v) >= 1000) return `$${Math.round(v / 1000)}k`;
  return `$${Math.round(v)}`;
}

function xeroBadge(status) {
  if (status?.connected) return { className: "badge success", label: "Connected" };
  if (status?.demo_mode) return { className: "badge neutral", label: "Demo mode" };
  return { className: "badge danger", label: "Not connected" };
}

function syncSummary(result) {
  if (!result) return "";
  if (result.status === "synced") {
    return `Synced ${result.fetched?.contacts ?? 0} contacts, ${result.fetched?.invoices ?? 0} invoices, ${result.fetched?.payments ?? 0} payments.`;
  }
  if (result.status === "demo") {
    return `Demo sync checked ${result.contacts ?? 0} contacts and ${result.invoices ?? 0} invoices.`;
  }
  return result.detail || result.status || "Sync checked.";
}

function ForecastChart({ forecast }) {
  const buckets = forecast?.buckets?.filter((bucket) => bucket.week_start !== "later") || [];
  if (!buckets.length) return <div className="empty">No forecast data</div>;

  const width = 820;
  const height = 340;
  const pad = { top: 24, right: 28, bottom: 44, left: 70 };
  const rawMax = Math.max(
    forecast.cash_floor,
    ...buckets.flatMap((bucket) => [
      bucket.cumulative_due,
      bucket.cumulative_predicted,
      bucket.cumulative_accelerated ?? bucket.cumulative_predicted
    ])
  );
  // Round the axis up to a clean value so the dollar ticks read nicely.
  const tickStep = rawMax > 12000 ? 5000 : rawMax > 4000 ? 2000 : 1000;
  const maxValue = Math.ceil(rawMax / tickStep) * tickStep;
  const ticks = [];
  for (let t = 0; t <= maxValue; t += tickStep) ticks.push(t);
  const x = (idx) => pad.left + (idx * (width - pad.left - pad.right)) / Math.max(buckets.length - 1, 1);
  const y = (value) => height - pad.bottom - (value / maxValue) * (height - pad.top - pad.bottom);
  const path = (key) =>
    buckets
      .map((bucket, idx) => {
        const value = key === "cumulative_accelerated" ? bucket[key] ?? bucket.cumulative_predicted : bucket[key];
        return `${idx === 0 ? "M" : "L"} ${x(idx)} ${y(value)}`;
      })
      .join(" ");
  const gapPoints = [
    ...buckets.map((bucket, idx) => `${x(idx)},${y(bucket.cumulative_due)}`),
    ...buckets
      .slice()
      .reverse()
      .map((bucket, idx) => `${x(buckets.length - 1 - idx)},${y(bucket.cumulative_predicted)}`)
  ].join(" ");
  const floorY = y(forecast.cash_floor);

  return (
    <div className="chart-wrap">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Cash forecast">
        {ticks.map((tick) => (
          <g key={tick}>
            <line className="grid-line" x1={pad.left} y1={y(tick)} x2={width - pad.right} y2={y(tick)} />
            <text className="y-label" x={pad.left - 10} y={y(tick) + 4} textAnchor="end">{compactMoney(tick)}</text>
          </g>
        ))}
        <line className="axis" x1={pad.left} y1={height - pad.bottom} x2={width - pad.right} y2={height - pad.bottom} />
        <line className="axis" x1={pad.left} y1={pad.top} x2={pad.left} y2={height - pad.bottom} />
        <polygon className="gap-fill" points={gapPoints} />
        <line className="cash-floor" x1={pad.left} y1={floorY} x2={width - pad.right} y2={floorY} />
        <text
          className="floor-label"
          x={pad.left + (width - pad.left - pad.right) * 0.6}
          y={floorY - 9}
          textAnchor="middle"
        >
          Cash floor {compactMoney(forecast.cash_floor)}
        </text>
        <path className="due-line" d={path("cumulative_due")} />
        <path className="predicted-line" d={path("cumulative_predicted")} />
        <path className="accelerated-line" d={path("cumulative_accelerated")} />
        {buckets.map((bucket, idx) => (
          <g key={bucket.week_start}>
            <circle className="predicted-dot" cx={x(idx)} cy={y(bucket.cumulative_predicted)} r="4" />
            {(bucket.cumulative_predicted ?? 0) < forecast.cash_floor && (
              <circle className="warning-dot" cx={x(idx)} cy={y(bucket.cumulative_predicted) - 13} r="5" />
            )}
            <text className="x-label" x={x(idx)} y={height - 18}>
              {bucket.week_start.slice(5)}
            </text>
          </g>
        ))}
      </svg>
      <div className="legend">
        <span><i className="legend-due" /> By due dates</span>
        <span><i className="legend-predicted" /> Predicted (Nero)</span>
        <span><i className="legend-accelerated" /> After Nero actions</span>
      </div>
    </div>
  );
}

function XeroConnection({ status, syncResult, onSyncXero, busy }) {
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
      </dl>
      <div className="mini-actions">
        <button className="button primary" onClick={onSyncXero} disabled={busy || !canSync}>
          <RefreshCw size={16} /> {status?.demo_mode ? "Check demo sync" : "Sync Xero"}
        </button>
        {!status?.demo_mode && !status?.connected && status?.client_credentials_configured && (
          <a className="button ghost" href="/auth/login">
            <ExternalLink size={16} /> Connect
          </a>
        )}
      </div>
      {syncResult && <p className="sync-result">{syncSummary(syncResult)}</p>}
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
        <button className="icon-button" onClick={onScanResearch} disabled={busy} title="Scan research">
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

function Dashboard({ data, cashDisplay, onRunAgent, onMarkPaid, onScanResearch, onSyncXero, syncResult, busy }) {
  const cutoff = addDays(TODAY, 30);
  const dueNext30 = data.invoices
    .filter((invoice) => parseDate(invoice.due_date) <= cutoff)
    .reduce((sum, invoice) => sum + invoice.amount_due, 0);
  const predictedNext30 = data.invoices
    .filter((invoice) => parseDate(invoice.predicted_paid_date) <= cutoff)
    .reduce((sum, invoice) => sum + invoice.amount_due, 0);
  const warningBuckets = data.forecast.buckets.filter((bucket) => bucket.cumulative_predicted < data.forecast.cash_floor);
  const researchSources = Object.entries(data.research?.sources || {});

  return (
    <main className="content">
      <div className="topbar">
        <div>
          <p className="eyebrow">Harbour & Co</p>
          <h1>Nero</h1>
        </div>
        <button className="button primary" onClick={onRunAgent} disabled={busy}>
          <Play size={16} /> Run agent
        </button>
      </div>

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
        <div className="panel chart-panel">
          <div className="panel-head">
            <div>
              <h2>Cash forecast</h2>
              {warningBuckets.length > 0 && <span className="badge danger">Week 3 below floor</span>}
            </div>
          </div>
          <ForecastChart forecast={data.forecast} />
        </div>

        <aside className="panel signal-panel">
          <XeroConnection
            status={data.xeroStatus}
            syncResult={syncResult}
            onSyncXero={onSyncXero}
            busy={busy}
          />
          <ResearchSignals sources={researchSources} onScanResearch={onScanResearch} busy={busy} />
        </aside>
      </section>

      <section className="panel">
        <div className="panel-head">
          <h2>Open invoices</h2>
        </div>
        <div className="table-wrap">
          <table>
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
                    <button className="button ghost" onClick={() => onMarkPaid(invoice.id)}>Mark paid</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
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
          <table>
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
                <span className="badge">{proposal.type.replaceAll("_", " ")}</span>
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
                <button className="button primary" disabled={busy} onClick={() => onApprove(proposal.id)}>
                  <Check size={16} /> Approve
                </button>
                {proposal.draft_subject && (
                  <button className="button ghost" disabled={busy} onClick={() => onEdit(proposal.id, draftBody)}>
                    Edit
                  </button>
                )}
                <button className="icon-button danger-icon" disabled={busy} onClick={() => onDismiss(proposal.id)} title="Dismiss">
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
          <span className="badge muted-badge">Sandbox mode: no real emails sent</span>
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
    <div className="app-shell">
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

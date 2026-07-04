import {
  Bot,
  Check,
  ClipboardList,
  LayoutDashboard,
  Play,
  RefreshCw,
  Send,
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
  scanResearch
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

function gradeClass(grade) {
  return `grade grade-${String(grade).charAt(0).toLowerCase()}`;
}

function trendLabel(slope) {
  if (slope > 1) return "up";
  if (slope < -1) return "down";
  return "flat";
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

function ForecastChart({ forecast }) {
  const buckets = forecast?.buckets?.filter((bucket) => bucket.week_start !== "later") || [];
  if (!buckets.length) return <div className="empty">No forecast data</div>;

  const width = 820;
  const height = 300;
  const pad = { top: 24, right: 28, bottom: 44, left: 62 };
  const maxValue = Math.max(
    forecast.cash_floor,
    ...buckets.flatMap((bucket) => [
      bucket.cumulative_due,
      bucket.cumulative_predicted,
      bucket.cumulative_accelerated ?? bucket.cumulative_predicted
    ])
  );
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
        <line className="axis" x1={pad.left} y1={height - pad.bottom} x2={width - pad.right} y2={height - pad.bottom} />
        <line className="axis" x1={pad.left} y1={pad.top} x2={pad.left} y2={height - pad.bottom} />
        <polygon className="gap-fill" points={gapPoints} />
        <line className="cash-floor" x1={pad.left} y1={floorY} x2={width - pad.right} y2={floorY} />
        <text className="floor-label" x={width - pad.right - 78} y={floorY - 7}>
          Cash floor
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

function Dashboard({ data, cashDisplay, onRunAgent, onMarkPaid, onScanResearch, busy }) {
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

        <aside className="panel research-panel">
          <div className="panel-head compact">
            <h2>Research signals</h2>
            <button className="icon-button" onClick={onScanResearch} title="Scan research">
              <RefreshCw size={16} />
            </button>
          </div>
          <div className="research-list">
            {researchSources.length === 0 && <p className="muted">No raw research files indexed.</p>}
            {researchSources.map(([source, summary]) => (
              <div className="research-row" key={source}>
                <strong>{source}</strong>
                <span>{summary.files} files</span>
                <span>{summary.records} records</span>
                <em>{summary.changed_files} changed</em>
              </div>
            ))}
          </div>
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

function Payers({ contacts }) {
  const [selected, setSelected] = useState(contacts[0]);

  useEffect(() => {
    if (!selected && contacts.length) setSelected(contacts[0]);
  }, [contacts, selected]);

  return (
    <main className="content payers-layout">
      <section className="panel">
        <div className="panel-head">
          <h2>Customers</h2>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Grade</th>
                <th>Revenue 12m</th>
                <th>Avg late</th>
                <th>Trend</th>
                <th>Invoices</th>
              </tr>
            </thead>
            <tbody>
              {contacts.map((contact) => (
                <tr
                  key={contact.id}
                  className={selected?.id === contact.id ? "selected-row" : ""}
                  onClick={() => setSelected(contact)}
                >
                  <td>{contact.name}</td>
                  <td><span className={gradeClass(contact.grade)}>{contact.grade}</span></td>
                  <td>{formatCurrency(contact.revenue_12m)}</td>
                  <td>{contact.avg_days_late}</td>
                  <td>{trendLabel(contact.trend_slope)}</td>
                  <td>{contact.invoice_count}</td>
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
              <div><dt>Revenue</dt><dd>{formatCurrency(selected.revenue_12m)}</dd></div>
              <div><dt>Average days late</dt><dd>{selected.avg_days_late}</dd></div>
              <div><dt>Variance</dt><dd>{selected.stdev_days_late}</dd></div>
              <div><dt>Trend slope</dt><dd>{selected.trend_slope}</dd></div>
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
        />
      );
    }
    if (activeTab === "payers") return <Payers contacts={data.contacts} />;
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
  }, [activeTab, data, cashDisplay, busy]);

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

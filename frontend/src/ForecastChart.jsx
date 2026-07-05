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

function parseDate(value) {
  return new Date(`${value}T00:00:00Z`);
}

function formatWeekLabel(value) {
  if (!value || value === "later") return "Later";
  return new Intl.DateTimeFormat("en-GB", {
    month: "short",
    day: "numeric"
  }).format(parseDate(value));
}

function formatCurrency(value) {
  return `£${new Intl.NumberFormat("en-GB").format(Math.round(Number(value || 0)))}`;
}

function compactMoney(value) {
  const v = Number(value || 0);
  if (Math.abs(v) >= 1000) return `£${Math.round(v / 1000)}k`;
  return `£${Math.round(v)}`;
}

export default function ForecastChart({ forecast }) {
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
              label={{ value: `Minimum cash ${compactMoney(forecast.cash_floor)}`, fill: chartColors.floor, fontSize: 12 }}
            />
            <Area
              name="Invoice range"
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
              name="If paid on due date"
              type="monotone"
              dataKey="due"
              stroke={chartColors.due}
              strokeWidth={2.5}
              strokeDasharray="7 6"
              dot={false}
            />
            <Line
              className="forecast-line predicted-line"
              name="Likely payment date"
              type="monotone"
              dataKey="predicted"
              stroke={chartColors.predicted}
              strokeWidth={2.8}
              dot={{ r: 3, fill: chartColors.predicted, strokeWidth: 0 }}
              activeDot={{ r: 5 }}
            />
            <Line
              className="forecast-line accelerated-line"
              name="After approved actions"
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

import { CartesianGrid, Legend, Line, LineChart, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Plan } from "../api";
import { money, planTitle } from "../format";

// As-is (brick), recommended (ledger green), decline (grey), then plum, ochre, ink blue.
const COLORS = ["#bd503b", "#1f6647", "#9d988b", "#85607f", "#b9861d", "#3d6386"];

// Balance only changes on event days, so the path is a step function. On a
// day with outflows and inflows the intra-day low (outflows first) is drawn
// as a vertical dip before the end-of-day balance.
function points(p: Plan, lastDay: number, opening: number) {
  const pts: { day: number; v: number }[] = [{ day: 0, v: opening }];
  for (const s of p.path) {
    if (s.low !== s.end) pts.push({ day: s.day, v: s.low });
    pts.push({ day: s.day, v: s.end });
  }
  if (pts.length && pts[pts.length - 1].day < lastDay) pts.push({ day: lastDay, v: pts[pts.length - 1].v });
  return pts;
}

export function CashChart({ plans, reserve, currency, opening, height = 360 }: { plans: Plan[]; reserve: number; currency: string; opening: number; height?: number }) {
  const lastDay = Math.max(...plans.flatMap((p) => p.path.map((s) => s.day))) + 5;
  const all = [opening, ...plans.flatMap((p) => p.path.flatMap((s) => [s.low, s.end]))];
  const lo = Math.min(reserve, ...all), hi = Math.max(reserve, ...all);
  const pad = (hi - lo) * 0.08 || 1000;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart margin={{ top: 10, right: 20, bottom: 10, left: 10 }}>
        <CartesianGrid stroke="#e2dfd5" strokeDasharray="2 4" vertical={false} />
        <XAxis type="number" dataKey="day" domain={[0, lastDay]} tickCount={10} allowDuplicatedCategory={false}
          label={{ value: "Day", position: "insideBottomRight", offset: -4, fontSize: 12, fill: "#6c685e" }} tick={{ fontSize: 12, fill: "#6c685e" }} stroke="#cdc8bb" />
        <YAxis domain={[lo - pad, hi + pad]} tickFormatter={(v) => money(v, currency)} width={90} tick={{ fontSize: 12, fill: "#6c685e" }} stroke="#cdc8bb" />
        <ReferenceArea y1={lo - pad} y2={reserve} fill="#f6ded8" fillOpacity={0.55} ifOverflow="extendDomain" />
        <ReferenceLine y={reserve} stroke="#9a6c12" strokeDasharray="6 4" strokeWidth={1.5}
          label={{ value: `Your reserve ${money(reserve, currency)}`, position: "insideTopLeft", fill: "#7a540e", fontSize: 12 }} />
        <ReferenceLine y={0} stroke="#9d988b" />
        <Tooltip formatter={(v) => money(Number(v), currency)} labelFormatter={(d) => `Day ${d}`}
          contentStyle={{ borderRadius: 8, border: "1px solid #e2dfd5", fontSize: 12, boxShadow: "0 6px 16px -6px rgb(28 27 24 / 0.14)" }} />
        <Legend wrapperStyle={{ fontSize: 12, paddingTop: 8 }} />
        {plans.map((p, i) => (
          <Line key={p.id} data={points(p, lastDay, opening)} dataKey="v" type="stepAfter" name={(p.recommended ? "★ " : "") + planTitle(p, currency)}
            stroke={COLORS[i % COLORS.length]} strokeWidth={p.recommended ? 3 : 2} dot={false}
            strokeDasharray={p.id === "decline" ? "5 4" : undefined} isAnimationActive={false} />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

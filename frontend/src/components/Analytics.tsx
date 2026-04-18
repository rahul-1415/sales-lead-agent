"use client";

import {
  Bar, BarChart, Cell, Pie, PieChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import type { EnrichedLead } from "@/lib/types";

interface Props { leads: EnrichedLead[] }

const ACTION_COLORS: Record<string, string> = {
  priority: "#22c55e",
  standard: "#6366f1",
  research: "#f59e0b",
  reject:   "#ef4444",
};

export function Analytics({ leads }: Props) {
  if (leads.length === 0) return null;

  // Action distribution pie
  const actionCounts = leads.reduce<Record<string, number>>((acc, l) => {
    acc[l.recommended_action] = (acc[l.recommended_action] ?? 0) + 1;
    return acc;
  }, {});
  const pieData = Object.entries(actionCounts).map(([name, value]) => ({ name, value }));

  // Score histogram (10 buckets)
  const buckets = Array.from({ length: 10 }, (_, i) => ({
    range: `${i * 10}–${i * 10 + 10}`,
    count: 0,
  }));
  leads.forEach((l) => {
    const idx = Math.min(Math.floor(l.confidence_score * 10), 9);
    buckets[idx].count += 1;
  });

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {/* Score distribution */}
      <div className="rounded-xl border border-gray-200 bg-white p-5">
        <h3 className="mb-4 text-sm font-semibold text-gray-900">Score Distribution</h3>
        <ResponsiveContainer width="100%" height={160}>
          <BarChart data={buckets} margin={{ top: 0, right: 0, bottom: 0, left: -20 }}>
            <XAxis dataKey="range" tick={{ fontSize: 10 }} interval={1} />
            <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
            <Tooltip
              contentStyle={{ fontSize: 12 }}
              formatter={(v: number) => [v, "leads"]}
            />
            <Bar dataKey="count" fill="#6366f1" radius={[3, 3, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Action breakdown pie */}
      <div className="rounded-xl border border-gray-200 bg-white p-5">
        <h3 className="mb-4 text-sm font-semibold text-gray-900">Action Breakdown</h3>
        <div className="flex items-center gap-4">
          <ResponsiveContainer width="50%" height={160}>
            <PieChart>
              <Pie
                data={pieData}
                cx="50%" cy="50%"
                innerRadius={40} outerRadius={68}
                dataKey="value"
                paddingAngle={2}
              >
                {pieData.map((entry) => (
                  <Cell key={entry.name} fill={ACTION_COLORS[entry.name] ?? "#94a3b8"} />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{ fontSize: 12 }}
                formatter={(v: number, name: string) => [v, name]}
              />
            </PieChart>
          </ResponsiveContainer>
          <ul className="space-y-1.5 text-sm">
            {pieData.map(({ name, value }) => (
              <li key={name} className="flex items-center gap-2">
                <span
                  className="h-2.5 w-2.5 rounded-full shrink-0"
                  style={{ background: ACTION_COLORS[name] ?? "#94a3b8" }}
                />
                <span className="capitalize text-gray-600">{name}</span>
                <span className="ml-auto font-medium text-gray-900">{value}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}

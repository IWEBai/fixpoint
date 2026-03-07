import React, { useEffect, useState } from "react";
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
  RadialBarChart,
  RadialBar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import {
  Activity,
  ShieldCheck,
  ShieldAlert,
  Timer,
  GitMerge,
  CheckCircle2,
  GitPullRequestDraft,
  GitPullRequest,
} from "lucide-react";
import api from "../lib/api";

interface Summary {
  total_runs: number;
  succeeded_runs: number;
  failed_runs: number;
  avg_duration_seconds: number;
  fix_merge_rate: number;
  ci_success_rate: number;
  fix_prs_created: number;
  fix_prs_merged: number;
}

interface VulnBreakdown {
  name: string;
  count: number;
}

interface DryRunRepo {
  repo: string;
  count: number;
}

interface DryRunStats {
  would_have_auto_merged: number;
  by_repo: DryRunRepo[];
}

const VULN_COLORS = [
  "#f87171",
  "#fb923c",
  "#fbbf24",
  "#34d399",
  "#60a5fa",
  "#a78bfa",
  "#f472b6",
  "#94a3b8",
];

export default function Analytics() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [timeseries, setTimeseries] = useState([]);
  const [vulnBreakdown, setVulnBreakdown] = useState<VulnBreakdown[]>([]);
  const [dryRunStats, setDryRunStats] = useState<DryRunStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [sumRes, timeRes, vulnRes, dryRes] = await Promise.all([
          api.get("/analytics/summary"),
          api.get("/analytics/timeseries"),
          api.get("/analytics/vulnerabilities"),
          api.get("/dashboard/dry-run-stats"),
        ]);
        setSummary(sumRes.data ?? null);
        setTimeseries(
          Array.isArray(timeRes.data?.data) ? timeRes.data.data : [],
        );
        setVulnBreakdown(
          Array.isArray(vulnRes.data?.data) ? vulnRes.data.data : [],
        );
        setDryRunStats(
          dryRes.data?.would_have_auto_merged !== undefined
            ? dryRes.data
            : null,
        );
      } catch (err: any) {
        setError(err?.response?.data?.error ?? "Failed to load analytics data");
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  const stats = [
    {
      name: "Total Runs",
      value: summary?.total_runs ?? 0,
      icon: Activity,
      color: "text-blue-400",
    },
    {
      name: "Succeeded",
      value: summary?.succeeded_runs ?? 0,
      icon: ShieldCheck,
      color: "text-emerald-400",
    },
    {
      name: "Failed",
      value: summary?.failed_runs ?? 0,
      icon: ShieldAlert,
      color: "text-red-400",
    },
    {
      name: "Avg Duration (s)",
      value: summary?.avg_duration_seconds?.toFixed(1) ?? "0.0",
      icon: Timer,
      color: "text-amber-400",
    },
    {
      name: "Fix PRs Created",
      value: summary?.fix_prs_created ?? 0,
      icon: GitPullRequest,
      color: "text-violet-400",
    },
    {
      name: "Fix PRs Merged",
      value: summary?.fix_prs_merged ?? 0,
      icon: GitMerge,
      color: "text-teal-400",
    },
  ];

  const mergeRateData = [
    {
      name: "Fix Merge Rate",
      value: +(summary?.fix_merge_rate?.toFixed(1) ?? 0),
      fill: "#34d399",
    },
  ];
  const ciRateData = [
    {
      name: "CI Success Rate",
      value: +(summary?.ci_success_rate?.toFixed(1) ?? 0),
      fill: "#60a5fa",
    },
  ];

  if (loading) {
    return (
      <div className="space-y-8">
        <h2 className="text-3xl font-bold tracking-tight">
          Analytics Overview
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-6">
          {Array.from({ length: 6 }).map((_, i) => (
            <div
              key={i}
              className="bg-slate-900 border border-slate-800 rounded-xl p-6 animate-pulse"
            >
              <div className="flex items-center space-x-4">
                <div className="w-14 h-14 rounded-lg bg-slate-800" />
                <div className="space-y-2">
                  <div className="h-3 w-20 bg-slate-800 rounded" />
                  <div className="h-7 w-10 bg-slate-800 rounded" />
                </div>
              </div>
            </div>
          ))}
        </div>
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 h-80 animate-pulse" />
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div className="flex justify-between items-center">
        <h2 className="text-3xl font-bold tracking-tight">
          Analytics Overview
        </h2>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 text-red-400 text-sm">
          {error}
        </div>
      )}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-6">
        {stats.map((stat) => (
          <div
            key={stat.name}
            className="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-md hover:shadow-lg transition-shadow"
          >
            <div className="flex items-center space-x-4">
              <div className={`p-4 rounded-lg bg-slate-800 ${stat.color}`}>
                <stat.icon className="w-6 h-6" />
              </div>
              <div>
                <p className="text-slate-400 font-medium text-sm">
                  {stat.name}
                </p>
                <h3 className="text-3xl font-bold text-slate-100">
                  {stat.value}
                </h3>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Runs over 30 days – NORTH STAR */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl shadow-md p-6">
        <h3 className="text-xl font-semibold mb-6">
          Fixes merged per day{" "}
          <span className="text-xs ml-2 px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 ring-1 ring-emerald-500/20">
            NORTH STAR
          </span>
        </h3>
        <div className="h-72 w-full">
          {timeseries.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={timeseries}>
                <CartesianGrid
                  strokeDasharray="3 3"
                  stroke="#1e293b"
                  vertical={false}
                />
                <XAxis dataKey="date" stroke="#64748b" />
                <YAxis stroke="#64748b" />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#0f172a",
                    borderColor: "#1e293b",
                    borderRadius: "0.5rem",
                  }}
                  itemStyle={{ color: "#f8fafc" }}
                />
                <Legend />
                <Line
                  type="monotone"
                  dataKey="succeeded_runs"
                  name="Successful Fixes"
                  stroke="#34d399"
                  strokeWidth={2}
                  dot={false}
                />
                <Line
                  type="monotone"
                  dataKey="failed_runs"
                  name="Failed Runs"
                  stroke="#f87171"
                  strokeWidth={2}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-full flex items-center justify-center text-slate-500">
              No data available yet
            </div>
          )}
        </div>
      </div>

      {/* Runs created (bar) */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl shadow-md p-6">
        <h3 className="text-xl font-semibold mb-6">Fixes created per day</h3>
        <div className="h-64 w-full">
          {timeseries.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={timeseries}>
                <CartesianGrid
                  strokeDasharray="3 3"
                  stroke="#1e293b"
                  vertical={false}
                />
                <XAxis dataKey="date" stroke="#64748b" />
                <YAxis stroke="#64748b" />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#0f172a",
                    borderColor: "#1e293b",
                    borderRadius: "0.5rem",
                  }}
                  itemStyle={{ color: "#f8fafc" }}
                />
                <Legend />
                <Bar
                  dataKey="succeeded_runs"
                  name="Succeeded"
                  fill="#34d399"
                  radius={[4, 4, 0, 0]}
                />
                <Bar
                  dataKey="failed_runs"
                  name="Failed"
                  fill="#f87171"
                  radius={[4, 4, 0, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-full flex items-center justify-center text-slate-500">
              No data available yet
            </div>
          )}
        </div>
      </div>

      {/* Gauges: fix merge rate + CI success rate */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {[
          {
            label: "Fix Merge Rate",
            data: mergeRateData,
            icon: GitMerge,
            color: "#34d399",
          },
          {
            label: "CI Success Rate",
            data: ciRateData,
            icon: CheckCircle2,
            color: "#60a5fa",
          },
        ].map(({ label, data, icon: Icon, color }) => (
          <div
            key={label}
            className="bg-slate-900 border border-slate-800 rounded-xl shadow-md p-6 flex flex-col items-center"
          >
            <h3 className="text-lg font-semibold mb-4 text-slate-300">
              {label}
            </h3>
            <ResponsiveContainer width="100%" height={180}>
              <RadialBarChart
                cx="50%"
                cy="50%"
                innerRadius="60%"
                outerRadius="80%"
                startAngle={180}
                endAngle={0}
                data={data}
              >
                <RadialBar
                  background
                  dataKey="value"
                  cornerRadius={8}
                  fill={color}
                />
              </RadialBarChart>
            </ResponsiveContainer>
            <p className="text-4xl font-bold mt-2" style={{ color }}>
              {data[0].value}%
            </p>
          </div>
        ))}
      </div>

      {/* Vulnerability Breakdown Pie Chart */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl shadow-md p-6">
        <h3 className="text-lg font-semibold mb-4 text-slate-300">
          Vulnerability Type Breakdown
        </h3>
        {vulnBreakdown.length > 0 ? (
          <div className="flex flex-col md:flex-row items-center gap-8">
            <ResponsiveContainer width="100%" height={280}>
              <PieChart>
                <Pie
                  data={vulnBreakdown}
                  cx="50%"
                  cy="50%"
                  outerRadius={110}
                  dataKey="count"
                  nameKey="name"
                  label={({ name, percent }) =>
                    `${name} ${(percent * 100).toFixed(0)}%`
                  }
                >
                  {vulnBreakdown.map((_entry, index) => (
                    <Cell
                      key={`cell-${index}`}
                      fill={VULN_COLORS[index % VULN_COLORS.length]}
                    />
                  ))}
                </Pie>
                <Tooltip
                  formatter={(value: number) => [value, "Runs"]}
                  contentStyle={{
                    background: "#1e293b",
                    border: "none",
                    borderRadius: "8px",
                    color: "#e2e8f0",
                  }}
                />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <div className="h-40 flex items-center justify-center text-slate-500">
            No vulnerability data yet — classifications will appear after the
            first fix runs.
          </div>
        )}
      </div>

      {/* Auto-merge readiness: Tier A dry-run counts */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl shadow-md p-6">
        <div className="flex items-center justify-between mb-1">
          <h3 className="text-lg font-semibold text-slate-300">
            Auto-merge Readiness
          </h3>
          <span className="text-xs px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-400 ring-1 ring-amber-500/20">
            Tier A dry runs
          </span>
        </div>
        <p className="text-sm text-slate-500 mb-5">
          Fix PRs that passed all 5 safety gates but were not auto-merged
          because the repo is on Tier A. Upgrade to Tier B to enable actual
          merging.
        </p>

        {/* Total KPI */}
        <div className="flex items-center gap-3 mb-6">
          <div className="p-3 rounded-lg bg-slate-800 text-amber-400">
            <GitPullRequestDraft className="w-5 h-5" />
          </div>
          <div>
            <p className="text-xs text-slate-500 uppercase tracking-widest">
              Total would-have-merged
            </p>
            <p className="text-3xl font-bold text-amber-400">
              {dryRunStats?.would_have_auto_merged ?? 0}
            </p>
          </div>
        </div>

        {/* Per-repo bar chart */}
        {(dryRunStats?.by_repo?.length ?? 0) > 0 ? (
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                layout="vertical"
                data={dryRunStats!.by_repo}
                margin={{ left: 16, right: 24, top: 4, bottom: 4 }}
              >
                <CartesianGrid
                  strokeDasharray="3 3"
                  stroke="#1e293b"
                  horizontal={false}
                />
                <XAxis type="number" stroke="#64748b" allowDecimals={false} />
                <YAxis
                  type="category"
                  dataKey="repo"
                  stroke="#64748b"
                  width={160}
                  tick={{ fontSize: 12 }}
                  tickFormatter={(v: string) =>
                    v.length > 22 ? `…${v.slice(-20)}` : v
                  }
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#0f172a",
                    borderColor: "#1e293b",
                    borderRadius: "0.5rem",
                  }}
                  itemStyle={{ color: "#fbbf24" }}
                  formatter={(v: number) => [v, "would-have-merged"]}
                />
                <Bar
                  dataKey="count"
                  name="Would-have-merged"
                  fill="#f59e0b"
                  radius={[0, 4, 4, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <div className="h-24 flex items-center justify-center text-slate-500 text-sm">
            No dry-run data yet — appears when a Tier A repo’s fix PR passes all
            5 auto-merge gates.
          </div>
        )}
      </div>
    </div>
  );
}

import React, { useEffect, useState } from "react";
import api from "../lib/api";
import { formatDistanceToNow } from "date-fns";

export default function RunHistory() {
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchRuns = async () => {
      try {
        const res = await api.get("/runs");
        setRuns(res.data.runs);
      } catch (e: any) {
        setError(e?.response?.data?.error ?? "Failed to load run history");
      } finally {
        setLoading(false);
      }
    };
    fetchRuns();
  }, []);

  return (
    <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="flex justify-between items-center">
        <h2 className="text-3xl font-bold tracking-tight">Run History</h2>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 text-red-400 text-sm">
          {error}
        </div>
      )}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-md">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-slate-950/50 border-b border-slate-800 text-sm font-semibold text-slate-400">
                <th className="p-4">Repository</th>
                <th className="p-4">Status</th>
                <th className="p-4">PR</th>
                <th className="p-4">Findings</th>
                <th className="p-4">Fix PR</th>
                <th className="p-4">CI</th>
                <th className="p-4">Time</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {loading ? (
                <tr>
                  <td colSpan={7} className="p-8 text-center text-slate-500">
                    Loading...
                  </td>
                </tr>
              ) : runs.length === 0 ? (
                <tr>
                  <td colSpan={7} className="p-8 text-center text-slate-500">
                    No runs found
                  </td>
                </tr>
              ) : (
                runs.map((run: any) => (
                  <tr
                    key={run.id}
                    className="hover:bg-slate-800/50 transition-colors group"
                  >
                    <td className="p-4 font-medium text-slate-200">
                      {run.repo || `${run.repo_owner}/${run.repo_name}`}
                    </td>
                    <td className="p-4">
                      <span
                        className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold
                      ${
                        run.status === "success"
                          ? "bg-emerald-500/10 text-emerald-400 ring-1 ring-emerald-500/20"
                          : run.status === "error"
                            ? "bg-red-500/10 text-red-400 ring-1 ring-red-500/20"
                            : "bg-blue-500/10 text-blue-400 ring-1 ring-blue-500/20"
                      }
                    `}
                      >
                        {run.status
                          ? run.status.charAt(0).toUpperCase() +
                            run.status.slice(1)
                          : "Unknown"}
                      </span>
                    </td>
                    <td className="p-4 text-slate-300">
                      {run.pr_number ? `#${run.pr_number}` : "–"}
                    </td>
                    <td className="p-4">
                      {run.violations_found > 0 ? (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-red-500/10 text-red-400 ring-1 ring-red-500/20">
                          {run.violations_found} issue
                          {run.violations_found !== 1 ? "s" : ""}
                        </span>
                      ) : (
                        <span className="text-slate-500 text-xs">Clean</span>
                      )}
                    </td>
                    <td className="p-4 text-slate-300">
                      {run.fix_pr_number ? (
                        <a
                          className="text-emerald-400 hover:underline"
                          href={run.fix_pr_url}
                          target="_blank"
                          rel="noreferrer"
                        >
                          PR #{run.fix_pr_number}
                        </a>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="p-4">
                      {run.ci_passed === true ? (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 ring-1 ring-emerald-500/20">
                          ✓ Pass
                        </span>
                      ) : run.ci_passed === false ? (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-red-500/10 text-red-400 ring-1 ring-red-500/20">
                          ✗ Fail
                        </span>
                      ) : (
                        <span className="text-slate-500">—</span>
                      )}
                    </td>
                    <td className="p-4 text-slate-400 text-sm">
                      {run.timestamp
                        ? formatDistanceToNow(new Date(run.timestamp), {
                            addSuffix: true,
                          })
                        : "–"}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

import React, { useEffect, useState } from "react";
import api from "../lib/api";

export default function Installations() {
  const [repos, setRepos] = useState([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get("/repos")
      .then((res) => setRepos(res.data.repos))
      .catch((e: any) =>
        setError(e?.response?.data?.error ?? "Failed to load installations"),
      );
  }, []);

  return (
    <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="flex justify-between items-center">
        <h2 className="text-3xl font-bold tracking-tight">
          Active Installations
        </h2>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 text-red-400 text-sm">
          {error}
        </div>
      )}
      <div className="bg-slate-900 border border-slate-800 rounded-xl shadow-md p-6">
        <h3 className="text-lg font-semibold mb-4 text-slate-200">
          Enforced Repositories
        </h3>
        <ul className="divide-y divide-slate-800">
          {repos.length === 0 ? (
            <li className="py-4 text-slate-500 text-center">
              No installations found
            </li>
          ) : (
            repos.map((repo: any) => (
              <li
                key={repo.id}
                className="py-4 flex justify-between items-center"
              >
                <div>
                  <p className="font-medium text-slate-200">
                    {repo.repo_owner}/{repo.repo_name}
                  </p>
                  <p className="text-sm text-slate-500">
                    Mode: <span className="text-emerald-400">{repo.mode}</span>
                  </p>
                </div>
                <div className="px-3 py-1 bg-slate-800 rounded-full text-xs font-semibold text-slate-400 ring-1 ring-slate-700">
                  {repo.enabled ? "Enabled" : "Disabled"}
                </div>
              </li>
            ))
          )}
        </ul>
      </div>
    </div>
  );
}

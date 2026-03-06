import React, { useEffect, useState } from "react";
import api from "../lib/api";
import { Save, Info } from "lucide-react";

interface RepoSetting {
  repo: string;
  enabled: boolean;
  mode: "warn" | "fix" | "disabled";
  max_diff_lines: number;
  max_runtime_seconds: number;
  ignore_file: string;
  auto_merge_enabled: boolean;
  permission_tier: string;
}

interface EffectiveSetting {
  enabled: boolean;
  mode: string;
  max_diff_lines: number;
  max_runtime_seconds: number;
  ignore_file: string;
  auto_merge_enabled: boolean;
  permission_tier: string;
  source?: string;
}

const DEFAULT_SETTING: RepoSetting = {
  repo: "",
  enabled: true,
  mode: "warn",
  max_diff_lines: 500,
  max_runtime_seconds: 120,
  ignore_file: "",
  auto_merge_enabled: false,
  permission_tier: "A",
};

export default function RepoSettings() {
  const [repos, setRepos] = useState<
    { id: number; repo_owner: string; repo_name: string }[]
  >([]);
  const [selected, setSelected] = useState<string>("");
  const [settings, setSettings] = useState<RepoSetting>({ ...DEFAULT_SETTING });
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [effective, setEffective] = useState<EffectiveSetting | null>(null);

  useEffect(() => {
    api
      .get("/repos")
      .then((res) => {
        const repoList = (res.data.repos || []).map((r: any) => ({
          id: r.id,
          repo_owner: r.repo_owner,
          repo_name: r.repo_name,
        }));
        setRepos(repoList);
        if (repoList.length > 0)
          setSelected(`${repoList[0].repo_owner}/${repoList[0].repo_name}`);
      })
      .catch((e: any) =>
        setError(e?.response?.data?.error ?? "Failed to load repositories"),
      );
  }, []);

  useEffect(() => {
    if (!selected) return;
    const encoded = encodeURIComponent(selected);
    api
      .get(`/repos/${encoded}/settings`)
      .then((res) => setSettings(res.data))
      .catch(() => setSettings({ ...DEFAULT_SETTING, repo: selected }));
    api
      .get(`/repos/${encoded}/effective-settings`)
      .then((res) => setEffective(res.data))
      .catch(() => setEffective(null));
  }, [selected]);

  const handleSave = () => {
    const encoded = encodeURIComponent(selected);
    api
      .put(`/repos/${encoded}/settings`, settings)
      .then(() => {
        setSaved(true);
        setError(null);
        setTimeout(() => setSaved(false), 3000);
      })
      .catch(() => setError("Failed to save settings"));
  };

  return (
    <div className="max-w-3xl space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <h2 className="text-3xl font-bold tracking-tight">Repository Settings</h2>

      {repos.length > 0 && (
        <select
          className="w-full bg-slate-800 border border-slate-700 rounded-lg p-3 text-slate-200 focus:outline-none focus:ring-2 focus:ring-emerald-500"
          value={selected}
          onChange={(e) => setSelected(e.target.value)}
        >
          {repos.map((r) => (
            <option key={r.id} value={`${r.repo_owner}/${r.repo_name}`}>
              {r.repo_owner}/{r.repo_name}
            </option>
          ))}
        </select>
      )}

      <div className="bg-slate-900 border border-slate-800 rounded-xl shadow-md p-8 space-y-6">
        {/* Enable toggle */}
        <div className="flex items-center justify-between">
          <div>
            <p className="font-medium text-slate-200">Enable Railo</p>
            <p className="text-sm text-slate-500">
              Turn scanning on or off for this repo
            </p>
          </div>
          <label className="relative inline-flex items-center cursor-pointer">
            <input
              type="checkbox"
              className="sr-only peer"
              checked={settings.enabled}
              onChange={(e) =>
                setSettings((s) => ({ ...s, enabled: e.target.checked }))
              }
            />
            <div className="w-11 h-6 bg-slate-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-emerald-500" />
          </label>
        </div>

        {/* Mode */}
        <div className="flex items-center justify-between">
          <div>
            <p className="font-medium text-slate-200">Mode</p>
            <p className="text-sm text-slate-500">
              warn: comment only. fix: open fix PRs. disabled: do nothing.
            </p>
          </div>
          <select
            className="bg-slate-800 border border-slate-700 rounded-lg px-4 py-2 text-slate-200 focus:outline-none focus:ring-2 focus:ring-emerald-500"
            value={settings.mode}
            onChange={(e) =>
              setSettings((s) => ({
                ...s,
                mode: e.target.value as "warn" | "fix" | "disabled",
              }))
            }
          >
            <option value="warn">warn — comment only</option>
            <option value="fix">fix — open fix PRs automatically</option>
            <option value="disabled">disabled — do nothing</option>
          </select>
        </div>

        {/* Max diff lines */}
        <div className="space-y-1">
          <div className="flex justify-between">
            <p className="font-medium text-slate-200">Max Diff Lines</p>
            <span className="text-slate-400 font-mono">
              {settings.max_diff_lines}
            </span>
          </div>
          <input
            type="range"
            min={100}
            max={2000}
            step={50}
            className="w-full accent-emerald-500"
            value={settings.max_diff_lines}
            onChange={(e) =>
              setSettings((s) => ({ ...s, max_diff_lines: +e.target.value }))
            }
          />
          <div className="flex justify-between text-xs text-slate-600">
            <span>100</span>
            <span>2000</span>
          </div>
        </div>

        {/* Max runtime */}
        <div className="space-y-1">
          <div className="flex justify-between">
            <p className="font-medium text-slate-200">Max Runtime (seconds)</p>
            <span className="text-slate-400 font-mono">
              {settings.max_runtime_seconds}s
            </span>
          </div>
          <input
            type="range"
            min={10}
            max={300}
            step={10}
            className="w-full accent-emerald-500"
            value={settings.max_runtime_seconds}
            onChange={(e) =>
              setSettings((s) => ({
                ...s,
                max_runtime_seconds: +e.target.value,
              }))
            }
          />
          <div className="flex justify-between text-xs text-slate-600">
            <span>10s</span>
            <span>300s</span>
          </div>
        </div>

        {/* Ignore file */}
        <div className="space-y-2">
          <p className="font-medium text-slate-200">.fixpointignore</p>
          <p className="text-sm text-slate-500">One glob pattern per line</p>
          <textarea
            rows={6}
            className="w-full bg-slate-800 border border-slate-700 rounded-lg p-3 text-slate-200 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500 resize-y"
            placeholder={"**/.git/\nnode_modules/\ndist/"}
            value={settings.ignore_file}
            onChange={(e) =>
              setSettings((s) => ({ ...s, ignore_file: e.target.value }))
            }
          />
        </div>

        {/* Permission tier */}
        <div className="border-t border-slate-800 pt-6 space-y-3">
          <div>
            <p className="font-medium text-slate-200">Permission Tier</p>
            <p className="text-sm text-slate-500">
              Tier A (default) — warn &amp; fix PRs. Tier B (enterprise) —
              enables revert push and auto-merge.
            </p>
          </div>
          <select
            className="w-full bg-slate-800 border border-slate-700 rounded-lg px-4 py-2 text-slate-200 focus:outline-none focus:ring-2 focus:ring-emerald-500"
            value={settings.permission_tier}
            onChange={(e) =>
              setSettings((s) => ({ ...s, permission_tier: e.target.value }))
            }
          >
            <option value="A">A — Safe (default): warn &amp; fix PRs</option>
            <option value="B">B — Enterprise: revert push + auto-merge</option>
          </select>
        </div>

        {/* Auto-merge */}
        <div className="flex items-center justify-between">
          <div>
            <p className="font-medium text-slate-200">
              Auto-merge low-risk fix PRs
            </p>
            <p className="text-sm text-slate-500">
              {settings.permission_tier === "B"
                ? "Merges fix PRs that pass all 5 safety gates."
                : "Requires Tier B."}
            </p>
          </div>
          <label
            className={`relative inline-flex items-center ${
              settings.permission_tier === "B"
                ? "cursor-pointer"
                : "cursor-not-allowed opacity-40"
            }`}
          >
            <input
              type="checkbox"
              className="sr-only peer"
              checked={
                settings.auto_merge_enabled && settings.permission_tier === "B"
              }
              disabled={settings.permission_tier !== "B"}
              onChange={(e) =>
                setSettings((s) => ({
                  ...s,
                  auto_merge_enabled: e.target.checked,
                }))
              }
            />
            <div className="w-11 h-6 bg-slate-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-emerald-500" />
          </label>
        </div>

        {error && <p className="text-red-400 text-sm">{error}</p>}

        <button
          onClick={handleSave}
          className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold px-5 py-2.5 rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-emerald-400"
        >
          <Save className="w-4 h-4" />
          {saved ? "Saved!" : "Save Settings"}
        </button>
      </div>

      {/* Effective settings panel */}
      {effective && (
        <div className="bg-slate-950 border border-slate-700 rounded-xl shadow-md p-6 space-y-4">
          <div className="flex items-center gap-2 mb-2">
            <Info className="w-4 h-4 text-slate-400" />
            <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-widest">
              Effective Settings (merged org + repo)
            </h3>
          </div>
          <p className="text-xs text-slate-500">
            The values actually applied when Railo runs on this repo. Org-level
            defaults are overridden by any repo-specific setting above.
          </p>
          <div className="grid grid-cols-2 gap-x-8 gap-y-2 text-sm">
            {(
              [
                ["Enabled", effective.enabled ? "yes" : "no"],
                ["Mode", effective.mode],
                ["Max diff lines", String(effective.max_diff_lines)],
                ["Max runtime (s)", String(effective.max_runtime_seconds)],
                ["Permission tier", effective.permission_tier ?? "A"],
                [
                  "Auto-merge",
                  effective.auto_merge_enabled ? "enabled" : "disabled",
                ],
                ["Ignore file", effective.ignore_file || "(none)"],
              ] as [string, string][]
            ).map(([label, val]) => (
              <React.Fragment key={label}>
                <span className="text-slate-500">{label}</span>
                <span className="text-slate-200 font-mono">{val}</span>
              </React.Fragment>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

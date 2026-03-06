import React, { useEffect, useState } from "react";
import { Building2, Save, RefreshCw } from "lucide-react";
import api from "../lib/api";

interface OrgPolicy {
  account_login: string;
  enabled: boolean;
  mode: string;
  max_diff_lines: number;
  max_runtime_seconds: number;
  ignore_file: string;
  auto_merge_enabled: boolean;
  permission_tier: string;
}

const DEFAULTS: Omit<OrgPolicy, "account_login"> = {
  enabled: true,
  mode: "warn",
  max_diff_lines: 500,
  max_runtime_seconds: 120,
  ignore_file: "",
  auto_merge_enabled: false,
  permission_tier: "A",
};

export default function OrgSettings() {
  const [login, setLogin] = useState("");
  const [policy, setPolicy] = useState<OrgPolicy | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchPolicy = async (slug: string) => {
    if (!slug.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.get(`/orgs/${slug.trim()}/settings`);
      setPolicy(res.data);
    } catch (e: any) {
      setError(e?.response?.data?.error ?? "Failed to fetch org settings");
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    if (!policy) return;
    setSaving(true);
    setError(null);
    try {
      await api.put(`/orgs/${policy.account_login}/settings`, {
        enabled: policy.enabled,
        mode: policy.mode,
        max_diff_lines: policy.max_diff_lines,
        max_runtime_seconds: policy.max_runtime_seconds,
        ignore_file: policy.ignore_file,
        auto_merge_enabled: policy.auto_merge_enabled,
        permission_tier: policy.permission_tier,
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e: any) {
      setError(e?.response?.data?.error ?? "Failed to save org settings");
    } finally {
      setSaving(false);
    }
  };

  const update = (field: keyof OrgPolicy, value: any) => {
    setPolicy((p) => (p ? { ...p, [field]: value } : p));
  };

  return (
    <div className="p-8 max-w-2xl mx-auto space-y-8">
      <div className="flex items-center space-x-3">
        <Building2 className="w-7 h-7 text-emerald-400" />
        <h1 className="text-2xl font-bold text-slate-100">Org-Level Policy</h1>
      </div>

      <p className="text-sm text-slate-400">
        Set default scanning policy for an entire GitHub organisation or user
        account. Individual repo settings can still override these defaults.
      </p>

      {/* Lookup */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-4">
        <label className="block text-sm font-medium text-slate-300">
          GitHub Organisation / User Login
        </label>
        <div className="flex gap-3">
          <input
            className="flex-1 bg-slate-800 border border-slate-700 rounded-lg px-4 py-2 text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-emerald-500"
            placeholder="e.g. acme-corp"
            value={login}
            onChange={(e) => setLogin(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && fetchPolicy(login)}
          />
          <button
            onClick={() => fetchPolicy(login)}
            disabled={loading || !login.trim()}
            className="flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white rounded-lg transition-colors"
          >
            {loading ? (
              <RefreshCw className="w-4 h-4 animate-spin" />
            ) : (
              <RefreshCw className="w-4 h-4" />
            )}
            Load
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-red-900/40 border border-red-700 rounded-lg px-4 py-3 text-red-300 text-sm">
          {error}
        </div>
      )}

      {policy && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-6">
          <h2 className="text-lg font-semibold text-slate-200">
            Policy for{" "}
            <span className="text-emerald-400">{policy.account_login}</span>
          </h2>

          {/* Enabled toggle */}
          <div className="flex items-center justify-between">
            <span className="text-sm text-slate-300">
              Fixpoint enabled for all repos in this org
            </span>
            <button
              onClick={() => update("enabled", !policy.enabled)}
              className={`relative w-12 h-6 rounded-full transition-colors ${
                policy.enabled ? "bg-emerald-500" : "bg-slate-700"
              }`}
            >
              <span
                className={`absolute top-1 left-1 w-4 h-4 rounded-full bg-white transition-transform ${
                  policy.enabled ? "translate-x-6" : "translate-x-0"
                }`}
              />
            </button>
          </div>

          {/* Mode */}
          <div className="space-y-2">
            <label className="text-sm font-medium text-slate-300">
              Default Mode
            </label>
            <select
              value={policy.mode}
              onChange={(e) => update("mode", e.target.value)}
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-slate-100 focus:outline-none focus:ring-2 focus:ring-emerald-500"
            >
              <option value="warn">warn — Comment only, no PR</option>
              <option value="fix">fix — Open a fix PR automatically</option>
              <option value="disabled">disabled — Do nothing</option>
            </select>
          </div>

          {/* max_diff_lines */}
          <div className="space-y-2">
            <label className="text-sm font-medium text-slate-300">
              Max diff lines{" "}
              <span className="text-slate-500 font-normal">(default 500)</span>
            </label>
            <input
              type="number"
              min={10}
              max={10000}
              value={policy.max_diff_lines}
              onChange={(e) =>
                update("max_diff_lines", parseInt(e.target.value, 10) || 500)
              }
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-slate-100 focus:outline-none focus:ring-2 focus:ring-emerald-500"
            />
          </div>

          {/* max_runtime_seconds */}
          <div className="space-y-2">
            <label className="text-sm font-medium text-slate-300">
              Max runtime (seconds){" "}
              <span className="text-slate-500 font-normal">(default 120)</span>
            </label>
            <input
              type="number"
              min={10}
              max={600}
              value={policy.max_runtime_seconds}
              onChange={(e) =>
                update(
                  "max_runtime_seconds",
                  parseInt(e.target.value, 10) || 120,
                )
              }
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-slate-100 focus:outline-none focus:ring-2 focus:ring-emerald-500"
            />
          </div>

          {/* ignore_file */}
          <div className="space-y-2">
            <label className="text-sm font-medium text-slate-300">
              Ignore file path{" "}
              <span className="text-slate-500 font-normal">
                (e.g. .semgrepignore)
              </span>
            </label>
            <input
              type="text"
              value={policy.ignore_file}
              onChange={(e) => update("ignore_file", e.target.value)}
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-emerald-500"
              placeholder=".semgrepignore"
            />
          </div>

          {/* Permission tier */}
          <div className="space-y-2 border-t border-slate-800 pt-4">
            <label className="text-sm font-medium text-slate-300">
              Permission Tier
            </label>
            <p className="text-xs text-slate-500">
              Tier A (default) — warn &amp; fix PRs. Tier B (enterprise) —
              enables revert push and auto-merge.
            </p>
            <select
              value={policy.permission_tier}
              onChange={(e) => update("permission_tier", e.target.value)}
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-slate-100 focus:outline-none focus:ring-2 focus:ring-emerald-500"
            >
              <option value="A">A — Safe (default): warn &amp; fix PRs</option>
              <option value="B">
                B — Enterprise: revert push + auto-merge
              </option>
            </select>
          </div>

          {/* Auto-merge — only meaningful on Tier B */}
          <div className="flex items-center justify-between">
            <div>
              <span className="text-sm text-slate-300">
                Auto-merge low-risk fix PRs
              </span>
              {policy.permission_tier !== "B" && (
                <p className="text-xs text-amber-500 mt-0.5">Requires Tier B</p>
              )}
            </div>
            <button
              onClick={() =>
                policy.permission_tier === "B" &&
                update("auto_merge_enabled", !policy.auto_merge_enabled)
              }
              disabled={policy.permission_tier !== "B"}
              className={`relative w-12 h-6 rounded-full transition-colors ${
                policy.auto_merge_enabled && policy.permission_tier === "B"
                  ? "bg-emerald-500"
                  : "bg-slate-700"
              } disabled:opacity-40 disabled:cursor-not-allowed`}
            >
              <span
                className={`absolute top-1 left-1 w-4 h-4 rounded-full bg-white transition-transform ${
                  policy.auto_merge_enabled && policy.permission_tier === "B"
                    ? "translate-x-6"
                    : "translate-x-0"
                }`}
              />
            </button>
          </div>

          <button
            onClick={handleSave}
            disabled={saving}
            className={`flex items-center gap-2 px-6 py-2 rounded-lg font-medium transition-colors ${
              saved
                ? "bg-green-600 text-white"
                : "bg-emerald-600 hover:bg-emerald-500 text-white disabled:opacity-50"
            }`}
          >
            <Save className="w-4 h-4" />
            {saved ? "Saved!" : saving ? "Saving…" : "Save Policy"}
          </button>
        </div>
      )}
    </div>
  );
}

import React, { useEffect, useState } from "react";
import { Bell, Save, RefreshCw } from "lucide-react";
import api from "../lib/api";

interface NotifSettings {
  installation_id: number;
  slack_webhook_url: string;
  email: string;
  notify_on_fix_applied: boolean;
  notify_on_ci_failure: boolean;
  notify_on_ci_success: boolean;
  notify_on_revert: boolean;
  digest_mode: boolean;
}

interface Installation {
  installation_id: number;
  account_login: string;
}

export default function NotificationSettings() {
  const [installations, setInstallations] = useState<Installation[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [settings, setSettings] = useState<NotifSettings | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.get("/installations").then((res) => {
      const list: Installation[] = res.data?.installations ?? res.data ?? [];
      setInstallations(list);
      if (list.length > 0) {
        setSelectedId(list[0].installation_id);
      }
    });
  }, []);

  useEffect(() => {
    if (selectedId === null) return;
    setLoading(true);
    setError(null);
    api
      .get(`/installations/${selectedId}/notifications`)
      .then((res) => setSettings(res.data))
      .catch((e) =>
        setError(
          e?.response?.data?.error ?? "Failed to fetch notification settings",
        ),
      )
      .finally(() => setLoading(false));
  }, [selectedId]);

  const update = (field: keyof NotifSettings, value: any) => {
    setSettings((s) => (s ? { ...s, [field]: value } : s));
  };

  const handleSave = async () => {
    if (!settings) return;
    setSaving(true);
    setError(null);
    try {
      await api.put(
        `/installations/${settings.installation_id}/notifications`,
        {
          slack_webhook_url: settings.slack_webhook_url,
          email: settings.email,
          notify_on_fix_applied: settings.notify_on_fix_applied,
          notify_on_ci_failure: settings.notify_on_ci_failure,
          notify_on_ci_success: settings.notify_on_ci_success,
          notify_on_revert: settings.notify_on_revert,
          digest_mode: settings.digest_mode,
        },
      );
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e: any) {
      setError(
        e?.response?.data?.error ?? "Failed to save notification settings",
      );
    } finally {
      setSaving(false);
    }
  };

  const Toggle = ({
    value,
    onChange,
    label,
  }: {
    value: boolean;
    onChange: (v: boolean) => void;
    label: string;
  }) => (
    <div className="flex items-center justify-between py-2">
      <span className="text-sm text-slate-300">{label}</span>
      <button
        onClick={() => onChange(!value)}
        className={`relative w-12 h-6 rounded-full transition-colors ${
          value ? "bg-emerald-500" : "bg-slate-700"
        }`}
      >
        <span
          className={`absolute top-1 left-1 w-4 h-4 rounded-full bg-white transition-transform ${
            value ? "translate-x-6" : "translate-x-0"
          }`}
        />
      </button>
    </div>
  );

  return (
    <div className="p-8 max-w-2xl mx-auto space-y-8">
      <div className="flex items-center space-x-3">
        <Bell className="w-7 h-7 text-emerald-400" />
        <h1 className="text-2xl font-bold text-slate-100">
          Notification Settings
        </h1>
      </div>

      <p className="text-sm text-slate-400">
        Configure where Railo sends alerts when it creates a fix PR, when CI
        passes, or when CI fails and a revert is pushed.
      </p>

      {/* Installation picker */}
      {installations.length > 1 && (
        <div className="space-y-2">
          <label className="text-sm font-medium text-slate-300">
            Installation
          </label>
          <select
            value={selectedId ?? ""}
            onChange={(e) => setSelectedId(Number(e.target.value))}
            className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-slate-100 focus:outline-none focus:ring-2 focus:ring-emerald-500"
          >
            {installations.map((i) => (
              <option key={i.installation_id} value={i.installation_id}>
                {i.account_login} (#{i.installation_id})
              </option>
            ))}
          </select>
        </div>
      )}

      {loading && (
        <div className="flex items-center gap-2 text-slate-400 text-sm">
          <RefreshCw className="w-4 h-4 animate-spin" /> Loading…
        </div>
      )}

      {error && (
        <div className="bg-red-900/40 border border-red-700 rounded-lg px-4 py-3 text-red-300 text-sm">
          {error}
        </div>
      )}

      {settings && !loading && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-6">
          {/* Slack */}
          <div className="space-y-2">
            <label className="text-sm font-medium text-slate-300">
              Slack Incoming Webhook URL
            </label>
            <input
              type="url"
              value={settings.slack_webhook_url}
              onChange={(e) => update("slack_webhook_url", e.target.value)}
              placeholder="https://hooks.slack.com/services/…"
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-emerald-500"
            />
          </div>

          {/* Email */}
          <div className="space-y-2">
            <label className="text-sm font-medium text-slate-300">
              Email address
            </label>
            <input
              type="email"
              value={settings.email}
              onChange={(e) => update("email", e.target.value)}
              placeholder="security@example.com"
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-emerald-500"
            />
          </div>

          {/* Event toggles */}
          <div className="border-t border-slate-800 pt-4 space-y-1">
            <p className="text-xs font-semibold uppercase tracking-widest text-slate-500 mb-3">
              Events
            </p>
            <Toggle
              value={settings.notify_on_fix_applied}
              onChange={(v) => update("notify_on_fix_applied", v)}
              label="Fix PR created"
            />
            <Toggle
              value={settings.notify_on_ci_failure}
              onChange={(v) => update("notify_on_ci_failure", v)}
              label="CI failed (revert applied)"
            />
            <Toggle
              value={settings.notify_on_ci_success}
              onChange={(v) => update("notify_on_ci_success", v)}
              label="CI passed successfully"
            />
            <Toggle
              value={settings.notify_on_revert}
              onChange={(v) => update("notify_on_revert", v)}
              label="Revert triggered"
            />
          </div>

          {/* Delivery mode */}
          <div className="border-t border-slate-800 pt-4 space-y-1">
            <p className="text-xs font-semibold uppercase tracking-widest text-slate-500 mb-3">
              Delivery
            </p>
            <Toggle
              value={settings.digest_mode}
              onChange={(v) => update("digest_mode", v)}
              label="Daily digest instead of real-time alerts"
            />
            {settings.digest_mode && (
              <p className="text-xs text-slate-500 pl-1">
                Events will be batched. Use the digest flush API to send
                immediately.
              </p>
            )}
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
            {saved ? "Saved!" : saving ? "Saving…" : "Save Settings"}
          </button>
        </div>
      )}

      {installations.length === 0 && !loading && (
        <div className="text-slate-500 text-sm">
          No installations found. Install the GitHub App first.
        </div>
      )}
    </div>
  );
}

import React, { useEffect, useState } from "react";
import api from "../lib/api";

export default function Settings() {
  const [settings, setSettings] = useState({
    theme: "dark",
    notifications_enabled: true,
    role: "admin",
  });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get("/user/settings")
      .then((res) => setSettings(res.data))
      .catch((e: any) =>
        setError(e?.response?.data?.error ?? "Failed to load settings"),
      );
  }, []);

  const handleToggle = () => {
    setSettings((prev) => ({
      ...prev,
      notifications_enabled: !prev.notifications_enabled,
    }));
    setSaved(false);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.put("/user/settings", {
        notifications_enabled: settings.notifications_enabled,
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (err: any) {
      setError(err?.response?.data?.error ?? "Failed to save settings");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="max-w-3xl space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <h2 className="text-3xl font-bold tracking-tight">Settings</h2>

      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 text-red-400 text-sm">
          {error}
        </div>
      )}
      <div className="bg-slate-900 border border-slate-800 rounded-xl shadow-md p-8 space-y-6">
        <div>
          <h3 className="text-xl font-semibold border-b border-slate-800 pb-2 mb-4">
            Profile
          </h3>
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="font-medium text-slate-200">Current Role</p>
                <p className="text-sm text-slate-500">
                  Your assigned RBAC role
                </p>
              </div>
              <span className="px-3 py-1 bg-blue-500/10 text-blue-400 rounded-full text-xs font-bold uppercase tracking-wider ring-1 ring-blue-500/20">
                {settings.role}
              </span>
            </div>
          </div>
        </div>

        <div>
          <h3 className="text-xl font-semibold border-b border-slate-800 pb-2 mb-4">
            Preferences
          </h3>
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="font-medium text-slate-200">
                  Email Notifications
                </p>
                <p className="text-sm text-slate-500">
                  Receive alerts for failed runs
                </p>
              </div>
              <label className="relative inline-flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  checked={settings.notifications_enabled}
                  onChange={handleToggle}
                  className="sr-only peer"
                />
                <div className="w-11 h-6 bg-slate-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-emerald-500"></div>
              </label>
            </div>
          </div>
        </div>

        <div className="flex items-center justify-end gap-3 pt-2">
          {saved && (
            <span className="text-sm text-emerald-400 font-medium">
              Saved ✓
            </span>
          )}
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-sm font-semibold rounded-lg transition-colors"
          >
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}

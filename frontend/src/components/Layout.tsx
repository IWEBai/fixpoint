import React, { useEffect, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import {
  LayoutDashboard,
  History,
  Settings,
  LogOut,
  Server,
  Building2,
  Bell,
} from "lucide-react";
import api from "../lib/api";

export default function Layout() {
  const navigate = useNavigate();
  const [user, setUser] = useState<{ username?: string; role?: string } | null>(
    null,
  );

  useEffect(() => {
    api
      .get("/auth/me", { baseURL: "/" })
      .then((res) => setUser(res.data))
      .catch(() => {});
  }, []);

  const handleLogout = async () => {
    try {
      await api.post("/auth/logout");
    } catch {
      // Ignore logout errors — navigate away regardless
    }
    navigate("/");
  };

  const navLinks = [
    { to: "/app", label: "Analytics", icon: LayoutDashboard },
    { to: "/app/runs", label: "Run History", icon: History },
    { to: "/app/installations", label: "Installations", icon: Server },
    { to: "/app/org-settings", label: "Org Policy", icon: Building2 },
    { to: "/app/repo-settings", label: "Repo Settings", icon: Settings },
    { to: "/app/notifications", label: "Notifications", icon: Bell },
    { to: "/app/settings", label: "Settings", icon: Settings },
  ];

  return (
    <div className="flex h-screen bg-slate-900 text-slate-100 overflow-hidden">
      {/* Sidebar */}
      <aside className="w-64 bg-slate-950 border-r border-slate-800 flex flex-col">
        <div className="p-6 flex items-center space-x-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-emerald-400 to-blue-500 shadow-emerald-500/50 shadow-lg"></div>
          <h1 className="text-xl font-bold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-emerald-400 to-blue-400">
            Railo Cloud
          </h1>
        </div>
        <nav className="flex-1 px-4 space-y-2 mt-4">
          {navLinks.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              className={({ isActive }) =>
                `flex items-center space-x-3 px-3 py-2 rounded-md transition-all duration-200 ${
                  isActive
                    ? "bg-slate-800 text-emerald-400 font-medium shadow-md"
                    : "text-slate-400 hover:bg-slate-800/50 hover:text-slate-200"
                }`
              }
            >
              <link.icon className="w-5 h-5" />
              <span>{link.label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="p-4 border-t border-slate-800">
          <button
            onClick={handleLogout}
            className="flex items-center space-x-3 px-3 py-2 w-full text-left text-slate-400 hover:text-red-400 hover:bg-slate-800/50 rounded-md transition-colors"
          >
            <LogOut className="w-5 h-5" />
            <span>Sign Out</span>
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col overflow-hidden">
        <header className="h-16 border-b border-slate-800 flex items-center px-8 bg-slate-950/50 backdrop-blur-md sticky top-0 z-10">
          <div className="flex-1"></div>
          <div className="flex items-center space-x-4">
            {user?.role && (
              <span className="text-sm font-medium text-slate-400 px-3 py-1 rounded-full bg-slate-800 ring-1 ring-slate-700 capitalize">
                {user.role === "admin" ? "Admin Mode" : user.role}
              </span>
            )}
            <div className="w-8 h-8 rounded-full bg-slate-700 flex items-center justify-center border border-slate-600">
              <span className="text-sm font-bold text-slate-300">
                {user?.username ? user.username[0].toUpperCase() : "?"}
              </span>
            </div>
          </div>
        </header>
        <div className="flex-1 overflow-auto p-8 bg-gradient-to-b from-slate-900 to-slate-950">
          <Outlet />
        </div>
      </main>
    </div>
  );
}

import React from "react";
import { useNavigate } from "react-router-dom";
import {
  ShieldCheck,
  GitPullRequest,
  Zap,
  Lock,
  Code2,
  GitMerge,
  ChevronRight,
  Github,
} from "lucide-react";

const GITHUB_APP_INSTALL_URL = "https://github.com/apps/railo/installations/new";

export default function LandingPage() {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      {/* ── Navbar ── */}
      <header className="fixed top-0 left-0 right-0 z-50 border-b border-slate-800/60 bg-slate-950/80 backdrop-blur-md">
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-emerald-400 to-blue-500 shadow-lg shadow-emerald-500/30 flex items-center justify-center">
              <span className="text-sm font-bold text-white">R</span>
            </div>
            <span className="text-lg font-bold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-emerald-400 to-blue-400">
              Railo
            </span>
          </div>
          <nav className="hidden md:flex items-center space-x-8 text-sm text-slate-400">
            <a href="#how-it-works" className="hover:text-slate-200 transition-colors">How it works</a>
            <a href="#what-it-catches" className="hover:text-slate-200 transition-colors">What it catches</a>
            <a href="#why-railo" className="hover:text-slate-200 transition-colors">Why Railo</a>
          </nav>
          <button
            onClick={() => navigate("/login")}
            className="flex items-center space-x-2 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 text-sm font-medium px-4 py-2 rounded-lg transition-colors"
          >
            <Github className="w-4 h-4" />
            <span>Sign in</span>
          </button>
        </div>
      </header>

      {/* ── Hero ── */}
      <section className="flex-1 flex flex-col items-center justify-center text-center px-6 pt-32 pb-24">
        {/* Badge */}
        <div className="mb-6 inline-flex items-center space-x-2 bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs font-medium px-4 py-1.5 rounded-full">
          <ShieldCheck className="w-3.5 h-3.5" />
          <span>Automated security patching for GitHub repositories</span>
        </div>

        <h1 className="text-5xl md:text-7xl font-extrabold tracking-tight leading-tight max-w-4xl bg-clip-text text-transparent bg-gradient-to-br from-slate-100 via-slate-200 to-slate-400">
          Fix security bugs{" "}
          <span className="bg-clip-text text-transparent bg-gradient-to-r from-emerald-400 to-blue-400">
            before they ship.
          </span>
        </h1>

        <p className="mt-6 text-lg md:text-xl text-slate-400 max-w-2xl leading-relaxed">
          Railo watches every pull request, detects vulnerabilities, and opens
          a companion fix PR automatically — no tickets, no manual review
          backlog, no context switching.
        </p>

        <div className="mt-10 flex flex-col sm:flex-row items-center gap-4">
          <a
            href={GITHUB_APP_INSTALL_URL}
            className="flex items-center space-x-2 bg-gradient-to-r from-emerald-500 to-blue-500 hover:from-emerald-400 hover:to-blue-400 text-white font-semibold px-7 py-3.5 rounded-xl shadow-lg shadow-emerald-500/20 transition-all hover:scale-[1.03]"
          >
            <Github className="w-5 h-5" />
            <span>Install on GitHub — it's free</span>
            <ChevronRight className="w-4 h-4" />
          </a>
          <button
            onClick={() => navigate("/login")}
            className="text-slate-400 hover:text-slate-200 text-sm font-medium transition-colors"
          >
            Already installed? Sign in →
          </button>
        </div>

        {/* Hero visual — terminal snippet */}
        <div className="mt-16 w-full max-w-2xl bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden shadow-2xl shadow-black/40 text-left">
          <div className="flex items-center space-x-2 px-4 py-3 border-b border-slate-800 bg-slate-950">
            <div className="w-3 h-3 rounded-full bg-red-500/70"></div>
            <div className="w-3 h-3 rounded-full bg-yellow-500/70"></div>
            <div className="w-3 h-3 rounded-full bg-emerald-500/70"></div>
            <span className="ml-3 text-xs text-slate-500 font-mono">railo — PR #147 scan result</span>
          </div>
          <div className="p-5 font-mono text-sm space-y-1.5">
            <p><span className="text-slate-500">→</span> <span className="text-slate-300">Scanning PR #147: </span><span className="text-blue-400">add-user-search</span></p>
            <p><span className="text-slate-500">→</span> <span className="text-yellow-400">SQLi detected</span><span className="text-slate-400"> in </span><span className="text-slate-300">src/db/users.py:83</span></p>
            <p><span className="text-slate-500">→</span> <span className="text-yellow-400">XSS detected</span><span className="text-slate-400"> in </span><span className="text-slate-300">src/api/search.py:41</span></p>
            <p className="pt-1"><span className="text-emerald-400">✓</span> <span className="text-slate-300">Fix PR opened: </span><span className="text-blue-400">#148 railo/fix-pr-147</span></p>
            <p><span className="text-emerald-400">✓</span> <span className="text-slate-300">CI passed — ready to merge</span></p>
          </div>
        </div>
      </section>

      {/* ── How it works ── */}
      <section id="how-it-works" className="py-24 px-6 border-t border-slate-800/60">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-14">
            <h2 className="text-3xl md:text-4xl font-bold">How it works</h2>
            <p className="mt-3 text-slate-400">Three steps. Fully automatic.</p>
          </div>
          <div className="grid md:grid-cols-3 gap-8">
            {[
              {
                icon: GitPullRequest,
                step: "01",
                title: "PR is opened",
                desc: "A developer opens a pull request. Railo is notified instantly via GitHub webhook.",
                color: "from-slate-700 to-slate-600",
              },
              {
                icon: ShieldCheck,
                step: "02",
                title: "Railo scans",
                desc: "Railo analyses the diff for SQL injection, XSS, secrets, command injection, path traversal, and SSRF.",
                color: "from-emerald-600 to-emerald-500",
              },
              {
                icon: GitMerge,
                step: "03",
                title: "Fix PR created",
                desc: "If vulnerabilities are found, Railo opens a companion fix PR with patches applied and CI running.",
                color: "from-blue-600 to-blue-500",
              },
            ].map((item) => (
              <div key={item.step} className="relative bg-slate-900 border border-slate-800 rounded-2xl p-7 flex flex-col space-y-4 hover:border-slate-700 transition-colors">
                <div className={`w-12 h-12 rounded-xl bg-gradient-to-br ${item.color} flex items-center justify-center shadow-lg`}>
                  <item.icon className="w-6 h-6 text-white" />
                </div>
                <span className="text-xs font-mono text-slate-600 absolute top-6 right-6">{item.step}</span>
                <h3 className="text-lg font-semibold">{item.title}</h3>
                <p className="text-slate-400 text-sm leading-relaxed">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── What it catches ── */}
      <section id="what-it-catches" className="py-24 px-6 bg-slate-900/40">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-14">
            <h2 className="text-3xl md:text-4xl font-bold">What it catches</h2>
            <p className="mt-3 text-slate-400">
              Railo targets the OWASP Top 10 vulnerabilities most commonly missed in code review.
            </p>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            {[
              { label: "SQL Injection", desc: "Parameterised query enforcement", color: "emerald" },
              { label: "Cross-Site Scripting", desc: "Output encoding + sanitisation", color: "blue" },
              { label: "Secrets & Credentials", desc: "Hardcoded keys, tokens, passwords", color: "violet" },
              { label: "Command Injection", desc: "Shell call escaping", color: "orange" },
              { label: "Path Traversal", desc: "Directory escape prevention", color: "pink" },
              { label: "SSRF", desc: "Server-side request forgery blocks", color: "yellow" },
            ].map((item) => (
              <div key={item.label} className="bg-slate-900 border border-slate-800 rounded-xl p-5 flex flex-col space-y-2 hover:border-slate-700 transition-colors">
                <div className={`w-2 h-2 rounded-full bg-${item.color}-400`}></div>
                <h4 className="font-semibold text-sm">{item.label}</h4>
                <p className="text-xs text-slate-500">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Why Railo ── */}
      <section id="why-railo" className="py-24 px-6 border-t border-slate-800/60">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-14">
            <h2 className="text-3xl md:text-4xl font-bold">Why Railo</h2>
            <p className="mt-3 text-slate-400">Built for engineering teams, not security theatre.</p>
          </div>
          <div className="grid md:grid-cols-3 gap-8">
            {[
              {
                icon: Zap,
                title: "Zero config",
                desc: "Install the GitHub App. That's it. No YAML files, no CI pipeline changes, no agent to deploy.",
              },
              {
                icon: Code2,
                title: "Lives inside GitHub",
                desc: "Developers see fix PRs alongside their code. No dashboards to check, no external tools to learn.",
              },
              {
                icon: Lock,
                title: "No blame, just fixes",
                desc: "Railo opens fix PRs automatically. Security findings become merged code, not unanswered tickets.",
              },
            ].map((item) => (
              <div key={item.title} className="flex flex-col space-y-4">
                <div className="w-11 h-11 rounded-xl bg-slate-800 border border-slate-700 flex items-center justify-center">
                  <item.icon className="w-5 h-5 text-emerald-400" />
                </div>
                <h3 className="text-lg font-semibold">{item.title}</h3>
                <p className="text-slate-400 text-sm leading-relaxed">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── CTA ── */}
      <section className="py-24 px-6 bg-gradient-to-b from-slate-900/0 to-slate-900/60 border-t border-slate-800/60">
        <div className="max-w-2xl mx-auto text-center flex flex-col items-center space-y-6">
          <h2 className="text-3xl md:text-4xl font-bold leading-tight">
            Ready to ship{" "}
            <span className="bg-clip-text text-transparent bg-gradient-to-r from-emerald-400 to-blue-400">
              secure code?
            </span>
          </h2>
          <p className="text-slate-400">
            Install Railo on your GitHub organisation in under a minute.
          </p>
          <a
            href={GITHUB_APP_INSTALL_URL}
            className="flex items-center space-x-2 bg-gradient-to-r from-emerald-500 to-blue-500 hover:from-emerald-400 hover:to-blue-400 text-white font-semibold px-8 py-4 rounded-xl shadow-lg shadow-emerald-500/20 transition-all hover:scale-[1.03]"
          >
            <Github className="w-5 h-5" />
            <span>Install on GitHub</span>
          </a>
        </div>
      </section>

      {/* ── Footer ── */}
      <footer className="border-t border-slate-800 py-8 px-6">
        <div className="max-w-6xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4 text-sm text-slate-600">
          <div className="flex items-center space-x-2">
            <div className="w-5 h-5 rounded bg-gradient-to-tr from-emerald-400 to-blue-500"></div>
            <span>Railo — automated security patching</span>
          </div>
          <div className="flex items-center space-x-6">
            <a href="https://github.com/IWEBai/railo" className="hover:text-slate-400 transition-colors">GitHub</a>
            <a href="/docs" className="hover:text-slate-400 transition-colors">Docs</a>
            <button onClick={() => navigate("/login")} className="hover:text-slate-400 transition-colors">Sign in</button>
          </div>
        </div>
      </footer>
    </div>
  );
}

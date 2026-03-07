import React from "react";

export default function Login() {
  const handleLogin = () => {
    // Redirect to GitHub OAuth entry point
    window.location.href = "/auth/login/github";
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-950 text-slate-100">
      <div className="w-full max-w-md p-8 bg-slate-900 border border-slate-800 rounded-xl shadow-2xl flex flex-col items-center space-y-8">
        <div className="w-16 h-16 rounded-2xl bg-gradient-to-tr from-emerald-500 to-blue-600 shadow-emerald-500/50 shadow-lg mb-4 flex items-center justify-center">
          <span className="text-2xl font-bold">R</span>
        </div>

        <div className="text-center space-y-2">
          <h2 className="text-3xl font-bold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-emerald-400 to-blue-400">
            Railo Cloud
          </h2>
          <p className="text-slate-400">
            Sign in to manage and monitor your secure fixes.
          </p>
        </div>

        <button
          onClick={handleLogin}
          className="w-full flex items-center justify-center space-x-3 bg-slate-100 hover:bg-white text-slate-900 font-semibold py-3 px-4 rounded-lg transition-transform transform hover:scale-[1.02] shadow-md"
        >
          <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
            <path
              fillRule="evenodd"
              clipRule="evenodd"
              d="M12 2C6.477 2 2 6.477 2 12c0 4.42 2.87 8.167 6.839 9.49.5.092.682-.217.682-.482 0-.237-.008-.866-.013-1.7-2.782.603-3.369-1.34-3.369-1.34-.454-1.156-1.11-1.464-1.11-1.464-.908-.62.069-.608.069-.608 1.003.07 1.531 1.03 1.531 1.03.892 1.529 2.341 1.087 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.11-4.555-4.943 0-1.091.39-1.984 1.029-2.683-.103-.253-.446-1.27.098-2.647 0 0 .84-.269 2.75 1.025A9.564 9.564 0 0112 6.844c.85.004 1.705.114 2.504.336 1.909-1.294 2.747-1.025 2.747-1.025.546 1.377.203 2.394.1 2.647.64.699 1.028 1.592 1.028 2.683 0 3.842-2.339 4.687-4.566 4.935.359.309.678.919.678 1.852 0 1.336-.012 2.415-.012 2.743 0 .267.18.578.688.48C19.138 20.161 22 16.416 22 12c0-5.523-4.477-10-10-10z"
            />
          </svg>
          <span>Continue with GitHub</span>
        </button>
      </div>
    </div>
  );
}

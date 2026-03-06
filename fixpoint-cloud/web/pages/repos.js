import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export default function ReposPage() {
  const [items, setItems] = useState([]);
  const [status, setStatus] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const res = await fetch(`${API}/repos`, { credentials: "include" });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          throw new Error(data?.detail || `Failed to load (${res.status})`);
        }
        if (mounted) setItems(data.repos || []);
      } catch (e) {
        if (mounted) setError(e?.message || "Failed to load");
      } finally {
        if (mounted) setLoading(false);
      }
    })();
    return () => {
      mounted = false;
    };
  }, []);

  const updateRepo = async (repoId, payload) => {
    setStatus((prev) => ({ ...prev, [repoId]: "saving" }));
    try {
      const res = await fetch(`${API}/repos/${repoId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data?.detail || `Update failed (${res.status})`);
      }
      const updated = await res.json();
      setItems((prev) =>
        prev.map((item) => (item.id === repoId ? updated : item)),
      );
      setStatus((prev) => ({ ...prev, [repoId]: "saved" }));
    } catch (err) {
      setStatus((prev) => ({ ...prev, [repoId]: err.message || "error" }));
    }
  };

  return (
    <div>
      <section className="hero">
        <span className="pill">Repositories</span>
        <h1>Repo controls</h1>
        <p>
          Enable or disable Railo per repo and switch between warn and enforce
          modes.
        </p>
      </section>

      {error && (
        <p className="muted">
          {error}{" "}
          {String(error).toLowerCase().includes("not authenticated") && (
            <a href="/login">Sign in</a>
          )}
        </p>
      )}

      <div className="card" style={{ marginTop: "20px" }}>
        {loading ? <p className="muted">Loading…</p> : null}
        {items.length === 0 ? (
          <p className="muted">No repositories registered yet.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Repo</th>
                <th>Mode</th>
                <th>Enabled</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {items.map((repo) => (
                <tr key={repo.id}>
                  <td>{`${repo.repo_owner}/${repo.repo_name}`}</td>
                  <td>
                    <select
                      value={repo.mode || "warn"}
                      onChange={(e) =>
                        updateRepo(repo.id, { mode: e.target.value })
                      }
                    >
                      <option value="warn">warn</option>
                      <option value="enforce">enforce</option>
                    </select>
                  </td>
                  <td>
                    <input
                      type="checkbox"
                      checked={repo.enabled}
                      onChange={(e) =>
                        updateRepo(repo.id, { enabled: e.target.checked })
                      }
                    />
                  </td>
                  <td className="muted">{status[repo.id] || ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

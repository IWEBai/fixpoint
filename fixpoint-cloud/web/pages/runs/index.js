import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export default function RunsPage() {
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const res = await fetch(`${API}/runs`, { credentials: "include" });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          throw new Error(data?.detail || `Failed to load (${res.status})`);
        }
        if (mounted) setRuns(data.runs || []);
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

  return (
    <div>
      <section className="hero">
        <span className="pill">Runs</span>
        <h1>Recent executions</h1>
        <p>Each run tracks scan status, fixes applied, and mode used.</p>
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
        {loading ? (
          <p className="muted">Loading…</p>
        ) : null}
        <table className="table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Status</th>
              <th>Repo</th>
              <th>PR</th>
              <th>Updated</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((r) => (
              <tr key={r.id}>
                <td>
                  <a href={`/runs/${r.id}`}>{r.id.slice(0, 8)}</a>
                </td>
                <td>{r.status}</td>
                <td>{`${r.repo_owner}/${r.repo_name}`}</td>
                <td>{r.pr_number ?? "-"}</td>
                <td>
                  {r.updated_at ? new Date(r.updated_at).toLocaleString() : "-"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

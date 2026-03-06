import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export default function RunDetail({ runId }) {
  const [run, setRun] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const res = await fetch(`${API}/runs/${runId}`, {
          credentials: "include",
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          throw new Error(data?.detail || `Failed to load (${res.status})`);
        }
        if (mounted) setRun(data);
      } catch (e) {
        if (mounted) setError(e?.message || "Unable to load this run.");
      } finally {
        if (mounted) setLoading(false);
      }
    })();
    return () => {
      mounted = false;
    };
  }, [runId]);

  if (loading) {
    return (
      <section className="hero">
        <span className="pill">Run detail</span>
        <h1>Loading…</h1>
      </section>
    );
  }

  if (!run) {
    return (
      <section className="hero">
        <span className="pill">Run detail</span>
        <h1>Run unavailable</h1>
        <p className="muted">
          {error}{" "}
          {String(error).toLowerCase().includes("not authenticated") && (
            <a href="/login">Sign in</a>
          )}
        </p>
      </section>
    );
  }

  return (
    <div>
      <section className="hero">
        <span className="pill">Run {run.id.slice(0, 8)}</span>
        <h1>
          {run.repo_owner}/{run.repo_name}
        </h1>
        <p className="muted">
          Mode: {run.mode || "warn"} · Status: {run.status}
        </p>
      </section>

      <div className="grid" style={{ marginTop: "20px" }}>
        <div className="card">
          <h3>Summary</h3>
          <p className="muted">{run.summary?.message || "No summary."}</p>
          {run.error_summary && <p>{run.error_summary}</p>}
        </div>
        <div className="card">
          <h3>Refs</h3>
          <p className="muted">Base: {run.base_ref || "-"}</p>
          <p className="muted">Head: {run.head_ref || "-"}</p>
          <p className="muted">SHA: {run.head_sha || "-"}</p>
        </div>
        <div className="card">
          <h3>Meta</h3>
          <p className="muted">PR: {run.pr_number ?? "-"}</p>
          <p className="muted">Engine: {run.engine_version ?? "-"}</p>
          <p className="muted">Fingerprint: {run.fingerprint ?? "-"}</p>
          <p className="muted">
            Updated:{" "}
            {run.updated_at ? new Date(run.updated_at).toLocaleString() : "-"}
          </p>
        </div>
      </div>

      <div className="card" style={{ marginTop: "20px" }}>
        <h3>Artifacts</h3>
        {run.artifact_paths && Object.keys(run.artifact_paths).length ? (
          <ul>
            {Object.entries(run.artifact_paths).map(([k, v]) => (
              <li key={k}>
                {k}: {String(v)}
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">No artifacts recorded.</p>
        )}
      </div>

      {run.error && (
        <div className="card" style={{ marginTop: "20px" }}>
          <h3>Error</h3>
          <pre className="code-block">{run.error}</pre>
        </div>
      )}

      <form
        action={`${API}/runs/${run.id}/rerun`}
        method="post"
        style={{ marginTop: "20px" }}
      >
        <button className="button button--ghost" type="submit">
          Rerun (local only)
        </button>
      </form>
    </div>
  );
}

export async function getServerSideProps(context) {
  return { props: { runId: context.params.id } };
}

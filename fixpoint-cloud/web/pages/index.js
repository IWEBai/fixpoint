export default function Home() {
  return (
    <div>
      <section className="hero">
        <span className="pill">Live security automation</span>
        <h1>Railo Cloud dashboard</h1>
        <p>
          Monitor pull request runs, tune warn/enforce mode, and see every fix
          applied by the Railo engine.
        </p>
        <div className="grid">
          <div className="card">
            <h3>Runs</h3>
            <p className="muted">Recent executions and status checks.</p>
            <a className="button" href="/runs">
              View runs
            </a>
          </div>
          <div className="card">
            <h3>Repositories</h3>
            <p className="muted">Enable repos and set warn/enforce mode.</p>
            <a className="button button--ghost" href="/repos">
              Manage repos
            </a>
          </div>
        </div>
      </section>
    </div>
  );
}

const API = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export default function LoginPage() {
  return (
    <section className="hero">
      <span className="pill">GitHub OAuth</span>
      <h1>Sign in to Railo</h1>
      <p>
        OAuth is handled by the API service. Continue to authenticate and return
        here for dashboard access.
      </p>
      <a
        className="button"
        href={`${API}/auth/callback/github?role=admin`}
      >
        Continue with GitHub
      </a>
    </section>
  );
}

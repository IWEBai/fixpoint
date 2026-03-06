import React from "react";
import Head from "next/head";
import "../styles/globals.css";

function MyApp({ Component, pageProps }) {
  return (
    <div className="page">
      <Head>
        <title>Railo Cloud</title>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          rel="preconnect"
          href="https://fonts.gstatic.com"
          crossOrigin=""
        />
        <link
          href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap"
          rel="stylesheet"
        />
      </Head>
      <div className="glow" />
      <div className="shell">
        <header className="nav">
          <div className="brand">
            <span className="brand__dot" />
            <span className="brand__name">Railo</span>
            <span className="brand__tag">Cloud</span>
          </div>
          <nav className="nav__links">
            <a href="/runs">Runs</a>
            <a href="/repos">Repos</a>
            <a href="/login">Login</a>
          </nav>
        </header>
        <main className="main">
          <Component {...pageProps} />
        </main>
        <footer className="footer">
          Railo Cloud · Deterministic security fixes
        </footer>
      </div>
    </div>
  );
}

export default MyApp;

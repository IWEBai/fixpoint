"""
Entry point for Fixpoint webhook server (Phase 2).
Run this to start listening for GitHub PR webhooks.
"""
from webhook.server import app

if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("DEBUG", "false").lower() == "true"
    
    print(f"Starting Fixpoint webhook server on port {port}")
    print("Listening for GitHub PR webhooks...")
    
    app.run(host="0.0.0.0", port=port, debug=debug)

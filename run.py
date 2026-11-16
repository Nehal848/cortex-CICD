"""
CortexCICD Application Entry Point
Usage:
    python run.py
"""
import os
from app.app import create_app

app = create_app()

if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_ENV", "development") != "production"
    print(f"\n[CortexCICD] Starting application on http://localhost:{port} (host={host}, debug={debug})\n")
    app.run(host=host, port=port, debug=debug)

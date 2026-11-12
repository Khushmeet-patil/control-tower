"""Start the Control Tower server: `python run.py` → http://localhost:5050"""
import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    # Port 5050 because macOS uses 5000 for AirPlay.
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5050")), debug=app.debug)

"""Start the Flask application for local development or deployment."""

import os

from app import create_app


app = create_app()


if __name__ == "__main__":
    app.run(
        host=os.environ.get("APBD_HOST", "127.0.0.1"),
        port=int(os.environ.get("APBD_PORT", "8000")),
    )

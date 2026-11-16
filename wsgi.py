"""WSGI entry point for production servers (e.g. Gunicorn / uWSGI) and dev."""

from app.app import create_app

application = create_app()
app = application

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)



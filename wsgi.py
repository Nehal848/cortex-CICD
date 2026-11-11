"""WSGI entry point for production servers (e.g. Gunicorn / uWSGI)."""

from app.app import create_app

application = create_app()
app = application


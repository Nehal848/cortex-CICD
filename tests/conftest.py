"""
Shared test fixtures for CortexCICD test suite.
Uses in-memory SQLite so tests never touch cortex.db.
"""
import pytest
from app.app import create_app


import tempfile
import os

_temp_db_fd, _temp_db_path = tempfile.mkstemp(suffix=".db")

_TEST_CONFIG = {
    "TESTING":                    True,
    "SQLALCHEMY_DATABASE_URI":    f"sqlite:///{_temp_db_path}",
    "WTF_CSRF_ENABLED":           False,
    "SECRET_KEY":                 "test-secret",
}


@pytest.fixture(scope="function")
def app():
    """Fresh Flask app per test with cleared DB."""
    application = create_app(test_config=_TEST_CONFIG)
    with application.app_context():
        from app.db import db
        db.drop_all()
        db.create_all()
        yield application


@pytest.fixture(scope="function")
def client(app):
    """Authenticated test client."""
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess["logged_in"] = True
        yield c


@pytest.fixture(scope="function")
def anon_client(app):
    """Unauthenticated test client."""
    with app.test_client() as c:
        yield c

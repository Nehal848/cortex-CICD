#!/usr/bin/env python3
"""
CortexCICD Automated Test Suite Runner
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Discovers and executes all unit and integration test cases across tests/
without requiring external pytest CLI installation.
"""

import importlib
import inspect
import os
import sys
import tempfile
import traceback
import types
from contextlib import contextmanager

workspace = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
tests_dir = os.path.join(workspace, "tests")

if workspace not in sys.path:
    sys.path.insert(0, workspace)
if tests_dir not in sys.path:
    sys.path.insert(0, tests_dir)

os.chdir(workspace)


class MonkeyPatch:
    def __init__(self):
        self._patches = []

    def setattr(self, target, name_or_val=None, val=None, raising=True):
        if val is None:
            path = target
            val = name_or_val
            mod_name, attr = path.rsplit(".", 1)
            mod = importlib.import_module(mod_name)
            target = mod
            name = attr
        else:
            name = name_or_val
        old_val = getattr(target, name, None)
        self._patches.append((target, name, old_val, hasattr(target, name)))
        setattr(target, name, val)

    def undo(self):
        for target, name, old_val, had in reversed(self._patches):
            if had:
                setattr(target, name, old_val)
            else:
                delattr(target, name)


class DummyPytest:
    def fixture(self, *args, **kwargs):
        def decorator(f):
            return f
        if args and callable(args[0]):
            return args[0]
        return decorator

    @contextmanager
    def raises(self, expected_exception):
        class ExcInfo:
            value = None
        info = ExcInfo()
        try:
            yield info
        except expected_exception as e:
            info.value = e
        else:
            raise AssertionError(f"Expected exception {expected_exception} was not raised.")


dummy_pytest = DummyPytest()
sys.modules["pytest"] = dummy_pytest

# Setup tests package in sys.modules
import conftest
tests_pkg = types.ModuleType("tests")
tests_pkg.conftest = conftest
sys.modules["tests"] = tests_pkg
sys.modules["tests.conftest"] = conftest

from app.app import create_app
from app.db import db

_temp_db_fd, _temp_db_path = tempfile.mkstemp(suffix=".db")
_TEST_CONFIG = {
    "TESTING": True,
    "SQLALCHEMY_DATABASE_URI": f"sqlite:///{_temp_db_path}",
    "WTF_CSRF_ENABLED": False,
    "SECRET_KEY": "test-secret",
}

app_instance = create_app(test_config=_TEST_CONFIG)

test_modules = [
    "test_alert_lifecycle",
    "test_api",
    "test_healing",
    "test_health",
    "test_ml",
    "test_notifications",
    "test_pipeline_service",
    "test_realworld",
    "test_security",
    "test_status_poller",
    "test_validation",
    "test_webhooks",
]

results = []

for mod_name in test_modules:
    mod = __import__(mod_name, fromlist=["*"])

    test_funcs = [getattr(mod, f) for f in dir(mod) if f.startswith("test_") and callable(getattr(mod, f))]
    for tf in test_funcs:
        # Reset DB before every test
        with app_instance.app_context():
            db.drop_all()
            db.create_all()

        sig = inspect.signature(tf)
        kwargs = {}
        mp = None
        gen_to_close = None

        if "monkeypatch" in sig.parameters:
            mp = MonkeyPatch()
            kwargs["monkeypatch"] = mp

        if "app" in sig.parameters:
            kwargs["app"] = app_instance

        if "anon_client" in sig.parameters:
            kwargs["anon_client"] = app_instance.test_client()

        if "client" in sig.parameters:
            if hasattr(mod, "client") and callable(getattr(mod, "client")):
                client_func = getattr(mod, "client")
                csig = inspect.signature(client_func)
                ckwargs = {}
                if "app" in csig.parameters:
                    ckwargs["app"] = app_instance
                c_val = client_func(**ckwargs)
                if inspect.isgenerator(c_val):
                    gen_to_close = c_val
                    c = next(c_val)
                else:
                    c = c_val
                kwargs["client"] = c
            else:
                c = app_instance.test_client()
                with c.session_transaction() as sess:
                    sess["logged_in"] = True
                kwargs["client"] = c

        try:
            # Modules with custom client fixture manage their own context
            if hasattr(mod, "client") and callable(getattr(mod, "client")):
                tf(**kwargs)
            else:
                with app_instance.app_context():
                    tf(**kwargs)
            results.append((f"{mod_name}.{tf.__name__}", "PASS", None))
            print(f"PASS: {mod_name}.{tf.__name__}")
        except Exception as e:
            results.append((f"{mod_name}.{tf.__name__}", "FAIL", traceback.format_exc()))
            print(f"FAIL: {mod_name}.{tf.__name__}: {e}")
        finally:
            if gen_to_close:
                try:
                    next(gen_to_close)
                except StopIteration:
                    pass
                except Exception:
                    pass
            if mp:
                mp.undo()

passed = sum(1 for r in results if r[1] == "PASS")
failed = sum(1 for r in results if r[1] == "FAIL")

print(f"\n==============================")
print(f"TOTAL: {len(results)} | PASSED: {passed} | FAILED: {failed}")
print(f"==============================")

if failed > 0:
    print(f"\nTotal failures: {failed}")
    for name, status, tb in results:
        if status == "FAIL":
            print(f"\n--- {name} ---")
            print(tb)
    sys.exit(1)
else:
    print("\nAll tests passed successfully!")
    sys.exit(0)

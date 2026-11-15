"""Database configuration regression checks without importing Django or .env.

Execute only the database-building section of settings.py against fixture
environment values. No application initialization or database driver is used.
Run: python -m unittest tests.test_database_config
"""

import ast
import unittest
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlparse

SETTINGS_PATH = Path(__file__).resolve().parents[1] / "config" / "settings.py"


def database_configuration(values):
    tree = ast.parse(SETTINGS_PATH.read_text(encoding="utf-8-sig"))
    database_nodes = []
    collecting = False
    for node in tree.body:
        targets = (
            {target.id for target in node.targets if isinstance(target, ast.Name)}
            if isinstance(node, ast.Assign)
            else set()
        )
        if "database_url" in targets:
            collecting = True
        if "development_database_name" in targets:
            break
        if collecting:
            database_nodes.append(node)
    if not database_nodes:
        raise AssertionError("Could not find database configuration section")
    namespace = {
        "env": lambda key, default="": values.get(key, default),
        "urlparse": urlparse,
        "unquote": unquote,
        "parse_qsl": parse_qsl,
        "VERCEL_URL": values.get("VERCEL_URL", ""),
    }
    module = ast.Module(body=database_nodes, type_ignores=[])
    exec(compile(module, str(SETTINGS_PATH), "exec"), namespace)
    return namespace["DATABASES"]["default"]


class DatabaseConfigurationTests(unittest.TestCase):
    def test_url_connection_is_not_persistent_on_local_asgi(self):
        config = database_configuration({"DATABASE_URL": "postgresql://fixture:unused@db.invalid/rentals"})
        self.assertEqual(config["CONN_MAX_AGE"], 0)
        self.assertEqual(config["OPTIONS"]["connect_timeout"], 5)
        self.assertEqual(config["HOST"], "db.invalid")

    def test_url_query_options_and_explicit_timeout_are_preserved(self):
        config = database_configuration({
            "DATABASE_URL": (
                "postgresql://fixture:unused@db.invalid/rentals"
                "?sslmode=require&connect_timeout=12&application_name=fire-monitor"
                "&options=-c%20statement_timeout%3D3000"
            )
        })
        self.assertEqual(config["CONN_MAX_AGE"], 0)
        self.assertEqual(config["OPTIONS"], {
            "sslmode": "require",
            "connect_timeout": "12",
            "application_name": "fire-monitor",
            "options": "-c statement_timeout=3000",
        })

    def test_timeout_default_does_not_remove_other_url_options(self):
        config = database_configuration({
            "DATABASE_URL": "postgresql://fixture:unused@db.invalid/rentals?sslmode=require"
        })
        self.assertEqual(config["OPTIONS"], {"sslmode": "require", "connect_timeout": 5})

    def test_fallback_connection_is_not_persistent_and_has_timeout(self):
        config = database_configuration({
            "POSTGRES_DB": "fixture_db",
            "POSTGRES_USER": "fixture_user",
            "POSTGRES_PASSWORD": "unused_fixture",
            "POSTGRES_HOST": "fixture.invalid",
            "POSTGRES_PORT": "6543",
        })
        self.assertEqual(config["CONN_MAX_AGE"], 0)
        self.assertEqual(config["OPTIONS"], {"connect_timeout": 5})
        self.assertEqual((config["NAME"], config["USER"], config["HOST"], config["PORT"]),
                         ("fixture_db", "fixture_user", "fixture.invalid", "6543"))

    def test_hosted_deployment_also_has_no_persistent_connection(self):
        config = database_configuration({
            "DATABASE_URL": "postgresql://fixture:unused@db.invalid/rentals",
            "VERCEL_URL": "fixture.invalid",
        })
        self.assertEqual(config["CONN_MAX_AGE"], 0)
        self.assertEqual(config["OPTIONS"]["connect_timeout"], 5)


if __name__ == "__main__":
    unittest.main()

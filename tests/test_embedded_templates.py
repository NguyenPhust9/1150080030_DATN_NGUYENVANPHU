"""Keep the serverless template fallback in sync without loading .env or a DB.

Regenerate with: python scripts/build_embedded_templates.py
"""

import unittest
from pathlib import Path

from django.template import Engine

from apps.rentals.embedded_templates import TEMPLATES

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "apps" / "rentals" / "templates"


class EmbeddedTemplateTests(unittest.TestCase):
    def test_fallback_covers_every_html_template(self):
        expected = {
            path.relative_to(TEMPLATES_DIR).as_posix()
            for path in TEMPLATES_DIR.rglob("*.html")
            if path.is_file()
        }
        self.assertEqual(set(TEMPLATES), expected)

    def test_fallback_matches_source_templates(self):
        for name, content in TEMPLATES.items():
            with self.subTest(template=name):
                self.assertEqual(
                    content,
                    (TEMPLATES_DIR / name).read_text(encoding="utf-8"),
                    "Regenerate using scripts/build_embedded_templates.py",
                )

    def test_fallback_templates_compile_without_filesystem_loader(self):
        engine = Engine(
            loaders=[("django.template.loaders.locmem.Loader", TEMPLATES)],
            libraries={"static": "django.templatetags.static"},
            builtins=["apps.rentals.templatetags.vietnamese"],
        )
        for name in TEMPLATES:
            with self.subTest(template=name):
                engine.get_template(name)


if __name__ == "__main__":
    unittest.main()

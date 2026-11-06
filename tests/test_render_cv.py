#!/usr/bin/env python3
"""Tests for the resume and cover letter renderer.

    python3 -m unittest tests.test_render_cv
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import render_cv


def sample_cv(**overrides):
    data = {
        "type": "cv",
        "name": "Ada Example",
        "contact": ["ada@example.com"],
        "bio": "Staff PM.",
        "work": [{"title": "PM • Acme", "subtitle": "Platform", "bullets": ["Shipped <fast> & well"]}],
    }
    data.update(overrides)
    return data


class RenderCvTests(unittest.TestCase):
    def test_finds_placeholders_in_nested_fields(self):
        data = sample_cv(work=[{"title": "PM", "bullets": ["Led [team size: confirm] people"]}])
        self.assertEqual(render_cv.find_placeholders(data), ["[team size: confirm]"])


    def test_no_placeholders_in_clean_draft(self):
        self.assertEqual(render_cv.find_placeholders(sample_cv()), [])


    def test_escapes_html_and_highlights_placeholders(self):
        output = render_cv.render_html(sample_cv(bio="Built [confirm] <b>"))
        self.assertIn("<mark>[confirm]</mark>", output)
        self.assertIn("&lt;b&gt;", output)
        self.assertIn("Shipped &lt;fast&gt; &amp; well", output)


    def test_optional_sections_are_left_out(self):
        output = render_cv.render_html(sample_cv())
        self.assertNotIn("0 TO 1 PRODUCTS", output)
        self.assertNotIn("EDUCATION", output)


    def test_renders_cover_letter(self):
        data = {"type": "letter", "name": "Ada Example", "paragraphs": ["Dear team,", "Thanks."]}
        output = render_cv.render_html(data)
        self.assertIn("<p>Dear team,</p>", output)
        self.assertIn("Cover Letter", output)

    def test_final_refuses_placeholders(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "cv.json"
            source.write_text('{"name": "Ada", "bio": "[confirm]"}', encoding="utf-8")
            argv = ["render_cv.py", str(source), "--out", str(Path(folder) / "cv.pdf"), "--final"]
            with mock.patch.object(sys, "argv", argv):
                self.assertEqual(render_cv.main(), 2)
            self.assertFalse((Path(folder) / "cv.html").exists())


if __name__ == "__main__":
    unittest.main()

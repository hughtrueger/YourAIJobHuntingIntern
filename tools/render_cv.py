#!/usr/bin/env python3
"""Render a resume or cover letter from JSON to a single-column PDF.

Usage:
    python3 tools/render_cv.py input.json --out output.pdf [--final]

Without --final, [bracketed placeholders] are highlighted for review.
With --final, rendering stops if any placeholder remains.

Resume JSON:
    {"type": "cv", "name": "...", "contact": ["...", "..."], "bio": "...",
     "work": [{"title": "...", "subtitle": "...", "bullets": ["..."]}],
     "products": [{"name": "...", "description": "..."}],
     "education": ["..."]}

Cover letter JSON:
    {"type": "letter", "name": "...", "contact": ["..."],
     "paragraphs": ["Dear ...", "...", "Many thanks for your consideration,"]}

"products" and "education" are optional.
"""
import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

PLACEHOLDER = re.compile(r"\[[^\]]*\]")

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
]
CHROME_COMMANDS = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome"]

CSS = """
@page { size: A4; margin: 9mm 12mm; }
* { box-sizing: border-box; }
body { margin: 0; font-family: 'Raleway', Helvetica, Arial, sans-serif; color: #111;
       background: #fff; font-size: 8.7pt; line-height: 1.22; }
h1 { font-size: 25pt; font-weight: 700; line-height: 1; margin: 0 0 3px; letter-spacing: .3px; }
.contact { font-size: 8pt; margin-bottom: 5px; }
.bio { font-size: 9.6pt; line-height: 1.28; margin: 0 0 5px; padding-bottom: 6px;
       border-bottom: 1px solid #111; }
h2 { display: inline-block; font-size: 10.5pt; font-weight: 700; letter-spacing: 1px;
     margin: 4px 0 4px; padding: 0 22px 2px 0; border-bottom: 1px solid #111; }
.role { margin-bottom: 5px; break-inside: avoid; }
.role h3 { font-size: 9.6pt; font-weight: 700; margin: 0; letter-spacing: .2px; }
.subtitle { font-size: 8.9pt; margin: 0; }
ul { margin: 1px 0 0; padding-left: 13px; }
li { margin: 0; }
.product { margin-bottom: 3px; break-inside: avoid; }
.product b { font-weight: 700; }
.letter { border-top: 1px solid #111; padding-top: 14px; font-size: 10.5pt; line-height: 1.45; }
.letter p { margin: 0 0 10px; }
mark { background: #fff2a8; }
"""

FONT_LINK = (
    '<link href="https://fonts.googleapis.com/css2?family=Raleway:wght@400;700&display=swap" '
    'rel="stylesheet">'
)


def strings_in(value):
    """Yield every string in a nested JSON value."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings_in(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings_in(item)


def find_placeholders(data):
    return [match for text in strings_in(data) for match in PLACEHOLDER.findall(text)]


def text(value):
    """Escape text for HTML and highlight any placeholders."""
    return PLACEHOLDER.sub(lambda m: f"<mark>{m.group(0)}</mark>", html.escape(value, quote=False))


def header(data):
    return f'<h1>{text(data["name"].upper())}</h1><div class="contact">{text(" · ".join(data.get("contact", [])))}</div>'


def cv_body(data):
    parts = [header(data)]
    if data.get("bio"):
        parts.append(f'<p class="bio">{text(data["bio"])}</p>')
    parts.append("<h2>WORK HISTORY</h2>")
    for role in data.get("work", []):
        bullets = "".join(f"<li>{text(b)}</li>" for b in role.get("bullets", []))
        subtitle = f'<p class="subtitle">{text(role["subtitle"])}</p>' if role.get("subtitle") else ""
        parts.append(f'<div class="role"><h3>{text(role["title"])}</h3>{subtitle}<ul>{bullets}</ul></div>')
    if data.get("products"):
        parts.append("<h2>0 TO 1 PRODUCTS</h2>")
        for product in data["products"]:
            parts.append(f'<div class="product"><b>{text(product["name"])}:</b> {text(product["description"])}</div>')
    if data.get("education"):
        parts.append("<h2>EDUCATION</h2>")
        parts.extend(f"<div>{text(line)}</div>" for line in data["education"])
    return "\n".join(parts)


def letter_body(data):
    paragraphs = "".join(f"<p>{text(p)}</p>" for p in data.get("paragraphs", []))
    return f'{header(data)}<div class="letter">{paragraphs}</div>'


def render_html(data):
    kind = data.get("type", "cv")
    if kind not in ("cv", "letter"):
        raise ValueError(f"Unknown type: {kind}")
    body = cv_body(data) if kind == "cv" else letter_body(data)
    title = html.escape(f'{data["name"]} {"Resume" if kind == "cv" else "Cover Letter"}', quote=False)
    return (
        f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{title}</title>'
        f"{FONT_LINK}<style>{CSS}</style></head><body>{body}</body></html>"
    )


def find_chrome():
    configured = os.environ.get("CHROME_PATH")
    if configured and Path(configured).exists():
        return configured
    for path in CHROME_CANDIDATES:
        if Path(path).exists():
            return path
    for command in CHROME_COMMANDS:
        found = shutil.which(command)
        if found:
            return found
    return None


def page_count(pdf_path):
    return len(re.findall(rb"/Type\s*/Page[^s]", pdf_path.read_bytes()))


def print_to_pdf(chrome, html_path, pdf_path):
    subprocess.run(
        [
            chrome,
            "--headless",
            "--disable-gpu",
            "--no-pdf-header-footer",
            "--virtual-time-budget=8000",
            f"--print-to-pdf={pdf_path}",
            html_path.resolve().as_uri(),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=60,
    )


def main():
    parser = argparse.ArgumentParser(description="Render a resume or cover letter to PDF.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--final", action="store_true", help="fail if any [placeholder] remains")
    args = parser.parse_args()

    data = json.loads(args.input.read_text(encoding="utf-8"))
    placeholders = find_placeholders(data)
    if args.final and placeholders:
        print("Not rendered. Resolve these placeholders first:", file=sys.stderr)
        for placeholder in placeholders:
            print(f"  {placeholder}", file=sys.stderr)
        return 2

    html_path = args.out.with_suffix(".html")
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(render_html(data), encoding="utf-8")

    chrome = find_chrome()
    if not chrome:
        print(f"Chrome not found. Open {html_path} in a browser and print it to PDF.")
        return 0
    print_to_pdf(chrome, html_path, args.out.resolve())
    pages = page_count(args.out)
    note = f", {len(placeholders)} placeholders highlighted" if placeholders else ""
    print(f"Wrote {args.out} ({pages} page{'s' if pages != 1 else ''}{note})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

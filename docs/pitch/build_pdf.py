"""
Render pitch.md (with Mermaid diagrams) to InsightDesk_Pitch.pdf using headless Chrome.

Usage:
    python docs/pitch/build_pdf.py

Requires Chrome (or Edge) and internet access for the marked Mermaid CDN scripts.
"""

import json
import pathlib
import shutil
import subprocess
import sys


BASE_DIR = pathlib.Path(__file__).resolve().parent

SOURCE_MD = BASE_DIR / "pitch.md"
OUTPUT_HTML = BASE_DIR / "pitch.html"
OUTPUT_PDF = BASE_DIR / "InsightDesk_Pitch.pdf"

BROWSERS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "google-chrome",
    "chromium",
    "chrome",
    "msedge",
]


HTML_TEMPLATE = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>InsightDesk Pitch</title>

<style>
    @page {
        size: A4;
        margin: 14mm 14mm 16mm;
    }

    body {
        font-family: "Segoe UI", Arial, sans-serif;
        font-size: 10.5pt;
        color: #111827;
        line-height: 1.45;
    }

    .cover {
        height: 250mm;
        display: flex;
        flex-direction: column;
        justify-content: center;
    }

    .cover .kicker {
        color: #4f46e5;
        font-weight: 600;
        letter-spacing: .04em;
        text-transform: uppercase;
        font-size: 10pt;
    }

    .cover h1 {
        font-size: 30pt;
        line-height: 1.15;
        margin: 8px 0 14px;
    }

    .cover .tagline {
        font-size: 14pt;
        color: #374151;
        max-width: 150mm;
    }

    .cover .byline {
        margin-top: 28px;
        color: #6b7280;
    }

    h2 {
        break-before: page;
        font-size: 18pt;
        border-bottom: 3px solid #4f46e5;
        padding-bottom: 4px;
        margin-top: 0;
    }

    h3 {
        font-size: 12.5pt;
        margin-top: 18px;
    }

    table {
        border-collapse: collapse;
        width: 100%;
        margin: 10px 0 14px;
        font-size: 9pt;
        break-inside: auto;
    }

    tr {
        break-inside: avoid;
    }

    th {
        background: #eef2ff;
        text-align: left;
    }

    th,
    td {
        border: 1px solid #d1d5db;
        padding: 5px 7px;
        vertical-align: top;
    }

    code {
        background: #f1f5f9;
        padding: 1px 4px;
        border-radius: 3px;
        font-size: 9pt;
    }

    pre {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 6px;
        padding: 10px;
        white-space: pre-wrap;
        font-size: 8.3pt;
        break-inside: avoid;
    }

    pre code {
        background: none;
        padding: 0;
    }

    blockquote {
        border-left: 4px solid #4f46e5;
        margin: 10px 0;
        padding: 6px 14px;
        background: #f5f7ff;
        color: #1f2937;
    }

    .mermaid {
        text-align: center;
        margin: 12px 0 16px;
        break-inside: avoid;
    }

    .mermaid svg {
        max-width: 100% !important;
        height: auto;
        max-height: 225mm;
    }
</style>

<script src="https://cdn.jsdelivr.net/npm/marked@12.0.2/marked.min.js"></script>

</head>

<body data-status="loading">

<div id="content"></div>

<script type="module">

import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.esm.min.mjs";

const MD = __MARKDOWN__;
const root = document.getElementById("content");

root.innerHTML = marked.parse(MD);

// Cover page: title, byline and the closing tagline.
const h1 = root.querySelector("h1");
const byline = h1.nextElementSibling;

const cover = document.createElement("section");
cover.className = "cover";

cover.innerHTML =
    '<div class="kicker">HCLTech Future Ready AI Engineer Hackathon · Use case 2</div>';

cover.appendChild(h1);

const tagline = document.createElement("div");
tagline.className = "tagline";
tagline.textContent =
    "A correct, cited answer in seconds, or the right human with the whole story. Never a confident guess.";

cover.appendChild(tagline);

byline.className = "byline";
cover.appendChild(byline);

root.prepend(cover);

// Turn ```mermaid blocks into diagrams.
document.querySelectorAll("pre > code.language-mermaid").forEach(code => {
    const diagram = document.createElement("div");

    diagram.className = "mermaid";
    diagram.textContent = code.textContent;

    code.parentElement.replaceWith(diagram);
});

mermaid.initialize({
    startOnLoad: false,
    securityLevel: "loose",
    theme: "base",

    themeVariables: {
        fontFamily: "Segoe UI, Arial, sans-serif",
        fontSize: "14px",
        primaryColor: "#eef2ff",
        primaryBorderColor: "#6366f1",
        primaryTextColor: "#111827",
        lineColor: "#64748b",
        secondaryColor: "#f1f5f9",
        tertiaryColor: "#ffffff",
        clusterBkg: "#f8fafc",
        clusterBorder: "#cbd5e1"
    },

    flowchart: {
        htmlLabels: true,
        curve: "basis"
    }
});

const errors = [];

for (const diagram of document.querySelectorAll(".mermaid")) {
    try {
        await mermaid.parse(diagram.textContent);
    } catch (error) {
        errors.push(
            String(error.message || error).slice(0, 200)
        );
    }
}

try {
    await mermaid.run({
        querySelector: ".mermaid"
    });
} catch (error) {
    errors.push(
        String(error.message || error).slice(0, 200)
    );
}

document.body.dataset.status =
    errors.length
        ? "error: " + errors.join(" | ")
        : "ok";

</script>

</body>
</html>
"""


def find_browser():
    """Find an installed Chrome or Edge executable."""

    for browser in BROWSERS:
        if pathlib.Path(browser).exists() or shutil.which(browser):
            return browser

    sys.exit("No Chrome or Edge found.")


def main():
    markdown = SOURCE_MD.read_text(encoding="utf-8")

    # json.dumps creates a safe JavaScript string.
    # Breaking </ prevents the Markdown from closing the script tag.
    safe_markdown = json.dumps(markdown).replace("</", "<\\/")

    OUTPUT_HTML.write_text(
        HTML_TEMPLATE.replace("__MARKDOWN__", safe_markdown),
        encoding="utf-8"
    )

    browser = find_browser()

    common_args = [
        browser,
        "--headless=new",
        "--disable-gpu",
        "--virtual-time-budget=60000",
        "--run-all-compositor-stages-before-draw"
    ]

    html_url = OUTPUT_HTML.as_uri()

    dom_output = subprocess.run(
        common_args + [
            "--dump-dom",
            html_url
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=180
    ).stdout

    status = (
        dom_output.split('data-status="', 1)[1].split('"', 1)[0]
        if 'data-status="' in dom_output
        else "unknown"
    )

    print("render status:", status)

    if status != "ok":
        sys.exit(
            "Fix the Mermaid errors above before printing."
        )

    subprocess.run(
        common_args + [
            "--no-pdf-header-footer",
            f"--print-to-pdf={OUTPUT_PDF}",
            html_url
        ],
        check=True,
        capture_output=True,
        timeout=180
    )

    print("wrote", OUTPUT_PDF)


if __name__ == "__main__":
    main()
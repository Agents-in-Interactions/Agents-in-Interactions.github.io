"""Extract title and authors from CVPR openaccess paper PDFs.

Usage:
    python3 tools/extract_papers.py tools/papers_2026.txt tools/papers_2026.json

Input file: one openaccess HTML URL per line (blank lines ignored).
For each URL, the matching PDF is downloaded (replacing /html/ -> /papers/ and
.html -> .pdf), and title + authors are extracted by font-size clustering on
page 1.

Output JSON schema:
    [
      {"title": str, "authors": [str, ...], "html_url": str, "pdf_url": str},
      ...
    ]
"""

import io
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import pdfplumber


def html_to_pdf_url(html_url: str) -> str:
    return html_url.replace("/html/", "/papers/").replace(".html", ".pdf")


def fetch(url: str) -> bytes:
    # Use curl to side-step Python's stricter SSL trust store (works under
    # corporate MITM proxies that ship their own root cert via the system
    # keychain).
    out = subprocess.run(
        ["curl", "-sSL", "--fail", "-A", "Mozilla/5.0", url],
        capture_output=True,
        check=True,
    )
    return out.stdout


def _group_words_into_lines(words: list[dict], y_tol: float = 3.0) -> list[list[dict]]:
    lines: list[list[dict]] = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        placed = False
        for line in lines:
            if abs(line[0]["top"] - w["top"]) <= y_tol:
                line.append(w)
                placed = True
                break
        if not placed:
            lines.append([w])
    for line in lines:
        line.sort(key=lambda w: w["x0"])
    lines.sort(key=lambda line: line[0]["top"])
    return lines


def _line_max_size(line: list[dict]) -> float:
    return max(w["size"] for w in line)


SUPER_CHARS = set("0123456789*†‡§¶∗⋆⋄(),.;:")


def _is_superscript(word: dict, body_size: float) -> bool:
    """Heuristic: superscript markers are notably smaller than body and
    contain only digits/punctuation/symbol characters."""
    if word["size"] < body_size - 0.5:
        return True
    text = word["text"].replace("(cid:66)", "")
    return bool(text) and all(c in SUPER_CHARS for c in text)


def _split_authors_by_gaps(line: list[dict]) -> list[str]:
    """Split an author line into name tokens by horizontal gaps.

    Strategy: estimate the inter-word baseline gap (small) vs inter-author
    gap (large). Words separated by a "big" gap become a new author. A
    second pass strips superscript-style tokens that pdfplumber emitted as
    separate words (digits, asterisks, daggers).
    """
    if not line:
        return []
    body_size = max(w["size"] for w in line)
    gaps = [b["x0"] - a["x1"] for a, b in zip(line, line[1:])]
    if not gaps:
        return [line[0]["text"]]

    sorted_gaps = sorted(gaps)
    median = sorted_gaps[len(sorted_gaps) // 2]
    threshold = max(median * 2.0, median + 3.0, 5.0)

    groups: list[list[dict]] = [[line[0]]]
    for i, gap in enumerate(gaps):
        next_w = line[i + 1]
        if gap > threshold:
            groups.append([next_w])
        else:
            groups[-1].append(next_w)

    authors: list[str] = []
    for group in groups:
        kept = [w["text"] for w in group if not _is_superscript(w, body_size)]
        name = " ".join(kept).strip()
        if name:
            authors.append(name)
    return authors


def _clean_author(name: str) -> str:
    # Strip superscript-style trailing/leading markers.
    name = name.strip()
    # Remove parenthetical email refs etc.
    # Common CVPR markers: digits, *, †, ‡, §, ¶, ∗, ⋆, ⋄, (cid:..)
    while name and name[-1] in "0123456789*†‡§¶∗⋆⋄,.;:":
        name = name[:-1].rstrip()
    while name and name[0] in "0123456789*†‡§¶∗⋆⋄,.;:":
        name = name[1:].lstrip()
    # Drop "(cid:NN)" tokens that pdfplumber emits for glyphs it can't map.
    parts = [p for p in name.split() if not p.startswith("(cid:")]
    return " ".join(parts).strip()


def extract_title_and_authors(pdf_bytes: bytes) -> tuple[str, list[str]]:
    """Use font-size clustering on page 1.

    Largest font => title. Next-largest contiguous font block under title
    (before any affiliation/abstract marker) => authors.
    """
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        page = pdf.pages[0]
        # x_tolerance=1.0 keeps normal inter-word spaces as word boundaries
        # (default 3.0 merges them, gluing first/last names together).
        words = page.extract_words(
            extra_attrs=["size"], use_text_flow=False, x_tolerance=1.0
        )
        if not words:
            raise RuntimeError("no words on page 1")

        # Coerce sizes to float (pdfplumber returns Decimal).
        for w in words:
            w["size"] = float(w["size"])

        lines = _group_words_into_lines(words)

        max_size = max(_line_max_size(line) for line in lines)

        # Title: consecutive lines from the top whose max-size matches the
        # page-max. Skip non-title preamble (e.g. page header) by walking
        # until we find the first title line.
        i = 0
        while i < len(lines) and abs(_line_max_size(lines[i]) - max_size) > 0.5:
            i += 1
        title_parts: list[str] = []
        while i < len(lines) and abs(_line_max_size(lines[i]) - max_size) <= 0.5:
            title_parts.append(" ".join(w["text"] for w in lines[i]))
            i += 1
        title = " ".join(title_parts).strip()

        # Author block: next contiguous lines whose font size is uniform
        # and smaller than the title, until we hit an affiliation marker.
        affil_markers = (
            "@", "Abstract", "University", "Institute", "Laboratory",
            "College", "School", "Corporation", "Research",
            "ETH", "MIT", "Stanford", "Berkeley", "CMU", "Tsinghua",
            "Peking", "Shanghai", "Beijing", "Microsoft", "Google",
            "NVIDIA", "Meta", "Apple", "Amazon", "Adobe",
        )
        authors: list[str] = []
        # Skip blank gap if the line immediately after the title is much
        # smaller (likely the author line). We allow up to 4 author lines.
        author_lines: list[list[dict]] = []
        while i < len(lines) and len(author_lines) < 4:
            line = lines[i]
            text = " ".join(w["text"] for w in line)
            if any(m in text for m in affil_markers):
                break
            # Stop if size drops a lot (likely already into affiliations/body).
            if author_lines:
                prev_size = _line_max_size(author_lines[-1])
                if _line_max_size(line) < prev_size - 1.0:
                    break
            author_lines.append(line)
            i += 1

        for line in author_lines:
            for name in _split_authors_by_gaps(line):
                cleaned = _clean_author(name)
                if cleaned and cleaned not in authors:
                    authors.append(cleaned)

        return title, authors


def main(in_path: str, out_path: str) -> None:
    urls = [
        ln.strip()
        for ln in Path(in_path).read_text().splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    results = []
    for html_url in urls:
        pdf_url = html_to_pdf_url(html_url)
        print(f"fetching {pdf_url}", file=sys.stderr)
        pdf_bytes = fetch(pdf_url)
        title, authors = extract_title_and_authors(pdf_bytes)
        results.append({
            "title": title,
            "authors": authors,
            "html_url": html_url,
            "pdf_url": pdf_url,
        })
        print(f"  title:   {title}", file=sys.stderr)
        print(f"  authors: {authors}", file=sys.stderr)

    Path(out_path).write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"wrote {len(results)} entries to {out_path}", file=sys.stderr)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])

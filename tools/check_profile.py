#!/usr/bin/env python3
"""Validate the profile README (Amz34/Amz34).

The profile README is the most-visited page of the account, so two classes of
defect cost the most: a link that 404s for visitors (for example a link to a
private repository) and a broken local image. This checker catches both.

Offline mode (default) is deterministic and runs in CI:

  * every referenced local asset exists in the working tree;
  * every link uses https (or mailto);
  * every github.com/Amz34/<repo> link is listed in tools/public_repos.txt,
    the committed manifest of repositories that are public right now, so a
    private repository can never be featured again;
  * the featured table keeps three columns per row and does not list a
    repository twice;
  * no placeholders and no unterminated code fence.

Live mode (--live) additionally asks the GitHub API whether each Amz34
repository in the manifest is still public, and fetches every external URL.

Exit codes: 0 = pass, 1 = problems found, 2 = input could not be read.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

OWNER = "Amz34"
LINK_RE = re.compile(r"\[[^\]]*\]\(\s*<?([^)\s>]+)>?\s*\)")
AUTOLINK_RE = re.compile(r"<(https?://[^>\s]+)>")
IMG_SRC_RE = re.compile(r"<img[^>]+src=[\"']([^\"']+)[\"']", re.IGNORECASE)
IMAGE_EXT_RE = re.compile(r"\.(?:png|jpe?g|gif|svg|webp|avif)$", re.IGNORECASE)
AMZ_REPO_RE = re.compile(r"^https?://github\.com/" + OWNER + r"/([A-Za-z0-9_.-]+)", re.IGNORECASE)
PLACEHOLDERS = ("TODO", "TBD", "FIXME", "XXX", "lorem ipsum")
USER_AGENT = "Amz34-profile-check/1.0"


class InputError(Exception):
    """Raised when the target README cannot be read."""


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:  # unreadable target is not a pass
        raise InputError(f"cannot read {path}: {exc}") from exc


def extract_links(text: str) -> list[str]:
    """Return markdown and autolink targets, in document order."""
    links = LINK_RE.findall(text)
    links += AUTOLINK_RE.findall(text)
    links += IMG_SRC_RE.findall(text)
    return links


def is_remote(url: str) -> bool:
    return url.startswith("http://") or url.startswith("https://")


def load_manifest(path: Path) -> set[str]:
    """Load the allowlist as lower-case owner/name entries.

    Bare names are expanded with the account owner, so a manifest written as
    one repository per line keeps working.
    """
    if not path.exists():
        return set()
    names = set()
    for line in read_text(path).splitlines():
        line = line.strip().lower()
        if not line or line.startswith("#"):
            continue
        names.add(line if "/" in line else f"{OWNER.lower()}/{line}")
    return names


def check(text: str, root: Path, manifest: set[str]) -> list[str]:
    problems: list[str] = []

    for url in extract_links(text):
        if is_remote(url):
            if url.startswith("http://"):
                problems.append(f"insecure http link: {url}")
            continue
        if url.startswith(("mailto:", "#")):
            continue
        clean = url.split("#", 1)[0].split("?", 1)[0]
        if (root / clean).exists():
            continue
        if IMAGE_EXT_RE.search(clean):
            problems.append(f"missing local asset referenced by the README: {clean}")
        else:
            problems.append(f"link points to no local file and is not https: {url}")

    seen: list[str] = []
    for url in extract_links(text):
        match = AMZ_REPO_RE.match(url)
        if not match:
            continue
        repo = match.group(1)
        name = f"{OWNER}/{repo}".lower()
        if name not in manifest:
            problems.append(
                f"link to unlisted {OWNER} repository (private or renamed?): {OWNER}/{repo}"
            )
        if name in seen:
            problems.append(f"repository linked twice in the README: {OWNER}/{repo}")
        seen.append(name)

    for marker in PLACEHOLDERS:
        if marker.lower() in text.lower():
            problems.append(f"placeholder text left in the README: {marker}")

    if text.count("```") % 2:
        problems.append("unbalanced code fence (```) in the README")

    for line in text.splitlines():
        if line.startswith("| [") and "|" in line:
            cells = [c for c in line.strip().strip("|").split("|")]
            if len(cells) != 3:
                problems.append(f"featured-table row does not have 3 columns: {line[:60]}...")

    if len(text) < 800:
        problems.append(f"README looks truncated ({len(text)} characters)")

    return problems


def live_problems(manifest: set[str]) -> list[str]:
    """Ask the GitHub API whether every manifest repository is still public."""
    problems: list[str] = []
    for full in sorted(manifest):
        result = subprocess.run(
            ["gh", "api", f"repos/{full}", "--jq", ".visibility"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            problems.append(f"live check failed for {full}: {result.stderr.strip()[:120]}")
            continue
        visibility = result.stdout.strip()
        if visibility != "public":
            problems.append(f"{full} is not public (visibility={visibility or 'unknown'})")
    return problems


def external_problems(text: str) -> list[str]:
    """Fetch every non-GitHub external URL and report a non-2xx/3xx status."""
    problems: list[str] = []
    for url in extract_links(text):
        if not is_remote(url) or "github.com/" in url:
            continue
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                status = getattr(response, "status", 200)
        except urllib.error.HTTPError as exc:
            status = exc.code
        except Exception as exc:  # network problems are reported, never ignored
            problems.append(f"could not fetch {url}: {exc.__class__.__name__}")
            continue
        if status >= 400 and status != 999:  # LinkedIn answers 999 to non-browsers
            problems.append(f"external link returned HTTP {status}: {url}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the Amz34 profile README.")
    parser.add_argument("readme", nargs="?", default="README.md")
    parser.add_argument("--manifest", default="tools/public_repos.txt")
    parser.add_argument("--live", action="store_true", help="also query the GitHub API and external URLs")
    args = parser.parse_args(argv)

    readme_path = Path(args.readme)
    root = readme_path.parent if readme_path.parent != Path("") else Path(".")
    manifest_path = Path(args.manifest) if Path(args.manifest).is_absolute() else root / args.manifest

    try:
        text = read_text(readme_path)
        manifest = load_manifest(manifest_path)
    except InputError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if not manifest:
        print(f"ERROR: empty repository manifest at {manifest_path}", file=sys.stderr)
        return 2

    problems = check(text, root, manifest)
    if args.live:
        problems += live_problems(manifest)
        problems += external_problems(text)

    links = extract_links(text)
    amz = {m.group(1).lower() for m in (AMZ_REPO_RE.match(u) for u in links) if m}
    if problems:
        for problem in problems:
            print(f"FAIL: {problem}")
        print(f"\n{len(problems)} problem(s) found.")
        return 1

    print(f"PASS: {len(links)} links, {len(amz)} {OWNER} repositories, {len(manifest)} in the public manifest.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

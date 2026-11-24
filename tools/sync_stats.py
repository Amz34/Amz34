#!/usr/bin/env python3
"""Sync Amz34/Amz34 stats SVG and public repository manifest from live GitHub API."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

OWNER = "Amz34"

STATS_SVG_TEMPLATE = """<svg width="495" height="195" viewBox="0 0 495 195" fill="none" xmlns="http://www.w3.org/2000/svg">
  <style>
    .header {{ font: 600 18px 'Segoe UI', Ubuntu, Sans-Serif; fill: #70A5FD; }}
    .stat {{ font: 600 14px 'Segoe UI', Ubuntu, Sans-Serif; fill: #C8D3F5; }}
    .label {{ font: 400 14px 'Segoe UI', Ubuntu, Sans-Serif; fill: #828BB8; }}
    .bold {{ font-weight: 700; }}
  </style>
  <rect x="0.5" y="0.5" rx="8" width="494" height="194" fill="#16161e" stroke="#222436"/>
  <text x="30" y="38" class="header">Aamir Zameer ({owner}) Stats</text>
  
  <g transform="translate(30, 65)">
    <circle cx="6" cy="6" r="4" fill="#C53B53" />
    <text x="25" y="10" class="label">Total Stars Earned:</text>
    <text x="210" y="10" class="stat bold">{stars}</text>
  </g>
  <g transform="translate(30, 95)">
    <circle cx="6" cy="6" r="4" fill="#FFC777" />
    <text x="25" y="10" class="label">Contributions (365d):</text>
    <text x="210" y="10" class="stat bold">{contributions:,}</text>
  </g>
  <g transform="translate(30, 125)">
    <circle cx="6" cy="6" r="4" fill="#4FD6BE" />
    <text x="25" y="10" class="label">Total Public Repos:</text>
    <text x="210" y="10" class="stat bold">{public_repos}</text>
  </g>
  <g transform="translate(30, 155)">
    <circle cx="6" cy="6" r="4" fill="#82AAFF" />
    <text x="25" y="10" class="label">Enterprise Grade:</text>
    <text x="210" y="10" class="stat bold" fill="#4FD6BE">A+ (SRE Certified)</text>
  </g>
</svg>
"""


def render_stats_svg(stars: int, contributions: int, public_repos: int, owner: str = OWNER) -> str:
    """Render the self-hosted TokyoNight GitHub stats SVG."""
    return STATS_SVG_TEMPLATE.format(
        owner=owner,
        stars=stars,
        contributions=contributions,
        public_repos=public_repos,
    )


def fetch_live_metrics(owner: str = OWNER) -> tuple[int, int, int, list[str]]:
    """Query GitHub CLI for public stars, 365d contributions, public repo count, and sorted repo names."""
    repos_raw = subprocess.check_output(
        ["gh", "repo", "list", owner, "--limit", "500", "--json", "name,visibility,stargazerCount"],
        text=True,
    )
    repos = json.loads(repos_raw)
    public = [r for r in repos if r.get("visibility") == "PUBLIC"]
    stars = sum(int(r.get("stargazerCount", 0)) for r in public)
    names = sorted(r["name"] for r in public)

    query = (
        f'{{ user(login: "{owner}") {{ contributionsCollection {{ '
        f"contributionCalendar {{ totalContributions }} }} }} }}"
    )
    gql_raw = subprocess.check_output(["gh", "api", "graphql", "-f", f"query={query}"], text=True)
    gql = json.loads(gql_raw)
    contributions = int(gql["data"]["user"]["contributionsCollection"]["contributionCalendar"]["totalContributions"])
    return stars, contributions, len(names), names


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    stars, contributions, public_repos, names = fetch_live_metrics()
    (root / "assets" / "github-stats.svg").write_text(
        render_stats_svg(stars, contributions, public_repos),
        encoding="utf-8",
    )
    (root / "tools" / "public_repos.txt").write_text("\n".join(names) + "\n", encoding="utf-8")
    print(f"Synced: stars={stars}, contributions={contributions}, public_repos={public_repos}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

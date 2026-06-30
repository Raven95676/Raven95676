#!/usr/bin/env python3
"""Update the exclude_repo lists in README.md for github-stats-extended images.

Only repos where Raven95676 has commits are kept; all others (plus a fixed blacklist)
are added to exclude_repo.
"""

import json
import os
import re
import sys
import urllib.request
import urllib.error

USERNAME = "Raven95676"

BLACKLIST = {
    "astrbot_prompts_collection",
    "ravenote",
    "virus-bar_u_faq",
    "home",
    "raven95676.github.io",
    "AstrBot_Plugins_Collection",
    "AstrBot-docs",
    "AstrBot",
    "cpython",
}

TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("PAT") or ""
BASE = "https://api.github.com"


def _headers():
    h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if TOKEN:
        h["Authorization"] = f"Bearer {TOKEN}"
    return h


def _get_json(url):
    """GET a JSON endpoint, respecting pagination (list endpoints only)."""
    results = []
    page = 1
    while True:
        sep = "&" if "?" in url else "?"
        full = f"{url}{sep}per_page=100&page={page}"
        req = urllib.request.Request(full, headers=_headers())
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            print(f"  HTTP {e.code} for {url}")
            break
        except Exception as e:
            print(f"  Error for {url}: {e}")
            break

        if isinstance(data, list):
            results.extend(data)
            if len(data) < 100:
                break
        else:
            results.append(data)
            break
        page += 1
    return results


def get_owned_repos():
    """Return list of repo objects owned by the user."""
    print("Fetching owned repos...")
    return _get_json(f"{BASE}/users/{USERNAME}/repos?type=owner")


def get_org_repos():
    """Return list of repo objects from orgs the user belongs to."""
    print("Fetching orgs...")
    orgs = _get_json(f"{BASE}/users/{USERNAME}/orgs")
    repos = []
    for org in orgs:
        name = org["login"]
        print(f"  Fetching repos for org: {name}")
        repos.extend(_get_json(f"{BASE}/orgs/{name}/repos?type=all"))
    return repos


def has_commits(full_name):
    """Return True if USERNAME has at least one commit in this repo."""
    url = f"{BASE}/repos/{full_name}/commits?author={USERNAME}&per_page=1"
    data = _get_json(url)
    return len(data) > 0 if isinstance(data, list) else bool(data)


def main():
    owned = get_owned_repos()
    if not owned:
        print("ERROR: Failed to fetch owned repos (rate limited or network error). Aborting.")
        sys.exit(1)

    org_repos = get_org_repos()

    # Deduplicate by full_name
    all_repos = {}
    for r in owned + org_repos:
        fn = r["full_name"]
        if fn not in all_repos:
            all_repos[fn] = r["name"]

    print(f"\nTotal unique repos: {len(all_repos)}")

    # Owned repos (Raven95676/*) always count as having commits.
    # Only org repos need to be checked.
    owned_names = {r["name"] for r in owned if r["name"] not in BLACKLIST}
    org_candidates = [(fn, n) for fn, n in all_repos.items() if n not in BLACKLIST and fn not in [r["full_name"] for r in owned]]

    repos_with_commits = set(owned_names)
    print(f"\nOwned repos (auto-included): {len(owned_names)}")

    for i, (full_name, name) in enumerate(org_candidates, 1):
        print(f"[{i}/{len(org_candidates)}] {full_name} ...", end=" ", flush=True)
        if has_commits(full_name):
            repos_with_commits.add(name)
            print("[OK] has commits")
        else:
            print("[--] no commits")

    # Exclude = repos without commits + blacklist
    all_names = {n for _, n in all_repos.items()}
    exclude = sorted(all_names - repos_with_commits | BLACKLIST)
    exclude_str = ",".join(exclude)

    print(f"\nExcluding {len(exclude)} repos:")
    for n in exclude:
        marker = " [BLACKLIST]" if n in BLACKLIST else ""
        print(f"  - {n}{marker}")

    # Update README.md
    readme_path = os.path.join(
        os.environ.get("GITHUB_WORKSPACE", "."), "README.md"
    )
    with open(readme_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Match both URL forms: /api?... and /api/top-langs/?...
    # Group 1: everything up to and including "exclude_repo="
    # Group 2: the old value (non-&, non-quote, non-whitespace)
    pattern = re.compile(
        r"(https://github-stats-extended\.vercel\.app/api[^\"'\s]*?[&?]exclude_repo=)"
        r"([^&\s\"']*)"
    )

    new_content = pattern.sub(rf"\g<1>{exclude_str}", content)

    if new_content != content:
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        print("\nREADME.md updated.")
    else:
        print("\nNo changes needed.")

    # Signal whether the workflow should push a commit
    output_file = os.environ.get("GITHUB_OUTPUT")
    if output_file:
        with open(output_file, "a") as f:
            f.write(f'changed={"true" if new_content != content else "false"}\n')


if __name__ == "__main__":
    main()

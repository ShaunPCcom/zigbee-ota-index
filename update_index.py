#!/usr/bin/env python3
"""
Zigbee OTA Index Aggregator

Fetches z2m/ota_index.json from configured device repositories and combines
them into OTA index files for Zigbee2MQTT.

Produces two indexes:
  - ota_index.json      : stable releases only (from default branches)
  - ota_index_beta.json : stable + beta releases (highest version wins)

Usage:
    python3 update_index.py repos.yaml ota_index.json
"""

import sys
import json
import yaml
import urllib.request
import urllib.error
from typing import List, Dict, Any, Optional, Tuple


def fetch_branch_index(user: str, repo: str, branch: str) -> Optional[List[Dict[str, Any]]]:
    """Fetch z2m/ota_index.json from a specific branch. Returns None on 404."""
    raw_url = f"https://raw.githubusercontent.com/{user}/{repo}/{branch}/z2m/ota_index.json"

    try:
        print(f"  Fetching from {branch} branch: {raw_url}")
        with urllib.request.urlopen(raw_url, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))

            if not isinstance(data, list):
                print(f"  ⚠ OTA index must be an array, got {type(data)}")
                return None

            print(f"  ✓ Found {len(data)} entries on {branch}")
            return data

    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        print(f"  ✗ HTTP error {e.code} fetching {raw_url}: {e.reason}")
        return None
    except urllib.error.URLError as e:
        print(f"  ✗ Network error fetching {raw_url}: {e.reason}")
        return None


def fetch_repo_index(repo_url: str) -> List[Dict[str, Any]]:
    """Fetch z2m/ota_index.json from a repo's default branch (master or main)."""
    if not repo_url.startswith("https://github.com/"):
        raise ValueError(f"Invalid GitHub URL: {repo_url}")

    parts = repo_url.replace("https://github.com/", "").strip("/").split("/")
    if len(parts) != 2:
        raise ValueError(f"Invalid GitHub repo format: {repo_url}")

    user, repo = parts

    for branch in ["master", "main"]:
        data = fetch_branch_index(user, repo, branch)
        if data is not None:
            return data

    raise Exception(f"Could not find z2m/ota_index.json in {repo_url} (tried master and main)")


def fetch_beta_index(repo_url: str, beta_branch: str) -> List[Dict[str, Any]]:
    """Fetch z2m/ota_index.json from a repo's beta branch."""
    if not repo_url.startswith("https://github.com/"):
        raise ValueError(f"Invalid GitHub URL: {repo_url}")

    parts = repo_url.replace("https://github.com/", "").strip("/").split("/")
    user, repo = parts

    data = fetch_branch_index(user, repo, beta_branch)
    if data is not None:
        return data

    print(f"  ℹ No beta index on {beta_branch} branch (not yet published)")
    return []


def add_entries(entries: List[Dict[str, Any]], seen: Dict[Tuple, Dict], label: str):
    """Add entries to a seen dict, keeping highest fileVersion per device."""
    for entry in entries:
        required_fields = ["manufacturerCode", "imageType", "fileVersion", "url"]
        missing = [f for f in required_fields if f not in entry]
        if missing:
            print(f"  ⚠ Skipping entry missing fields: {missing}")
            continue

        mc = entry["manufacturerCode"]
        it = entry["imageType"]
        fv = entry["fileVersion"]
        device_key = (mc, it)

        if device_key in seen:
            existing_version = seen[device_key]["fileVersion"]
            if fv > existing_version:
                print(f"  ℹ [{label}] Replacing (mfr={mc}, type={it}): v{existing_version} -> v{fv}")
                seen[device_key] = entry
            else:
                print(f"  ℹ [{label}] Keeping existing (mfr={mc}, type={it}): v{existing_version} >= v{fv}")
        else:
            print(f"  ✓ [{label}] Added: mfr={mc}, type={it}, version={fv}")
            seen[device_key] = entry


def write_index(entries: Dict[Tuple, Dict], output_file: str, label: str):
    """Write a sorted OTA index to a JSON file."""
    combined = sorted(entries.values(), key=lambda e: (e["manufacturerCode"], e["imageType"]))

    with open(output_file, 'w') as f:
        json.dump(combined, f, indent=2)

    print(f"\n✓ Wrote {label} index ({len(combined)} entries) to: {output_file}")

    for entry in combined:
        filename = entry["url"].split("/")[-1]
        print(f"  - Manufacturer {entry['manufacturerCode']}, "
              f"Type {entry['imageType']}, "
              f"Version {entry['fileVersion']} ({filename})")


def main():
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <repos.yaml> <output.json>")
        sys.exit(1)

    repos_file = sys.argv[1]
    output_file = sys.argv[2]
    beta_output = output_file.replace(".json", "_beta.json")

    print(f"Reading repository list from: {repos_file}")

    try:
        with open(repos_file, 'r') as f:
            config = yaml.safe_load(f)

        raw_repos = config.get("repositories", [])
        if not raw_repos:
            print("Warning: No repositories configured")
            sys.exit(0)

        # Normalize repos — support both string and dict formats
        repos = []
        for r in raw_repos:
            if isinstance(r, str):
                repos.append({"url": r, "beta_branch": None})
            elif isinstance(r, dict):
                repos.append({"url": r["url"], "beta_branch": r.get("beta_branch")})

        print(f"Found {len(repos)} configured repositories")

        # Collect stable entries
        stable_seen = {}
        for repo in repos:
            print(f"\nProcessing (stable): {repo['url']}")
            try:
                entries = fetch_repo_index(repo["url"])
                add_entries(entries, stable_seen, "stable")
            except Exception as e:
                print(f"  ✗ Error: {e}")

        # Beta index starts with all stable entries, then overlays beta
        beta_seen = dict(stable_seen)
        has_beta = False

        for repo in repos:
            if not repo["beta_branch"]:
                continue
            has_beta = True
            print(f"\nProcessing (beta): {repo['url']} [{repo['beta_branch']}]")
            try:
                entries = fetch_beta_index(repo["url"], repo["beta_branch"])
                add_entries(entries, beta_seen, "beta")
            except Exception as e:
                print(f"  ✗ Error: {e}")

        # Write outputs
        print(f"\n{'='*60}")
        write_index(stable_seen, output_file, "stable")

        if has_beta:
            write_index(beta_seen, beta_output, "beta")
        else:
            print("\nNo beta branches configured — skipping beta index")

        print(f"\n{'='*60}")
        print("Done!")

    except FileNotFoundError:
        print(f"Error: File not found: {repos_file}")
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"Error parsing YAML: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

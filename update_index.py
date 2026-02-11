#!/usr/bin/env python3
"""
Zigbee OTA Index Aggregator

Fetches z2m/ota_index.json from configured device repositories and combines
them into a single OTA index file for Zigbee2MQTT.

Usage:
    python3 update_index.py repos.yaml ota_index.json
"""

import sys
import json
import yaml
import urllib.request
import urllib.error
from typing import List, Dict, Any

def fetch_repo_index(repo_url: str) -> List[Dict[str, Any]]:
    """
    Fetch z2m/ota_index.json from a GitHub repository's default branch.

    Args:
        repo_url: GitHub repository URL (e.g., https://github.com/user/repo)

    Returns:
        List of OTA index entries (typically one entry per repo)

    Raises:
        Exception: If fetch fails or JSON is invalid
    """
    # Convert GitHub URL to raw content URL
    # https://github.com/user/repo -> https://raw.githubusercontent.com/user/repo/master/z2m/ota_index.json
    if not repo_url.startswith("https://github.com/"):
        raise ValueError(f"Invalid GitHub URL: {repo_url}")

    parts = repo_url.replace("https://github.com/", "").strip("/").split("/")
    if len(parts) != 2:
        raise ValueError(f"Invalid GitHub repo format: {repo_url}")

    user, repo = parts

    # Try master first, then main
    for branch in ["master", "main"]:
        raw_url = f"https://raw.githubusercontent.com/{user}/{repo}/{branch}/z2m/ota_index.json"

        try:
            print(f"  Fetching from {branch} branch: {raw_url}")
            with urllib.request.urlopen(raw_url, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))

                if not isinstance(data, list):
                    raise ValueError(f"OTA index must be an array, got {type(data)}")

                print(f"  ✓ Found {len(data)} entries")
                return data

        except urllib.error.HTTPError as e:
            if e.code == 404:
                # Try next branch
                continue
            raise Exception(f"HTTP error {e.code} fetching {raw_url}: {e.reason}")
        except urllib.error.URLError as e:
            raise Exception(f"Network error fetching {raw_url}: {e.reason}")

    raise Exception(f"Could not find z2m/ota_index.json in {repo_url} (tried master and main branches)")

def combine_indexes(repos: List[str]) -> List[Dict[str, Any]]:
    """
    Fetch and combine OTA indexes from all configured repositories.

    Args:
        repos: List of GitHub repository URLs

    Returns:
        Combined list of OTA index entries, deduplicated by (manufacturerCode, imageType)
    """
    all_entries = []
    seen_devices = {}  # Key: (manufacturerCode, imageType), Value: entry

    for repo_url in repos:
        print(f"\nProcessing: {repo_url}")

        try:
            entries = fetch_repo_index(repo_url)

            for entry in entries:
                # Validate required fields
                required_fields = ["manufacturerCode", "imageType", "fileVersion", "url"]
                missing = [f for f in required_fields if f not in entry]
                if missing:
                    print(f"  ⚠ Skipping entry missing fields: {missing}")
                    continue

                mc = entry["manufacturerCode"]
                it = entry["imageType"]
                fv = entry["fileVersion"]

                device_key = (mc, it)

                # Check if we already have an entry for this device
                if device_key in seen_devices:
                    existing = seen_devices[device_key]
                    existing_version = existing["fileVersion"]

                    # Keep the entry with higher fileVersion
                    if fv > existing_version:
                        print(f"  ℹ Replacing entry (mfr={mc}, type={it}): v{existing_version} -> v{fv}")
                        seen_devices[device_key] = entry
                    else:
                        print(f"  ℹ Keeping existing entry (mfr={mc}, type={it}): v{existing_version} >= v{fv}")
                else:
                    print(f"  ✓ Added entry: mfr={mc}, type={it}, version={fv}")
                    seen_devices[device_key] = entry

        except Exception as e:
            print(f"  ✗ Error processing {repo_url}: {e}")
            # Continue with other repos even if one fails
            continue

    # Convert back to list, sorted by (manufacturerCode, imageType)
    combined = sorted(seen_devices.values(), key=lambda e: (e["manufacturerCode"], e["imageType"]))

    return combined

def main():
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <repos.yaml> <output.json>")
        sys.exit(1)

    repos_file = sys.argv[1]
    output_file = sys.argv[2]

    print(f"Reading repository list from: {repos_file}")

    try:
        with open(repos_file, 'r') as f:
            config = yaml.safe_load(f)

        repos = config.get("repositories", [])

        if not repos:
            print("Warning: No repositories configured")
            sys.exit(0)

        print(f"Found {len(repos)} configured repositories")

        combined = combine_indexes(repos)

        print(f"\n{'='*60}")
        print(f"Combined OTA index: {len(combined)} total entries")
        print(f"{'='*60}")

        # Write combined index
        with open(output_file, 'w') as f:
            json.dump(combined, f, indent=2)

        print(f"\n✓ Wrote combined index to: {output_file}")

        # Print summary
        print("\nDevices in combined index:")
        for entry in combined:
            mc = entry["manufacturerCode"]
            it = entry["imageType"]
            fv = entry["fileVersion"]
            url = entry["url"]
            filename = url.split("/")[-1]
            print(f"  - Manufacturer {mc}, Type {it}, Version {fv} ({filename})")

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

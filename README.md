# Zigbee OTA Index Aggregator

[![Update OTA Index](https://github.com/ShaunPCcom/zigbee-ota-index/actions/workflows/update-index.yml/badge.svg)](https://github.com/ShaunPCcom/zigbee-ota-index/actions/workflows/update-index.yml)

**Automated OTA index aggregator for custom Zigbee devices.** Combines firmware updates from multiple device repositories into a single Zigbee2MQTT-compatible OTA index.

## Overview

This repository monitors configured Zigbee device repositories and automatically generates a combined `ota_index.json` file that Zigbee2MQTT (Z2M) can use to provide OTA firmware updates for custom devices.

**How it works:**
1. Each device repository maintains its own `z2m/ota_index.json` (single entry for that device)
2. This repo's scheduled workflow fetches all configured device indexes
3. Combines them into one master index, deduplicating by manufacturer/image type
4. Publishes to GitHub Pages for Z2M to access

**Users get automatic update notifications** in Home Assistant when new firmware is released for any configured device.

## Quick Start

### For End Users (Using This Index)

Configure Zigbee2MQTT to use this OTA index:

```yaml
# configuration.yaml (Z2M)
ota:
  zigbee_ota_override_index_location: https://shaunpccom.github.io/zigbee-ota-index/ota_index.json
```

Restart Z2M, and your custom devices will automatically receive update notifications when new firmware is released.

### For Device Developers (Adding Your Device)

To add your custom Zigbee device to this index:

1. **Fork this repository**

2. **Edit `repos.yaml`** and add your device repo:
   ```yaml
   repositories:
     - https://github.com/ShaunPCcom/ESP32-H2-LD2450
     - https://github.com/YourUsername/your-zigbee-device  # Add your repo here
   ```

3. **Ensure your repo has `z2m/ota_index.json`** in the default branch:
   ```json
   [
     {
       "manufacturerCode": 4891,
       "imageType": 1,
       "fileVersion": 65536,
       "url": "https://github.com/YourUsername/your-zigbee-device/releases/download/v1.0.0.0/firmware.ota"
     }
   ]
   ```

4. **Submit a pull request** or deploy your own fork

Your device's firmware updates will now be included in the combined index. When you release new firmware, this repo's hourly workflow will automatically pick it up.

## How It Works

### Architecture

```
Device Repos (yours + others)
  ├─ z2m/ota_index.json (single entry)
  └─ Releases with .ota files

         ↓ (fetched hourly)

zigbee-ota-index (this repo)
  ├─ repos.yaml (list of device repos)
  ├─ update_index.py (aggregator script)
  └─ Workflow → gh-pages branch

         ↓ (served via GitHub Pages)

Zigbee2MQTT
  └─ Downloads ota_index.json
  └─ Notifies users of updates
```

### Update Frequency

- **Automatic**: Runs every hour via GitHub Actions cron
- **Manual**: Can be triggered from Actions tab
- **On config change**: Runs when `repos.yaml` is updated

### Deduplication

If multiple repos have entries for the same device (same `manufacturerCode` and `imageType`), the entry with the **highest `fileVersion`** is kept.

## Configuration

### repos.yaml

Simple list of GitHub repository URLs:

```yaml
repositories:
  - https://github.com/ShaunPCcom/ESP32-H2-LD2450
  - https://github.com/ShaunPCcom/zigbee-LED-ESP32-controller
  - https://github.com/YourOrg/your-device
```

**Requirements for listed repos:**
- Must be public GitHub repositories (or accessible with appropriate credentials)
- Must have `z2m/ota_index.json` in `master` or `main` branch
- OTA index must be valid JSON array with required fields

### Device OTA Index Format

Each device's `z2m/ota_index.json` must be a JSON array (typically with one entry):

```json
[
  {
    "manufacturerCode": 4891,      // Zigbee manufacturer ID
    "imageType": 1,                // Application-specific image type
    "fileVersion": 65536,          // Numeric firmware version
    "url": "https://..."           // Direct download URL for .ota file
  }
]
```

**Field descriptions:**
- `manufacturerCode`: Zigbee manufacturer code (e.g., 4891 = 0x131B for Espressif)
- `imageType`: Application-specific identifier (must be unique per manufacturer)
- `fileVersion`: Numeric version (e.g., v1.0.0.0 = 0x00010000 = 65536)
- `url`: Direct download URL for the `.ota` firmware file

## Device Repository Setup

For device repositories to work with this aggregator, they should:

1. **Maintain `z2m/ota_index.json`** in the repo root
2. **Use automated releases** (GitHub Actions recommended)
3. **Update the OTA index** when releasing new firmware
4. **Follow version conventions** (semantic versioning)

### Example: Automated Device Release Workflow

Device repos can use GitHub Actions to automate releases:

```yaml
# .github/workflows/release-on-tag.yml (simplified)
on:
  push:
    tags: ['v*.*.*.*']

jobs:
  release:
    steps:
      - name: Build firmware
        run: idf.py build

      - name: Create OTA image
        run: # ... create Zigbee OTA format image

      - name: Create GitHub Release
        run: gh release create $TAG firmware.ota

      - name: Update OTA index
        run: |
          cat > z2m/ota_index.json <<EOF
          [{
            "manufacturerCode": 4891,
            "imageType": 1,
            "fileVersion": $VERSION_NUM,
            "url": "https://github.com/$REPO/releases/download/$TAG/firmware.ota"
          }]
          EOF
          git commit -am "chore: update OTA index for $TAG"
          git push
```

See [ESP32-H2-LD2450](https://github.com/ShaunPCcom/ESP32-H2-LD2450) for a complete reference implementation.

## Running Locally

Test the aggregator script locally:

```bash
# Install dependencies
pip install pyyaml

# Run aggregator
python3 update_index.py repos.yaml ota_index.json

# View generated index
cat ota_index.json
```

## Deployment

This repository uses GitHub Pages to serve the combined OTA index:

1. Workflow runs and generates `ota_index.json`
2. File is committed to `gh-pages` branch
3. GitHub Pages serves it at: `https://shaunpccom.github.io/zigbee-ota-index/ota_index.json`

**No manual deployment needed** - everything is automated via GitHub Actions.

## Troubleshooting

### Device Not Appearing in Combined Index

1. **Check the Actions tab** for workflow runs and errors
2. **Verify your repo's `z2m/ota_index.json`** is valid JSON and in the default branch
3. **Check required fields** are present (manufacturerCode, imageType, fileVersion, url)
4. **Wait for next hourly run** or manually trigger workflow

### Z2M Not Detecting Updates

1. **Verify Z2M configuration** points to the correct URL
2. **Restart Z2M** after changing ota configuration
3. **Check device firmware version** is lower than index version
4. **Trigger manual update check** in Z2M UI (About tab)

### Conflicts Between Repos

If multiple repos have the same `(manufacturerCode, imageType)`:
- The entry with **highest `fileVersion`** is kept
- This is by design (latest version wins)
- If unintended, use different `imageType` values for different devices

## Community Use

This repository is designed to be **forkable and reusable**:

1. Fork this repo
2. Edit `repos.yaml` with your own device repos
3. Enable GitHub Pages in your fork settings
4. Point your Z2M to your fork's GitHub Pages URL

You can run your own index with any combination of device repositories - mix public devices with your private ones as needed.

## Contributing

Contributions welcome! To add a device to the public index:

1. Ensure your device repo follows the structure above
2. Fork this repo
3. Add your repo URL to `repos.yaml`
4. Submit a pull request

Please ensure your device:
- Uses unique `(manufacturerCode, imageType)` combination
- Has working automated releases
- Provides stable `.ota` download URLs

## License

MIT License - See LICENSE file for details

## Related Projects

- [ESP32-H2-LD2450](https://github.com/ShaunPCcom/ESP32-H2-LD2450) - Reference device implementation
- [esp32-zigbee-ota](https://github.com/ShaunPCcom/esp32-zigbee-ota) - Reusable OTA component for ESP32-H2/C6
- [Zigbee2MQTT](https://www.zigbee2mqtt.io/) - Zigbee to MQTT bridge

## Support

For issues with:
- **This aggregator**: Open an issue in this repo
- **A specific device**: Open an issue in that device's repo
- **Z2M integration**: See [Zigbee2MQTT docs](https://www.zigbee2mqtt.io/guide/usage/ota_updates.html)

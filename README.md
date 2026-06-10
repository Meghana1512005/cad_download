# CAD Model Auto-Downloader

Downloads free GLB models from Sketchfab for all platforms in the military equipment register.

## Setup (one-time, 5 minutes)

1. **Add your Sketchfab token as a secret**
   - Go to repo → Settings → Secrets and variables → Actions → New repository secret
   - Name: `SKETCHFAB_TOKEN`
   - Value: `7ca059dbec904c6da9985c82faa2ca44`

2. **Create the release tag** (so downloads have somewhere to go)
   - Go to Releases → Create a new release → Tag: `models-latest` → Publish

That's it — the workflows are ready to run.

## How to run

### Step 1: Search for models on Sketchfab
Go to **Actions → 1 - Search Sketchfab for Models → Run workflow**

- Searches 100 models per run
- For all 5,416 models run it 55 times (or let the hourly schedule handle it)
- Updates `data/models.json` with Sketchfab IDs

### Step 2: Download found models
Go to **Actions → 2 - Download GLB Models → Run workflow**

- Downloads 20 models per run (keeps within GitHub Actions limits)
- Files are uploaded to the **Releases** page as assets
- Status in `data/models.json` is updated to "Downloaded"

## Downloading your files
All GLB files appear under **Releases → Downloaded CAD Models**.
You can download them individually or use the release ZIP.

## Files
- `data/models.json` — master list with download status for all 5,416 models
- `downloaded_models/` — GLB files (uploaded to Releases, not stored in Git)
- `scripts/search_sketchfab.py` — Sketchfab search script
- `scripts/download_glb.py` — GLB download script

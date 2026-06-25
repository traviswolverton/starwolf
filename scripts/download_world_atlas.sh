#!/usr/bin/env bash
# Downloads and extracts the World Atlas of Artificial Night Sky Brightness
# (Falchi et al. 2016) GeoTIFF used for Bortle class lookups.
#
# The file is ~2.9 GB and only needs to be downloaded once.
# Target: /opt/stargazing-app/data/World_Atlas_2015.tif

set -euo pipefail

DATA_DIR="/opt/stargazing-app/data"
TIF_PATH="$DATA_DIR/World_Atlas_2015.tif"
ZIP_PATH="$DATA_DIR/world_atlas.zip"
DOI_URL="https://datapub.gfz-potsdam.de/download/10.5880.GFZ.1.4.2016.001"

mkdir -p "$DATA_DIR"

if [ -f "$TIF_PATH" ]; then
    echo "GeoTIFF already present at $TIF_PATH — nothing to do."
    exit 0
fi

echo "Downloading World Atlas zip (~2.9 GB)…"
curl -L --progress-bar -o "$ZIP_PATH" "$DOI_URL"

echo "Extracting World_Atlas_2015.tif…"
unzip -j "$ZIP_PATH" "*.tif" -d "$DATA_DIR"

# The extracted file may be named slightly differently — normalise it
extracted=$(find "$DATA_DIR" -maxdepth 1 -name "*.tif" | head -1)
if [ "$extracted" != "$TIF_PATH" ] && [ -n "$extracted" ]; then
    mv "$extracted" "$TIF_PATH"
fi

rm -f "$ZIP_PATH"

echo "Done. GeoTIFF at $TIF_PATH ($(du -sh "$TIF_PATH" | cut -f1))."

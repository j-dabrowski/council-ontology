#!/usr/bin/env bash
# Download WA Local Government Area boundaries as GeoJSON.
# Source: Australian Bureau of Statistics ASGS Edition 3 (2021) via ArcGIS REST.
# Output: frontend/public/data/wa_lga.geojson
#
# The LGA name field in the result is LGA_NAME_2021.
# Run from the repo root: bash scripts/download_wa_lga.sh

set -euo pipefail

OUT="frontend/public/data/wa_lga.geojson"

echo "Downloading WA LGA boundaries from ABS ASGS 2021..."

# WA state code = 5 in the ABS ASGS.
# resultRecordCount=-1 requests all features (no server-side pagination).
curl -fsSL \
  "https://geo.abs.gov.au/arcgis/rest/services/ASGS2021/LGA/FeatureServer/0/query?where=STATE_CODE_2021%3D'5'&outFields=LGA_CODE_2021%2CLGA_NAME_2021&f=geojson&returnGeometry=true&geometryPrecision=4&resultRecordCount=-1" \
  -o "$OUT"

echo "Saved to $OUT"
echo "Feature count: $(python3 -c "import json,sys; d=json.load(open('$OUT')); print(len(d['features']))" 2>/dev/null || echo '(install python3 to count)')"

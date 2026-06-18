#!/bin/bash
# Vendor Three.js r128 locally so /viewer/3d slipper bero på CDN.
set -euo pipefail
cd "$(dirname "$0")"
curl -fL -o three.min.js https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js
echo "✅ three.min.js sparad i $(pwd)"
ls -la three.min.js

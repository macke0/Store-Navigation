# static/

Lokala JS/CSS-resurser som serveras under `/static/` av FastAPI.

## Vendor Three.js (rekommenderat)

Kör på servern (där backenden körs):

```bash
cd ~/ICA_ai/BackendPulsAr/static
curl -L -o three.min.js https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js
```

`/viewer/3d` försöker först ladda `/static/three.min.js`. Om filen saknas
faller den tillbaka till CDN automatiskt — men det blir snabbare/mer
robust om filen är vendored lokalt.

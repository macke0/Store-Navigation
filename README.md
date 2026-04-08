# ICA_ai (Puls-AR)

AI-driven app som hjalper kunder hitta produkter i matbutiker.

## Struktur

```
ICA_ai/
├── BackendPulsAr/   # Python FastAPI backend (Qwen VL + CLIP + SQLite)
├── iOSApp/          # Swift/SwiftUI iOS-app
└── README.md
```

## Backend

- **FastAPI** server med produktdatabas, sokning och VPS
- **Qwen2.5-VL-32B** for produktigenkanning fran hyllbilder
- **CLIP** for visuell matchning mot produktdatabasen
- **SQLite** for lokal datalagring

## iOS App

AR-baserad kundapp for att navigera i butiken och hitta produkter.

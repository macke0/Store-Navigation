# PulsAr

**AR-powered in-store navigation that helps shoppers find products — like Google Maps, but inside the grocery store.**

Customers ask an AI assistant for shopping help, get a shopping list, tap *"Find in store"* on an item, and follow a live augmented-reality route straight to the shelf.

---

## The problem

Shoppers can't find what they're looking for. They give up, ask staff, or leave without buying.
That's a worse experience for the customer and lost sales for the store. PulsAr closes that gap by
turning any phone into an in-store guide.

## What it does

- **AR navigation** — Localize the shopper inside a 3D model of the store and draw a walking route to any product, rendered live through the camera with ARKit.
- **AI shopping assistant** — A Claude-powered assistant answers questions ("where's the oat milk?", "what's on sale?"), builds shopping lists, and surfaces active campaigns. Each item gets a *"Find in store"* button.
- **Recipe inspiration** — Search free-text ("high-protein dinners using this week's deals") and get real, rated recipes with real photos, per-portion nutrition, live prices, and total cost — every ingredient mapped to a real product you can navigate to.
- **Store mapping (staff mode)** — Staff walk the store with an iPhone; LiDAR + photogrammetry build the 3D map and place products on it.

## How it works

```
                 iOS app (SwiftUI · ARKit · RealityKit)
                              │  HTTP / JSON
                              ▼
            FastAPI backend  (Python, on VPS)
   ┌──────────────┬─────────────────┬────────────────────┐
   │  3D mapping  │   Navigation    │   AI / search       │
   │  & product   │   A* over an    │   Claude assistant, │
   │  localization│   occupancy     │   recipe engine,    │
   │  (point      │   grid →        │   fuzzy product     │
   │  clouds)     │   waypoints     │   search            │
   └──────────────┴─────────────────┴────────────────────┘
                              │
                ICA product catalog + campaigns + recipes
```

**Two modes:**

| Mode | Who | What |
|------|-----|------|
| **Store scanning** | Staff | Build the 3D map from LiDAR mesh and locate products on it. Uses the server continuously. |
| **Product finding** | Customers | Localize once against the map via the server, then track position with ARKit on-device. |

**Customer flow:** AI assistant → shopping list → tap *"Find in store"* → one-shot localization → 3D map with a live route to the shelf.

## Tech stack

- **iOS** — Swift / SwiftUI, ARKit + RealityKit, LiDAR scanning.
- **Backend** — Python, FastAPI, NumPy. A* pathfinding over an occupancy grid. 3D point-cloud localization (with optional COLMAP bundle adjustment).
- **AI** — Anthropic Claude (shopping assistant, recipe parsing), Qwen2.5-VL for in-store product recognition, fuzzy catalog search.
- **Data** — Scraped ICA product catalog (~18k products with live prices & campaigns) and ~23k real ICA recipes with nutrition and photos.

## Repository layout

```
ICA_ai/
├── BackendPulsAr/          FastAPI backend
│   ├── server.py           App entry point + route registration
│   ├── vps_endpoints.py    Mapping / localization / navigation endpoints
│   ├── chat_endpoints.py   Assistant + recipe endpoints
│   ├── core/               Mapping, navigation, AI assistant, recipe & search engines
│   ├── scraper/            ICA catalog + recipe scrapers
│   └── data/               Store models, catalog, recipes
└── iOSApp/                 SwiftUI + ARKit client
```

## Status

Active development. The backend mapping, navigation, AI assistant, recipe inspiration, and
campaign-aware search are working. The customer AR navigation flow and a frictionless QR / App Clip
entry point are the current focus.

## Vision

PulsAr is built to be sold to stores as an API: drop in the assistant, map the store once, and give
every shopper a guided, deal-aware path through the aisles.

# PulsAr — find where you are, and where things are, inside a store

**Send one photo and the system tells you where you are in a mapped room. Film the aisles and it works out where each product sits on the map. Search the catalogue with fuzzy matching or Claude.**

PulsAr is a prototype for in-store navigation. The idea is a "Google Maps for the grocery store": a shopper asks for something, and the app knows where it is and where *they* are. It is **unfinished but partly working**. The localization and product-mapping pipelines are real code, and the AR route display is the missing piece (see [Status](#status)).

```
 iPhone (SwiftUI · ARKit · LiDAR)                    Backend (Python · FastAPI)
┌───────────────────────────────┐   frames + depth   ┌──────────────────────────────────┐
│ scan mode:  walk and film     │ ─────────────────▶ │ 1. Visual localization (VPS)     │
│ find mode:  send a photo      │ ◀───────────────── │ 2. Product → map position        │
│ ARKit tracks motion in between│   pose / positions │ 3. Search: fuzzy  or  Claude     │
└───────────────────────────────┘                    │ 4. Occupancy grid + A* routing   │
                                                     └──────────────────────────────────┘
```

## 1. Where am I? Localization from a single image

Send a photo and get back a metric 6-DoF camera pose in the store map. This is a small visual positioning system ([`core/vps_3d.py`](BackendPulsAr/core/vps_3d.py)).

**Building the map.** Staff walk the store with a LiDAR iPhone. For every frame the backend extracts SuperPoint keypoints and lifts them to 3D by back-projecting the LiDAR depth map into ARKit world space. The keypoints and their 3D positions are stored. Two FAISS indexes are built, one over per-frame descriptors and one over all 3D-point descriptors. Because the 3D points come from LiDAR, **the map is in metres and needs no scale estimation.**

**Localizing a query image**, coarse to fine:

1. Extract SuperPoint features from the query (rejected below 20 keypoints).
2. **Retrieve** the 8 most similar map frames with FAISS.
3. **Match** the query against each candidate with LightGlue. Matches whose map keypoint has a 3D point become 2D–3D correspondences, pooled across all good frames.
4. **Solve** `solvePnPRansac` (EPnP, 12 px threshold, 2,000 iterations). The result is rejected below 8 inliers.
5. **Report confidence** (high / medium / low) from the inlier count and inlier ratio.

**Connecting the phone to the map.** The photo pose is turned into a transform between ARKit's world frame and the map frame. That transform is constrained to a **pure yaw rotation**: PnP pitch and roll noise otherwise made products "sink through the floor". After one fix, ARKit tracks motion on the device and the app re-localizes in the background every few seconds, blending the correction in over half a second.

Other pieces: multi-session map merging by RANSAC and Umeyama rigid alignment on 3D–3D matches ([`multi_session.py`](BackendPulsAr/core/multi_session.py)), and a loop-closure drift correction for scans that end near their start ([`loop_closure.py`](BackendPulsAr/core/loop_closure.py)).

## 2. Where is that product? Film a room, get product positions

Walk through the store filming shelves. The app sends a frame every 0.5 s with the camera pose, intrinsics and up to 600 LiDAR points. The backend ([`produkt_skanning.py`](BackendPulsAr/core/produkt_skanning.py)):

1. **Reads the shelf labels.** A vision-language model (Qwen2.5-VL) returns the product name and bounding box of each label in the frame. It is hosted through OpenRouter or run locally on a GPU with vLLM.
2. **Gets depth from LiDAR.** The LiDAR points are projected into the image. The median depth of the points inside the box gives the label's distance, which needs at least 3 points.
3. **Back-projects to 3D.** The box centre becomes a point in ARKit world space, then in map coordinates through the localization transform. Yaw comes from the map alignment and translation is anchored at the camera, so relative placement keeps ARKit's local precision.
4. **Matches to the catalogue.** The name goes through the fuzzy product search below. Observations are scored as high, medium or low confidence.
5. **Consolidates across frames.** The same product seen from many frames is merged by greedy spatial clustering (1.5 m). Only the best-scored observations in each cluster are kept and averaged into one position.

The result is a product → (x, y, z) table on the store map, built just by filming.

## 3. Finding products: fuzzy search or Claude

There are two search paths over an 18,107-product catalogue.

**Fuzzy search** ([`produkt_sok.py`](BackendPulsAr/core/produkt_sok.py)). A custom word-level scorer, written for Swedish:
- Understands Swedish inflections (*tomat* → *tomater* scores 0.95, while *mjöl* → *mjölk* scores only 0.6).
- Handles compound words by suffix, containment and coverage.
- Ranks with category-aware boosts and penalties, so "mjölk" returns milk before coconut milk or milk-free alternatives.
- Runs on the phone, too ([`LokalProdukt.swift`](iOSApp/LokalProdukt.swift)), so results appear instantly.

**Claude** ([`smart_sok.py`](BackendPulsAr/core/smart_sok.py)). For queries like "something for a Friday evening" or typos the fuzzy scorer cannot rescue:
- A cheap local prefilter (word matches, synonyms, concept groups) narrows the catalogue to 50 candidates.
- Claude Haiku picks the best IDs from `id | name | category` lines and returns IDs only.
- Answers are cached on disk, so a repeated query costs nothing.

The iPhone app shows the local fuzzy results first, then replaces them with the Claude-ranked list a moment later.

There is also a **shopping assistant** ([`claude_assistant.py`](BackendPulsAr/core/claude_assistant.py)): Claude Sonnet with a manual tool-use loop and five tools (product search, details, similar products, healthier alternatives, and product position on the map), so an answer can end in "it's in aisle 4, here's where".

## 4. Routing

[`navigation.py`](BackendPulsAr/core/navigation.py) turns the map's point cloud into a 2D occupancy grid (0.1 m cells, obstacles between 0.3 m and 2 m above the floor, dilated by 0.35 m so the path keeps clear of shelves). It runs 8-connected A* with line-of-sight path simplification. Start and goal snap into the main walkable region, so a point inside a shelf does not fail the search.

## Status

| | |
|---|---|
| **Implemented** | SuperPoint + LightGlue + PnP localization, LiDAR-lifted maps, map merging, label reading and product back-projection, multi-frame consolidation, fuzzy and Claude search, the Sonnet assistant, occupancy grid and A* backend, iOS scan and find flows, a 3D map viewer. |
| **Not finished** | The **AR route display**. The app shows a direction arrow and distance, but is not yet wired to the A* route. |
| **Not measured** | Localization accuracy. The design target is roughly 5–15 cm, but there is no evaluation and the repo has no map data to run one. The app has a test view that measures hit rate and error on known positions. |
| **Known rough edges** | No automated tests, no dependency file, paths and a server address hardcoded to the author's machine, and a bundle-adjustment step with a known bug. |

This is a prototype built to find out whether the idea works, and it taught me where the hard parts are: coordinate frames (ARKit vs OpenCV axes, and drift in pitch and roll) and keeping product positions consistent across a long walk.

## Stack

- **iOS:** Swift, SwiftUI, ARKit (LiDAR scene depth, mesh anchors), RealityKit and SceneKit. About 9,300 lines.
- **Backend:** Python, FastAPI, NumPy, OpenCV, PyTorch, LightGlue / SuperPoint, FAISS, pycolmap, SciPy. About 17,800 lines.
- **AI:** Anthropic Claude (Haiku for search, Sonnet for the assistant), Qwen2.5-VL for label reading.

```
BackendPulsAr/
  server.py, run_server.py     FastAPI app
  core/vps_3d.py               map building + localization
  core/produkt_skanning.py     film → product positions
  core/produkt_sok.py          fuzzy search
  core/smart_sok.py            Claude search
  core/claude_assistant.py     tool-using assistant
  core/navigation.py           occupancy grid + A*
iOSApp/                        SwiftUI + ARKit client
```

The server needs `ANTHROPIC_API_KEY` and `OPENROUTER_KEY` in the environment. It is not packaged for a one-command run yet.

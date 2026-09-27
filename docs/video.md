# Relay — demo video script (YouTube, ~2:45)

The recorded version of the pitch in `docs/demo.md`. Same pair, same numbers (see
`docs/demo.md` → **Figures**, which a test recomputes from the data — if a number there
changes, change it here too). Shots on the left, voiceover on the right.

**Target length:** 2:45 (hard cap 3:00). **Voice:** calm, one idea per sentence.

## Before you record

- [ ] **Merge `test-branch-1` into `main`** (after `/test-gate full`) and wait for the
      auto-deploy. The live site only shows the tier chips and tier-first ranks after that.
- [ ] Open **https://relaygrid.us** and re-check: 39 pairs, pair #3 is Jasper – Okatie ↔
      McIntosh – Purrysburg, total $4,242,766. If a rank moved, update the script.
- [ ] **Dark theme**, map on **Dark** basemap, sidebar closed, no uploads in this browser.
- [ ] Browser window **1920×1080**, zoom 100%, bookmarks bar and extensions hidden, a clean
      profile (no personal tabs). Turn on cursor highlighting if your recorder has it.
- [ ] Do one silent dry run of the clicks. Record voice separately if you can — it's easier
      to fix one sentence than to re-record the screen.

## Script

| # | Time | On screen | Voiceover |
|---|------|-----------|-----------|
| 1 | 0:00–0:15 | **Landing page** (relaygrid.us, the site root): the headline *Plan together. Build once.* over the power-line scene. Hold 2 s, then move to **Try the map →** and click — the map opens at `relaygrid.us/#/map`. | "Neighboring utilities plan their transmission work in isolation. In 2024, FERC issued Order 1920 because of exactly that. Relay puts two utilities' public plans on one map." |
| 2 | 0:15–0:45 | **The map loads**, fitted to the data. Slowly zoom toward the Savannah River border. Open the sidebar with the **☰** button: the ranked list with **% match** and tier chips. | "This is Dominion Energy South Carolina in blue and Georgia Power in red — every project parsed from their own public filings and placed on the map. Relay flags every cross-utility pair within 25 miles. Along this border we found 39 coordination opportunities, ranked here — each one with a match score and a tier: must coordinate, share land, share site logistics, or share crews." |
| 3 | 0:45–1:30 | **Click card #3**, Jasper – Okatie ↔ SAV: McIntosh – Purrysburg. The map flies to the pair; the **detail panel** opens. Hover the numbers as you say them. | "Take number three. Dominion's Jasper – Okatie line and Georgia Power's McIntosh – Purrysburg reactors. At their closest, the lines are just three miles apart, and they go into service only 152 days apart — an 83% match. Built together, they can share laydown yards, deliveries and crews. From Dominion's published cost, sharing mobilization is worth about **$709,579**." |
| 4 | 1:30–1:45 | Briefly click **#1** so the map shows the Thurmond crossing, then back. | "Numbers one and two rank higher because they physically touch at the Thurmond substation — a crossing has to be coordinated whenever each is built, even eight years apart." |
| 5 | 1:45–2:05 | **Sort by** → *Est. savings*, then back to *Score %*. Nudge the **Minimum match** slider up and back. Toggle **Satellite** for 2 s, then back to **Dark**. | "Planners can re-sort by distance, timing or savings, filter to the strongest matches, and check the ground itself on satellite imagery." |
| 6 | 2:05–2:20 | **Zoom out** to the whole region; hold on the **savings headline** in the sidebar. | "Across these two utilities alone: 39 coordination opportunities, worth an estimated **$4.24 million**." |
| 7 | 2:20–2:35 | Quick cuts (1–2 s each): a page of the DESC PDF → the map → the GitHub Actions run going green. *(Optional; stay on the map if you don't have these clips.)* | "Under the hood: real PDFs, substations located with OpenStreetMap, and a 25-mile overlap engine on Tiger Data's Postgres and PostGIS — checked against Sperry's own reference table — deployed on DigitalOcean." |
| 8 | 2:35–2:45 | Browser **Back** to the landing page headline. End card: **relaygrid.us**. | "Relay. **Plan together. Build once.** Next: more utilities and live filing ingestion. Try it at relaygrid.us." |

## Notes for the edit

- **Captions:** add them — many judges watch muted. Put the three key numbers on screen as
  text when they're spoken: **3 mi · 152 days · ≈ $709,579** in scene 3, and
  **39 opportunities · ≈ $4.24M** in scene 6.
- **Don't claim** the Snowflake savings note or uploads-for-everyone — neither is live
  (uploads stay in the viewer's browser).
- If you run long, cut scene 5 first, then scene 7.
- Upload as **Unlisted** on YouTube and put the link where `docs/devpost.md` says
  `[VIDEO: …]`.

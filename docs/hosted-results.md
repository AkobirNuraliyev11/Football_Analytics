# Hosted results explorer

The November 23, 2026 website presents saved research results. It does not run
Python inference, accept cloud video uploads, or establish new model accuracy.

Site: https://football-analytics-results.carefreefudge5.chatgpt.site
Audience: owner-private. Site project ID: appgprj_6b03c27a2f7c8191883e8d5e3911c81d.

## Included evidence

The initial snapshot contains 375 frames, 97 JSON reports, 38 method documents,
11 occupancy heatmaps, 55 experimental radar samples and the existing 15-second
source video. Tracking boxes and radar follow video time; missing positions are
not interpolated. Reports can be searched, read and downloaded. Large report
previews are limited to 40,000 characters; downloads contain the complete file.

The selected role review is 82/96 (85.42%), not overall or held-out accuracy.
Radar supports only 0.65% of person observations. Real speed, distance and
sprints remain unavailable. Tackles and possession are not implemented. The
website displays these limitations alongside the relevant results.

## Source and refresh

UI: web/results/. Exporter: scripts/export_hosted_results.py.
The exporter requires the local saved inputs explicitly named in that script;
a fresh Git clone does not include these ignored private artifacts.

```sh
.venv/bin/python scripts/export_hosted_results.py data/published-football-results/dist
.venv/bin/python scripts/serve_results_preview.py data/published-football-results/dist --port 8013
```

Preview supports byte ranges so saved video seeking works. The Sites checkout
is data/published-football-results; its .openai/hosting.json retains the site ID.
Use the installed Sites source/package workflow and owner-private deployment to
publish updates. Do not create a new Site or expand its audience for a refresh.
Credentials must remain in memory and enter the helper only through hidden stdin.

Exports omit weights, databases, credentials and raw feature dumps; local path
prefixes are sanitized. Catalog hashes describe the exported report bytes.
Historical missing videos are not recreated. To analyze a new video, install and
run the local dashboard using the repository README.

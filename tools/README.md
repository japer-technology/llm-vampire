# tools/

Standalone single-file HTML apps for **lmstudio-vampire**.

Each app in this directory is a self-contained `.html` file: all CSS, JavaScript,
and assets are inlined, there is no build step, and nothing here is served by the
running gateway. The gateway's served dashboard lives in `web/` (mounted at `/`),
and the marketing landing page is `LANDING.html` at the repository root — neither
of those belongs here.

## How to run

Open the file directly in a web browser (double-click it, or `File > Open`). No
server, install, or build is required. The apps run entirely from the local
filesystem and talk to your LAN from the browser.

## Apps

| File | What it does |
| --- | --- |
| `vampire-scanner.html` | A single-file "command deck" for discovering, triaging, monitoring, saving, and exporting reachable LM Studio API surfaces and Vampire gateways on a trusted LAN. |

## Adding a new app

- Keep it to a single self-contained `.html` file (inline CSS/JS/assets, no build step).
- Give it a descriptive, purpose-based name (e.g. `network-scanner.html`,
  `node-inspector.html`) so the directory listing is self-documenting.
- Add a row to the table above describing what it does.

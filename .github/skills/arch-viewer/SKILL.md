---
name: arch-viewer
description: "Open the SystemArchitecture.json knowledge graph in a schema-driven web viewer. Use when: viewing architecture, browsing elements, exploring relationships, inspecting views, reading KG, open arch viewer, architecture browser, show knowledge graph."
argument-hint: "(optional) port number, default 7432"
---

# Architecture Knowledge Graph Viewer

Opens `design/KG/SystemArchitecture.json` in a local schema-driven web viewer.
The viewer UI is generated entirely from `.github/argoschema/SystemArchitecture.schema.json` —
it adapts to the schema structure, not to the specific data content.

## Features

- React Flow topology UI with nested parent containers, typed child nodes, and schema-driven edge styling
- Dagre-powered auto-layout with left-to-right or top-to-bottom structure for large architecture graphs
- Search, scope-by-view, collapse/expand containers, relationship highlighting, and a schema-aligned details drawer
- Schema-driven rendering: field labels, validation summary, and raw JSON details stay aligned with SystemArchitecture.schema.json
- All assets stay inside this skill folder: server script, HTML shell, source JS, bundled JS, and CSS

## Procedure

1. Run the local server from the **workspace root** and keep it running:
   ```
   node .github/skills/arch-viewer/scripts/serve.js
   ```
   - The script may open the system browser automatically to `http://localhost:7432`
   - To use a different port: `ARCH_VIEWER_PORT=8080 node .github/skills/arch-viewer/scripts/serve.js`

2. Wait for the server to print `Architecture Viewer  →  http://localhost:PORT`.

3. Immediately open that URL in the VS Code integrated browser.
   - Use the browser page tool rather than only telling the user the URL.
   - Prefer opening `http://127.0.0.1:PORT/` so the browser tools can interact with the page reliably.
   - Always open a fresh page with `forceNew: true`.
   - Add a cache-busting query string such as `?t=<timestamp>` so stale boot-screen tabs are not reused accidentally.

4. Leave the server running while the page is in use. Press Ctrl+C in the terminal to stop it when done.

## Invocation Contract

When this skill is invoked, the expected result is not just a URL or terminal output.
The skill should finish with the architecture viewer page already opened inside VS Code and ready for interaction.

## Frontend Notes

- The page now loads the local bundle at `assets/app.bundle.js`.
- The editable source lives at `assets/app.js`.
- If you change `assets/app.js`, rebuild the bundle from the workspace root:
   ```
   node -e "const esbuild=require('esbuild'); esbuild.build({ entryPoints:['.github/skills/arch-viewer/assets/app.js'], outfile:'.github/skills/arch-viewer/assets/app.bundle.js', bundle:true, format:'iife', platform:'browser', target:['chrome120'], jsx:'automatic', loader:{'.js':'jsx'}, define:{'process.env.NODE_ENV':'\"production\"'}, logLevel:'info' }).catch(()=>process.exit(1));"
   ```

## Files

- Server: [scripts/serve.js](./scripts/serve.js)
- Viewer shell: [assets/index.html](./assets/index.html)
- Viewer source: [assets/app.js](./assets/app.js)
- Viewer bundle: [assets/app.bundle.js](./assets/app.bundle.js)
- Viewer styles: [assets/styles.css](./assets/styles.css)

## Requirements

- Node.js (no npm install needed — uses only built-in modules)
- `design/KG/SystemArchitecture.json` must exist (data file)
- `.github/argoschema/SystemArchitecture.schema.json` must exist (schema file)

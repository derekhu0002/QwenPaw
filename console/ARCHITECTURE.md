---
contract_type: implementation-architecture-element
contract_version: 1
scope: stable-element
element_name: qwenpaw-console
element_kind: OperatorConsole
element_path: console
---

## Implementation Architecture Contract

### Responsibility
- Own the operator-facing console frontend and Tauri-oriented packaging assets.
- Materialize pages, hooks, stores, layouts, and API client code for the browser or desktop console surface.

### Out Of Scope
- Owning Python backend runtime behavior.
- Owning public documentation and marketing content under website/.

### Stable Subdirectories
- src/api
- src/pages
- src/layouts
- src/stores
- src/tauri

### Dependency Direction
- The console depends on backend APIs and shared runtime contracts, but the runtime must not depend on console implementation details.---
contract_type: implementation-architecture-element
contract_version: 1
scope: stable-element
element_name: qwenpaw-console
element_kind: OperatorConsole
element_path: console
---

## Implementation Architecture Contract

### Responsibility
- Own the operator-facing browser console and bundled Tauri-specific frontend assets.
- Materialize runtime administration, chat, settings, channel, and coding-mode UI flows against backend APIs.

### Out Of Scope
- Owning backend API behavior or CLI entrypoints.
- Owning external documentation and adoption content.

### Children
- path: src
  kind: frontend-source
  role: React application source for operator workflows
- path: src-tauri
  kind: desktop-shell
  role: Tauri bootstrap and desktop packaging assets
- path: public
  kind: static-assets
  role: static assets served with the console bundle

### Notes
- No explicit testcase is mounted here yet in the intent graph. The current acceptance baseline is backend and CLI centered, while console behavior remains covered by implementation-side tests and future design expansion.
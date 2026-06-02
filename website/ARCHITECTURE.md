---
contract_type: implementation-architecture-element
contract_version: 1
scope: stable-element
element_name: qwenpaw-docs-website
element_kind: DocumentationSite
element_path: website
---

## Implementation Architecture Contract

### Responsibility
- Own the public documentation and adoption website.
- Materialize documentation pages, routing, shared content components, and build-time search indexing assets.

### Out Of Scope
- Owning operator console workflows under console/.
- Owning backend runtime behavior under src/qwenpaw/.

### Stable Subdirectories
- src/pages
- src/components
- src/data
- scripts

### Dependency Direction
- The website may describe or link to product capabilities, but it does not own runtime or console execution flow.---
contract_type: implementation-architecture-element
contract_version: 1
scope: stable-element
element_name: qwenpaw-website
element_kind: AdoptionWebsite
element_path: website
---

## Implementation Architecture Contract

### Responsibility
- Own the external-facing documentation and adoption website.
- Materialize installation guidance, feature communication, and release-facing product content.

### Out Of Scope
- Owning operator console workflows.
- Owning backend runtime behavior.

### Children
- path: src
  kind: website-source
  role: React website source, routing, and documentation rendering
- path: public
  kind: website-static-assets
  role: static assets bundled with the website
- path: scripts
  kind: website-build-support
  role: build-time indexing and static page generation helpers

### Notes
- This stable element is present because the repository ships a separately built external-facing site with its own dependency graph and build system.
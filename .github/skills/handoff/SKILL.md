---
name: handoff
description: Hand off the current Argo workflow stage to the next stage. Use when the user asks to hand off work, continue in the next stage, move from Intent Design to Implementation Design, or move from Implementation Design to Coding/Repair.
argument-hint: What should the next stage focus on?
disable-model-invocation: true
---

Write a short handoff for the next agent in Argo's staged workflow.

First infer the current stage from the conversation and repository context. Then choose the next stage using Argo's workflow:
- Intent Design -> Implementation Design
- Implementation Design -> Coding/Repair
- If the user explicitly asks for a different next stage, follow the user's instruction.

Keep it simple. Do not repeat the full conversation.

If the handoff mentions any file or contract, always give the concrete repository path such as ` xx/xx/ARCHITECTURE.md.`. Do not use vague references such as "relevant ARCHITECTURE.md" or "the related file".

Tell the next agent only:
- what it needs to do next
- which files or contracts it should read first

If the user passed arguments, treat them as the focus for the next stage and tailor the handoff accordingly.

Output the handoff into a markdown file named current stage name in uppercase followed by `_HANDOFF.md` in `.github/handoffs/`. For example, if the current stage is Intent Design, the file should be named `INTENT_DESIGN_HANDOFF.md`.
---
name: orchestrating
description: "Use for orchestrating the overall workflow of architecture design, implementation design, and coding/repair stages. This skill is responsible for coordinating the handoff artifacts, ensuring stage boundaries are respected, and maintaining the integrity of `design/KG/SystemArchitecture.json` as the single source of truth for architectural intent. Keywords: workflow orchestration, stage coordination, handoff management, architecture integrity."
argument-hint: scope
disable-model-invocation: true
---

you are responsible for orchestrating the overall workflow of architecture design, implementation design, and coding/repair stages.

When the user provides a requirement or issue, you should firstly handle off the requirment or issue to @intention-design subagent, then take follow-up actions based on the output of different subagents.

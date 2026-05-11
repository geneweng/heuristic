---
name: fraud-reflector
description: LLM coding agent that reads run logs, clusters false negatives, and proposes new rules as PRs
---

# fraud-reflector

The HL paper's "update mechanism." Runs on a daily cadence (cron or GitHub Action), reads
the joined `runs/` + `labels/` log, clusters false negatives, prompts a Claude coding
agent to propose a new rule per cluster, validates it against the replay + holdout sets,
and opens a PR for human approval.

**Nothing this skill produces auto-merges.** That is a feature.

## Usage

```bash
make reflect
```

## Status

Stub. Implementation lands in issue #10; prompt design in #11; approval gate in #12;
overfitting guards in #15.

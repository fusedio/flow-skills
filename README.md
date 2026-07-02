# flow-skills

A [Claude Code](https://claude.com/claude-code) plugin bundling the Fused **`_core` management skills** — the ones that read and write the Fused App state store (tasks, runs, feedback cards, secrets, the agent roster, artifact chats).

These skills drive the `_core` workspace UDFs — the App state store at `~/.openfused/app/state.json` — over the local execution layer started with `fused dev serve`. Reads go through SQL (`/api/exec/sql`), writes through UDFs (`/api/exec/udf`); each skill documents its own access pattern and is usable on its own.

> Driving the `fused` CLI for setup, running code, and building projects/widgets lives in the **`agent-core`** plugin in [`fusedio/skills`](https://github.com/fusedio/skills). This repo is management-state only.

## Install

Load the repo as a plugin:

```sh
claude --plugin-dir /path/to/flow-skills
```

The manifest at [`.claude-plugin/plugin.json`](.claude-plugin/plugin.json) points at the [`skills/`](skills/) directory (`"skills": "./skills"`), so every skill below loads at once. Each skill is also self-contained and usable on its own.

For the CLI-driving usage skills (setup, infra, projects, execute, verify, storage, widgets, feedback), also load the companion `agent-core` plugin alongside this one:

```sh
git clone https://github.com/fusedio/skills
claude --plugin-dir /path/to/flow-skills --plugin-dir /path/to/skills/agent-core
```

## Skills

| Skill | Purpose |
|---|---|
| [`task-management`](skills/task-management/) | Read, create, assign, and re-status tasks and their comments; render the standalone task-board widget. |
| [`run-management`](skills/run-management/) | Read and write agent run records and per-run transcripts. |
| [`feedback-management`](skills/feedback-management/) | Read and write interaction cards — the system of record for HITL decisions. |
| [`secrets-management`](skills/secrets-management/) | Get, put, list, and delete secrets in the local Fernet-encrypted store. |
| [`agents-management`](skills/agents-management/) | Create, read, update, delete, clone, and reset agent-roster entries. |
| [`artifact-chat-management`](skills/artifact-chat-management/) | Create and update artifact chat threads and their messages/transcripts. |

Each skill is a Fused `_core` project: a set of UDFs under `scripts/<op>/` (each with a `main.py` + `spec.md`), an `openfused.toml` that registers them, and — where relevant — a shipped widget under `widgets/`. See any skill's `SKILL.md` for its operations and the read/write access pattern.

## Customizing & contributing

Two kinds of change, handled in opposite ways — see [`CONTRIBUTING.md`](CONTRIBUTING.md):

- **Changing what a skill *means*** (new defaults, a repurposed op, a
  team-specific workflow) → **don't edit the shipped skill.** Create a new skill
  or Fused project in **your own workspace** and diverge there.
- **Fixing a bug or adding to a skill** (doc fix, wrong/missing field, an
  additive op) → **contribute it back as a PR** so the fix lands upstream instead
  of living as a local divergence.

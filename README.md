# flow-skills

A self-contained [Claude Code](https://claude.com/claude-code) plugin for working with **OpenFused** — end-to-end data work on cloud-native datasets via MCP and CLI. It bundles the OpenFused `_core` management skills together with usage skills that take you from a fresh install to a running project and its widget UI, with no other repo required.

## Install

Load the repo as a plugin:

```sh
claude --plugin-dir /path/to/flow-skills
```

The manifest at [`.claude-plugin/plugin.json`](.claude-plugin/plugin.json) auto-discovers every top-level skill directory (`"skills": "./"`), so all skills below become available at once.

## Where to start

- **Set up OpenFused** → [`openfused-setup`](openfused-setup/) (then [`openfused-infra`](openfused-infra/) to provision resources).
- **Build a project and get its widget UI** → [`openfused-projects`](openfused-projects/) → [`openfused-widgets`](openfused-widgets/) → [`openfused-feedback`](openfused-feedback/) for approval gates.
- **Not sure which skill?** Load [`openfused-guide`](openfused-guide/) — it routes your goal to the right skill.

## Skills

### Usage — setting up and building with OpenFused

| Skill | Purpose |
|---|---|
| [`openfused-guide`](openfused-guide/) | Entry-point router — maps a goal (set up / run code / build a widget) to the right skill. |
| [`openfused-setup`](openfused-setup/) | Install and set up OpenFused for the first time — AWS credential checks, install, provision, verify. |
| [`openfused-infra`](openfused-infra/) | Reference for the infrastructure OpenFused manages (AWS: IAM, Lambda, ECR, S3; local: data dirs + venvs) — what exists, why, and when it changes. |
| [`openfused-cli`](openfused-cli/) | The `openfused` CLI reference — environments, file storage, secrets, code execution, infra commands. |
| [`openfused-projects`](openfused-projects/) | The canonical end-to-end guide — pick an env, create a project, decompose into UDFs, author specs + code, validate, run/preview, deploy. |
| [`openfused-execute`](openfused-execute/) | Best practices for running code through `execute_code` — structuring code, choosing a data library, handling results, writing outputs. |
| [`openfused-verify`](openfused-verify/) | Security scanning, testing, and correctness validation (`verify_code`, `test_code`, audit log, spec checks). |
| [`openfused-storage`](openfused-storage/) | Storage + secrets MCP tools — inspect cloud-native datasets and manage secrets. |
| [`openfused-widgets`](openfused-widgets/) | Author and preview JSON-UI widgets as a project's response — the compute→visualize pattern and the surfaces that render them. |
| [`openfused-feedback`](openfused-feedback/) | Show the human a real browser UI for questions, approvals, and plan reviews via `openfused widget open` / parley. |

### Management (`_core`)

These expose the OpenFused App state store as live UDFs.

| Skill | Purpose |
|---|---|
| [`task-management`](task-management/) | Read, create, assign, and re-status tasks; render the task-board widget. |
| [`run-management`](run-management/) | Read and write agent run records and per-run transcripts. |
| [`feedback-management`](feedback-management/) | Read and write interaction cards — the system of record for HITL decisions. |
| [`secrets-management`](secrets-management/) | Get, put, list, and delete secrets in the local Fernet-encrypted store. |
| [`agents-management`](agents-management/) | Create, read, update, delete, clone, and reset agent-roster entries. |

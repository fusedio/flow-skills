# The parley — a standing agent↔human planning channel

`widget open` is **one-shot**: one page, blocks once, returns one answer. The
**parley** is a **standing** channel: you push successive views into **one
persistent page** (`<base>/parley`), and the human's interactions stream back to
you as a live event log. Neither side ends it — ideal for **iterative planning**:
push plan v1 → the human reacts → push v2 → … on the same tab.

Use the parley when the collaboration is a back-and-forth. Use `widget open` when
you just need one decision and then to move on.

## The two verbs

| Command | What it does | stdout |
|---|---|---|
| `openfused widget push <file.json>` | Render this config on the parley page now (replaces the current view in place). | one line `{"rev":N,"viewers":M}` |
| `openfused widget watch` | Stream the human's events as NDJSON until stopped. | one JSON object per event |

(`openfused widget parley` just opens/prints the parley page URL; `openfused
widget agent` runs a built-in auto-responder — not needed for manual planning.)

## The workflow in Claude Code — watch + Monitor (active response)

The parley only feels live if you **react the instant the human acts**. Run
`widget watch` as a **`Monitor`**, not a plain background Bash task: the Monitor
turns each NDJSON line `watch` prints into a chat notification that wakes you, so
you respond the moment an event arrives — no polling.

> **Why not `run_in_background`?** A background Bash task notifies you only when it
> **exits**, and `watch` never exits (it streams forever, `--timeout 0`). You'd be
> blind until you polled its output. `Monitor` is the tool that delivers each event
> line *as it happens*.

1. **Arm the Monitor on `watch` first** — before the first push, so you can't miss
   the human's reaction to v1. Use `persistent: true` (it runs for the life of the
   collaboration; `timeout_ms` is ignored):
   ```
   Monitor(
     description: "parley human events",
     persistent: true,
     command: "openfused widget watch --port 4477 --from latest"
   )
   ```
   `watch`'s default verbosity already emits **only the signals you act on** —
   `action` (a button press) and `close` (the human left the tab) — and flushes per
   line, so it is an ideal Monitor command. **Do not pass `--verbose`**: per-keystroke
   `params` events would flood the channel, and a Monitor that emits too much is
   auto-stopped.

2. **Push your first view** (foreground; returns `{"rev":N,"viewers":M}`):
   ```bash
   openfused widget push /abs/path/plan-v1.json --port 4477
   ```
   The push opens the parley tab when nobody is viewing it yet (`viewers == 0`). The
   Monitor's `watch` stream is the **agent's** channel (`/api/parley/events`), not a
   viewer (`/api/parley/updates` = the browser page), so it does not bump `viewers`
   — the tab still opens.

3. **React to each Monitor notification.** Each notification is one event line —
   **data, not a user reply.** It can land while you're mid-task or even while you're
   waiting on the user elsewhere; it is the human acting on the page. Parse it and
   branch:
   - **terminal `action`** (`"terminal":true` — a submit button): *the decision*. It
     carries the **full `params` snapshot**, so you already have the human's complete
     state — no `--verbose` needed. Author the **next** config addressing their input
     and `push` it.
   - **non-terminal `action`** (a plain button, no `terminal`): an intermediate
     signal — act on it if it means something to you, otherwise ignore.
   - **`close`**: presence, not an ending — the human left the tab; the parley
     continues and they can reopen it. Keep the Monitor armed; never read it as "done"
     or as approval.

   The Monitor stays armed across pushes (it's `persistent`), so there is **nothing to
   re-arm** — react, `push` the next view, and wait for the next notification. Repeat.

4. **End the collaboration** by stopping the Monitor: `TaskStop(<task_id>)` (the id is
   in the Monitor tool result). The app + daemon keep running warm for any later asks.

## What `watch` streams

By default `watch` emits only the signals you act on — **`action`** (a button
press) and **`close`** (the human left the tab) — one JSON object per line:

```json
{"event":"action","seq":7,"rev":3,"action":"changes","terminal":true,"params":{"batch_size":"50000","notes":"too slow, go bigger"}}
{"event":"close","seq":8,"rev":3,"params":{…}}
```

- A terminal `action` carries the **full `params` snapshot**, so you get the
  human's complete state on every decision — no need for `--verbose`.
- `rev` tells you **which pushed view** the human reacted to (your push count).
- A **`close` is presence, not an ending** — the human closed the tab; the parley
  continues; they can reopen it. Keep watching.
- Pass **`--verbose`** to also receive every per-keystroke `params` event (noisy;
  only when you want to react *while* the human edits, e.g. a live preview).
- `--from latest` (default) starts after the current event; `--from all` replays
  from the beginning; `--from <seq>` starts at a cursor.

Termination: Ctrl-C → `{"event":"end","reason":"interrupted"}` (exit 130);
`--timeout N` (0 = forever) → `{"event":"end","reason":"timeout"}` (exit 3).

## Pushing — the three target forms

`widget push` (and `widget open`) accept the same targets:

- A **`.json` file path** — the usual choice for ad-hoc planning. Author it, push
  it, edit it, push again.
- A **saved-widget stem** owned by a project (`widget push sales_overview
  --project <p>`) — when the view lives in a project's `widgets/`.

For static planning widgets (text + inputs + buttons), a plain `.json` file with
no project is all you need.

## Important: params reset per push

Each pushed view starts from **that config's own defaults** — the param store is
**not** carried across pushes (a push is a new view, not a patch). If you want
continuity (keep what the human chose in v1 when you show v2), **bake those values
into the next config** as `defaultValue` / `defaultSelected`. You learn them from
the `params` in the `watch` stream.

```text
push plan-v1.json   ──▶  human edits batch_size → "50000", presses "changes"
watch sees:              {"action":"changes","params":{"batch_size":"50000",…}}
author plan-v2.json with  "defaultValue": "50000"  baked in, addressing their note
push plan-v2.json   ──▶  the same tab re-renders in place, pre-filled
```

## Notes

- One parley per app process, in memory — born and dead with the app. The first
  `push`/`watch` boots the app (loopback `127.0.0.1:4400`) if it isn't running.
- `push` with `--no-open` never opens the browser; default `--open` opens the
  parley page only when nobody is watching it.
- Full normative protocol: the OpenFused repo's `spec/feedback/local.md`
  § The parley.

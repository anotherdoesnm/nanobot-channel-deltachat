# nanobot-channel-deltachat

A [Delta Chat](https://delta.chat/) channel for [nanobot](https://github.com/HKUDS/nanobot) that lets you chat with your AI agent over email/IMAP.

Since nanobot 0.3.0 there is no external channel-plugin path: a channel must be a self-contained package physically inside `nanobot/channels/<channel>/`. This repo is the canonical source of that channel package, and `patch_nanobot.py` builds a nanobot fork with it baked in.

## How it works

`patch_nanobot.py` copies the nanobot source plus this channel into a fresh directory, patches `pyproject.toml` so the Delta Chat runtime dependencies are pulled in, and can install the result via `uv tool install` — the same way the original nanobot is installed.

## Build the fork

`patch_nanobot.py` takes the nanobot checkout and the output directory as arguments. The channel package lives in this repo next to the script, so there is nothing else to configure:

```bash
# from this repo
uv run patch_nanobot.py /path/to/nanobot /path/to/patched-nanobot
uv run patch_nanobot.py /path/to/nanobot /path/to/patched-nanobot --install  # also `uv tool install`
```

The build uses the standard `uv tool install` flow; the WebUI is built from the bundled source during install.

## Install and run

```bash
uv run patch_nanobot.py /path/to/nanobot /path/to/patched-nanobot --install
nanobot plugins list     # verify "Delta Chat" appears as a channel
nanobot gateway
```

To install a previously built fork without re-patching:

```bash
uv tool install /path/to/nanobot-with-deltachat
```

## Configuration

In `~/.nanobot/config.json`:

```json
{
  "channels": {
    "deltachat": {
      "enabled": true,
      "accountUrl": "DCACCOUNT://nine.testrun.org",
      "dbDir": "~/.nanobot/dc_channel",
      "displayName": "Nanobot AI",
      "allowFrom": ["*"],
      "streaming": true
    }
  }
}
```

- `accountUrl` is a `DCACCOUNT://` URL (e.g. `DCACCOUNT://nine.testrun.org`). The account is created automatically from it via `account.add_transport_from_qr(...)` — there is no email/password configuration anymore.
- `dbDir` stores the Delta Chat account. If omitted, data lives in `~/.nanobot/dc_channel/`; an explicit path is expanded via `~`. Restarts reuse the persisted account instead of creating a new one. To force a fresh account, delete the directory (default `~/.nanobot/dc_channel`).
- `streaming` (default `true`) enables nanobot's streamed delivery. Turn it off to get each reply as one whole message instead of being updated in place.

## Streaming

Progress messages and tool-call hints arrive as separate whole messages. Model
reasoning and the streamed answer text are delivered as a **single message that
the bot keeps updating in place** via Delta Chat message editing (`send_edit_request`
— the client shows such messages as "edited"). Chunks are accumulated and an edit
is pushed at most once every 2 seconds; on stream end the full text is written
regardless of timing. A new message starts whenever the content type changes
(reasoning → tool call → answer).

## First run

The invite link is logged once at startup. Copy it into Delta Chat via **New contact → Invite by link** before restarting the bot, otherwise the link becomes invalid.

## Development

Code changes take effect after restarting `nanobot gateway`. Re-run `patch_nanobot.py` only when the manifest, runtime dependencies, or `pyproject.toml` change.

- Syntax check: `uv run python -m py_compile nanobot_channel_deltachat/*.py`
- Lint: `ruff check nanobot_channel_deltachat/` (config in `pyproject.toml`; ruff is not a project dependency — install it separately, e.g. `uv tool install ruff`)
- Tests (inside the fork): `uv run pytest nanobot/channels/deltachat/tests -q`

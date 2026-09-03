# AGENTS.md

## What this repo is

`nanobot-channel-deltachat` is the source tree for a **Delta Chat channel** of the
[nanobot](https://github.com/HKUDS/nanobot) agent framework. Since nanobot 0.3.0,
channels are self-contained packages physically under `nanobot/channels/<channel>/`;
the old `nanobot.channels` entry-point plugin system no longer exists. This repo is
NOT a standalone pip package anymore.

## Where the code actually runs

The channel package (`nanobot_channel_deltachat/`) is copied into a nanobot checkout
as `nanobot/channels/deltachat/`. `runtime.py`/`manifest.py` import
`nanobot.channels.*`, so they only resolve inside that tree — you cannot import or
test this package in isolation. Tests use relative imports (`from ..runtime import …`)
so they run in the fork.

Reference source locations (local clones, not committed):
- nanobot checkout: the repo that `patch_nanobot.py` copies (any checkout of HKUDS/nanobot)
- deltachat core (RPC client source of truth): the `chatmail/core` clone, `deltachat-rpc-client/` subdirectory

## Channel-package contract (nanobot 0.3.0)

- `manifest.py` declares `PLUGIN = ChannelPlugin(name="deltachat", runtime=f"{__package__}.runtime:DeltaChatChannel", …)`.
  It is imported during discovery and MUST NOT import `deltachat_rpc_client` or other SDKs.
- `ChannelManager` instantiates `cls(section, bus)` where `section` is the raw
  `channels.deltachat` dict from `config.json` — so `__init__` must coerce dict → Pydantic model.
- `start()` must block forever; `send()` must **raise** on delivery failure (manager
  retries) and should skip `ProgressEvent`. `_handle_message()` handles `allow_from`.
- Config model subclasses `nanobot.config.schema.Base` (accepts both `account_url` and `accountUrl`).
- `accountUrl` must be a `DCACCOUNT://` URL — enforced by the setup validator in
  `validation.py` (`manifest.setup.validator`); there is no email/password config.
- Per-channel data dir (weixin pattern): empty `dbDir` falls back to
  `get_runtime_subdir("dc_channel")` → `~/.nanobot/dc_channel/`; an explicit value is
  expanded via `~`. Resolve at `start()`, not at import time.
- Streaming: the channel overrides `send_delta`/`send_reasoning_delta`/`send_reasoning_end`
  (`send_reasoning` one-shot comes for free via the base delta+end pair). Streaming
  only activates when config `streaming=True` AND `send_delta` is overridden
  (`BaseChannel.supports_streaming` → `_wants_stream`); default `DeltaChatConfig.streaming` is True.
  Delivery logic lives in `chat_stream.py`: whole messages (progress/tool hints, non-streamed
  replies) send one chunk per message; streamed messages (reasoning, answer) create one message
  on the first chunk and update it via edits (+2s throttle, flush writes the full text).
  Edits use `send_edit_request` – the DC client renders them as "edited".

## deltachat-rpc-client notes (2.54–2.59)

- Account creation: `account.add_transport_from_qr("DCACCOUNT://<domain>")` — blocks,
  configures, starts I/O. `configure()` is **deprecated**; do not use it.
- Idempotent restart: check `account.is_configured()` before adding the transport so a
  gateway restart reuses the persisted account in `dbDir` instead of creating a new one.
- `Rpc(accounts_dir=...)` maps to the `DC_ACCOUNTS_PATH` env var. `wait_for_event()`
  returns an `AttrDict` (`kind`, `msg_id`, `msg`); `EventType` is a `str` enum
  (`EventType.INCOMING_MSG == "IncomingMsg"`).
- Message editing: `send_edit_request(account_id, msg_id, new_text)` (core ≥ 1.156) has
  **no Python wrapper** — call it via `Rpc.__getattr__` (`self._rpc.send_edit_request(...)`).
- `send()` currently swallows nothing — `chat.send_text()` and `send_edit_request`
  propagate errors (contract-correct); the old unconditional `ProgressEvent` skip is gone.

## Gotchas

- `stop()` is cooperative only (`_running = False`); a blocking `wait_for_event` in a
  thread is not interrupted, so shutdown can stall until the next event arrives.
- Changing `accountUrl` after first run does not reconfigure (`is_configured()` is already
  true). To force a fresh account, delete the account data dir (default `~/.nanobot/dc_channel/`).
- Log/comment strings are in Russian — preserve that style.

## Build the fork (patch + install)

`patch_nanobot.py` copies nanobot + this channel into a fresh checkout, patches
`pyproject.toml` with the deltachat runtime deps, and can install via uv. It takes
the nanobot checkout and the output directory as positional arguments; the channel
package is located relative to the script:

```bash
uv run patch_nanobot.py <nanobot-src> <dest>
uv run patch_nanobot.py <nanobot-src> <dest> --install   # also run `uv tool install`
```

The script and docs must NOT hardcode local filesystem paths.

## Commands

- Syntax check: `uv run python -m py_compile nanobot_channel_deltachat/*.py`
- Lint: `ruff check nanobot_channel_deltachat/` (ruff config lives in `pyproject.toml`; ruff is not a project dependency — install separately, e.g. `uv tool install ruff`)
- Tests run inside the fork: `uv run pytest nanobot/channels/deltachat/tests -q`

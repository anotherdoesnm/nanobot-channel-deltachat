**nanobot-channel-deltachat**

A channel plugin for [nanobot](https://github.com/HKUDS/nanobot) that lets you chat with your AI agent through [Delta Chat](https://delta.chat/).

Uses email as transport: full privacy, no lock-in to a specific messenger, and decentralization.

## 📋 Features

- Sending and receiving text messages.
- Full support for nanobot's plugin architecture (Pydantic configuration, `allow_from`).
- Proper integration with nanobot's async event loop.
- Bot nickname support.

## 📦 Dependencies

```bash
pip install deltachat-rpc-server deltachat-rpc-client
```

## 🚀 Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/your-username/nanobot-channel-deltachat.git
   cd nanobot-channel-deltachat
   ```

2. Install the plugin in development mode:
   ```bash
   pip install -e .
   ```

3. Verify that nanobot sees the plugin:
   ```bash
   nanobot plugins list
   ```

## ⚙️ Configuration

Add the following block to `~/.nanobot/config.json`:

```json
{
  "channels": {
    "deltachat": {
      "enabled": true,
      "email": "your-bot@example.com",
      "password": "your-app-password",
      "display_name": "Nanobot AI",
      "allow_from": ["*"],
      "db_dir": "~/.nanobot/deltachat_db"
    }
  }
}
```

*Use an App Password, not your main email password.*

## 🏃 Running

1. Start the gateway:
   ```bash
   nanobot gateway
   ```

2. An invite link will appear in the logs:
   ```
   📋 Bot invite link: https://i.delta.chat/#...
   ```

3. Copy it and paste into Delta Chat via **"New contact" → "Invite by link"**.

> *Note: Don't restart the bot before adding it via the invite link, otherwise the link will become invalid.*

## 🛠 Development

Thanks to the `-e` flag, code changes take effect immediately after restarting `nanobot gateway`. Reinstallation is only needed when modifying `pyproject.toml`.

---

*Thanks to Zhipu.AI and GLM.*
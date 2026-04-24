# nanobot-channel-deltachat

Плагин канала для [nanobot](https://github.com/HKUDS/nanobot), позволяющий общаться с вашим AI-агентом через [Delta Chat](https://delta.chat/). 

Использует электронную почту как транспорт: полная конфиденциальность, отсутствие привязки к конкретному мессенджеру и децентрализация.

## 📋 Возможности

*   Прием и отправка текстовых сообщений.
*   Полная поддержка архитектуры плагинов nanobot (Pydantic конфигурация, `allow_from`).
*   Корректная работа с асинхронным event loop nanobot.
*   Поддержка никнеймов ботов.

## 📦 Зависимости

```bash
pip install deltachat-rpc-server deltachat-rpc-client
```

## 🚀 Установка

1. Клонируйте репозиторий:
   ```bash
   git clone https://github.com/your-username/nanobot-channel-deltachat.git
   cd nanobot-channel-deltachat
   ```

2. Установите плагин в режиме разработки:
   ```bash
   pip install -e .
   ```

3. Проверьте, что nanobot видит плагин:
   ```bash
   nanobot plugins list
   ```

## ⚙️ Настройка

Добавьте блок в `~/.nanobot/config.json`:

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

*Используйте пароль приложения (App Password), а не основной пароль от почты.*

## 🏃 Запуск

1. Запустите шлюз:
   ```bash
   nanobot gateway
   ```

2. В логах появится ссылка:
   ```
   📋 Ссылка-приглашение для бота: https://i.delta.chat/#...
   ```

3. Скопируйте её и вставьте в Delta Chat через **"Новый контакт" -> "Приглашение по ссылке"**. 
   > *Примечание: не перезапускайте бота до того, как добавите его по ссылке, иначе ссылка станет недействительной.*

## 🛠 Разработка

Благодаря флагу `-e` изменения в коде применяются сразу после перезапуска `nanobot gateway`. Переустановка требуется только при изменении `pyproject.toml`.

---

*Спасибо Zhipu.AI и GLM.*
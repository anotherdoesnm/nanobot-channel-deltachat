import asyncio
from typing import Any, Optional
from loguru import logger
from pydantic import Field
import os
from nanobot.channels.base import BaseChannel
from nanobot.bus.events import OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.config.schema import Base

from deltachat_rpc_client import Rpc, DeltaChat, EventType


class DeltaChatConfig(Base):
    """Конфигурация для канала DeltaChat."""
    enabled: bool = False
    email: str = ""
    password: str = ""
    allow_from: list[str] = Field(default_factory=list)
    db_dir: str = "deltachat_db"
    display_name: str = "nanobot"


class DeltaChatChannel(BaseChannel):
    name = "deltachat"
    display_name = "Delta Chat"

    def __init__(self, config: Any, bus: MessageBus):
        if isinstance(config, dict):
            config = DeltaChatConfig(**config)
        super().__init__(config, bus)

        self._rpc: Optional[Rpc] = None
        self._dc: Optional[DeltaChat] = None
        self._account = None
        self._account_id: Optional[int] = None
        self._running = False

    @classmethod
    def default_config(cls) -> dict[str, Any]:
        return DeltaChatConfig().model_dump(by_alias=True)

    async def start(self) -> None:
        """Запускает DeltaChat аккаунт и начинает слушать входящие сообщения."""
        self._running = True

        if not self.config.email or not self.config.password:
            raise ValueError("Отсутствуют учетные данные DeltaChat")

        try:

            # Create RPC with explicit executable path
            self._rpc = Rpc(
                accounts_dir=os.path.expanduser(self.config.db_dir)
            )
            
            # Start the RPC server
            self._rpc.start()
            self._dc = DeltaChat(self._rpc)

            accounts = self._dc.get_all_accounts()
            self._account = self._select_account(accounts)
            if self._account is None:
                self._account = self._dc.add_account()

            self._account_id = self._account.id
            if not self._account.is_configured():
                self._account.set_config("addr", self.config.email)
                self._account.set_config("mail_pw", self.config.password)
                self._account.set_config("bot", "1")
                if self.config.display_name:
                    self._account.set_config("displayname", self.config.display_name)
                self._account.configure()

            self._account.bring_online()
            try:
                invite_link = self._account.get_qr_code()
                logger.info(f"Ссылка-приглашение для бота: {invite_link}")
            except Exception as qr_err:
                logger.warning(f"Не удалось получить invite-ссылку: {qr_err}")
            logger.info(f"Аккаунт {self.config.email} успешно настроен")
            await self._start_event_loop()

        except Exception as e:
            logger.error(f"Ошибка при запуске DeltaChat канала: {e}")
            raise
        finally:
            self._running = False
            # Clean up RPC connection
            if self._rpc:
                self._rpc.close()
                self._rpc = None
            self._dc = None
            self._account = None
            self._account_id = None

    def _select_account(self, accounts: list[Any]) -> Optional[Any]:
        if not accounts:
            return None
        for account in accounts:
            try:
                if account.get_config("addr") == self.config.email:
                    return account
            except Exception:
                continue
        return accounts[0]

    @staticmethod
    def _event_value(event: Any, key: str, default: Any = None) -> Any:
        if isinstance(event, dict):
            return event.get(key, default)
        return getattr(event, key, default)

    async def _start_event_loop(self) -> None:
        """Вечный цикл событий."""
        while self._running:
            try:
                if self._account is None:
                    logger.warning("DeltaChat аккаунт не инициализирован, завершаем event loop")
                    break
                event = await asyncio.to_thread(self._account.wait_for_event)
                await self._handle_event(event)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Ошибка в цикле событий DeltaChat: {e}")
                await asyncio.sleep(5)

    async def _handle_event(self, event) -> None:
        kind = self._event_value(event, "kind")
        if kind == EventType.INCOMING_MSG:
            msg_id = self._event_value(event, "msg_id")
            if msg_id is None:
                logger.warning(f"INCOMING_MSG без msg_id: {event}")
                return
            if self._account is None:
                logger.warning("Получено входящее сообщение до инициализации аккаунта")
                return

            message = self._account.get_message_by_id(msg_id)
            snapshot = message.get_snapshot()

            if snapshot.is_info:
                return

            await self._handle_message(
                sender_id=str(snapshot.from_id),
                chat_id=str(snapshot.chat_id),
                content=snapshot.text or "",
                media=[],
            )
        elif kind == EventType.INFO:
            logger.info(self._event_value(event, "msg", str(event)))
        elif kind == EventType.WARNING:
            logger.warning(self._event_value(event, "msg", str(event)))
        elif kind == EventType.ERROR:
            logger.error(self._event_value(event, "msg", str(event)))

    async def stop(self) -> None:
        self._running = False
        logger.info("Остановка канала DeltaChat...")
        await asyncio.sleep(0)

    async def send(self, msg: OutboundMessage) -> None:
        try:
            if self._account is None:
                raise RuntimeError("DeltaChat аккаунт не инициализирован")
            chat = self._account.get_chat_by_id(int(msg.chat_id))
            chat.send_text(msg.content)
            logger.info(f"Сообщение отправлено в чат {msg.chat_id}")
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения: {e}")
"""Delta Chat channel implementation using the deltachat-rpc-client SDK."""

import asyncio
from pathlib import Path
from typing import Any, Optional

from deltachat_rpc_client import DeltaChat, EventType, Rpc
from loguru import logger
from nanobot.bus.events import OutboundMessage
from nanobot.bus.outbound_events import ProgressEvent
from nanobot.bus.queue import MessageBus
from nanobot.channels.base import BaseChannel
from nanobot.config.paths import get_runtime_subdir
from nanobot.config.schema import Base
from pydantic import Field

from .chat_stream import ChatStreamController

# Интервал (сек) между обновлениями стримового сообщения через editMessage.
STREAM_THROTTLE_S = 2.0


class DeltaChatConfig(Base):
    """Конфигурация для канала DeltaChat."""

    enabled: bool = False
    account_url: str = ""
    allow_from: list[str] = Field(default_factory=list)
    db_dir: str = ""  # По умолчанию: ~/.nanobot/dc_channel/
    display_name: str = "nanobot"
    streaming: bool = True


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
        self._stream_controller: Optional[ChatStreamController] = None

    @classmethod
    def default_config(cls) -> dict[str, Any]:
        return DeltaChatConfig().model_dump(by_alias=True)

    async def start(self) -> None:
        """Запускает DeltaChat аккаунт и начинает слушать входящие сообщения."""
        self._running = True

        if not self.config.account_url:
            raise ValueError("Отсутствует accountUrl DeltaChat")

        try:
            if self.config.db_dir:
                accounts_dir = Path(self.config.db_dir).expanduser()
            else:
                accounts_dir = get_runtime_subdir("dc_channel")
            self._rpc = Rpc(accounts_dir=str(accounts_dir))
            self._rpc.start()
            self._dc = DeltaChat(self._rpc)

            accounts = self._dc.get_all_accounts()
            self._account = accounts[0] if accounts else self._dc.add_account()

            self._account_id = self._account.id
            self._stream_controller = ChatStreamController(
                create_message=self._create_dc_message,
                edit_message=self._edit_dc_message,
                throttle_s=STREAM_THROTTLE_S,
            )
            if not self._account.is_configured():
                self._account.set_config("bot", "1")
                if self.config.display_name:
                    self._account.set_config("displayname", self.config.display_name)
                self._account.add_transport_from_qr(self.config.account_url)

            self._account.bring_online()
            try:
                invite_link = self._account.get_qr_code()
                logger.info(f"Ссылка-приглашение для бота: {invite_link}")
            except Exception as qr_err:
                logger.warning(f"Не удалось получить invite-ссылку: {qr_err}")
            logger.info("Аккаунт DeltaChat успешно настроен")
            await self._start_event_loop()

        except Exception as e:
            logger.error(f"Ошибка при запуске DeltaChat канала: {e}")
            raise
        finally:
            self._running = False
            if self._rpc:
                self._rpc.close()
                self._rpc = None
            self._dc = None
            self._account = None
            self._account_id = None

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

    def _create_dc_message(self, chat_id: str, content: str) -> int:
        if self._account is None:
            raise RuntimeError("DeltaChat аккаунт не инициализирован")
        chat = self._account.get_chat_by_id(int(chat_id))
        msg = chat.send_text(content)
        logger.info(f"Сообщение отправлено в чат {chat_id}")
        return int(msg.id)

    def _edit_dc_message(self, chat_id: str, msg_id: int, content: str) -> None:
        if self._rpc is None or self._account_id is None:
            raise RuntimeError("DeltaChat канал не инициализирован")
        self._rpc.send_edit_request(self._account_id, msg_id, content)
        logger.info(f"Сообщение {msg_id} обновлено в чате {chat_id}")

    def _require_stream_controller(self) -> ChatStreamController:
        if self._stream_controller is None:
            raise RuntimeError("DeltaChat канал не инициализирован")
        return self._stream_controller

    async def send(self, msg: OutboundMessage) -> None:
        controller = self._require_stream_controller()
        event = msg.event
        if isinstance(event, ProgressEvent):
            if event.reasoning or event.reasoning_delta or event.reasoning_end:
                return
            kind = "tool" if event.tool_hint else "progress"
        else:
            kind = "answer"
        if not msg.content:
            return
        await controller.on_whole(msg.chat_id, kind, msg.content)

    async def send_delta(
        self,
        chat_id: str,
        delta: str,
        metadata: dict[str, Any] | None = None,
        *,
        stream_id: str | None = None,
        stream_end: bool = False,
        resuming: bool = False,
        merge_next: bool = False,
    ) -> None:
        controller = self._require_stream_controller()
        if delta:
            await controller.on_stream(chat_id, "answer", delta)
        if stream_end:
            await controller.on_stream_end(chat_id, "answer", merge_next=merge_next)

    async def send_reasoning_delta(
        self,
        chat_id: str,
        delta: str,
        metadata: dict[str, Any] | None = None,
        *,
        stream_id: str | None = None,
    ) -> None:
        controller = self._require_stream_controller()
        if delta:
            await controller.on_stream(chat_id, "reasoning", delta)

    async def send_reasoning_end(
        self,
        chat_id: str,
        metadata: dict[str, Any] | None = None,
        *,
        stream_id: str | None = None,
    ) -> None:
        controller = self._require_stream_controller()
        await controller.on_stream_end(chat_id, "reasoning")

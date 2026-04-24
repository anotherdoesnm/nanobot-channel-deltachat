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
            self._rpc = Rpc(accounts_dir=os.path.expanduser(self.config.db_dir))
            self._rpc.start()
            self._dc = DeltaChat(self._rpc)

            accounts = self._dc.get_all_accounts()
            if accounts:
                self._account = accounts[0] 
            else:
                self._account = self._dc.add_account()

            self._account_id = self._account.id 
                        # 3. Настраиваем аккаунт
            if not self._account.is_configured():
                self._account.set_config("addr", self.config.email)
                self._account.set_config("mail_pw", self.config.password)
                self._account.set_config("bot", "1")
                if self.config.display_name:
                    self._account.set_config("displayname", self.config.display_name)
                self._account.configure()
            
            # Запускаем I/O и ждем полного подключения (включая настройку Mvbox)
            self._account.bring_online()
            invite_link = self._account.get_qr_code()
            logger.info(f"📋 Ссылка-приглашение для бота: {invite_link}")
            logger.info(f"Аккаунт {self.config.email} успешно настроен")
            await self._start_event_loop()

        except Exception as e:
            logger.error(f"Ошибка при запуске DeltaChat канала: {e}")
            raise
        finally:
            if self._rpc:
                self._rpc.close()

    async def _start_event_loop(self) -> None:
        """Вечный цикл событий."""
        while self._running:
            try:
                # 1. wait_for_event - метод Account
                # 2. Он возвращает ОДНО событие, а не список (убрали for)
                event = await asyncio.to_thread(self._account.wait_for_event)
                await self._handle_event(event)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Ошибка в цикле событий DeltaChat: {e}")
                await asyncio.sleep(5)

    async def _handle_event(self, event) -> None:
        if event["kind"] == EventType.INCOMING_MSG:
            msg_id = event["msg_id"]

            # get_message_by_id - метод Account (не DeltaChat)
            message = self._account.get_message_by_id(msg_id)
            snapshot = message.get_snapshot()

            # Пропускаем системные сообщения (например, "контакт добавлен")
            if snapshot.is_info:
                return

            await self._handle_message(
                sender_id=str(snapshot.from_id),
                chat_id=str(snapshot.chat_id),
                content=snapshot.text or "",
                media=[],
            )
        elif event['kind'] == EventType.INFO:
           logger.info(event['msg'])
        elif event['kind'] == EventType.WARNING:
           logger.warning(event['msg'])
        elif event['kind'] == EventType.ERROR:
           logger.error(event['msg'])

    async def stop(self) -> None:
        self._running = False
        logger.info("Остановка канала DeltaChat...")

    async def send(self, msg: OutboundMessage) -> None:
        try:
            # send_text - метод Chat, а не DeltaChat. Получаем чат по ID.
            chat = self._account.get_chat_by_id(int(msg.chat_id))
            chat.send_text(msg.content)
            logger.info(f"Сообщение отправлено в чат {msg.chat_id}")
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения: {e}")
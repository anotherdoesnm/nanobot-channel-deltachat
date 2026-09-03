"""Потоковая отправка сообщений: цельные и стримовые сообщения.

Цельное сообщение отправляется одним сообщением на один чанк. Стримовое
сообщение аккумулирует чанки в буфер и по тирттлингу обновляется через
``send_edit_request``; финальный ``flush()`` отправляет полный текст вне
зависимости от тайминга.

Модуль не импортирует ``deltachat_rpc_client`` и не зависит от nanobot —
колбэки создания и правки сообщений инъектируются из runtime.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Callable

CreateMessage = Callable[[str, str], int]
EditMessage = Callable[[str, int, str], None]
Now = Callable[[], float]

DEFAULT_THROTTLE_S = 2.0


class ChatMessageSender(ABC):
    """ООП-интерфейс единицы сообщения (цельной или стримовой)."""

    def __init__(self, chat_id: str, kind: str) -> None:
        self.chat_id = chat_id
        self.kind = kind

    @abstractmethod
    async def consume_chunk(self, content: str) -> None:
        """Принять очередной чанк текста сообщения."""

    @abstractmethod
    async def flush(self) -> None:
        """Зафиксировать финальное содержимое сообщения."""


class WholeChatMessage(ChatMessageSender):
    """Цельное сообщение: по сути сообщение длиной в один чанк."""

    def __init__(
        self,
        chat_id: str,
        kind: str,
        create_message: CreateMessage,
    ) -> None:
        super().__init__(chat_id, kind)
        self._create_message = create_message
        self._done = False

    async def consume_chunk(self, content: str) -> None:
        if self._done or not content:
            return
        self._create_message(self.chat_id, content)
        self._done = True

    async def flush(self) -> None:
        self._done = True


class StreamingChatMessage(ChatMessageSender):
    """Стримовое сообщение: первый чанк создаёт сообщение, остальные правятся.

    Каждый чанк дописывается в буфер. Если с прошлой отправки прошло не
    меньше ``throttle_s`` секунд — буфер отправляется как ``editMessage``.
    ``flush()`` отправляет полный текст финальным ``editMessage``.
    """

    def __init__(
        self,
        chat_id: str,
        kind: str,
        create_message: CreateMessage,
        edit_message: EditMessage,
        *,
        throttle_s: float = DEFAULT_THROTTLE_S,
        now: Now | None = None,
    ) -> None:
        super().__init__(chat_id, kind)
        self._create_message = create_message
        self._edit_message = edit_message
        self._throttle_s = throttle_s
        self._now: Now = now or time.monotonic
        self._buffer: list[str] = []
        self._msg_id: int | None = None
        self._last_sent_at: float = 0.0
        self._last_sent_text: str = ""
        self._closed = False

    @property
    def text(self) -> str:
        return "".join(self._buffer)

    async def consume_chunk(self, content: str) -> None:
        if self._closed or not content:
            return
        self._buffer.append(content)
        if self._msg_id is None:
            self._msg_id = self._send(self.text)
        elif self._now() - self._last_sent_at >= self._throttle_s:
            self._send(self.text)

    async def flush(self) -> None:
        self._closed = True
        if self._msg_id is None:
            return
        self._send(self.text)

    def reopen(self) -> None:
        """Открыть закрытое сообщение для следующего сегмента (merge_next)."""
        self._closed = False

    def _send(self, text: str) -> int:
        if text == self._last_sent_text:
            return self._msg_id if self._msg_id is not None else 0
        if self._msg_id is None:
            self._msg_id = self._create_message(self.chat_id, text)
        else:
            self._edit_message(self.chat_id, self._msg_id, text)
        self._last_sent_text = text
        self._last_sent_at = self._now()
        assert self._msg_id is not None
        return self._msg_id


class ChatStreamController:
    """Контроллер: держит текущее сообщение на каждый чат.

    При смене типа (например reasoning -> answer или tool call) делает
    ``flush()`` старого, создаёт новое сообщение под новый тип и шлёт в его
    ``consumeChunk``.
    """

    def __init__(
        self,
        *,
        create_message: CreateMessage,
        edit_message: EditMessage,
        throttle_s: float = DEFAULT_THROTTLE_S,
        now: Now | None = None,
    ) -> None:
        self._create_message = create_message
        self._edit_message = edit_message
        self._throttle_s = throttle_s
        self._now: Now = now or time.monotonic
        self._current: dict[str, ChatMessageSender] = {}

    async def on_stream(self, chat_id: str, kind: str, content: str) -> None:
        """Новый чанк стримового сообщения типа ``kind``."""
        current = self._current.get(chat_id)
        if current is not None and current.kind != kind:
            await current.flush()
            current = None
        if current is None:
            current = StreamingChatMessage(
                chat_id,
                kind,
                self._create_message,
                self._edit_message,
                throttle_s=self._throttle_s,
                now=self._now,
            )
            self._current[chat_id] = current
        await current.consume_chunk(content)

    async def on_stream_end(
        self,
        chat_id: str,
        kind: str,
        *,
        merge_next: bool = False,
    ) -> None:
        """Финал стримового сегмента типа ``kind``."""
        current = self._current.get(chat_id)
        if current is None or current.kind != kind:
            self._current.pop(chat_id, None)
            return
        await current.flush()
        if merge_next and isinstance(current, StreamingChatMessage):
            current.reopen()
        else:
            self._current.pop(chat_id, None)

    async def on_whole(self, chat_id: str, kind: str, content: str) -> None:
        """Цельное сообщение типа ``kind`` (один чанк)."""
        current = self._current.pop(chat_id, None)
        if current is not None:
            await current.flush()
        whole = WholeChatMessage(chat_id, kind, self._create_message)
        try:
            await whole.consume_chunk(content)
        finally:
            await whole.flush()

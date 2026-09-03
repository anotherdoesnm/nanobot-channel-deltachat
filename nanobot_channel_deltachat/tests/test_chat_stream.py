from ..chat_stream import ChatStreamController, StreamingChatMessage, WholeChatMessage


class Clock:
    def __init__(self, times: list[float]) -> None:
        self._times = list(times)
        self._i = 0

    def __call__(self) -> float:
        t = self._times[min(self._i, len(self._times) - 1)]
        self._i += 1
        return t


class FakeCalls:
    def __init__(self) -> None:
        self.created: list[tuple[str, str, int]] = []
        self.edited: list[tuple[str, int, str]] = []
        self._next_id = 1

    def create(self, chat_id: str, content: str) -> int:
        msg_id = self._next_id
        self._next_id += 1
        self.created.append((chat_id, content, msg_id))
        return msg_id

    def edit(self, chat_id: str, msg_id: int, content: str) -> None:
        self.edited.append((chat_id, msg_id, content))


async def test_whole_message_is_single_chunk() -> None:
    calls = FakeCalls()
    whole = WholeChatMessage("1", "tool", calls.create)
    await whole.consume_chunk("read_file(x)")
    await whole.flush()
    await whole.consume_chunk("ignored")
    assert [c[1] for c in calls.created] == ["read_file(x)"]
    assert [c[0] for c in calls.created] == ["1"]
    assert calls.edited == []


async def test_streaming_first_chunk_creates_then_edits_throttled() -> None:
    calls = FakeCalls()
    stream = StreamingChatMessage(
        "1", "reasoning", calls.create, calls.edit,
        throttle_s=2.0, now=Clock([0.0, 3.0, 3.5]),
    )
    await stream.consume_chunk("a")
    await stream.consume_chunk("b")
    await stream.consume_chunk("c")
    assert [c[1] for c in calls.created] == ["a"]
    assert [(c[1], c[2]) for c in calls.edited] == [(1, "ab")]


async def test_streaming_flush_sends_full_text_regardless_of_timing() -> None:
    calls = FakeCalls()
    stream = StreamingChatMessage(
        "1", "reasoning", calls.create, calls.edit,
        throttle_s=2.0, now=Clock([0.0, 0.5, 0.7]),
    )
    await stream.consume_chunk("a")
    await stream.consume_chunk("b")
    assert calls.edited == []
    await stream.flush()
    assert [(c[1], c[2]) for c in calls.edited] == [(1, "ab")]


async def test_streaming_flush_is_idempotent() -> None:
    calls = FakeCalls()
    stream = StreamingChatMessage(
        "1", "reasoning", calls.create, calls.edit,
        throttle_s=2.0, now=Clock([0.0, 0.5, 0.5]),
    )
    await stream.consume_chunk("a")
    await stream.consume_chunk("b")
    await stream.flush()
    await stream.flush()
    assert [(c[1], c[2]) for c in calls.edited] == [(1, "ab")]


async def test_controller_type_switch_flushes_and_creates_new_message() -> None:
    calls = FakeCalls()
    controller = ChatStreamController(
        create_message=calls.create, edit_message=calls.edit,
        throttle_s=2.0, now=Clock([0.0, 0.5, 0.5, 0.5]),
    )
    await controller.on_stream("1", "reasoning", "r1")
    await controller.on_stream("1", "reasoning", "r2")
    await controller.on_whole("1", "tool", "read_file(x)")
    await controller.on_stream_end("1", "answer")
    assert [c[1] for c in calls.created] == ["r1", "read_file(x)"]
    assert [(c[1], c[2]) for c in calls.edited] == [(1, "r1r2")]


async def test_controller_full_turn_flow() -> None:
    calls = FakeCalls()
    controller = ChatStreamController(
        create_message=calls.create, edit_message=calls.edit,
        throttle_s=2.0, now=Clock([0.0, 3.0, 3.0, 6.0, 8.0]),
    )
    await controller.on_stream("1", "reasoning", "r1")
    await controller.on_stream("1", "reasoning", "r2")
    await controller.on_stream_end("1", "reasoning")
    await controller.on_stream("1", "answer", "ans1")
    await controller.on_stream("1", "answer", "ans2")
    assert [c[1] for c in calls.created] == ["r1", "ans1"]
    assert [(c[1], c[2]) for c in calls.edited] == [(1, "r1r2"), (2, "ans1ans2")]


async def test_controller_merge_next_keeps_same_message() -> None:
    calls = FakeCalls()
    controller = ChatStreamController(
        create_message=calls.create, edit_message=calls.edit,
        throttle_s=2.0, now=Clock([0.0, 3.0, 3.0, 6.0]),
    )
    await controller.on_stream("1", "answer", "part1a")
    await controller.on_stream_end("1", "answer", merge_next=True)
    await controller.on_stream("1", "answer", "part2a")
    await controller.on_stream_end("1", "answer")
    assert [c[1] for c in calls.created] == ["part1a"]
    assert [(c[1], c[2]) for c in calls.edited] == [(1, "part1apart2a")]


async def test_controller_whole_answer_arriving() -> None:
    calls = FakeCalls()
    controller = ChatStreamController(
        create_message=calls.create, edit_message=calls.edit,
        throttle_s=2.0, now=Clock([0.0, 0.5, 0.5]),
    )
    await controller.on_stream("1", "reasoning", "r")
    await controller.on_whole("1", "answer", "final")
    assert [c[1] for c in calls.created] == ["r", "final"]
    assert calls.edited == []


async def test_controller_per_chat_state() -> None:
    calls = FakeCalls()
    controller = ChatStreamController(
        create_message=calls.create, edit_message=calls.edit,
        throttle_s=2.0, now=Clock([0.0, 0.5, 0.5]),
    )
    await controller.on_stream("1", "reasoning", "r1")
    await controller.on_stream("2", "reasoning", "r2")
    await controller.on_stream_end("2", "reasoning")
    assert [c[1] for c in calls.created] == ["r1", "r2"]
    assert calls.edited == []

from nanobot.bus.events import OutboundMessage
from nanobot.bus.outbound_events import ProgressEvent

from ..chat_stream import ChatStreamController
from ..runtime import DeltaChatChannel, DeltaChatConfig
from .test_chat_stream import Clock


def test_config_accepts_camel_case_aliases() -> None:
    cfg = DeltaChatConfig(
        **{
            "accountUrl": "DCACCOUNT://nine.testrun.org",
            "allowFrom": ["*"],
            "dbDir": "/tmp/db",
            "displayName": "Bot",
        }
    )
    assert cfg.account_url == "DCACCOUNT://nine.testrun.org"
    assert cfg.allow_from == ["*"]
    assert cfg.db_dir == "/tmp/db"
    assert cfg.display_name == "Bot"


def test_default_config_shape() -> None:
    defaults = DeltaChatChannel.default_config()
    assert defaults["enabled"] is False
    assert "accountUrl" in defaults
    assert "allowFrom" in defaults
    assert defaults["dbDir"] == ""
    assert defaults["streaming"] is True


async def test_runtime_routes_events_to_controller() -> None:
    channel = DeltaChatChannel({"accountUrl": "DCACCOUNT://x.org"}, bus=None)
    created: list[str] = []
    edited: list[tuple[int, str]] = []

    def create(chat_id: str, content: str) -> int:
        created.append(content)
        return len(created)

    def edit(chat_id: str, msg_id: int, content: str) -> None:
        edited.append((msg_id, content))

    channel._stream_controller = ChatStreamController(
        create_message=create,
        edit_message=edit,
        throttle_s=2.0,
        now=Clock([0.0, 0.5, 0.5, 0.5]),
    )

    await channel.send_delta("7", "ans1")
    await channel.send_delta("7", "ans2")
    await channel.send_delta("7", "", stream_end=True)
    await channel.send(
        OutboundMessage(
            channel="deltachat", chat_id="7", content="final", event=None
        )
    )
    await channel.send_reasoning_delta("7", "r1")
    await channel.send_reasoning_end("7")

    reasoning_skip = OutboundMessage(
        channel="deltachat",
        chat_id="7",
        content="r2",
        event=ProgressEvent(reasoning=True, content="r2"),
    )
    await channel.send(reasoning_skip)

    tool = OutboundMessage(
        channel="deltachat",
        chat_id="7",
        content="read_file(x)",
        event=ProgressEvent(tool_hint=True, content="read_file(x)"),
    )
    await channel.send(tool)

    assert created == ["ans1", "final", "r1", "read_file(x)"]
    assert edited == [(1, "ans1ans2")]

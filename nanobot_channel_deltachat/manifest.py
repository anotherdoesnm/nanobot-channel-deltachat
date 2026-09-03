"""Delta Chat channel management contract.

This module is imported during discovery and must stay free of the optional
platform SDK (``deltachat_rpc_client``). The runtime is loaded lazily only when
the channel is enabled.
"""

from nanobot.channels._manifest import field, required_fields
from nanobot.channels.contracts import ChannelSetupSpec
from nanobot.channels.plugin import ChannelPlugin

from .validation import validate

PLUGIN = ChannelPlugin(
    name="deltachat",
    display_name="Delta Chat",
    runtime=f"{__package__}.runtime:DeltaChatChannel",
    setup=ChannelSetupSpec(
        fields={
            "accountUrl": field(),
            "dbDir": field(),
            "displayName": field(default="nanobot"),
            "allowFrom": field("list"),
            "streaming": field("bool", default=True),
        },
        required=required_fields("accountUrl"),
        official_url="https://delta.chat/",
        validator=validate,
    ),
)

__all__ = ["PLUGIN"]

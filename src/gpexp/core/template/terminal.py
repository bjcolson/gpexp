"""Template card terminal.

This terminal extends the base Terminal directly — it does NOT inherit
from GenericTerminal, so there is no select, read_binary, probe, or
raw APDU support. Use this as a starting point for cards that have a
fully proprietary command set.

If your card also speaks standard ISO 7816 SELECT/READ, inherit from
GenericTerminal instead (like GPTerminal does).

Each @handles method receives a typed Message dataclass and returns a
typed Result dataclass. The terminal translates between the app-layer
message vocabulary and the protocol-layer APDU vocabulary.
"""

from __future__ import annotations

from gpexp.core.base import Agent, Terminal
from gpexp.core.base.terminal import handles
from gpexp.core.template.messages import (
    EchoMessage,
    EchoResult,
    GetVersionMessage,
    GetVersionResult,
)
from gpexp.core.template.protocol import TemplateProtocol


class TemplateTerminal(Terminal):
    """Terminal for the template card.

    Inherits from Terminal (not GenericTerminal) — no ISO 7816 file
    commands are available. Only the handlers defined here (and any
    future subclass handlers) are active.
    """

    def __init__(self, agent: Agent) -> None:
        super().__init__(agent)
        self._proto = TemplateProtocol(agent.transmit)

    @handles(GetVersionMessage)
    def _get_version(self, message: GetVersionMessage) -> GetVersionResult:
        resp = self._proto.send_get_version()
        return GetVersionResult(version=resp.data, sw=resp.sw)

    @handles(EchoMessage)
    def _echo(self, message: EchoMessage) -> EchoResult:
        resp = self._proto.send_echo(message.data)
        return EchoResult(data=resp.data, sw=resp.sw)

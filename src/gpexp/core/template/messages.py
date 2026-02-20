"""Template card messages and results.

Each operation has a Message/Result pair. The Message carries the input
parameters; the Result carries the typed output. Both are plain
dataclasses with no logic.

Add one pair per card operation. The message type is used for dispatch
in the terminal (via the @handles decorator), so each operation needs
its own message class even if the fields are identical.
"""

from __future__ import annotations

from dataclasses import dataclass

from gpexp.core.base import Message, Result


@dataclass
class GetVersionMessage(Message):
    """Request the card's version information."""


@dataclass
class GetVersionResult(Result):
    """Version response from the card."""

    version: bytes
    sw: int


@dataclass
class EchoMessage(Message):
    """Send data to the card and receive it back."""

    data: bytes


@dataclass
class EchoResult(Result):
    """Echo response from the card."""

    data: bytes
    sw: int

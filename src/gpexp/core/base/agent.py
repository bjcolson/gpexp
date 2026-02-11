from __future__ import annotations

import logging
from typing import Protocol

from gpexp.core.smartcard import APDU, Card, Response

lg = logging.getLogger(__name__)


class SecureChannel(Protocol):
    """Protocol for secure channel wrap/unwrap."""

    def wrap(self, apdu: APDU) -> APDU: ...
    def unwrap(self, response: Response) -> Response: ...


class Agent:
    """Agent that manages card connectivity and APDU transmission.

    Protocol-specific operations live in standalone protocol classes
    (ISO7816, GP) that receive agent.transmit as a callable. Terminals
    construct the protocol objects they need.
    """

    def __init__(self, card: Card) -> None:
        self._card = card
        self._channel: SecureChannel | None = None

    def connect(self) -> None:
        """Discover a reader with a card present and connect."""
        available = Card.list_readers()
        if not available:
            raise RuntimeError("no readers found")
        for reader in available:
            try:
                self._card.connect(reader)
                lg.info("connected")
                return
            except Exception:
                lg.debug("no card on %s", reader)
        raise RuntimeError("no card found on any reader")

    def disconnect(self) -> None:
        """Disconnect from the card."""
        self.close_channel()
        self._card.disconnect()

    def get_uid(self) -> bytes | None:
        """Return the UID of a contactless card, or None if not available."""
        return self._card.get_uid()

    def get_atr(self) -> bytes:
        """Return the ATR of the connected card."""
        return self._card.get_atr()

    def open_channel(self, channel: SecureChannel) -> None:
        """Install a secure channel for APDU wrapping."""
        self._channel = channel

    def close_channel(self) -> None:
        """Remove the active secure channel."""
        self._channel = None

    def transmit(self, apdu: APDU) -> Response:
        """Send an APDU, wrapping/unwrapping if a secure channel is active."""
        if self._channel is not None:
            apdu = self._channel.wrap(apdu)
        response = self._card.transmit(apdu)
        if self._channel is not None:
            response = self._channel.unwrap(response)
        return response

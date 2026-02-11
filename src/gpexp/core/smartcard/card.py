from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from smartcard.CardConnection import CardConnection
from smartcard.System import readers

from gpexp.core.smartcard.observer import LoggingCardObserver
from gpexp.core.smartcard.types import APDU, Response

if TYPE_CHECKING:
    from smartcard.reader.Reader import Reader

lg = logging.getLogger(__name__)


class Card:
    """Wrapper around pyscard for smartcard communication."""

    def __init__(self) -> None:
        self._connection: CardConnection | None = None
        self._observer = LoggingCardObserver()

    @property
    def connected(self) -> bool:
        return self._connection is not None

    @staticmethod
    def list_readers() -> list[Reader]:
        return readers()

    def connect(self, reader: Reader) -> None:
        self._connection = reader.createConnection()
        self._connection.addObserver(self._observer)
        self._connection.connect()

    def disconnect(self) -> None:
        if self._connection is not None:
            self._connection.disconnect()
            self._connection.deleteObserver(self._observer)
            self._connection = None

    def get_uid(self) -> bytes | None:
        """Get the UID of a contactless card via PC/SC pseudo-APDU FF CA 00 00."""
        if self._connection is None:
            raise RuntimeError("not connected to a card")
        data, sw1, sw2 = self._connection.transmit([0xFF, 0xCA, 0x00, 0x00, 0x00])
        if sw1 == 0x90 and sw2 == 0x00:
            return bytes(data)
        return None

    def get_atr(self) -> bytes:
        if self._connection is None:
            raise RuntimeError("not connected to a card")
        return bytes(self._connection.getATR())

    def transmit(self, apdu: APDU) -> Response:
        if self._connection is None:
            raise RuntimeError("not connected to a card")
        data, sw1, sw2 = self._connection.transmit(list(apdu.to_bytes()))
        return Response(data=bytes(data), sw1=sw1, sw2=sw2)

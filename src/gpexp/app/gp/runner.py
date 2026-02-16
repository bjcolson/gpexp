"""GPRunner — extends base Runner with GP session state."""

from __future__ import annotations

import logging

from gpexp.app.generic.commands import COMMAND_MODULES as GENERIC_MODULES
from gpexp.app.generic.runner import Runner
from gpexp.app.gp.cardinfo import GPCardInfo
from gpexp.app.gp.commands import COMMAND_MODULES as GP_MODULES
from gpexp.core.gp import GPTerminal

lg = logging.getLogger(__name__)

GP_DEFAULT_KEY = bytes.fromhex("404142434445464748494A4B4C4D4E4F")


class GPRunner(Runner):
    """Runner with GP session state."""

    def __init__(self, terminal: GPTerminal) -> None:
        super().__init__(terminal, GENERIC_MODULES + GP_MODULES)
        self._info = GPCardInfo()
        self._key = GP_DEFAULT_KEY
        self._enc: bytes | None = None
        self._mac: bytes | None = None
        self._dek: bytes | None = None
        self._settings["key"] = self._set_key
        self._settings["enc"] = self._set_enc
        self._settings["mac"] = self._set_mac
        self._settings["dek"] = self._set_dek

    def _set_key(self, _runner, value: str) -> None:
        self._key = bytes.fromhex(value)
        self._enc = self._mac = self._dek = None
        lg.info("key set to %s", self._key.hex().upper())

    def _set_enc(self, _runner, value: str) -> None:
        self._enc = bytes.fromhex(value)
        lg.info("enc key set to %s", self._enc.hex().upper())

    def _set_mac(self, _runner, value: str) -> None:
        self._mac = bytes.fromhex(value)
        lg.info("mac key set to %s", self._mac.hex().upper())

    def _set_dek(self, _runner, value: str) -> None:
        self._dek = bytes.fromhex(value)
        lg.info("dek key set to %s", self._dek.hex().upper())

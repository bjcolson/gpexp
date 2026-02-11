from __future__ import annotations

from gpexp.core.base import Agent, Terminal
from gpexp.core.base.iso7816 import ISO7816
from gpexp.core.base.terminal import handles
from gpexp.core.generic.messages import (
    ProbeMessage,
    ProbeResult,
    PutDataMessage,
    PutDataResult,
    RawAPDUMessage,
    RawAPDUResult,
    SelectMessage,
    SelectResult,
    UpdateBinaryMessage,
    UpdateBinaryResult,
)
from gpexp.core.smartcard import APDU
from gpexp.core.smartcard.tlv import parse as parse_tlv


class GenericTerminal(Terminal):
    """Terminal that connects to a reader and probes the card."""

    def __init__(self, agent: Agent) -> None:
        super().__init__(agent)
        self._iso = ISO7816(agent.transmit)

    @handles(ProbeMessage)
    def _probe(self, message: ProbeMessage) -> ProbeResult:
        uid = self._agent.get_uid()
        atr = self._agent.get_atr()

        fci = []
        resp = self._iso.send_select(b"")
        if resp.success:
            fci = parse_tlv(resp.data)

        return ProbeResult(uid=uid, atr=atr, fci=fci)

    @handles(SelectMessage)
    def _select(self, message: SelectMessage) -> SelectResult:
        resp = self._iso.send_select(message.aid, message.p1, message.p2)
        fci = parse_tlv(resp.data) if resp.data else []
        return SelectResult(fci=fci, sw=resp.sw)

    @handles(PutDataMessage)
    def _put_data(self, message: PutDataMessage) -> PutDataResult:
        resp = self._iso.send_put_data(message.tag, message.data)
        return PutDataResult(success=resp.success, sw=resp.sw)

    @handles(UpdateBinaryMessage)
    def _update_binary(self, message: UpdateBinaryMessage) -> UpdateBinaryResult:
        resp = self._iso.send_update_binary(message.offset, message.data, sfi=message.sfi)
        return UpdateBinaryResult(success=resp.success, sw=resp.sw)

    @handles(RawAPDUMessage)
    def _raw_apdu(self, message: RawAPDUMessage) -> RawAPDUResult:
        apdu = APDU(message.cla, message.ins, message.p1, message.p2,
                    message.data, message.le)
        response = self._agent.transmit(apdu)
        return RawAPDUResult(data=response.data, sw=response.sw)

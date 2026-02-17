from __future__ import annotations

import os

from gpexp.core.base import Agent
from gpexp.core.base.terminal import handles
from gpexp.core.generic import GenericTerminal
from cryptography.hazmat.decrepit.ciphers.algorithms import TripleDES
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from gpexp.core.gp.messages import (
    UPGRADE_START,
    AuthenticateMessage,
    AuthenticateResult,
    DeleteKeyMessage,
    DeleteKeyResult,
    DeleteMessage,
    DeleteResult,
    GetCardDataMessage,
    GetCardDataResult,
    GetCPLCMessage,
    GetCPLCResult,
    InstallMessage,
    InstallResult,
    ListContentsMessage,
    ListContentsResult,
    LoadMessage,
    LoadResult,
    ManageUpgradeMessage,
    ManageUpgradeResult,
    PutKeyMessage,
    SetStatusMessage,
    SetStatusResult,
    PutKeyResult,
)
from gpexp.core.gp.protocol import GP
from gpexp.core.gp import scp02, scp03
from gpexp.core.smartcard.tlv import parse as parse_tlv

from gpexp.core.gp.padding import pad80

_AES_KEY_TYPE = 0x88
_DES_KEY_TYPE = 0x80


def _encrypt_key_des_dek(dek: bytes, key: bytes) -> bytes:
    """Encrypt key value under a 3DES DEK (ECB mode)."""
    k = dek + dek[:8]
    cipher = Cipher(TripleDES(k), modes.ECB())
    enc = cipher.encryptor()
    return enc.update(key) + enc.finalize()


def _encrypt_key_aes_dek(dek: bytes, key: bytes) -> bytes:
    """Encrypt key value under an AES DEK (CBC mode, pad80)."""
    padded = pad80(key, 16)
    cipher = Cipher(algorithms.AES(dek), modes.CBC(b"\x00" * 16))
    enc = cipher.encryptor()
    return enc.update(padded) + enc.finalize()


def _des_kcv(key: bytes) -> bytes:
    """Compute 3-byte DES Key Check Value: 3DES-ECB(key, 00*8)[:3]."""
    k = key + key[:8]
    cipher = Cipher(TripleDES(k), modes.ECB())
    enc = cipher.encryptor()
    return (enc.update(b"\x00" * 8) + enc.finalize())[:3]


def _aes_kcv(key: bytes, *, zero_block: bool = False) -> bytes:
    """Compute 3-byte AES Key Check Value.

    Some cards expect AES KCV over 0x00*16 (esp. when loading via SCP02/3DES),
    while SCP03/AES deployments often use 0x01*16.
    """
    block = b"\x00" * 16 if zero_block else b"\x01" * 16
    cipher = Cipher(algorithms.AES(key), modes.ECB())
    enc = cipher.encryptor()
    return (enc.update(block) + enc.finalize())[:3]


def _build_put_key_data(
    new_kvn: int,
    keys: list[bytes],
    dek: bytes,
    aes_dek: bool,
    key_type: int,
) -> bytes:
    """Build PUT KEY data field for keys encrypted under DEK.

    AES format (GP Amd): type(1) | key_data_len(1) | key_value_len(1)
                         | encrypted(n) | kcv_len(1) | kcv(3)
    DES format:          type(1) | key_data_len(1) | encrypted(n)
                         | kcv_len(1) | kcv(3)
    """
    encrypt = _encrypt_key_aes_dek if aes_dek else _encrypt_key_des_dek
    aes_format = key_type == _AES_KEY_TYPE
    buf = bytearray([new_kvn])
    for key in keys:
        encrypted = encrypt(dek, key)
        kcv = _aes_kcv(key) if aes_format else _des_kcv(key)
        if aes_dek:
            # AES DEK format: type || length || key_value_length || encrypted || kcv_len || kcv
            buf.extend([key_type, 1 + len(encrypted), len(key)])
        else:
            # DES DEK format: type || length || encrypted || kcv_len || kcv
            buf.extend([key_type, len(encrypted)])
        buf.extend(encrypted)
        buf.extend([0x03])
        buf.extend(kcv)
    return bytes(buf)


class GPTerminal(GenericTerminal):
    """GP terminal — inherits Probe, adds GP card management messages."""

    def __init__(self, agent: Agent) -> None:
        super().__init__(agent)
        self._gp = GP(agent.transmit)
        self._static_keys: StaticKeys | None = None
        self._session_dek: bytes = b""
        self._aes_dek: bool = False

    @handles(GetCPLCMessage)
    def _get_cplc(self, message: GetCPLCMessage) -> GetCPLCResult:
        resp = self._iso.send_get_data(0x9F7F)
        data = None
        if resp.success:
            data = resp.data
            # Strip TLV wrapper if card returns 9F7F tag around the value
            if len(data) > 42:
                nodes = parse_tlv(data)
                if nodes and nodes[0].tag == 0x9F7F:
                    data = nodes[0].value
        return GetCPLCResult(cplc=data, sw=resp.sw)

    @handles(GetCardDataMessage)
    def _get_card_data(self, message: GetCardDataMessage) -> GetCardDataResult:
        results = {}
        for key, tag in [
            ("key_info", 0x00E0),
            ("card_recognition", 0x0066),
            ("iin", 0x0042),
            ("cin", 0x0045),
            ("seq_counter", 0x00C1),
        ]:
            resp = self._gp.send_get_data(tag)
            results[key] = resp.data if resp.success else None

        # Unwrap seq_counter: strip C1 TLV wrapper and convert to int
        raw = results.get("seq_counter")
        if raw is not None:
            nodes = parse_tlv(raw)
            if nodes and nodes[0].tag == 0xC1:
                raw = nodes[0].value
            results["seq_counter"] = int.from_bytes(raw, "big") if raw else None

        return GetCardDataResult(**results)

    @handles(ListContentsMessage)
    def _list_contents(self, message: ListContentsMessage) -> ListContentsResult:
        isd_data, apps_data, elf_data = self._gp.list_all_content()
        return ListContentsResult(
            isd=parse_tlv(isd_data) if isd_data else [],
            applications=parse_tlv(apps_data) if apps_data else [],
            packages=parse_tlv(elf_data) if elf_data else [],
        )

    @handles(AuthenticateMessage)
    def _authenticate(self, message: AuthenticateMessage) -> AuthenticateResult:
        host_challenge = os.urandom(8)

        init_resp = self._gp.send_initialize_update(
            message.key_version, message.key_id, host_challenge
        )
        if not init_resp.success:
            return AuthenticateResult(authenticated=False, sw=init_resp.sw)

        if len(init_resp.data) <= 11:
            return AuthenticateResult(
                authenticated=False, error="truncated response"
            )

        scp_id = init_resp.data[11]
        try:
            match scp_id:
                case 0x02:
                    setup = scp02.establish(
                        init_resp.data, message.keys, host_challenge, message.security_level
                    )
                case 0x03:
                    setup = scp03.establish(
                        init_resp.data, message.keys, host_challenge, message.security_level
                    )
                case _:
                    return AuthenticateResult(
                        authenticated=False, error=f"unsupported SCP {scp_id:#04x}"
                    )
        except ValueError as exc:
            return AuthenticateResult(authenticated=False, error=str(exc))

        self._static_keys = message.keys
        self._session_dek = setup.dek
        self._aes_dek = setup.aes_dek
        self._agent.open_channel(setup.channel)

        try:
            resp = self._gp.send_external_authenticate(
                message.security_level, setup.host_cryptogram
            )
        except Exception:
            self._agent.close_channel()
            raise

        if not resp.success:
            self._agent.close_channel()
            return AuthenticateResult(authenticated=False, sw=resp.sw)

        return AuthenticateResult(
            authenticated=True,
            key_diversification_data=init_resp.data[0:10],
            key_info=setup.key_info,
            scp_i=setup.i_param,
        )

    @handles(PutKeyMessage)
    def _put_key(self, message: PutKeyMessage) -> PutKeyResult:
        data = _build_put_key_data(
            message.new_kvn,
            [message.new_keys.enc, message.new_keys.mac, message.new_keys.dek],
            self._session_dek,
            self._aes_dek,
            message.key_type,
        )
        # GP: bit 8 of P2 = multiple keys in command data
        key_id = message.key_id | 0x80
        resp = self._gp.send_put_key(message.old_kvn, key_id, data)
        return PutKeyResult(success=resp.success, sw=resp.sw)

    @handles(DeleteKeyMessage)
    def _delete_key(self, message: DeleteKeyMessage) -> DeleteKeyResult:
        resp = self._gp.send_delete_key(message.key_version)
        return DeleteKeyResult(success=resp.success, sw=resp.sw)

    @handles(SetStatusMessage)
    def _set_status(self, message: SetStatusMessage) -> SetStatusResult:
        resp = self._gp.send_set_status(message.scope, message.status, message.aid)
        return SetStatusResult(success=resp.success, sw=resp.sw)

    @handles(DeleteMessage)
    def _delete(self, message: DeleteMessage) -> DeleteResult:
        resp = self._gp.send_delete(message.aid, message.related)
        return DeleteResult(success=resp.success, sw=resp.sw)

    @handles(LoadMessage)
    def _load(self, message: LoadMessage) -> LoadResult:
        # INSTALL [for load]: AID | SD AID | hash(0) | params(0) | token(0)
        buf = bytearray()
        buf.append(len(message.load_file_aid))
        buf.extend(message.load_file_aid)
        buf.append(len(message.sd_aid))
        buf.extend(message.sd_aid)
        buf.append(0x00)  # load file data block hash length
        buf.append(0x00)  # load parameters length
        buf.append(0x00)  # load token length

        resp = self._gp.send_install(0x02, 0x00, bytes(buf))
        if not resp.success:
            return LoadResult(
                success=False, blocks_sent=0, sw=resp.sw,
                error="INSTALL [for load] failed",
            )

        resp = self._gp.load_file(message.load_file_data, message.block_size)
        block_count = max(
            1,
            (len(message.load_file_data) + message.block_size - 1) // message.block_size,
        )
        return LoadResult(
            success=resp.success,
            blocks_sent=block_count if resp.success else 0,
            sw=resp.sw,
            error=None if resp.success else "LOAD failed",
        )

    @handles(InstallMessage)
    def _install(self, message: InstallMessage) -> InstallResult:
        instance_aid = message.instance_aid or message.module_aid

        # INSTALL [for install]: pkg AID | module AID | instance AID
        #                        | privileges | params | token(0)
        buf = bytearray()
        buf.append(len(message.package_aid))
        buf.extend(message.package_aid)
        buf.append(len(message.module_aid))
        buf.extend(message.module_aid)
        buf.append(len(instance_aid))
        buf.extend(instance_aid)
        buf.append(len(message.privileges))
        buf.extend(message.privileges)
        buf.append(len(message.params))
        buf.extend(message.params)
        buf.append(0x00)  # install token length

        p1 = 0x0C if message.make_selectable else 0x04
        resp = self._gp.send_install(p1, 0x00, bytes(buf))
        return InstallResult(success=resp.success, sw=resp.sw)

    @handles(ManageUpgradeMessage)
    def _manage_upgrade(self, message: ManageUpgradeMessage) -> ManageUpgradeResult:
        data = b""
        if message.action == UPGRADE_START:
            # Build A1 TLV: 4F <aid> [80 01 <options>]
            inner = bytes([0x4F, len(message.elf_aid)]) + message.elf_aid
            if message.options:
                inner += bytes([0x80, 0x01, message.options])
            data = bytes([0xA1, len(inner)]) + inner

        resp = self._gp.send_manage_elf_upgrade(message.action, data)
        if not resp.success:
            return ManageUpgradeResult(
                success=False, sw=resp.sw, error=f"SW={resp.sw:04X}"
            )

        session_status, elf_aid = self._parse_upgrade_response(resp.data)
        return ManageUpgradeResult(
            success=True, sw=resp.sw,
            session_status=session_status, elf_aid=elf_aid,
        )

    @staticmethod
    def _parse_upgrade_response(data: bytes) -> tuple[int | None, bytes | None]:
        """Extract session status and ELF AID from MANAGE ELF UPGRADE response.

        Response format: [confirmation_len][confirmation][session_info_len][session_info_tlv]
        Session info is an A1 TLV containing 90 (status) and optionally 4F (AID).
        """
        if not data:
            return None, None

        session_status = None
        elf_aid = None

        # Skip confirmation data (first length-prefixed block)
        offset = 0
        if offset >= len(data):
            return None, None
        conf_len = data[offset]
        offset += 1 + conf_len

        # Parse session info TLV block
        if offset < len(data):
            info_len = data[offset]
            offset += 1
            info_data = data[offset : offset + info_len]
            nodes = parse_tlv(info_data)
            for node in nodes:
                if node.tag == 0xA1:
                    inner = parse_tlv(node.value)
                    for child in inner:
                        if child.tag == 0x90 and child.value:
                            session_status = child.value[0]
                        elif child.tag == 0x4F:
                            elf_aid = child.value

        return session_status, elf_aid

"""SCP03 secure channel (GlobalPlatform 2.3, Amendment D)."""

from __future__ import annotations

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.cmac import CMAC

from gpexp.core.gp.padding import pad80
from gpexp.core.gp.security import C_DECRYPTION, C_MAC, R_MAC, SessionSetup, StaticKeys
from gpexp.core.smartcard.types import APDU, Response

# KDF derivation constants
_CARD_CRYPTOGRAM = 0x00
_HOST_CRYPTOGRAM = 0x01
_S_ENC = 0x04
_S_MAC = 0x06
_S_RMAC = 0x07


def _cmac(key: bytes, data: bytes) -> bytes:
    """Compute 16-byte AES-CMAC."""
    c = CMAC(algorithms.AES(key))
    c.update(data)
    return c.finalize()


def _kdf(key: bytes, constant: int, context: bytes, length_bits: int) -> bytes:
    """SCP03 KDF (NIST SP 800-108 counter mode, AES-CMAC PRF).

    Derivation data per iteration (32 bytes):
      [00]*11 || constant || 00 || L (2 bytes) || counter || context (16 bytes)

    For outputs > 128 bits, multiple iterations with incrementing counter
    are concatenated and truncated to the requested length.
    """
    length_bytes = (length_bits + 7) // 8
    # Each AES-CMAC iteration produces 16 bytes
    n_blocks = (length_bytes + 15) // 16
    result = b""
    for counter in range(1, n_blocks + 1):
        data = (
            b"\x00" * 11
            + bytes([constant])
            + b"\x00"
            + length_bits.to_bytes(2, "big")
            + bytes([counter])
            + context
        )
        result += _cmac(key, data)
    return result[:length_bytes]


def derive_session_keys(
    static_keys: StaticKeys,
    host_challenge: bytes,
    card_challenge: bytes,
) -> tuple[bytes, bytes, bytes]:
    """Derive session keys (S-ENC, S-MAC, S-RMAC).

    Session key length matches the static key length (128/192/256 bits).
    """
    context = host_challenge + card_challenge
    key_bits = len(static_keys.enc) * 8
    s_enc = _kdf(static_keys.enc, _S_ENC, context, key_bits)
    s_mac = _kdf(static_keys.mac, _S_MAC, context, key_bits)
    s_rmac = _kdf(static_keys.mac, _S_RMAC, context, key_bits)
    return s_enc, s_mac, s_rmac


def verify_card_cryptogram(
    s_mac: bytes,
    host_challenge: bytes,
    card_challenge: bytes,
    received: bytes,
) -> bool:
    """Verify the card cryptogram from INITIALIZE UPDATE."""
    context = host_challenge + card_challenge
    expected = _kdf(s_mac, _CARD_CRYPTOGRAM, context, 0x0040)[:8]
    return expected == received


def compute_host_cryptogram(
    s_mac: bytes,
    host_challenge: bytes,
    card_challenge: bytes,
) -> bytes:
    """Compute the host cryptogram for EXTERNAL AUTHENTICATE."""
    context = host_challenge + card_challenge
    return _kdf(s_mac, _HOST_CRYPTOGRAM, context, 0x0040)[:8]


# -- session establishment ----------------------------------------------------


def establish(
    init_update_data: bytes,
    static_keys: StaticKeys,
    host_challenge: bytes,
    security_level: int,
) -> SessionSetup:
    """Parse INITIALIZE UPDATE response, derive keys, verify, build channel.

    Raises ValueError on truncated data or card cryptogram mismatch.
    """
    if len(init_update_data) < 29:
        raise ValueError("truncated INITIALIZE UPDATE response")

    key_info = init_update_data[10:13]
    i_param = key_info[2]
    card_challenge = init_update_data[13:21]
    card_cryptogram = init_update_data[21:29]

    s_enc, s_mac, s_rmac = derive_session_keys(
        static_keys, host_challenge, card_challenge
    )

    if not verify_card_cryptogram(
        s_mac, host_challenge, card_challenge, card_cryptogram
    ):
        raise ValueError("card cryptogram mismatch")

    host_cryptogram = compute_host_cryptogram(
        s_mac, host_challenge, card_challenge
    )

    channel = SCP03Channel(s_enc, s_mac, s_rmac, static_keys.dek, security_level)

    return SessionSetup(
        key_info=key_info,
        i_param=i_param,
        host_cryptogram=host_cryptogram,
        channel=channel,
    )


class SCP03Channel:
    """SCP03 secure channel — wraps/unwraps APDUs after authentication.

    Installed on the agent after a successful INITIALIZE UPDATE /
    EXTERNAL AUTHENTICATE handshake.  All subsequent APDUs are routed
    through wrap() and unwrap() by Agent.transmit().
    """

    def __init__(
        self,
        s_enc: bytes,
        s_mac: bytes,
        s_rmac: bytes,
        dek: bytes,
        security_level: int,
    ) -> None:
        self._s_enc = s_enc
        self._s_mac = s_mac
        self._s_rmac = s_rmac
        self._dek = dek
        self._security_level = security_level
        self._mac_chain = b"\x00" * 16
        self._enc_counter = 1

    @property
    def security_level(self) -> int:
        return self._security_level

    @property
    def dek(self) -> bytes:
        return self._dek

    def _next_enc_icv(self) -> bytes:
        """Derive encryption ICV from counter, then increment."""
        block = self._enc_counter.to_bytes(16, "big")
        cipher = Cipher(algorithms.AES(self._s_enc), modes.ECB())
        enc = cipher.encryptor()
        icv = enc.update(block) + enc.finalize()
        self._enc_counter += 1
        return icv

    def wrap(self, apdu: APDU) -> APDU:
        """Apply C-MAC (and optionally C-DECRYPTION) to an outgoing command."""
        if not (self._security_level & C_MAC) and apdu.ins != 0x82:
            return apdu

        data = apdu.data

        # Encrypt command data if required (before MAC)
        if (self._security_level & C_DECRYPTION) and data:
            icv = self._next_enc_icv()
            padded = pad80(data, 16)
            cipher = Cipher(algorithms.AES(self._s_enc), modes.CBC(icv))
            enc = cipher.encryptor()
            data = enc.update(padded) + enc.finalize()

        # CLA with secure messaging indicator (bit 2)
        cla = apdu.cla | 0x04

        # MAC input: chaining value || header (with Lc including MAC) || data
        lc = len(data) + 8
        mac_input = (
            self._mac_chain
            + bytes([cla, apdu.ins, apdu.p1, apdu.p2, lc])
            + data
        )
        full_mac = _cmac(self._s_mac, mac_input)
        self._mac_chain = full_mac

        return APDU(
            cla=cla,
            ins=apdu.ins,
            p1=apdu.p1,
            p2=apdu.p2,
            data=data + full_mac[:8],
            le=apdu.le,
        )

    def unwrap(self, response: Response) -> Response:
        """Verify R-MAC (and optionally R-ENCRYPTION) on an incoming response."""
        if not (self._security_level & R_MAC):
            return response

        data = response.data
        if len(data) < 8:
            return response

        payload = data[:-8]
        r_mac = data[-8:]

        # R-MAC: chaining value || payload || SW
        mac_input = (
            self._mac_chain + payload + bytes([response.sw1, response.sw2])
        )
        expected = _cmac(self._s_rmac, mac_input)[:8]
        if expected != r_mac:
            raise ValueError("R-MAC verification failed")

        return Response(data=payload, sw1=response.sw1, sw2=response.sw2)

"""SCP02 secure channel (GlobalPlatform 2.1.1 / 2.2)."""

from __future__ import annotations

from cryptography.hazmat.decrepit.ciphers.algorithms import TripleDES
from cryptography.hazmat.primitives.ciphers import Cipher, modes

from gpexp.core.gp.padding import pad80
from gpexp.core.gp.security import C_DECRYPTION, R_MAC, SessionSetup, StaticKeys
from gpexp.core.smartcard.types import APDU, Response

# Key derivation constants
_DERIV_S_ENC = b"\x01\x82"
_DERIV_S_MAC = b"\x01\x01"
_DERIV_S_RMAC = b"\x01\x02"
_DERIV_S_DEK = b"\x01\x81"

_ZERO_ICV = b"\x00" * 8


def _tdes_key(key_2k: bytes) -> bytes:
    """Expand 16-byte 2-key 3DES key to 24-byte (K1, K2, K1)."""
    return key_2k + key_2k[:8]


def _tdes_ecb(key_2k: bytes, block: bytes) -> bytes:
    """Single-block 3DES-ECB encrypt (full two-key 3DES)."""
    cipher = Cipher(TripleDES(_tdes_key(key_2k)), modes.ECB())
    enc = cipher.encryptor()
    return enc.update(block) + enc.finalize()


def _des_ecb(key_2k: bytes, block: bytes) -> bytes:
    """Single-block one-key 3DES-ECB encrypt (K1 only, equivalent to single DES)."""
    k1 = key_2k[:8] * 3
    cipher = Cipher(TripleDES(k1), modes.ECB())
    enc = cipher.encryptor()
    return enc.update(block) + enc.finalize()


def _tdes_cbc(key_2k: bytes, iv: bytes, data: bytes) -> bytes:
    """3DES-CBC encrypt."""
    cipher = Cipher(TripleDES(_tdes_key(key_2k)), modes.CBC(iv))
    enc = cipher.encryptor()
    return enc.update(data) + enc.finalize()


def _full_mac(key_2k: bytes, icv: bytes, data: bytes) -> bytes:
    """Full 3DES-CBC-MAC (ISO 9797-1 Algorithm 1), Method 2 padding.

    All blocks processed with full 3DES; returns the last 8-byte block.
    Used for card/host cryptogram computation.
    """
    padded = pad80(data, 8)
    ct = _tdes_cbc(key_2k, icv, padded)
    return ct[-8:]


def _retail_mac(key_2k: bytes, icv: bytes, data: bytes) -> bytes:
    """ISO 9797-1 Algorithm 3 (Retail MAC), Method 2 padding.

    Single-DES-CBC (K1) for blocks 1..n-1, full 2-key 3DES for block n.
    Returns 8-byte MAC.  Used for C-MAC / R-MAC.
    """
    padded = pad80(data, 8)
    k1_3 = key_2k[:8] * 3
    k_full = _tdes_key(key_2k)
    cv = icv
    n = len(padded) // 8
    for i in range(n):
        xored = bytes(a ^ b for a, b in zip(padded[i * 8 : (i + 1) * 8], cv))
        k = k_full if i == n - 1 else k1_3
        cipher = Cipher(TripleDES(k), modes.ECB())
        enc = cipher.encryptor()
        cv = enc.update(xored) + enc.finalize()
    return cv


# -- key derivation ----------------------------------------------------------


def derive_session_keys(
    static_keys: StaticKeys,
    sequence_counter: bytes,
) -> tuple[bytes, bytes, bytes, bytes]:
    """Derive SCP02 session keys from static keys and 2-byte sequence counter."""

    def _derive(key: bytes, constant: bytes) -> bytes:
        block = constant + sequence_counter + b"\x00" * 12
        return _tdes_cbc(key, _ZERO_ICV, block)

    s_enc = _derive(static_keys.enc, _DERIV_S_ENC)
    s_mac = _derive(static_keys.mac, _DERIV_S_MAC)
    s_rmac = _derive(static_keys.mac, _DERIV_S_RMAC)
    s_dek = _derive(static_keys.dek, _DERIV_S_DEK) if static_keys.dek else b""
    return s_enc, s_mac, s_rmac, s_dek


# -- cryptograms -------------------------------------------------------------


def verify_card_cryptogram(
    s_enc: bytes,
    host_challenge: bytes,
    sequence_counter: bytes,
    card_challenge: bytes,
    received: bytes,
) -> bool:
    """Verify the card cryptogram from INITIALIZE UPDATE."""
    data = host_challenge + sequence_counter + card_challenge
    expected = _full_mac(s_enc, _ZERO_ICV, data)
    return expected == received


def compute_host_cryptogram(
    s_enc: bytes,
    host_challenge: bytes,
    sequence_counter: bytes,
    card_challenge: bytes,
) -> bytes:
    """Compute the host cryptogram for EXTERNAL AUTHENTICATE."""
    data = sequence_counter + card_challenge + host_challenge
    return _full_mac(s_enc, _ZERO_ICV, data)


# -- session establishment ----------------------------------------------------

_DEFAULT_I_PARAM = 0x15  # modified APDU, ICV encryption, R-MAC


def establish(
    init_update_data: bytes,
    static_keys: StaticKeys,
    host_challenge: bytes,
    security_level: int,
    i_param: int = _DEFAULT_I_PARAM,
) -> SessionSetup:
    """Parse INITIALIZE UPDATE response, derive keys, verify, build channel.

    Raises ValueError on truncated data or card cryptogram mismatch.
    """
    if len(init_update_data) < 28:
        raise ValueError("truncated INITIALIZE UPDATE response")

    key_info = init_update_data[10:12]
    sequence_counter = init_update_data[12:14]
    card_challenge = init_update_data[14:20]
    card_cryptogram = init_update_data[20:28]

    s_enc, s_mac, s_rmac, s_dek = derive_session_keys(static_keys, sequence_counter)

    if not verify_card_cryptogram(
        s_enc, host_challenge, sequence_counter,
        card_challenge, card_cryptogram,
    ):
        raise ValueError("card cryptogram mismatch")

    host_cryptogram = compute_host_cryptogram(
        s_enc, host_challenge, sequence_counter, card_challenge
    )

    channel = SCP02Channel(s_enc, s_mac, s_rmac, s_dek, security_level, i_param)

    return SessionSetup(
        key_info=key_info,
        i_param=i_param,
        host_cryptogram=host_cryptogram,
        channel=channel,
    )


# -- channel ------------------------------------------------------------------


class SCP02Channel:
    """SCP02 secure channel — wraps/unwraps APDUs after authentication.

    Installed on the agent after a successful INITIALIZE UPDATE /
    EXTERNAL AUTHENTICATE handshake.  All subsequent APDUs are routed
    through wrap() and unwrap() by Agent.transmit().

    The *i_param* controls ICV handling and MAC scope (GP 2.3 Table D-6):
      bit 1 (0x01): 0=C-MAC on unmodified APDU, 1=C-MAC on modified APDU
      bit 3 (0x04): 0=no ICV encryption, 1=ICV encrypted with S-MAC
      bit 5 (0x10): R-MAC support
      bit 7 (0x40): well-known card challenge
    """

    def __init__(
        self,
        s_enc: bytes,
        s_mac: bytes,
        s_rmac: bytes,
        s_dek: bytes,
        security_level: int,
        i_param: int,
    ) -> None:
        self._s_enc = s_enc
        self._s_mac = s_mac
        self._s_rmac = s_rmac
        self._dek = s_dek
        self._security_level = security_level
        self._i_param = i_param
        self._icv = _ZERO_ICV
        self._last_c_mac = _ZERO_ICV

    @property
    def security_level(self) -> int:
        return self._security_level

    @property
    def dek(self) -> bytes:
        return self._dek

    def _next_icv(self) -> bytes:
        """Return the ICV for the next C-MAC computation."""
        icv = self._icv
        # Encrypt chaining value when bit 3 (0x04) is set (skip for initial zero).
        # GP spec: "one key Triple DES in ECB mode" — K1 of the S-MAC key only.
        if icv != _ZERO_ICV and (self._i_param & 0x04):
            icv = _des_ecb(self._s_mac, icv)
        return icv

    def wrap(self, apdu: APDU) -> APDU:
        """Apply C-MAC (and optionally C-DECRYPTION) to an outgoing command."""
        data = apdu.data

        # Encrypt command data if required (skip EXTERNAL AUTHENTICATE)
        if (self._security_level & C_DECRYPTION) and data and apdu.ins != 0x82:
            data = _tdes_cbc(self._s_enc, _ZERO_ICV, pad80(data, 8))

        # CLA with secure messaging indicator (bit 2)
        cla = apdu.cla | 0x04
        lc = len(data) + 8

        # Build MAC input — bit 1 (0x01): 0=unmodified APDU, 1=modified APDU
        if self._i_param & 0x01:
            # Modified APDU (CLA with secure messaging bit, Lc includes MAC)
            mac_input = bytes([cla, apdu.ins, apdu.p1, apdu.p2, lc]) + data
        else:
            # Unmodified APDU (original CLA, original Lc)
            mac_input = bytes([apdu.cla, apdu.ins, apdu.p1, apdu.p2])
            if apdu.data:
                mac_input += bytes([len(apdu.data)]) + apdu.data

        icv = self._next_icv()
        c_mac = _retail_mac(self._s_mac, icv, mac_input)
        self._icv = c_mac
        self._last_c_mac = c_mac

        return APDU(
            cla=cla,
            ins=apdu.ins,
            p1=apdu.p1,
            p2=apdu.p2,
            data=data + c_mac,
            le=apdu.le,
        )

    def unwrap(self, response: Response) -> Response:
        """Verify R-MAC on an incoming response."""
        if not (self._security_level & R_MAC):
            return response

        data = response.data
        if len(data) < 8:
            return response

        payload = data[:-8]
        r_mac = data[-8:]

        mac_input = payload + bytes([response.sw1, response.sw2])
        expected = _retail_mac(self._s_rmac, self._last_c_mac, mac_input)
        if expected != r_mac:
            raise ValueError("R-MAC verification failed")

        return Response(data=payload, sw1=response.sw1, sw2=response.sw2)

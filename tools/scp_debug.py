#!/usr/bin/env python3
"""Standalone SCP02/SCP03 session key derivation debugger.

Takes INITIALIZE UPDATE inputs and response, computes and displays all
derivation steps, session keys, cryptograms, and the EXTERNAL AUTHENTICATE
APDU.  No project dependencies — only the 'cryptography' library is required.

Usage examples:

  SCP02:
    python scp_debug.py scp02 \\
      --keys 404142434445464748494A4B4C4D4E4F:404142434445464748494A4B4C4D4E4F:404142434445464748494A4B4C4D4E4F \\
      --host-challenge A0A1A2A3A4A5A6A7 \\
      --init-update-response 00000000000000000000FF02001C7E8283EED5BF5F0E7E5B2B1F4B0A6A1FCA34F0

  SCP03:
    python scp_debug.py scp03 \\
      --keys 404142434445464748494A4B4C4D4E4F:404142434445464748494A4B4C4D4E4F:404142434445464748494A4B4C4D4E4F \\
      --host-challenge A0A1A2A3A4A5A6A7 \\
      --init-update-response 00000000000000000000FF030060B0B1B2B3B4B5B6B7C0C1C2C3C4C5C6C7

  Provide security level to compute the full EXTERNAL AUTHENTICATE APDU with MAC:
    python scp_debug.py scp03 ... --security-level 33
"""

from __future__ import annotations

import argparse
import sys

# ---------------------------------------------------------------------------
# Cryptographic primitives
# ---------------------------------------------------------------------------

from cryptography.hazmat.decrepit.ciphers.algorithms import TripleDES
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.cmac import CMAC


def _hex(data: bytes) -> str:
    return data.hex().upper()


def _hex_spaced(data: bytes) -> str:
    return " ".join(f"{b:02X}" for b in data)


# -- padding ----------------------------------------------------------------

def _pad80(data: bytes, block_size: int) -> bytes:
    """ISO 9797-1 Method 2 padding."""
    return data + b"\x80" + b"\x00" * ((-len(data) - 1) % block_size)


# -- 3DES helpers (SCP02) --------------------------------------------------

def _tdes_key(key_2k: bytes) -> bytes:
    """Expand 16-byte 2-key 3DES to 24-byte (K1, K2, K1)."""
    return key_2k + key_2k[:8]


def _tdes_ecb(key_2k: bytes, block: bytes) -> bytes:
    cipher = Cipher(TripleDES(_tdes_key(key_2k)), modes.ECB())
    return cipher.encryptor().update(block) + cipher.encryptor().finalize()


def _des_ecb(key_2k: bytes, block: bytes) -> bytes:
    """Single-DES ECB using K1 of a 2-key 3DES key."""
    k1 = key_2k[:8] * 3
    cipher = Cipher(TripleDES(k1), modes.ECB())
    enc = cipher.encryptor()
    return enc.update(block) + enc.finalize()


def _tdes_cbc(key_2k: bytes, iv: bytes, data: bytes) -> bytes:
    cipher = Cipher(TripleDES(_tdes_key(key_2k)), modes.CBC(iv))
    enc = cipher.encryptor()
    return enc.update(data) + enc.finalize()


def _full_tdes_mac(key_2k: bytes, icv: bytes, data: bytes) -> bytes:
    """Full 3DES-CBC-MAC — all blocks with full 3DES, returns last 8 bytes."""
    padded = _pad80(data, 8)
    ct = _tdes_cbc(key_2k, icv, padded)
    return ct[-8:]


def _retail_mac(key_2k: bytes, icv: bytes, data: bytes) -> bytes:
    """ISO 9797-1 Algorithm 3 (Retail MAC), Method 2 padding.

    Single-DES (K1) for blocks 1..n-1, full 3DES for block n.
    """
    padded = _pad80(data, 8)
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


# -- AES helpers (SCP03) ---------------------------------------------------

def _aes_cmac(key: bytes, data: bytes) -> bytes:
    """Compute 16-byte AES-CMAC."""
    c = CMAC(algorithms.AES(key))
    c.update(data)
    return c.finalize()


def _scp03_kdf(key: bytes, constant: int, context: bytes, length_bits: int) -> bytes:
    """SCP03 KDF — NIST SP 800-108 counter mode with AES-CMAC PRF.

    Derivation data per iteration (32 bytes):
      [00]*11 || constant || 00 || L (2 bytes big-endian) || counter || context
    """
    length_bytes = (length_bits + 7) // 8
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
        result += _aes_cmac(key, data)
    return result[:length_bytes]


# ---------------------------------------------------------------------------
# SCP02 debug
# ---------------------------------------------------------------------------

_SCP02_DERIV = {
    "S-ENC":  b"\x01\x82",
    "S-MAC":  b"\x01\x01",
    "S-RMAC": b"\x01\x02",
    "S-DEK":  b"\x01\x81",
}

_ZERO_ICV_8 = b"\x00" * 8


def debug_scp02(
    enc_key: bytes,
    mac_key: bytes,
    dek_key: bytes,
    host_challenge: bytes,
    init_update_response: bytes,
    security_level: int,
    i_param: int,
) -> None:
    print("=" * 72)
    print("SCP02 Session Derivation Debug")
    print("=" * 72)

    # -- Parse INITIALIZE UPDATE response -----------------------------------
    print("\n--- INITIALIZE UPDATE Response Parsing ---\n")
    print(f"  Raw response ({len(init_update_response)} bytes): {_hex(init_update_response)}")

    if len(init_update_response) < 28:
        print(f"\n  ERROR: response too short (need >= 28 bytes, got {len(init_update_response)})")
        sys.exit(1)

    key_div_data = init_update_response[0:10]
    key_info = init_update_response[10:12]
    seq_counter = init_update_response[12:14]
    card_challenge = init_update_response[14:20]
    card_cryptogram = init_update_response[20:28]

    print(f"  Key diversification data: {_hex(key_div_data)}")
    print(f"  Key information:          {_hex(key_info)}  (SCP{key_info[0]:02X}, i={key_info[1]:02X})")
    print(f"  Sequence counter:         {_hex(seq_counter)}")
    print(f"  Card challenge:           {_hex(card_challenge)}")
    print(f"  Card cryptogram:          {_hex(card_cryptogram)}")

    # -- Static keys --------------------------------------------------------
    print("\n--- Static Keys ---\n")
    print(f"  ENC: {_hex(enc_key)}")
    print(f"  MAC: {_hex(mac_key)}")
    print(f"  DEK: {_hex(dek_key) if dek_key else '(not provided)'}")

    # -- Input summary ------------------------------------------------------
    print("\n--- Input Summary ---\n")
    print(f"  Host challenge:    {_hex(host_challenge)}")
    print(f"  Sequence counter:  {_hex(seq_counter)}")
    print(f"  Security level:    0x{security_level:02X}", end="")
    flags = []
    if security_level & 0x01: flags.append("C-MAC")
    if security_level & 0x02: flags.append("C-DEC")
    if security_level & 0x10: flags.append("R-MAC")
    if security_level & 0x20: flags.append("R-ENC")
    print(f"  ({' | '.join(flags)})" if flags else "")
    print(f"  i parameter:       0x{i_param:02X}")

    # -- Session key derivation ---------------------------------------------
    print("\n--- Session Key Derivation ---\n")
    print("  Algorithm: 3DES-CBC with zero ICV")
    print("  Derivation block = constant(2) || seq_counter(2) || 0x00 * 12\n")

    keys_map = {
        "S-ENC":  enc_key,
        "S-MAC":  mac_key,
        "S-RMAC": mac_key,
        "S-DEK":  dek_key,
    }

    session_keys = {}
    for name, constant in _SCP02_DERIV.items():
        static_key = keys_map[name]
        if name == "S-DEK" and not static_key:
            print(f"  {name}: skipped (no DEK provided)")
            continue
        block = constant + seq_counter + b"\x00" * 12
        result = _tdes_cbc(static_key, _ZERO_ICV_8, block)
        session_keys[name] = result

        print(f"  {name}:")
        print(f"    Static key:       {_hex(static_key)}")
        print(f"    Constant:         {_hex(constant)}")
        print(f"    Derivation block: {_hex(block)}")
        print(f"    3DES-CBC result:  {_hex(result)}")
        print()

    s_enc = session_keys["S-ENC"]
    s_mac = session_keys["S-MAC"]
    s_rmac = session_keys["S-RMAC"]
    s_dek = session_keys.get("S-DEK", b"")

    # -- Card cryptogram verification ---------------------------------------
    print("--- Card Cryptogram Verification ---\n")
    crypt_data = host_challenge + seq_counter + card_challenge
    padded_crypt = _pad80(crypt_data, 8)
    expected_card_crypt = _full_tdes_mac(s_enc, _ZERO_ICV_8, crypt_data)

    print(f"  Input data:  host_challenge || seq_counter || card_challenge")
    print(f"               {_hex(host_challenge)} || {_hex(seq_counter)} || {_hex(card_challenge)}")
    print(f"  Concatenated: {_hex(crypt_data)}")
    print(f"  Padded (M2):  {_hex(padded_crypt)}")
    print(f"  Key (S-ENC):  {_hex(s_enc)}")
    print(f"  ICV:          {_hex(_ZERO_ICV_8)}")
    print(f"  Full 3DES-CBC-MAC (last 8 bytes of CBC output):")
    print(f"    Computed:   {_hex(expected_card_crypt)}")
    print(f"    Received:   {_hex(card_cryptogram)}")
    match = expected_card_crypt == card_cryptogram
    print(f"    MATCH:      {'YES' if match else 'NO  *** MISMATCH ***'}")

    # -- Host cryptogram computation ----------------------------------------
    print("\n--- Host Cryptogram Computation ---\n")
    host_data = seq_counter + card_challenge + host_challenge
    padded_host = _pad80(host_data, 8)
    host_cryptogram = _full_tdes_mac(s_enc, _ZERO_ICV_8, host_data)

    print(f"  Input data:  seq_counter || card_challenge || host_challenge")
    print(f"               {_hex(seq_counter)} || {_hex(card_challenge)} || {_hex(host_challenge)}")
    print(f"  Concatenated: {_hex(host_data)}")
    print(f"  Padded (M2):  {_hex(padded_host)}")
    print(f"  Key (S-ENC):  {_hex(s_enc)}")
    print(f"  ICV:          {_hex(_ZERO_ICV_8)}")
    print(f"  Host cryptogram: {_hex(host_cryptogram)}")

    # -- EXTERNAL AUTHENTICATE APDU -----------------------------------------
    print("\n--- EXTERNAL AUTHENTICATE APDU ---\n")
    _build_ext_auth_scp02(s_mac, host_cryptogram, security_level, i_param)

    # -- Session keys summary -----------------------------------------------
    print("\n--- Session Keys Summary ---\n")
    print(f"  S-ENC:  {_hex(s_enc)}")
    print(f"  S-MAC:  {_hex(s_mac)}")
    print(f"  S-RMAC: {_hex(s_rmac)}")
    if s_dek:
        print(f"  S-DEK:  {_hex(s_dek)}")
    print()


def _build_ext_auth_scp02(
    s_mac: bytes,
    host_cryptogram: bytes,
    security_level: int,
    i_param: int,
) -> None:
    """Build and display the EXTERNAL AUTHENTICATE APDU with C-MAC (SCP02)."""
    # The EXTERNAL AUTHENTICATE is always MACed through the channel.
    # CLA = 0x84 (secure messaging), INS = 0x82, P1 = security_level, P2 = 0x00
    cla = 0x84
    ins = 0x82
    p1 = security_level
    p2 = 0x00
    data = host_cryptogram

    # ICV for first command is always zero
    icv = _ZERO_ICV_8

    # Build MAC input based on i_param bit 1
    lc_with_mac = len(data) + 8  # 16
    if i_param & 0x01:
        # Modified APDU: CLA with secure messaging, Lc includes MAC
        mac_input = bytes([cla, ins, p1, p2, lc_with_mac]) + data
        print(f"  MAC mode:     modified APDU (i_param bit 0 set)")
    else:
        # Unmodified APDU: original CLA, original Lc
        mac_input = bytes([cla, ins, p1, p2, len(data)]) + data
        print(f"  MAC mode:     unmodified APDU (i_param bit 0 clear)")

    print(f"  MAC input:    {_hex(mac_input)}")
    padded_mac = _pad80(mac_input, 8)
    print(f"  Padded (M2):  {_hex(padded_mac)}")
    print(f"  Key (S-MAC):  {_hex(s_mac)}")
    print(f"  ICV:          {_hex(icv)}  (first command, always zero)")

    c_mac = _retail_mac(s_mac, icv, mac_input)
    print(f"  C-MAC:        {_hex(c_mac)}")

    apdu_data = data + c_mac
    apdu = bytes([cla, ins, p1, p2, len(apdu_data)]) + apdu_data
    print(f"\n  EXTERNAL AUTHENTICATE APDU:")
    print(f"    {_hex_spaced(apdu)}")


# ---------------------------------------------------------------------------
# SCP03 debug
# ---------------------------------------------------------------------------

_SCP03_DERIV = {
    "S-ENC":  0x04,
    "S-MAC":  0x06,
    "S-RMAC": 0x07,
}


def debug_scp03(
    enc_key: bytes,
    mac_key: bytes,
    dek_key: bytes,
    host_challenge: bytes,
    init_update_response: bytes,
    security_level: int,
) -> None:
    print("=" * 72)
    print("SCP03 Session Derivation Debug")
    print("=" * 72)

    # -- Parse INITIALIZE UPDATE response -----------------------------------
    print("\n--- INITIALIZE UPDATE Response Parsing ---\n")
    print(f"  Raw response ({len(init_update_response)} bytes): {_hex(init_update_response)}")

    if len(init_update_response) < 29:
        print(f"\n  ERROR: response too short (need >= 29 bytes, got {len(init_update_response)})")
        sys.exit(1)

    key_div_data = init_update_response[0:10]
    key_info = init_update_response[10:13]
    card_challenge = init_update_response[13:21]
    card_cryptogram = init_update_response[21:29]
    i_param = key_info[2]

    print(f"  Key diversification data: {_hex(key_div_data)}")
    print(f"  Key information:          {_hex(key_info)}  (ver={key_info[0]:02X}, SCP{key_info[1]:02X}, i={i_param:02X})")
    print(f"  Card challenge:           {_hex(card_challenge)}")
    print(f"  Card cryptogram:          {_hex(card_cryptogram)}")

    # -- Static keys --------------------------------------------------------
    print("\n--- Static Keys ---\n")
    print(f"  ENC: {_hex(enc_key)}  ({len(enc_key)*8} bits)")
    print(f"  MAC: {_hex(mac_key)}  ({len(mac_key)*8} bits)")
    print(f"  DEK: {_hex(dek_key) if dek_key else '(not provided)'}")

    # -- Input summary ------------------------------------------------------
    print("\n--- Input Summary ---\n")
    print(f"  Host challenge:    {_hex(host_challenge)}")
    context = host_challenge + card_challenge
    print(f"  KDF context:       host_challenge || card_challenge")
    print(f"                     {_hex(context)}")
    key_bits = len(enc_key) * 8
    print(f"  Output key length: {key_bits} bits")
    print(f"  Security level:    0x{security_level:02X}", end="")
    flags = []
    if security_level & 0x01: flags.append("C-MAC")
    if security_level & 0x02: flags.append("C-DEC")
    if security_level & 0x10: flags.append("R-MAC")
    if security_level & 0x20: flags.append("R-ENC")
    print(f"  ({' | '.join(flags)})" if flags else "")

    # -- Session key derivation ---------------------------------------------
    print("\n--- Session Key Derivation (NIST SP 800-108 counter mode) ---\n")
    print("  KDF(key, constant, context, L):")
    print("    derivation_data = 00*11 || constant || 00 || L(2) || counter || context(16)")
    print("    output = AES-CMAC(key, derivation_data)")
    n_blocks = (key_bits // 8 + 15) // 16
    if n_blocks > 1:
        print(f"    ({n_blocks} blocks needed for {key_bits}-bit keys)")
    print()

    keys_map = {
        "S-ENC":  enc_key,
        "S-MAC":  mac_key,
        "S-RMAC": mac_key,
    }

    session_keys = {}
    for name, constant in _SCP03_DERIV.items():
        static_key = keys_map[name]
        length_bytes = len(static_key)
        n_iter = (length_bytes + 15) // 16
        result = b""

        print(f"  {name} (constant=0x{constant:02X}):")
        print(f"    Static key:  {_hex(static_key)}")

        for counter in range(1, n_iter + 1):
            deriv_data = (
                b"\x00" * 11
                + bytes([constant])
                + b"\x00"
                + key_bits.to_bytes(2, "big")
                + bytes([counter])
                + context
            )
            block_result = _aes_cmac(static_key, deriv_data)
            result += block_result

            label = "" if n_iter == 1 else f" (block {counter})"
            print(f"    Derivation data{label}: {_hex(deriv_data)}")
            print(f"    AES-CMAC result{label}: {_hex(block_result)}")

        session_key = result[:length_bytes]
        session_keys[name] = session_key
        print(f"    Session key: {_hex(session_key)}")
        print()

    s_enc = session_keys["S-ENC"]
    s_mac = session_keys["S-MAC"]
    s_rmac = session_keys["S-RMAC"]

    # -- Card cryptogram verification ---------------------------------------
    print("--- Card Cryptogram Verification ---\n")
    print(f"  KDF(S-MAC, constant=0x00, context, 64 bits)")
    deriv_data = (
        b"\x00" * 11
        + bytes([0x00])
        + b"\x00"
        + (0x0040).to_bytes(2, "big")
        + bytes([0x01])
        + context
    )
    full_result = _aes_cmac(s_mac, deriv_data)
    expected_card_crypt = full_result[:8]

    print(f"  Key (S-MAC):      {_hex(s_mac)}")
    print(f"  Derivation data:  {_hex(deriv_data)}")
    print(f"  AES-CMAC output:  {_hex(full_result)}")
    print(f"  Truncated to 8B:  {_hex(expected_card_crypt)}")
    print(f"  Received:         {_hex(card_cryptogram)}")
    match = expected_card_crypt == card_cryptogram
    print(f"  MATCH:            {'YES' if match else 'NO  *** MISMATCH ***'}")

    # -- Host cryptogram computation ----------------------------------------
    print("\n--- Host Cryptogram Computation ---\n")
    print(f"  KDF(S-MAC, constant=0x01, context, 64 bits)")
    deriv_data = (
        b"\x00" * 11
        + bytes([0x01])
        + b"\x00"
        + (0x0040).to_bytes(2, "big")
        + bytes([0x01])
        + context
    )
    full_result = _aes_cmac(s_mac, deriv_data)
    host_cryptogram = full_result[:8]

    print(f"  Key (S-MAC):      {_hex(s_mac)}")
    print(f"  Derivation data:  {_hex(deriv_data)}")
    print(f"  AES-CMAC output:  {_hex(full_result)}")
    print(f"  Host cryptogram:  {_hex(host_cryptogram)}")

    # -- EXTERNAL AUTHENTICATE APDU -----------------------------------------
    print("\n--- EXTERNAL AUTHENTICATE APDU ---\n")
    _build_ext_auth_scp03(s_mac, host_cryptogram, security_level)

    # -- Session keys summary -----------------------------------------------
    print("\n--- Session Keys Summary ---\n")
    print(f"  S-ENC:  {_hex(s_enc)}")
    print(f"  S-MAC:  {_hex(s_mac)}")
    print(f"  S-RMAC: {_hex(s_rmac)}")
    if dek_key:
        print(f"  DEK:    {_hex(dek_key)}  (static key passed through in SCP03)")
    print()


def _build_ext_auth_scp03(
    s_mac: bytes,
    host_cryptogram: bytes,
    security_level: int,
) -> None:
    """Build and display the EXTERNAL AUTHENTICATE APDU with C-MAC (SCP03)."""
    cla = 0x84
    ins = 0x82
    p1 = security_level
    p2 = 0x00
    data = host_cryptogram

    # MAC chaining value starts as zero
    mac_chain = b"\x00" * 16

    lc_with_mac = len(data) + 8  # 16
    mac_input = mac_chain + bytes([cla, ins, p1, p2, lc_with_mac]) + data

    print(f"  MAC chaining:  {_hex(mac_chain)}  (initial, all zeros)")
    print(f"  APDU header:   {_hex(bytes([cla, ins, p1, p2, lc_with_mac]))}")
    print(f"  APDU data:     {_hex(data)}")
    print(f"  MAC input:     {_hex(mac_input)}")
    print(f"  Key (S-MAC):   {_hex(s_mac)}")

    full_mac = _aes_cmac(s_mac, mac_input)
    c_mac = full_mac[:8]
    print(f"  AES-CMAC:      {_hex(full_mac)}")
    print(f"  C-MAC (8B):    {_hex(c_mac)}")

    apdu_data = data + c_mac
    apdu = bytes([cla, ins, p1, p2, len(apdu_data)]) + apdu_data
    print(f"\n  EXTERNAL AUTHENTICATE APDU:")
    print(f"    {_hex_spaced(apdu)}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_hex(s: str) -> bytes:
    """Parse a hex string, stripping whitespace and optional 0x prefix."""
    s = s.strip().replace(" ", "").replace(":", "").replace("-", "")
    if s.lower().startswith("0x"):
        s = s[2:]
    return bytes.fromhex(s)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="SCP02/SCP03 session key derivation debugger",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "scp", nargs="?", choices=["scp02", "scp03"], default=None,
        help="Secure channel protocol version (auto-detected from response byte 11 if omitted)",
    )
    parser.add_argument(
        "--keys", required=True,
        help="Static keys as ENC:MAC:DEK (hex, colon-separated). "
             "DEK can be omitted (ENC:MAC).",
    )
    parser.add_argument(
        "--host-challenge", required=True,
        help="Host challenge sent in INITIALIZE UPDATE (8 bytes hex)",
    )
    parser.add_argument(
        "--init-update-response", required=True,
        help="Full INITIALIZE UPDATE response data (hex, 28+ bytes for SCP02, 29+ for SCP03)",
    )
    parser.add_argument(
        "--security-level", default="0x01",
        help="Security level for EXTERNAL AUTHENTICATE (hex, default 0x01 = C-MAC only)",
    )
    parser.add_argument(
        "--i-param", default=None,
        help="SCP02 i parameter override (hex, default 0x15). "
             "Ignored for SCP03 (read from response).",
    )

    args = parser.parse_args()

    # Parse keys
    key_parts = args.keys.split(":")
    if len(key_parts) == 2:
        enc_key = parse_hex(key_parts[0])
        mac_key = parse_hex(key_parts[1])
        dek_key = b""
    elif len(key_parts) == 3:
        enc_key = parse_hex(key_parts[0])
        mac_key = parse_hex(key_parts[1])
        dek_key = parse_hex(key_parts[2])
    else:
        parser.error("--keys must be ENC:MAC or ENC:MAC:DEK")

    host_challenge = parse_hex(args.host_challenge)
    init_update_response = parse_hex(args.init_update_response)
    security_level = int(args.security_level, 0)

    scp = args.scp
    if scp is None:
        if len(init_update_response) < 12:
            parser.error("response too short to auto-detect SCP version")
        scp_id = init_update_response[11]
        if scp_id == 0x02:
            scp = "scp02"
        elif scp_id == 0x03:
            scp = "scp03"
        else:
            parser.error(
                f"unknown SCP identifier 0x{scp_id:02X} at response byte 11; "
                "specify scp02 or scp03 explicitly"
            )

    if scp == "scp02":
        i_param = int(args.i_param, 0) if args.i_param else 0x15
        debug_scp02(
            enc_key, mac_key, dek_key,
            host_challenge, init_update_response,
            security_level, i_param,
        )
    else:
        debug_scp03(
            enc_key, mac_key, dek_key,
            host_challenge, init_update_response,
            security_level,
        )


if __name__ == "__main__":
    main()

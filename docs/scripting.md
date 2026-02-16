# Scripting

gpexp provides two ways to run commands: scenario files and the interactive REPL.

## CLI

```bash
uv run gpexp                          # interactive REPL (default)
uv run gpexp -f scenarios/read_card.gps  # run commands from a file
uv run gpexp -v                       # TRACE-level logging (raw APDUs)
uv run gpexp -v -f scenarios/read_card.gps  # combine flags
```

| Flag | Description |
|------|-------------|
| `-v`, `--verbose` | TRACE level — show raw APDUs |
| `-f`, `--file PATH` | Run commands from a scenario file |

With no `-f` flag, gpexp starts the interactive REPL.

## Commands

Commands are `cmd_*` functions organized in modules under `src/gpexp/app/gp/commands/`:

| Module | Description |
|--------|-------------|
| `iso.py` | ISO 7816 generic file and data commands |
| `gp.py` | GlobalPlatform commands |
| `session.py` | Session management and raw APDU |

The `cmd_` prefix is stripped to form the command name. The first docstring line becomes the help text. `help`, `set`, and `quit`/`exit` are built into `Runner` itself.

### ISO 7816 commands (`iso.py`)

Each command sends a single APDU.

| Command | Parameters | APDU | Description |
|---------|-----------|------|-------------|
| `probe` | `display` | SELECT (`00 A4`) | Select default applet, collect UID, ATR, FCI |
| `select` | `aid` or `fid`, `p1`, `p2` | SELECT (`00 A4`) | Select by AID, DF name, or EF file identifier |
| `read_binary` | `le`, `offset`, `sfi` | READ BINARY (`00 B0`) | Read from a transparent EF |
| `put_data` | `tag` (required), `data` | PUT DATA (`00 DA`) | Store a data object by tag (simple TLV) |
| `update_binary` | `offset`, `data`, `sfi` | UPDATE BINARY (`00 D6`) | Write to a transparent EF |

### GlobalPlatform commands (`gp.py`)

**Action commands:**

| Command | Parameters | Description |
|---------|-----------|-------------|
| `auth` | `kvn`, `level` | Establish SCP02/SCP03 secure channel |
| `load` | `file` (required), `aid`, `sd`, `block_size` | Load a CAP/IJC file onto the card |
| `install` | `package` (required), `module`, `instance`, `privileges`, `params`, `selectable` | Install an applet from a loaded package |
| `put_keys` | `new_kvn`, `key_type`, `key_length` | Load a new key set |
| `delete` | `aid` (required), `related` | Delete a package or applet instance by AID |
| `delete_keys` | `kvn` (required) | Delete a key set by version number |

**Info commands** — collect data into runner state, accept `display=true`:

| Command | Parameters | Description |
|---------|-----------|-------------|
| `info_cplc` | `display` | Read CPLC data (GET DATA 9F7F) |
| `info_card_data` | `display` | Read key info, card recognition, IIN, CIN, sequence counter (5× GET DATA) |
| `info_keys` | `display` | Read the key information template (GET DATA 00E0) |
| `info_contents` | `display` | List ISD, applications, and packages (GET STATUS) |

### Session commands (`session.py`)

| Command | Parameters | APDU | Description |
|---------|-----------|------|-------------|
| `connect` | — | — | Connect to the card |
| `disconnect` | — | — | Disconnect from the card |
| `reconnect` | — | — | Disconnect and reconnect |
| `apdu` | `apdu` or `cla`/`ins`/`p1`/`p2`/`data`/`le` | (user-defined) | Send a raw APDU |

### Built-in

| Command | Parameters | Description |
|---------|-----------|-------------|
| `set` | `key`, `enc`, `mac`, `dek`, `stop_on_error` | Set runner configuration |
| `help` | — | List available commands |
| `quit` / `exit` | — | Exit the REPL |

All commands return `True` on success, `False` on error.

### Parameter defaults

| Parameter | Default | Description |
|-----------|---------|-------------|
| `aid` | `""` (empty = card default) | Application identifier (hex) |
| `kvn` | `00` | Key version number |
| `level` | `01` (C-MAC) | Security level |
| `new_kvn` | `30` | Target key version for PUT KEY |
| `key_type` | `88` (AES) | Key type byte — TODO: accept `des`/`aes` names and validate `key_length` against the type |
| `key_length` | `16` | Key length in bytes (decimal) |
| `display` | `false` | Print collected results immediately |
| `block_size` | `239` | LOAD block size in bytes (decimal) |
| `privileges` | `00` | Application privileges (hex or symbolic, see [privilege mnemonics](#privilege-mnemonics)) |
| `params` | `C900` | Install parameters TLV (hex, `C900` = empty) |
| `related` | `false` | Delete related objects (cascade) |
| `selectable` | `true` | Make applet selectable on install |

## Scenario files (.gps)

Scenario files are plain text with one command per line. They live in `scenarios/`.

### Format

```
# comment
command_name
command_name param1=value1 param2=value2
```

- One command per line
- `#` for comments (full line or inline)
- Blank lines are ignored
- Parameters use `key=value` syntax
- A bare word `flag` is treated as `flag=true`
- Quoting follows `shlex` rules (use quotes for values with spaces)

Execution stops on the first error by default. Override with `set stop_on_error=false`.

### Parameter parsing

Parameters are parsed differently depending on the command and parameter name:

1. **Raw commands** (`apdu`, `put_data`, `read_binary`, `select`, `update_binary`, `load`, `install`, `delete`) — all parameters are passed as raw strings with no conversion.

2. **Hex parameters** (`kvn`, `new_kvn`, `key_type`, `key_length`, `level`) — always parsed as hexadecimal, so `kvn=20` means `0x20` (decimal 32).

3. **Other parameters** — auto-detected:
   - `true`, `yes` → boolean `True`; `false`, `no` → boolean `False`
   - `0x` prefix or contains `a`-`f` → hex integer
   - All digits → decimal integer
   - Otherwise → string

### Example: read_card.gps

```
# read_card.gps — probe, authenticate, and read card contents
probe display=true
info_cplc display=true
info_card_data display=true
auth kvn=20
info_contents display=true
```

### Example: put_delete_key.gps

```
# put_delete_key.gps — authenticate, PUT KEY, then DELETE KEY
info_card_data
auth kvn=20
info_keys display=true
put_keys new_kvn=30
info_keys display=true
delete_keys kvn=30
info_keys display=true
```

### Example: raw APDU

```
# raw_get_data.gps — authenticate and send raw GET DATA 0066
probe
info_card_data
auth kvn=00
apdu apdu=80CA006600
```

## Interactive REPL

When started without `-f`, gpexp drops into an interactive prompt:

```
gpexp> help
gpexp> probe
gpexp> auth kvn=20
gpexp> apdu apdu=80CA006600
gpexp> quit
```

- Readline line-editing is available (arrow keys, history)
- Type `help` to list commands
- Type `quit` or `exit` (or Ctrl-D / Ctrl-C) to leave

The REPL uses the same command syntax as scenario files.

## The `set` command

`set` changes runner configuration at runtime. It works in both scenario files and the REPL.

```
set key=404142434445464748494A4B4C4D4E4F
set stop_on_error=false
```

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `key` | hex string | `404142434445464748494A4B4C4D4E4F` | Base key — used for ENC/MAC/DEK unless individually overridden. Clears any per-key overrides. |
| `enc` | hex string | (uses `key`) | ENC key override |
| `mac` | hex string | (uses `key`) | MAC key override |
| `dek` | hex string | (uses `key`) | DEK key override |
| `stop_on_error` | bool | `true` | Stop file execution on first error |

When all three keys are the same, `set key=` is sufficient. When they differ, set them individually:

```
set enc=00112233445566778899AABBCCDDEEFF
set mac=AABBCCDDEEFF00112233445566778899
set dek=112233445566778899AABBCCDDEEFF00
auth
```

You can also set a base key and override selectively — `set key=` resets all three overrides:

```
set key=00112233445566778899AABBCCDDEEFF
set dek=FFEEDDCCBBAA99887766554433221100
auth
```

## The `select` command

SELECT a file or application (ISO 7816-4, INS `A4`). Three modes:

```
select aid=A0000000031010        # by AID, return FCI (P1=04, P2=00)
select aid=A0000000031010 p2=0C  # by DF name, no response (P1=04, P2=0C)
select fid=011C                  # EF by file identifier (P1=02, P2=0C)
select p1=00 p2=00               # select MF
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `aid` | `""` | Application identifier or DF name (hex) |
| `fid` | `""` | EF file identifier (hex, sets P1=02 P2=0C) |
| `p1` | `04` (aid) / `02` (fid) | Selection method |
| `p2` | `00` (aid) / `0C` (fid) | Response control |

When `fid=` is used, defaults change to P1=`02` P2=`0C` (select EF, no response data). Both `p1` and `p2` can be overridden explicitly.

## The `read_binary` command

Read data from a transparent EF (ISO 7816-4 READ BINARY, INS `B0`). Either from the currently selected file or by SFI.

```
read_binary le=00                    # read from selected file, offset 0
read_binary offset=10 le=00          # read at offset 0x10
read_binary sfi=1C le=00             # read by SFI (no SELECT needed)
read_binary sfi=1C offset=10 le=00   # SFI with offset (max FF)
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `offset` | `0` | Read offset (hex, up to `7FFF` without SFI, up to `FF` with SFI) |
| `le` | `0` | Expected response length (hex, `00` = up to 256 bytes) |
| `sfi` | — | Short file identifier (hex, encodes in P1 bit 8) |

## The `put_data` command

Store a data object on the card by tag (ISO 7816-4 PUT DATA, simple TLV, INS `DA`). The tag maps to P1-P2, Lc is derived from the data length.

```
put_data tag=2002 data=A0A1A2A3
```

| Parameter | Required | Description |
|-----------|----------|-------------|
| `tag` | yes | Tag identifier (hex, 2 bytes in P1-P2) |
| `data` | no | Data object value (hex) |

## The `update_binary` command

Write data to a transparent EF (ISO 7816-4 UPDATE BINARY, INS `D6`). Either to the currently selected file or by SFI.

```
update_binary data=A0A1A2A3                    # selected file, offset 0
update_binary offset=0495 data=A0A1A2A3        # selected file at offset
update_binary sfi=1C data=A0A1A2A3             # by SFI (no SELECT needed)
update_binary sfi=1C offset=10 data=A0A1A2A3   # SFI with offset (max FF)
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `offset` | `0` | Write offset (hex, up to `7FFF` without SFI, up to `FF` with SFI) |
| `data` | `""` | Data to write (hex) |
| `sfi` | — | Short file identifier (hex, encodes in P1 bit 8) |

## The `apdu` command

Send an arbitrary APDU. Two forms:

**Hex string** — the entire APDU as a single hex blob:

```
apdu apdu=80CA006600
```

The bytes are split as CLA(1) INS(1) P1(1) P2(1) then either Le(1) if 5 bytes total, or Lc+Data if longer.

**Component parts** — each field separately (all hex):

```
apdu cla=80 ins=CA p1=00 p2=66 le=00
apdu cla=80 ins=E2 p1=80 p2=00 data=5F2001FF
```

## The `load` command

Load a CAP or IJC file onto the card. Sends INSTALL [for load] (`80 E6`, P1=`02`) followed by LOAD (`80 E8`) blocks. Requires an authenticated session.

```
load file=applets/MyApplet.cap
load file=applets/MyApplet.cap aid=A00000006203010C08
load file=applets/MyApplet.cap block_size=200
load file=applets/MyApplet.ijc aid=A00000006203010C08
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `file` | (required) | Path to CAP or IJC file |
| `aid` | from CAP metadata | Load file AID (hex) — overrides AID extracted from CAP Header component |
| `sd` | `""` (ISD) | Security domain AID (hex) |
| `block_size` | `239` | LOAD block size in bytes (decimal) — 239 stays within short APDU with C-MAC |

CAP files are ZIP archives; components are extracted and concatenated in GP 2.2 Table 6-2 order. IJC files are raw binary load file data. The package AID and applet AIDs are extracted from the Header and Applet components when available.

## The `install` command

Install an applet from a loaded package. Sends INSTALL [for install and make selectable] (`80 E6`, P1=`0C`). Can also install from packages loaded in a previous session or by another tool.

```
install package=A00000006203010C08 module=A00000006203010C0801
install package=A00000006203010C08 module=A00000006203010C0801 instance=A00000006203010C0802
install package=A00000006203010C08 module=A00000006203010C0801 privileges=04
install package=A00000006203010C08 module=A00000006203010C0801 privileges=SD,TP,AM,CLFDB
install package=A00000006203010C08 module=A00000006203010C0801 selectable=false
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `package` | (required) | Executable load file AID (hex) |
| `module` | same as `package` | Executable module AID (hex) |
| `instance` | same as `module` | Application instance AID (hex) |
| `privileges` | `00` | Application privileges (hex or symbolic, see [privilege mnemonics](#privilege-mnemonics)) |
| `params` | `C900` | Install parameters TLV (hex) — `C900` = empty |
| `selectable` | `true` | Make the applet selectable (P1=`0C`); `false` uses P1=`04` |

### Privilege mnemonics

The `privileges` parameter accepts raw hex bytes (e.g. `80C040`) or comma-separated symbolic names. Names are case-insensitive.

| Mnemonic | Privilege | Byte.Bit |
|----------|-----------|----------|
| `sd` | Security Domain | 0.7 |
| `dap` | DAP Verification | 0.6 |
| `dm` | Delegated Management | 0.5 |
| `lock` | Card Lock | 0.4 |
| `terminate` | Card Terminate | 0.3 |
| `default` | Default Selected | 0.2 |
| `cvm` | CVM Management | 0.1 |
| `mdap` | Mandated DAP Verification | 0.0 |
| `tp` | Trusted Path | 1.7 |
| `am` | Authorized Management | 1.6 |
| `tv` | Token Verification | 1.5 |
| `gdelete` | Global Delete | 1.4 |
| `glock` | Global Lock | 1.3 |
| `greg` | Global Registry | 1.2 |
| `final` | Final Application | 1.1 |
| `gsvc` | Global Service | 1.0 |
| `receipt` | Receipt Generation | 2.7 |
| `clfdb` | Ciphered Load File Data Block | 2.6 |
| `clact` | Contactless Activation | 2.5 |
| `clsact` | Contactless Self-Activation | 2.4 |

When only byte-0 privileges are used, a 1-byte encoding is produced. Otherwise a 3-byte encoding is used automatically.

## The `delete` command

Delete a package or applet instance from the card. Sends DELETE (`80 E4`) with tag `4F` containing the AID. Requires an authenticated session.

```
delete aid=A00000006203010C0801
delete aid=A00000006203010C08 related=true
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `aid` | (required) | AID of the object to delete (hex) |
| `related` | `false` | Delete related objects — set `true` to cascade-delete a package and its instances (P2=`80`) |


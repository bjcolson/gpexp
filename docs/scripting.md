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

Commands map directly to `cmd_*` methods on the `Runner` class. The `cmd_` prefix is stripped to form the command name. The first docstring line becomes the help text.

| Command | Parameters | Description |
|---------|-----------|-------------|
| `probe` | — | Probe card: UID, ATR, FCI |
| `select` | `aid` | SELECT an application by AID |
| `read_cplc` | — | Read CPLC data |
| `read_card_data` | — | Read GP data objects (key info, card recognition, IIN, CIN, sequence counter) |
| `auth` | `kvn`, `level` | Authenticate with default keys |
| `list_contents` | — | GET STATUS for ISD, applications, and packages |
| `read_key_info` | — | Read and log the key information template |
| `put_keys` | `new_kvn`, `key_type`, `key_length` | PUT KEY to load a new key set |
| `delete_keys` | `kvn` (required) | Delete a key set by version number |
| `connect` | — | Connect to the card |
| `disconnect` | — | Disconnect from the card |
| `reconnect` | — | Disconnect and reconnect |
| `display` | — | Display collected card information |
| `set` | `key`, `stop_on_error` | Set runner configuration |
| `apdu` | `apdu` or `cla`/`ins`/`p1`/`p2`/`data`/`le` | Send a raw APDU |
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
| `key_type` | `88` (AES) | Key type byte |
| `key_length` | `16` | Key length in bytes (decimal) |

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

1. **Raw commands** (`apdu`, `select`) — all parameters are passed as raw strings with no conversion.

2. **Hex parameters** (`kvn`, `new_kvn`, `key_type`, `key_length`, `level`) — always parsed as hexadecimal, so `kvn=20` means `0x20` (decimal 32).

3. **Other parameters** — auto-detected:
   - `true`, `yes` → boolean `True`; `false`, `no` → boolean `False`
   - `0x` prefix or contains `a`-`f` → hex integer
   - All digits → decimal integer
   - Otherwise → string

### Example: read_card.gps

```
# read_card.gps — probe, authenticate, and read card contents
probe
read_cplc
read_card_data
auth kvn=20
list_contents
display
```

### Example: put_delete_key.gps

```
# put_delete_key.gps — authenticate, PUT KEY, then DELETE KEY
read_card_data
auth kvn=20
read_key_info
put_keys new_kvn=30
read_key_info
delete_keys kvn=30
read_key_info
```

### Example: raw APDU

```
# raw_get_data.gps — authenticate and send raw GET DATA 0066
probe
read_card_data
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
| `key` | hex string | `404142434445464748494A4B4C4D4E4F` | Session key material (replicated across ENC/MAC/DEK) |
| `stop_on_error` | bool | `true` | Stop file execution on first error |

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


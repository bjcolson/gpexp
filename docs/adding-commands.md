# Adding Commands

There are two levels of commands in gpexp: **runner commands** (user-facing, in the app layer) and **terminal messages** (core layer, APDU-level). Most new features only need a runner command that reuses existing messages. New terminal messages are only needed when a new APDU or APDU sequence is required.

## Runner commands (app layer)

Runner commands are `cmd_*` functions in command modules. They are automatically discovered and exposed to the REPL, scenario files, and Python scenarios. Commands are split across two packages:

**Generic commands** (`src/gpexp/app/generic/commands/`) — protocol-independent, available to all runners:

| Module | Description |
|--------|-------------|
| `iso.py` | ISO 7816 generic file and data commands (single APDU each) |
| `session.py` | Session management and raw APDU |

**GP commands** (`src/gpexp/app/gp/commands/`) — GlobalPlatform-specific:

| Module | Description |
|--------|-------------|
| `gp.py` | GlobalPlatform commands (single APDU and multi-APDU sequences) |

Commands that map to a single APDU belong in `iso.py` or `gp.py` depending on the protocol. Multi-APDU sequences (e.g. `auth`, `info_contents`, `info_card_data`) also live in `gp.py` — the terminal handler composes the APDU sequence. See `docs/scripting.md` for the full command reference with APDU details.

`Runner` (`src/gpexp/app/generic/runner.py`) holds the built-in commands (`help`, `set`, `quit`/`exit`) and the dispatch infrastructure (`execute`, `run_file`, `run_interactive`). Settings (`stop_on_error`) are registered directly on `Runner`. `GPRunner` extends `Runner` with GP session state (key material, `GPCardInfo`) and adds GP-specific settings (`key`).

### Adding a runner command

1. Add a `cmd_<name>` function to the appropriate command module. The first argument is `runner`:

```python
def cmd_read_iin(runner) -> bool:
    """Read Issuer Identification Number."""
    result = runner._terminal.send(GetCardDataMessage())
    if result.iin is not None:
        runner._info.iin = result.iin
        lg.info("IIN: %s", result.iin.hex().upper())
    return True
```

The function is automatically registered as command `read_iin`. The first line of the docstring becomes the help text. Return `True` on success, `False` on error.

2. If any parameters map to APDU fields or tags (hex values), add the parameter names to the module-level `_hex_params` set:

```python
_hex_params: set[str] = {"my_new_tag"}
```

These are always parsed as hex from scenario files and the REPL (e.g. `my_command my_new_tag=9F7F`).

3. If the command needs all parameters as raw strings (like `cmd_apdu`), add the command name to the module-level `_raw_commands` set:

```python
_raw_commands: set[str] = {"my_raw_command"}
```

4. If the command needs custom settings for the `set` command, either register them directly on the runner (for core settings like `stop_on_error` on `Runner` or `key` on `GPRunner`), or declare a `_settings` dict in a command module. Each handler receives `(runner, value: str)`:

```python
# On a runner class:
self._settings["my_option"] = self._set_my_option

# Or in a command module:
def _set_my_option(runner, value: str) -> None:
    runner._my_option = int(value, 16)
    lg.info("my_option = %04X", runner._my_option)

_settings: dict[str, callable] = {"my_option": _set_my_option}
```

The `set` command is built into `Runner` and dispatches to handlers. Handlers always receive raw string values.

5. If adding a new module, register it in the appropriate `commands/__init__.py`:

```python
# Generic (protocol-independent) commands:
# src/gpexp/app/generic/commands/__init__.py
COMMAND_MODULES = [iso, session, my_module]

# GP-specific commands:
# src/gpexp/app/gp/commands/__init__.py
COMMAND_MODULES = [gp, my_module]
```

### Using from scenario files (.gps)

The command is immediately available:

```
read_iin
```

## Terminal messages (core layer)

Terminal messages define the contract between the app layer and the core layer. Each message is a `Message`/`Result` dataclass pair, handled by a `@handles`-decorated method on a terminal class.

### When to add a new message

Add a new message when you need to send an APDU (or APDU sequence) that no existing message covers. If the operation can be composed from existing messages, use a runner command instead.

### Steps

1. **Define Message and Result dataclasses** in the appropriate `messages.py`:

   For GP-specific operations, use `src/gpexp/core/gp/messages.py`:

   ```python
   @dataclass
   class StoreDataMessage(Message):
       """STORE DATA command."""
       data: bytes
       block_number: int = 0
       last_block: bool = True

   @dataclass
   class StoreDataResult(Result):
       success: bool
       sw: int
   ```

   For generic (non-GP) operations, use `src/gpexp/core/generic/messages.py`.

2. **Add a protocol method** (if it maps to a single APDU) in the protocol class.

   In `src/gpexp/core/gp/protocol.py`:

   ```python
   def send_store_data(self, p1: int, data: bytes) -> Response:
       """GP STORE DATA (80 E2)."""
       apdu = APDU(cla=0x80, ins=0xE2, p1=p1, p2=0x00, data=data)
       return self._send("STORE DATA", apdu)
   ```

   Use the `send_` prefix for methods that map to a single APDU command. Omit it for higher-level operations that compose multiple APDUs.

3. **Add a handler** on the terminal class.

   In `src/gpexp/core/gp/terminal.py`:

   ```python
   @handles(StoreDataMessage)
   def _store_data(self, message: StoreDataMessage) -> StoreDataResult:
       p1 = 0x80 if message.last_block else 0x00
       p1 |= message.block_number & 0x1F
       resp = self._gp.send_store_data(p1, message.data)
       return StoreDataResult(success=resp.success, sw=resp.sw)
   ```

4. **Export** from the package `__init__.py`:

   In `src/gpexp/core/gp/__init__.py`, add the new types to imports and `__all__`.

5. **Add a runner command** in the appropriate command module (see above):

   ```python
   def cmd_store_data(runner, *, data: str = "") -> bool:
       """STORE DATA to the card."""
       result = runner._terminal.send(
           StoreDataMessage(data=bytes.fromhex(data))
       )
       if result.success:
           lg.info("STORE DATA success")
           return True
       lg.error("STORE DATA failed: SW=%04X", result.sw)
       return False
   ```

## Summary

| What | Where | When |
|------|-------|------|
| Runner command | `commands/*.py` → `cmd_*` function | Composing existing messages, user-facing operation |
| Scenario file | `scenarios/*.gps` | Scripted sequence of runner commands |
| Terminal message | `core/**/messages.py` + `terminal.py` handler | New APDU or APDU sequence needed |
| Protocol method | `core/**/protocol.py` → `send_*` | New single-APDU command |

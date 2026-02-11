# Adding Commands

There are two levels of commands in gpexp: **runner commands** (user-facing, in the app layer) and **terminal messages** (core layer, APDU-level). Most new features only need a runner command that reuses existing messages. New terminal messages are only needed when a new APDU or APDU sequence is required.

## Runner commands (app layer)

Runner commands are methods on `Runner` in `src/gpexp/app/gp/runner.py`. They are automatically discovered and exposed to the REPL, scenario files, and Python scenarios.

### Adding a runner command

1. Add a `cmd_<name>` method to `Runner`:

```python
def cmd_read_iin(self) -> bool:
    """Read Issuer Identification Number."""
    result = self._terminal.send(GetCardDataMessage())
    if result.iin is not None:
        self._info.iin = result.iin
        lg.info("IIN: %s", result.iin.hex().upper())
    return True
```

The method is automatically registered as command `read_iin`. The first line of the docstring becomes the help text. Return `True` on success, `False` on error.

2. If any parameters map to APDU fields or tags (hex values), add the parameter names to `_hex_params`:

```python
_hex_params: set[str] = {
    "kvn", "new_kvn", "key_type", "key_length",
    "my_new_tag",  # add here
}
```

These are always parsed as hex from scenario files and the REPL (e.g. `my_command my_new_tag=9F7F`).

3. If the command needs all parameters as raw strings (like `cmd_apdu`), add the command name to `_raw_commands`:

```python
_raw_commands: set[str] = {"apdu", "my_raw_command"}
```

### Using from scenario files (.gps)

The command is immediately available:

```
read_iin
```

### Using from Python scenarios

Call the method directly on the runner:

```python
def scenario_example(runner: Runner) -> None:
    runner.cmd_read_iin()
```

Register in `SCENARIOS` in `src/gpexp/app/gp/scenarios.py` if it should be selectable via `-s`.

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

5. **Add a runner command** that uses the new message (see above):

   ```python
   def cmd_store_data(self, *, data: str = "") -> bool:
       """STORE DATA to the card."""
       result = self._terminal.send(
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
| Runner command | `runner.py` → `cmd_*` method | Composing existing messages, user-facing operation |
| Python scenario | `scenarios.py` → function + `SCENARIOS` entry | Multi-step sequence with logic (loops, conditionals) |
| Scenario file | `scenarios/*.gps` | Scripted sequence of runner commands |
| Terminal message | `core/**/messages.py` + `terminal.py` handler | New APDU or APDU sequence needed |
| Protocol method | `core/**/protocol.py` → `send_*` | New single-APDU command |

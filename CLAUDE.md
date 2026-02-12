# gpexp

TUI smartcard interaction tool built on pyscard and urwid.

## Architecture

Three-layer design under `src/gpexp/core/`:

- **smartcard/** — Card wrapper around pyscard, APDU/Response types, BER-TLV parser, transport-level logging observer
- **base/** — Agent, Terminal with message dispatch, ISO7816 protocol class, Message/Result types, ISO 7816-4 tag registry
- **generic/** — GenericTerminal, messages (ProbeMessage/ProbeResult)
- **gp/** — GP protocol class, GPTerminal (extends GenericTerminal), messages, SCP02/SCP03, tags

Data flow: **App → Terminal → Agent → Card**

The app sends `Message` objects to the terminal via `send()` and receives typed `Result` subclasses back. The terminal dispatches to handler methods registered with the `@handles` decorator. Handlers call protocol objects, which translate operations into APDUs via `agent.transmit`. The terminal has no visibility of the Card object.

Messages and their typed results are defined in per-package `messages.py` files. Each result subclass carries its own fields instead of a generic dict. Protocol classes (`ISO7816`, `GP`) are standalone objects that receive `agent.transmit` as a callable — there is one `Agent` class, no subclasses. Terminals construct the protocol objects they need (e.g. `GenericTerminal` creates `self._iso`, `GPTerminal` adds `self._gp`). Terminals inherit handlers from parent classes, so GPTerminal extends GenericTerminal.

Protocol methods that map directly to APDU commands use a `send_` prefix (e.g. `send_select`, `send_get_data`, `send_get_status`). Higher-level operations that compose multiple commands do not (e.g. `list_content`, `list_all_content`).

## Secure Channel

SCP02 and SCP03 are both supported. The `_authenticate` handler selects the appropriate protocol based on the SCP identifier in the INITIALIZE UPDATE response. Session state (keys, IVs, MAC chaining) is managed by `SCP02Channel` or `SCP03Channel`, held on the agent. The agent's `transmit()` delegates to `channel.wrap(apdu)` / `channel.unwrap(response)` when a session is active, passing through unchanged otherwise. The channel is created during INITIALIZE UPDATE + EXTERNAL AUTHENTICATE. Static keys are provided by the app layer via an `AuthenticateMessage`.

## Runner

`Runner` (`src/gpexp/app/generic/runner.py`) is the base runner class. It holds session state (terminal, `CardInfo`, `stop_on_error`) and dispatches commands. `GPRunner` (`src/gpexp/app/gp/runner.py`) extends it with GP-specific state (`GPCardInfo`, key material).

Commands are `cmd_*` plain functions in modules split across two packages:

**Generic** (`src/gpexp/app/generic/commands/`):
- **`iso.py`** — ISO 7816 generic file and data commands (select, read_binary, etc.)
- **`session.py`** — Session management and raw APDU (connect, disconnect, apdu)

**GP** (`src/gpexp/app/gp/commands/`):
- **`gp.py`** — GlobalPlatform commands (auth, info_contents, put_keys, etc.)

Each function takes `runner` as its first argument. `Runner.__init__` collects `cmd_*` functions from all modules listed in `commands.COMMAND_MODULES` via `functools.partial`. Each module declares `_raw_commands`, `_hex_params` sets and an optional `_settings` dict that Runner unions together. `GPRunner` combines generic and GP `COMMAND_MODULES`.

The `help`, `set`, `quit`/`exit` commands are built into `Runner`. Settings (`stop_on_error`) are registered directly on `Runner`; `GPRunner` adds GP-specific settings (`key`). Command modules can still contribute additional settings via `_settings` dicts. `set` is a raw command — handlers always receive string values.

Parameter values that map to APDU fields or tags (listed in module-level `_hex_params` sets) are always parsed as hex. Commands listed in module-level `_raw_commands` sets receive all parameters as raw strings.

Data-collecting commands (`probe`, `info_cplc`, `info_card_data`, `info_keys`, `info_contents`) accept `display=true` to print their results immediately after collection.

## Running

```bash
uv run gpexp                             # interactive REPL (default)
uv run gpexp -f scenarios/read_card.gps  # run commands from a file
uv run gpexp -v                          # TRACE-level logging (raw APDUs)
```

CLI entry point defined in `src/gpexp/scripts.py`, calls `src/gpexp/app/main.py:main()`.

## Scenario files

Scenario files (`.gps`) live in `scenarios/`. One command per line, `#` comments, blank lines ignored. Stops on first error by default (`set stop_on_error=false` to override).

Some commands have implicit ordering dependencies that vary by card. No runtime checks enforce these — misordering produces raw SW error codes. For example, `info_contents` requires selecting the ISD and an authenticated session (`probe` → `auth` → `info_contents`). Use `-v` to see APDU traces when debugging failures.

## Adding commands

See `docs/adding-commands.md` for how to add runner commands and terminal messages.

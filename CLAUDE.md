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

`Runner` (`src/gpexp/app/gp/runner.py`) holds session state (terminal, CardInfo, key material) and exposes unit operations as `cmd_*` methods. Methods are auto-discovered and registered as commands available in the REPL, scenario files, and Python scenarios.

Parameter values that map to APDU fields or tags (listed in `Runner._hex_params`) are always parsed as hex. Commands listed in `Runner._raw_commands` receive all parameters as raw strings.

## Running

```bash
uv run gpexp                          # default scenario (read_card)
uv run gpexp -s list                  # list available scenarios and options
uv run gpexp -s read_card             # run scenario by name
uv run gpexp -s 2                     # run scenario by number
uv run gpexp -s 2 -o kvn=20          # run scenario with options
uv run gpexp -f scenarios/read_card.gps  # run commands from a file
uv run gpexp -i                       # interactive REPL
uv run gpexp -v                       # TRACE-level logging (raw APDUs)
```

CLI entry point defined in `src/gpexp/scripts.py`, calls `src/gpexp/app/main.py:main()`.

## Scenarios

Python scenarios live in `src/gpexp/app/gp/scenarios.py`. The `SCENARIOS` list registers them for CLI access. Each entry is a 4-tuple: `(name, description, callable, option_defs)`. The callable receives `(runner, **opts)`. Option defs map option names to `(type, default, description)` where type is `"bool"`, `"hex"`, or `"int"`.

Scenario files (`.gps`) live in `scenarios/`. One command per line, `#` comments, blank lines ignored. Stops on first error by default (`set stop_on_error=false` to override).

## Adding commands

See `docs/adding-commands.md` for how to add runner commands, terminal messages, and scenarios.

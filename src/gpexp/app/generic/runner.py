"""Runner — holds session state, dispatches commands."""

from __future__ import annotations

import logging
from functools import partial
try:
    import readline  # noqa: F401 — enables line editing in input()
except ImportError:
    pass
import shlex
from types import ModuleType

from gpexp.app.generic.cardinfo import CardInfo

lg = logging.getLogger(__name__)


def _parse_value(s: str) -> int | str | bool:
    """Parse a command argument value.

    Returns int (hex detection: contains a-f/A-F or 0x prefix), bool
    for true/false literals, otherwise the raw string.
    """
    low = s.lower()
    if low in ("true", "yes"):
        return True
    if low in ("false", "no"):
        return False
    # Hex: has 0x prefix or contains hex digit a-f
    if low.startswith("0x") or any(c in "abcdef" for c in low):
        try:
            return int(s, 16)
        except ValueError:
            pass
    # Plain int
    try:
        return int(s)
    except ValueError:
        pass
    return s


def parse_command(line: str) -> tuple[str, dict[str, str]] | None:
    """Parse a command line into (name, raw_kwargs).

    Returns None for blank/comment lines.  Values are kept as raw strings;
    the caller decides how to convert them.
    """
    stripped = line.split("#", 1)[0].strip()
    if not stripped:
        return None
    parts = shlex.split(stripped)
    name = parts[0]
    kwargs: dict[str, str] = {}
    for part in parts[1:]:
        if "=" in part:
            k, v = part.split("=", 1)
            kwargs[k] = v
        else:
            kwargs[part] = "true"
    return name, kwargs


class Runner:
    """Holds session state and dispatches commands."""

    def __init__(self, terminal, command_modules: list[ModuleType]) -> None:
        self._terminal = terminal
        self._info = CardInfo()
        self._stop_on_error = True

        # Build command table from external command modules
        self._commands: dict[str, callable] = {}
        self._descriptions: dict[str, str] = {}
        self._raw_commands: set[str] = set()
        self._hex_params: set[str] = set()
        self._settings: dict[str, callable] = {
            "stop_on_error": self._set_stop_on_error,
        }
        for mod in command_modules:
            for name in dir(mod):
                if name.startswith("cmd_"):
                    func = getattr(mod, name)
                    cmd_name = name[4:]
                    self._commands[cmd_name] = partial(func, self)
                    self._descriptions[cmd_name] = (func.__doc__ or "").split("\n")[0].strip()
            self._raw_commands |= getattr(mod, "_raw_commands", set())
            self._hex_params |= getattr(mod, "_hex_params", set())
            self._settings.update(getattr(mod, "_settings", {}))

        # Collect commands from self (help, set)
        for attr in dir(self):
            if attr.startswith("cmd_"):
                method = getattr(self, attr)
                cmd_name = attr[4:]
                self._commands[cmd_name] = method
                self._descriptions[cmd_name] = (method.__doc__ or "").split("\n")[0].strip()

        # 'set' is a raw command — handlers always receive strings
        self._raw_commands.add("set")

    # --- Settings ---

    def _set_stop_on_error(self, _runner, value: str) -> None:
        self._stop_on_error = value.lower() in ("true", "yes", "1")
        lg.info("stop_on_error = %s", self._stop_on_error)

    # --- Commands ---

    def cmd_help(self) -> bool:
        """List available commands."""
        lines = []
        for name in sorted(self._descriptions):
            lines.append(f"  {name:20s} {self._descriptions[name]}")
        lg.info("Commands:\n%s", "\n".join(lines))
        return True

    def cmd_set(self, **kwargs: str) -> bool:
        """Set runner configuration."""
        for k, v in kwargs.items():
            handler = self._settings.get(k)
            if handler is None:
                lg.warning("unknown setting: %s", k)
            else:
                handler(self, v)
        return True

    # --- Execution ---

    def execute(self, line: str) -> bool:
        """Parse and execute one command line. Returns True on success."""
        parsed = parse_command(line)
        if parsed is None:
            return True  # blank/comment — not an error
        name, raw_kwargs = parsed
        if name in ("quit", "exit"):
            raise StopIteration
        cmd = self._commands.get(name)
        if cmd is None:
            lg.error("unknown command: %s", name)
            return False
        if name in self._raw_commands:
            kwargs = raw_kwargs
        else:
            kwargs = {
                k: int(v, 16) if k in self._hex_params else _parse_value(v)
                for k, v in raw_kwargs.items()
            }
        try:
            return cmd(**kwargs)
        except TypeError as exc:
            lg.error("bad arguments for '%s': %s", name, exc)
            return False
        except Exception as exc:
            lg.error("command '%s' failed: %s", name, exc)
            return False

    def run_file(self, path: str) -> bool:
        """Read and execute commands from a file. Returns True if all succeed."""
        with open(path) as f:
            lines = f.readlines()
        for i, line in enumerate(lines, 1):
            ok = self.execute(line)
            if not ok and self._stop_on_error:
                lg.error("stopped at line %d: %s", i, line.strip())
                return False
        return True

    def run_interactive(self) -> None:
        """Interactive REPL with readline support."""
        lg.info("interactive mode — type 'help' for commands, 'quit' to exit")
        while True:
            try:
                line = input("gpexp> ")
            except (EOFError, KeyboardInterrupt):
                print()
                break
            try:
                self.execute(line)
            except StopIteration:
                break

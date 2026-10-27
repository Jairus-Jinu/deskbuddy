"""Run DeskBuddy as a background service that starts with the desktop session.

The goal: after login, saying "choom" pops the window up — no terminal, no
command, no file to run. That needs three things, and this module owns all
three so they stay in sync:

1. a long-running process (`main.py serve`),
2. a systemd user unit bound to `graphical-session.target`, so it starts when
   the Wayland session does and restarts if it dies,
3. a lock, so running `serve` by hand while the service is already up does not
   open a second microphone.

The unit is written to `~/.config/systemd/user/`, which is the user's own
directory — nothing here needs root.
"""

from __future__ import annotations

import fcntl
import os
import subprocess
from pathlib import Path

UNIT_NAME = "deskbuddy.service"
LOCK_PATH = Path.home() / ".cache" / "deskbuddy" / "service.lock"


def unit_dir() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "systemd" / "user"


def unit_path() -> Path:
    return unit_dir() / UNIT_NAME


def render_unit(python: str, main_py: Path) -> str:
    """The unit file as text. Kept visible so `service --show` can print it."""
    return f"""[Unit]
Description=DeskBuddy voice assistant (say "choom")
Documentation=file://{main_py.parent / 'README.md'}
After=graphical-session.target pipewire.service
PartOf=graphical-session.target

[Service]
Type=simple
WorkingDirectory={main_py.parent}
ExecStart={python} {main_py} serve
Environment=PYTHONUNBUFFERED=1
Restart=on-failure
RestartSec=3

[Install]
WantedBy=graphical-session.target
"""


def _systemctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["systemctl", "--user", *args], capture_output=True, text=True)


def install(python: str, main_py: Path) -> int:
    directory = unit_dir()
    directory.mkdir(parents=True, exist_ok=True)
    target = unit_path()
    target.write_text(render_unit(python, main_py), encoding="utf-8")

    _systemctl("daemon-reload")
    wanted = directory / "graphical-session.target.wants"
    wanted.mkdir(parents=True, exist_ok=True)
    link = wanted / UNIT_NAME
    if link.is_symlink() or link.exists():
        link.unlink()
    link.symlink_to(target)

    # If the desktop session is already up, start it now rather than making
    # the user log out and back in.
    started = _systemctl("start", UNIT_NAME)
    print(f"installed {target}")
    if started.returncode == 0:
        print("started — say “choom” and the window will appear")
    else:
        print(f"install ok, but it did not start: {started.stderr.strip()}")
        print("it will come up at your next login")
    print(f"logs:  journalctl --user -u {UNIT_NAME} -f")
    return 0


def uninstall() -> int:
    _systemctl("disable", "--now", UNIT_NAME)
    link = unit_dir() / "graphical-session.target.wants" / UNIT_NAME
    link.unlink(missing_ok=True)
    unit_path().unlink(missing_ok=True)
    _systemctl("daemon-reload")
    print("removed — DeskBuddy will not start with the session any more")
    return 0


def status() -> int:
    active = _systemctl("is-active", UNIT_NAME).stdout.strip() or "not installed"
    print(f"unit:   {unit_path() if unit_path().exists() else '(not installed)'}")
    print(f"state:  {active}")
    if active == "active":
        output = _systemctl("show", UNIT_NAME, "--property=MainPID,ActiveEnterTimestamp,MemoryCurrent").stdout
        for line in output.splitlines():
            key, _, value = line.partition("=")
            if key in {"MainPID", "ActiveEnterTimestamp", "MemoryCurrent"} and value not in {"", "[not set]"}:
                print(f"{key}: {value}")
        print("say “choom” to open the window; `journalctl --user -u deskbuddy -f` for the log")
    return 0 if active == "active" else 1


class ServiceLock:
    """Keeps exactly one live process on the microphone.

    Two instances means two streams on the same device and both answering the
    same question, which is worse than refusing to start. `flock` releases on
    process exit, even a crash, so there is no stale-lock cleanup.
    """

    def __init__(self, path: Path = LOCK_PATH) -> None:
        self.path = path
        self._handle = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = open(self.path, "w", encoding="utf-8")  # noqa: SIM115 - held open on purpose
        try:
            fcntl.flock(self._handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self._handle.close()
            self._handle = None
            return False
        self._handle.write(str(os.getpid()))
        self._handle.flush()
        return True

    def release(self) -> None:
        if self._handle is not None:
            try:
                fcntl.flock(self._handle, fcntl.LOCK_UN)
            finally:
                self._handle.close()
                self._handle = None

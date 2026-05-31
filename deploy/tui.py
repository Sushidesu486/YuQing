#!/usr/bin/env python3
"""YuQing TUI Monitor — real-time logs + GPU/process dashboard using rich."""
from __future__ import annotations

import fcntl
import os
import re
import subprocess
import sys
import termios
import time

try:
    from rich.live import Live
    from rich.layout import Layout
    from rich.panel import Panel
    from rich.console import Console
except ImportError:
    print("rich not installed, run: pip install rich")
    sys.exit(1)

console = Console()

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_BACKEND = os.path.join(PROJECT_DIR, "logs", "backend.log")
LOG_FRONTEND = os.path.join(PROJECT_DIR, "logs", "frontend.log")
PID_BACKEND = os.path.join(PROJECT_DIR, "logs", "backend.pid")
PID_FRONTEND = os.path.join(PROJECT_DIR, "logs", "frontend.pid")

HISTORY_LINES = 200
REFRESH_INTERVAL = 5

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_stdin_fd = sys.stdin.fileno()
_stdin_old = None


def stdin_setup():
    global _stdin_old
    if os.isatty(_stdin_fd):
        _stdin_old = termios.tcgetattr(_stdin_fd)
        new = termios.tcgetattr(_stdin_fd)
        new[3] &= ~(termios.ECHO | termios.ICANON)
        new[6][termios.VMIN] = 0
        new[6][termios.VTIME] = 0
        termios.tcsetattr(_stdin_fd, termios.TCSANOW, new)
    fl = fcntl.fcntl(_stdin_fd, fcntl.F_GETFL)
    fcntl.fcntl(_stdin_fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)


def stdin_restore():
    if _stdin_old:
        termios.tcsetattr(_stdin_fd, termios.TCSANOW, _stdin_old)


def get_key() -> str:
    try:
        data = os.read(_stdin_fd, 8)
        return data.decode("utf-8", errors="replace")
    except (BlockingIOError, OSError):
        return ""


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


# ── log watcher ──
class LogWatcher:
    def __init__(self, path: str):
        self.path = path
        self._pos = 0
        self.lines: list[str] = []
        self._pending: list[str] = []
        self.scroll = 0

    def load_history(self):
        if not os.path.exists(self.path):
            return
        with open(self.path, "r") as f:
            self.lines = [strip_ansi(line.rstrip("\n")) for line in f.readlines()[-HISTORY_LINES:]]
        self._pos = os.path.getsize(self.path)

    def poll(self):
        self._pending = []
        if not os.path.exists(self.path):
            return
        size = os.path.getsize(self.path)
        if size < self._pos:
            self._pos = 0
        if size > self._pos:
            with open(self.path, "r") as f:
                f.seek(self._pos)
                for line in f:
                    self._pending.append(line.rstrip("\n") if line.endswith("\n") else line)
            self._pos = f.tell()

    def commit(self):
        for line in self._pending:
            self.lines.append(strip_ansi(line))
        self.lines = self.lines[-5000:]
        self._pending = []

    def visible(self, n: int) -> list[str]:
        if self.scroll > 0:
            start = -self.scroll - n
            return self.lines[max(start, -len(self.lines)):(-self.scroll if self.scroll > 0 else None)]
        return self.lines[-n:]

    def scroll_up(self, steps: int = 5):
        self.scroll = min(len(self.lines), self.scroll + steps)

    def scroll_down(self, steps: int = 5):
        self.scroll = max(0, self.scroll - steps)

    def scroll_bottom(self):
        self.scroll = 0


# ── system info ──
def port_pid(port: int) -> int:
    try:
        out = subprocess.check_output(["lsof", "-ti", f":{port}"], stderr=subprocess.DEVNULL, timeout=3)
        pids = out.decode().strip().split()
        return int(pids[0]) if pids else 0
    except Exception:
        return 0


def read_pid_file(path: str) -> int:
    try:
        with open(path) as f:
            return int(f.read().strip())
    except Exception:
        return 0


def pid_running(pidfile: str, port: int) -> tuple[bool, int]:
    pid = read_pid_file(pidfile)
    if pid > 0:
        try:
            os.kill(pid, 0)
            return True, pid
        except OSError:
            pass
    # fallback to port
    pid = port_pid(port)
    if pid > 0:
        return True, pid
    return False, 0


def gpu_name() -> str:
    try:
        return subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            stderr=subprocess.DEVNULL, timeout=3,
        ).decode().strip()
    except Exception:
        return "N/A"


def gpu_stats() -> dict[str, str]:
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu",
             "--format=csv,noheader,nounits"],
            stderr=subprocess.DEVNULL, timeout=3,
        ).decode().strip()
        parts = [p.strip() for p in out.split(", ")]
        return {
            "util": parts[0] + "%" if len(parts) > 0 else "?",
            "vram_used": parts[1] if len(parts) > 1 else "?",
            "vram_total": parts[2] if len(parts) > 2 else "?",
            "temp": parts[3] + "°C" if len(parts) > 3 else "?",
        }
    except Exception:
        return {}


def process_mem(pid: int) -> str:
    try:
        out = subprocess.check_output(
            ["ps", "-o", "rss=", "-p", str(pid)],
            stderr=subprocess.DEVNULL, timeout=3,
        ).decode().strip()
        return f"{int(out) / 1024:.0f} MB"
    except Exception:
        return "N/A"


# ── panels ──
def build_sidebar(be_running: bool, fe_running: bool, be_pid: int, fe_pid: int) -> Panel:
    gpu = gpu_stats()
    name = gpu_name()
    lines = [f"[bold]GPU[/] {name}", ""]
    if gpu:
        lines += [
            f"  显存 {gpu.get('vram_used','?')}/{gpu.get('vram_total','?')} GB",
            f"  温度 {gpu.get('temp','?')}",
            f"  利用 {gpu.get('util','?')}",
        ]
    else:
        lines.append("  [dim]N/A[/]")
    lines.append("")
    lines.append("[bold]进程内存[/]")
    lines.append(f"  后端 {process_mem(be_pid)}" if be_running else "  后端 [red]已停止[/]")
    lines.append(f"  前端 {process_mem(fe_pid)}" if fe_running else "  前端 [red]已停止[/]")
    return Panel("\n".join(lines), title="[bold]System[/]", border_style="blue")


def build_header(be_running: bool, fe_running: bool, be_pid: int, fe_pid: int) -> Panel:
    be_s = f"[green]● [{be_pid}][/]" if be_running else f"[red]○ 已停止[/]"
    fe_s = f"[green]● [{fe_pid}][/]" if fe_running else f"[red]○ 已停止[/]"
    return Panel(
        f"[bold cyan]⚡ YuQing Monitor[/]          "
        f"[dim]q:退出 r:刷新 1/2:切日志 ↑↓:翻页 G:底部[/]\n"
        f"后端 {be_s}    前端 {fe_s}",
        border_style="grey50",
    )


def build_footer() -> Panel:
    return Panel("[dim]1/2 switch panel  ↑↓ scroll  G tail-lock  r refresh  q quit[/]",
                 border_style="grey50")


def build_log_panel(title: str, watcher: LogWatcher, n_lines: int, active: bool) -> Panel:
    vs = watcher.visible(n_lines)
    body = "\n".join(vs) if vs else "(waiting for log…)"
    scroll_info = f" [dim](scrolled ↑{watcher.scroll})[/]" if watcher.scroll > 0 else ""
    border = "cyan" if active else "grey50"
    return Panel(body, title=f"[bold]{title}[/]{scroll_info}", border_style=border)


def build(
    bw: LogWatcher, fw: LogWatcher,
    be_running: bool, fe_running: bool,
    be_pid: int, fe_pid: int,
    active_panel: int,
) -> Layout:
    root = Layout()
    root.split(Layout(name="header", size=5), Layout(name="body"), Layout(name="footer", size=3))
    root["body"].split_row(Layout(name="sidebar", size=24), Layout(name="logs"))
    root["logs"].split_column(Layout(name="be_log", ratio=2), Layout(name="fe_log", ratio=1))

    root["header"].update(build_header(be_running, fe_running, be_pid, fe_pid))
    root["footer"].update(build_footer())
    root["sidebar"].update(build_sidebar(be_running, fe_running, be_pid, fe_pid))

    term_h = console.height or 24
    body_h = term_h - 8
    be_h = max(3, body_h * 2 // 3)
    fe_h = max(3, body_h - be_h)

    root["be_log"].update(build_log_panel("Backend Log", bw, be_h, active_panel == 1))
    root["fe_log"].update(build_log_panel("Frontend Log", fw, fe_h, active_panel == 2))
    return root


# ── main loop ──
def main():
    stdin_setup()
    bw = LogWatcher(LOG_BACKEND)
    fw = LogWatcher(LOG_FRONTEND)
    bw.load_history()
    fw.load_history()

    active_panel = 0
    last_sys = 0.0
    be_running, fe_running = False, False
    be_pid, fe_pid = 0, 0

    layout = build(bw, fw, False, False, 0, 0, active_panel)
    live = Live(layout, console=console, refresh_per_second=6, screen=True)

    try:
        live.start()
        esc_buf = ""
        while True:
            bw.poll()
            fw.poll()
            bw.commit()
            fw.commit()

            now = time.time()
            if now - last_sys > REFRESH_INTERVAL:
                last_sys = now
                be_running, be_pid = pid_running(PID_BACKEND, 8000)
                fe_running, fe_pid = pid_running(PID_FRONTEND, 5173)

            live.update(build(bw, fw, be_running, fe_running, be_pid, fe_pid, active_panel))

            key = get_key()
            if not key:
                time.sleep(0.1)
                continue

            # Handle ESC sequences (arrow keys etc)
            if key == '\x1b':
                esc_buf = '\x1b'
                continue
            if esc_buf:
                key = esc_buf + key
                esc_buf = ""

            if key in ('q', 'Q'):
                break
            elif key == 'r' or key == 'R':
                last_sys = 0
            elif key == '1':
                active_panel = 1 if active_panel != 1 else 0
            elif key == '2':
                active_panel = 2 if active_panel != 2 else 0
            elif key in ('g', 'G'):
                bw.scroll_bottom()
                fw.scroll_bottom()
                active_panel = 0
            elif key == '\x1b[A':  # Up
                w = bw if active_panel in (0, 1) else fw
                w.scroll_up()
            elif key == '\x1b[B':  # Down
                w = bw if active_panel in (0, 1) else fw
                w.scroll_down()
            elif key == '\x03':  # Ctrl+C
                break

    except KeyboardInterrupt:
        pass
    finally:
        try:
            live.stop()
        except Exception:
            pass
        stdin_restore()
        print("\nTUI monitor stopped.")


if __name__ == "__main__":
    main()

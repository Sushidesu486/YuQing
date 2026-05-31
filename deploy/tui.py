#!/usr/bin/env python3
"""YuQing TUI Monitor — real-time logs + GPU/process dashboard using rich."""
from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime

# ── CLI: check/fetch rich ──
try:
    from rich.live import Live
    from rich.layout import Layout
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich.console import Console, RenderableType
except ImportError:
    print("rich not installed, run: pip install rich")
    sys.exit(1)

console = Console()

# ── paths ──
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_BACKEND = os.path.join(PROJECT_DIR, "logs", "backend.log")
LOG_FRONTEND = os.path.join(PROJECT_DIR, "logs", "frontend.log")
PID_BACKEND = os.path.join(PROJECT_DIR, "logs", "backend.pid")
PID_FRONTEND = os.path.join(PROJECT_DIR, "logs", "frontend.pid")

HISTORY_LINES = 200
REFRESH_INTERVAL = 5  # seconds for GPU/memory refresh

# ── log state ──
class LogWatcher:
    def __init__(self, path: str):
        self.path = path
        self._pos = 0
        self.tail_lines: list[str] = []
        self.new_lines: list[str] = []
        self.scroll_offset = 0  # 0 = tail (bottom), >0 = scrolled up

    def load_history(self):
        if not os.path.exists(self.path):
            return
        with open(self.path, "r") as f:
            lines = f.readlines()
            self.tail_lines = lines[-HISTORY_LINES:]
        self._pos = os.path.getsize(self.path)

    def poll(self) -> list[str]:
        self.new_lines = []
        if not os.path.exists(self.path):
            return self.new_lines
        size = os.path.getsize(self.path)
        if size < self._pos:
            self._pos = 0  # file truncated/rotated
        if size > self._pos:
            with open(self.path, "r") as f:
                f.seek(self._pos)
                for line in f:
                    if line.endswith("\n"):
                        self.new_lines.append(line.rstrip("\n"))
                    else:
                        self.new_lines.append(line)
            self._pos = f.tell()
        return self.new_lines

    def visible(self, max_lines: int) -> list[str]:
        """Return lines visible in the panel, respecting scroll_offset."""
        # remove ANSI for rich panel (rich renders markup, not raw CSI)
        clean = [strip_ansi(l) for l in self.tail_lines[-max_lines:]]
        return clean

    def append_new(self):
        for line in self.new_lines:
            self.tail_lines.append(line)
        self.tail_lines = self.tail_lines[-5000:]  # cap memory
        self.new_lines = []


def strip_ansi(text: str) -> str:
    """Strip ANSI CSI codes — keep text content, remove control characters."""
    # Rich has its own color system, so we strip the log file's raw ANSI
    # and optionally add back semantic coloring later.
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


# ── system info ──
def gpu_info() -> str:
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu",
             "--format=csv,noheader"],
            stderr=subprocess.DEVNULL, timeout=3,
        ).decode().strip()
        parts = [p.strip() for p in out.split(",")]
        if len(parts) >= 4:
            return f"利用 {parts[0]} | 显存 {parts[1]} / {parts[2]} | 温度 {parts[3]}°C"
    except Exception:
        pass
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            stderr=subprocess.DEVNULL, timeout=3,
        ).decode().strip()
        return out
    except Exception:
        return "N/A"


def pid_running(pidfile: str) -> tuple[bool, int]:
    if not os.path.exists(pidfile):
        return False, 0
    try:
        with open(pidfile) as f:
            pid = int(f.read().strip())
    except Exception:
        return False, 0
    try:
        os.kill(pid, 0)
        return True, pid
    except OSError:
        return False, 0


def process_memory(pid: int) -> str:
    try:
        out = subprocess.check_output(
            ["ps", "-o", "rss=", "-p", str(pid)],
            stderr=subprocess.DEVNULL, timeout=3,
        ).decode().strip()
        mb = int(out) / 1024
        return f"{mb:.0f} MB"
    except Exception:
        return "N/A"


# ── TUI ──
def build_layout(
    bw: LogWatcher, fw: LogWatcher,
    be_running: bool, fe_running: bool,
    be_pid: int, fe_pid: int,
    active_panel: int,  # 0=auto, 1=backend focused, 2=frontend focused
) -> Layout:

    layout = Layout()

    # ── header ──
    be_status = "[green]● 运行中[/green]" if be_running else "[red]○ 已停止[/red]"
    fe_status = "[green]● 运行中[/green]" if fe_running else "[red]○ 已停止[/red]"
    be_mem = process_memory(be_pid) if be_running else "-"
    fe_mem = process_memory(fe_pid) if fe_running else "-"

    # GPU section
    gpu_text = gpu_info()

    header = Table.grid(padding=(0, 2))
    header.add_column()
    header.add_column()
    header.add_row(
        f"[bold cyan]⚡ YuQing Monitor[/]",
        "[dim]q:退出 r:刷新 1/2:切日志 G:到底部[/]",
    )
    header.add_row(
        f"后端 {be_status}  [dim]PID {be_pid}  {be_mem}[/]",
        f"前端 {fe_status}  [dim]PID {fe_pid}  {fe_mem}[/]",
    )
    header.add_row(
        f"[bold]GPU:[/] {gpu_text}",
        "",
    )

    layout.split(
        Layout(Panel(header, title=""), size=7),
        Layout(name="main"),
    )

    # ── main: logs ──
    be_panel_height = 18
    fe_panel_height = 12

    be_lines = bw.visible(be_panel_height)
    fe_lines = fw.visible(fe_panel_height)

    be_text = "\n".join(be_lines[-be_panel_height:]) if be_lines else "(no log)"
    fe_text = "\n".join(fe_lines[-fe_panel_height:]) if fe_lines else "(no log)"

    # Highlight active panel border
    be_border = "cyan" if active_panel == 1 else "grey50"
    fe_border = "cyan" if active_panel == 2 else "grey50"

    log_layout = Layout(name="logs")
    log_layout.split_column(
        Layout(Panel(be_text, title="[bold]Backend Log[/]", border_style=be_border),
               size=be_panel_height + 2),
        Layout(Panel(fe_text, title="[bold]Frontend Log[/]", border_style=fe_border),
               size=fe_panel_height + 2),
    )

    layout["main"].split_row(
        Layout(name="left", size=0),
        Layout(log_layout),
        Layout(name="right", size=0),
    )

    return layout


def main():
    bw = LogWatcher(LOG_BACKEND)
    fw = LogWatcher(LOG_FRONTEND)
    bw.load_history()
    fw.load_history()

    active_panel = 0  # 0=auto-tail, 1=backend focused, 2=frontend focused
    last_refresh = 0.0

    layout = build_layout(bw, fw, False, False, 0, 0, active_panel)
    live = Live(layout, console=console, refresh_per_second=4, screen=True)
    live.start()

    try:
        while True:
            # Poll log changes
            be_new = bw.poll()
            fe_new = fw.poll()
            if be_new or fe_new:
                bw.append_new()
                fw.append_new()

            now = time.time()

            # Refresh GPU/memory status periodically
            if now - last_refresh > REFRESH_INTERVAL:
                last_refresh = now

            be_running, be_pid = pid_running(PID_BACKEND)
            fe_running, fe_pid = pid_running(PID_FRONTEND)

            layout = build_layout(bw, fw, be_running, fe_running,
                                  be_pid, fe_pid, active_panel)
            live.update(layout)

            # Keyboard check (non-blocking)
            if console.is_terminal:
                import select
                r, _, _ = select.select([sys.stdin], [], [], 0.15)
                if r:
                    ch = sys.stdin.read(1)
                    if ch == '\x1b':  # ESC or arrow keys
                        seq = sys.stdin.read(2)
                        if seq == '[A':  # Up arrow
                            if active_panel > 0:
                                bw.scroll_offset += 5
                                fw.scroll_offset += 5
                        elif seq == '[B':  # Down arrow
                            if active_panel > 0:
                                bw.scroll_offset = max(0, bw.scroll_offset - 5)
                                fw.scroll_offset = max(0, fw.scroll_offset - 5)
                    elif ch == 'q':
                        break
                    elif ch == 'r':
                        last_refresh = 0  # force immediate refresh
                    elif ch == '1':
                        active_panel = 1 if active_panel != 1 else 0
                    elif ch == '2':
                        active_panel = 2 if active_panel != 2 else 0
                    elif ch == 'g' or ch == 'G':
                        bw.scroll_offset = 0
                        fw.scroll_offset = 0
                        active_panel = 0
            else:
                time.sleep(0.2)
                # Ctrl+C
    except KeyboardInterrupt:
        pass
    finally:
        live.stop()
        print("TUI monitor stopped.")


if __name__ == "__main__":
    main()

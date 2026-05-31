#!/usr/bin/env python3
"""YuQing TUI Monitor — real-time logs + GPU/process dashboard using rich."""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time

try:
    from rich.live import Live
    from rich.layout import Layout
    from rich.panel import Panel
    from rich.table import Table
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

# ── ANSI strip ──
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


# ── log watcher ──
class LogWatcher:
    def __init__(self, path: str):
        self.path = path
        self._pos = 0
        self.lines: list[str] = []
        self._pending: list[str] = []
        self.scroll = 0                        # 0 = tail-locked

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
                    if line.endswith("\n"):
                        self._pending.append(line.rstrip("\n"))
                    else:
                        self._pending.append(line)
            self._pos = f.tell()

    def commit(self):
        for line in self._pending:
            self.lines.append(strip_ansi(line))
        self.lines = self.lines[-5000:]
        self._pending = []

    def visible(self, n: int) -> list[str]:
        if self.scroll > 0:
            return self.lines[-self.scroll - n:-self.scroll] if self.scroll else self.lines[-n:]
        return self.lines[-n:]

    def scroll_up(self, steps: int = 5):
        self.scroll = min(len(self.lines), self.scroll + steps)

    def scroll_down(self, steps: int = 5):
        self.scroll = max(0, self.scroll - steps)

    def scroll_bottom(self):
        self.scroll = 0


# ── system info ──
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


def process_mem(pid: int) -> str:
    try:
        out = subprocess.check_output(
            ["ps", "-o", "rss=", "-p", str(pid)],
            stderr=subprocess.DEVNULL, timeout=3,
        ).decode().strip()
        return f"{int(out) / 1024:.0f} MB"
    except Exception:
        return "N/A"


# ── build layout ──
def build_sidebar(be_running: bool, fe_running: bool, be_pid: int, fe_pid: int) -> Panel:
    gpu = gpu_stats()
    name = gpu_name()

    lines = [
        f"[bold]GPU[/] {name}",
        "",
    ]
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

    if be_running:
        lines.append(f"  后端 {process_mem(be_pid)}")
    else:
        lines.append(f"  后端 [red]已停止[/]")
    if fe_running:
        lines.append(f"  前端 {process_mem(fe_pid)}")
    else:
        lines.append(f"  前端 [red]已停止[/]")

    return Panel("\n".join(lines), title="[bold]System[/]", border_style="blue")


def build_header(be_running: bool, fe_running: bool, be_pid: int, fe_pid: int) -> Panel:
    be_s = f"[green]● [{be_pid}][/]" if be_running else f"[red]○ 已停止[/]"
    fe_s = f"[green]● [{fe_pid}][/]" if fe_running else f"[red]○ 已停止[/]"
    text = (
        f"[bold cyan]⚡ YuQing Monitor[/]          "
        f"[dim]q:退出  r:刷新  1/2:切日志  ↑↓:翻页  G:底部[/]\n"
        f"后端 {be_s}    前端 {fe_s}"
    )
    return Panel(text, border_style="grey50")


def build_footer() -> Panel:
    return Panel("[dim]Press 1/2 to switch log panel, ↑↓ to scroll, G to tail-lock, r to refresh, q to quit[/]",
                 border_style="grey50")


def build_log_panel(title: str, watcher: LogWatcher, n_lines: int, active: bool) -> Panel:
    vs = watcher.visible(n_lines)
    body = "\n".join(vs) if vs else "(waiting for log…)"

    scroll_info = ""
    if watcher.scroll > 0:
        scroll_info = f" [dim](scrolled ↑{watcher.scroll})[/]"

    border = "cyan" if active else "grey50"
    return Panel(body, title=f"[bold]{title}[/]{scroll_info}", border_style=border)


def build(
    bw: LogWatcher, fw: LogWatcher,
    be_running: bool, fe_running: bool,
    be_pid: int, fe_pid: int,
    active_panel: int,
) -> Layout:
    root = Layout()

    root.split(
        Layout(name="header", size=5),
        Layout(name="body"),
        Layout(name="footer", size=3),
    )

    root["body"].split_row(
        Layout(name="sidebar", size=24),
        Layout(name="logs"),
    )

    root["logs"].split_column(
        Layout(name="be_log", ratio=2),
        Layout(name="fe_log", ratio=1),
    )

    root["header"].update(build_header(be_running, fe_running, be_pid, fe_pid))
    root["footer"].update(build_footer())
    root["sidebar"].update(build_sidebar(be_running, fe_running, be_pid, fe_pid))

    term_h = console.height or 24
    body_h = term_h - 8  # header 5 + footer 3
    be_h = max(3, body_h * 2 // 3)
    fe_h = max(3, body_h - be_h)

    root["be_log"].update(build_log_panel("Backend Log", bw, be_h, active_panel == 1))
    root["fe_log"].update(build_log_panel("Frontend Log", fw, fe_h, active_panel == 2))

    return root


# ── main loop ──
def main():
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

    with live:
        while True:
            bw.poll()
            fw.poll()
            bw.commit()
            fw.commit()

            now = time.time()
            if now - last_sys > REFRESH_INTERVAL:
                last_sys = now
                be_running, be_pid = pid_running(PID_BACKEND)
                fe_running, fe_pid = pid_running(PID_FRONTEND)

            live.update(build(bw, fw, be_running, fe_running, be_pid, fe_pid, active_panel))

            if not console.is_terminal:
                time.sleep(0.3)
                continue

            import select
            if not select.select([sys.stdin], [], [], 0.15)[0]:
                continue

            ch = sys.stdin.read(1)
            if ch == '\x1b':
                seq = sys.stdin.read(2)
                if seq == '[A':                                    # Up
                    w = bw if active_panel in (0, 1) else fw
                    w.scroll_up()
                elif seq == '[B':                                  # Down
                    w = bw if active_panel in (0, 1) else fw
                    w.scroll_down()
            elif ch == 'q':
                break
            elif ch == 'r':
                last_sys = 0
            elif ch == '1':
                active_panel = 1 if active_panel != 1 else 0
            elif ch == '2':
                active_panel = 2 if active_panel != 2 else 0
            elif ch in ('g', 'G'):
                bw.scroll_bottom()
                fw.scroll_bottom()
                active_panel = 0

    print("TUI monitor stopped.")


if __name__ == "__main__":
    main()

"""Desktop OS automation tools: application launching, process monitoring, and notifications."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any, Optional

import psutil

from kaufee.tools.base import BaseTool

DANGEROUS_BINARIES = {
    "cmd", "cmd.exe", "powershell", "powershell.exe", "pwsh", "pwsh.exe",
    "bash", "sh", "zsh", "shutdown", "format", "diskpart", "taskkill",
    "reg", "reg.exe", "bcdedit", "vssadmin",
}

COMMON_DESKTOP_APPS = {
    "notepad": "notepad.exe" if platform.system() == "Windows" else "gedit",
    "calculator": "calc.exe" if platform.system() == "Windows" else "gnome-calculator",
    "calc": "calc.exe" if platform.system() == "Windows" else "gnome-calculator",
    "code": "code",
    "explorer": "explorer.exe" if platform.system() == "Windows" else "xdg-open",
    "paint": "mspaint.exe" if platform.system() == "Windows" else "gimp",
}


class LaunchApplicationTool(BaseTool):
    """Launch verified desktop applications in a non-blocking subprocess."""

    name = "launch_application"
    description = (
        "Launch an allowed desktop application (e.g., 'notepad', 'calc', 'code', 'explorer'). "
        "Blocks arbitrary shells and dangerous system utilities."
    )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "app_name": {
                    "type": "string",
                    "description": "Name or command of the desktop application to launch (e.g. 'notepad', 'calc', 'code').",
                },
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional command-line arguments to pass to the application.",
                    "default": [],
                },
            },
            "required": ["app_name"],
        }

    def run(self, arguments: dict[str, Any], workspace_root: Path) -> tuple[bool, str, dict[str, Any]]:
        app_name = str(arguments.get("app_name", "")).strip().lower()
        cli_args = arguments.get("args", [])
        if not app_name:
            return False, "Argument 'app_name' is required.", {}

        # Block dangerous system binaries
        base_cmd = Path(app_name).name.lower()
        if base_cmd in DANGEROUS_BINARIES:
            return False, f"Launching system binary '{app_name}' is blocked by security policy.", {"blocked": True}

        # Resolve known aliases
        resolved_cmd = COMMON_DESKTOP_APPS.get(app_name, app_name)
        if not shutil.which(resolved_cmd) and not Path(resolved_cmd).exists():
            return False, f"Application executable '{app_name}' was not found on system PATH.", {}

        cmd = [resolved_cmd] + [str(arg) for arg in cli_args]
        try:
            # Spawn asynchronously without blocking the agent
            proc = subprocess.Popen(
                cmd,
                cwd=str(workspace_root),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                start_new_session=True if platform.system() != "Windows" else False,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if platform.system() == "Windows" else 0,
            )
            return True, f"Successfully launched '{app_name}' (PID: {proc.pid}).", {
                "pid": proc.pid,
                "app_name": app_name,
                "command": cmd,
            }
        except Exception as exc:
            return False, f"Failed to launch application '{app_name}': {exc}", {"error": str(exc)}


class ListProcessesTool(BaseTool):
    """Query active system processes and resource consumption."""

    name = "list_system_processes"
    description = "Query running system processes, PIDs, memory usage, and CPU percentages."

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "filter_name": {
                    "type": "string",
                    "description": "Optional substring filter to match process name.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of processes to return (default 25).",
                    "default": 25,
                },
            },
        }

    def run(self, arguments: dict[str, Any], workspace_root: Path) -> tuple[bool, str, dict[str, Any]]:
        filter_name = arguments.get("filter_name")
        limit = max(1, min(100, int(arguments.get("limit", 25))))

        results = []
        try:
            for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
                info = p.info
                name = info.get("name") or ""
                if filter_name and filter_name.lower() not in name.lower():
                    continue
                results.append({
                    "pid": info.get("pid"),
                    "name": name,
                    "cpu_percent": info.get("cpu_percent") or 0.0,
                    "memory_percent": round(info.get("memory_percent") or 0.0, 2),
                })
        except Exception as exc:
            return False, f"Failed to list processes: {exc}", {"error": str(exc)}

        # Sort by memory descending
        results.sort(key=lambda x: x["memory_percent"], reverse=True)
        results = results[:limit]

        lines = [f"{'PID':<8} {'NAME':<30} {'CPU %':<8} {'MEM %':<8}"]
        lines.append("-" * 56)
        for r in results:
            lines.append(f"{r['pid']:<8} {r['name'][:28]:<30} {r['cpu_percent']:<8.1f} {r['memory_percent']:<8.2f}")

        return True, "\n".join(lines), {"count": len(results), "processes": results}


class DesktopNotificationTool(BaseTool):
    """Deliver a non-intrusive desktop notification."""

    name = "send_desktop_notification"
    description = "Display a desktop notification to alert the user of task events or status."

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Notification title."},
                "message": {"type": "string", "description": "Notification body message."},
            },
            "required": ["title", "message"],
        }

    def run(self, arguments: dict[str, Any], workspace_root: Path) -> tuple[bool, str, dict[str, Any]]:
        title = str(arguments.get("title", "Kaufee-Home")).strip()
        message = str(arguments.get("message", "")).strip()
        if not message:
            return False, "Argument 'message' is required.", {}

        # Non-blocking platform notification
        try:
            if platform.system() == "Windows":
                # Use powershell non-blocking tray/balloon notification
                ps_script = (
                    f"[reflection.assembly]::loadwithpartialname('System.Windows.Forms') | Out-Null; "
                    f"$notify = New-Object System.Windows.Forms.NotifyIcon; "
                    f"$notify.Icon = [System.Drawing.SystemIcons]::Information; "
                    f"$notify.Visible = $true; "
                    f"$notify.ShowBalloonTip(3000, '{title}', '{message}', [System.Windows.Forms.ToolTipIcon]::Info);"
                )
                subprocess.Popen(
                    ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_script],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                )
            elif platform.system() == "Darwin":
                osa_script = f'display notification "{message}" with title "{title}"'
                subprocess.Popen(["osascript", "-e", osa_script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                if shutil.which("notify-send"):
                    subprocess.Popen(["notify-send", title, message], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True, f"Notification sent: [{title}] {message}", {"title": title, "message": message}
        except Exception as exc:
            return False, f"Failed to send notification: {exc}", {"error": str(exc)}

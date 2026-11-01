"""Standalone, zero-dependency local web dashboard server for Kaufee-Home."""

from __future__ import annotations

import json
import logging
import os
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

from kaufee import __version__
from kaufee.config import KaufeeConfig
from kaufee.safety.principles import PRINCIPLE_DETAILS, ResponsibleAIPrinciple
from kaufee.state.store import StateStore

logger = logging.getLogger("kaufee.ui.web")

HTML_DASHBOARD = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Kaufee-Home Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body { background-color: #0d1117; color: #c9d1d9; font-family: ui-sans-serif, system-ui, -apple-system, sans-serif; }
        .card { background-color: #161b22; border: 1px solid #30363d; border-radius: 0.5rem; }
        .badge { font-size: 0.75rem; font-weight: 600; padding: 0.2rem 0.5rem; border-radius: 9999px; }
        .badge-success { background-color: #238636; color: #ffffff; }
        .badge-fail { background-color: #da3633; color: #ffffff; }
        .badge-cyan { background-color: #1f6feb; color: #ffffff; }
    </style>
</head>
<body class="p-6">
    <div class="max-w-7xl mx-auto space-y-6">
        <!-- Header -->
        <header class="flex justify-between items-center border-b border-gray-800 pb-4">
            <div>
                <h1 class="text-2xl font-bold text-white flex items-center gap-2">
                    <span>☕ Kaufee-Home</span>
                    <span class="text-xs bg-emerald-950 text-emerald-400 border border-emerald-800 px-2 py-0.5 rounded font-mono">v{{VERSION}}</span>
                </h1>
                <p class="text-sm text-gray-400 mt-1">Verifiable Agentic AI & Responsible Automation Dashboard</p>
            </div>
            <div class="flex items-center gap-3">
                <span id="conn-status" class="badge badge-success">Local Server Online</span>
                <button onclick="fetchData()" class="bg-blue-600 hover:bg-blue-700 text-white text-xs px-3 py-1.5 rounded transition">Refresh</button>
            </div>
        </header>

        <!-- Metrics Grid -->
        <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div class="card p-4">
                <div class="text-xs text-gray-400 uppercase tracking-wider font-semibold">Active Workspace</div>
                <div id="stat-workspace" class="text-sm font-mono text-emerald-400 mt-1 truncate">Loading...</div>
            </div>
            <div class="card p-4">
                <div class="text-xs text-gray-400 uppercase tracking-wider font-semibold">LLM Configuration</div>
                <div id="stat-llm" class="text-sm text-white font-medium mt-1">Loading...</div>
            </div>
            <div class="card p-4">
                <div class="text-xs text-gray-400 uppercase tracking-wider font-semibold">Execution Security</div>
                <div id="stat-security" class="text-sm text-cyan-400 font-medium mt-1">Loading...</div>
            </div>
            <div class="card p-4">
                <div class="text-xs text-gray-400 uppercase tracking-wider font-semibold">Recorded Tasks</div>
                <div id="stat-tasks" class="text-xl font-bold text-white mt-1">0</div>
            </div>
        </div>

        <!-- Main Content (2 Columns) -->
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <!-- Left: Task Audits Table -->
            <div class="lg:col-span-2 space-y-4">
                <div class="card p-5">
                    <h2 class="text-lg font-semibold text-white mb-3 flex items-center justify-between">
                        <span>Recent Task Audits</span>
                        <span class="text-xs text-gray-400">Click task row to inspect full trace</span>
                    </h2>
                    <div class="overflow-x-auto">
                        <table class="w-full text-left text-sm">
                            <thead class="text-xs text-gray-400 uppercase bg-gray-900 border-b border-gray-800">
                                <tr>
                                    <th class="p-3">Task ID</th>
                                    <th class="p-3">Goal</th>
                                    <th class="p-3">Status</th>
                                    <th class="p-3">Steps</th>
                                </tr>
                            </thead>
                            <tbody id="task-tbody" class="divide-y divide-gray-800">
                                <tr><td colspan="4" class="p-4 text-center text-gray-500">No tasks recorded yet</td></tr>
                            </tbody>
                        </table>
                    </div>
                </div>

                <!-- Responsible AI Principles -->
                <div class="card p-5">
                    <h2 class="text-lg font-semibold text-white mb-3">Responsible AI Safety Principles</h2>
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-3" id="principles-container">
                        <!-- Populated dynamically -->
                    </div>
                </div>
            </div>

            <!-- Right: Task Detail & Event Trace -->
            <div class="space-y-4">
                <div class="card p-5 sticky top-6">
                    <h2 class="text-lg font-semibold text-white mb-2">Audit Detail Viewer</h2>
                    <div id="detail-pane" class="text-sm text-gray-400 space-y-3">
                        <p class="italic">Select a task from the list on the left to inspect its timeline, policy decisions, and verified postconditions.</p>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        let currentTasks = [];

        async function fetchData() {
            try {
                const [statusRes, auditsRes, principlesRes] = await Promise.all([
                    fetch('/api/status'),
                    fetch('/api/audits'),
                    fetch('/api/principles')
                ]);
                const status = await statusRes.json();
                const audits = await auditsRes.json();
                const principles = await principlesRes.json();

                // Update Stats
                document.getElementById('stat-workspace').innerText = status.workspace_root || 'workspace';
                document.getElementById('stat-llm').innerText = `${status.llm_provider.toUpperCase()} (${status.model})`;
                document.getElementById('stat-security').innerText = `Autonomy: ${status.autonomy_mode.toUpperCase()} | Runner: ${status.runner.toUpperCase()}`;
                document.getElementById('stat-tasks').innerText = audits.length;

                // Update Audits
                currentTasks = audits;
                const tbody = document.getElementById('task-tbody');
                if (audits.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="4" class="p-4 text-center text-gray-500">No task audits recorded in workspace</td></tr>';
                } else {
                    tbody.innerHTML = audits.map((t, i) => `
                        <tr class="hover:bg-gray-800 cursor-pointer transition" onclick="showDetail('${t.task_id}')">
                            <td class="p-3 font-mono text-xs text-blue-400">${t.task_id.substring(0, 12)}...</td>
                            <td class="p-3 max-w-xs truncate text-gray-200">${t.goal}</td>
                            <td class="p-3">
                                <span class="badge ${t.status === 'COMPLETED' ? 'badge-success' : 'badge-fail'}">${t.status}</span>
                            </td>
                            <td class="p-3 text-xs text-gray-400">${t.step_count || 0}</td>
                        </tr>
                    `).join('');
                }

                // Update Principles
                const princDiv = document.getElementById('principles-container');
                princDiv.innerHTML = principles.map(p => `
                    <div class="p-3 rounded bg-gray-900 border border-gray-800">
                        <div class="font-semibold text-white text-xs flex items-center justify-between">
                            <span>${p.principle}</span>
                            <span class="text-[10px] text-gray-500">${p.mitigation}</span>
                        </div>
                        <div class="text-[11px] text-gray-400 mt-1">${p.risk}</div>
                    </div>
                `).join('');
            } catch (err) {
                console.error("Failed to load dashboard data:", err);
            }
        }

        async function showDetail(taskId) {
            const pane = document.getElementById('detail-pane');
            pane.innerHTML = '<div class="text-center py-6 text-gray-400">Loading audit details...</div>';
            try {
                const res = await fetch(`/api/audits/${taskId}`);
                const data = await res.json();
                
                const eventsHtml = (data.history || []).map((e, idx) => {
                    const action = e.action || {};
                    const result = e.result || {};
                    const isSuccess = result.success !== false;
                    return `
                        <div class="p-3 bg-gray-900 border border-gray-800 rounded space-y-1">
                            <div class="flex items-center justify-between text-xs">
                                <span class="font-bold text-cyan-400">${action.tool_name || 'step'}</span>
                                <span class="badge ${isSuccess ? 'badge-success' : 'badge-fail'}">${isSuccess ? 'PASS' : 'FAIL'}</span>
                            </div>
                            <div class="text-xs text-gray-400 font-mono break-all">${JSON.stringify(action.arguments || {})}</div>
                            ${result.error ? `<div class="text-xs text-red-400">${result.error}</div>` : ''}
                        </div>
                    `;
                }).join('');

                pane.innerHTML = `
                    <div class="space-y-3">
                        <div class="border-b border-gray-800 pb-2">
                            <div class="text-xs text-gray-400 uppercase">Task ID</div>
                            <div class="font-mono text-xs text-white">${data.task_id}</div>
                        </div>
                        <div class="border-b border-gray-800 pb-2">
                            <div class="text-xs text-gray-400 uppercase">Goal</div>
                            <div class="text-sm text-gray-200">${data.goal}</div>
                        </div>
                        <div>
                            <div class="text-xs text-gray-400 uppercase mb-2">Execution Timeline (${(data.history || []).length} events)</div>
                            <div class="space-y-2 max-h-96 overflow-y-auto pr-1">
                                ${eventsHtml || '<p class="text-xs text-gray-500">No events logged.</p>'}
                            </div>
                        </div>
                    </div>
                `;
            } catch (err) {
                pane.innerHTML = `<div class="text-red-400 text-xs">Failed to load task ${taskId}: ${err}</div>`;
            }
        }

        window.onload = fetchData;
        setInterval(fetchData, 5000);
    </script>
</body>
</html>
"""


class DashboardRequestHandler(BaseHTTPRequestHandler):
    """HTTP Request handler serving dashboard HTML and JSON telemetry APIs."""

    def __init__(self, config: KaufeeConfig, store: StateStore, *args, **kwargs):
        self.config = config
        self.store = store
        super().__init__(*args, **kwargs)

    def log_message(self, format: str, *args: Any) -> None:
        # Suppress noisy standard server logging
        pass

    def _send_json(self, status: int, data: Any) -> None:
        raw = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        url = urlparse(self.path)
        path = url.path.rstrip("/")

        if path in ("", "/"):
            rendered = HTML_DASHBOARD.replace("{{VERSION}}", __version__)
            content = rendered.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        if path == "/api/status":
            self._send_json(200, {
                "version": __version__,
                "workspace_root": str(self.config.workspace_root),
                "llm_provider": self.config.llm_provider,
                "model": self.config.ollama_model if self.config.llm_provider == "ollama" else self.config.remote_model,
                "autonomy_mode": self.config.autonomy_mode,
                "approval_mode": self.config.approval_mode,
                "runner": getattr(self.config, "runner_type", "auto"),
            })
            return

        if path == "/api/principles":
            principles_data = [
                {
                    "principle": p.value,
                    "risk": PRINCIPLE_DETAILS[p]["challenge_or_risk"],
                    "example": PRINCIPLE_DETAILS[p]["example"],
                    "mitigation": PRINCIPLE_DETAILS[p]["agentic_mitigation"],
                }
                for p in ResponsibleAIPrinciple
            ]
            self._send_json(200, principles_data)
            return

        if path == "/api/audits":
            tasks = self.store.list_tasks()[:50]
            audits_list = [
                {
                    "task_id": t.get("task_id", ""),
                    "goal": t.get("goal", ""),
                    "status": t.get("status", ""),
                    "created_at": str(t.get("created_at", "")),
                    "step_count": 0,
                }
                for t in tasks
            ]
            self._send_json(200, audits_list)
            return

        if path.startswith("/api/audits/"):
            task_id = path[len("/api/audits/"):].strip()
            task = self.store.load(task_id)
            if not task:
                self._send_json(404, {"error": f"Task '{task_id}' not found"})
                return
            self._send_json(200, {
                "task_id": task.task_id,
                "goal": task.goal,
                "status": task.status.value,
                "history": task.history,
                "plan": task.plan.model_dump() if task.plan else None,
            })
            return

        self.send_error(404, "Not Found")


class LocalDashboardServer:
    """Manages the background HTTP dashboard server."""

    def __init__(self, config: KaufeeConfig, host: str = "127.0.0.1", port: int = 8765):
        self.config = config
        self.host = host
        self.port = port
        self.store = StateStore(config.workspace_root / ".kaufee" / "state")

        def handler_factory(*args, **kwargs):
            return DashboardRequestHandler(self.config, self.store, *args, **kwargs)

        self.server = ThreadingHTTPServer((self.host, self.port), handler_factory)
        self._thread: Optional[threading.Thread] = None

    def start(self, open_browser: bool = True) -> None:
        """Start the server in a daemon thread."""
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self._thread.start()
        url = f"http://{self.host}:{self.port}"
        if open_browser:
            webbrowser.open(url)

    def stop(self) -> None:
        """Stop server gracefully."""
        self.server.shutdown()
        self.server.server_close()

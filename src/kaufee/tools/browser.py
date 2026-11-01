"""Browser automation tools for Kaufee-Home using Playwright and HTTP fallback."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional
import httpx
from kaufee.safety.permissions import is_path_safe_and_within_workspace
from kaufee.safety.redactor import redact_sensitive_text
from kaufee.tools.base import BaseTool


class BrowserOpenTool(BaseTool):
    """Tool to navigate to and inspect web pages."""

    name = "browser_open"
    description = "Navigate to a URL using a headless browser or HTTP client and check title and status."

    def __init__(self, timeout_seconds: float = 15.0):
        self.timeout = timeout_seconds

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Web URL to open (must start with http:// or https://)"},
            },
            "required": ["url"],
        }

    def run(self, arguments: dict[str, Any], workspace_root: Path) -> tuple[bool, str, dict[str, Any]]:
        url = arguments.get("url", "").strip()
        if not url or not (url.startswith("http://") or url.startswith("https://")):
            return False, "Invalid URL. Must begin with http:// or https://", {}

        # 1. Try Playwright
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.set_default_timeout(int(self.timeout * 1000))
                resp = page.goto(url)
                title = page.title()
                status = resp.status if resp else 200
                browser.close()
                return True, f"Successfully loaded '{url}' (Status {status}). Page title: '{title}'", {
                    "url": url,
                    "title": title,
                    "status": status,
                    "engine": "playwright",
                }
        except Exception:
            # 2. Fast HTTP fallback
            try:
                with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
                    resp = client.get(url)
                    resp.raise_for_status()
                    title_match = re.search(r"<title>(.*?)</title>", resp.text, re.IGNORECASE)
                    title = title_match.group(1).strip() if title_match else "No Title"
                    return True, f"Successfully loaded '{url}' (Status {resp.status_code}). Page title: '{title}'", {
                        "url": url,
                        "title": title,
                        "status": resp.status_code,
                        "engine": "httpx",
                    }
            except Exception as exc:
                return False, f"Failed to load URL '{url}': {exc}", {}


class BrowserScrapeTool(BaseTool):
    """Tool to extract sanitized text content from a web page."""

    name = "browser_scrape"
    description = "Extract and clean readable text content from a web page."

    def __init__(self, timeout_seconds: float = 15.0):
        self.timeout = timeout_seconds

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL of the webpage to scrape."},
                "max_chars": {"type": "integer", "description": "Maximum characters to extract (default 5000)."},
            },
            "required": ["url"],
        }

    def run(self, arguments: dict[str, Any], workspace_root: Path) -> tuple[bool, str, dict[str, Any]]:
        url = arguments.get("url", "").strip()
        max_chars = int(arguments.get("max_chars", 5000))
        if not url:
            return False, "Parameter 'url' is required.", {}

        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
                resp = client.get(url)
                resp.raise_for_status()
                text = resp.text

                # Clean scripts and styles
                text = re.sub(r"(?is)<script.*?</script>", "", text)
                text = re.sub(r"(?is)<style.*?</style>", "", text)
                clean_text = re.sub(r"<[^>]+>", " ", text)
                clean_text = re.sub(r"\s+", " ", clean_text).strip()

                if len(clean_text) > max_chars:
                    clean_text = clean_text[:max_chars] + f"... [Truncated at {max_chars} chars]"

                clean_text = redact_sensitive_text(clean_text)
                return True, clean_text, {"url": url, "chars": len(clean_text)}
        except Exception as exc:
            return False, f"Scrape failed for '{url}': {exc}", {}


class BrowserDownloadTool(BaseTool):
    """Tool to safely download web assets into the workspace."""

    name = "browser_download"
    description = "Download a file from a URL and save it within the designated workspace boundary."

    def __init__(self, timeout_seconds: float = 30.0):
        self.timeout = timeout_seconds

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL of the file to download."},
                "destination_path": {"type": "string", "description": "Destination relative file path in workspace."},
            },
            "required": ["url", "destination_path"],
        }

    def run(self, arguments: dict[str, Any], workspace_root: Path) -> tuple[bool, str, dict[str, Any]]:
        url = arguments.get("url", "").strip()
        dest = arguments.get("destination_path") or arguments.get("path", "")
        dest = dest.strip()

        if not url or not dest:
            return False, "Both 'url' and 'destination_path' are required.", {}

        is_safe, reason, resolved_target = is_path_safe_and_within_workspace(
            dest, workspace_root, must_exist=False
        )
        if not is_safe or resolved_target is None:
            return False, reason, {}

        try:
            resolved_target.parent.mkdir(parents=True, exist_ok=True)
            with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
                with client.stream("GET", url) as resp:
                    resp.raise_for_status()
                    total_bytes = 0
                    with open(resolved_target, "wb") as f:
                        for chunk in resp.iter_bytes(chunk_size=8192):
                            total_bytes += len(chunk)
                            if total_bytes > 50_000_000:  # 50MB ceiling
                                return False, "Download aborted: exceeded 50MB safety limit.", {}
                            f.write(chunk)

            return True, f"Successfully downloaded {total_bytes} bytes from '{url}' to '{dest}'.", {
                "url": url,
                "path": dest,
                "bytes": total_bytes,
            }
        except Exception as exc:
            if resolved_target.exists():
                try:
                    resolved_target.unlink()
                except Exception:
                    pass
            return False, f"Download failed: {exc}", {}

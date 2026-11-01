"""Unit tests for browser automation tools."""

from pathlib import Path
from kaufee.state.models import ToolCall
from kaufee.tools.browser import BrowserDownloadTool, BrowserOpenTool, BrowserScrapeTool


def test_browser_open_invalid_url(tmp_path: Path):
    tool = BrowserOpenTool()
    success, msg, meta = tool.run({"url": "invalid-url"}, tmp_path)
    assert not success
    assert "Invalid URL" in msg


def test_browser_open_mock_http(tmp_path: Path, monkeypatch):
    tool = BrowserOpenTool()

    class MockResponse:
        status_code = 200
        text = "<html><head><title>Test Page</title></head><body>Hello</body></html>"
        def raise_for_status(self): pass

    class MockClient:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, url): return MockResponse()

    import httpx
    monkeypatch.setattr(httpx, "Client", MockClient)

    success, msg, meta = tool.run({"url": "https://example.com"}, tmp_path)
    assert success
    assert "Test Page" in msg
    assert meta["title"] == "Test Page"


def test_browser_scrape_cleans_html_and_redacts(tmp_path: Path, monkeypatch):
    tool = BrowserScrapeTool()

    html_content = """
    <html>
        <head><style>body { color: red; }</style></head>
        <body>
            <h1>Welcome</h1>
            <p>Admin token is Bearer 1234567890abcdef1234567890 and secret is Password123!</p>
            <script>console.log("secret")</script>
        </body>
    </html>
    """

    class MockResponse:
        status_code = 200
        text = html_content
        def raise_for_status(self): pass

    class MockClient:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, url): return MockResponse()

    import httpx
    monkeypatch.setattr(httpx, "Client", MockClient)

    success, text, meta = tool.run({"url": "https://example.com/data"}, tmp_path)
    assert success
    assert "<script>" not in text
    assert "<style>" not in text
    assert "1234567890abcdef1234567890" not in text
    assert "Password123!" not in text
    assert "[REDACTED_SECRET]" in text


def test_browser_download_blocks_path_traversal(tmp_path: Path):
    tool = BrowserDownloadTool()
    success, msg, meta = tool.run(
        {"url": "https://example.com/file.zip", "destination_path": "../outside.zip"}, tmp_path
    )
    assert not success
    assert "traversal blocked" in msg.lower() or "outside workspace" in msg.lower()


def test_browser_download_successful_mock(tmp_path: Path, monkeypatch):
    tool = BrowserDownloadTool()

    class MockStreamResponse:
        def raise_for_status(self): pass
        def iter_bytes(self, chunk_size=8192):
            yield b"Sample file content 12345"

    class MockClient:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def stream(self, method, url):
            from contextlib import contextmanager
            @contextmanager
            def _gen(): yield MockStreamResponse()
            return _gen()

    import httpx
    monkeypatch.setattr(httpx, "Client", MockClient)

    dest = "downloads/sample.txt"
    success, msg, meta = tool.run({"url": "https://example.com/sample.txt", "destination_path": dest}, tmp_path)
    assert success
    assert (tmp_path / dest).exists()
    assert (tmp_path / dest).read_bytes() == b"Sample file content 12345"

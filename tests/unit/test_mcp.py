"""Unit tests for Model Context Protocol (MCP) client, manager, and policy integration."""

import json
import sys
import tempfile
from pathlib import Path
import pytest

from kaufee.config import KaufeeConfig
from kaufee.mcp.client import MCPClient, MCPClientError
from kaufee.mcp.manager import MCPManager, MCPProxyTool
from kaufee.safety.policy import PolicyEngine
from kaufee.safety.principles import ResponsibleAIPrinciple
from kaufee.state.models import RiskLevel, ToolCall
from kaufee.tools.registry import ToolRegistry


MOCK_MCP_SERVER_SCRIPT = """
import sys
import json

while True:
    line = sys.stdin.readline()
    if not line:
        break
    data = json.loads(line)
    req_id = data.get("id")
    method = data.get("method")
    
    if method == "initialize":
        res = {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "mock-mcp-server", "version": "1.0.0"}
            }
        }
        sys.stdout.write(json.dumps(res) + "\\n")
        sys.stdout.flush()
    elif method == "notifications/initialized":
        pass  # Notification, no response
    elif method == "tools/list":
        res = {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": [
                    {
                        "name": "query_database",
                        "description": "Execute a query against test database",
                        "inputSchema": {
                            "type": "object",
                            "properties": {"query": {"type": "string"}},
                            "required": ["query"]
                        }
                    }
                ]
            }
        }
        sys.stdout.write(json.dumps(res) + "\\n")
        sys.stdout.flush()
    elif method == "tools/call":
        args = data.get("params", {}).get("arguments", {})
        query = args.get("query", "")
        res = {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [{"type": "text", "text": f"Result for query: {query}"}],
                "isError": False
            }
        }
        sys.stdout.write(json.dumps(res) + "\\n")
        sys.stdout.flush()
"""


def test_mcp_client_handshake_and_tool_call(tmp_path: Path):
    script_path = tmp_path / "mock_server.py"
    script_path.write_text(MOCK_MCP_SERVER_SCRIPT, encoding="utf-8")

    client = MCPClient(
        server_name="test_server",
        command=sys.executable,
        args=[str(script_path)],
        timeout=5.0,
    )
    try:
        client.start()
        tools = client.list_tools()
        assert len(tools) == 1
        assert tools[0]["name"] == "query_database"

        success, output, meta = client.call_tool("query_database", {"query": "SELECT 1;"})
        assert success is True
        assert "Result for query: SELECT 1;" in output
        assert meta["server"] == "test_server"
    finally:
        client.close()


def test_mcp_manager_discovery_and_registration(tmp_path: Path):
    script_path = tmp_path / "mock_server.py"
    script_path.write_text(MOCK_MCP_SERVER_SCRIPT, encoding="utf-8")

    kaufee_dir = tmp_path / ".kaufee"
    kaufee_dir.mkdir(parents=True)
    config_file = kaufee_dir / "mcp_servers.json"
    config_data = {
        "mcpServers": {
            "mockdb": {
                "command": sys.executable,
                "args": [str(script_path)],
            }
        }
    }
    config_file.write_text(json.dumps(config_data), encoding="utf-8")

    manager = MCPManager(workspace_root=tmp_path, config_path=config_file)
    registry = ToolRegistry()
    try:
        count = manager.discover_and_register_tools(registry)
        assert count == 1
        tool = registry.get("mcp__mockdb__query_database")
        assert tool is not None
        assert "mockdb" in tool.description

        result = tool.execute({"query": "SHOW TABLES;"}, workspace_root=tmp_path)
        assert result.success is True
        assert "SHOW TABLES;" in result.output
    finally:
        manager.close_all()


def test_mcp_policy_evaluation(tmp_path: Path):
    cfg = KaufeeConfig(workspace_root=tmp_path, autonomy_mode="assisted")
    policy = PolicyEngine(cfg)

    # 1. Normal MCP tool call requires approval in assisted mode
    action = ToolCall(tool_name="mcp__mockdb__query", arguments={"query": "SELECT * FROM users"})
    decision = policy.validate(action, tmp_path)
    assert decision.allowed is True
    assert decision.requires_approval is True
    assert decision.risk_level == RiskLevel.HIGH
    assert decision.principle == ResponsibleAIPrinciple.ACCOUNTABILITY.value

    # 2. In autonomous mode, approval is not required
    cfg_auto = KaufeeConfig(workspace_root=tmp_path, autonomy_mode="autonomous")
    policy_auto = PolicyEngine(cfg_auto)
    decision_auto = policy_auto.validate(action, tmp_path)
    assert decision_auto.allowed is True
    assert decision_auto.requires_approval is False

    # 3. Path traversal in MCP tool argument is strictly blocked (Privacy & Security)
    unsafe_action = ToolCall(
        tool_name="mcp__files__export",
        arguments={"path": "../../../etc/shadow"},
    )
    unsafe_decision = policy.validate(unsafe_action, tmp_path)
    assert unsafe_decision.allowed is False
    assert unsafe_decision.risk_level == RiskLevel.CRITICAL
    assert unsafe_decision.principle == ResponsibleAIPrinciple.PRIVACY_AND_SECURITY.value
    assert "Path traversal blocked" in unsafe_decision.reason

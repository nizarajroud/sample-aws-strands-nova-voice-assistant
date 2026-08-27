"""
MCP Bridge Tool for Voice Agent Integration.
Loads MCP servers from kiro-cli configs (global + agent) and exposes them
as a single Strands Agent that Nova Sonic can call via tool use.
"""

import json
import os
import logging
from pathlib import Path
from strands import Agent
from strands.tools.mcp import MCPClient
from strands.models import BedrockModel
from mcp import stdio_client, StdioServerParameters

logger = logging.getLogger("mcp_bridge")

# Paths to kiro-cli configs
GLOBAL_MCP_FILE = Path.home() / ".kiro" / "settings" / "mcp.json"
AGENTS_DIR = Path.home() / ".kiro" / "agents"

# MCP servers to load for voice (fast, info-returning tools)
VOICE_MCPS = [
    # From global mcp.json
    "notion-workspace",
    "github",
    "agentcore-memory",
    "bookmarks",
    "fetch",
    "time",
    "firecrawl",
    # From exp2.json
    "remote.bridge.aws-mcp",
    "context7",
    "ssh-mcp-server",
    "memory-exp2",
]

# The env file that holds secrets
ENV_FILE = Path.home() / ".kiro" / ".env"


def _load_env_file():
    """Load environment variables from .env file."""
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key not in os.environ:
                    os.environ[key] = value


def _resolve_env_vars(env_dict: dict) -> dict:
    """Resolve ${VAR} references in env values."""
    resolved = {}
    for key, value in env_dict.items():
        if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
            var_name = value[2:-1]
            resolved[key] = os.environ.get(var_name, "")
        else:
            resolved[key] = value
    return resolved


def _load_all_mcp_configs() -> dict:
    """Load MCP configs from both global and agent files."""
    all_mcps = {}

    # Load global MCPs
    if GLOBAL_MCP_FILE.exists():
        with open(GLOBAL_MCP_FILE) as f:
            data = json.load(f)
        all_mcps.update(data.get("mcpServers", {}))
        logger.info(f"Loaded {len(data.get('mcpServers', {}))} MCPs from global config")

    # Load agent-specific MCPs (exp2)
    agent_file = AGENTS_DIR / "exp2.json"
    if agent_file.exists():
        with open(agent_file) as f:
            data = json.load(f)
        all_mcps.update(data.get("mcpServers", {}))
        logger.info(f"Loaded {len(data.get('mcpServers', {}))} MCPs from exp2 config")

    return all_mcps


def create_mcp_clients() -> list:
    """
    Create MCPClient instances for voice-relevant MCP servers.

    Returns:
        List of MCPClient instances ready to be used with Strands Agent
    """
    _load_env_file()
    all_mcps = _load_all_mcp_configs()
    clients = []

    for mcp_name in VOICE_MCPS:
        if mcp_name not in all_mcps:
            logger.warning(f"MCP '{mcp_name}' not found in any config, skipping")
            continue

        cfg = all_mcps[mcp_name]
        if cfg.get("disabled", False):
            logger.info(f"MCP '{mcp_name}' is disabled, skipping")
            continue

        command = cfg.get("command")
        args = cfg.get("args", [])
        env = _resolve_env_vars(cfg.get("env", {}))

        # Merge with current environment
        full_env = {**os.environ, **env}

        try:
            client = MCPClient(
                lambda cmd=command, a=args, e=full_env: stdio_client(
                    StdioServerParameters(command=cmd, args=a, env=e)
                ),
                prefix=mcp_name.replace("-", "_").replace(".", "_"),
            )
            clients.append(client)
            logger.info(f"Configured MCP client: {mcp_name}")
        except Exception as e:
            logger.error(f"Failed to configure MCP '{mcp_name}': {e}")

    logger.info(f"Total MCP clients configured: {len(clients)}")
    return clients


# Global bridge agent (singleton — initialized once, reused across calls)
_bridge_agent = None
_mcp_clients = []
_initialized = False


def _initialize_bridge():
    """Initialize the MCP Bridge Agent (called once)."""
    global _bridge_agent, _mcp_clients, _initialized

    if _initialized:
        return

    logger.info("Initializing MCP Bridge Agent...")

    _mcp_clients = create_mcp_clients()

    # Start all MCP clients (context manager enter)
    active_clients = []
    for client in _mcp_clients:
        try:
            client.__enter__()
            active_clients.append(client)
        except Exception as e:
            logger.error(f"Failed to start MCP client: {e}")

    logger.info(f"Started {len(active_clients)} MCP clients")

    # Create the bridge agent with MCP clients as tool providers
    import boto3
    session = boto3.Session(region_name="us-east-1")
    model = BedrockModel(
        model_id="anthropic.claude-3-haiku-20240307-v1:0",
        boto_session=session,
    )

    _bridge_agent = Agent(
        model=model,
        system_prompt="""You are a helpful assistant with access to many tools.
Answer the user's question using the available tools.
Be concise — your response will be spoken aloud by a voice assistant.
Limit responses to 2-3 sentences maximum.
Respond in the same language as the question.""",
        tools=active_clients,
    )

    _initialized = True
    logger.info("MCP Bridge Agent initialized successfully")


async def query_bridge(question: str) -> str:
    """
    Query the MCP Bridge Agent.

    Args:
        question: User's question

    Returns:
        Text response from the agent
    """
    try:
        _initialize_bridge()

        response = _bridge_agent(question)

        # Extract text
        if hasattr(response, "content"):
            result = response.content
        elif isinstance(response, dict):
            result = response.get("content", str(response))
        else:
            result = str(response)

        # Limit for voice
        if len(result) > 800:
            result = result[:800] + "... (truncated for voice)"

        return result

    except Exception as e:
        logger.error(f"Bridge query error: {e}")
        return f"Sorry, I encountered an error: {str(e)}"


def shutdown_bridge():
    """Cleanup MCP clients on shutdown."""
    global _mcp_clients, _bridge_agent, _initialized
    for client in _mcp_clients:
        try:
            client.__exit__(None, None, None)
        except Exception:
            pass
    _mcp_clients = []
    _bridge_agent = None
    _initialized = False
    logger.info("MCP Bridge shut down")

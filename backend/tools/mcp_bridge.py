"""
MCP Bridge Tool for Voice Agent Integration.
Loads MCP servers from kiro-cli agent configs and exposes them as a single
Strands Agent that Nova Sonic can call via tool use.
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

# Path to kiro-cli agent configs
AGENTS_DIR = Path.home() / ".kiro" / "agents"

# MCP servers to load for voice (subset — fast, info-returning tools only)
# Exclude: diagram generators, file writers, TTS, video transcribers, etc.
VOICE_MCPS = [
    "notion-workspace",
    "github",
    "agentcore-memory",
    "remote.bridge.aws-mcp",
    "context7",
    "fetch",
    "bookmarks",
    "time",
    "ssh-mcp-server",
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


def _load_mcp_config(agent_name: str = "exp2") -> dict:
    """Load MCP server configs from a kiro-cli agent JSON file."""
    agent_file = AGENTS_DIR / f"{agent_name}.json"
    if not agent_file.exists():
        logger.error(f"Agent config not found: {agent_file}")
        return {}

    with open(agent_file) as f:
        data = json.load(f)

    return data.get("mcpServers", {})


def create_mcp_clients(agent_name: str = "exp2") -> list:
    """
    Create MCPClient instances for voice-relevant MCP servers.

    Args:
        agent_name: Which kiro-cli agent config to read (default: exp2)

    Returns:
        List of MCPClient instances ready to be passed to a Strands Agent
    """
    _load_env_file()
    all_mcps = _load_mcp_config(agent_name)
    clients = []

    for mcp_name in VOICE_MCPS:
        if mcp_name not in all_mcps:
            logger.warning(f"MCP '{mcp_name}' not found in {agent_name} config, skipping")
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


# Global agent instance (singleton)
_bridge_agent = None
_mcp_clients = []


def get_bridge_agent() -> Agent:
    """Get or create the MCP bridge agent (singleton)."""
    global _bridge_agent, _mcp_clients

    if _bridge_agent is not None:
        return _bridge_agent

    logger.info("Initializing MCP Bridge Agent...")

    # Create MCP clients
    _mcp_clients = create_mcp_clients("exp2")

    # Enter all MCP client contexts
    active_clients = []
    for client in _mcp_clients:
        try:
            client.__enter__()
            active_clients.append(client)
        except Exception as e:
            logger.error(f"Failed to start MCP client: {e}")

    # Collect all tools from active MCP clients
    all_tools = []
    for client in active_clients:
        try:
            tools = client.list_tools_sync()
            all_tools.extend(tools)
            logger.info(f"  Loaded {len(tools)} tools from MCP")
        except Exception as e:
            logger.error(f"  Failed to list tools: {e}")

    logger.info(f"Total tools available: {len(all_tools)}")

    # Create the bridge agent with all MCP tools
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

    logger.info("MCP Bridge Agent initialized successfully")
    return _bridge_agent


async def query_bridge(question: str) -> str:
    """
    Query the MCP Bridge Agent.

    Args:
        question: User's question

    Returns:
        Text response from the agent
    """
    try:
        agent = get_bridge_agent()
        response = agent(question)

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
    global _mcp_clients, _bridge_agent
    for client in _mcp_clients:
        try:
            client.__exit__(None, None, None)
        except Exception:
            pass
    _mcp_clients = []
    _bridge_agent = None
    logger.info("MCP Bridge shut down")

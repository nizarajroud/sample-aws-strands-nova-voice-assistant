"""
MCP Daemon — Persistent MCP Bridge for Voice Agent.

Loads MCP servers from kiro-cli configs ONCE at backend startup and keeps them
alive for the lifetime of the server. Each voice query reuses the already-warm
agent instead of reloading MCPs (avoids the ~30-55s reload cost per query).

Usage:
    # At backend startup (once):
    await MCPDaemon.get_instance().initialize()

    # Per voice query (fast — MCPs already loaded):
    answer = await MCPDaemon.get_instance().query("what time is it?")
"""

import json
import os
import logging
import asyncio
from pathlib import Path
from strands import Agent
from strands.tools.mcp import MCPClient
from strands.models import BedrockModel
from mcp import stdio_client, StdioServerParameters

logger = logging.getLogger("mcp_daemon")

# Paths to kiro-cli configs
GLOBAL_MCP_FILE = Path.home() / ".kiro" / "settings" / "mcp.json"
AGENTS_DIR = Path.home() / ".kiro" / "agents"
ENV_FILE = Path.home() / ".kiro" / ".env"

# MCP servers to load for voice (minimal — start with memory only).
# Keep this list small — every MCP adds startup time and tool-selection latency.
VOICE_MCPS = [
    "agentcore-memory",
]


def _load_env_file():
    """Load environment variables from ~/.kiro/.env."""
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
            resolved[key] = os.environ.get(value[2:-1], "")
        else:
            resolved[key] = value
    return resolved


def _load_all_mcp_configs() -> dict:
    """Load MCP configs from both global and exp2 agent files."""
    all_mcps = {}
    if GLOBAL_MCP_FILE.exists():
        with open(GLOBAL_MCP_FILE) as f:
            all_mcps.update(json.load(f).get("mcpServers", {}))
    agent_file = AGENTS_DIR / "exp2.json"
    if agent_file.exists():
        with open(agent_file) as f:
            all_mcps.update(json.load(f).get("mcpServers", {}))
    return all_mcps


class MCPDaemon:
    """Singleton daemon that keeps MCP servers + a Strands agent warm."""

    _instance = None

    def __init__(self):
        self.agent = None
        self.mcp_clients = []
        self.initialized = False

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = MCPDaemon()
        return cls._instance

    def _build_clients(self) -> list:
        """Create MCPClient instances for the voice MCP subset."""
        _load_env_file()
        all_mcps = _load_all_mcp_configs()
        clients = []

        for name in VOICE_MCPS:
            if name not in all_mcps:
                logger.warning(f"MCP '{name}' not found in configs, skipping")
                continue
            cfg = all_mcps[name]
            if cfg.get("disabled", False):
                continue

            command = cfg.get("command")
            args = cfg.get("args", [])
            mcp_env = _resolve_env_vars(cfg.get("env", {}))

            # Build the child env. Start from the current environment so the MCP
            # inherits PATH etc.
            env = {**os.environ, **mcp_env}

            # Ensure USER is set explicitly — the agentcore-memory MCP uses it as
            # the actor_id when ACTOR_ID_TYPE=userid. If missing, it falls back to
            # a literal "$USER" which fails AWS actorId validation.
            if not env.get("USER"):
                import getpass
                env["USER"] = getpass.getuser()

            # If this MCP declares its own AWS_PROFILE, it must use that profile's
            # credentials — NOT the credentials we exported for Nova Sonic (which
            # belong to a different account). Explicit AWS_ACCESS_KEY_ID env vars
            # take priority over AWS_PROFILE, so we must strip them here.
            if mcp_env.get("AWS_PROFILE"):
                for cred_key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
                                 "AWS_SESSION_TOKEN", "AWS_DEFAULT_REGION"):
                    env.pop(cred_key, None)
                logger.info(f"MCP '{name}' uses AWS_PROFILE={mcp_env['AWS_PROFILE']} "
                            f"(stripped inherited credentials)")

            client = MCPClient(
                lambda cmd=command, a=args, e=env: stdio_client(
                    StdioServerParameters(command=cmd, args=a, env=e)
                ),
                prefix=name.replace("-", "_").replace(".", "_"),
            )
            clients.append(client)
            logger.info(f"Configured MCP: {name}")

        return clients

    def initialize(self):
        """
        Load MCPs and build the agent. Call ONCE at backend startup.
        This is the slow part (~30s) — done once, not per query.
        """
        if self.initialized:
            logger.info("MCP Daemon already initialized")
            return

        logger.info("=" * 50)
        logger.info("MCP DAEMON: Loading MCP servers (one-time startup)...")
        logger.info("=" * 50)

        self.mcp_clients = self._build_clients()

        import boto3
        session = boto3.Session(region_name="us-east-1")
        model = BedrockModel(
            model_id="anthropic.claude-3-haiku-20240307-v1:0",
            boto_session=session,
        )

        self.agent = Agent(
            model=model,
            system_prompt="""You are a helpful personal assistant for Nizar.
You have access to a conversational memory tool (agentcore-memory) that stores
the history of Nizar's past kiro-cli sessions and conversations.
When asked a question, search this memory to find relevant context.

CRITICAL TOOL USAGE:
- When calling memory tools, do NOT pass an actor_id parameter — leave it empty
  so the tool resolves the current user automatically. Never invent values like
  "$USER" or "nizar" for actor_id.
- Use the query/search parameters to find relevant conversations.

Answer concisely — responses are spoken aloud (2-3 sentences max).
Respond in the same language as the question.
If the memory has no relevant information, say so briefly.""",
            tools=self.mcp_clients,
        )

        self.initialized = True
        logger.info("=" * 50)
        logger.info(f"MCP DAEMON: Ready with {len(self.mcp_clients)} MCP servers (warm)")
        logger.info("=" * 50)

    async def query(self, question: str) -> str:
        """
        Query the warm agent. Fast — MCPs already loaded.

        Args:
            question: User's question

        Returns:
            Text response
        """
        if not self.initialized:
            logger.warning("Daemon not initialized, initializing now (slow)...")
            self.initialize()

        try:
            # Run the agent call in a thread to avoid blocking the event loop
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, self.agent, question)

            if hasattr(response, "content"):
                result = response.content
            elif isinstance(response, dict):
                result = response.get("content", str(response))
            else:
                result = str(response)

            if len(result) > 800:
                result = result[:800] + "... (truncated for voice)"

            return result

        except Exception as e:
            logger.error(f"Daemon query error: {e}")
            return f"Sorry, I encountered an error: {str(e)}"

    def shutdown(self):
        """Cleanup MCP clients on backend shutdown."""
        for client in self.mcp_clients:
            try:
                client.__exit__(None, None, None)
            except Exception:
                pass
        self.mcp_clients = []
        self.agent = None
        self.initialized = False
        logger.info("MCP Daemon shut down")

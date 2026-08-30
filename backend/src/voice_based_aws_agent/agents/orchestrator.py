"""
Agent Orchestrator — MCP Daemon mode.
Routes all queries to the warm MCP Daemon (MCPs loaded once at startup).
"""

import logging
from typing import Dict, Any

from ..config.tool_config import setup_tool_environment, get_tool_config

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """Orchestrator that routes all queries to the warm MCP Daemon."""

    def __init__(self, config=None):
        self.config = config
        self._setup_environment()
        logger.info("Agent Orchestrator initialized (MCP Daemon mode)")

    def _setup_environment(self):
        logger.info("Setting up tool environment...")
        setup_tool_environment()
        logger.info(f"Tool configuration: {get_tool_config()}")

    async def process_query(self, query: str) -> str:
        """Process a user query through the warm MCP Daemon."""
        try:
            logger.info(f"Processing query via MCP Daemon: {query}")
            from tools.mcp_daemon import MCPDaemon
            result = await MCPDaemon.get_instance().query(query)
            logger.info("Query processed successfully via MCP Daemon")
            return result
        except Exception as e:
            logger.error(f"Error processing query: {str(e)}")
            return f"Error: Unable to process query - {str(e)}"

    def get_agent_status(self) -> Dict[str, Any]:
        return {
            "mode": "mcp_daemon",
            "source": "~/.kiro/settings/mcp.json + agents/exp2.json",
            "tool_config": get_tool_config(),
        }

    def shutdown(self):
        logger.info("Shutting down agent orchestrator")

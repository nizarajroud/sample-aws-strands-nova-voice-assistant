"""
Agent Orchestrator — MCP Bridge Mode.
Routes all queries through the MCP Bridge Agent which has access to
all kiro-cli MCP servers (Notion, GitHub, Memory, etc.)
"""

import logging
from typing import Dict, Any
from ..config.tool_config import setup_tool_environment, get_tool_config

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """
    Orchestrator that routes all queries to the MCP Bridge Agent.
    The bridge agent has access to all kiro-cli MCP servers.
    """

    def __init__(self, config=None):
        """Initialize the orchestrator."""
        self.config = config
        self._setup_environment()
        logger.info("Agent Orchestrator initialized (MCP Bridge mode)")

    def _setup_environment(self):
        """Set up the environment for tool operations."""
        logger.info("Setting up tool environment...")
        setup_tool_environment()
        config = get_tool_config()
        logger.info(f"Tool configuration: {config}")

    async def process_query(self, query: str) -> str:
        """
        Process a user query through the MCP Bridge Agent.

        Args:
            query: User query to process

        Returns:
            Response from the bridge agent
        """
        try:
            logger.info(f"Processing query via MCP Bridge: {query}")

            from tools.mcp_bridge import query_bridge
            response = await query_bridge(query)

            logger.info("Query processed successfully via MCP Bridge")
            return response

        except Exception as e:
            logger.error(f"Error processing query: {str(e)}")
            return f"Error: Unable to process query - {str(e)}"

    def get_agent_status(self) -> Dict[str, Any]:
        """Get status of the system."""
        return {
            "mode": "mcp_bridge",
            "source": "~/.kiro/agents/exp2.json",
            "tool_config": get_tool_config(),
        }

    def shutdown(self):
        """Shutdown gracefully."""
        from tools.mcp_bridge import shutdown_bridge
        shutdown_bridge()
        logger.info("Shutting down agent orchestrator")

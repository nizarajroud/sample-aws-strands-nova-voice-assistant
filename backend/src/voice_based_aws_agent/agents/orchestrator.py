"""
Agent Orchestrator — Knowledge Base mode.
Routes all queries to the Bedrock Knowledge Base via retrieve_and_generate.
"""

import logging
from typing import Dict, Any

from ..config.tool_config import setup_tool_environment, get_tool_config

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """
    Orchestrator that routes all queries to the Bedrock Knowledge Base.
    """

    def __init__(self, config=None):
        """Initialize the orchestrator."""
        self.config = config
        self._setup_environment()
        logger.info("Agent Orchestrator initialized (Knowledge Base mode)")

    def _setup_environment(self):
        """Set up the environment for tool operations."""
        logger.info("Setting up tool environment...")
        setup_tool_environment()
        config = get_tool_config()
        logger.info(f"Tool configuration: {config}")

    async def process_query(self, query: str) -> str:
        """
        Process a user query through the Knowledge Base.

        Args:
            query: User query to process

        Returns:
            Response from the knowledge base
        """
        try:
            logger.info(f"Processing query via Knowledge Base: {query}")

            from tools.knowledge_base_tool import query_knowledge_base
            response = query_knowledge_base(question=query)

            if hasattr(response, 'content'):
                result = response.content
            elif isinstance(response, dict):
                result = response.get('content', str(response))
            else:
                result = str(response)

            logger.info("Query processed successfully via Knowledge Base")
            return result

        except Exception as e:
            logger.error(f"Error processing query: {str(e)}")
            return f"Error: Unable to process query - {str(e)}"

    def get_agent_status(self) -> Dict[str, Any]:
        """Get status of the system."""
        return {
            "mode": "knowledge_base",
            "knowledge_base_id": "9DPWLUDY7J",
            "region": "ca-central-1",
            "tool_config": get_tool_config(),
        }

    def shutdown(self):
        """Shutdown gracefully."""
        logger.info("Shutting down agent orchestrator")

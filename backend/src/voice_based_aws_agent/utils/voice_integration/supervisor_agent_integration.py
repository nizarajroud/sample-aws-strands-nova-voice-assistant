"""
Integration for the MCP Bridge Agent.
Routes all voice queries through the Strands agent with kiro-cli MCPs.
"""

import json
import logging
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("SupervisorAgentIntegration")


class SupervisorAgentIntegration:
    """
    Integration class — routes all voice queries to the MCP Bridge Agent.
    """

    def __init__(self, config=None):
        """Initialize the integration."""
        self.config = config
        self.orchestrator = None

        try:
            from src.voice_based_aws_agent.agents.orchestrator import AgentOrchestrator
            from src.voice_based_aws_agent.config.tool_config import setup_tool_environment
            from tools.supervisor_tool import set_orchestrator

            setup_tool_environment()
            self.orchestrator = AgentOrchestrator(config)
            set_orchestrator(self.orchestrator)

            logger.info("MCP Bridge orchestrator initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize orchestrator: {e}")
            self.orchestrator = None

    async def query(self, query_text):
        """
        Process a query through the MCP Bridge Agent.

        Args:
            query_text: The user's query

        Returns:
            str: The response
        """
        try:
            logger.info(f"Processing query: {query_text[:100]}...")

            # Parse input
            if isinstance(query_text, str):
                try:
                    query_json = json.loads(query_text)
                    actual_query = query_json.get("query", query_text)
                except json.JSONDecodeError:
                    actual_query = query_text
            else:
                actual_query = query_text.get("query", str(query_text))

            if self.orchestrator:
                response = await self.orchestrator.process_query(actual_query)
                logger.info("Query processed successfully")

                if hasattr(response, "content"):
                    response_text = response.content
                elif isinstance(response, dict):
                    response_text = response.get("content", str(response))
                else:
                    response_text = str(response)

                if len(response_text) > 800:
                    response_text = response_text[:800] + "... (truncated for voice)"

                return response_text
            else:
                return "The MCP Bridge is not available. Please check backend logs."

        except Exception as e:
            logger.error(f"Error: {e}")
            return f"Sorry, I encountered an error: {str(e)}"

    def shutdown(self):
        """Shutdown."""
        if self.orchestrator:
            self.orchestrator.shutdown()
        logger.info("SupervisorAgentIntegration shutdown")

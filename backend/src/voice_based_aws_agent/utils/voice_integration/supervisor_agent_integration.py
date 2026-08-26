"""
Integration for the Knowledge Base Agent.
Simplified version that routes all queries to Bedrock Knowledge Base.
"""

import json
import logging
import sys
import os
from pathlib import Path

project_root = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("SupervisorAgentIntegration")


class SupervisorAgentIntegration:
    """
    Integration class — routes all voice queries to the Knowledge Base.
    """

    def __init__(self, config=None):
        """Initialize the integration with Knowledge Base orchestrator."""
        self.config = config
        self.orchestrator = None

        try:
            from src.voice_based_aws_agent.agents.orchestrator import AgentOrchestrator
            from src.voice_based_aws_agent.config.tool_config import setup_tool_environment
            from tools.supervisor_tool import set_orchestrator

            # Setup tool environment
            setup_tool_environment()

            # Initialize the simplified orchestrator
            self.orchestrator = AgentOrchestrator(config)

            # Set the orchestrator for the supervisor tool
            set_orchestrator(self.orchestrator)

            logger.info("Knowledge Base orchestrator initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize orchestrator: {e}")
            logger.info("Falling back to placeholder mode")
            self.orchestrator = None

    async def query(self, query_text):
        """
        Process a query through the Knowledge Base.

        Args:
            query_text: The user's query

        Returns:
            str: The response from the knowledge base
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

            # Route to orchestrator (Knowledge Base)
            if self.orchestrator:
                try:
                    response = await self.orchestrator.process_query(actual_query)
                    logger.info("Query processed successfully via Knowledge Base")

                    if hasattr(response, "content"):
                        response_text = response.content
                    elif isinstance(response, dict):
                        response_text = response.get("content", str(response))
                    else:
                        response_text = str(response)

                    # Limit for voice
                    if len(response_text) > 800:
                        response_text = response_text[:800] + "... (truncated for voice)"

                    return response_text

                except Exception as e:
                    logger.error(f"Error processing query: {e}")
                    return f"Sorry, I encountered an error: {str(e)}"

            else:
                return "The knowledge base is not available. Please check the backend logs."

        except Exception as e:
            logger.error(f"Error in supervisor agent integration: {e}")
            return f"Sorry, I encountered an error: {str(e)}"

    def shutdown(self):
        """Shutdown the integration."""
        if self.orchestrator and hasattr(self.orchestrator, "shutdown"):
            self.orchestrator.shutdown()
        logger.info("SupervisorAgentIntegration shutdown")

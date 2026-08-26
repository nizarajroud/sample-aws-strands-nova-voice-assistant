"""
Agent Orchestrator — Customized for Knowledge Base only.
Routes all queries to the Bedrock Knowledge Base agent instead of EC2/SSM/Backup.
"""

import logging
from typing import Dict, Any

# COMMENTED OUT: Original AWS specialized agents
# from .supervisor_agent import SupervisorAgent
# from .ec2_agent import EC2Agent
# from .ssm_agent import SSMAgent
# from .backup_agent import BackupAgent

from ..config.tool_config import setup_tool_environment, get_tool_config

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """
    Simplified orchestrator that routes all queries to the Knowledge Base.
    No more EC2/SSM/Backup agents — just direct KB lookup.
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

            # Import and call the knowledge base tool directly
            from tools.knowledge_base_tool import query_knowledge_base
            response = query_knowledge_base(question=query)

            # Extract string result
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
            "agent_id": "4EBXLZQW3Q",
            "region": "ca-central-1",
            "tool_config": get_tool_config(),
        }

    def shutdown(self):
        """Shutdown gracefully."""
        logger.info("Shutting down agent orchestrator")

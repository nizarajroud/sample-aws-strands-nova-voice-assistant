"""
Knowledge Base Tool for Voice Agent Integration.
Queries a Bedrock Agent connected to a knowledge base for project-specific Q&A.
"""

import boto3
import logging
from strands import tool

logger = logging.getLogger("knowledge_base_tool")

# Configuration
AGENT_ID = "4EBXLZQW3Q"
AGENT_ALIAS_ID = "TSTALIASID"
REGION = "ca-central-1"


@tool(name="queryKnowledgeBase")
def query_knowledge_base(question: str) -> str:
    """
    Query the personal knowledge base via Bedrock Agent.
    Use this tool to answer questions about projects, personal notes,
    documentation, and any information stored in the knowledge base.

    Args:
        question: The user's question to search the knowledge base for

    Returns:
        str: Answer from the knowledge base
    """
    try:
        logger.info(f"Querying knowledge base: {question[:100]}...")

        client = boto3.client("bedrock-agent-runtime", region_name=REGION)

        response = client.invoke_agent(
            agentId=AGENT_ID,
            agentAliasId=AGENT_ALIAS_ID,
            sessionId="voice-session",
            inputText=question,
        )

        # Read the streaming response
        result = ""
        for event in response["completion"]:
            if "chunk" in event:
                result += event["chunk"]["bytes"].decode()

        if not result:
            result = "I couldn't find relevant information in the knowledge base for that question."

        # Limit for voice output
        if len(result) > 800:
            result = result[:800] + "... (truncated for voice)"

        logger.info(f"Knowledge base result: {result[:100]}...")
        return result

    except Exception as e:
        error_msg = f"Error querying knowledge base: {str(e)}"
        logger.error(error_msg)
        return error_msg

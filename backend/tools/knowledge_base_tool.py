"""
Knowledge Base Tool for Voice Agent Integration.
Uses retrieve_and_generate for low latency with pre-warmed boto3 client.
"""

import boto3
import logging
from strands import tool

logger = logging.getLogger("knowledge_base_tool")

# Configuration
KNOWLEDGE_BASE_ID = "9DPWLUDY7J"
MODEL_ARN = "arn:aws:bedrock:ca-central-1::foundation-model/anthropic.claude-3-haiku-20240307-v1:0"
REGION = "ca-central-1"
PROFILE = "csna-operations-sso-828"

# Pre-warm the boto3 client (avoids ~500ms cold start on each call)
_client = None


def _get_client():
    """Get or create the pre-warmed bedrock-agent-runtime client."""
    global _client
    if _client is None:
        session = boto3.Session(profile_name=PROFILE, region_name=REGION)
        _client = session.client("bedrock-agent-runtime")
        logger.info("boto3 bedrock-agent-runtime client pre-warmed")
    return _client


@tool(name="queryKnowledgeBase")
def query_knowledge_base(question: str) -> str:
    """
    Query the personal knowledge base directly via Bedrock retrieve_and_generate.
    Faster than invoke_agent — skips the agent orchestration layer.

    Args:
        question: The user's question to search the knowledge base for

    Returns:
        str: Answer from the knowledge base
    """
    try:
        logger.info(f"Querying knowledge base (direct): {question[:100]}...")

        client = _get_client()

        response = client.retrieve_and_generate(
            input={"text": question},
            retrieveAndGenerateConfiguration={
                "type": "KNOWLEDGE_BASE",
                "knowledgeBaseConfiguration": {
                    "knowledgeBaseId": KNOWLEDGE_BASE_ID,
                    "modelArn": MODEL_ARN,
                },
            },
        )

        result = response["output"]["text"]

        if not result:
            result = "I couldn't find relevant information in the knowledge base for that question."

        # Limit for voice output
        if len(result) > 800:
            result = result[:800] + "... (truncated for voice)"

        logger.info(f"Knowledge base result ({len(result)} chars): {result[:80]}...")
        return result

    except Exception as e:
        error_msg = f"Error querying knowledge base: {str(e)}"
        logger.error(error_msg)
        return error_msg

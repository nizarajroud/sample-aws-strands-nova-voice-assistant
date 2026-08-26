"""
Knowledge Base Tool for Voice Agent Integration.
Uses retrieve_and_generate for lower latency (skips the agent layer).
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

        session = boto3.Session(profile_name=PROFILE, region_name=REGION)
        client = session.client("bedrock-agent-runtime")

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

"""
Orchestration System for Voice-based Knowledge Base Agent

This package contains:
- AgentOrchestrator: Routes all queries to the Bedrock Knowledge Base
"""

from .orchestrator import AgentOrchestrator

__all__ = [
    "AgentOrchestrator",
]

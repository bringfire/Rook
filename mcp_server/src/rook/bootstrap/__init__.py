"""
Bootstrap Knowledge System

This package provides tools for systematically testing MCP tools
and building ground truth in the knowledge graph.

Workflow:
1. Define test cases in test_matrix.py
2. Run tests with runner.py (records to local knowledge)
3. Human validates local knowledge
4. Transfer validated entries to canonical with transfer.py

Usage:
    python -m rook.bootstrap run --phase 1
    python -m rook.bootstrap summary
    python -m rook.bootstrap transfer --reviewed
"""

from .test_matrix import TestCase, TestMatrix, TOOL_TESTS
from .runner import BootstrapRunner, TestResult
from .transfer import KnowledgeTransfer
from .executor import HttpExecutor, create_http_executor, create_mock_executor

__all__ = [
    "TestCase",
    "TestMatrix",
    "TOOL_TESTS",
    "BootstrapRunner",
    "TestResult",
    "KnowledgeTransfer",
    "HttpExecutor",
    "create_http_executor",
    "create_mock_executor",
]

"""
Learning module for Rook Autonomous Learning Agent.

This package contains infrastructure for autonomous knowledge cultivation,
investigation, visual verification, DSPy/MAB reasoning, and command/GH
knowledge systems.

Public symbols are resolved lazily so lightweight submodules such as
``rook.learning.plan_graph_outcomes`` can be imported without loading DSPy,
LiteLLM, or the heavier learning stack.
"""

from importlib import import_module
from typing import Any


__all__ = [
    # Schema classes
    "Pattern",
    "Antipattern",
    "Gap",
    "GapStatus",
    "GapPriority",
    "Insight",
    "InsightCategory",
    "ToolRelationship",
    "RelationshipType",
    "Verification",
    "SessionHandoff",
    "CultivationStats",
    "KnowledgeGraphV2Data",
    "ErrorCategory",
    # Knowledge Graph API
    "KnowledgeGraphV2",
    # Investigation
    "Investigator",
    "InvestigationResult",
    "Diagnosis",
    # Verification
    "VisualVerifier",
    "ViewportState",
    "StateDiff",
    # Session Management
    "LearningSession",
    "SessionPlan",
    "SessionProgress",
    # Agent
    "AutonomousLearningAgent",
    # Prompts
    "get_prompt",
    "CULTIVATOR_SYSTEM_PROMPT",
    # Monitoring
    "ProgressReporter",
    "AgentStatus",
    "setup_logging",
    "read_agent_status",
    "print_agent_status",
    "tail_log",
    # DSPy Configuration
    "configure_dspy",
    "get_lm",
    "is_configured",
    "TemporaryLMSettings",
    # DSPy Signatures
    "OrientSession",
    "PlanInvestigation",
    "DiagnoseFailure",
    "GenerateHypotheses",
    "SynthesizeInsight",
    "ConsolidatePattern",
    "SemanticFeedback",
    "DetectWorkflow",
    "ExecuteWithReasoning",
    "VerifyResult",
    # DSPy Modules
    "SessionOrienter",
    "InvestigationPlanner",
    "FailureDiagnoser",
    "HypothesisGenerator",
    "InsightSynthesizer",
    "PatternConsolidator",
    "FeedbackComputer",
    "WorkflowDetector",
    "ReasoningExecutor",
    "ResultVerifier",
    "ActionSelector",
    "InvestigationOrchestrator",
    "create_all_modules",
    # MAB Selectors
    "HypothesisSelector",
    "FixSelector",
    "PrioritySelector",
    "SelectionContext",
    "create_all_selectors",
    # Hybrid Investigator
    "HybridInvestigator",
    "HybridInvestigationResult",
    # Knowledge Consolidation Layer
    "IdentifyContexts",
    "ClassifyPattern",
    "ConsolidateContext",
    "ExtractErrorCategories",
    "GenerateQuickSummary",
    "ConsolidatedContext",
    "ConsolidatedTool",
    "ConsolidatedKnowledge",
    "IntelligentConsolidator",
    "consolidate_tool",
    "consolidate_all_tools",
    "consolidate_single_tool",
    "extract_patterns_by_tool",
    "DEFAULT_CONDENSED_PATH",
    "DEFAULT_TOOL_DESCRIPTIONS",
    # Retrieval MAB
    "QueryFeatures",
    "QueryFeatureEncoder",
    "RetrievalOutcome",
    "KnowledgeRetrievalMAB",
    "load_retrieval_mab",
    "initialize_retrieval_mab_from_condensed",
    "DEFAULT_RETRIEVAL_MAB_PATH",
    # Grasshopper Knowledge System
    "GHSparseIndex",
    "GHTieredKnowledge",
    "GHKnowledgeStore",
    "get_gh_knowledge_store",
    "gh_query_knowledge",
    "GH_TIER_TOKEN_ESTIMATES",
    # Sugiyama Canvas Layout
    "SugiyamaLayout",
    "SugiyamaNode",
    "SugiyamaEdge",
    # Command Learning System
    "InputType",
    "PromptType",
    "DialogueStep",
    "CommandPreconditions",
    "CommandResult",
    "CommandObservation",
    "DialogueParser",
    "ObservationStore",
    "CommandObserver",
    "DEFAULT_OBSERVATION_STORE_PATH",
    # Command Knowledge Store
    "CommandKnowledgeStore",
    "CommandKnowledge",
    "ModeKnowledge",
    "get_command_knowledge_store",
    # Command Learner with DSPy/MAB
    "COMMAND_LEARNING_QUEUE",
    "CommandPattern",
    "CommandLearner",
    "CommandSelector",
    "get_learning_queue",
    "consolidate_learned_commands",
    # Universal Knowledge Injection
    "PhaseTracker",
    "WorkflowPhase",
    "get_phase_tracker",
    "should_inject",
    "inject_knowledge",
    "record_injection_success",
    "get_command_knowledge_store",
]


_EXPORT_MODULES = {
    "Pattern": ".schema",
    "Antipattern": ".schema",
    "Gap": ".schema",
    "GapStatus": ".schema",
    "GapPriority": ".schema",
    "Insight": ".schema",
    "InsightCategory": ".schema",
    "ToolRelationship": ".schema",
    "RelationshipType": ".schema",
    "Verification": ".schema",
    "SessionHandoff": ".schema",
    "CultivationStats": ".schema",
    "KnowledgeGraphV2Data": ".schema",
    "ErrorCategory": ".schema",
    "KnowledgeGraphV2": ".graph",
    "Investigator": ".investigator",
    "InvestigationResult": ".investigator",
    "Diagnosis": ".investigator",
    "VisualVerifier": ".verifier",
    "ViewportState": ".verifier",
    "StateDiff": ".verifier",
    "LearningSession": ".session",
    "SessionPlan": ".session",
    "SessionProgress": ".session",
    "AutonomousLearningAgent": ".agent",
    "get_prompt": ".prompts",
    "CULTIVATOR_SYSTEM_PROMPT": ".prompts",
    "ProgressReporter": ".monitor",
    "AgentStatus": ".monitor",
    "setup_logging": ".monitor",
    "read_agent_status": ".monitor",
    "print_agent_status": ".monitor",
    "tail_log": ".monitor",
    "configure_dspy": ".dspy_config",
    "get_lm": ".dspy_config",
    "is_configured": ".dspy_config",
    "TemporaryLMSettings": ".dspy_config",
    "OrientSession": ".dspy_signatures",
    "PlanInvestigation": ".dspy_signatures",
    "DiagnoseFailure": ".dspy_signatures",
    "GenerateHypotheses": ".dspy_signatures",
    "SynthesizeInsight": ".dspy_signatures",
    "ConsolidatePattern": ".dspy_signatures",
    "SemanticFeedback": ".dspy_signatures",
    "DetectWorkflow": ".dspy_signatures",
    "ExecuteWithReasoning": ".dspy_signatures",
    "VerifyResult": ".dspy_signatures",
    "SessionOrienter": ".dspy_modules",
    "InvestigationPlanner": ".dspy_modules",
    "FailureDiagnoser": ".dspy_modules",
    "HypothesisGenerator": ".dspy_modules",
    "InsightSynthesizer": ".dspy_modules",
    "PatternConsolidator": ".dspy_modules",
    "FeedbackComputer": ".dspy_modules",
    "WorkflowDetector": ".dspy_modules",
    "ReasoningExecutor": ".dspy_modules",
    "ResultVerifier": ".dspy_modules",
    "ActionSelector": ".dspy_modules",
    "InvestigationOrchestrator": ".dspy_modules",
    "create_all_modules": ".dspy_modules",
    "HypothesisSelector": ".mab_selectors",
    "FixSelector": ".mab_selectors",
    "PrioritySelector": ".mab_selectors",
    "SelectionContext": ".mab_selectors",
    "create_all_selectors": ".mab_selectors",
    "HybridInvestigator": ".hybrid_investigator",
    "HybridInvestigationResult": ".hybrid_investigator",
    "IdentifyContexts": ".consolidator",
    "ClassifyPattern": ".consolidator",
    "ConsolidateContext": ".consolidator",
    "ExtractErrorCategories": ".consolidator",
    "GenerateQuickSummary": ".consolidator",
    "ConsolidatedContext": ".consolidator",
    "ConsolidatedTool": ".consolidator",
    "ConsolidatedKnowledge": ".consolidator",
    "IntelligentConsolidator": ".consolidator",
    "consolidate_tool": ".consolidator",
    "consolidate_all_tools": ".consolidator",
    "consolidate_single_tool": ".consolidator",
    "extract_patterns_by_tool": ".consolidator",
    "DEFAULT_CONDENSED_PATH": ".consolidator",
    "DEFAULT_TOOL_DESCRIPTIONS": ".consolidator",
    "QueryFeatures": ".retrieval_mab",
    "QueryFeatureEncoder": ".retrieval_mab",
    "RetrievalOutcome": ".retrieval_mab",
    "KnowledgeRetrievalMAB": ".retrieval_mab",
    "load_retrieval_mab": ".retrieval_mab",
    "initialize_retrieval_mab_from_condensed": ".retrieval_mab",
    "DEFAULT_RETRIEVAL_MAB_PATH": ".retrieval_mab",
    "GHSparseIndex": ".gh_knowledge",
    "GHTieredKnowledge": ".gh_knowledge",
    "GHKnowledgeStore": ".gh_knowledge",
    "get_gh_knowledge_store": ".gh_knowledge",
    "gh_query_knowledge": ".gh_knowledge",
    "SugiyamaLayout": ".sugiyama",
    "SugiyamaNode": ".sugiyama",
    "SugiyamaEdge": ".sugiyama",
    "InputType": ".command_observer",
    "PromptType": ".command_observer",
    "DialogueStep": ".command_observer",
    "CommandPreconditions": ".command_observer",
    "CommandResult": ".command_observer",
    "CommandObservation": ".command_observer",
    "DialogueParser": ".command_observer",
    "ObservationStore": ".command_observer",
    "CommandObserver": ".command_observer",
    "DEFAULT_OBSERVATION_STORE_PATH": ".command_observer",
    "CommandKnowledgeStore": ".command_knowledge_store",
    "CommandKnowledge": ".command_knowledge_store",
    "ModeKnowledge": ".command_knowledge_store",
    "get_command_knowledge_store": ".command_knowledge_store",
    "COMMAND_LEARNING_QUEUE": ".command_learner",
    "CommandLearner": ".command_learner",
    "CommandSelector": ".command_learner",
    "get_learning_queue": ".command_learner",
    "consolidate_learned_commands": ".command_learner",
    "PhaseTracker": ".phase_tracker",
    "WorkflowPhase": ".phase_tracker",
    "get_phase_tracker": ".phase_tracker",
    "should_inject": ".knowledge_injector",
    "inject_knowledge": ".knowledge_injector",
    "record_injection_success": ".knowledge_injector",
}


def __getattr__(name: str) -> Any:
    if name == "CommandPattern":
        value = getattr(import_module(".command_knowledge_store", __name__), "CommandKnowledge")
        globals()[name] = value
        return value
    if name == "GH_TIER_TOKEN_ESTIMATES":
        value = getattr(import_module(".gh_knowledge", __name__), "TIER_TOKEN_ESTIMATES")
        globals()[name] = value
        return value
    if name == "SugiyamaNode":
        value = getattr(import_module(".sugiyama", __name__), "Node")
        globals()[name] = value
        return value
    if name == "SugiyamaEdge":
        value = getattr(import_module(".sugiyama", __name__), "Edge")
        globals()[name] = value
        return value

    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    try:
        value = getattr(import_module(module_name, __name__), name)
    except ImportError:
        if name == "CommandSelector":
            value = None
        else:
            raise
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted((*globals(), *__all__))

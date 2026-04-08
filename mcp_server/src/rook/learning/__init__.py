"""
Learning module for Rook Autonomous Learning Agent.

This module contains the infrastructure for autonomous knowledge cultivation:
- Knowledge Graph V2 with enhanced schema (gaps, insights, relationships, verifications)
- Investigation Engine for problem-solving
- Visual Verification System
- Session Management for handoffs between instances
- DSPy-based declarative reasoning (Strategic Layer)
- MABWiser-based selection (Tactical Layer)
- Hybrid Investigator combining DSPy + MAB

The learning module wraps around the existing MAB-based knowledge system,
adding investigation coordination and session management on top.
"""

from .schema import (
    Pattern,
    Antipattern,
    Gap,
    GapStatus,
    GapPriority,
    Insight,
    InsightCategory,
    ToolRelationship,
    RelationshipType,
    Verification,
    SessionHandoff,
    CultivationStats,
    KnowledgeGraphV2Data,
    ErrorCategory,
)
from .graph import KnowledgeGraphV2
from .investigator import Investigator, InvestigationResult, Diagnosis
from .verifier import VisualVerifier, ViewportState, StateDiff
from .session import LearningSession, SessionPlan, SessionProgress
from .agent import AutonomousLearningAgent
from .prompts import get_prompt, CULTIVATOR_SYSTEM_PROMPT
from .monitor import (
    ProgressReporter,
    AgentStatus,
    setup_logging,
    read_agent_status,
    print_agent_status,
    tail_log,
)

# DSPy + MABWiser Integration (Phase 1-3 of DSPY_MABWISER_IMPLEMENTATION_PLAN)
from .dspy_config import configure_dspy, get_lm, is_configured, TemporaryLMSettings
from .dspy_signatures import (
    OrientSession,
    PlanInvestigation,
    DiagnoseFailure,
    GenerateHypotheses,
    SynthesizeInsight,
    ConsolidatePattern,
    SemanticFeedback,
    DetectWorkflow,
    ExecuteWithReasoning,
    VerifyResult,
)
from .dspy_modules import (
    SessionOrienter,
    InvestigationPlanner,
    FailureDiagnoser,
    HypothesisGenerator,
    InsightSynthesizer,
    PatternConsolidator,
    FeedbackComputer,
    WorkflowDetector,
    ReasoningExecutor,
    ResultVerifier,
    ActionSelector,
    InvestigationOrchestrator,
    create_all_modules,
)
from .mab_selectors import (
    HypothesisSelector,
    FixSelector,
    PrioritySelector,
    SelectionContext,
    create_all_selectors,
)
from .hybrid_investigator import HybridInvestigator, HybridInvestigationResult

# Knowledge Consolidation Layer (Phase 1)
from .consolidator import (
    # DSPy Signatures
    IdentifyContexts,
    ClassifyPattern,
    ConsolidateContext,
    ExtractErrorCategories,
    GenerateQuickSummary,
    # Data Classes
    ConsolidatedContext,
    ConsolidatedTool,
    ConsolidatedKnowledge,
    # Module
    IntelligentConsolidator,
    # Convenience Functions
    consolidate_tool,
    consolidate_all_tools,
    consolidate_single_tool,
    extract_patterns_by_tool,
    DEFAULT_CONDENSED_PATH,
    DEFAULT_TOOL_DESCRIPTIONS,
)
from .retrieval_mab import (
    QueryFeatures,
    QueryFeatureEncoder,
    RetrievalOutcome,
    KnowledgeRetrievalMAB,
    load_retrieval_mab,
    initialize_retrieval_mab_from_condensed,
    DEFAULT_RETRIEVAL_MAB_PATH,
)

# Grasshopper Knowledge System
from .gh_knowledge import (
    GHSparseIndex,
    GHTieredKnowledge,
    GHKnowledgeStore,
    get_gh_knowledge_store,
    gh_query_knowledge,
    TIER_TOKEN_ESTIMATES as GH_TIER_TOKEN_ESTIMATES,
)
from .sugiyama import SugiyamaLayout, Node as SugiyamaNode, Edge as SugiyamaEdge

# Command Learning System (Rhino Commands)
from .command_observer import (
    InputType,
    PromptType,
    DialogueStep,
    CommandPreconditions,
    CommandResult,
    CommandObservation,
    DialogueParser,
    ObservationStore,
    CommandObserver,
    DEFAULT_OBSERVATION_STORE_PATH,
)
from .command_knowledge_store import (
    CommandKnowledgeStore,
    CommandKnowledge,
    ModeKnowledge,
    get_command_knowledge_store,
)
from .command_learner import (
    COMMAND_LEARNING_QUEUE,
    CommandLearner,
    get_learning_queue,
    consolidate_learned_commands,
)

# Universal Knowledge Injection
from .phase_tracker import PhaseTracker, WorkflowPhase, get_phase_tracker
from .knowledge_injector import should_inject, inject_knowledge, record_injection_success

# Backward compatibility alias
CommandPattern = CommandKnowledge

# Conditionally import MAB/DSPy components
try:
    from .command_learner import CommandSelector
except ImportError:
    CommandSelector = None

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
    # - DSPy Signatures
    "IdentifyContexts",
    "ClassifyPattern",
    "ConsolidateContext",
    "ExtractErrorCategories",
    "GenerateQuickSummary",
    # - Data Classes
    "ConsolidatedContext",
    "ConsolidatedTool",
    "ConsolidatedKnowledge",
    # - Module
    "IntelligentConsolidator",
    # - Convenience Functions
    "consolidate_tool",
    "consolidate_all_tools",
    "consolidate_single_tool",
    "extract_patterns_by_tool",
    "DEFAULT_CONDENSED_PATH",
    "DEFAULT_TOOL_DESCRIPTIONS",
    # - Retrieval MAB
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
    # Command Knowledge Store (unified meta-learning module)
    "CommandKnowledgeStore",
    "CommandKnowledge",
    "ModeKnowledge",
    "get_command_knowledge_store",
    # Command Learner with DSPy/MAB
    "COMMAND_LEARNING_QUEUE",
    "CommandPattern",  # Alias for CommandKnowledge (backward compat)
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

"""
Financial Pipeline Harness
File: src/pipeline/harness.py

Assembles, connects, and compiles the multi-agent workflow using LangGraph StateGraph.
"""

from typing import Callable, Optional
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.pipeline.agents.dispatch_agent import dispatch_agent_node
from src.pipeline.agents.reader_agent import reader_agent_node
from src.pipeline.agents.reconciliation_agent import reconciliation_agent_node
from src.pipeline.agents.reporting_agent import reporting_agent_node
from src.pipeline.agents.storage_agent import storage_agent_node
from src.pipeline.schemas import AgentState


class FinancialPipelineHarness:
    """
    Orchestration harness that connects the 5 individual agents into an executable LangGraph pipeline:
      START -> Reader -> Storage -> Reconciliation -> Reporting -> Dispatch -> END
    """

    def __init__(
        self,
        reader_node: Optional[Callable[[AgentState], dict]] = None,
        storage_node: Optional[Callable[[AgentState], dict]] = None,
        reconciliation_node: Optional[Callable[[AgentState], dict]] = None,
        reporting_node: Optional[Callable[[AgentState], dict]] = None,
        dispatch_node: Optional[Callable[[AgentState], dict]] = None,
    ):
        self.reader_node = reader_node or reader_agent_node
        self.storage_node = storage_node or storage_agent_node
        self.reconciliation_node = reconciliation_node or reconciliation_agent_node
        self.reporting_node = reporting_node or reporting_agent_node
        self.dispatch_node = dispatch_node or dispatch_agent_node

    def build_core_pipeline(self) -> CompiledStateGraph:
        """Assembles the 3-agent core pipeline: Reader -> Storage -> Reconciliation -> END."""
        workflow = StateGraph(AgentState)

        workflow.add_node("reader_agent", self.reader_node)
        workflow.add_node("storage_agent", self.storage_node)
        workflow.add_node("reconciliation_agent", self.reconciliation_node)

        workflow.add_edge(START, "reader_agent")
        workflow.add_edge("reader_agent", "storage_agent")
        workflow.add_edge("storage_agent", "reconciliation_agent")
        workflow.add_edge("reconciliation_agent", END)

        return workflow.compile()

    def build_full_pipeline(self) -> CompiledStateGraph:
        """Assembles the full 5-agent pipeline: Reader -> Storage -> Recon -> Reporting -> Dispatch -> END."""
        workflow = StateGraph(AgentState)

        workflow.add_node("reader_agent", self.reader_node)
        workflow.add_node("storage_agent", self.storage_node)
        workflow.add_node("reconciliation_agent", self.reconciliation_node)
        workflow.add_node("reporting_agent", self.reporting_node)
        workflow.add_node("dispatch_agent", self.dispatch_node)

        workflow.add_edge(START, "reader_agent")
        workflow.add_edge("reader_agent", "storage_agent")
        workflow.add_edge("storage_agent", "reconciliation_agent")
        workflow.add_edge("reconciliation_agent", "reporting_agent")
        workflow.add_edge("reporting_agent", "dispatch_agent")
        workflow.add_edge("dispatch_agent", END)

        return workflow.compile()


def build_financial_pipeline() -> CompiledStateGraph:
    """Convenience factory returning a compiled 5-agent pipeline."""
    harness = FinancialPipelineHarness()
    return harness.build_full_pipeline()


def build_core_financial_pipeline() -> CompiledStateGraph:
    """Convenience factory returning a compiled 3-agent pipeline."""
    harness = FinancialPipelineHarness()
    return harness.build_core_pipeline()

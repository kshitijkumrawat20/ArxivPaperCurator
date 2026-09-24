import logging
import time
from typing import Dict, List, Optional

from gradio import workflow
from langchain_core.messages import HumanMessage
from langfuse.langchain import CallbackHandler
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from src.services.embeddings.jina_client import JinaEmbeddingsClient
from src.services.langfuse.client import LangfuseTracer
from src.services.ollama.client import OllamaClient
from src.services.opensearch.client import OpenSearchClient

from .config import GraphConfig
from .context import Context
from .nodes import (
    ainvoke_generate_answer_step,
    ainvoke_grade_documents_step,
    ainvoke_guardrail_step,
    ainvoke_out_of_scope_step,
    ainvoke_retrieve_step,
    ainvoke_rewrite_query_step,
    continue_after_guardrail,
)
from .state import AgentState
from .tools import create_retriever_tool

logger = logging.getLogger(__name__)

class AgenticRAGService: 
    """Agentic RAG service 

    This implementation uses:
    - context_schema for dependency injection
    - Runtime[Context] for type-safe access in nodes
    - Direct client invocation (no pre-built runnables)
    - Lightweight nodes as pure functions
    """

    def __init__(
        self, 
        opensearch_client: OpenSearchClient, 
        ollama_client: OllamaClient, 
        embedding_client: JinaEmbeddingsClient, 
        langfuse_tracer: Optional[LangfuseTracer] = None, 
        graph_config: Optional[GraphConfig] = None,
    ):

        """Initialize agentic RAG service.

        :param opensearch_client: Client for document search
        :param ollama_client: Client for LLM generation
        :param embeddings_client: Client for embeddings
        :param langfuse_tracer: Optional Langfuse tracer
        :param graph_config: Configuration for graph execution
        """
        self.ollama = ollama_client
        self.embeddings = embedding_client
        self.langfuse_tracer = langfuse_tracer
        self.graph_config = graph_config or GraphConfig()
        self.opensearch = opensearch_client 

        logger.info("Initializing AgenticRAGService with configuration:")
        logger.info(f"  Model: {self.graph_config.model}")
        logger.info(f"  Top-k: {self.graph_config.top_k}")
        logger.info(f"  Hybrid search: {self.graph_config.use_hybrid}")
        logger.info(f"  Max retrieval attempts: {self.graph_config.max_retrieval_attempts}")
        logger.info(f"  Guardrail threshold: {self.graph_config.guardrail_threshold}")

       # Build graph once (no runnables needed!)
        self.graph = self._build_graph()
        logger.info("✓ AgenticRAGService initialized successfully")

    def _build_graph(self): 
        """Build and compile the LangGraph workflow.

        Uses context_schema for type-safe dependency injection.
        Nodes are lightweight functions that receive Runtime[Context].

        :returns: Compiled graph ready for invocation
        """

        logger.info("Building langgraph workflow with context_schema")

        # create workflow with AgentState and Context schema 
        workflow = StateGraph(AgentState, context_schema = Context)
        # Create tools( these still sneed to be created upfront for ToolNode)

        retriever_tool = create_retriever_tool(
            opensearch_client = self.opensearch, 
            embeddings_client = self.embeddings, 
            top_k = self.graph_config.top_k, 
            use_hybrid = self.graph_config.use_hybrid,
        )
      
        tools = [retriever_tool]
      
        # Add Nodes (just function reference - no closures needed ! )

        logger.info('Adding nodes to workflow graph')
        workflow.add_node("guardrail",ainvoke_guardrail_step)
        workflow.add_node("out_of_scope", ainvoke_out_of_scope_step)
        workflow.add_node("retrieve", ainvoke_retrieve_step)
        workflow.add_node("tool_retrieve", ToolNode(tools))
        workflow.add_node("grade_documents", ainvoke_grade_documents_step)
        workflow.add_node("rewrite_query", ainvoke_rewrite_query_step)
        workflow.add_node("generate_answer", ainvoke_generate_answer_step)

        logger.info("Configuring graph edges and routing Logic")

        workflow.add_edge(START, "guardrail")
        workflow.add_conditional_edge(
            "guardrail", 
            continue_after_guardrail{
                "continue": "retrieve"
            }
        )

        # Out of scope then end 
        workflow.add_edge("out_of_scope", END)

        # Retrieve node creates tool call 
        workflow.add_conditional_edges(
            "retrieve",
            tools_condition(
                "tools": "tool_preview",
                END: END,
            ),
        )
        
        # After tool retrieval -> grade document s 
        workflow.add_conditional_edges(
            "grade_documents", 
            lambda state: state.get("routing_decision", "generate_answer"), # 
            {
                "generate_answer": "generate_answer", 
                "rewrite_query": "rewrite_query",
            }
        )

        # After rewriting -> try retrieve again 
        workflow.add_edge("rewrite_query", "retrieve")

        # After answer generation - don e
        workflow.add_edge("generate_answer", END)

        # Compile the graph 
        logger.info("Compiling workflow graph")
        compiled_graph = workflow.compile()
        logger.info("✓ Workflow graph compiled successfully")
        return compiled_graph

    async def ask(
        self,
        query: str, 
        user_id : str = "api_user",
        model: Optional[str] = None,
    ) -> dict: 
        """Ask a question using agentic RAG.

        :param query: User question
        :param user_id: User identifier for tracing
        :param model: Optional model override
        :returns: Dictionary with answer, sources, reasoning steps, and metadata
        :raises ValueError: If query is empty
        """
        model_to_use = model or self.graph_config.model

        logger.info("=" * 80)
        logger.info("Starting Agentic RAG Request")
        logger.info(f"Query: {query[:100]}...")
        logger.info(f"User ID: {user_id}")
        logger.info(f"Model: {model_to_use}")
        logger.info("=" * 80)

        # validation input 
        if not query or len(query.strip()) == 0: 
            logger.error("Empty query recieved")
            raise ValueError("Query cannot be empty")

        # create trace if langfuse is enabled v3 sdk 
        trace = None 
        if self.langfuse_tracer and self.langfuse_tracer.client: 
            logger.info("Creating langfuse trace (v3 SDK)")
            metadata = { 
                "env": self.graph_config.settings.environment, 
                "service": "agentic_rag", 
                "top_k": self.graph_config.top_k, 
                "use_hybrid": self.graph_config.use_hybrid, 
                "model": model_to_use,

            }

            # V3 SDK use start as current span - will be used with 'with; statement
            trace = self.langfuse_tracer.client.start_as_current_span(
                name = "agentic_rag_request",
            )

        # Use proper context manager pattern 
        async def _executive_with_trace():
            """
            Execute the workflow with or without tracing context.
            """
            if trace is not None: 
                with trace as trace_obj: 
                    trace_obj.update(
                        input = {"query": query}, 
                        metadata = metadata, 
                        user_id = user_id, 
                        session_id = f"session_{user_id}",
                    )
                    logger.debug(f"Trace created : {trace_obj}")
                    return await self._run_workflow(query, model_to_use, user_id, None)

            else: 
                return await self._run_workflow(query, model_to_use, user_id, None)

        try: 
            return await _executive_with_trace()
        except Exception as e:
            logger.error(f"Error during workflow execution: {e}")
            logger.exception("Full Traceback:")
            raise
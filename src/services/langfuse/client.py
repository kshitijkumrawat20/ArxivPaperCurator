import logging
from contextlib import contextmanager
from typing import Any, Dict, Optional

from langfuse import Langfuse
from src.config import Settings

logger = logging.getLogger(__name__)


class LangfuseTracer:
    """Wrapper for Langfuse v3 tracing client with CallBackHandler support."""

    def __init__(self, settings: Settings):
        self.settings = settings.langfuse
        self.client: Optional[Langfuse] = None

        if self.settings.enabled and self.settings.public_key and self.settings.secret_key:
            try:
                # Initialize the langfuse v3 singleton client 
                # configuratiion moved to client initialization
                self.client = Langfuse(
                    public_key=self.settings.public_key,
                    secret_key=self.settings.secret_key,
                    host=self.settings.host,
                    flush_at=self.settings.flush_at,
                    flush_interval=self.settings.flush_interval,
                    debug=self.settings.debug,
                )
                logger.info(f"Langfuse v3 tracing initialized (host: {self.settings.host})")
            except Exception as e:
                logger.error(f"Failed to initialize Langfuse: {e}")
                self.client = None
        else:
            logger.info("Langfuse v3 tracing disabled or missing credentials")

    # @contextmanager
    def get_callback_handler(
        self,
        trace_name: Optional[str]=None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[list[str]] = None,
    ):
        """
        Get a CallbackHandler for langchain / langgraph integration.
        This is the v3 recommended approach - all LLM calls are automatically traced. 
        Args:
            trace_name: Optional name for the trace
            user_id: Optional user identifier
            session_id: Optional session identifier
            metadata: Additional metadata to attach to the trace
            tags: Optional list of tags for the trace

        returns:
            CallbackHandler instance if Langfuse is enabled, None otherwise
        """
        if not self.client:
            return None

        try:
            # import v3 callbackhandler 
            from langfuse.langchain import CallbackHandler
            # create handler with trace metadata 
            # Note: flush settings are now on the client not the handler 
            handler = CallbackHandler(
                trace_name = trace_name, 
                user_id = user_id,
                session_id = session_id,
                metadata = metadata, 
                tags = tags,
            )
            return handler
        except Exception as e:
            logger.error(f"Error creating callbackHandler: {e}")
            return None
    @contextmanager
    def trace_langggraph_agent(
        self,
        name: str,
        user_id: Optional[str] = None, 
        session_id: Optional[str] = None, 
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[list[str]] = None,
    ):
        """
        Context manager to wrap langgraph agent execution with a top - level trace span. 
        
        This follows the langfuse langgraph cookbook pattern of wrapping the entire graph invocation in a span for better observability.

        Usage: 
            with tracer.trace_langgraph_agent(name = "agentic_rag", user_id = "user123", session_id = "session456") as trace:
                result = graph.invoke(input, config = {"callbacks": [handler]}) trace_ctx.update(output result)


        Args:
            name: Name for the trace span (e.g., "agentic_rag_graph") 
            user_id : Optional user identifier for the trace
            session_id: Optional session identifier for the trace
            metadata: Additional metadata
            tags: Optional list of tags for the trace


        Yields:
            Tuple of (trace_context, callback_handler) for graph execution
        """
        if not self.client:

            yield None, None
            return
        # create callback handler for langgraph integration 
        # the handler will automatically create traces 
        handler = self.get_callback_handler(
            trace_name = name, 
            user_id = user_id, 
            session_id = session_id, 
            metadata = metadata, 
            tags = tags,
        )
        yield (None, handler)

    def get_trace_id(
        self,
        trace = None,
    ) -> Optional[str]: 
        """
        Get the current trace ID from Langfuse context.

        In Langfuse v3, the CallbackHandler manages traces automatically.
        We can get the current trace ID using get_current_trace_id().

        Args:
            trace: Deprecated, not user in v3 
            Trace Id string or None if trace is disablecd 

        """
        if not self.client:
            return None

        try:
            trace_id = self.client.get_current_trace_id()
            return trace_id
        except Exception as e:
            logger.error(f"Error creating generation {name}: {e}")
            return None

    def score_trace(
        self,
        trace,
        name: str,
        value: float,
        comment: Optional[str] = None,
    ):
        """
        Add a score to a trace.

        Args:
            trace: Trace object
            name: Score name (e.g., "relevance", "accuracy")
            value: Score value
            comment: Optional comment
        """
        if not trace or not self.client:
            return

        try:
            # Create a score using v2 API
            self.client.score(
                trace_id=trace.trace_id,
                name=name,
                value=value,
                comment=comment,
            )
        except Exception as e:
            logger.error(f"Error scoring trace: {e}")

    def update_span(
        self,
        span,
        output: Optional[Any] = None,
        metadata: Optional[Dict[str, Any]] = None,
        level: Optional[str] = None,
        status_message: Optional[str] = None,
    ):
        """
        Update a span with output or additional metadata.

        Args:
            span: Span object to update
            output: Output data
            metadata: Additional metadata
            level: Log level (DEBUG, INFO, WARNING, ERROR)
            status_message: Status message
        """
        if not span:
            return

        try:
            # For v2 API, we can update spans with end_time and output
            if output is not None:
                # Update the span with output data
                span.update(output=output)
            if metadata:
                span.update(metadata=metadata)
            if level:
                span.update(level=level)
            if status_message:
                span.update(status_message=status_message)
        except Exception as e:
            logger.error(f"Error updating span: {e}")

    def end_span(self, span, output: Optional[Any] = None, metadata: Optional[Dict[str, Any]] = None):
        """
        End a span with optional final output and metadata.

        Args:
            span: Span object to end
            output: Final output data
            metadata: Final metadata
        """
        if not span:
            return

        try:
            # Update with final data if provided
            if output is not None or metadata is not None:
                self.update_span(span, output=output, metadata=metadata)

            # End the span to capture proper timing
            span.end()
        except Exception as e:
            logger.error(f"Error ending span: {e}")

    def flush(self):
        """Flush any pending traces."""
        if self.client:
            try:
                self.client.flush()
            except Exception as e:
                logger.error(f"Error flushing Langfuse: {e}")

    def shutdown(self):
        """Shutdown the Langfuse client."""
        if self.client:
            try:
                self.client.flush()
                self.client.shutdown()
            except Exception as e:
                logger.error(f"Error shutting down Langfuse: {e}")

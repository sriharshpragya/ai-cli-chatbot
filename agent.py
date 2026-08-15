# ============================================
# AI Agent — Async Agent Class
# Uses existing llm_client for full resilience stack
# ============================================
import json
import time
from typing import Callable, Optional
from llm_client import create_chat_completion
from logging_config import get_logger
from metrics import track_chat_request

logger = get_logger(__name__)


class Agent:
    """
    Reusable async AI agent with tool-use capabilities.
    
    Uses llm_client.create_chat_completion for full resilience:
    - Multi-provider fallback (OpenRouter → Groq)
    - Circuit breakers per provider
    - Retry logic with backoff
    - Metrics tracking
    """
    
    def __init__(
        self,
        model: str = "openai/gpt-4o-mini",
        system_prompt: Optional[str] = None,
        max_iterations: int = 10,
        max_tokens: int = 1000,
    ):
        """
        Initialize the agent.
        
        Args:
            model: Model identifier (respects OpenRouter format)
            system_prompt: Optional system instructions
            max_iterations: Safety limit for tool call loops
            max_tokens: Max tokens per LLM call
        """
        self.model = model
        self.max_iterations = max_iterations
        self.max_tokens = max_tokens
        
        # Tools registry: name -> {"schema": schema, "function": func}
        self.tools_registry: dict[str, dict] = {}
        
        # Conversation memory
        self.conversation: list[dict] = []
        
        # Set system prompt if provided
        if system_prompt:
            self.conversation.append({
                "role": "system",
                "content": system_prompt,
            })
        
        logger.info(
            "agent_initialized",
            model=model,
            has_system_prompt=bool(system_prompt),
            max_iterations=max_iterations,
        )
    
    def register_tool(self, schema: dict, function: Callable):
        """
        Register a tool with the agent.
        
        Args:
            schema: OpenAI tool schema dict
            function: The actual Python function to call
        """
        tool_name = schema["function"]["name"]
        self.tools_registry[tool_name] = {
            "schema": schema,
            "function": function,
        }
        logger.info("tool_registered", tool_name=tool_name)
    
    def get_tool_schemas(self) -> list[dict]:
        """Get all registered tool schemas in OpenAI format."""
        return [tool["schema"] for tool in self.tools_registry.values()]
    
    def get_tool_names(self) -> list[str]:
        """Get list of all registered tool names."""
        return list(self.tools_registry.keys())
    
    def execute_tool(self, tool_name: str, arguments: dict) -> str:
        """
        Execute a tool safely and return JSON string result.
        
        Args:
            tool_name: Name of the tool
            arguments: Arguments to pass to the function
        
        Returns:
            JSON string (success or error)
        """
        if tool_name not in self.tools_registry:
            error_msg = f"Unknown tool: {tool_name}. Available: {list(self.tools_registry.keys())}"
            logger.warning("unknown_tool_called", tool_name=tool_name)
            return json.dumps({"error": error_msg})
        
        function = self.tools_registry[tool_name]["function"]
        start_time = time.time()
        
        try:
            result = function(**arguments)
            duration_ms = round((time.time() - start_time) * 1000, 2)
            
            logger.info(
                "tool_executed_successfully",
                tool_name=tool_name,
                arguments=arguments,
                duration_ms=duration_ms,
            )
            
            if isinstance(result, str):
                return result
            return json.dumps(result)
        
        except Exception as e:
            duration_ms = round((time.time() - start_time) * 1000, 2)
            
            logger.error(
                "tool_execution_failed",
                tool_name=tool_name,
                arguments=arguments,
                duration_ms=duration_ms,
                error_type=type(e).__name__,
                error_message=str(e),
            )
            
            return json.dumps({
                "error": f"Tool execution failed: {type(e).__name__}",
                "message": str(e),
            })
    
    async def run(self, user_message: str) -> dict:
        """
        Run the agent with a user message.
        
        Args:
            user_message: The user's input
        
        Returns:
            Dict with response, tools_used, iterations, provider info
        """
        self.conversation.append({
            "role": "user",
            "content": user_message,
        })
        
        logger.info("agent_run_started", user_message=user_message[:100])
        
        tools_used = []
        total_tokens = 0
        provider_used = None
        model_used = None
        start_time = time.time()
        
        # Track chat request for metrics
        track_chat_request(mode="agent")
        
        for iteration in range(self.max_iterations):
            logger.info(
                "agent_iteration",
                iteration=iteration + 1,
                conversation_length=len(self.conversation),
            )
            
            # Call LLM using the resilient client
            try:
                response, provider, model = await create_chat_completion(
                    model=self.model,
                    messages=self.conversation,
                    tools=self.get_tool_schemas() if self.tools_registry else None,
                    tool_choice="auto" if self.tools_registry else None,
                    max_tokens=self.max_tokens,
                )
                provider_used = provider
                model_used = model
                
                # Track tokens
                if response.usage:
                    total_tokens += response.usage.total_tokens
                
            except Exception as e:
                logger.error(
                    "agent_llm_call_failed",
                    iteration=iteration + 1,
                    error_type=type(e).__name__,
                    error_message=str(e),
                )
                return {
                    "response": f"Sorry, I encountered an error: {str(e)}",
                    "error": type(e).__name__,
                    "tools_used": tools_used,
                    "iterations": iteration + 1,
                    "total_tokens": total_tokens,
                    "duration_ms": round((time.time() - start_time) * 1000, 2),
                }
            
            message = response.choices[0].message
            
            # Add assistant response to conversation
            assistant_msg = {
                "role": "assistant",
                "content": message.content,
            }
            
            if message.tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        }
                    }
                    for tc in message.tool_calls
                ]
            
            self.conversation.append(assistant_msg)
            
            # If no tool calls, we're done
            if not message.tool_calls:
                logger.info(
                    "agent_run_completed",
                    iterations_used=iteration + 1,
                    tools_used=tools_used,
                    total_tokens=total_tokens,
                    provider=provider_used,
                )
                
                return {
                    "response": message.content,
                    "tools_used": tools_used,
                    "iterations": iteration + 1,
                    "total_tokens": total_tokens,
                    "provider_used": provider_used,
                    "model_used": model_used,
                    "duration_ms": round((time.time() - start_time) * 1000, 2),
                }
            
            # Execute tool calls
            logger.info(
                "tool_calls_requested",
                iteration=iteration + 1,
                tool_count=len(message.tool_calls),
            )
            
            for tool_call in message.tool_calls:
                tool_name = tool_call.function.name
                tools_used.append(tool_name)
                
                try:
                    arguments = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError as e:
                    logger.error(
                        "invalid_tool_arguments_json",
                        tool_name=tool_name,
                        error=str(e),
                    )
                    result = json.dumps({
                        "error": "Invalid JSON in tool arguments",
                        "detail": str(e),
                    })
                else:
                    result = self.execute_tool(tool_name, arguments)
                
                self.conversation.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                })
        
        # Hit max iterations
        logger.error(
            "agent_max_iterations_exceeded",
            max_iterations=self.max_iterations,
        )
        return {
            "response": f"I've hit my maximum reasoning steps ({self.max_iterations}). Please try a simpler query.",
            "error": "max_iterations_exceeded",
            "tools_used": tools_used,
            "iterations": self.max_iterations,
            "total_tokens": total_tokens,
            "duration_ms": round((time.time() - start_time) * 1000, 2),
        }
    
    def reset_conversation(self, keep_system_prompt: bool = True):
        """Reset conversation, optionally keeping system prompt."""
        if keep_system_prompt and self.conversation and self.conversation[0]["role"] == "system":
            self.conversation = [self.conversation[0]]
        else:
            self.conversation = []
        
        logger.info("conversation_reset")
    
    def get_conversation_history(self) -> list[dict]:
        """Get conversation history (copy)."""
        return self.conversation.copy()
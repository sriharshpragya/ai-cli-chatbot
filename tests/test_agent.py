"""
Tests for the AI Agent.

Unit tests: Fast, no external calls
Integration tests: Real LLM calls (marked with @pytest.mark.integration)

Run unit tests only:
    pytest tests/test_agent.py -m "not integration" -v

Run integration tests:
    pytest tests/test_agent.py -m "integration" -v
"""
import pytest
import json


# ============================================
# UNIT TESTS - Structural (no LLM calls)
# ============================================

class TestAgentInitialization:
    """Test agent can be created and configured."""
    
    def test_agent_can_be_imported(self):
        """Basic import test."""
        from agent import Agent
        assert Agent is not None
    
    def test_agent_initialization_defaults(self):
        """Agent creates with sensible defaults."""
        from agent import Agent
        
        agent = Agent()
        
        assert agent.model == "openai/gpt-4o-mini"
        assert agent.max_iterations == 10
        assert agent.max_tokens == 1000
        assert len(agent.tools_registry) == 0
        assert len(agent.conversation) == 0
    
    def test_agent_with_system_prompt(self):
        """Agent stores system prompt correctly."""
        from agent import Agent
        
        prompt = "You are a helpful assistant."
        agent = Agent(system_prompt=prompt)
        
        assert len(agent.conversation) == 1
        assert agent.conversation[0]["role"] == "system"
        assert agent.conversation[0]["content"] == prompt
    
    def test_agent_custom_config(self):
        """Agent accepts custom configuration."""
        from agent import Agent
        
        agent = Agent(
            model="custom-model",
            max_iterations=5,
            max_tokens=500,
        )
        
        assert agent.model == "custom-model"
        assert agent.max_iterations == 5
        assert agent.max_tokens == 500


class TestToolRegistration:
    """Test tool registration works."""
    
    def test_register_single_tool(self):
        """Can register a single tool."""
        from agent import Agent
        
        agent = Agent()
        
        schema = {
            "type": "function",
            "function": {
                "name": "test_tool",
                "description": "A test tool",
                "parameters": {"type": "object", "properties": {}},
            }
        }
        
        def test_function():
            return "test result"
        
        agent.register_tool(schema, test_function)
        
        assert "test_tool" in agent.tools_registry
        assert len(agent.tools_registry) == 1
    
    def test_get_tool_schemas(self):
        """Can retrieve registered tool schemas."""
        from agent import Agent
        
        agent = Agent()
        schema = {
            "type": "function",
            "function": {"name": "test", "description": "test", "parameters": {}}
        }
        agent.register_tool(schema, lambda: None)
        
        schemas = agent.get_tool_schemas()
        assert len(schemas) == 1
        assert schemas[0]["function"]["name"] == "test"
    
    def test_get_tool_names(self):
        """Can list registered tool names."""
        from agent import Agent
        
        agent = Agent()
        schema = {
            "type": "function",
            "function": {"name": "test_tool", "description": "test", "parameters": {}}
        }
        agent.register_tool(schema, lambda: None)
        
        names = agent.get_tool_names()
        assert "test_tool" in names


class TestAllToolsRegistration:
    """Test that all production tools can be registered."""
    
    def test_register_all_tools(self):
        """All tools register successfully."""
        from agent import Agent
        from tools import register_all_tools, get_all_tools
        
        agent = Agent()
        register_all_tools(agent)
        
        expected_count = len(get_all_tools())
        assert len(agent.tools_registry) == expected_count
        # At minimum: basic (5) + file/URL (2) = 7 tools
        assert expected_count >= 7
    
    def test_all_tools_have_valid_schemas(self):
        """Every registered tool has a valid OpenAI schema."""
        from agent import Agent
        from tools import register_all_tools
        
        agent = Agent()
        register_all_tools(agent)
        
        for tool_name, tool_data in agent.tools_registry.items():
            schema = tool_data["schema"]
            
            # Check schema structure
            assert schema["type"] == "function"
            assert "function" in schema
            assert schema["function"]["name"] == tool_name
            assert "description" in schema["function"]
            assert "parameters" in schema["function"]
    
    def test_all_tool_functions_are_callable(self):
        """Every registered tool has a callable function."""
        from agent import Agent
        from tools import register_all_tools
        
        agent = Agent()
        register_all_tools(agent)
        
        for tool_name, tool_data in agent.tools_registry.items():
            assert callable(tool_data["function"]), \
                f"Tool {tool_name} function is not callable"


class TestToolExecution:
    """Test tool execution and error handling."""
    
    def test_execute_registered_tool(self):
        """Can execute a registered tool."""
        from agent import Agent
        
        agent = Agent()
        
        schema = {
            "type": "function",
            "function": {"name": "adder", "description": "adds", "parameters": {}}
        }
        
        def adder(a, b):
            return {"result": a + b}
        
        agent.register_tool(schema, adder)
        
        result = agent.execute_tool("adder", {"a": 5, "b": 3})
        parsed = json.loads(result)
        
        assert parsed["result"] == 8
    
    def test_execute_unknown_tool(self):
        """Executing unknown tool returns error, doesn't crash."""
        from agent import Agent
        
        agent = Agent()
        result = agent.execute_tool("nonexistent", {})
        parsed = json.loads(result)
        
        assert "error" in parsed
    
    def test_tool_execution_handles_exceptions(self):
        """Tool exceptions are caught and returned as errors."""
        from agent import Agent
        
        agent = Agent()
        
        schema = {
            "type": "function",
            "function": {"name": "broken", "description": "broken", "parameters": {}}
        }
        
        def broken_tool():
            raise ValueError("Intentional error")
        
        agent.register_tool(schema, broken_tool)
        
        result = agent.execute_tool("broken", {})
        parsed = json.loads(result)
        
        assert "error" in parsed


class TestConversationManagement:
    """Test conversation state management."""
    
    def test_reset_conversation_keeps_system_prompt(self):
        """Reset preserves system prompt by default."""
        from agent import Agent
        
        agent = Agent(system_prompt="System prompt")
        agent.conversation.append({"role": "user", "content": "Hi"})
        
        agent.reset_conversation()
        
        assert len(agent.conversation) == 1
        assert agent.conversation[0]["role"] == "system"
    
    def test_reset_conversation_drops_system_prompt(self):
        """Reset can drop system prompt if requested."""
        from agent import Agent
        
        agent = Agent(system_prompt="System prompt")
        agent.reset_conversation(keep_system_prompt=False)
        
        assert len(agent.conversation) == 0
    
    def test_get_conversation_history_returns_copy(self):
        """History is returned as copy (immutable)."""
        from agent import Agent
        
        agent = Agent(system_prompt="System")
        history = agent.get_conversation_history()
        
        history.append({"role": "user", "content": "extra"})
        
        # Internal state unchanged
        assert len(agent.conversation) == 1


# ============================================
# INTEGRATION TESTS - Real LLM calls
# Only run when explicitly requested via -m "integration"
# ============================================

@pytest.mark.integration
async def test_agent_can_call_llm():
    """Integration: agent can make real LLM call."""
    from agent import Agent
    
    agent = Agent(
        system_prompt="You are a helpful assistant.",
        max_iterations=3,
    )
    
    result = await agent.run("Say the word 'hello' and nothing else.")
    
    assert "response" in result
    assert result["response"] is not None
    assert len(result["response"]) > 0
    assert "iterations" in result
    assert result["iterations"] >= 1


@pytest.mark.integration
async def test_agent_uses_tool():
    """Integration: agent uses a tool when appropriate."""
    from agent import Agent
    from tools import register_all_tools
    
    agent = Agent(max_iterations=5)
    register_all_tools(agent)
    
    result = await agent.run("What is 42 * 17? Use the calculator tool.")
    
    assert "response" in result
    assert "tools_used" in result
    assert "calculate" in result["tools_used"]
    # Response should contain the answer
    assert "714" in result["response"]
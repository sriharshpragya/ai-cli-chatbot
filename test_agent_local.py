"""
Quick local test for agent integration.
Verifies agent works with your existing llm_client.
"""
import asyncio
from agent import Agent
from tools import register_all_tools, get_available_tool_names


async def main():
    print("Available tools:", get_available_tool_names())
    print()
    
    # Create agent
    agent = Agent(
        model="openai/gpt-4o-mini",
        system_prompt=(
            "You are a helpful personal assistant with access to weather, "
            "calculator, time, GitHub, file reading, and URL fetching tools. "
            "Use tools when needed to help the user."
        ),
        max_iterations=5,
    )
    
    # Register all tools
    register_all_tools(agent)
    
    print(f"Agent has {len(agent.tools_registry)} tools registered")
    print()
    
    # Test queries
    queries = [
        "What is 42 * 17?",
        "What's the weather in Tokyo?",
    ]
    
    for query in queries:
        print("=" * 60)
        print(f"USER: {query}")
        print("=" * 60)
        
        agent.reset_conversation()
        
        result = await agent.run(query)
        
        print(f"\nRESPONSE: {result['response']}")
        print(f"Tools used: {result.get('tools_used', [])}")
        print(f"Iterations: {result.get('iterations')}")
        print(f"Provider: {result.get('provider_used')}")
        print(f"Model: {result.get('model_used')}")
        print(f"Duration: {result.get('duration_ms')}ms")
        print()


if __name__ == "__main__":
    asyncio.run(main())


# OUTPUT: 

# [CONFIG] Environment: development
# [CONFIG] Database: ENABLED
# [CONFIG] Redis: ENABLED
# [CONFIG] Model: openai/gpt-4o-mini
# [CONFIG] Agent: ENABLED
# [CONFIG] GitHub tools: DISABLED
# 08:32:21 [info     ] providers_initialized          count=2 providers=['openrouter', 'groq']
# 08:32:21 [info     ] github_tools_disabled          reason=GITHUB_TOKEN not set
# Available tools: ['get_weather', 'calculate', 'get_current_time', 'analyze_text', 'send_email', 'read_file', 'fetch_url']

# 08:32:21 [info     ] agent_initialized              has_system_prompt=True max_iterations=5 model=openai/gpt-4o-mini
# 08:32:21 [info     ] github_tools_disabled          reason=GITHUB_TOKEN not set
# 08:32:21 [info     ] tool_registered                tool_name=get_weather
# 08:32:21 [info     ] tool_registered                tool_name=calculate
# 08:32:21 [info     ] tool_registered                tool_name=get_current_time
# 08:32:21 [info     ] tool_registered                tool_name=analyze_text
# 08:32:21 [info     ] tool_registered                tool_name=send_email
# 08:32:21 [info     ] tool_registered                tool_name=read_file
# 08:32:21 [info     ] tool_registered                tool_name=fetch_url
# 08:32:21 [info     ] all_tools_registered           count=7
# Agent has 7 tools registered

# ============================================================
# USER: What is 42 * 17?
# ============================================================
# 08:32:21 [info     ] conversation_reset            
# 08:32:21 [info     ] agent_run_started              user_message=What is 42 * 17?
# 08:32:21 [info     ] agent_iteration                conversation_length=2 iteration=1
# 08:32:21 [info     ] provider_attempt               provider=openrouter
# 08:32:22 [info     ] provider_success               duration_ms=1177.38 model=openai/gpt-4o-mini provider=openrouter tokens=685
# 08:32:22 [info     ] tool_calls_requested           iteration=1 tool_count=1
# 08:32:22 [info     ] tool_executed_successfully     arguments={'operation': 'multiply', 'a': 42, 'b': 17} duration_ms=0.0 tool_name=calculate
# 08:32:22 [info     ] agent_iteration                conversation_length=4 iteration=2
# 08:32:22 [info     ] provider_attempt               provider=openrouter
# 08:32:23 [info     ] provider_success               duration_ms=905.53 model=openai/gpt-4o-mini provider=openrouter tokens=726
# 08:32:23 [info     ] agent_run_completed            iterations_used=2 provider=openrouter tools_used=['calculate'] total_tokens=1411

# RESPONSE: 42 multiplied by 17 equals 714.
# Tools used: ['calculate']
# Iterations: 2
# Provider: openrouter
# Model: openai/gpt-4o-mini
# Duration: 2084.04ms

# ============================================================
# USER: What's the weather in Tokyo?
# ============================================================
# 08:32:23 [info     ] conversation_reset            
# 08:32:23 [info     ] agent_run_started              user_message=What's the weather in Tokyo?
# 08:32:23 [info     ] agent_iteration                conversation_length=2 iteration=1
# 08:32:23 [info     ] provider_attempt               provider=openrouter
# 08:32:24 [info     ] provider_success               duration_ms=711.32 model=openai/gpt-4o-mini provider=openrouter tokens=676
# 08:32:24 [info     ] tool_calls_requested           iteration=1 tool_count=1
# 08:32:24 [info     ] tool_executed_successfully     arguments={'city': 'Tokyo'} duration_ms=0.02 tool_name=get_weather
# 08:32:24 [info     ] agent_iteration                conversation_length=4 iteration=2
# 08:32:24 [info     ] provider_attempt               provider=openrouter
# 08:32:25 [info     ] provider_success               duration_ms=929.7 model=openai/gpt-4o-mini provider=openrouter tokens=737
# 08:32:25 [info     ] agent_run_completed            iterations_used=2 provider=openrouter tools_used=['get_weather'] total_tokens=1413

# RESPONSE: The current weather in Tokyo is 14°C with cloudy conditions and a humidity level of 70%.
# Tools used: ['get_weather']
# Iterations: 2
# Provider: openrouter
# Model: openai/gpt-4o-mini
# Duration: 1642.19ms
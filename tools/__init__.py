"""
Tool registry for the AI agent.
"""
from config import GITHUB_ENABLED
from logging_config import get_logger

logger = get_logger(__name__)


def get_all_tools():
    """Get all available tools based on configuration."""
    from tools.basic_tools import ALL_TOOLS as BASIC_TOOLS
    from tools.file_reader import read_file, read_file_schema
    from tools.url_fetcher import fetch_url, fetch_url_schema
    
    tools = list(BASIC_TOOLS)  # 5 tools from Day 28
    
    # Add file/URL tools
    tools.append((read_file_schema, read_file))
    tools.append((fetch_url_schema, fetch_url))
    
    # Add GitHub tools if configured
    if GITHUB_ENABLED:
        from tools.github_tools import ALL_GITHUB_TOOLS
        tools.extend(ALL_GITHUB_TOOLS)
        logger.info("github_tools_enabled", count=len(ALL_GITHUB_TOOLS))
    else:
        logger.info("github_tools_disabled", reason="GITHUB_TOKEN not set")
    
    return tools


def register_all_tools(agent):
    """Register all available tools with an agent."""
    tools = get_all_tools()
    for schema, function in tools:
        agent.register_tool(schema, function)
    
    logger.info("all_tools_registered", count=len(tools))
    return agent


def get_available_tool_names():
    """Get list of all available tool names."""
    tools = get_all_tools()
    return [schema["function"]["name"] for schema, _ in tools]
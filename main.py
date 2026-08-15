# ============================================
# CLI CHATBOT — Stage 2: Multiple Modes & mode switching
# ============================================
from openai import OpenAI
from dotenv import load_dotenv
import os
from modes import MODES, get_mode_list, get_system_prompt, get_mode_display_name
from storage import save_conversation, load_conversation, list_conversations
from cost_tracker import CostTracker
from router import get_model_for_question, explain_routing, MODELS
from prompt_registry import PromptManager
from config import OPENROUTER_API_KEY, DEFAULT_MODEL, DEFAULT_MODEL, AGENT_ENABLED, AGENT_MAX_ITERATIONS, AGENT_DEFAULT_MODEL
import argparse
import asyncio

load_dotenv()

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)

MODEL = DEFAULT_MODEL

class ChatSession:
    def __init__(self, mode="general", max_history_turns=10, prompt_manager=None):
        self.mode = mode
        self.prompt_manager = prompt_manager or PromptManager()

        # Get prompt from registry instead of modes.py
        prompt_data = self.prompt_manager.get_prompt(mode)
        if prompt_data:
            self.system_prompt = prompt_data["system"]
            self.prompt_version = prompt_data["version"]
        else:
            self.system_prompt = "You are a helpful assistant."
            self.prompt_version = "default"
        
        self.messages = [
            {"role": "system", "content": self.system_prompt}
        ]
        self.total_tokens = 0
        self.turn_count = 0
        self.cost_tracker = CostTracker()
        self.max_history_turns = max_history_turns
        self.routing_enabled = True
        self.last_model_used = None
    
    def chat(self, user_input):
        self.messages.append({"role": "user", "content": user_input})

        # Apply sliding window before sending to API
        trimmed = self._apply_sliding_window()

        # Route to the right model
        if self.routing_enabled:
            model_config = get_model_for_question(user_input, self.mode)
            model_to_use = model_config["name"]
            self.last_model_used = model_config["display"]
        else:
            model_to_use = MODEL  # fall back to default
            self.last_model_used = MODEL

        try:
            response = client.chat.completions.create(
                model=model_to_use,
                max_tokens=500,
                messages=self.messages
            )
            
            content = response.choices[0].message.content
            prompt_tokens = response.usage.prompt_tokens if response.usage else 0
            completion_tokens = response.usage.completion_tokens if response.usage else 0
            finish = response.choices[0].finish_reason
            
            if content:
                self.messages.append({"role": "assistant", "content": content})
                self.turn_count += 1
                
                # Log to cost tracker with the ACTUAL model used
                call_log = self.cost_tracker.log_call(
                    model=model_to_use,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    finish_reason=finish,
                    operation=f"chat_{self.mode}"
                )
                
                return {
                    "content": content,
                    "tokens": prompt_tokens + completion_tokens,
                    "finish_reason": finish,
                    "display": self.cost_tracker.format_call_display(call_log),
                    "model_used": self.last_model_used,
                    "turns": self.turn_count,
                    "history_size": len(self.messages),
                }
            else:
                self.messages.pop()
                return {
                    "content": "(no response — try again)",
                    "tokens": 0,
                    "finish_reason": finish,
                    "display": "   [0 tok | failed]",
                    "model_used": self.last_model_used,
                    "turns": self.turn_count,
                    "history_size": len(self.messages),
                }
        except Exception as e:
            self.messages.pop()
            return {
                "content": f"Error: {e}",
                "tokens": 0,
                "finish_reason": "error",
                "display": "   [0 tok | error]",
                "model_used": self.last_model_used,
                "turns": self.turn_count,
                "history_size": len(self.messages),
            }
    
    def switch_mode(self, new_mode):
        """Switch mode — keeps conversation history but changes system prompt."""
        prompt_data = self.prompt_manager.get_prompt(new_mode)
        if not prompt_data:
            return False
        
        self.mode = new_mode
        self.system_prompt = prompt_data["system"]
        self.prompt_version = prompt_data["version"]

        # Replace system prompt (always first message)
        self.messages[0] = {
            "role": "system",
            "content": self.system_prompt
        }
        return True
    
    def reset(self):
        """Clear conversation history."""
        prompt_data = self.prompt_manager.get_prompt(self.mode)
        self.system_prompt = prompt_data["system"] if prompt_data else self.system_prompt

        self.messages = [
            {"role": "system", "content": self.system_prompt}
        ]
        self.total_tokens = 0
        self.turn_count = 0
        self.cost_tracker = CostTracker() # reset cost tracker
    
    def get_stats(self):
        return {
            "mode": get_mode_display_name(self.mode),
            "turns": self.turn_count,
            "total_tokens": self.total_tokens,
            "messages_in_history": len(self.messages),
            "est_cost": f"${self.total_tokens * 0.000003:.6f}",
        }

    def _apply_sliding_window(self):
        """Keep system prompt + last N turn pairs (max_history_turns * 2 messages)."""
        if self.max_history_turns is None:
            return  # unlimited (for testing/comparison)
        
        max_messages = 1 + (self.max_history_turns * 2)  # system + N user/assistant pairs
        
        if len(self.messages) > max_messages:
            # Keep system message (index 0) + last N turn pairs
            system = self.messages[0]
            recent = self.messages[-(self.max_history_turns * 2):]
            trimmed_count = len(self.messages) - max_messages
            self.messages = [system] + recent
            return trimmed_count
        return 0

# ============================================
# AGENT MODE (uses tools + resilient LLM client)
# ============================================

async def run_agent_mode():
    """Interactive CLI for the AI agent with tool-use capabilities."""
    from agent import Agent
    from tools import register_all_tools
    
    if not AGENT_ENABLED:
        print("❌ Agent mode is disabled. Set AGENT_ENABLED=true in .env")
        return
    
    # Initialize agent
    agent = Agent(
        model=AGENT_DEFAULT_MODEL,
        system_prompt=(
            "You are a helpful personal assistant with access to various tools "
            "including weather, calculator, GitHub, file reading, and URL fetching. "
            "Use tools when appropriate to help the user. Be concise and helpful."
        ),
        max_iterations=AGENT_MAX_ITERATIONS,
    )
    
    # Register all available tools
    register_all_tools(agent)
    
    # Welcome banner
    print("\n" + "=" * 60)
    print("🤖 AI PERSONAL ASSISTANT AGENT")
    print("=" * 60)
    print(f"Model: {agent.model}")
    print(f"Available tools: {len(agent.tools_registry)}")
    print(f"Max iterations: {agent.max_iterations}")
    print()
    print("Commands:")
    print("  quit, exit  - Exit the agent")
    print("  /tools      - List available tools")
    print("  /reset      - Clear conversation history")
    print("  /history    - Show conversation history")
    print("  /help       - Show this help")
    print("=" * 60)
    print("\nAsk me anything! I can check weather, do math, search GitHub, and more.\n")
    
    while True:
        try:
            user_input = input("💬 You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\n👋 Goodbye!")
            break
        
        if not user_input:
            continue
        
        # Exit commands
        if user_input.lower() in ('quit', 'exit', '/quit', '/exit'):
            print("\n👋 Goodbye!")
            break
        
        # Help command
        if user_input.lower() in ('/help', 'help'):
            print("\n📖 Commands:")
            print("  quit, exit  - Exit the agent")
            print("  /tools      - List available tools")
            print("  /reset      - Clear conversation history")
            print("  /history    - Show conversation history")
            print("  /help       - Show this help")
            print()
            continue
        
        # List tools
        if user_input.lower() == '/tools':
            print(f"\n🔧 Available Tools ({len(agent.tools_registry)}):")
            for name in agent.get_tool_names():
                schema = agent.tools_registry[name]["schema"]
                desc = schema["function"]["description"]
                # Truncate long descriptions
                if len(desc) > 80:
                    desc = desc[:80] + "..."
                print(f"  • {name}: {desc}")
            print()
            continue
        
        # Reset conversation
        if user_input.lower() == '/reset':
            agent.reset_conversation()
            print("\n♻️  Conversation reset\n")
            continue
        
        # Show history
        if user_input.lower() == '/history':
            history = agent.get_conversation_history()
            print(f"\n📜 Conversation history ({len(history)} messages):")
            for i, msg in enumerate(history):
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                if content and len(content) > 80:
                    content = content[:80] + "..."
                marker = "[tool_call]" if not content and msg.get("tool_calls") else content
                print(f"  [{i}] {role}: {marker}")
            print()
            continue
        
        # Send to agent
        print("\n🤖 Thinking...", end="", flush=True)
        
        try:
            result = await agent.run(user_input)
            
            # Clear "Thinking..." line
            print("\r" + " " * 20 + "\r", end="")
            
            # Show tools used and stats
            if result.get("tools_used"):
                tools_str = ", ".join(result["tools_used"])
                print(f"🔧 Tools used: {tools_str}")
                print(
                    f"📊 Iterations: {result.get('iterations')} | "
                    f"Tokens: {result.get('total_tokens')} | "
                    f"Provider: {result.get('provider_used')} | "
                    f"Duration: {result.get('duration_ms'):.0f}ms"
                )
                print()
            
            # Show response
            print(f"🤖 Agent: {result['response']}\n")
            
            # Show error if any
            if result.get("error"):
                print(f"⚠️  Note: {result['error']}\n")
        
        except KeyboardInterrupt:
            print("\n\n⚠️  Interrupted. Continuing...\n")
            continue
        
        except Exception as e:
            print(f"\n❌ Error: {type(e).__name__}: {e}\n")

def print_header():
    print("\n" + "=" * 55)
    print("  🤖  AI CLI Chatbot — Week 1 Project")
    print("  Built by Pragya Sriharsh")
    print("=" * 55)

def print_help():
    print("\nCommands:")
    print("  /mode <name>    Switch mode (see /modes)")
    print("  /modes          List available modes")
    print("  /stats          Show session stats")
    print("  /reset          Clear conversation history")
    print("  /save [name]    Save conversation to file")
    print("  /load <name>    Load a saved conversation")
    print("  /history        List saved conversations")
    print("  /window <n>     Set sliding window size (or 'off' for unlimited)")
    print("  /routing on/off Toggle automatic model selection")
    print("  /explain <q>    Show which model would handle a question")
    print("  /versions <mode>     Show version history of a mode's prompt")
    print("  /rollback <mode> <version> Roll back to an older prompt version")
    print("  /help           Show this help")
    print("  /quit           Exit")
    print()

def main():
    print_header()
    
    prompt_manager = PromptManager()
    session = ChatSession(mode="general", prompt_manager=prompt_manager)
    
    print(f"\n  Mode: {get_mode_display_name('general')}")
    print("  Type /help for commands\n")
    
    while True:
        try:
            user_input = input(f"You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\nGoodbye!")
            break
        
        if not user_input:
            continue
        
        # Handle commands
        if user_input.startswith("/"):
            cmd = user_input.lower().split()
            
            if cmd[0] in ["/quit", "/exit", "/q"]:
                stats = session.get_stats()
                print(f"\nSession stats: {stats['turns']} turns, {stats['total_tokens']} tokens")
                print("Goodbye! 👋\n")
                break
            
            elif cmd[0] == "/modes":
                print(f"\nAvailable modes:\n{get_mode_list()}\n")
            
            elif cmd[0] == "/mode" and len(cmd) > 1:
                mode_name = cmd[1]
                if mode_name in MODES:
                    session.switch_mode(mode_name)
                    print(f"\n  Switched to: {get_mode_display_name(mode_name)}\n")
                else:
                    print(f"\n  Unknown mode: {mode_name}")
                    print(f"  Available: {', '.join(MODES.keys())}\n")
            
            elif cmd[0] == "/stats":
                summary = session.cost_tracker.get_summary()
                breakdown = session.cost_tracker.get_per_model_breakdown()
                
                print(f"\n  === Session Stats ===")
                print(f"  Mode:           {get_mode_display_name(session.mode)}")
                print(f"  Total calls:    {summary['total_calls']}")
                print(f"  Input tokens:   {summary['total_input_tokens']:,}")
                print(f"  Output tokens:  {summary['total_output_tokens']:,}")
                print(f"  Total tokens:   {summary['total_tokens']:,}")
                print(f"  Avg per call:   {summary['avg_tokens_per_call']:.0f}")
                print(f"  Total cost:     ${summary['total_cost_usd']:.6f}")
                
                if len(breakdown) > 1:
                    print(f"\n  === Per-Model Breakdown ===")
                    for model, stats in breakdown.items():
                        model_short = model.split("/")[-1][:30]
                        print(f"  {model_short}: {stats['calls']} calls, "
                            f"{stats['input_tokens'] + stats['output_tokens']} tok, "
                            f"${stats['cost']:.6f}")
                print(f"  Window:         {session.max_history_turns if session.max_history_turns else 'unlimited'} turns")
                print(f"  Mode:           {get_mode_display_name(session.mode)} ({session.prompt_version})")
                print()
            
            elif cmd[0] == "/reset":
                session.reset()
                print("\n  Conversation cleared. Fresh start!\n")
            
            elif cmd[0] == "/save":
                name = cmd[1] if len(cmd) > 1 else None
                filepath = save_conversation(
                    session.messages,
                    session.mode,
                    session.get_stats(),
                    name
                )
                print(f"\n  Saved to: {filepath}\n")
            
            elif cmd[0] == "/load":
                if len(cmd) < 2:
                    print("\n  Usage: /load <filename>\n")
                else:
                    data = load_conversation(cmd[1])
                    if data:
                        session.messages = data["messages"]
                        session.mode = data.get("mode", "general")
                        session.total_tokens = data.get("stats", {}).get("total_tokens", 0)
                        session.turn_count = data.get("stats", {}).get("turns", 0)
                        print(f"\n  Loaded: {cmd[1]}")
                        print(f"  Mode: {get_mode_display_name(session.mode)}")
                        print(f"  Turns: {session.turn_count}\n")
                    else:
                        print(f"\n  File not found: {cmd[1]}\n")
            
            elif cmd[0] == "/history":
                convos = list_conversations()
                if not convos:
                    print("\n  No saved conversations.\n")
                else:
                    print("\n  Saved conversations:")
                    for c in convos:
                        print(f"    {c['filename']:<30} {c['mode']:<15} {c['turns']} turns, {c['tokens']} tok")
                    print()
            elif cmd[0] == "/window":
                if len(cmd) < 2:
                    current = session.max_history_turns
                    print(f"\n  Current window: {current if current else 'unlimited'} turns")
                    print(f"  Usage: /window <number>  (e.g. /window 5)")
                    print(f"         /window off       (disable, keep all history)\n")
                elif cmd[1].lower() == "off":
                    session.max_history_turns = None
                    print("\n  Sliding window OFF — full history kept (expensive!)\n")
                else:
                    try:
                        n = int(cmd[1])
                        if n < 1:
                            print("\n  Window size must be at least 1\n")
                        else:
                            session.max_history_turns = n
                            print(f"\n  Sliding window set to {n} turn pairs\n")
                    except ValueError:
                        print(f"\n  Invalid window size: {cmd[1]}\n")

            elif cmd[0] == "/routing":
                if len(cmd) < 2:
                    status = "ON" if session.routing_enabled else "OFF"
                    print(f"\n  Routing: {status}")
                    print(f"  Available models:")
                    for cat, m in MODELS.items():
                        print(f"    {cat:<10} {m['display']:<25} — for {', '.join(m['strengths'])}")
                    print(f"\n  Usage: /routing on  or  /routing off\n")
                elif cmd[1].lower() == "on":
                    session.routing_enabled = True
                    print("\n  Routing ON — auto-selecting model per question\n")
                elif cmd[1].lower() == "off":
                    session.routing_enabled = False
                    print(f"\n  Routing OFF — always using {MODEL}\n")

            elif cmd[0] == "/explain":
                if len(cmd) < 2:
                    print("\n  Usage: /explain <your question>")
                    print("  Shows which model would be used (without actually asking)\n")
                else:
                    question = " ".join(cmd[1:])
                    info = explain_routing(question, session.mode)
                    print(f"\n  Question: {question}")
                    print(f"  Would use: {info['model_name']}")
                    print(f"  Reason:    {info['reason']}\n")

            elif cmd[0] == "/versions":
                if len(cmd) < 2:
                    print(f"\n  Usage: /versions <mode>")
                    print(f"  Available modes: {', '.join(MODES.keys())}\n")
                else:
                    mode = cmd[1]
                    versions = session.prompt_manager.list_versions(mode)
                    if not versions:
                        print(f"\n  Unknown mode: {mode}\n")
                    else:
                        print(f"\n  === Versions for '{mode}' ===")
                        for v in versions:
                            marker = "→" if v["is_current"] else " "
                            print(f"  {marker} {v['version']} ({v['created']}): {v['notes']}")
                        print()

            elif cmd[0] == "/rollback":
                if len(cmd) < 3:
                    print(f"\n  Usage: /rollback <mode> <version>")
                    print(f"  Example: /rollback ruby v1.0\n")
                else:
                    mode = cmd[1]
                    version = cmd[2]
                    success = session.prompt_manager.set_active_version(mode, version)
                    if success:
                        print(f"\n  Rolled back '{mode}' to {version}")
                        # If currently in this mode, reload the prompt
                        if session.mode == mode:
                            session.switch_mode(mode)
                            print(f"  (Current session updated to use {version})\n")
                        else:
                            print()
                    else:
                        print(f"\n  Failed: invalid mode or version\n")
            
            elif cmd[0] == "/help":
                print_help()

            
            else:
                print(f"\n  Unknown command: {cmd[0]}. Type /help\n")
            
            continue
        
        # Regular chat
        result = session.chat(user_input)
        
        print(f"\nAI [{result['model_used']}]: {result['content']}")
        print(result['display'])
        print()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="AI CLI Chatbot - Chat mode or Agent mode with tools"
    )
    parser.add_argument(
        "--agent",
        action="store_true",
        help="Run in agent mode with tool-use capabilities"
    )
    args = parser.parse_args()
    
    if args.agent:
        # Agent mode with tools
        asyncio.run(run_agent_mode())
    else:
        # Existing chat mode (unchanged)
        main()
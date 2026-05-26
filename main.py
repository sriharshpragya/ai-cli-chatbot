# ============================================
# CLI CHATBOT — Stage 2: Multiple Modes & mode switching
# ============================================
from openai import OpenAI
from dotenv import load_dotenv
import os
from modes import MODES, get_mode_list, get_system_prompt, get_mode_display_name
from storage import save_conversation, load_conversation, list_conversations

load_dotenv()

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)

MODEL = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"

class ChatSession:
    def __init__(self, mode="general"):
        self.mode = mode
        self.messages = [
            {"role": "system", "content": get_system_prompt(mode)}
        ]
        self.total_tokens = 0
        self.turn_count = 0
    
    def chat(self, user_input):
        self.messages.append({"role": "user", "content": user_input})
        
        try:
            response = client.chat.completions.create(
                model=MODEL,
                max_tokens=500,
                messages=self.messages
            )
            
            content = response.choices[0].message.content
            tokens = response.usage.total_tokens if response.usage else 0
            finish = response.choices[0].finish_reason
            
            if content:
                self.messages.append({"role": "assistant", "content": content})
                self.total_tokens += tokens
                self.turn_count += 1
            else:
                self.messages.pop()
                content = "(no response — try again)"
            
            return {
                "content": content,
                "tokens": tokens,
                "finish_reason": finish,
                "total_tokens": self.total_tokens,
                "turns": self.turn_count,
                "history_size": len(self.messages),
            }
        
        except Exception as e:
            self.messages.pop()
            return {
                "content": f"Error: {e}",
                "tokens": 0,
                "finish_reason": "error",
                "total_tokens": self.total_tokens,
                "turns": self.turn_count,
                "history_size": len(self.messages),
            }
    
    def switch_mode(self, new_mode):
        """Switch mode — keeps conversation history but changes system prompt."""
        self.mode = new_mode
        # Replace system prompt (always first message)
        self.messages[0] = {
            "role": "system",
            "content": get_system_prompt(new_mode)
        }
    
    def reset(self):
        """Clear conversation history."""
        self.messages = [
            {"role": "system", "content": get_system_prompt(self.mode)}
        ]
        self.total_tokens = 0
        self.turn_count = 0
    
    def get_stats(self):
        return {
            "mode": get_mode_display_name(self.mode),
            "turns": self.turn_count,
            "total_tokens": self.total_tokens,
            "messages_in_history": len(self.messages),
            "est_cost": f"${self.total_tokens * 0.000003:.6f}",
        }


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
    print("  /help           Show this help")
    print("  /quit           Exit")
    print()

def main():
    print_header()
    
    session = ChatSession(mode="general")
    
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
                stats = session.get_stats()
                print(f"\n  Mode:     {stats['mode']}")
                print(f"  Turns:    {stats['turns']}")
                print(f"  Tokens:   {stats['total_tokens']}")
                print(f"  Messages: {stats['messages_in_history']}")
                print(f"  Est cost: {stats['est_cost']}\n")
            
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

            elif cmd[0] == "/help":
                print_help()
            
            else:
                print(f"\n  Unknown command: {cmd[0]}. Type /help\n")
            
            continue
        
        # Regular chat
        result = session.chat(user_input)
        
        print(f"\nAI: {result['content']}")
        print(f"   [{result['tokens']} tok | {result['finish_reason']} | turn {result['turns']}]\n")

if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
AI Shell - A natural language command line interface utility.

This utility allows users to interact with the command line using natural language,
converting NL commands to bash commands using an LLM, with safety checks and
background task support.
"""

import argparse
import asyncio
import os
import signal
import sys
import time
from pathlib import Path
from typing import Optional

import colorama
from colorama import Fore, Style
from prompt_toolkit import prompt
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter, Completer, Completion
from prompt_toolkit.shortcuts import CompleteStyle

from config_manager import ConfigManager
from llm_handler import LLMHandler
from safety_checker import SafetyChecker
from task_manager import TaskManager


class AIShellCompleter(Completer):
    """Custom completer for AI Shell commands."""
    
    def __init__(self, ai_shell):
        self.ai_shell = ai_shell
        
        # Define special commands that can be completed
        self.special_commands = [
            'help', 'exit', 'quit', 'tasks', 'config', 'reload-config',
            'cache-stats', 'clear-cache'
        ]
        
        # Common command prefixes for natural language
        self.nl_commands = [
            'show all files', 'list all', 'find files', 'remove files',
            'delete files', 'copy files', 'move files', 'search for',
            'monitor cpu', 'monitor memory', 'monitor disk', 'monitor process',
            'watch folder', 'track changes', 'list processes', 'kill process',
            'start service', 'stop service', 'check status', 'get info about',
            'compress files', 'extract files', 'backup folder', 'sync folders'
        ]
    
    def get_completions(self, document, complete_event):
        """Get completions for the current document."""
        text = document.text_before_cursor.lower().strip()
        
        # Skip completion if text is too short
        if len(text) < 1:
            return
        
        # Complete special commands first (highest priority)
        for cmd in self.special_commands:
            if cmd.startswith(text):
                yield Completion(cmd, start_position=-len(text), display=cmd)
        
        # Complete kill-task commands with actual task IDs
        if text.startswith('kill-task'):
            if ' ' in text:
                task_prefix = text.split(' ', 1)[1] if len(text.split(' ', 1)) > 1 else ''
                for task_id in self.ai_shell.task_manager.background_tasks.keys():
                    if task_id.startswith(task_prefix):
                        yield Completion(
                            task_id, 
                            start_position=-len(task_prefix),
                            display=f"{task_id} (task)"
                        )
            else:
                # Just 'kill-task' typed, suggest the space
                yield Completion('kill-task ', start_position=-len(text), display='kill-task <task-id>')
        
        # Complete natural language command starters (lower priority)
        for nl_cmd in self.nl_commands:
            if nl_cmd.startswith(text) and text not in self.special_commands:
                yield Completion(nl_cmd, start_position=-len(text), display=nl_cmd)


class AIShell:
    """Main AI Shell interface."""
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize the AI Shell."""
        # Initialize colorama first with proper settings
        colorama.init(autoreset=True, strip=False, convert=True)
        
        self.config = ConfigManager(config_path)
        
        # Validate and create logging directory - exit if it fails
        if not self.config.validate_and_create_log_directory():
            print(f"{Fore.RED}Fatal error: Cannot initialize logging directory. Exiting.{Style.RESET_ALL}")
            sys.exit(1)
        
        # Check if colors should be disabled
        self.use_colors = self.config.get('shell.colored_output', True)
        if not self.use_colors:
            # Disable colorama if colors are disabled
            colorama.init(strip=True)
        
        self.llm_handler = LLMHandler(self.config)
        self.safety_checker = SafetyChecker(self.llm_handler)
        self.task_manager = TaskManager(self.config)  # Pass config to TaskManager
        self.running = True
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        # Setup history file
        self.history_file = Path.home() / ".ai_shell_history"
        self.history = FileHistory(str(self.history_file))
        
        # Setup command cache
        self.cache_file = Path.home() / ".ai_shell_cache.json"
        self.command_cache = self._load_command_cache()
        
        # Setup completer
        self.completer = AIShellCompleter(self)
        
        # Check terminal capabilities
        self.terminal_supports_cpr = self._check_terminal_capabilities()
    
    def _color(self, color_code: str, text: str) -> str:
        """Safely apply color codes with fallback."""
        if self.use_colors:
            return f"{color_code}{text}{Style.RESET_ALL}"
        return text
    
    def _check_terminal_capabilities(self) -> bool:
        """Check if terminal supports advanced features like CPR."""
        # Check if we're in a basic terminal that doesn't support CPR
        term = os.environ.get('TERM', '').lower()
        
        # List of terminals that typically don't support CPR well
        basic_terminals = ['dumb', 'unknown', 'emacs', 'tramp']
        
        if term in basic_terminals:
            return False
        
        # Check if we're running in a CI environment
        ci_vars = ['CI', 'GITHUB_ACTIONS', 'TRAVIS', 'JENKINS_URL', 'GITLAB_CI']
        if any(os.environ.get(var) for var in ci_vars):
            return False
        
        # Check if stdout is not a tty (redirected)
        if not sys.stdout.isatty():
            return False
        
        return True
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        print(f"\n{self._color(Fore.YELLOW, 'Shutting down AI Shell...')}")
        self.running = False
        
        # Save command cache on shutdown
        self._save_command_cache()
        
        self.task_manager.shutdown()
        sys.exit(0)
    
    def _load_command_cache(self) -> dict:
        """Load command cache from file."""
        try:
            if self.cache_file.exists():
                import json
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                    # Validate cache structure
                    if isinstance(cache_data, dict):
                        print(f"{self._color(Fore.GREEN, f'📚 Loaded {len(cache_data)} cached commands')}")
                        return cache_data
        except Exception as e:
            print(f"{self._color(Fore.YELLOW, f'⚠️  Could not load command cache: {e}')}")
        
        return {}
    
    def _save_command_cache(self):
        """Save command cache to file."""
        try:
            import json
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.command_cache, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"{self._color(Fore.YELLOW, f'⚠️  Could not save command cache: {e}')}")
    
    def _get_cache_key(self, user_input: str) -> str:
        """Generate a normalized cache key from user input."""
        # Normalize the input for consistent caching
        return user_input.lower().strip()
    
    def _get_cached_command(self, user_input: str) -> Optional[dict]:
        """Get cached command if available."""
        cache_key = self._get_cache_key(user_input)
        return self.command_cache.get(cache_key)
    
    def _cache_command(self, user_input: str, bash_command: str, is_background: bool, safety_result: dict = None):
        """Cache a command mapping with safety check results."""
        cache_key = self._get_cache_key(user_input)
        
        # If no safety result provided, perform safety check now for caching
        if safety_result is None:
            safety_result = self.safety_checker.check_command_safety(bash_command)
        
        self.command_cache[cache_key] = {
            'bash_command': bash_command,
            'is_background': is_background,
            'safety_result': safety_result,
            'timestamp': time.time(),
            'usage_count': self.command_cache.get(cache_key, {}).get('usage_count', 0) + 1
        }
        
        # Limit cache size (keep most recent 1000 commands)
        if len(self.command_cache) > 1000:
            # Remove oldest 100 commands
            sorted_cache = sorted(
                self.command_cache.items(), 
                key=lambda x: x[1].get('timestamp', 0)
            )
            for key, _ in sorted_cache[:100]:
                del self.command_cache[key]
        
        # Save cache periodically
        self._save_command_cache()
    
    def _show_cache_stats(self):
        """Show command cache statistics."""
        if not self.command_cache:
            print(self._color(Fore.YELLOW, "📊 No cached commands."))
            return
        
        cache_size = len(self.command_cache)
        total_usage = sum(entry.get('usage_count', 1) for entry in self.command_cache.values())
        
        # Count commands with cached safety results
        safety_cached = sum(1 for entry in self.command_cache.values() if entry.get('safety_result'))
        dangerous_cached = sum(1 for entry in self.command_cache.values() 
                              if entry.get('safety_result', {}).get('is_dangerous', False))
        
        print(self._color(Fore.CYAN, "📊 Command Cache Statistics:"))
        print(f"  Total cached commands: {cache_size}")
        print(f"  Total cache hits: {total_usage}")
        print(f"  Commands with cached safety checks: {safety_cached}")
        print(f"  Dangerous commands cached: {dangerous_cached}")
        print(f"  Cache file: {self.cache_file}")
        
        # Show most used commands
        if cache_size > 0:
            print("\n🔥 Most used commands:")
            sorted_commands = sorted(
                self.command_cache.items(),
                key=lambda x: x[1].get('usage_count', 1),
                reverse=True
            )[:5]
            
            for i, (nl_cmd, data) in enumerate(sorted_commands, 1):
                usage = data.get('usage_count', 1)
                bash_cmd = data.get('bash_command', '').strip()
                is_dangerous = data.get('safety_result', {}).get('is_dangerous', False)
                safety_icon = "⚠️ " if is_dangerous else "✅ "
                
                if len(bash_cmd) > 45:
                    bash_cmd = bash_cmd[:42] + "..."
                print(f"  {i}. [{usage}x] {safety_icon}{nl_cmd} → {bash_cmd}")
    
    def _clear_cache(self):
        """Clear the command cache."""
        cache_size = len(self.command_cache)
        confirm = input(f"{self._color(Fore.YELLOW, f'Clear {cache_size} cached commands? (yes/no): ')}")
        
        if confirm.lower() in ['yes', 'y']:
            self.command_cache.clear()
            self._save_command_cache()
            print(self._color(Fore.GREEN, "✅ Command cache cleared."))
        else:
            print(self._color(Fore.BLUE, "Cache clear cancelled."))
    
    def print_banner(self):
        """Print the welcome banner."""
        banner = f"""
{self._color(Fore.CYAN, '╔══════════════════════════════════════════════════════════════╗')}
{self._color(Fore.CYAN, '║                        AI Shell v1.0                        ║')}
{self._color(Fore.CYAN, '║              Natural Language Command Line Interface         ║')}
{self._color(Fore.CYAN, '╚══════════════════════════════════════════════════════════════╝')}

{self._color(Fore.GREEN, 'Features:')}
• Convert natural language to bash commands
• Safety checks for potentially harmful commands
• Background task monitoring and automation
• LLM-powered command analysis

{self._color(Fore.YELLOW, "Type 'help' for commands, 'exit' to quit")}
"""
        print(banner)
    
    def print_help(self):
        """Print help information."""
        help_text = f"""
{Fore.CYAN}AI Shell Commands:{Style.RESET_ALL}

{Fore.GREEN}Basic Usage:{Style.RESET_ALL}
  Just type your request in natural language!
  
{Fore.GREEN}Examples:{Style.RESET_ALL}
  • show all files one day old
  • remove image files in current directory
  • list python processes that run on GPU
  • monitor cpu usage of all python processes
  • monitor folder 'test' and notify if size exceeds 5GB

{Fore.GREEN}Special Commands:{Style.RESET_ALL}
  help                    - Show this help
  exit, quit              - Exit AI Shell
  tasks                   - Show running background tasks
  kill-task <id>          - Stop a background task
  config                  - Show current configuration
  reload-config           - Reload configuration file
  cache-stats             - Show command cache statistics  
  clear-cache             - Clear command cache

{Fore.GREEN}Safety Features:{Style.RESET_ALL}
  • All commands are reviewed for safety before execution
  • Confirmation required for potentially harmful operations
  • Background monitoring tasks can be controlled and stopped
"""
        print(help_text)
    
    def handle_special_commands(self, user_input: str) -> bool:
        """Handle special shell commands. Returns True if command was handled."""
        user_input = user_input.strip().lower()
        
        if user_input in ['exit', 'quit']:
            print(self._color(Fore.YELLOW, "Goodbye!"))
            self.running = False
            return True
        
        elif user_input == 'help':
            self.print_help()
            return True
        
        elif user_input == 'tasks':
            self.task_manager.show_tasks()
            return True
        
        elif user_input.startswith('kill-task '):
            task_id = user_input.split(' ', 1)[1]
            self.task_manager.stop_task(task_id)
            return True
        
        elif user_input == 'config':
            self.config.show_config()
            return True
        
        elif user_input == 'reload-config':
            self.config.reload()
            print(self._color(Fore.GREEN, "Configuration reloaded successfully."))
            return True
        
        elif user_input == 'cache-stats':
            self._show_cache_stats()
            return True
        
        elif user_input == 'clear-cache':
            self._clear_cache()
            return True
        
        return False
    
    def process_natural_language_command(self, user_input: str):
        """Process a natural language command."""
        try:
            # Check cache first
            cached_result = self._get_cached_command(user_input)
            
            if cached_result:
                print(self._color(Fore.GREEN, "📚 Using cached command..."))
                bash_command = cached_result['bash_command']
                is_background_task = cached_result['is_background']
                safety_result = cached_result.get('safety_result')
                
                # Update usage count
                self._cache_command(user_input, bash_command, is_background_task, safety_result)
            else:
                print(self._color(Fore.BLUE, "🤖 Converting to bash command..."))
                
                # Convert NL to bash command (outputs to console by default)
                bash_command = self.llm_handler.convert_nl_to_bash(user_input)
                
                if not bash_command:
                    print(self._color(Fore.RED, "❌ Could not convert command. Please try rephrasing."))
                    return
                
                # Check if it's a monitoring/background task
                is_background_task = self.llm_handler.is_background_task(user_input)
                
                # Perform safety check for new commands
                safety_result = self.safety_checker.check_command_safety(bash_command)
                
                # Cache the result with safety check
                self._cache_command(user_input, bash_command, is_background_task, safety_result)
            
            print(f"{self._color(Fore.CYAN, 'Generated command:')} {self._color(Fore.WHITE, bash_command)}")
            
            if is_background_task:
                self.handle_background_task(user_input, bash_command)
            else:
                # Pass cached safety result to avoid re-checking
                self.handle_regular_command(bash_command, cached_result.get('safety_result') if cached_result else safety_result)
        
        except Exception as e:
            print(self._color(Fore.RED, f"❌ Error processing command: {str(e)}"))
    
    def handle_regular_command(self, bash_command: str, cached_safety_result: dict = None):
        """Handle a regular (non-background) command."""
        # Use cached safety result if available, otherwise perform safety check
        if cached_safety_result:
            print(self._color(Fore.GREEN, "📚 Using cached safety check..."))
            safety_result = cached_safety_result
        else:
            print(self._color(Fore.BLUE, "🔍 Checking command safety..."))
            safety_result = self.safety_checker.check_command_safety(bash_command)
        
        if safety_result['is_dangerous']:
            print(f"{Fore.RED}⚠️  WARNING: This command may be harmful!{Style.RESET_ALL}")
            print(f"{Fore.RED}Reason: {safety_result['reason']}{Style.RESET_ALL}")
            
            confirm = input(f"{Fore.YELLOW}Do you still want to proceed? (yes/no): {Style.RESET_ALL}")
            if confirm.lower() not in ['yes', 'y']:
                print(f"{Fore.GREEN}Command cancelled.{Style.RESET_ALL}")
                return
        else:
            confirm = input(f"{Fore.GREEN}Execute this command? (yes/no): {Style.RESET_ALL}")
            if confirm.lower() not in ['yes', 'y']:
                print(f"{Fore.GREEN}Command cancelled.{Style.RESET_ALL}")
                return
        
        # Execute the command
        print(self._color(Fore.BLUE, "🚀 Executing command..."))
        result = asyncio.run(self.task_manager.execute_command(bash_command))
        
        if result['success']:
            if result['output']:
                print(f"{Fore.GREEN}Output:{Style.RESET_ALL}\n{result['output']}")
                # Show additional info if command succeeded with non-zero exit code
                if result['return_code'] != 0:
                    print(f"{Fore.YELLOW}ℹ️  Command completed successfully (exit code: {result['return_code']}){Style.RESET_ALL}")
            else:
                success_msg = "✅ Command executed successfully."
                if result['return_code'] != 0:
                    success_msg += f" (exit code: {result['return_code']})"
                print(f"{Fore.GREEN}{success_msg}{Style.RESET_ALL}")
        else:
            error_msg = f"❌ Command failed (exit code: {result['return_code']}):"
            print(f"{Fore.RED}{error_msg}{Style.RESET_ALL}\n{result['error']}")
    
    def handle_background_task(self, user_input: str, bash_command: str):
        """Handle a background monitoring task."""
        print(self._color(Fore.MAGENTA, "🔄 This appears to be a monitoring task."))
        
        # Get log directory from config
        log_directory = self.config.get('monitoring.log_directory', 'logs/')
        
        # Generate monitoring script without pre-generating task ID
        # The task manager will generate the actual task ID when creating the task
        monitoring_script = self.llm_handler.generate_monitoring_script(
            user_input, bash_command, log_directory, "PLACEHOLDER"
        )
        
        if not monitoring_script:
            print(self._color(Fore.RED, "❌ Could not generate monitoring script."))
            return
        
        print(self._color(Fore.CYAN, "Generated monitoring script:"))
        print(self._color(Fore.WHITE, f"{monitoring_script[:200]}..."))
        
        confirm = input(f"{self._color(Fore.GREEN, 'Start this monitoring task? (yes/no): ')}")
        if confirm.lower() not in ['yes', 'y']:
            print(self._color(Fore.GREEN, "Task cancelled."))
            return
        
        # Start background task (non-blocking)
        try:
            task_id = self.task_manager.start_monitoring_task_sync(
                user_input, monitoring_script
            )
            print(self._color(Fore.GREEN, f"✅ Background task started with ID: {task_id}"))
            print(self._color(Fore.YELLOW, f"Use 'tasks' to view running tasks or 'kill-task {task_id}' to stop."))
            
            # Brief pause to let the task initialize before returning to prompt
            import time
            time.sleep(0.5)
            
        except Exception as e:
            print(self._color(Fore.RED, f"❌ Failed to start task: {str(e)}"))
    
    def run(self):
        """Run the main shell loop."""
        self.print_banner()
        
        # Create a simple prompt without color codes to avoid control character issues
        prompt_text = "ai-shell> "
        
        while self.running:
            try:
                # Try advanced prompt first
                try:
                    # Configure prompt based on terminal capabilities
                    prompt_kwargs = {
                        'history': self.history,
                        'auto_suggest': AutoSuggestFromHistory(),
                        'completer': self.completer,
                        'complete_style': CompleteStyle.READLINE_LIKE,
                        'enable_history_search': True,
                        'mouse_support': False,
                        'wrap_lines': True,
                        'complete_while_typing': False,
                        'validate_while_typing': False
                    }
                    
                    # Add terminal-specific settings only if supported
                    if not self.terminal_supports_cpr:
                        # Disable features that require CPR for basic terminals
                        prompt_kwargs.update({
                            'swap_light_and_dark_colors': False,
                            'include_default_pygments_style': False
                        })
                    
                    user_input = prompt(prompt_text, **prompt_kwargs).strip()
                
                except Exception as prompt_error:
                    # Fallback to basic input if prompt-toolkit fails
                    print(f"Warning: Using fallback input method due to terminal compatibility issues.")
                    try:
                        user_input = input(prompt_text).strip()
                    except Exception:
                        # Last resort - just use raw input
                        sys.stdout.write(prompt_text)
                        sys.stdout.flush()
                        user_input = sys.stdin.readline().strip()
                
                if not user_input:
                    continue
                
                # Handle special commands
                if self.handle_special_commands(user_input):
                    continue
                
                # Process natural language command
                self.process_natural_language_command(user_input)
            
            except KeyboardInterrupt:
                print(self._color(Fore.YELLOW, "\nUse 'exit' to quit or Ctrl+C again to force quit."))
                continue
            except EOFError:
                print(self._color(Fore.YELLOW, "\nGoodbye!"))
                break
            except Exception as e:
                print(self._color(Fore.RED, f"❌ Unexpected error: {str(e)}"))
        
        # Cleanup
        print(self._color(Fore.YELLOW, "Saving command cache..."))
        self._save_command_cache()
        self.task_manager.shutdown()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="AI Shell - Natural Language Command Line Interface"
    )
    parser.add_argument(
        "--config", "-c",
        type=str,
        help="Path to configuration file (default: config.yaml)"
    )
    parser.add_argument(
        "--version", "-v",
        action="version",
        version="AI Shell 1.0"
    )
    
    args = parser.parse_args()
    
    # Create and run the AI Shell
    shell = AIShell(config_path=args.config)
    
    try:
        shell.run()
    except KeyboardInterrupt:
        # Initialize colorama for this message too
        colorama.init(autoreset=True)
        print(f"\n{Fore.YELLOW}Forced shutdown.{Style.RESET_ALL}")
        sys.exit(0)


if __name__ == "__main__":
    main()
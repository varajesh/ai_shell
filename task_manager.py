"""
Task Manager module for AI Shell.

This module handles execution of commands and management of background monitoring tasks,
including process management, logging, and cleanup.
"""

import asyncio
import os
import signal
import subprocess
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
import json
import threading

import colorama
from colorama import Fore, Style


class BackgroundTask:
    """Represents a background monitoring task."""
    
    def __init__(self, task_id: str, description: str, script_content: str, interval: int = 5):
        self.task_id = task_id
        self.description = description
        self.script_content = script_content
        self.interval = interval
        self.process: Optional[subprocess.Popen] = None
        self.script_file: Optional[str] = None
        self.monitor_thread: Optional[threading.Thread] = None
        self.start_time = datetime.now()
        self.status = "created"  # created, running, stopped, error
        self.output_log: List[str] = []
        self.error_log: List[str] = []
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert task to dictionary for serialization."""
        return {
            "task_id": self.task_id,
            "description": self.description,
            "interval": self.interval,
            "start_time": self.start_time.isoformat(),
            "status": self.status,
            "pid": self.process.pid if self.process else None,
            "output_lines": len(self.output_log),
            "error_lines": len(self.error_log)
        }


class TaskManager:
    """Manages command execution and background tasks."""
    
    def __init__(self, config_manager=None):
        """Initialize the task manager."""
        # Initialize colorama for cross-platform color support
        colorama.init(autoreset=True, convert=True)
        
        self.config = config_manager
        self.background_tasks: Dict[str, BackgroundTask] = {}
        
        # Get log directory from config or use default
        if self.config:
            log_dir = self.config.get('monitoring.log_directory', 'logs/')
            self.task_logging_enabled = self.config.get('monitoring.task_logging.enabled', True)
            self.max_log_file_size = self.config.get('monitoring.task_logging.max_log_file_size_mb', 10) * 1024 * 1024
            self.max_log_files = self.config.get('monitoring.task_logging.max_log_files_per_task', 5)
        else:
            log_dir = 'logs/'
            self.task_logging_enabled = True
            self.max_log_file_size = 10 * 1024 * 1024  # 10MB
            self.max_log_files = 5
        
        self.log_directory = Path(log_dir).resolve()
        self.log_directory.mkdir(parents=True, exist_ok=True)
        self.max_log_lines = 1000
        
        # Setup signal handling for graceful shutdown
        self._shutdown_requested = False
        
        # Clean up any orphaned task directories on startup
        self._cleanup_orphaned_tasks()
        
    def shutdown(self):
        """Shutdown all background tasks."""
        self._shutdown_requested = True
        
        print(f"{Fore.YELLOW}Stopping all background tasks...{Style.RESET_ALL}")
        
        for task_id in list(self.background_tasks.keys()):
            self.stop_task(task_id)
        
        print(f"{Fore.GREEN}All background tasks stopped.{Style.RESET_ALL}")
    
    async def execute_command(self, command: str, timeout: int = 60) -> Dict[str, Any]:
        """
        Execute a command and return the result.
        
        Args:
            command: The bash command to execute
            timeout: Maximum execution time in seconds
        
        Returns:
            Dict with keys: success, output, error, return_code
        """
        try:
            # Log the command execution
            self._log_command(command)
            
            # Execute the command using bash explicitly for better shell compatibility
            # This ensures complex shell constructs work properly
            process = await asyncio.create_subprocess_exec(
                '/bin/bash', '-c', command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=os.getcwd()
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return {
                    "success": False,
                    "output": "",
                    "error": f"Command timed out after {timeout} seconds",
                    "return_code": -1
                }
            
            # Decode output
            output = stdout.decode('utf-8', errors='replace') if stdout else ""
            error = stderr.decode('utf-8', errors='replace') if stderr else ""
            
            # Use intelligent success determination
            success = self._determine_command_success(command, process.returncode, output, error)
            
            # Log additional info for non-zero exit codes that we're treating as success
            if success and process.returncode != 0:
                self._log_info(f"Command with exit code {process.returncode} treated as successful: {command[:100]}...")
            
            result = {
                "success": success,
                "output": output,
                "error": error,
                "return_code": process.returncode
            }
            
            # Log the result
            self._log_command_result(command, result)
            
            return result
        
        except Exception as e:
            error_msg = f"Failed to execute command: {str(e)}"
            self._log_error(f"Command execution error: {error_msg}")
            
            return {
                "success": False,
                "output": "",
                "error": error_msg,
                "return_code": -1
            }
    
    
    def start_monitoring_task_sync(self, description: str, script_content: str, interval: int = 5) -> str:
        """
        Start a background monitoring task synchronously (non-blocking).
        
        Args:
            description: Human-readable description of the task
            script_content: The bash script content to execute
            interval: Execution interval in seconds
        
        Returns:
            Task ID string
        """
        task_id = str(uuid.uuid4())[:8]
        
        # Create the background task
        task = BackgroundTask(task_id, description, script_content, interval)
        
        try:
            # Create a temporary script file with the actual task ID
            script_file = self._create_script_file(task_id, script_content, interval)
            task.script_file = script_file
            
            # Start the background process with complete isolation (no pipes to prevent blocking)
            process = subprocess.Popen(
                ['nohup', 'bash', script_file],
                stdout=subprocess.DEVNULL,  # No pipes - prevents blocking
                stderr=subprocess.DEVNULL,  # Script handles all logging  
                stdin=subprocess.DEVNULL,   # No input needed
                start_new_session=True,     # Process isolation
                cwd=os.getcwd()
            )
            
            task.process = process
            task.status = "running"
            
            # Store the task
            self.background_tasks[task_id] = task
            
            # Log immediately (non-blocking)
            self._log_info(f"Started background task {task_id}: {description}")
            
            # Start monitoring the task output in a daemon thread (non-blocking)
            # Do this AFTER logging to ensure we return quickly
            self._start_task_monitoring(task)
            
            # Return immediately - no waiting
            return task_id
        
        except Exception as e:
            task.status = "error"
            error_msg = f"Failed to start background task: {str(e)}"
            task.error_log.append(f"{datetime.now()}: {error_msg}")
            self._log_error(error_msg)
            raise RuntimeError(error_msg)
    
    def _create_script_file(self, task_id: str, script_content: str, interval: int) -> str:
        """Create a script file for the monitoring task."""
        # Create logs directory for this task
        task_log_dir = self.log_directory / f"task_{task_id}"
        task_log_dir.mkdir(exist_ok=True)
        
        # Replace any placeholder task IDs in the script content with the actual task ID
        script_content = script_content.replace("PLACEHOLDER", task_id)
        
        # Create the wrapper script that handles logging and intervals
        wrapper_script = f"""#!/bin/bash

# Task: {task_id}
# Generated by AI Shell

TASK_ID="{task_id}"
INTERVAL={interval}
LOG_DIR="{task_log_dir}"
OUTPUT_LOG="$LOG_DIR/output.log"
ERROR_LOG="$LOG_DIR/error.log"

# Signal handler for graceful shutdown
cleanup() {{
    echo "$(date): Task $TASK_ID shutting down..." >> "$OUTPUT_LOG"
    exit 0
}}

trap cleanup SIGTERM SIGINT

echo "$(date): Task $TASK_ID started" >> "$OUTPUT_LOG"

# Main monitoring loop
while true; do
    # Execute the monitoring command
    {{
{self._indent_script(script_content, 8)}
    }} >> "$OUTPUT_LOG" 2>> "$ERROR_LOG"
    
    # Sleep for the specified interval
    sleep "$INTERVAL"
done
"""
        
        # Write the script to a temporary file
        script_file = tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.sh',
            prefix=f'ai_shell_task_{task_id}_',
            delete=False
        )
        
        script_file.write(wrapper_script)
        script_file.close()
        
        # Make the script executable
        os.chmod(script_file.name, 0o755)
        
        return script_file.name
    
    def _determine_command_success(self, command: str, return_code: int, output: str, error: str) -> bool:
        """Determine if a command succeeded based on context-aware exit code analysis."""
        
        # Commands that are considered successful even with non-zero exit codes
        command_lower = command.lower().strip()
        
        # Diff command: exit code 1 means files differ (expected behavior)
        if 'diff' in command_lower:
            # diff returns 0 (identical), 1 (different), 2 (error)
            if return_code in [0, 1]:
                return True
            elif return_code == 2:
                # Only consider it a failure if there's actual error output
                return not error.strip() or 'no such file' not in error.lower()
        
        # Grep command: exit code 1 means no matches found (not an error)
        if 'grep' in command_lower:
            # grep returns 0 (found), 1 (not found), 2 (error)
            if return_code in [0, 1]:
                return True
            elif return_code == 2:
                return not error.strip()
        
        # Find command: various non-zero codes can be acceptable
        if 'find' in command_lower:
            # find can return 1 for various non-error conditions
            if return_code in [0, 1]:
                return True
            # Check if error is about permissions (often acceptable)
            elif 'permission denied' in error.lower() and output.strip():
                return True
        
        # Test commands: exit codes are the result, not error indicators
        if command_lower.startswith('[') or command_lower.startswith('test'):
            # For test commands, any exit code is valid (0=true, 1=false)
            return True
        
        # Commands that commonly have acceptable non-zero exit codes
        acceptable_nonzero_commands = [
            'which', 'whereis',  # May return 1 if command not found
            'ping',              # May return 1 if host unreachable
            'curl', 'wget',      # May return various codes for different conditions
            'sort', 'uniq',      # May return 1 for various conditions
        ]
        
        for cmd in acceptable_nonzero_commands:
            if cmd in command_lower:
                # Accept return codes 0 and 1 for these commands
                if return_code in [0, 1]:
                    return True
                # If there's output but minimal error, likely successful
                elif output.strip() and not error.strip():
                    return True
        
        # For complex commands (loops, conditionals), check if there's meaningful output
        if self._is_complex_command(command):
            # If command produced output and no stderr, likely successful
            if output.strip() and not error.strip():
                return True
            # If no output but also no error, might be successful (e.g., no matches found)
            elif not output.strip() and not error.strip():
                return True
        
        # Default: only return code 0 is success
        return return_code == 0
    
    def _is_complex_command(self, command: str) -> bool:
        """Check if a command contains complex shell constructs that need script execution."""
        complex_patterns = [
            'for ', 'while ', 'if ', 'case ',  # Control structures
            ' do ', ' then ', ' else ',        # Control keywords
            '&&', '||',                        # Logical operators
            '$(', '`',                         # Command substitution
            '{', '}',                          # Brace expansion or blocks
            ';',                               # Command separator
            '|',                               # Pipes
            '>', '>>',                         # Redirections
            '\n'                               # Multi-line commands
        ]
        
        command_lower = command.lower()
        return any(pattern in command_lower for pattern in complex_patterns)
    
    def _indent_script(self, script: str, spaces: int) -> str:
        """Indent all lines of a script by the specified number of spaces."""
        indent = " " * spaces
        return "\n".join(indent + line for line in script.split("\n"))
    
    def _start_task_monitoring(self, task: BackgroundTask):
        """Start monitoring a background task's output."""
        def monitor():
            try:
                # Give the process a moment to start
                time.sleep(0.1)
                
                while task.process and task.process.poll() is None:
                    if self._shutdown_requested:
                        break
                    
                    # Read any available output from log files
                    try:
                        # Check if there's new output in the log files
                        task_log_dir = self.log_directory / f"task_{task.task_id}"
                        output_log = task_log_dir / "output.log"
                        error_log = task_log_dir / "error.log"
                        
                        # Read new lines from output log
                        if output_log.exists():
                            self._read_new_log_lines(output_log, task.output_log)
                        
                        # Read new lines from error log
                        if error_log.exists():
                            self._read_new_log_lines(error_log, task.error_log)
                        
                    except Exception as e:
                        self._log_error(f"Error monitoring task {task.task_id}: {str(e)}")
                    
                    # Check less frequently to reduce CPU usage
                    time.sleep(2)
                
                # Task has finished
                if task.process:
                    return_code = task.process.returncode
                    task.status = "stopped" if return_code == 0 else "error"
                    self._log_info(f"Task {task.task_id} finished with return code {return_code}")
                    if self.task_logging_enabled:
                        self._log_task_event(task.task_id, 'finished', f"Return code: {return_code}")
                        
            except Exception as e:
                self._log_error(f"Task monitoring thread error for {task.task_id}: {str(e)}")
                task.status = "error"
        
        # Start monitoring in a separate daemon thread (non-blocking)
        monitor_thread = threading.Thread(
            target=monitor, 
            daemon=True, 
            name=f"TaskMonitor-{task.task_id}"
        )
        monitor_thread.start()
        
        # Store thread reference for debugging
        task.monitor_thread = monitor_thread
    
    def _read_new_log_lines(self, log_file: Path, log_list: List[str]):
        """Read new lines from a log file and add them to the log list."""
        try:
            if log_file.exists():
                with open(log_file, 'r') as f:
                    lines = f.readlines()
                    
                # Add only new lines
                new_lines = lines[len(log_list):]
                for line in new_lines:
                    log_list.append(line.strip())
                    
                    # Limit log size
                    if len(log_list) > self.max_log_lines:
                        log_list.pop(0)
        
        except Exception as e:
            self._log_error(f"Error reading log file {log_file}: {str(e)}")
    
    def stop_task(self, task_id: str) -> bool:
        """Stop a background task."""
        if task_id not in self.background_tasks:
            print(f"{Fore.RED}Task {task_id} not found.{Style.RESET_ALL}")
            return False
        
        task = self.background_tasks[task_id]
        
        try:
            self._log_task_event(task_id, 'stopping', 'Task stop requested')
            
            if task.process and task.process.poll() is None:
                pid = task.process.pid
                
                # For nohup processes, we need to kill the entire process group
                try:
                    # First try to kill the process group (since we used start_new_session=True)
                    import signal
                    os.killpg(pid, signal.SIGTERM)
                    self._log_task_event(task_id, 'signal', f'SIGTERM sent to process group {pid}')
                    
                    # Wait for graceful shutdown
                    try:
                        task.process.wait(timeout=5)
                        self._log_task_event(task_id, 'stopped', 'Graceful shutdown completed')
                    except subprocess.TimeoutExpired:
                        # Force kill the process group
                        try:
                            os.killpg(pid, signal.SIGKILL)
                            self._log_task_event(task_id, 'killed', f'SIGKILL sent to process group {pid}')
                        except ProcessLookupError:
                            # Process already dead
                            pass
                        task.process.wait()
                        self._log_task_event(task_id, 'killed', 'Forced termination completed')
                        
                except (ProcessLookupError, PermissionError):
                    # Fallback to regular process termination
                    try:
                        task.process.terminate()
                        task.process.wait(timeout=3)
                        self._log_task_event(task_id, 'stopped', 'Fallback termination completed')
                    except subprocess.TimeoutExpired:
                        task.process.kill()
                        task.process.wait()
                        self._log_task_event(task_id, 'killed', 'Fallback kill completed')
            
            task.status = "stopped"
            
            # Clean up script file
            if task.script_file and os.path.exists(task.script_file):
                try:
                    os.unlink(task.script_file)
                    self._log_task_event(task_id, 'cleanup', 'Script file removed')
                except OSError as e:
                    self._log_task_event(task_id, 'cleanup_error', f'Failed to remove script file: {e}')
            
            # Final log entry
            self._log_task_event(task_id, 'completed', f'Task stopped after {datetime.now() - task.start_time}')
            
            # Remove from active tasks
            del self.background_tasks[task_id]
            
            print(f"{Fore.GREEN}Task {task_id} stopped successfully.{Style.RESET_ALL}")
            self._log_info(f"Stopped task {task_id}: {task.description}")
            
            return True
        
        except Exception as e:
            error_msg = f"Error stopping task {task_id}: {str(e)}"
            print(f"{Fore.RED}{error_msg}{Style.RESET_ALL}")
            self._log_error(error_msg)
            self._log_task_event(task_id, 'error', error_msg)
            return False
    
    def show_tasks(self):
        """Display information about running background tasks."""
        if not self.background_tasks:
            print(f"{Fore.YELLOW}No background tasks running.{Style.RESET_ALL}")
            return
        
        print(f"{Fore.CYAN}Background Tasks:{Style.RESET_ALL}")
        print(f"{'ID':<8} {'Status':<8} {'Description':<40} {'Runtime':<10} {'Output':<8}")
        print("-" * 80)
        
        for task_id, task in self.background_tasks.items():
            runtime = str(datetime.now() - task.start_time).split('.')[0]
            output_lines = len(task.output_log)
            
            # Color-code status
            status_color = Fore.GREEN if task.status == "running" else Fore.RED
            
            print(f"{task_id:<8} {status_color}{task.status:<8}{Style.RESET_ALL} "
                  f"{task.description[:40]:<40} {runtime:<10} {output_lines:<8}")
    
    def get_task_output(self, task_id: str, lines: int = 20) -> Optional[str]:
        """Get recent output from a background task."""
        if task_id not in self.background_tasks:
            return None
        
        task = self.background_tasks[task_id]
        recent_output = task.output_log[-lines:] if task.output_log else []
        
        return "\n".join(recent_output)
    
    def get_task_errors(self, task_id: str, lines: int = 20) -> Optional[str]:
        """Get recent errors from a background task."""
        if task_id not in self.background_tasks:
            return None
        
        task = self.background_tasks[task_id]
        recent_errors = task.error_log[-lines:] if task.error_log else []
        
        return "\n".join(recent_errors)
    
    def _log_command(self, command: str):
        """Log command execution."""
        log_entry = f"{datetime.now()}: EXEC: {command}"
        self._write_to_main_log(log_entry)
    
    def _log_command_result(self, command: str, result: Dict[str, Any]):
        """Log command execution result."""
        status = "SUCCESS" if result["success"] else "FAILED"
        log_entry = f"{datetime.now()}: {status}: {command} (return code: {result['return_code']})"
        self._write_to_main_log(log_entry)
    
    def _log_info(self, message: str):
        """Log an info message."""
        log_entry = f"{datetime.now()}: INFO: {message}"
        self._write_to_main_log(log_entry)
    
    def _log_error(self, message: str):
        """Log an error message."""
        log_entry = f"{datetime.now()}: ERROR: {message}"
        self._write_to_main_log(log_entry)
    
    def _write_to_main_log(self, entry: str):
        """Write an entry to the main log file."""
        try:
            main_log = self.log_directory / "ai_shell.log"
            with open(main_log, 'a', encoding='utf-8') as f:
                f.write(entry + "\n")
            
            # Rotate log if it gets too large
            self._rotate_log_if_needed(main_log)
        except Exception:
            # Silently fail if we can't write to log
            pass
    
    def _rotate_log_if_needed(self, log_file: Path):
        """Rotate log file if it exceeds maximum size."""
        try:
            if log_file.exists() and log_file.stat().st_size > self.max_log_file_size:
                # Rotate existing log files
                for i in range(self.max_log_files - 1, 0, -1):
                    old_log = log_file.with_suffix(f".log.{i}")
                    new_log = log_file.with_suffix(f".log.{i + 1}")
                    if old_log.exists():
                        if new_log.exists():
                            new_log.unlink()
                        old_log.rename(new_log)
                
                # Move current log to .1
                rotated_log = log_file.with_suffix(".log.1")
                if rotated_log.exists():
                    rotated_log.unlink()
                log_file.rename(rotated_log)
        except Exception as e:
            self._log_error(f"Failed to rotate log file {log_file}: {str(e)}")
    
    def _setup_task_logging(self, task_id: str) -> Dict[str, Path]:
        """Setup logging files for a specific task."""
        task_log_dir = self.log_directory / f"task_{task_id}"
        task_log_dir.mkdir(exist_ok=True)
        
        log_files = {
            'output': task_log_dir / "output.log",
            'error': task_log_dir / "error.log", 
            'status': task_log_dir / "status.log",
            'script': task_log_dir / "script.sh"
        }
        
        # Initialize log files with headers
        timestamp = datetime.now().isoformat()
        
        for log_type, log_file in log_files.items():
            if log_type != 'script':  # Don't add header to script file
                try:
                    with open(log_file, 'a', encoding='utf-8') as f:
                        f.write(f"\n=== Task {task_id} {log_type.upper()} Log - Started {timestamp} ===\n")
                except Exception:
                    pass
        
        return log_files
    
    def _log_task_event(self, task_id: str, event_type: str, message: str):
        """Log a task event to the task's status log."""
        if not self.task_logging_enabled:
            return
            
        try:
            task_log_dir = self.log_directory / f"task_{task_id}"
            status_log = task_log_dir / "status.log"
            
            timestamp = datetime.now().isoformat()
            log_entry = f"[{timestamp}] {event_type.upper()}: {message}\n"
            
            with open(status_log, 'a', encoding='utf-8') as f:
                f.write(log_entry)
                
        except Exception as e:
            self._log_error(f"Failed to log task event for {task_id}: {str(e)}")
    
    def _cleanup_orphaned_tasks(self):
        """Clean up task directories that don't have running processes."""
        try:
            # Look for task directories in the log directory
            for task_dir in self.log_directory.glob("task_*"):
                if task_dir.is_dir():
                    task_id = task_dir.name.replace("task_", "")
                    
                    # Check if this task is in our active tasks
                    if task_id not in self.background_tasks:
                        # Check if there's a script file for this task that might still be running
                        script_pattern = f"ai_shell_task_{task_id}_*.sh"
                        temp_scripts = list(Path("/tmp").glob(script_pattern))
                        
                        # If no temp script files and not in active tasks, it's orphaned
                        if not temp_scripts:
                            self._log_info(f"Cleaning up orphaned task directory: {task_id}")
                            # We could remove the directory, but let's just log it for now
                            # shutil.rmtree(task_dir)  # Uncomment if you want to auto-remove
                            
        except Exception as e:
            self._log_error(f"Error cleaning up orphaned tasks: {str(e)}")
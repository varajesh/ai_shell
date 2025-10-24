"""
LLM Handler module for AI Shell.

This module handles all interactions with Language Learning Models using LangChain,
including prompt templates, command conversion, and safety analysis.
"""

from typing import Dict, Optional, List
import json
import re
from langchain_core.language_models.llms import LLM
from langchain_core.prompts import PromptTemplate
from langchain_core.messages import HumanMessage, SystemMessage
from gen_ai_hub.proxy.core.proxy_clients import get_proxy_client
from gen_ai_hub.proxy import set_proxy_version

from config_manager import ConfigManager


class LLMHandler:
    """Handles LLM interactions for command conversion and analysis."""
    
    def __init__(self, config: ConfigManager):
        """Initialize the LLM handler with configuration."""
        self.config = config
        self.llm = self._initialize_llm()
        self._setup_prompts()
    
    def _initialize_llm(self) -> LLM:
        """Initialize the LLM based on configuration."""
        llm_config = self.config.get_llm_config()
        
        provider = llm_config.get('provider', 'openai').lower()
        model = llm_config.get('model', 'gpt-3.5-turbo')
        api_key = llm_config.get('api_key')
        
        if provider != 'aicore' and not api_key:
            raise ValueError(f"API key not found for {provider}. Please check your configuration.")
        
        if provider == 'openai':
            from langchain_openai import OpenAI, ChatOpenAI
            if 'gpt-3.5-turbo' in model or 'gpt-4' in model:
                return ChatOpenAI(
                    model=model,
                    openai_api_key=api_key,
                    temperature=llm_config.get('temperature', 0.1),
                    max_tokens=llm_config.get('max_tokens', 1000)
                )
            else:
                return OpenAI(
                    model=model,
                    openai_api_key=api_key,
                    temperature=llm_config.get('temperature', 0.1),
                    max_tokens=llm_config.get('max_tokens', 1000)
                )
        
        elif provider == 'anthropic':
            from langchain_anthropic import ChatAnthropic, Anthropic
            if 'claude' in model:
                return ChatAnthropic(
                    model=model,
                    anthropic_api_key=api_key,
                    temperature=llm_config.get('temperature', 0.1),
                    max_tokens=llm_config.get('max_tokens', 1000)
                )
            else:
                return Anthropic(
                    model=model,
                    anthropic_api_key=api_key,
                    temperature=llm_config.get('temperature', 0.1),
                    max_tokens=llm_config.get('max_tokens', 1000)
                )
        elif provider == 'aicore':
            from gen_ai_hub.proxy.langchain.openai import ChatOpenAI
            set_proxy_version('gen-ai-hub')
            proxy_client = get_proxy_client()
            chat_llm = ChatOpenAI(proxy_model_name=model, proxy_client=proxy_client)
            return chat_llm
        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")
    
    def _setup_prompts(self):
        """Setup prompt templates for different tasks."""
        
        # Natural language to bash conversion prompt
        self.nl_to_bash_prompt = PromptTemplate(
            input_variables=["user_input", "current_dir", "os_type"],
            template="""You are an expert Unix/Linux command line assistant. Convert the following natural language request into a precise bash command.

Context:
- Current directory: {current_dir}
- Operating System: {os_type}
- User request: {user_input}

Rules:
1. Generate only valid bash commands that work on {os_type}
2. Use appropriate command options and flags
3. Handle file paths and permissions correctly
4. For complex operations, chain commands with pipes or && as needed
5. Ensure commands are safe and do what the user asks
6. If the request is ambiguous, choose the most reasonable interpretation
7. Output results to the console by default (standard output)
8. Only redirect to files if explicitly requested by the user
9. Avoid writing to system directories like /tmp, /var/log unless specifically requested
10. For shell loops and conditional statements, ensure they are properly formatted for bash execution
11. Use explicit bash syntax for complex operations (e.g., for loops, conditionals)
12. Test file existence with proper error handling in loops

Examples:
- "show all files one day old" → find . -type f -mtime -1 -ls
- "remove image files in current directory" → rm *.jpg *.png *.gif *.jpeg 2>/dev/null || true
- "list python processes that run on GPU" → ps aux | grep python | grep -E "(cuda|gpu|nvidia)"
- "save process list to file" → ps aux > process_list.txt
- "compare files with another directory" → for file in *; do if [ -f "other_dir/$file" ]; then diff -q "$file" "other_dir/$file"; fi; done
- "check disk space" → df -h

User request: {user_input}

Generate only the bash command, no explanations:"""
        )
        
        # Safety analysis prompt
        self.safety_prompt = PromptTemplate(
            input_variables=["command"],
            template="""Analyze the following bash command for potential safety risks.

Command: {command}

Evaluate if this command could:
1. Delete important files or directories (especially with rm, rmdir)
2. Modify system files or permissions
3. Install or remove software
4. Access sensitive information
5. Consume excessive system resources
6. Make irreversible changes
7. Affect network security

IMPORTANT: Respond ONLY with a valid JSON object. Do not include any other text.

For common safe commands like ls, find, grep, cat, head, tail, ps, etc., mark as not dangerous.

Example response format:
{{
  "is_dangerous": false,
  "risk_level": "low",
  "reason": "Safe read-only command",
  "suggestions": ""
}}

JSON Response:"""
        )
        
        # Background task detection prompt
        self.background_task_prompt = PromptTemplate(
            input_variables=["user_input"],
            template="""Determine if the following user request requires a background monitoring task.

User request: {user_input}

Background tasks are needed for:
- Continuous monitoring (CPU, memory, disk usage)
- File/directory watching
- Process monitoring
- Periodic checks and notifications
- Long-running observations

Regular tasks are:
- One-time file operations
- Single command executions
- Immediate information retrieval

Respond with only "true" or "false"."""
        )
        
        # Monitoring script generation prompt
        self.monitoring_script_prompt = PromptTemplate(
            input_variables=["user_input", "base_command", "log_directory", "task_id"],
            template="""Generate a bash script for continuous monitoring based on the user request.

User request: {user_input}
Base command: {base_command}
Log directory: {log_directory}
Task ID: {task_id}

Create a bash script that:
1. Runs in a loop with appropriate intervals
2. Executes the monitoring command
3. Checks conditions and sends notifications
4. Handles errors gracefully
5. Can be stopped with SIGTERM
6. Logs important events
7. IMPORTANT: All output files must be written to {log_directory}/task_{task_id}/ directory
8. Use absolute paths for all log files within the log directory

The script should be production-ready and include:
- Proper signal handling
- Error checking
- Logging with timestamps to {log_directory}/task_{task_id}/output.log
- Error logging to {log_directory}/task_{task_id}/error.log
- Configuration variables at the top
- All temporary files and outputs within the designated log directory

IMPORTANT: Do not write files to /tmp, /var/log, or any system directories. Use only {log_directory}/task_{task_id}/ for all outputs.

Generate only the bash script content:"""
        )
    
    def convert_nl_to_bash(self, user_input: str) -> Optional[str]:
        """Convert natural language input to bash command."""
        try:
            import os
            import platform
            
            current_dir = os.getcwd()
            os_type = platform.system()
            
            # Check if this is a chat model or completion model
            if hasattr(self.llm, 'invoke') and 'Chat' in self.llm.__class__.__name__:
                # Use chat interface
                messages = [
                    SystemMessage(content="You are an expert Unix/Linux command line assistant. Generate commands that output to console by default."),
                    HumanMessage(content=self.nl_to_bash_prompt.format(
                        user_input=user_input,
                        current_dir=current_dir,
                        os_type=os_type
                    ))
                ]
                response = self.llm.invoke(messages)
                bash_command = response.content.strip()
            else:
                # Use completion interface
                prompt = self.nl_to_bash_prompt.format(
                    user_input=user_input,
                    current_dir=current_dir,
                    os_type=os_type
                )
                response = self.llm.invoke(prompt)
                if hasattr(response, 'content'):
                    bash_command = response.content.strip()
                else:
                    bash_command = str(response).strip()
            
            # Clean up the response
            bash_command = self._clean_bash_command(bash_command)
            
            return bash_command if bash_command else None
        
        except Exception as e:
            print(f"Error converting NL to bash: {str(e)}")
            return None
    
    def analyze_command_safety(self, command: str) -> Dict:
        """Analyze the safety of a bash command."""
        try:
            # Check if this is a chat model or completion model
            if hasattr(self.llm, 'invoke') and 'Chat' in self.llm.__class__.__name__:
                messages = [
                    SystemMessage(content="You are a cybersecurity expert analyzing bash commands for safety."),
                    HumanMessage(content=self.safety_prompt.format(command=command))
                ]
                response = self.llm.invoke(messages)
                safety_analysis = response.content.strip()
            else:
                prompt = self.safety_prompt.format(command=command)
                response = self.llm.invoke(prompt)
                if hasattr(response, 'content'):
                    safety_analysis = response.content.strip()
                else:
                    safety_analysis = str(response).strip()
            
            # Try to parse JSON response
            try:
                return json.loads(safety_analysis)
            except json.JSONDecodeError:
                # Try to extract key information from text response
                analysis_text = safety_analysis.lower()
                
                # Look for safety indicators in the text
                if any(word in analysis_text for word in ['safe', 'harmless', 'low risk', 'no danger']):
                    return {
                        "is_dangerous": False,
                        "risk_level": "low",
                        "reason": "LLM analysis indicates safe command (non-JSON response)",
                        "suggestions": ""
                    }
                elif any(word in analysis_text for word in ['dangerous', 'harmful', 'risky', 'destructive']):
                    return {
                        "is_dangerous": True,
                        "risk_level": "medium",
                        "reason": "LLM analysis indicates potential risks (non-JSON response)",
                        "suggestions": "Please review the command manually"
                    }
                else:
                    # Conservative fallback only for unknown responses
                    return {
                        "is_dangerous": False,
                        "risk_level": "low", 
                        "reason": "Unable to parse LLM safety analysis",
                        "suggestions": "Command appears to be a standard operation"
                    }
        
        except Exception as e:
            print(f"Error analyzing command safety: {str(e)}")
            return {
                "is_dangerous": True,
                "risk_level": "high",
                "reason": f"Error during analysis: {str(e)}",
                "suggestions": "Please review the command manually"
            }
    
    def is_background_task(self, user_input: str) -> bool:
        """Determine if the user input requires a background task."""
        try:
            # Check if this is a chat model or completion model
            if hasattr(self.llm, 'invoke') and 'Chat' in self.llm.__class__.__name__:
                messages = [
                    SystemMessage(content="You are an assistant that determines task types."),
                    HumanMessage(content=self.background_task_prompt.format(user_input=user_input))
                ]
                response = self.llm.invoke(messages)
                result = response.content.strip()
            else:
                prompt = self.background_task_prompt.format(user_input=user_input)
                response = self.llm.invoke(prompt)
                if hasattr(response, 'content'):
                    result = response.content.strip()
                else:
                    result = str(response).strip()
            
            return result.lower() == "true"
        
        except Exception as e:
            print(f"Error determining task type: {str(e)}")
            return False
    
    def generate_monitoring_script(self, user_input: str, base_command: str, log_directory: str = "logs", task_id: str = "unknown") -> Optional[str]:
        """Generate a monitoring script for background tasks."""
        try:
            # Check if this is a chat model or completion model
            if hasattr(self.llm, 'invoke') and 'Chat' in self.llm.__class__.__name__:
                messages = [
                    SystemMessage(content="You are an expert bash script developer specializing in monitoring scripts. Always ensure all output files are written to the specified log directory."),
                    HumanMessage(content=self.monitoring_script_prompt.format(
                        user_input=user_input,
                        base_command=base_command,
                        log_directory=log_directory,
                        task_id=task_id
                    ))
                ]
                response = self.llm.invoke(messages)
                script = response.content.strip()
            else:
                prompt = self.monitoring_script_prompt.format(
                    user_input=user_input,
                    base_command=base_command,
                    log_directory=log_directory,
                    task_id=task_id
                )
                response = self.llm.invoke(prompt)
                if hasattr(response, 'content'):
                    script = response.content.strip()
                else:
                    script = str(response).strip()
            
            return script if script else None
        
        except Exception as e:
            print(f"Error generating monitoring script: {str(e)}")
            return None
    
    def _clean_bash_command(self, command: str) -> str:
        """Clean and validate the generated bash command."""
        # Remove any markdown formatting
        command = re.sub(r'```bash\n?', '', command)
        command = re.sub(r'```\n?', '', command)
        
        # Remove extra whitespace and newlines
        command = command.strip()
        
        # Remove any explanatory text that might come after the command
        lines = command.split('\n')
        if lines:
            # Take the first non-empty line that looks like a command
            for line in lines:
                line = line.strip()
                if line and not line.startswith('#') and not line.startswith('//'):
                    return line
        
        return command
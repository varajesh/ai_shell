# AI Shell
# Most of the code built by AI (with agent mode in Co-pilot), including this README :) 

A powerful natural language command line interface utility that converts your plain English requests into bash commands using AI/LLM technology.

## Features

🤖 **Natural Language Processing**: Convert plain English to bash commands using state-of-the-art LLMs  
🛡️ **Safety First**: Built-in safety checks and warnings for potentially harmful commands  
📊 **Background Monitoring**: Create monitoring tasks that run in the background  
⚙️ **Configurable**: Support for multiple LLM providers (OpenAI, Anthropic)  
🎨 **Rich Interface**: Colorful, interactive command line interface with history  
🔄 **Task Management**: Start, stop, and monitor background processes  

## Installation

### Prerequisites

- Python 3.8 or higher
- An API key for OpenAI or Anthropic

### Install from source

```bash
git clone <repository-url>
cd ai_shell
pip install -r requirements.txt
```

### Install as a package

```bash
pip install -e .
```

## Configuration

1. Copy the example configuration:
```bash
cp config.yaml config.yaml
```

2. Edit `config.yaml` and add your API key:
```yaml
llm:
  provider: openai  # or 'anthropic'
  model: gpt-3.5-turbo
  api_key: "your-api-key-here"
```

Alternatively, set environment variables:
```bash
export OPENAI_API_KEY="your-openai-key"
# or
export ANTHROPIC_API_KEY="your-anthropic-key"
```

## Usage

### Basic Usage

Start the AI Shell:
```bash
python ai_shell.py
```

or if installed as a package:
```bash
ai-shell
```

### Example Commands

```
ai-shell> show all files one day old
Generated command: find . -type f -mtime -1 -ls
Execute this command? (yes/no): yes

ai-shell> remove image files in current directory  
Generated command: rm *.jpg *.png *.gif *.jpeg 2>/dev/null || true
⚠️  WARNING: This command may be harmful!
Reason: High-risk command 'rm' detected
Do you still want to proceed? (yes/no): no

ai-shell> list python processes that run on GPU
Generated command: ps aux | grep python | grep -E "(cuda|gpu|nvidia)"
Execute this command? (yes/no): yes

ai-shell> monitor cpu usage of all python processes and notify if exceeds 80%
🔄 This appears to be a monitoring task.
Generated monitoring script:
#!/bin/bash
# Monitor Python processes CPU usage
while true; do
    ps aux | grep python | awk '{if($3>80) print $0}'
    sleep 5
done
Start this monitoring task? (yes/no): yes
✅ Background task started with ID: abc12345
```

### Special Commands

- `help` - Show help information
- `tasks` - List running background tasks  
- `kill-task <id>` - Stop a background task
- `config` - Show current configuration
- `reload-config` - Reload configuration file
- `exit` or `quit` - Exit AI Shell

### Background Monitoring Tasks

AI Shell can detect when you want to create monitoring tasks and will automatically generate appropriate scripts:

**Examples:**
- "monitor folder 'test' and notify if total size exceeds 5GB"
- "watch for new log files in /var/log"
- "alert when disk usage exceeds 90%"
- "monitor memory usage of docker containers"

## Configuration Options

### LLM Settings
```yaml
llm:
  provider: openai          # 'openai' or 'anthropic'
  model: gpt-3.5-turbo     # Model name
  api_key: ""              # Your API key
  temperature: 0.1         # Creativity level (0.0-1.0)
  max_tokens: 1000         # Maximum response length
  timeout: 30              # Request timeout in seconds
```

### Safety Settings
```yaml
safety:
  always_confirm: true                           # Always ask before running commands
  dangerous_commands_require_explicit_confirm: true  # Extra confirmation for risky commands
  blocked_commands:                              # Commands that are completely blocked
    - "rm -rf /"
    - "chmod -R 777 /"
```

### Monitoring Settings
```yaml
monitoring:
  default_interval: 5        # Default monitoring interval in seconds
  max_background_tasks: 10   # Maximum concurrent background tasks
  log_directory: logs/       # Directory for log files
  notifications:
    enabled: true
    method: console          # console, email, webhook
```

## Safety Features

### Built-in Protections

1. **Pattern Detection**: Identifies dangerous command patterns
2. **LLM Analysis**: Uses AI to analyze potential risks
3. **Confirmation Prompts**: Always asks before executing commands
4. **Blocked Commands**: Configurable list of forbidden commands
5. **Critical Path Protection**: Extra warnings for system directories

### Risk Levels

- 🟢 **Low**: Safe commands that pose minimal risk
- 🟡 **Medium**: Commands that could affect files/settings
- 🔴 **High**: Commands that could cause significant damage
- ⚫ **Critical**: Commands that could destroy the system

## Logging

AI Shell maintains logs in the `logs/` directory:

- `ai_shell.log` - Main application log
- `task_<id>/` - Individual background task logs
  - `output.log` - Task output
  - `error.log` - Task errors

## Troubleshooting

### Common Issues

1. **API Key Errors**
   ```
   API key not found for openai. Please check your configuration.
   ```
   Solution: Add your API key to `config.yaml` or set the environment variable.

2. **Permission Denied**
   ```
   Permission denied: /usr/bin/some-command
   ```
   Solution: Some commands may require `sudo`. AI Shell will ask for confirmation.

3. **Command Not Found**
   ```
   Command 'some-tool' not found
   ```
   Solution: Ensure the required tools are installed on your system.

### Debug Mode

Enable debug logging by setting:
```bash
export AI_SHELL_DEBUG=1
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request


## Disclaimer

⚠️ **Important Safety Notice**

AI Shell is a powerful tool that can execute system commands. While it includes safety features:

- Always review generated commands before execution
- Test in a safe environment first
- Keep backups of important data
- Use with caution on production systems
- The AI may occasionally misinterpret requests



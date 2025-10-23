"""
Configuration Manager for AI Shell.

This module handles loading and managing configuration settings for the AI Shell,
including LLM settings, API keys, and other application preferences.
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
import colorama
from colorama import Fore, Style


class ConfigManager:
    """Manages configuration settings for AI Shell."""
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize the configuration manager."""
        # Initialize colorama for cross-platform color support
        colorama.init(autoreset=True, convert=True)
        
        self.config_path = config_path or self._find_config_file()
        self.config = {}
        self.load_config()
    
    def _find_config_file(self) -> str:
        """Find the configuration file in standard locations."""
        # Priority order for config file locations
        search_paths = [
            "config.yaml",  # Current directory
            "config.yml",   # Current directory (alternative extension)
            str(Path.home() / ".ai_shell" / "config.yaml"),  # User home
            str(Path.home() / ".ai_shell_config.yaml"),      # User home (alternative)
        ]
        
        for path in search_paths:
            if os.path.exists(path):
                return path
        
        # If no config file found, create a default one
        default_path = "config.yaml"
        self._create_default_config(default_path)
        return default_path
    
    def _create_default_config(self, path: str):
        """Create a default configuration file."""
        default_config = {
            'llm': {
                'provider': 'openai',  # or 'anthropic'
                'model': 'gpt-3.5-turbo',
                'api_key': '',  # User needs to fill this
                'temperature': 0.1,
                'max_tokens': 1000,
                'timeout': 30
            },
            'safety': {
                'always_confirm': True,
                'dangerous_commands_require_explicit_confirm': True,
                'blocked_commands': [
                    'rm -rf /',
                    'chmod -R 777 /',
                    'dd if=/dev/zero of=/dev/sda'
                ]
            },
            'monitoring': {
                'default_interval': 5,  # seconds
                'max_background_tasks': 10,
                'log_directory': 'logs/',
                'notifications': {
                    'enabled': True,
                    'method': 'console'  # or 'email', 'webhook'
                }
            },
            'shell': {
                'prompt_style': 'ai-shell',
                'history_size': 1000,
                'auto_suggest': True,
                'colored_output': True
            }
        }
        
        try:
            with open(path, 'w') as f:
                yaml.dump(default_config, f, default_flow_style=False, indent=2)
            
            print(f"{Fore.YELLOW}Created default configuration file: {path}")
            print(f"Please edit it to add your LLM API key.{Style.RESET_ALL}")
        
        except Exception as e:
            print(f"{Fore.RED}Error creating default config: {str(e)}{Style.RESET_ALL}")
    
    def load_config(self):
        """Load configuration from file."""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as f:
                    self.config = yaml.safe_load(f) or {}
            else:
                self.config = {}
            
            # Validate and set defaults
            self._validate_config()
            
        except Exception as e:
            print(f"{Fore.RED}Error loading config: {str(e)}{Style.RESET_ALL}")
            self.config = self._get_fallback_config()
    
    def _validate_config(self):
        """Validate and set default values for configuration."""
        # Ensure required sections exist
        if 'llm' not in self.config:
            self.config['llm'] = {}
        
        if 'safety' not in self.config:
            self.config['safety'] = {}
        
        if 'monitoring' not in self.config:
            self.config['monitoring'] = {}
        
        if 'shell' not in self.config:
            self.config['shell'] = {}
        
        # Set defaults for LLM configuration
        llm_defaults = {
            'provider': 'openai',
            'model': 'gpt-3.5-turbo',
            'temperature': 0.1,
            'max_tokens': 1000,
            'timeout': 30
        }
        
        for key, default_value in llm_defaults.items():
            if key not in self.config['llm']:
                self.config['llm'][key] = default_value
        
        # Check for API key in environment if not in config
        if not self.config['llm'].get('api_key'):
            provider = self.config['llm']['provider'].lower()
            if provider == 'openai':
                self.config['llm']['api_key'] = os.getenv('OPENAI_API_KEY', '')
            elif provider == 'anthropic':
                self.config['llm']['api_key'] = os.getenv('ANTHROPIC_API_KEY', '')
        
        # Set defaults for other sections
        safety_defaults = {
            'always_confirm': True,
            'dangerous_commands_require_explicit_confirm': True,
            'blocked_commands': []
        }
        
        for key, default_value in safety_defaults.items():
            if key not in self.config['safety']:
                self.config['safety'][key] = default_value
        
        monitoring_defaults = {
            'default_interval': 5,
            'max_background_tasks': 10,
            'log_directory': 'logs/',
            'notifications': {'enabled': True, 'method': 'console'}
        }
        
        for key, default_value in monitoring_defaults.items():
            if key not in self.config['monitoring']:
                self.config['monitoring'][key] = default_value
        
        shell_defaults = {
            'prompt_style': 'ai-shell',
            'history_size': 1000,
            'auto_suggest': True,
            'colored_output': True
        }
        
        for key, default_value in shell_defaults.items():
            if key not in self.config['shell']:
                self.config['shell'][key] = default_value
    
    def _get_fallback_config(self) -> Dict[str, Any]:
        """Get a fallback configuration if loading fails."""
        return {
            'llm': {
                'provider': 'openai',
                'model': 'gpt-3.5-turbo',
                'api_key': os.getenv('OPENAI_API_KEY', ''),
                'temperature': 0.1,
                'max_tokens': 1000,
                'timeout': 30
            },
            'safety': {
                'always_confirm': True,
                'dangerous_commands_require_explicit_confirm': True,
                'blocked_commands': []
            },
            'monitoring': {
                'default_interval': 5,
                'max_background_tasks': 10,
                'log_directory': 'logs/',
                'notifications': {'enabled': True, 'method': 'console'}
            },
            'shell': {
                'prompt_style': 'ai-shell',
                'history_size': 1000,
                'auto_suggest': True,
                'colored_output': True
            }
        }
    
    def get_llm_config(self) -> Dict[str, Any]:
        """Get LLM configuration."""
        return self.config.get('llm', {})
    
    def get_safety_config(self) -> Dict[str, Any]:
        """Get safety configuration."""
        return self.config.get('safety', {})
    
    def get_monitoring_config(self) -> Dict[str, Any]:
        """Get monitoring configuration."""
        return self.config.get('monitoring', {})
    
    def get_shell_config(self) -> Dict[str, Any]:
        """Get shell configuration."""
        return self.config.get('shell', {})
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value by key."""
        keys = key.split('.')
        value = self.config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def set(self, key: str, value: Any):
        """Set a configuration value by key."""
        keys = key.split('.')
        config = self.config
        
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        
        config[keys[-1]] = value
    
    def save_config(self):
        """Save the current configuration to file."""
        try:
            # Ensure the directory exists
            os.makedirs(os.path.dirname(self.config_path) or '.', exist_ok=True)
            
            with open(self.config_path, 'w') as f:
                yaml.dump(self.config, f, default_flow_style=False, indent=2)
            
            print(f"{Fore.GREEN}Configuration saved to {self.config_path}{Style.RESET_ALL}")
        
        except Exception as e:
            print(f"{Fore.RED}Error saving config: {str(e)}{Style.RESET_ALL}")
    
    def reload(self):
        """Reload configuration from file."""
        self.load_config()
    
    def show_config(self):
        """Display the current configuration (masking sensitive data)."""
        config_copy = self._mask_sensitive_data(self.config.copy())
        
        print(f"{Fore.CYAN}Current Configuration:{Style.RESET_ALL}")
        print(f"{Fore.WHITE}Config file: {self.config_path}{Style.RESET_ALL}")
        print()
        
        self._print_config_section(config_copy, "")
    
    def _mask_sensitive_data(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Mask sensitive data in configuration for display."""
        import copy
        masked_config = copy.deepcopy(config)
        
        # Mask API keys
        if 'llm' in masked_config and 'api_key' in masked_config['llm']:
            api_key = masked_config['llm']['api_key']
            if api_key:
                masked_config['llm']['api_key'] = api_key[:8] + '...' if len(api_key) > 8 else '***'
        
        return masked_config
    
    def _print_config_section(self, section: Any, prefix: str, indent: int = 0):
        """Recursively print configuration sections."""
        indent_str = "  " * indent
        
        if isinstance(section, dict):
            for key, value in section.items():
                if isinstance(value, dict):
                    print(f"{indent_str}{Fore.YELLOW}{key}:{Style.RESET_ALL}")
                    self._print_config_section(value, f"{prefix}.{key}" if prefix else key, indent + 1)
                else:
                    print(f"{indent_str}{Fore.GREEN}{key}:{Style.RESET_ALL} {value}")
        elif isinstance(section, list):
            for i, item in enumerate(section):
                print(f"{indent_str}{Fore.BLUE}[{i}]:{Style.RESET_ALL} {item}")
        else:
            print(f"{indent_str}{section}")
    
    def validate_llm_config(self) -> bool:
        """Validate that LLM configuration is complete and valid."""
        llm_config = self.get_llm_config()
        
        required_fields = ['provider', 'model', 'api_key']
        for field in required_fields:
            if not llm_config.get(field):
                print(f"{Fore.RED}Missing required LLM configuration: {field}{Style.RESET_ALL}")
                return False
        
        # Validate provider
        supported_providers = ['openai', 'anthropic']
        if llm_config['provider'].lower() not in supported_providers:
            print(f"{Fore.RED}Unsupported LLM provider: {llm_config['provider']}")
            print(f"Supported providers: {', '.join(supported_providers)}{Style.RESET_ALL}")
            return False
        
        return True
    
    def validate_and_create_log_directory(self) -> bool:
        """Validate and create the logging directory. Returns False if creation fails."""
        log_dir = self.get('monitoring.log_directory', 'logs/')
        
        try:
            # Convert to Path object and resolve
            log_path = Path(log_dir).resolve()
            
            # Create directory if it doesn't exist
            log_path.mkdir(parents=True, exist_ok=True)
            
            # Test write permissions
            test_file = log_path / '.ai_shell_test'
            try:
                test_file.write_text('test')
                test_file.unlink()  # Remove test file
            except Exception as e:
                print(f"{Fore.RED}Cannot write to log directory {log_path}: {str(e)}{Style.RESET_ALL}")
                return False
            
            print(f"{Fore.GREEN}Log directory initialized: {log_path}{Style.RESET_ALL}")
            return True
            
        except Exception as e:
            print(f"{Fore.RED}Failed to create log directory '{log_dir}': {str(e)}{Style.RESET_ALL}")
            return False
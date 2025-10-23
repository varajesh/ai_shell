"""
Safety Checker module for AI Shell.

This module handles safety analysis of bash commands using LLM,
identifying potentially harmful operations and providing warnings.
"""

import re
from typing import Dict, List
import colorama
from colorama import Fore, Style

from llm_handler import LLMHandler


class SafetyChecker:
    """Handles safety analysis of bash commands."""
    
    def __init__(self, llm_handler: LLMHandler):
        """Initialize the safety checker."""
        # Initialize colorama for cross-platform color support
        colorama.init(autoreset=True, convert=True)
        
        self.llm_handler = llm_handler
        
        # Define patterns for known dangerous commands
        self.dangerous_patterns = [
            r'rm\s+-rf\s+/',  # rm -rf /
            r'chmod\s+-R\s+777\s+/',  # chmod -R 777 /
            r'dd\s+if=/dev/zero\s+of=/dev/[hs]d[a-z]',  # dd to disk
            r':\(\)\{.*\}',  # Fork bomb
            r'mkfs\.',  # Format filesystem
            r'fdisk.*--delete',  # Delete partitions
            r'shred.*/',  # Shred files
            r'wipefs',  # Wipe filesystem signatures
        ]
        
        # Commands that always require extra confirmation
        self.high_risk_commands = [
            'rm', 'rmdir', 'shred', 'dd', 'mkfs', 'fdisk',
            'parted', 'gparted', 'wipefs', 'chmod', 'chown',
            'usermod', 'userdel', 'groupdel', 'passwd',
            'shutdown', 'reboot', 'halt', 'init'
        ]
        
        # File patterns that are risky to delete
        self.critical_paths = [
            '/', '/bin', '/boot', '/dev', '/etc', '/lib',
            '/lib64', '/proc', '/root', '/sbin', '/sys',
            '/usr', '/var', '/home'
        ]
    
    def check_command_safety(self, command: str) -> Dict:
        """
        Check the safety of a bash command.
        
        Returns:
            Dict with keys: is_dangerous, risk_level, reason, suggestions
        """
        # First, do pattern-based checks for immediate threats
        pattern_result = self._check_dangerous_patterns(command)
        if pattern_result['is_dangerous']:
            return pattern_result
        
        # Check for high-risk commands
        risk_result = self._check_high_risk_commands(command)
        
        # Get LLM analysis for more sophisticated checking
        try:
            llm_result = self.llm_handler.analyze_command_safety(command)
            
            # Combine results - be conservative
            combined_result = self._combine_safety_results(risk_result, llm_result)
            return combined_result
        
        except Exception as e:
            print(f"{Fore.RED}Error in LLM safety analysis: {str(e)}{Style.RESET_ALL}")
            # Fall back to pattern-based result
            return risk_result
    
    def _check_dangerous_patterns(self, command: str) -> Dict:
        """Check command against known dangerous patterns."""
        for pattern in self.dangerous_patterns:
            if re.search(pattern, command, re.IGNORECASE):
                return {
                    "is_dangerous": True,
                    "risk_level": "critical",
                    "reason": f"Command matches dangerous pattern: {pattern}",
                    "suggestions": "This command could cause severe system damage. Avoid running it."
                }
        
        return {
            "is_dangerous": False,
            "risk_level": "low",
            "reason": "No dangerous patterns detected",
            "suggestions": ""
        }
    
    def _check_high_risk_commands(self, command: str) -> Dict:
        """Check for high-risk commands that need careful attention."""
        # Extract the base command
        base_command = self._extract_base_command(command)
        
        if base_command in self.high_risk_commands:
            # Check if it affects critical paths
            affects_critical_path = any(path in command for path in self.critical_paths)
            
            if affects_critical_path:
                return {
                    "is_dangerous": True,
                    "risk_level": "high",
                    "reason": f"High-risk command '{base_command}' affecting critical system paths",
                    "suggestions": "Double-check the target paths and consider using more specific paths"
                }
            else:
                return {
                    "is_dangerous": True,
                    "risk_level": "medium",
                    "reason": f"High-risk command '{base_command}' detected",
                    "suggestions": "Review the command carefully before execution"
                }
        
        # Check for file operations on critical paths
        if self._affects_critical_paths(command):
            return {
                "is_dangerous": True,
                "risk_level": "high",
                "reason": "Command may affect critical system directories",
                "suggestions": "Ensure you're targeting the correct directories"
            }
        
        # Check for potentially destructive operations
        destructive_keywords = ['delete', 'remove', 'destroy', 'wipe', 'format', 'erase']
        if any(keyword in command.lower() for keyword in destructive_keywords):
            return {
                "is_dangerous": True,
                "risk_level": "medium",
                "reason": "Command contains potentially destructive keywords",
                "suggestions": "Verify the target files/directories before proceeding"
            }
        
        return {
            "is_dangerous": False,
            "risk_level": "low",
            "reason": "No immediate safety concerns detected",
            "suggestions": ""
        }
    
    def _extract_base_command(self, command: str) -> str:
        """Extract the base command from a complex command line."""
        # Handle pipes, redirects, and command chaining
        command = command.split('|')[0].split('>')[0].split('<')[0]
        command = command.split('&&')[0].split('||')[0].split(';')[0]
        
        # Get the first word (the command)
        parts = command.strip().split()
        if parts:
            base_cmd = parts[0]
            # Remove path if present
            return base_cmd.split('/')[-1]
        
        return ""
    
    def _affects_critical_paths(self, command: str) -> bool:
        """Check if command affects critical system paths."""
        for path in self.critical_paths:
            # Look for the path as a standalone argument
            if f" {path}" in command or f"={path}" in command or command.startswith(path):
                return True
        return False
    
    def _combine_safety_results(self, pattern_result: Dict, llm_result: Dict) -> Dict:
        """Combine pattern-based and LLM-based safety analysis."""
        # If either says it's dangerous, consider it dangerous
        is_dangerous = pattern_result['is_dangerous'] or llm_result['is_dangerous']
        
        # Use the higher risk level
        risk_levels = ['low', 'medium', 'high', 'critical']
        pattern_risk = pattern_result.get('risk_level', 'low')
        llm_risk = llm_result.get('risk_level', 'low')
        
        risk_level = max(pattern_risk, llm_risk, key=lambda x: risk_levels.index(x))
        
        # Combine reasons
        reasons = []
        if pattern_result.get('reason'):
            reasons.append(f"Pattern analysis: {pattern_result['reason']}")
        if llm_result.get('reason'):
            reasons.append(f"LLM analysis: {llm_result['reason']}")
        
        combined_reason = "; ".join(reasons) if reasons else "No specific risks identified"
        
        # Combine suggestions
        suggestions = []
        if pattern_result.get('suggestions'):
            suggestions.append(pattern_result['suggestions'])
        if llm_result.get('suggestions'):
            suggestions.append(llm_result['suggestions'])
        
        combined_suggestions = "; ".join(suggestions) if suggestions else ""
        
        return {
            "is_dangerous": is_dangerous,
            "risk_level": risk_level,
            "reason": combined_reason,
            "suggestions": combined_suggestions
        }
    
    def get_safety_recommendations(self, command: str) -> List[str]:
        """Get general safety recommendations for a command."""
        recommendations = []
        
        base_command = self._extract_base_command(command)
        
        if base_command == 'rm':
            recommendations.extend([
                "Consider using 'mv' to move files to a trash directory instead",
                "Always double-check file paths before deletion",
                "Use 'rm -i' for interactive confirmation",
                "Test with 'ls' first to see what would be affected"
            ])
        
        elif base_command == 'chmod':
            recommendations.extend([
                "Avoid using 777 permissions unless absolutely necessary",
                "Be specific about which files/directories to modify",
                "Consider the security implications of permission changes"
            ])
        
        elif base_command == 'chown':
            recommendations.extend([
                "Ensure you have the necessary privileges",
                "Be careful when changing ownership of system files",
                "Test on a small subset first if affecting many files"
            ])
        
        elif base_command in ['shutdown', 'reboot', 'halt']:
            recommendations.extend([
                "Save all work before proceeding",
                "Notify other users if this is a shared system",
                "Consider using scheduled shutdown for safety"
            ])
        
        elif 'sudo' in command:
            recommendations.extend([
                "Only use sudo when necessary",
                "Understand exactly what the command will do",
                "Avoid running untrusted scripts with sudo"
            ])
        
        # General recommendations
        if '>' in command:
            recommendations.append("Double-check redirection targets to avoid overwriting important files")
        
        if '*' in command or '?' in command:
            recommendations.append("Test glob patterns with 'ls' first to see what files will be affected")
        
        if '/' in command and not command.startswith('cd'):
            recommendations.append("Verify all file paths are correct")
        
        return recommendations
    
    def is_command_blocked(self, command: str, blocked_commands: List[str]) -> bool:
        """Check if a command is in the blocked commands list."""
        for blocked in blocked_commands:
            if blocked.lower() in command.lower():
                return True
        return False
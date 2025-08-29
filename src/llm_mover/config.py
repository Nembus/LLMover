"""Configuration management for LLM Model Mover."""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, List
from rich.console import Console
from rich.prompt import Prompt

# Import verification function (avoiding circular imports by importing at method level)


class ConfigManager:
    """Manages configuration file and user settings."""
    
    def __init__(self, config_file: Path = None):
        """Initialize config manager."""
        self.config_file = config_file or Path.cwd() / "config.yml"
        self.console = Console()
        self.config_data = {}
    
    def load_config(self) -> Dict[str, Any]:
        """Load configuration from file, create if missing."""
        if not self.config_file.exists():
            self._create_initial_config()
        else:
            try:
                with open(self.config_file, 'r') as f:
                    self.config_data = yaml.safe_load(f) or {}
            except Exception as e:
                self.console.print(f"[red]Error loading config: {e}[/red]")
                self.console.print("[yellow]Using default configuration[/yellow]")
                self.config_data = {
                    'local_path': '~/.lmstudio/models',
                    'usb_path': '/Volumes/USBSTICK/LMModels'
                }
        
        # Override with environment variables if present
        self._apply_environment_overrides()
        
        # Validate required paths exist
        if not self._validate_config():
            self._prompt_for_missing_config()
        
        # Validate USB mount point if possible
        self._validate_usb_mount()
        
        return self.config_data
    
    def _create_initial_config(self):
        """Create default config file with sensible defaults."""
        default_config = {
            'local_path': '~/.lmstudio/models',
            'usb_path': '/Volumes/USBSTICK/LMModels'
        }
        
        config_content = """# LLM Model Mover Configuration
# This file is automatically created if missing and can be customized

# Local directory where LM Studio stores models
# Default: ~/.lmstudio/models (expands to your home directory)
local_path: ~/.lmstudio/models

# USB drive directory where models will be moved
# Default: /Volumes/USBSTICK/LMModels (adjust for your USB drive name)
# Windows example: D:\\LMModels
# Linux example: /media/usb/LMModels
usb_path: /Volumes/USBSTICK/LMModels

# Advanced settings (uncomment and modify if needed)
# chunk_size: 8192          # File copy chunk size in bytes
# speed_test_size: 1048576  # Size for USB speed testing (1MB)
# min_free_space: 104857600 # Minimum free space buffer (100MB)

# Symlink strategy (auto, directory, file)
# auto: MLX/MX models use file symlinks, GGUF uses directory symlinks
# directory: Always use directory symlinks (simple, fast)
# file: Always use file-level symlinks (flexible, compatible)
symlink_strategy: auto

# File size threshold for file-level symlinks (only move files larger than this)
file_size_threshold_mb: 100

# File patterns to always keep local (even with file-level symlinks)
keep_local_patterns:
  - "*.json"
  - "*.txt" 
  - "*.yaml"
  - "*.yml"
  - "*.md"
  - "tokenizer*"
"""
        
        try:
            with open(self.config_file, 'w') as f:
                f.write(config_content)
            self.console.print(f"[green]✅ Created default config file: {self.config_file}[/green]")
            self.console.print("[dim]💡 You can customize paths in config.yml or use command-line flags[/dim]")
            
            # Load the default values into config_data
            self.config_data = default_config
            
        except Exception as e:
            self.console.print(f"[red]❌ Error creating config file: {e}[/red]")
            # Fallback: set defaults in memory only
            self.config_data = default_config
    
    def _apply_environment_overrides(self):
        """Apply environment variable overrides if present."""
        env_local = os.environ.get('LLM_LOCAL_PATH')
        env_usb = os.environ.get('LLM_USB_PATH')
        
        if env_local:
            self.config_data['local_path'] = env_local
            self.console.print(f"[dim]Using environment override for local path: {env_local}[/dim]")
        
        if env_usb:
            self.config_data['usb_path'] = env_usb
            self.console.print(f"[dim]Using environment override for USB path: {env_usb}[/dim]")
    
    def _validate_config(self) -> bool:
        """Check if required config values exist."""
        return (
            'local_path' in self.config_data and 
            'usb_path' in self.config_data and
            self.config_data['local_path'] and
            self.config_data['usb_path']
        )
    
    def _validate_usb_mount(self) -> None:
        """Validate USB mount point and warn if issues detected."""
        usb_path_str = self.config_data.get('usb_path')
        if not usb_path_str:
            return
        
        try:
            # Import here to avoid circular imports
            from .utils import verify_usb_mounted
            
            usb_path = Path(usb_path_str).expanduser().resolve()
            verification = verify_usb_mounted(usb_path, min_space_bytes=1024 * 1024)  # 1MB minimum
            
            if not verification.is_mounted:
                if verification.mount_type == "directory":
                    self.console.print(f"[yellow]⚠️  Warning: USB path exists as directory but is not a mount point[/yellow]")
                    self.console.print(f"[dim]Path: {usb_path}[/dim]")
                    self.console.print("[dim]💡 This may be a local directory instead of a USB drive.[/dim]")
                elif verification.mount_type == "not_mounted":
                    # This is expected when USB isn't connected - don't warn
                    pass
                else:
                    self.console.print(f"[yellow]⚠️  Warning: USB mount verification issue: {verification.error_message}[/yellow]")
            elif not verification.is_writable:
                self.console.print(f"[yellow]⚠️  Warning: USB path not writable: {verification.error_message}[/yellow]")
                self.console.print("[dim]💡 Check if USB is write-protected.[/dim]")
        except ImportError:
            # utils module not available during testing/setup
            pass
        except Exception as e:
            # Don't fail config loading due to USB validation issues
            self.console.print(f"[dim]Note: Could not verify USB mount: {e}[/dim]")
    
    def _prompt_for_missing_config(self):
        """Prompt user for missing configuration values."""
        self.console.print("[yellow]Configuration setup required[/yellow]")
        
        if not self.config_data.get('local_path'):
            local_path = Prompt.ask(
                "Enter local LLM models path",
                default="~/.lmstudio/models"
            )
            self.config_data['local_path'] = local_path
        
        if not self.config_data.get('usb_path'):
            usb_path = Prompt.ask(
                "Enter USB models path", 
                default="/Volumes/USBSTICK/LMModels"
            )
            self.config_data['usb_path'] = usb_path
        
        self._save_config()
        self.console.print("[green]Configuration saved![/green]")
    
    def _save_config(self):
        """Save current config to file."""
        with open(self.config_file, 'w') as f:
            yaml.dump(self.config_data, f, default_flow_style=False)
    
    def get_local_path(self) -> Path:
        """Get configured local models path."""
        path_str = self.config_data.get('local_path')
        if not path_str:
            raise ValueError("Local path not configured. Run the tool to set it up.")
        return Path(path_str).expanduser().resolve()
    
    def get_usb_path(self) -> Path:
        """Get configured USB models path."""
        path_str = self.config_data.get('usb_path')
        if not path_str:
            raise ValueError("USB path not configured. Run the tool to set it up.")
        return Path(path_str).expanduser().resolve()
    
    def get_symlink_strategy(self) -> str:
        """Get configured symlink strategy (auto, directory, file)."""
        return self.config_data.get('symlink_strategy', Config.DEFAULT_SYMLINK_STRATEGY)
    
    def get_file_size_threshold_bytes(self) -> int:
        """Get file size threshold in bytes for file-level symlinks."""
        threshold_mb = self.config_data.get('file_size_threshold_mb', Config.DEFAULT_FILE_SIZE_THRESHOLD_MB)
        return threshold_mb * 1024 * 1024
    
    def get_keep_local_patterns(self) -> List[str]:
        """Get list of file patterns to keep local."""
        return self.config_data.get('keep_local_patterns', Config.DEFAULT_KEEP_LOCAL_PATTERNS)


class Config:
    """Configuration settings for the LLM Model Mover."""
    
    # Size thresholds
    LARGE_FILE_THRESHOLD = 1024 * 1024 * 1024  # 1GB
    MIN_FREE_SPACE_BUFFER = 1024 * 1024 * 100  # 100MB buffer
    
    # Performance settings
    CHUNK_SIZE = 8192  # For file operations
    TEST_FILE_SIZE = 1024 * 1024  # 1MB for speed tests
    
    # Model type priorities (higher number = prefer to keep local)
    MODEL_TYPE_PRIORITIES = {
        'mlx_dir': 3,      # Apple Silicon optimized, keep local
        'single_file': 2,   # Easy to move
        'gguf_dir': 1,     # Usually single large files, good candidates
        'other_dir': 1,    # Unknown, but movable
        'unknown': 0       # Lowest priority
    }
    
    # Default symlink strategy settings
    DEFAULT_SYMLINK_STRATEGY = "auto"
    DEFAULT_FILE_SIZE_THRESHOLD_MB = 100
    DEFAULT_KEEP_LOCAL_PATTERNS = [
        "*.json", "*.txt", "*.yaml", "*.yml", "*.md", "tokenizer*"
    ]
    
    @classmethod
    def get_settings(cls, config_manager: ConfigManager) -> Dict[str, Any]:
        """Get all configuration settings as a dictionary."""
        return {
            'local_path': config_manager.get_local_path(),
            'usb_path': config_manager.get_usb_path(),
            'large_file_threshold': cls.LARGE_FILE_THRESHOLD,
            'min_free_space_buffer': cls.MIN_FREE_SPACE_BUFFER,
            'chunk_size': cls.CHUNK_SIZE,
            'model_type_priorities': cls.MODEL_TYPE_PRIORITIES,
        }
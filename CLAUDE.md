# LLM Model Mover - Project Documentation

## Project Overview

**Purpose**: A Python CLI tool that moves Large Language Model files from local storage to external USB drives while maintaining full LM Studio compatibility through symbolic links.

**Problem Solved**: LM Studio doesn't provide options for choosing download locations or moving models after download. This tool solves storage management issues for users with large model collections.

## Architecture & Design

### Core Components

#### 1. Model Management System (`models.py`)
- **ModelInfo Class**: Data structure representing individual models
  - Tracks size, type, symlink status, and file paths
  - Auto-detects model types (GGUF, MLX, single files, directories)
  - Provides display-friendly names and size formatting
  - Enhanced symlink resolution for accurate size calculation

- **ModelManager Class**: Core orchestration engine
  - Scans and categorizes models in local directory
  - Manages safe file operations with verification
  - Handles symlink creation and health monitoring
  - Provides smart move recommendations based on model priorities
  - Health check and repair functionality for broken symlinks
  - Model removal functionality with intelligent cleanup of symlinks and USB targets

#### 2. CLI Interface (`main.py`)
- Rich-powered interactive interface with tables and progress bars
- Interactive model selection with support for ranges and bulk operations
- Real-time storage analysis and space validation
- Comprehensive error handling with user-friendly messages
- Health check (`--check-health`) and repair (`--repair`) commands
- External model viewing (`--show-external`) functionality
- Model restoration (`--bring-back`) from USB to local storage
- Model removal (`--remove`) with multiple safety confirmations and force override (`--force`)
- External model linking (`--link-external`) to link USB models without moving them first
- External model unlinking (`--unlink-external`) to remove symlinks without deleting USB files

#### 3. Safety & Utilities (`utils.py`)
- **safe_move_with_verification()**: Atomic file operations with rollback
- **verify_file_integrity()**: Checksums and sampling for large files
- **check_symlink_health()**: Validates symlink integrity
- **estimate_copy_time()**: Transfer time estimation based on USB speed tests
- Enhanced verification for directory moves with file count validation

#### 4. Configuration Management (`config.py`)
- **ConfigManager Class**: Intelligent configuration handling with auto-creation
- **YAML-based Configuration**: Automatic `config.yml` creation with sensible defaults
- **Environment Variable Support**: Override config via `LLM_LOCAL_PATH` and `LLM_USB_PATH`
- **Interactive Setup**: Prompts for missing configuration values
- **Path Validation**: Automatic validation and expansion of user/relative paths
- **Graceful Error Handling**: Fallback to defaults when config files are corrupted

### Key Design Decisions

1. **Safety First**: All operations are atomic with automatic rollback on failure
2. **Non-Destructive**: Uses symlinks to maintain LM Studio compatibility
3. **User-Centric**: Interactive selection rather than automated bulk operations
4. **Performance-Aware**: Different handling strategies for MLX vs GGUF models
5. **Recovery-Capable**: Built-in health checking and repair functionality

## Technical Implementation

### File Operation Strategy
```python
# Atomic move pattern with verification
try:
    safe_move_with_verification(source, destination)
    create_symlink(source, destination)
    verify_symlink_health(source)
    update_model_metadata()
except Exception:
    rollback_operation()
    restore_original_state()
```

### Model Type Detection
- **GGUF Directories**: Contains `.gguf` files (recommended for USB)
- **MLX Directories**: Contains `.mlx` files (keep local for performance)  
- **Single Files**: Individual model files
- **Other Directories**: Mixed or unknown content

### Space Management
- Pre-flight checks ensure sufficient USB space
- 100MB buffer maintained for safety
- Real-time transfer speed testing for time estimates

## Current Environment Setup

### Directory Structure
```
~/.lmstudio/models/          # Local models (294GB total)
├── lmstudio-community/      # 146.5GB - Largest model
├── OpenAi/                  # 59.0GB
├── unsloth/                 # 32.1GB  
├── bartowski/               # 17.4GB
├── gabriellarson/           # 17.5GB
├── Tesslate/                # 14.6GB
├── mlx-community/           # 7.0GB (MLX - keep local)
└── [other models]

/Volumes/USBSTICK/LMModels/  # USB destination (401GB free)
```

### Model Inventory Analysis
- **Total Local Storage**: 294GB across 9 models
- **Recommended for Moving**: ~287GB (excluding MLX models)
- **Available USB Space**: 401GB of 460GB total
- **Current Status**: No models moved yet (all local)

## Usage Patterns & Commands

### Installation & Setup
```bash
cd LLMover
uv sync                    # Install dependencies (includes PyYAML)
uv run llm-mover --help    # View all available options
```

### Primary Workflows

#### 1. Initial Setup (Automatic)
- First run automatically creates `config.yml` with sensible defaults
- No manual configuration needed for standard setups
- Interactive prompts if paths need customization

#### 2. Assessment Mode
```bash
uv run llm-mover --list-only    # or -ls (short flag)
```
- Scans and categorizes all models
- Shows storage usage and available space
- No changes made to filesystem

#### 3. Interactive Moving
```bash
uv run llm-mover
```
- Displays model selection interface
- User selects models to move (ID ranges supported)
- Confirms operations before execution
- Shows progress during transfers

#### 4. Health Management
```bash
uv run llm-mover --check-health # Check symlink integrity
uv run llm-mover --repair       # Repair broken symlinks
uv run llm-mover --show-external # View models on USB (-se)
```

#### 5. Model Restoration
```bash
uv run llm-mover --bring-back   # or -bb (short flag)
```
- Move models from USB back to local storage
- Useful when USB transfer speeds are too slow for regular use
- Reverses the symlink process safely

#### 6. Link External USB Models
```bash
uv run llm-mover --link-external       # or -le (scan mode)
uv run llm-mover -le --path /path/to/usb/model  # specific path mode
```
- Link models already on USB to LM Studio without moving them
- Scan mode shows unlinked USB models for interactive selection
- Specific path mode links a single model directly
- Auto-detects publisher from directory structure or prompts for it

#### 7. Unlink External USB Models
```bash
uv run llm-mover --unlink-external     # or -ue
```
- Remove symlinks for externally-linked models (inverse of link)
- Keeps USB files intact - only removes local symlinks
- Use for unsupported models or temporary cleanup

#### 8. Model Removal
```bash
uv run llm-mover --remove       # or -rm (short flag)
uv run llm-mover --remove --force # Skip confirmation prompts
```
- Permanently delete models from storage
- Works with both local and USB-stored models
- Multiple safety confirmations prevent accidental deletion
- Shows detailed breakdown by storage location
- Requires explicit confirmation text for large operations

#### 7. Custom Paths
```bash
uv run llm-mover -l /custom/local/path -u /custom/usb/path
```

### Configuration Priority
1. **Command-line flags** (highest priority)
2. **Environment variables** (override config.yml)
3. **config.yml file** (auto-created with defaults)

### Environment Variables
```bash
export LLM_LOCAL_PATH="~/.lmstudio/models"
export LLM_USB_PATH="/Volumes/USBSTICK/LMModels"
```

## Testing & Validation

### Tested Scenarios
- ✅ Model detection and categorization
- ✅ Storage space analysis and reporting
- ✅ CLI interface and user interaction
- ✅ Help system and error messages
- ✅ USB availability detection
- ✅ Path validation and safety checks

### Ready for Production Testing
- File moving operations (safe mode implemented)
- Symlink creation and verification
- Rollback and recovery mechanisms
- Large file transfer handling

## Development Tools & Dependencies

### Technology Stack
- **Python 3.11+**: Core language
- **uv**: Fast dependency management and project tooling
- **Rich**: Terminal UI with tables, progress bars, and styling
- **Click**: Command-line interface framework
- **PyYAML**: YAML configuration file handling
- **Pathlib**: Modern path handling
- **shutil**: File operations with disk usage monitoring

### Project Structure
```
src/llm_mover/
├── __init__.py           # Package initialization
├── main.py              # CLI entry point with health check features
├── models.py            # Core classes with enhanced symlink handling
├── utils.py             # Safety utilities with improved verification
└── config.py            # YAML-based configuration management (153 lines)
.claude/                  # Claude Code automation
├── settings.local.json   # Permissions and additional directories
└── commands/             # Custom command definitions
    └── update-claudemd.md # Automatic documentation updates
pyproject.toml           # uv project configuration with PyYAML
config.yml               # Auto-generated configuration file (git-ignored)
README.md               # User documentation with CLI reference
CLAUDE.md               # This project knowledge base
```

## Operational Considerations

### Performance Characteristics
- **Scanning Speed**: ~2-3 seconds for 9 models (294GB)
- **Transfer Speed**: ~50 MB/s average USB 3.0 performance
- **Estimated Times**: 
  - lmstudio-community (146GB): ~50 minutes
  - OpenAi (59GB): ~20 minutes
  - Combined large models: ~2+ hours

### Safety Measures
- Atomic operations prevent partial moves
- Automatic rollback on any failure
- Space validation before starting
- Integrity verification for moved files
- Health monitoring for created symlinks

### Recommended Usage
1. Start with smaller models for testing (Tesslate 14.6GB)
2. Move largest models first for maximum space savings
3. Keep MLX models local for Apple Silicon performance
4. Use `--list-only` for planning sessions
5. Monitor transfer progress during large operations

## Future Enhancements

### Potential Features
- Batch move configuration files
- Model usage analytics integration
- Automatic model recommendation based on usage
- Cross-platform path handling (Windows/Linux)
- Progress persistence across sessions
- Model integrity scheduling and monitoring

### Extension Points
- Plugin system for different model managers
- Custom model type detection rules
- Alternative storage backends (network drives, cloud)
- Integration with other LLM tools (Ollama, etc.)

## Troubleshooting Guide

### Common Issues
1. **USB Not Detected**: Check mount point `/Volumes/USBSTICK/LMModels`
2. **Permission Errors**: Verify read/write access to both directories
3. **Space Issues**: Tool validates space but check for hidden files
4. **Symlink Problems**: Use verbose mode for detailed error information

### Debug Commands
```bash
uv run llm-mover --verbose          # Detailed logging
uv run llm-mover --list-only -v     # Verbose scanning only
uv run llm-mover --check-health     # Check symlink and model health
uv run llm-mover --repair           # Repair broken symlinks
uv run llm-mover --show-external    # View models currently on USB
uv run llm-mover --link-external    # Link unlinked USB models to LM Studio
uv run llm-mover --unlink-external  # Remove symlinks (keep USB files)
ls -la ~/.lmstudio/models/          # Manual directory inspection
df -h /Volumes/USBSTICK/            # Check USB space manually
```

### Recent Updates (Updated: December 27, 2025)

#### External Model Linking & Unlinking Features (Latest)
- **Link Feature**: Link models already on USB to LM Studio without moving them first
  - CLI: `--link-external` (`-le`) with optional `--path` (`-p`) argument
  - Scan mode or specific path mode
  - Auto-detects publisher or prompts for flat models
- **Unlink Feature**: Remove symlinks without deleting USB files (inverse of link)
  - CLI: `--unlink-external` (`-ue`)
  - Shows externally-linked models for selection
  - Removes local symlinks only, preserves USB files
  - Use case: Remove unsupported models like MiniMax-M2.1 from LM Studio
- **Smart Detection**: Compares USB models against existing local symlinks
- **Safety Features**: Validates paths, checks for existing symlinks, cleanup on failure

#### Model Removal Feature (Previous)
- **Major Feature**: Added permanent model deletion capability with comprehensive safety measures
- **CLI Integration**: New `--remove` (`-rm`) flag with interactive model selection
- **Safety Confirmations**: Multiple confirmation layers prevent accidental deletion
  - Basic confirmation for all deletions
  - Double confirmation for large operations (>10GB or multiple models)
  - Explicit text confirmation required for high-risk deletions
- **Force Override**: `--force` (`-f`) flag to skip confirmation prompts for automated scripts
- **Smart Detection**: Handles all model types (local, symlinked, internal symlinks) intelligently
- **Complete Cleanup**: Removes both local symlinks and USB targets in coordinated manner
- **Storage Analysis**: Shows detailed breakdown by storage location before deletion
- **Space Reporting**: Calculates and displays total space freed across all storage locations

#### README Documentation Enhancement (Latest)
- **Complete Feature Coverage**: Updated README with model removal workflow documentation
- **Safety Documentation**: Comprehensive safety feature documentation with warnings
- **CLI Reference**: Updated command-line flag reference table with removal options
- **Use Case Guidance**: Clear guidance on when to use removal vs. other operations
- **Backup Warnings**: Prominent warnings about permanent deletion and backup recommendations

#### Configuration Management Overhaul (Previous)
- **Major Feature**: Complete rewrite of configuration system using `ConfigManager` class
- **Auto-Creation**: Automatic `config.yml` generation with sensible defaults on first run
- **YAML Support**: Added PyYAML dependency for human-readable configuration files
- **Interactive Setup**: Prompts for missing configuration values with intelligent defaults
- **Path Validation**: Automatic expansion and validation of user/relative paths
- **Graceful Fallbacks**: Robust error handling with in-memory defaults when config files fail
- **Environment Override**: Full support for `LLM_LOCAL_PATH` and `LLM_USB_PATH` variables
- **Developer Experience**: No manual configuration needed for standard macOS setups

#### Enhanced CLI Documentation (Previous)
- **Complete CLI Reference**: Added comprehensive documentation for all command-line flags
- **Short Flag Support**: Added short flags (`-ls`, `-se`, `-l`, `-u`) for frequently used options  
- **Health Management**: New `--check-health` and `--repair` commands for symlink maintenance
- **External Model Viewing**: `--show-external` flag to view models currently stored on USB
- **Configuration Priority**: Clear documentation of flag > environment > config.yml precedence

#### Git Integration & Development Automation (Previous)
- **Claude Code Integration**: Added `.claude/` folder with settings and command automation
- **Automatic Documentation**: Created custom `update-claudemd` command for maintaining documentation
- **Permission Management**: Configured permissions for model directory access and uv command execution
- **Development Workflow**: Enhanced development experience with automated documentation updates

#### Previous Fixes (August 28, 2025)

#### Size Display Bug (Fixed)
- **Issue**: Models on USB showing 0.0 B due to symlink size calculation bug
- **Root Cause**: `_calculate_size()` method not following symlinks to USB targets
- **Fix**: Enhanced method to resolve symlinks and calculate actual target sizes
- **Result**: Correctly displays sizes for models on USB (e.g., 32.1 GB for Kimi model)

#### Move Operation Reliability (Enhanced)  
- **Issue**: File move operations could succeed partially, leaving empty directories on USB
- **Enhancement**: Added comprehensive verification for directory moves
- **Verification**: Checks file count and total size after copy operations
- **Safety**: Automatic rollback if verification fails

#### Health Check & Repair System (New)
- **Feature**: `--check-health` flag detects broken symlinks and empty USB directories
- **Feature**: `--repair` flag automatically removes broken symlinks
- **Benefits**: Proactive maintenance and issue detection
- **Usage**: Run `uv run llm-mover --check-health` for diagnostics

#### USB Scanning Improvements (Fixed)
- **Issue**: Empty directories on USB showing as 0 byte "models" in `--show-external`
- **Root Cause**: USB scanning included empty publisher directories after failed moves
- **Fix**: Enhanced scanning logic to skip directories with zero content
- **Result**: Clean USB listings show only legitimate models with actual content

### Recovery Procedures
- Tool includes automatic rollback for failed operations
- Manual recovery: check USB for moved files, recreate symlinks if needed
- Health check feature can repair broken symlinks automatically

This documentation captures the complete project state, technical decisions, and operational knowledge for the LLM Model Mover tool.
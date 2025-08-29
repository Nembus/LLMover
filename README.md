# 🚀 LLMover

**Free up disk space while keeping your LM Studio models accessible!**

A simple Python tool that moves your Large Language Model files to an external USB drive while maintaining full compatibility with LM Studio through symbolic links.

## 🎯 Why Use This Tool?

**The Problem:**
- LM Studio doesn't let you choose where to download models
- Large models eat up your precious SSD space (often 50-200GB+ each!)
- No built-in way to move models after downloading

**The Solution:**
- Move models to external USB storage (cheap and expandable!)
- Keep LM Studio working exactly as before through "symbolic links"
- Safe operations with automatic backup and recovery

## ✨ Key Features

- 🔍 **Smart Detection** - Automatically finds and categorizes your models
- 📊 **Storage Overview** - See exactly what's using your disk space
- 🎛️ **Interactive Selection** - Choose exactly which models to move
- ⚡ **Safe & Fast** - Atomic operations with automatic rollback on failure
- 🔗 **Seamless Integration** - LM Studio keeps working normally
- ⏱️ **Time Estimates** - Know how long transfers will take
- 🛡️ **Health Monitoring** - Validates everything is working correctly

## 📋 Prerequisites

- **Python 3.11+** (check with `python3 --version`)
- **uv package manager** ([install here](https://docs.astral.sh/uv/))
- **macOS** (works with other systems but paths need adjustment)
- **External USB drive** with enough free space

**📝 Note:** The tool automatically creates a `config.yml` file with sensible defaults when you first run it. No manual configuration needed!

## 🚀 Quick Start

### 1. Download & Install
```bash
# Clone this repository
git clone git@github.com:Nembus/LLMover.git
cd LLMover

# Install dependencies
uv sync
```

### 2. First Look (Safe - No Changes Made)
```bash
# See what models you have and their sizes
uv run llm-mover --list-only
# Or using the short flag
uv run llm-mover -ls
```

### 3. Move Models Interactively
```bash
# Interactive mode - you choose what to move
uv run llm-mover
```

That's it! The tool will guide you through the process.

## 💡 Step-by-Step Walkthrough

### What You'll See:

1. **Storage Overview** - Current usage and available space
```
╭─── Storage Overview ───╮
│ 💾 Local: 9 models, 294.2 GB │
│ 📎 USB: 0 models, 0.0 B      │  
│ 💽 USB: 401.1 GB free        │
╰───────────────────────────────╯
```

2. **Model List** - All your models with sizes and types
```
Models Available to Move
┏━━━━┳━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━┓
┃ ID ┃ Model Name         ┃     Size ┃ Type     ┃
┡━━━━╇━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━┩
│ 1  │ lmstudio-community │ 146.5 GB │ GGUF     │
│ 2  │ OpenAi             │  59.0 GB │ GGUF     │
│ 3  │ unsloth            │  32.1 GB │ GGUF     │
└────┴────────────────────┴──────────┴──────────┘
```

3. **Easy Selection** - Choose models by number
```bash
Select models: 1,3        # Move models 1 and 3
Select models: 1-5        # Move models 1 through 5  
Select models: all        # Move all available models
```

4. **Safe Transfer** - Automatic verification and progress tracking
```
🚚 Moving lmstudio-community...
⏱️ Estimated time: 45 minutes
🔄 [████████████████████] 100%
✅ Successfully moved and linked!
```

## ⚙️ Advanced Usage

### Custom Paths
```bash
# If your models or USB are in different locations
uv run llm-mover --local-path /path/to/models --usb-path /path/to/usb
# Or using short flags
uv run llm-mover -l /path/to/models -u /path/to/usb
```

### Environment Variables
```bash
# Set once and forget - overrides config.yml settings
export LLM_LOCAL_PATH="/custom/model/path"
export LLM_USB_PATH="/Volumes/MyUSB/Models"
```

**💡 Tip:** The tool creates a `config.yml` file automatically with defaults. Environment variables override these settings, and command-line flags override everything.

### View Models on USB
```bash
# See what models are currently stored on your USB drive
uv run llm-mover --show-external
# Or using short flag
uv run llm-mover -se
```

### Bring Models Back from USB
```bash
# Move models from USB back to local storage
uv run llm-mover --bring-back
# Or using short flag
uv run llm-mover -bb
```

**What happens:**
- Shows models currently on USB (via symlinks)
- Lets you select which models to bring back
- Checks local storage space before proceeding
- Moves selected models from USB to local storage
- Removes symlinks (models are now fully local again)
- Shows space freed up on USB and used locally

**When to use:**
- You want to use certain models frequently without USB
- Working offline and need local access
- USB transfer speeds are too slow for regular use
- Preparing to remove or reformat the USB drive

### Health Checking & Repair
```bash
# Check if all symlinks are working properly
uv run llm-mover --check-health
# Or using short flag
uv run llm-mover -ch

# Automatically repair broken symlinks
uv run llm-mover --repair
# Or using short flag
uv run llm-mover -r
```

### Verbose Mode
```bash
# See detailed information during operations
uv run llm-mover --verbose
# Or using short flag
uv run llm-mover -v
```

## 🏷️ Understanding Model Types

The tool automatically categorizes your models:

- **🗂️ GGUF Models** - Standard quantized models (great for moving to USB)
- **🍎 MLX Models** - Apple Silicon optimized (recommend keeping local for speed)  
- **📄 Single Files** - Individual model files
- **📁 Other** - Mixed or unknown content

**💡 Tip:** GGUF models are perfect candidates for USB storage since they're typically single large files that compress well and don't need ultra-fast access.

## 📖 Complete Command Reference

| Command | Short | Description |
|---------|-------|-------------|
| `--help` | | Show help message and exit |
| `--local-path PATH` | `-l` | Override local models directory path |
| `--usb-path PATH` | `-u` | Override USB models directory path |
| `--list-only` | `-ls` | Only list models, don't move anything (safe mode) |
| `--show-external` | `-se` | Show models currently stored on USB drive |
| `--check-health` | `-ch` | Check health of symlinks and models |
| `--repair` | `-r` | Automatically repair broken symlinks |
| `--bring-back` | `-bb` | Move models from USB back to local storage |
| `--verbose` | `-v` | Show detailed information during operations |

### Usage Examples
```bash
# Safe exploration (no changes made)
uv run llm-mover --list-only
uv run llm-mover -ls

# View what's on USB
uv run llm-mover --show-external -v

# Health check and repair workflow
uv run llm-mover --check-health
uv run llm-mover --repair

# Bring models back from USB to local storage
uv run llm-mover --bring-back
uv run llm-mover -bb

# Custom paths with verbose output
uv run llm-mover -l /custom/path -u /Volumes/MyUSB/Models -v
```

## 🔒 Safety & Recovery

**This tool is designed to be safe:**

✅ **Atomic Operations** - Moves either complete 100% or rollback completely  
✅ **Space Validation** - Checks available space before starting  
✅ **Backup Creation** - Temporary backups during operations  
✅ **Integrity Verification** - Confirms files transferred correctly  
✅ **Health Monitoring** - Validates symbolic links are working  
✅ **Automatic Recovery** - Rollback on any failure  

**If something goes wrong:** The tool automatically tries to restore your original setup.

## 🆘 Troubleshooting

### "USB Not Detected"
- **Check mount point:** Your USB should appear at `/Volumes/USBSTICK/LMModels`
- **Different path?** Use `--usb-path /Volumes/YourUSBName/Models`
- **Not mounted?** Unplug and reconnect your USB drive

### "Permission Denied"
```bash
# Fix permissions for your models directory
chmod -R u+rw ~/.lmstudio/models/
```

### "LM Studio Can't Find Models"
- This shouldn't happen with proper symlinks
- Run health check to diagnose issues: `uv run llm-mover --check-health`
- Use automatic repair: `uv run llm-mover --repair`
- Use `--verbose` to see detailed error information

### Symlink Issues
```bash
# Diagnose symlink problems
uv run llm-mover --check-health --verbose

# Automatically fix broken symlinks
uv run llm-mover --repair

# Check what's actually on your USB
uv run llm-mover --show-external
```

### Need Help?
```bash
# Get detailed output for troubleshooting
uv run llm-mover --verbose --list-only

# Complete diagnostic workflow
uv run llm-mover --check-health -v
uv run llm-mover --show-external -v

# View all available options
uv run llm-mover --help
```

## ❓ Frequently Asked Questions

**Q: Will this break LM Studio?**  
A: No! LM Studio will continue working normally. The symbolic links make it appear as if models are still in the original location.

**Q: What if I unplug my USB drive?**  
A: LM Studio won't be able to load models stored on the USB until you plug it back in. Models still on local storage continue working.

**Q: Can I move models back to local storage?**  
A: Yes! Use `uv run llm-mover --bring-back` to interactively select and move models from USB back to local storage. The tool will remove symlinks and transfer files safely.

**Q: How much space will I save?**  
A: It depends on your models! You could save hundreds of GB. Run `uv run llm-mover --list-only` to see potential savings.

**Q: Is this reversible?**  
A: Yes! The file operations are completely reversible. Use `uv run llm-mover --bring-back` to automatically move models back to local storage and clean up symlinks.

## 🔧 Technical Details

**Built with:**
- **Python 3.11+** - Modern Python features
- **Rich** - Beautiful terminal interfaces  
- **Click** - Command-line interface framework
- **uv** - Fast, modern Python package management

**How symbolic links work:**
- Original location: `~/.lmstudio/models/my-model/` (symlink)
- Actual location: `/Volumes/USB/Models/my-model/` (real files)
- LM Studio sees: The model in the original location (transparent!)

---

**Ready to free up some disk space? Give it a try with `uv run llm-mover --list-only` first! 🎉**
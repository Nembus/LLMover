"""Model management classes for LLM model organization."""

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .utils import (safe_move_with_verification, check_symlink_health, estimate_copy_time, 
                    safe_restore_from_usb, safe_restore_internal_symlinks,
                    should_keep_local, safe_move_with_file_symlinks, verify_usb_mounted, 
                    USBVerificationResult)
from .config import Config, ConfigManager


@dataclass
class ModelInfo:
    """Information about a single model."""
    
    name: str  # Full unique identifier (publisher/model_name)
    path: Path
    size_bytes: int
    publisher: str = ""  # Publisher/lab name (e.g., 'bartowski', 'lmstudio-community')
    model_name: str = ""  # Actual model name (e.g., 'THUDM_GLM-4-32B-0414-GGUF')
    is_symlink: bool = False
    linked_to: Optional[Path] = None
    has_internal_symlinks: bool = False  # True if directory contains symlinks to USB
    internal_symlink_target: Optional[Path] = None  # Common USB target for internal symlinks
    type: str = field(init=False)
    
    def __post_init__(self):
        """Determine model type based on path contents and parse publisher info."""
        # Determine model type
        if self.path.is_file():
            self.type = "single_file"
        elif self.path.is_dir():
            # Check if it contains GGUF files
            if any(f.suffix.lower() == '.gguf' for f in self.path.rglob('*.gguf')):
                self.type = "gguf_dir"
            elif any(f.suffix.lower() == '.mlx' for f in self.path.rglob('*.mlx')):
                self.type = "mlx_dir"
            else:
                self.type = "other_dir"
        else:
            self.type = "unknown"
        
        # Parse publisher and model name if not already set
        if not self.publisher and not self.model_name:
            # If this is a two-level path structure (publisher/model)
            parts = self.path.parts
            if len(parts) >= 2:
                self.publisher = parts[-2]  # Second to last part
                self.model_name = parts[-1]  # Last part
            else:
                # Single level - use the directory name as both
                self.publisher = self.path.name
                self.model_name = self.path.name
    
    @property
    def size_gb(self) -> float:
        """Return size in GB."""
        return self.size_bytes / (1024 ** 3)
    
    @property
    def display_name(self) -> str:
        """Return a display-friendly name showing publisher and model."""
        if self.publisher and self.model_name and self.publisher != self.model_name:
            # Format: Publisher/Model Name
            clean_model = self.model_name.replace('_', ' ').replace('-', ' ')
            return f"{self.publisher}/{clean_model}"
        else:
            # Fallback to just the name
            return self.name.replace('_', ' ').replace('-', ' ')


class ModelManager:
    """Manages LLM models between local and USB storage."""
    
    def __init__(self, local_path: str, usb_path: str, config_manager: ConfigManager = None):
        """Initialize with local and USB paths."""
        self.local_path = Path(local_path).expanduser().resolve()
        self.usb_path = Path(usb_path).expanduser().resolve()
        self.config_manager = config_manager or ConfigManager()
        self._models: Dict[str, ModelInfo] = {}
        self._usb_verification: Optional[USBVerificationResult] = None
        
        self._check_paths()
        self._scan_models()
    
    def _check_paths(self) -> None:
        """Check if paths exist and are accessible."""
        if not self.local_path.exists():
            raise FileNotFoundError(f"Local models path not found: {self.local_path}")
        
        # Perform comprehensive USB verification
        self._usb_verification = verify_usb_mounted(self.usb_path)
        if not self._usb_verification.is_mounted:
            print(f"⚠️  USB verification failed: {self._usb_verification.error_message}")
        elif not self._usb_verification.is_writable:
            print(f"⚠️  USB mounted but not writable: {self._usb_verification.error_message}")
        elif not self._usb_verification.has_space:
            print(f"⚠️  USB mounted but insufficient space: {self._usb_verification.error_message}")
    
    def _scan_models(self) -> None:
        """Scan for models in the local directory, looking inside publisher directories."""
        if not self.local_path.exists():
            return
        
        for publisher_dir in self.local_path.iterdir():
            if publisher_dir.name.startswith('.'):
                continue
            
            # Handle both old structure (top-level models) and new structure (publisher/model)
            if publisher_dir.is_dir():
                # Check if this directory contains model subdirectories
                model_subdirs = [
                    d for d in publisher_dir.iterdir() 
                    if d.is_dir() and not d.name.startswith('.')
                ]
                
                if model_subdirs:
                    # This is a publisher directory with model subdirectories
                    for model_dir in model_subdirs:
                        try:
                            self._process_model_directory(model_dir, publisher_dir.name)
                        except (OSError, PermissionError) as e:
                            print(f"⚠️  Skipping {publisher_dir.name}/{model_dir.name}: {e}")
                else:
                    # This might be a direct model directory (old structure)
                    try:
                        self._process_model_directory(publisher_dir, "")
                    except (OSError, PermissionError) as e:
                        print(f"⚠️  Skipping {publisher_dir.name}: {e}")
            else:
                # Handle single model files
                try:
                    self._process_model_directory(publisher_dir, "")
                except (OSError, PermissionError) as e:
                    print(f"⚠️  Skipping {publisher_dir.name}: {e}")
    
    def _process_model_directory(self, model_path: Path, publisher: str = "") -> None:
        """Process a single model directory or file."""
        size = self._calculate_size(model_path)
        
        # Skip empty directories (placeholder directories with no actual model files)
        if model_path.is_dir() and size == 0:
            return  # Don't add empty directories to the model list
        
        is_symlink = model_path.is_symlink()
        linked_to = model_path.readlink() if is_symlink else None
        
        # Check for internal symlinks (files within directory that point to USB)
        has_internal_symlinks = False
        internal_symlink_target = None
        if not is_symlink and model_path.is_dir():
            has_internal_symlinks, internal_symlink_target = self._has_symlinked_contents(model_path)
        
        # Create unique identifier
        if publisher:
            unique_name = f"{publisher}/{model_path.name}"
        else:
            unique_name = model_path.name
        
        model_info = ModelInfo(
            name=unique_name,
            path=model_path,
            size_bytes=size,
            publisher=publisher,
            model_name=model_path.name,
            is_symlink=is_symlink,
            linked_to=linked_to,
            has_internal_symlinks=has_internal_symlinks,
            internal_symlink_target=internal_symlink_target
        )
        
        self._models[unique_name] = model_info
    
    def _calculate_size(self, path: Path) -> int:
        """Calculate total size of a file or directory, following symlinks."""
        # If it's a symlink, follow it to calculate the actual size
        if path.is_symlink():
            try:
                # Get the target path and calculate its size
                target = path.resolve()
                return self._calculate_size(target)
            except (OSError, RuntimeError):
                # If symlink is broken or we can't follow it, return 0
                return 0
        
        if path.is_file():
            return path.stat().st_size
        elif path.is_dir():
            try:
                return sum(f.stat().st_size for f in path.rglob('*') if f.is_file())
            except (OSError, PermissionError):
                # If we can't access the directory, return 0
                return 0
        return 0
    
    def _has_symlinked_contents(self, directory_path: Path) -> tuple[bool, Optional[Path]]:
        """Check if directory contains files that are symlinks to USB.
        
        Returns:
            tuple: (has_symlinks_to_usb, common_usb_target_directory)
        """
        if not directory_path.is_dir() or not self.usb_available:
            return False, None
        
        try:
            files = list(directory_path.rglob('*'))
            file_count = len([f for f in files if f.is_file()])
            
            if file_count == 0:
                return False, None
            
            symlink_files = []
            usb_targets = []
            
            for file_path in files:
                if file_path.is_file() and file_path.is_symlink():
                    try:
                        target = file_path.resolve()
                        # Check if target is on USB by seeing if it's under USB path
                        if str(target).startswith(str(self.usb_path)):
                            symlink_files.append(file_path)
                            usb_targets.append(target.parent)
                    except (OSError, RuntimeError):
                        # Broken symlink, ignore
                        continue
            
            # Consider it "on USB" if majority of files are symlinked to USB
            symlink_ratio = len(symlink_files) / file_count if file_count > 0 else 0
            has_usb_symlinks = symlink_ratio > 0.5  # More than 50% of files are on USB
            
            # Find common USB target directory
            common_target = None
            if usb_targets:
                # Get the most common target directory
                from collections import Counter
                target_counts = Counter(str(target) for target in usb_targets)
                most_common_target = target_counts.most_common(1)[0][0]
                common_target = Path(most_common_target)
            
            return has_usb_symlinks, common_target
            
        except (OSError, PermissionError):
            return False, None
    
    def _determine_symlink_strategy(self, model_info: ModelInfo) -> str:
        """Determine the best symlink strategy for a given model."""
        config_strategy = self.config_manager.get_symlink_strategy()
        
        # If user has explicit preference, respect it
        if config_strategy in ['directory', 'file']:
            return config_strategy
        
        # Auto-detection logic (config_strategy == 'auto')
        model_path = model_info.path
        model_name = model_info.name.lower()
        
        # Check for MLX/MX model indicators
        mlx_indicators = [
            'mlx' in model_name,
            'mx' in model_name and any(x in model_name for x in ['fp4', 'fp6', 'fp8']),  # Mixed precision
            model_info.type == 'mlx_dir',
        ]
        
        if any(mlx_indicators):
            return 'file'  # MLX/MX models work better with file-level symlinks
        
        # Check file patterns in model directory
        if model_path.is_dir():
            files = list(model_path.rglob('*'))
            file_extensions = {f.suffix.lower() for f in files if f.is_file()}
            
            # MLX models typically have .safetensors files
            if '.safetensors' in file_extensions and any(mlx_indicators):
                return 'file'
            
            # Check for files with MX/mixed precision indicators
            for file in files:
                if file.is_file() and any(indicator in file.name.lower() for indicator in ['mxfp', 'mx-']):
                    return 'file'
            
            # GGUF models are usually good with directory symlinks
            if '.gguf' in file_extensions and not any(mlx_indicators):
                return 'directory'
        
        # Default to file-level symlinks for safety/compatibility
        return 'file'
    
    def _move_with_file_symlinks(self, model: ModelInfo, usb_dest: Path) -> bool:
        """Move model using file-level symlinks (selective file moving)."""
        if not model.path.is_dir():
            # For single files, fall back to directory symlink approach
            return self._move_with_directory_symlink(model, usb_dest)
        
        # Get configuration for file-level moves
        size_threshold = self.config_manager.get_file_size_threshold_bytes()
        keep_patterns = self.config_manager.get_keep_local_patterns()
        
        # Find large files to move to USB
        all_files = list(model.path.rglob('*'))
        all_files = [f for f in all_files if f.is_file()]
        
        files_to_move = []
        files_to_keep = []
        
        for file_path in all_files:
            # Check if file should be kept local based on patterns
            if should_keep_local(file_path, keep_patterns):
                files_to_keep.append(file_path)
            # Check if file is large enough to move
            elif file_path.stat().st_size >= size_threshold:
                files_to_move.append(file_path)
            else:
                files_to_keep.append(file_path)
        
        if not files_to_move:
            raise RuntimeError("No files meet the criteria for moving to USB")
        
        print(f"Moving {len(files_to_move)} large files to USB, keeping {len(files_to_keep)} files local")
        
        # Use the safe file symlink utility
        success = safe_move_with_file_symlinks(model.path, usb_dest, files_to_move, files_to_keep)
        
        if success:
            # Update model info to reflect internal symlinks
            model.has_internal_symlinks = True
            model.internal_symlink_target = usb_dest
            return True
        
        return False
    
    def _move_with_directory_symlink(self, model: ModelInfo, usb_dest: Path) -> bool:
        """Move model using directory symlink (move entire directory)."""
        # Use safe move with verification and USB monitoring
        safe_move_with_verification(model.path, usb_dest, monitor_usb_path=self.usb_path)
        
        # Create symlink in original location
        model.path.symlink_to(usb_dest)
        
        # Verify symlink health
        health = check_symlink_health(model.path)
        if health['is_broken']:
            raise RuntimeError("Created symlink is broken")
        
        # Update model info
        model.is_symlink = True
        model.linked_to = usb_dest
        return True
    
    @property
    def usb_available(self) -> bool:
        """Check if USB is available and properly mounted."""
        if not self._usb_verification:
            return False
        return (self._usb_verification.is_mounted and 
                self._usb_verification.is_writable and 
                self._usb_verification.has_space)
    
    @property
    def usb_verification(self) -> Optional[USBVerificationResult]:
        """Get detailed USB verification results."""
        return self._usb_verification
    
    def refresh_usb_status(self) -> USBVerificationResult:
        """Re-verify USB mount status and return detailed results."""
        self._usb_verification = verify_usb_mounted(self.usb_path)
        return self._usb_verification
    
    def get_movable_models(self) -> List[ModelInfo]:
        """Get models that can be moved to USB (not already symlinked)."""
        return [model for model in self._models.values() if not model.is_symlink and not model.has_internal_symlinks]
    
    def get_usb_models(self) -> List[ModelInfo]:
        """Get models that are currently on USB (symlinked or with internal symlinks)."""
        return [model for model in self._models.values() if model.is_symlink or model.has_internal_symlinks]
    
    def get_model_by_name(self, name: str) -> Optional[ModelInfo]:
        """Get model info by name."""
        return self._models.get(name)
    
    def move_model_to_usb(self, model_name: str) -> bool:
        """Move a model from local storage to USB and create symlink."""
        # Comprehensive pre-flight USB verification
        usb_status = self.refresh_usb_status()
        if not usb_status.is_mounted:
            raise RuntimeError(f"USB not properly mounted: {usb_status.error_message}")
        if not usb_status.is_writable:
            raise RuntimeError(f"USB not writable: {usb_status.error_message}")
        if not usb_status.has_space:
            raise RuntimeError(f"USB insufficient space: {usb_status.error_message}")
        
        model = self.get_model_by_name(model_name)
        if not model:
            raise ValueError(f"Model '{model_name}' not found")
        
        if model.is_symlink:
            raise ValueError(f"Model '{model_name}' is already on USB")
        
        # Create destination path maintaining publisher structure if needed
        if model.publisher:
            # Create publisher directory on USB if it doesn't exist
            publisher_dir = self.usb_path / model.publisher
            publisher_dir.mkdir(exist_ok=True)
            usb_dest = publisher_dir / model.model_name
        else:
            # Direct model (old structure or single files)
            usb_dest = self.usb_path / model.model_name
        
        # Check if destination already exists
        if usb_dest.exists():
            raise FileExistsError(f"Destination already exists: {usb_dest}")
        
        # Check available space with buffer
        space_info = self.get_usb_space_info()
        required_space = model.size_bytes + Config.MIN_FREE_SPACE_BUFFER
        
        if required_space > space_info['free']:
            raise RuntimeError(f"Insufficient USB space: need {required_space}, have {space_info['free']}")
        
        # Estimate copy time
        try:
            est_seconds, est_str = estimate_copy_time(model.size_bytes, self.usb_path)
            print(f"Estimated transfer time: {est_str}")
        except Exception:
            pass
        
        try:
            # Determine the best symlink strategy for this model
            strategy = self._determine_symlink_strategy(model)
            
            print(f"Moving {model.name} to USB using {strategy} symlink strategy...")
            
            if strategy == 'file':
                # Use file-level symlinks
                return self._move_with_file_symlinks(model, usb_dest)
            else:
                # Use directory symlink (traditional approach)
                print(f"Moving entire directory to USB...")
                return self._move_with_directory_symlink(model, usb_dest)
            
        except Exception as e:
            # Try to recover if something went wrong
            if usb_dest.exists() and not model.path.exists():
                try:
                    safe_move_with_verification(usb_dest, model.path)
                    print(f"Recovered model to original location")
                except Exception:
                    pass
            raise RuntimeError(f"Failed to move model: {e}")
    
    def move_model_from_usb(self, model_name: str) -> bool:
        """Move a model from USB storage back to local and remove symlink."""
        model = self.get_model_by_name(model_name)
        if not model:
            raise ValueError(f"Model '{model_name}' not found")
        
        if not model.is_symlink and not model.has_internal_symlinks:
            raise ValueError(f"Model '{model_name}' is not on USB (not a symlink or internal symlinks)")
        
        # Comprehensive pre-flight USB verification
        usb_status = self.refresh_usb_status()
        if not usb_status.is_mounted:
            raise RuntimeError(f"USB not properly mounted: {usb_status.error_message}")
        if not usb_status.is_writable:
            raise RuntimeError(f"USB not writable: {usb_status.error_message}")
        
        # Verify that the USB source exists
        usb_source_path = None
        if model.is_symlink:
            # Full directory symlink case
            if not model.linked_to or not model.linked_to.exists():
                raise RuntimeError(f"Model '{model_name}' target on USB not found or broken symlink")
            usb_source_path = model.linked_to
        elif model.has_internal_symlinks:
            # Internal file symlinks case
            if not model.internal_symlink_target or not model.internal_symlink_target.exists():
                raise RuntimeError(f"Model '{model_name}' USB target directory not found or broken internal symlinks")
            usb_source_path = model.internal_symlink_target
        
        # Check local storage space
        local_stat = shutil.disk_usage(self.local_path)
        required_space = model.size_bytes + Config.MIN_FREE_SPACE_BUFFER
        
        if required_space > local_stat.free:
            raise RuntimeError(f"Insufficient local space: need {required_space}, have {local_stat.free}")
        
        # Estimate copy time
        try:
            est_seconds, est_str = estimate_copy_time(model.size_bytes, self.local_path)
            print(f"Estimated transfer time: {est_str}")
        except Exception:
            pass
        
        try:
            print(f"Restoring {model.name} from USB to local storage...")
            
            if model.is_symlink:
                # Full directory symlink case - use existing restore function
                safe_restore_from_usb(model.path, usb_source_path, model.path)
                
                # Update model info
                model.is_symlink = False
                model.linked_to = None
                
            elif model.has_internal_symlinks:
                # Internal file symlinks case - use new restore function
                safe_restore_internal_symlinks(model.path, usb_source_path)
                
                # Update model info
                model.has_internal_symlinks = False
                model.internal_symlink_target = None
            
            return True
            
        except Exception as e:
            raise RuntimeError(f"Failed to restore model from USB: {e}")
    
    def remove_model(self, model_name: str) -> bool:
        """Permanently remove/delete a model from storage."""
        model = self.get_model_by_name(model_name)
        if not model:
            raise ValueError(f"Model '{model_name}' not found")
        
        print(f"Removing {model.name}...")
        
        try:
            if model.is_symlink:
                # Model is a symlink - remove both the symlink and the target on USB
                print(f"Removing symlinked model (local symlink + USB target)...")
                
                # Remove the target on USB first
                if model.linked_to and model.linked_to.exists():
                    if model.linked_to.is_dir():
                        shutil.rmtree(model.linked_to)
                    else:
                        model.linked_to.unlink()
                    print(f"Removed USB target: {model.linked_to}")
                
                # Remove the local symlink
                if model.path.is_symlink():
                    model.path.unlink()
                    print(f"Removed local symlink: {model.path}")
                
            elif model.has_internal_symlinks:
                # Model has internal file symlinks - remove local structure and USB target
                print(f"Removing model with internal symlinks (local structure + USB files)...")
                
                # Remove the USB target directory
                if model.internal_symlink_target and model.internal_symlink_target.exists():
                    if model.internal_symlink_target.is_dir():
                        shutil.rmtree(model.internal_symlink_target)
                    else:
                        model.internal_symlink_target.unlink()
                    print(f"Removed USB target: {model.internal_symlink_target}")
                
                # Remove the local directory structure (contains symlinks)
                if model.path.exists():
                    if model.path.is_dir():
                        shutil.rmtree(model.path)
                    else:
                        model.path.unlink()
                    print(f"Removed local structure: {model.path}")
                
            else:
                # Model is purely local - remove it directly
                print(f"Removing local model...")
                
                if model.path.exists():
                    if model.path.is_dir():
                        shutil.rmtree(model.path)
                    else:
                        model.path.unlink()
                    print(f"Removed local model: {model.path}")
            
            # Remove from internal model tracking
            if model_name in self._models:
                del self._models[model_name]
            
            return True
            
        except Exception as e:
            raise RuntimeError(f"Failed to remove model '{model_name}': {e}")
    
    def get_usb_space_info(self) -> Dict[str, int]:
        """Get USB storage space information."""
        if not self.usb_available:
            return {"total": 0, "used": 0, "free": 0}
        
        try:
            stat = shutil.disk_usage(self.usb_path)
            return {
                "total": stat.total,
                "used": stat.used,
                "free": stat.free
            }
        except Exception:
            return {"total": 0, "used": 0, "free": 0}
    
    def get_smart_move_recommendations(self) -> List[ModelInfo]:
        """Get smart recommendations for which models to move."""
        movable = self.get_movable_models()
        if not movable:
            return []
        
        # Sort by priority: largest first, but consider model type
        def priority_score(model: ModelInfo) -> float:
            type_priority = Config.MODEL_TYPE_PRIORITIES.get(model.type, 0)
            size_gb = model.size_gb
            
            # Larger files get higher priority, but adjust based on type
            # MLX models get lower priority (prefer to keep local for performance)
            if model.type == 'mlx_dir':
                return size_gb * 0.3  # Reduce priority for MLX
            else:
                return size_gb * (1 + type_priority * 0.1)
        
        return sorted(movable, key=priority_score, reverse=True)
    
    def check_symlink_health(self) -> Dict[str, any]:
        """Check health of all symlinked models."""
        results = {}
        usb_models = self.get_usb_models()
        
        for model in usb_models:
            health = check_symlink_health(model.path)
            results[model.name] = health
        
        return results
    
    def repair_broken_symlinks(self) -> List[str]:
        """Attempt to repair broken symlinks."""
        repaired = []
        health_check = self.check_symlink_health()
        
        for model_name, health in health_check.items():
            if health['is_broken']:
                model = self.get_model_by_name(model_name)
                if not model:
                    continue
                
                # Try to find the model on USB using proper structure
                if model.publisher:
                    expected_usb_path = self.usb_path / model.publisher / model.model_name
                else:
                    expected_usb_path = self.usb_path / model.model_name
                    
                if expected_usb_path.exists():
                    try:
                        # Remove broken symlink
                        if model.path.is_symlink():
                            model.path.unlink()
                        
                        # Create new symlink
                        model.path.symlink_to(expected_usb_path)
                        repaired.append(model_name)
                    except Exception:
                        pass
        
        return repaired
    
    def scan_usb_models(self) -> List[ModelInfo]:
        """Scan for models directly on the USB drive."""
        if not self.usb_available:
            return []
        
        usb_models = []
        
        for publisher_dir in self.usb_path.iterdir():
            if publisher_dir.name.startswith('.'):
                continue
            
            if publisher_dir.is_dir():
                # Check if this directory contains model subdirectories
                model_subdirs = [
                    d for d in publisher_dir.iterdir() 
                    if d.is_dir() and not d.name.startswith('.')
                ]
                
                if model_subdirs:
                    # This is a publisher directory with model subdirectories
                    for model_dir in model_subdirs:
                        try:
                            size = self._calculate_size(model_dir)
                            if size == 0:
                                continue  # Skip empty model directories
                            unique_name = f"{publisher_dir.name}/{model_dir.name}"
                            
                            model_info = ModelInfo(
                                name=unique_name,
                                path=model_dir,
                                size_bytes=size,
                                publisher=publisher_dir.name,
                                model_name=model_dir.name,
                                is_symlink=False,  # These are the actual files on USB
                                linked_to=None
                            )
                            usb_models.append(model_info)
                        except (OSError, PermissionError) as e:
                            print(f"⚠️  Skipping {publisher_dir.name}/{model_dir.name}: {e}")
                else:
                    # This might be a direct model directory (old structure)
                    # But first check if it's empty
                    try:
                        size = self._calculate_size(publisher_dir)
                        if size == 0:
                            continue  # Skip empty directories
                        unique_name = publisher_dir.name
                        
                        model_info = ModelInfo(
                            name=unique_name,
                            path=publisher_dir,
                            size_bytes=size,
                            publisher="",
                            model_name=publisher_dir.name,
                            is_symlink=False,
                            linked_to=None
                        )
                        usb_models.append(model_info)
                    except (OSError, PermissionError) as e:
                        print(f"⚠️  Skipping {publisher_dir.name}: {e}")
            else:
                # Handle single model files
                try:
                    size = self._calculate_size(publisher_dir)
                    unique_name = publisher_dir.name
                    
                    model_info = ModelInfo(
                        name=unique_name,
                        path=publisher_dir,
                        size_bytes=size,
                        publisher="",
                        model_name=publisher_dir.name,
                        is_symlink=False,
                        linked_to=None
                    )
                    usb_models.append(model_info)
                except (OSError, PermissionError) as e:
                    print(f"⚠️  Skipping {publisher_dir.name}: {e}")
        
        return usb_models
    
    def check_health(self) -> Dict[str, List[str]]:
        """Check health of all models and return issues found."""
        issues = {
            'broken_symlinks': [],
            'missing_targets': [],
            'empty_directories': []
        }
        
        for model_name, model in self._models.items():
            if model.is_symlink:
                # Check if symlink is broken
                health = check_symlink_health(model.path)
                if health['is_broken']:
                    issues['broken_symlinks'].append(model_name)
                elif health['target_exists']:
                    # Check if target directory is empty
                    target = model.path.resolve()
                    if target.is_dir():
                        files = list(target.rglob('*'))
                        total_files = len([f for f in files if f.is_file()])
                        if total_files == 0:
                            issues['empty_directories'].append(model_name)
        
        return issues
    
    def repair_broken_symlinks(self) -> Dict[str, str]:
        """Attempt to repair broken symlinks by removing them."""
        results = {}
        
        for model_name, model in self._models.items():
            if model.is_symlink:
                health = check_symlink_health(model.path)
                if health['is_broken']:
                    try:
                        model.path.unlink()
                        results[model_name] = "Removed broken symlink"
                        # Update model info
                        model.is_symlink = False
                        model.linked_to = None
                    except Exception as e:
                        results[model_name] = f"Failed to remove: {e}"
                elif not health['target_exists']:
                    try:
                        model.path.unlink()
                        results[model_name] = "Removed symlink to missing target"
                        # Update model info
                        model.is_symlink = False
                        model.linked_to = None
                    except Exception as e:
                        results[model_name] = f"Failed to remove: {e}"
        
        return results

    def refresh(self) -> None:
        """Refresh model information."""
        self._models.clear()
        self._check_paths()
        self._scan_models()
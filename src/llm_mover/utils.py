"""Utility functions for LLM model management."""

import hashlib
import os
import shutil
import fnmatch
import time
import platform
from pathlib import Path
from typing import Dict, Optional, Tuple, List, NamedTuple


class USBVerificationResult(NamedTuple):
    """Result of USB mount verification."""
    is_mounted: bool
    is_writable: bool
    has_space: bool
    error_message: str
    mount_type: str  # "not_mounted", "directory", "mount_point", "unknown"


def verify_usb_mounted(usb_path: Path, min_space_bytes: int = 1024 * 1024 * 100) -> USBVerificationResult:
    """
    Comprehensively verify that a USB drive is properly mounted and writable.
    
    Args:
        usb_path: Path to the USB mount directory
        min_space_bytes: Minimum required free space (default: 100MB)
    
    Returns:
        USBVerificationResult with detailed status information
    """
    try:
        # Check if path exists
        if not usb_path.exists():
            return USBVerificationResult(
                is_mounted=False, is_writable=False, has_space=False,
                error_message=f"USB path does not exist: {usb_path}",
                mount_type="not_mounted"
            )
        
        # Check if it's actually a mount point (not just a directory)
        is_mount_point = False
        mount_type = "directory"
        
        if platform.system() == "Darwin":  # macOS
            # On macOS, check if it's under /Volumes and is a mount point
            if str(usb_path).startswith('/Volumes/'):
                is_mount_point = os.path.ismount(str(usb_path))
                mount_type = "mount_point" if is_mount_point else "directory"
        else:
            # On Linux/other systems, check if it's a mount point
            is_mount_point = os.path.ismount(str(usb_path))
            mount_type = "mount_point" if is_mount_point else "directory"
        
        # If it's not a mount point and we're on macOS, it might be a subdirectory of a mount
        if not is_mount_point and platform.system() == "Darwin":
            # Check parent directories up to /Volumes/
            current = usb_path
            while str(current) != '/Volumes' and current != current.parent:
                if os.path.ismount(str(current)):
                    is_mount_point = True
                    mount_type = "mount_point"
                    break
                current = current.parent
        
        # Test write permissions and actual space
        test_file = usb_path / f".llm_mover_test_{os.getpid()}"
        is_writable = False
        has_space = False
        
        try:
            # Test write capability
            test_data = b"LLM_MOVER_TEST_" + str(int(time.time())).encode()
            with open(test_file, 'wb') as f:
                f.write(test_data)
                f.flush()
                os.fsync(f.fileno())  # Force write to disk
            
            # Verify we can read it back
            with open(test_file, 'rb') as f:
                read_data = f.read()
                if read_data == test_data:
                    is_writable = True
            
            # Check available space
            stat = shutil.disk_usage(usb_path)
            has_space = stat.free >= min_space_bytes
            
            # Clean up test file
            test_file.unlink()
            
        except (OSError, PermissionError) as e:
            # Clean up test file if it exists
            try:
                if test_file.exists():
                    test_file.unlink()
            except:
                pass
            
            error_msg = f"Cannot write to USB path: {e}"
            return USBVerificationResult(
                is_mounted=is_mount_point, is_writable=False, has_space=False,
                error_message=error_msg, mount_type=mount_type
            )
        
        # Determine final status
        if not is_mount_point:
            error_msg = f"Path exists but is not a mount point (may be local directory): {usb_path}"
        elif not is_writable:
            error_msg = f"USB is mounted but not writable: {usb_path}"
        elif not has_space:
            error_msg = f"USB is mounted but insufficient space (need {min_space_bytes:,} bytes): {usb_path}"
        else:
            error_msg = "USB is properly mounted and accessible"
        
        return USBVerificationResult(
            is_mounted=is_mount_point,
            is_writable=is_writable, 
            has_space=has_space,
            error_message=error_msg,
            mount_type=mount_type
        )
        
    except Exception as e:
        return USBVerificationResult(
            is_mounted=False, is_writable=False, has_space=False,
            error_message=f"USB verification failed: {e}",
            mount_type="unknown"
        )


def verify_file_integrity(source: Path, destination: Path) -> bool:
    """Verify that a file was copied correctly by comparing checksums."""
    if not source.exists() or not destination.exists():
        return False
    
    # For large files, we'll use a sampling approach
    source_size = source.stat().st_size
    dest_size = destination.stat().st_size
    
    if source_size != dest_size:
        return False
    
    # For very large files (>1GB), do a quick sampling check
    if source_size > 1024 * 1024 * 1024:  # 1GB
        return _verify_large_file(source, destination)
    
    # For smaller files, do full checksum
    return _calculate_checksum(source) == _calculate_checksum(destination)


def _verify_large_file(source: Path, destination: Path) -> bool:
    """Verify large files by sampling chunks."""
    try:
        with open(source, 'rb') as sf, open(destination, 'rb') as df:
            # Check first 1MB
            if sf.read(1024 * 1024) != df.read(1024 * 1024):
                return False
            
            # Check middle
            file_size = source.stat().st_size
            middle = file_size // 2
            sf.seek(middle)
            df.seek(middle)
            if sf.read(1024 * 1024) != df.read(1024 * 1024):
                return False
            
            # Check last 1MB
            sf.seek(-1024 * 1024, 2)
            df.seek(-1024 * 1024, 2)
            if sf.read() != df.read():
                return False
            
            return True
    except Exception:
        return False


def _calculate_checksum(file_path: Path, chunk_size: int = 8192) -> str:
    """Calculate MD5 checksum of a file."""
    hasher = hashlib.md5()
    try:
        with open(file_path, 'rb') as f:
            while chunk := f.read(chunk_size):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception:
        return ""


def _monitored_move(source: Path, destination: Path, monitor_usb_path: Optional[Path] = None) -> None:
    """Move files/directories with periodic USB monitoring during operation."""
    import shutil
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    # Track monitoring state
    monitoring_active = threading.Event()
    monitoring_active.set()
    usb_disconnected = threading.Event()
    
    def usb_monitor():
        """Monitor USB connection during the move operation."""
        if not monitor_usb_path:
            return
            
        while monitoring_active.is_set():
            try:
                usb_check = verify_usb_mounted(monitor_usb_path, min_space_bytes=0)
                if not (usb_check.is_mounted and usb_check.is_writable):
                    usb_disconnected.set()
                    break
                time.sleep(5)  # Check every 5 seconds
            except Exception:
                usb_disconnected.set()
                break
    
    # Start USB monitoring thread if requested
    monitor_thread = None
    if monitor_usb_path:
        monitor_thread = threading.Thread(target=usb_monitor, daemon=True)
        monitor_thread.start()
    
    try:
        # Perform the actual move
        if source.is_file():
            # For files, use shutil.move
            shutil.move(str(source), str(destination))
        else:
            # For directories, use shutil.copytree then remove source
            shutil.copytree(str(source), str(destination), dirs_exist_ok=True)
            # Check USB status periodically during removal
            if monitor_usb_path and usb_disconnected.is_set():
                raise RuntimeError("USB disconnected during move operation")
            shutil.rmtree(str(source))
        
        # Check for USB disconnection
        if monitor_usb_path and usb_disconnected.is_set():
            raise RuntimeError("USB disconnected during move operation")
            
    finally:
        # Stop monitoring
        monitoring_active.clear()
        if monitor_thread and monitor_thread.is_alive():
            monitor_thread.join(timeout=1)


def safe_move_with_verification(source: Path, destination: Path, monitor_usb_path: Optional[Path] = None) -> bool:
    """Safely move a file/directory with verification and rollback capability.
    
    Args:
        source: Source file/directory path
        destination: Destination file/directory path  
        monitor_usb_path: Optional USB path to monitor during operation
    """
    backup_suffix = ".backup_" + str(os.getpid())
    backup_path = None
    
    # Pre-operation USB check if monitoring requested
    if monitor_usb_path:
        usb_check = verify_usb_mounted(monitor_usb_path)
        if not (usb_check.is_mounted and usb_check.is_writable):
            raise RuntimeError(f"USB verification failed before operation: {usb_check.error_message}")
    
    try:
        # Create backup if destination exists
        if destination.exists():
            backup_path = Path(str(destination) + backup_suffix)
            shutil.move(str(destination), str(backup_path))
        
        # For large directories, use monitored move; for small files, use atomic move
        source_size = 0
        if source.is_file():
            source_size = source.stat().st_size
        elif source.is_dir():
            source_size = sum(f.stat().st_size for f in source.rglob('*') if f.is_file())
        
        # Use monitored move for large operations (>1GB) or when USB monitoring requested
        if (source_size > 1024 * 1024 * 1024) or monitor_usb_path:
            _monitored_move(source, destination, monitor_usb_path)
        else:
            # Use atomic move for smaller operations
            shutil.move(str(source), str(destination))
        
        # Verify the move
        if destination.is_file():
            # For files, check existence and non-zero size
            if not destination.exists() or destination.stat().st_size == 0:
                raise ValueError("Destination file is empty or doesn't exist")
        elif destination.is_dir():
            # For directories, check that they contain files and have reasonable total size
            if not destination.exists():
                raise ValueError("Destination directory doesn't exist")
            
            # Count files and calculate size
            files = list(destination.rglob('*'))
            total_files = len([f for f in files if f.is_file()])
            total_size = sum(f.stat().st_size for f in files if f.is_file())
            
            if total_files == 0:
                raise ValueError("Destination directory is empty (no files found)")
            if total_size == 0:
                raise ValueError("Destination directory has no content (total size is 0)")
        
        # Clean up backup if everything went well
        if backup_path and backup_path.exists():
            if backup_path.is_dir():
                shutil.rmtree(backup_path)
            else:
                backup_path.unlink()
        
        return True
        
    except Exception as e:
        # Attempt recovery
        try:
            # If destination exists, remove it
            if destination.exists():
                if destination.is_dir():
                    shutil.rmtree(destination)
                else:
                    destination.unlink()
            
            # Try to restore source from backup
            if backup_path and backup_path.exists():
                shutil.move(str(backup_path), str(source))
            
            # Restore original destination from backup
            if backup_path and not destination.exists():
                backup_path_check = Path(str(destination) + backup_suffix)
                if backup_path_check.exists():
                    shutil.move(str(backup_path_check), str(destination))
                    
        except Exception:
            pass  # Recovery failed, but we'll still raise the original error
        
        raise e


def safe_restore_from_usb(symlink_path: Path, usb_source: Path, local_destination: Path) -> bool:
    """Safely restore a model from USB to local storage, removing symlink."""
    backup_suffix = ".backup_" + str(os.getpid())
    backup_symlink = None
    
    try:
        # Validate input
        if not symlink_path.exists():
            raise ValueError("Symlink path doesn't exist")
        if not symlink_path.is_symlink():
            raise ValueError("Path is not a symlink")
        if not usb_source.exists():
            raise ValueError("USB source doesn't exist")
        if local_destination.exists() and not local_destination.is_symlink():
            raise ValueError("Local destination already exists and is not a symlink")
        
        # Create backup of symlink
        backup_symlink = Path(str(symlink_path) + backup_suffix)
        if backup_symlink.exists():
            backup_symlink.unlink()
        
        # Copy the symlink (as a regular backup) 
        shutil.copy2(str(symlink_path), str(backup_symlink), follow_symlinks=False)
        
        # Remove the symlink
        symlink_path.unlink()
        
        # Move from USB to local location
        shutil.move(str(usb_source), str(local_destination))
        
        # Verify the move
        if local_destination.is_file():
            # For files, check existence and non-zero size
            if not local_destination.exists() or local_destination.stat().st_size == 0:
                raise ValueError("Destination file is empty or doesn't exist")
        elif local_destination.is_dir():
            # For directories, check that they contain files and have reasonable total size
            if not local_destination.exists():
                raise ValueError("Destination directory doesn't exist")
            
            # Count files and calculate size
            files = list(local_destination.rglob('*'))
            total_files = len([f for f in files if f.is_file()])
            total_size = sum(f.stat().st_size for f in files if f.is_file())
            
            if total_files == 0:
                raise ValueError("Destination directory is empty (no files found)")
            if total_size == 0:
                raise ValueError("Destination directory has no content (total size is 0)")
        
        # Clean up backup if everything went well
        if backup_symlink and backup_symlink.exists():
            backup_symlink.unlink()
        
        return True
        
    except Exception as e:
        # Attempt recovery
        try:
            # If local destination exists, try to move it back to USB
            if local_destination.exists():
                if usb_source.parent.exists():  # Make sure USB parent dir still exists
                    shutil.move(str(local_destination), str(usb_source))
            
            # Restore symlink from backup if possible
            if backup_symlink and backup_symlink.exists():
                if symlink_path.exists():
                    symlink_path.unlink()  # Remove any partial symlink
                shutil.move(str(backup_symlink), str(symlink_path))
                    
        except Exception:
            pass  # Recovery failed, but we'll still raise the original error
        
        raise e


def safe_restore_internal_symlinks(model_directory: Path, usb_source_directory: Path) -> bool:
    """Safely restore a model with internal file symlinks by copying files from USB and removing symlinks."""
    try:
        # Find all symlink files in the model directory
        symlink_files = []
        for file_path in model_directory.rglob('*'):
            if file_path.is_file() and file_path.is_symlink():
                try:
                    target = file_path.resolve()
                    # Check if target is in the USB source directory
                    if target.parent == usb_source_directory:
                        symlink_files.append((file_path, target))
                except (OSError, RuntimeError):
                    # Broken symlink, skip
                    continue
        
        if not symlink_files:
            raise ValueError("No valid internal symlinks found to restore")
        
        # Create backup of symlinks and copy files from USB
        backups = []
        for symlink_path, usb_target in symlink_files:
            backup_path = Path(str(symlink_path) + f".backup_{os.getpid()}")
            
            try:
                # Backup the symlink
                shutil.copy2(str(symlink_path), str(backup_path), follow_symlinks=False)
                backups.append((symlink_path, backup_path))
                
                # Remove symlink
                symlink_path.unlink()
                
                # Copy file from USB to local location
                shutil.copy2(str(usb_target), str(symlink_path))
                
                # Verify the copy
                if not symlink_path.exists() or symlink_path.stat().st_size == 0:
                    raise ValueError(f"Failed to copy {usb_target.name}")
                
            except Exception as e:
                # Restore all backups created so far
                for backup_symlink, backup_file in backups:
                    try:
                        if backup_symlink.exists():
                            backup_symlink.unlink()
                        shutil.move(str(backup_file), str(backup_symlink))
                    except Exception:
                        pass
                raise e
        
        # Clean up backup files
        for _, backup_path in backups:
            if backup_path.exists():
                backup_path.unlink()
        
        # Now remove the files from USB
        for _, usb_target in symlink_files:
            try:
                usb_target.unlink()
            except Exception:
                # Non-critical if we can't clean up USB files
                pass
        
        # Try to remove empty USB directory
        try:
            if usb_source_directory.exists() and not any(usb_source_directory.iterdir()):
                usb_source_directory.rmdir()
        except Exception:
            # Non-critical if we can't remove directory
            pass
        
        return True
        
    except Exception as e:
        raise RuntimeError(f"Failed to restore internal symlinks: {e}")


def check_symlink_health(symlink_path: Path) -> Dict[str, any]:
    """Check if a symlink is healthy and points to a valid target."""
    result = {
        'is_symlink': False,
        'exists': symlink_path.exists(),
        'target_exists': False,
        'target_path': None,
        'is_broken': False,
        'size_match': False,
    }
    
    if not symlink_path.exists():
        return result
    
    if symlink_path.is_symlink():
        result['is_symlink'] = True
        try:
            target = symlink_path.readlink()
            result['target_path'] = target
            result['target_exists'] = target.exists()
            
            if not result['target_exists']:
                result['is_broken'] = True
            else:
                # Check if sizes match (rough validation)
                if symlink_path.is_file() and target.is_file():
                    result['size_match'] = symlink_path.stat().st_size == target.stat().st_size
                elif symlink_path.is_dir() and target.is_dir():
                    result['size_match'] = True  # Can't easily compare directory sizes
        except Exception:
            result['is_broken'] = True
    
    return result


def estimate_copy_time(size_bytes: int, dest_path: Path) -> Tuple[float, str]:
    """Estimate copy time based on file size and destination type."""
    # Test write speed to destination (write a small test file)
    test_file = dest_path / f".speed_test_{os.getpid()}"
    test_data = b"0" * (1024 * 1024)  # 1MB test
    
    try:
        import time
        start_time = time.time()
        with open(test_file, 'wb') as f:
            f.write(test_data)
            f.flush()
            os.fsync(f.fileno())  # Force write to disk
        end_time = time.time()
        
        # Clean up test file
        test_file.unlink()
        
        write_time = end_time - start_time
        if write_time > 0:
            mb_per_second = len(test_data) / (1024 * 1024) / write_time
            estimated_seconds = (size_bytes / (1024 * 1024)) / mb_per_second
            
            if estimated_seconds < 60:
                time_str = f"{estimated_seconds:.1f} seconds"
            elif estimated_seconds < 3600:
                time_str = f"{estimated_seconds/60:.1f} minutes"
            else:
                time_str = f"{estimated_seconds/3600:.1f} hours"
            
            return estimated_seconds, time_str
    except Exception:
        pass
    
    # Fallback estimates based on typical USB speeds
    # Assume ~50 MB/s for USB 3.0
    mb_size = size_bytes / (1024 * 1024)
    estimated_seconds = mb_size / 50  # 50 MB/s
    
    if estimated_seconds < 60:
        time_str = f"~{estimated_seconds:.1f} seconds"
    elif estimated_seconds < 3600:
        time_str = f"~{estimated_seconds/60:.1f} minutes"
    else:
        time_str = f"~{estimated_seconds/3600:.1f} hours"
    
    return estimated_seconds, time_str


def get_available_space(path: Path) -> Optional[int]:
    """Get available space on the filesystem containing the path."""
    try:
        stat = shutil.disk_usage(path)
        return stat.free
    except Exception:
        return None


def format_bytes(bytes_size: int) -> str:
    """Format bytes as human-readable string."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_size < 1024:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024
    return f"{bytes_size:.1f} PB"


def get_large_files(directory: Path, size_threshold_bytes: int) -> List[Path]:
    """Get all files in directory above size threshold."""
    large_files = []
    
    if not directory.is_dir():
        return large_files
    
    try:
        for file_path in directory.rglob('*'):
            if file_path.is_file() and file_path.stat().st_size >= size_threshold_bytes:
                large_files.append(file_path)
    except (OSError, PermissionError):
        pass  # Skip files we can't access
    
    return large_files


def should_keep_local(file_path: Path, keep_patterns: List[str]) -> bool:
    """Check if a file should be kept local based on patterns."""
    file_name = file_path.name
    
    for pattern in keep_patterns:
        if fnmatch.fnmatch(file_name, pattern):
            return True
    
    return False


def create_file_symlinks(model_directory: Path, usb_directory: Path, 
                        files_to_move: List[Path]) -> Dict[str, str]:
    """Create symlinks for specific files in a model directory.
    
    Returns:
        Dict mapping local file path to result status
    """
    results = {}
    backup_suffix = f".backup_{os.getpid()}"
    
    for file_path in files_to_move:
        try:
            # Calculate relative path within model directory
            relative_path = file_path.relative_to(model_directory)
            usb_target = usb_directory / relative_path
            
            # Ensure USB target directory exists
            usb_target.parent.mkdir(parents=True, exist_ok=True)
            
            # Create backup of original file
            backup_path = Path(str(file_path) + backup_suffix)
            if backup_path.exists():
                backup_path.unlink()
            
            # Move file to USB
            shutil.move(str(file_path), str(usb_target))
            
            # Create symlink in original location
            file_path.symlink_to(usb_target)
            
            results[str(file_path)] = "Success"
            
        except Exception as e:
            results[str(file_path)] = f"Failed: {e}"
            
            # Try to recover by moving file back if it exists on USB
            try:
                if usb_target.exists() and not file_path.exists():
                    shutil.move(str(usb_target), str(file_path))
            except Exception:
                pass  # Recovery failed
    
    return results


def safe_move_with_file_symlinks(model_directory: Path, usb_directory: Path,
                                files_to_move: List[Path], keep_local_files: List[Path]) -> bool:
    """Safely move selected files to USB with symlinks, keeping others local."""
    backup_suffix = f".backup_{os.getpid()}"
    moved_files = []
    created_symlinks = []
    
    try:
        # Ensure USB directory exists
        usb_directory.mkdir(parents=True, exist_ok=True)
        
        # Move files and create symlinks
        for file_path in files_to_move:
            # Calculate relative path within model directory
            relative_path = file_path.relative_to(model_directory)
            usb_target = usb_directory / relative_path
            
            # Ensure USB target directory exists
            usb_target.parent.mkdir(parents=True, exist_ok=True)
            
            # Move file to USB
            shutil.move(str(file_path), str(usb_target))
            moved_files.append((file_path, usb_target))
            
            # Create symlink in original location
            file_path.symlink_to(usb_target)
            created_symlinks.append(file_path)
            
            # Verify the symlink works
            if not file_path.exists() or not file_path.is_symlink():
                raise RuntimeError(f"Symlink verification failed for {file_path}")
        
        # Verify all files are accessible
        for file_path in files_to_move:
            if not file_path.exists():
                raise RuntimeError(f"File not accessible after move: {file_path}")
        
        return True
        
    except Exception as e:
        # Recovery: try to restore all moved files
        for symlink_path in created_symlinks:
            try:
                if symlink_path.is_symlink():
                    symlink_path.unlink()
            except Exception:
                pass
        
        for file_path, usb_target in moved_files:
            try:
                if usb_target.exists() and not file_path.exists():
                    shutil.move(str(usb_target), str(file_path))
            except Exception:
                pass
        
        raise RuntimeError(f"Failed to create file symlinks: {e}")
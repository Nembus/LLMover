"""Main CLI interface for LLM Model Mover."""

import shutil
import sys
from typing import List

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import track
from rich.prompt import Confirm
from rich.table import Table
from rich.text import Text

from .models import ModelInfo, ModelManager
from .config import ConfigManager


console = Console()


def display_usb_error(manager: ModelManager) -> None:
    """Display detailed USB error message based on verification results."""
    verification = manager.usb_verification
    if not verification:
        console.print("\n[red]❌ USB storage status unknown. Please check your USB connection.[/red]")
        return
    
    if not verification.is_mounted:
        if verification.mount_type == "not_mounted":
            console.print("\n[red]❌ USB drive not connected.[/red]")
            console.print("[dim]💡 Please connect your USB stick to continue.[/dim]")
        elif verification.mount_type == "directory":
            console.print("\n[red]❌ USB path exists but drive is not properly mounted.[/red]")
            console.print(f"[dim]Path: {manager.usb_path}[/dim]")
            console.print("[dim]💡 This may be a local directory instead of a USB mount point.[/dim]")
        else:
            console.print(f"\n[red]❌ USB mount verification failed: {verification.error_message}[/red]")
    elif not verification.is_writable:
        console.print("\n[red]❌ USB drive is connected but not writable.[/red]")
        console.print("[dim]💡 Check if the USB stick is write-protected or full.[/dim]")
    elif not verification.has_space:
        console.print("\n[red]❌ USB drive is connected but has insufficient space.[/red]")
        console.print("[dim]💡 Free up space on the USB stick and try again.[/dim]")
    else:
        console.print(f"\n[red]❌ USB error: {verification.error_message}[/red]")



def format_size(bytes_size: int) -> str:
    """Format bytes as human-readable size."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_size < 1024:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024
    return f"{bytes_size:.1f} PB"


def display_model_table(models: List[ModelInfo], title: str) -> None:
    """Display models in a formatted table."""
    if not models:
        console.print(f"📭 No {title.lower()} found.")
        return
    
    table = Table(title=title, show_header=True, header_style="bold magenta")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Model Name", style="white")
    table.add_column("Type", style="blue")
    table.add_column("Size", style="green", justify="right")
    table.add_column("Status", style="yellow")
    
    for idx, model in enumerate(models, 1):
        # Determine status based on context - if title contains "USB" or "External", show USB status
        if "USB" in title or "External" in title:
            status = "💽 On USB"
        else:
            status = "📎 On USB" if model.is_symlink else "💾 Local"
            
        type_icon = {
            "single_file": "📄",
            "gguf_dir": "🗂️",
            "mlx_dir": "🍎",
            "other_dir": "📁",
            "unknown": "❓"
        }.get(model.type, "❓")
        
        table.add_row(
            str(idx),
            model.display_name,
            f"{type_icon} {model.type}",
            format_size(model.size_bytes),
            status
        )
    
    console.print(table)


def display_space_info(manager: ModelManager) -> None:
    """Display storage space information."""
    local_models = manager.get_movable_models()
    usb_models = manager.get_usb_models()
    
    local_size = sum(model.size_bytes for model in local_models)
    usb_size = sum(model.size_bytes for model in usb_models)
    
    space_info = manager.get_usb_space_info()
    
    info_text = Text()
    info_text.append("💾 Local Models: ", style="bold")
    info_text.append(f"{len(local_models)} models, {format_size(local_size)}\n")
    info_text.append("📎 USB Models: ", style="bold")
    info_text.append(f"{len(usb_models)} models, {format_size(usb_size)}\n")
    
    if manager.usb_available:
        info_text.append("💽 USB Storage: ", style="bold")
        info_text.append(f"{format_size(space_info['free'])} free / {format_size(space_info['total'])} total")
    else:
        info_text.append("⚠️  USB Storage: ", style="bold red")
        info_text.append("Not Available")
    
    console.print(Panel(info_text, title="Storage Overview"))


def select_models_to_move(models: List[ModelInfo]) -> List[ModelInfo]:
    """Allow user to select which models to move."""
    if not models:
        return []
    
    console.print("\n🎯 Select models to move to USB:")
    console.print("Enter model IDs separated by commas, ranges (e.g., 1-3), or 'all'")
    console.print("Example: 1,3,5-7 or all")
    
    display_model_table(models, "Available Models to Move")
    
    while True:
        try:
            selection = console.input("\n[bold cyan]Select models[/bold cyan]: ").strip()
            
            if not selection:
                return []
            
            if selection.lower() == 'all':
                return models
            
            selected_indices = set()
            
            for part in selection.split(','):
                part = part.strip()
                
                if '-' in part and part.count('-') == 1:
                    # Range selection
                    start, end = map(int, part.split('-'))
                    selected_indices.update(range(start, end + 1))
                else:
                    # Single selection
                    selected_indices.add(int(part))
            
            # Validate indices
            valid_indices = {i for i in selected_indices if 1 <= i <= len(models)}
            invalid_indices = selected_indices - valid_indices
            
            if invalid_indices:
                console.print(f"[red]Invalid selection(s): {sorted(invalid_indices)}[/red]")
                continue
            
            if not valid_indices:
                return []
            
            selected_models = [models[i - 1] for i in sorted(valid_indices)]
            
            # Show selection summary
            total_size = sum(model.size_bytes for model in selected_models)
            console.print(f"\n✅ Selected {len(selected_models)} model(s), total size: {format_size(total_size)}")
            
            return selected_models
            
        except (ValueError, IndexError):
            console.print("[red]Invalid input. Please try again.[/red]")
        except KeyboardInterrupt:
            console.print("\n[yellow]Selection cancelled.[/yellow]")
            return []


def select_models_to_bring_back(models: List[ModelInfo]) -> List[ModelInfo]:
    """Allow user to select which models to bring back from USB."""
    if not models:
        return []
    
    console.print("\n🎯 Select models to bring back to local storage:")
    console.print("Enter model IDs separated by commas, ranges (e.g., 1-3), or 'all'")
    console.print("Example: 1,3,5-7 or all")
    console.print("[dim]💡 This will move models from USB back to local SSD/storage[/dim]")
    
    display_model_table(models, "USB Models Available to Bring Back")
    
    while True:
        try:
            selection = console.input("\n[bold cyan]Select models to bring back[/bold cyan]: ").strip()
            
            if not selection:
                return []
            
            if selection.lower() == 'all':
                return models
            
            selected_indices = set()
            
            for part in selection.split(','):
                part = part.strip()
                
                if '-' in part and part.count('-') == 1:
                    # Range selection
                    start, end = map(int, part.split('-'))
                    selected_indices.update(range(start, end + 1))
                else:
                    # Single selection
                    selected_indices.add(int(part))
            
            # Validate indices
            valid_indices = {i for i in selected_indices if 1 <= i <= len(models)}
            invalid_indices = selected_indices - valid_indices
            
            if invalid_indices:
                console.print(f"[red]Invalid selection(s): {sorted(invalid_indices)}[/red]")
                continue
            
            if not valid_indices:
                return []
            
            selected_models = [models[i - 1] for i in sorted(valid_indices)]
            
            # Show selection summary
            total_size = sum(model.size_bytes for model in selected_models)
            console.print(f"\n✅ Selected {len(selected_models)} model(s), total size: {format_size(total_size)}")
            
            return selected_models
            
        except (ValueError, IndexError):
            console.print("[red]Invalid input. Please try again.[/red]")
        except KeyboardInterrupt:
            console.print("\n[yellow]Selection cancelled.[/yellow]")
            return []


@click.command()
@click.option(
    '--local-path', '-l',
    default=None,
    help='Override local models directory path'
)
@click.option(
    '--usb-path', '-u', 
    default=None,
    help='Override USB models directory path'
)
@click.option('--list-only', '-ls', is_flag=True, help='Only list models, don\'t move anything')
@click.option('--show-external', '-se', is_flag=True, help='Show models on external USB storage')
@click.option('--check-health', '-ch', is_flag=True, help='Check health of symlinks and models')
@click.option('--repair', '-r', is_flag=True, help='Repair broken symlinks')
@click.option('--bring-back', '-bb', is_flag=True, help='Move models from USB back to local storage')
@click.option('--verbose', '-v', is_flag=True, help='Verbose output')
def main(local_path: str, usb_path: str, list_only: bool, show_external: bool, check_health: bool, repair: bool, bring_back: bool, verbose: bool):
    """LLM Model Mover - Move models from local storage to USB stick with symlink creation."""
    
    # Initialize configuration manager
    config_manager = ConfigManager()
    config_manager.load_config()
    
    # Override config paths with CLI options if provided
    if local_path:
        console.print(f"[dim]Using CLI override for local path: {local_path}[/dim]")
    else:
        local_path = str(config_manager.get_local_path())
    
    if usb_path:
        console.print(f"[dim]Using CLI override for USB path: {usb_path}[/dim]")
    else:
        usb_path = str(config_manager.get_usb_path())
    
    console.print(Panel.fit(
        "[bold blue]🚀 LLM Model Mover[/bold blue]\n"
        "Move models to USB stick and create symlinks for LM Studio",
        border_style="blue"
    ))
    
    try:
        # Initialize model manager
        with console.status("[bold green]Scanning models...", spinner="dots"):
            manager = ModelManager(local_path, usb_path, config_manager)
        
        # Handle health check flag
        if check_health:
            with console.status("[bold yellow]Checking model health...", spinner="dots"):
                issues = manager.check_health()
            
            if any(issues.values()):
                console.print("\n[yellow]⚠️  Health Check Results:[/yellow]")
                
                if issues['broken_symlinks']:
                    console.print(f"[red]❌ Broken symlinks ({len(issues['broken_symlinks'])}):[/red]")
                    for model in issues['broken_symlinks']:
                        console.print(f"  • {model}")
                
                if issues['empty_directories']:
                    console.print(f"[orange]⚠️  Empty USB directories ({len(issues['empty_directories'])}):[/orange]")  
                    for model in issues['empty_directories']:
                        console.print(f"  • {model}")
                        
                if issues['missing_targets']:
                    console.print(f"[red]❌ Missing targets ({len(issues['missing_targets'])}):[/red]")
                    for model in issues['missing_targets']:
                        console.print(f"  • {model}")
                        
                console.print("\n[dim]Use --repair to attempt fixing broken symlinks[/dim]")
            else:
                console.print("\n[green]✅ All models are healthy![/green]")
            return
        
        # Handle repair flag  
        if repair:
            console.print("[yellow]Repairing broken symlinks...[/yellow]")
            results = manager.repair_broken_symlinks()
            
            if results:
                console.print("\n[yellow]🔧 Repair Results:[/yellow]")
                for model, result in results.items():
                    if "Failed" in result:
                        console.print(f"[red]❌ {model}: {result}[/red]")
                    else:
                        console.print(f"[green]✅ {model}: {result}[/green]")
                        
                # Refresh model info after repairs
                manager.refresh()
            else:
                console.print("[green]✅ No repairs needed![/green]")
            return

        # Handle bring-back flag
        if bring_back:
            if verbose:
                console.print(f"\n[dim]USB path: {manager.usb_path}[/dim]")
            
            if not manager.usb_available:
                display_usb_error(manager)
                return
            
            # Get USB models that can be brought back (currently symlinked)
            usb_models = manager.get_usb_models()
            
            if not usb_models:
                console.print("\n[yellow]📭 No models found on USB to bring back.[/yellow]")
                console.print("[dim]💡 Use --show-external to see what's actually on the USB drive[/dim]")
                return
            
            console.print("\n🔄 Models Currently on USB (available to bring back):")
            display_model_table(usb_models, "USB Models")
            
            # Get local storage info
            local_stat = shutil.disk_usage(manager.local_path)
            local_free_gb = local_stat.free / (1024**3)
            console.print(f"\n💾 Local storage available: {format_size(local_stat.free)}")
            
            # Let user select models to bring back
            selected_models = select_models_to_bring_back(usb_models)
            
            if not selected_models:
                console.print("[yellow]No models selected. Exiting.[/yellow]")
                return
            
            # Check local storage space
            total_selected_size = sum(model.size_bytes for model in selected_models)
            
            if total_selected_size > local_stat.free:
                console.print(f"\n[red]❌ Insufficient local storage space![/red]")
                console.print(f"Required: {format_size(total_selected_size)}")
                console.print(f"Available: {format_size(local_stat.free)}")
                return
            
            # Final confirmation
            console.print(f"\n🏠 About to bring back {len(selected_models)} model(s) from USB to local storage:")
            for model in selected_models:
                console.print(f"  • {model.display_name} ({format_size(model.size_bytes)})")
            
            console.print(f"\n📊 This will use {format_size(total_selected_size)} of local storage")
            console.print(f"💽 This will free up {format_size(total_selected_size)} on USB")
            
            if not Confirm.ask("\nProceed with bringing back models?", default=True):
                console.print("[yellow]Operation cancelled.[/yellow]")
                return
            
            # Bring back models
            console.print("\n🏠 Starting model recovery from USB...")
            
            success_count = 0
            for model in track(selected_models, description="Bringing back models..."):
                try:
                    console.print(f"\n📦 Bringing back {model.display_name}...")
                    manager.move_model_from_usb(model.name)
                    console.print(f"✅ Successfully brought back {model.display_name}")
                    success_count += 1
                    
                except Exception as e:
                    console.print(f"[red]❌ Failed to bring back {model.display_name}: {e}[/red]")
                    
                    # Ask if user wants to continue
                    if len(selected_models) > 1 and not Confirm.ask("Continue with remaining models?", default=True):
                        break
            
            # Summary
            console.print(f"\n🎉 Recovery complete!")
            console.print(f"✅ Successfully brought back: {success_count}/{len(selected_models)} models")
            
            if success_count > 0:
                recovered_space = sum(model.size_bytes for model in selected_models[:success_count])
                console.print(f"💾 Local space used: {format_size(recovered_space)}")
                console.print(f"💽 USB space freed: {format_size(recovered_space)}")
            
            console.print("\n[dim]💡 Your models are now stored locally and no longer require the USB stick.[/dim]")
            return

        # Handle show-external flag
        if show_external:
            if verbose:
                console.print(f"\n[dim]USB path: {manager.usb_path}[/dim]")
            
            if not manager.usb_available:
                display_usb_error(manager)
                return
            
            # Scan and display USB models
            with console.status("[bold green]Scanning USB models...", spinner="dots"):
                usb_models = manager.scan_usb_models()
            
            if usb_models:
                display_model_table(usb_models, "Models on External USB Storage")
                
                # Show USB storage info
                space_info = manager.get_usb_space_info()
                total_size = sum(model.size_bytes for model in usb_models)
                
                info_text = Text()
                info_text.append("📎 USB Models: ", style="bold")
                info_text.append(f"{len(usb_models)} models, {format_size(total_size)}\n")
                info_text.append("💽 USB Storage: ", style="bold")
                info_text.append(f"{format_size(space_info['free'])} free / {format_size(space_info['total'])} total")
                
                console.print(Panel(info_text, title="USB Storage Overview"))
            else:
                console.print("[yellow]📭 No models found on USB storage.[/yellow]")
            
            return
        
        # Display overview
        display_space_info(manager)
        
        # Get available models
        movable_models = manager.get_movable_models()
        usb_models = manager.get_usb_models()
        
        if verbose:
            console.print(f"\n[dim]Local path: {manager.local_path}[/dim]")
            console.print(f"[dim]USB path: {manager.usb_path}[/dim]")
        
        # Display current models
        if usb_models:
            console.print("\n")
            display_model_table(usb_models, "Models Already on USB")
        
        if movable_models:
            console.print("\n")
            display_model_table(movable_models, "Local Models Available to Be Moved")
        else:
            console.print("\n[green]✅ All models are already on USB![/green]")
            return
        
        # Stop here if list-only mode
        if list_only:
            return
        
        # Check if USB is available
        if not manager.usb_available:
            display_usb_error(manager)
            return
        
        # Ask user what to do
        console.print("\n" + "="*60)
        
        if not movable_models:
            console.print("[green]All models are already on USB![/green]")
            return
        
        # Let user select models to move
        selected_models = select_models_to_move(movable_models)
        
        if not selected_models:
            console.print("[yellow]No models selected. Exiting.[/yellow]")
            return
        
        # Check USB space
        total_selected_size = sum(model.size_bytes for model in selected_models)
        space_info = manager.get_usb_space_info()
        
        if total_selected_size > space_info['free']:
            console.print(f"[red]❌ Insufficient USB space![/red]")
            console.print(f"Required: {format_size(total_selected_size)}")
            console.print(f"Available: {format_size(space_info['free'])}")
            return
        
        # Final confirmation
        console.print(f"\n🚚 About to move {len(selected_models)} model(s) to USB:")
        for model in selected_models:
            console.print(f"  • {model.display_name} ({format_size(model.size_bytes)})")
        
        if not Confirm.ask("\nProceed with moving models?", default=True):
            console.print("[yellow]Operation cancelled.[/yellow]")
            return
        
        # Move models
        console.print("\n🚀 Starting model migration...")
        
        success_count = 0
        for model in track(selected_models, description="Moving models..."):
            try:
                console.print(f"\n📦 Moving {model.display_name}...")
                manager.move_model_to_usb(model.name)
                console.print(f"✅ Successfully moved {model.display_name}")
                success_count += 1
                
            except Exception as e:
                console.print(f"[red]❌ Failed to move {model.display_name}: {e}[/red]")
                
                # Ask if user wants to continue
                if len(selected_models) > 1 and not Confirm.ask("Continue with remaining models?", default=True):
                    break
        
        # Summary
        console.print(f"\n🎉 Migration complete!")
        console.print(f"✅ Successfully moved: {success_count}/{len(selected_models)} models")
        
        if success_count > 0:
            saved_space = sum(model.size_bytes for model in selected_models[:success_count])
            console.print(f"💾 Local space saved: {format_size(saved_space)}")
        
        console.print("\n[dim]💡 Your models are now stored on the USB stick but remain accessible in LM Studio through symlinks.[/dim]")
        
    except KeyboardInterrupt:
        console.print("\n[yellow]Operation cancelled by user.[/yellow]")
        sys.exit(1)
    except Exception as e:
        console.print(f"\n[red]❌ Error: {e}[/red]")
        if verbose:
            console.print_exception()
        sys.exit(1)


if __name__ == '__main__':
    main()
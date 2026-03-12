"""
report.py — Terminal output using rich. Clean, developer-friendly diagnostic report.
"""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box
from rich.rule import Rule

console = Console()

BRAND = "[bold cyan]docker-compose-doctor[/bold cyan]"
OK = "[bold green]✓[/bold green]"
WARN = "[bold yellow]⚠[/bold yellow]"
ERR = "[bold red]✗[/bold red]"
INFO = "[dim]→[/dim]"


def print_header(compose_file: str, project_name: str, has_explicit_name: bool):
    console.print()
    console.print(Panel(
        f"{BRAND}  [dim]v0.1.0 — local dev environment diagnostics[/dim]",
        border_style="cyan",
        padding=(0, 2)
    ))
    console.print(f"  [dim]file:[/dim]    {compose_file}")
    console.print(f"  [dim]project:[/dim] [bold]{project_name}[/bold]", end="")
    if has_explicit_name:
        console.print("  [dim](explicitly set via name:)[/dim]")
    else:
        console.print("  [dim](inferred from directory name)[/dim]")
    console.print()


# ─── Fix Reporting ─────────────────────────────────────────────────────────────

def print_fix_header(dry_run: bool = False):
    mode = "[bold yellow]DRY RUN:[/bold yellow] " if dry_run else ""
    console.print()
    console.print(Rule(f"{mode}Applying automated fixes"))
    console.print()


def print_fix_result(operation: str, result: dict):
    """Print the result of a fix operation."""
    if result.get('success'):
        if result.get('dry_run'):
            console.print(f"  {WARN} {operation} [dim](dry run)[/dim]")
            if 'preview' in result:
                console.print(f"    {result['preview']}")
            console.print(f"    [dim]{result['message']}[/dim]")
        else:
            console.print(f"  {OK} {operation}")
            if 'backup' in result:
                console.print(f"    [dim]Backup: {result['backup']}[/dim]")
            console.print(f"    {result['message']}")
    else:
        console.print(f"  {ERR} {operation}")
        console.print(f"    {result['message']}")
        if 'error' in result:
            console.print(f"    [dim red]{result['error']}[/dim red]")


def print_fix_footer():
    console.print()
    console.print(Rule("Fixes applied"))
    console.print("[dim green]✓ All safe fixes applied. Restart your containers to use the restored volumes.[/dim green]")
    console.print()


def print_volume_drift_report(drift):
    console.print(Rule("[bold]Named Volume Check[/bold]", style="dim"))
    console.print()

    if not drift.expected_volumes:
        console.print(f"  {INFO} No named volumes declared in compose file.")
        console.print()
        return

    if not drift.has_drift:
        for vol in drift.expected_volumes:
            console.print(f"  {OK} [green]{vol}[/green]")
        console.print()
        return

    # Show missing volumes
    for vol in drift.missing_volumes:
        console.print(f"  {ERR} [red]{vol}[/red]  [dim]— not found in Docker[/dim]")

    console.print()

    # Show orphaned candidates
    if drift.orphaned_volumes:
        console.print(f"  {WARN} [yellow]Orphaned volumes found — possible project name drift:[/yellow]")
        for ov in drift.orphaned_volumes:
            console.print(f"      [dim]•[/dim] {ov.name}  [dim]({ov.mountpoint})[/dim]")
        console.print()

    if drift.candidate_old_names:
        best = drift.candidate_old_names[0]
        console.print(f"  [bold yellow]Likely old project name:[/bold yellow] [yellow]{best}[/yellow]")
        console.print()

    # Fix options
    console.print(f"  [bold]Fix options:[/bold]")
    console.print()

    console.print(f"  [cyan]Option A[/cyan] — [bold]Fastest[/bold]. Lock the project name in your compose file:")
    console.print(f"  [dim]  Add this to the top of docker-compose.yml:[/dim]")
    if drift.candidate_old_names:
        old = drift.candidate_old_names[0]
        console.print(f"\n    [green]name: {old}[/green]\n")
        console.print(f"  [dim]  This makes Docker Compose use your old volume data immediately.[/dim]")
        console.print(f"  [dim]  No data movement required.[/dim]")

    console.print()

    if drift.fix_option_b:
        console.print(f"  [cyan]Option B[/cyan] — [bold]Clean migration[/bold]. Copy old volumes to new project name:")
        for old_vol, new_vol in drift.fix_option_b:
            console.print(f"  [dim]  •[/dim] {old_vol} → {new_vol}")
        console.print()
        console.print(f"  [dim]  Run this for each pair:[/dim]")
        for old_vol, new_vol in drift.fix_option_b[:1]:
            console.print(f"""
    [green]docker run --rm \\
      -v {old_vol}:/from \\
      -v {new_vol}:/to \\
      alpine sh -c "cp -av /from/. /to/"[/green]
""")

    console.print()


def print_bind_mount_report(issues):
    console.print(Rule("[bold]Bind Mount Path Check[/bold]", style="dim"))
    console.print()

    if not issues:
        console.print(f"  {INFO} No bind mounts declared.")
        console.print()
        return

    all_ok = all(i.exists for i in issues)

    for issue in issues:
        if issue.exists:
            console.print(f"  {OK} [green]{issue.resolved_path}[/green]  [dim]({issue.service})[/dim]")
        else:
            console.print(f"  {ERR} [red]{issue.resolved_path}[/red]  [dim]({issue.service})[/dim]")
            console.print(f"      [dim]path does not exist on disk[/dim]")
            if issue.suggestions:
                console.print(f"      [yellow]Closest matches:[/yellow]")
                for s in issue.suggestions:
                    console.print(f"      [dim]  →[/dim] {s}")

    console.print()


def print_summary(drift, path_issues):
    console.print(Rule("[bold]Summary[/bold]", style="dim"))
    console.print()

    volume_ok = not drift.has_drift
    paths_ok = all(i.exists for i in path_issues)

    if volume_ok and paths_ok:
        console.print(Panel(
            f"{OK} [bold green]All checks passed.[/bold green] Your Docker Compose environment looks healthy.",
            border_style="green",
            padding=(0, 2)
        ))
    else:
        issues_found = []
        if not volume_ok:
            issues_found.append(f"{len(drift.missing_volumes)} missing volume(s) — likely project name drift")
        broken_paths = [i for i in path_issues if not i.exists]
        if broken_paths:
            issues_found.append(f"{len(broken_paths)} broken bind mount path(s)")

        body = "\n".join(f"  {ERR} {i}" for i in issues_found)
        body += f"\n\n  [dim]Run with [bold]--fix[/bold] to apply automated corrections (coming in v0.2)[/dim]"

        console.print(Panel(
            body,
            title="[bold red]Issues Found[/bold red]",
            border_style="red",
            padding=(0, 2)
        ))

    console.print()

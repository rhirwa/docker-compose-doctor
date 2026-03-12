"""
cli.py — docker-compose-doctor entry point.
Usage: docker-compose-doctor [-f compose_file] [--fix] [--dry-run] [--migrate-volumes]
"""

import argparse
import os
import sys

from parser import parse_compose_file
from volume_inspector import list_docker_volumes, detect_volume_drift
from path_inspector import inspect_bind_mounts
from fix_engine import inject_project_name, patch_bind_mount_paths, migrate_volumes
import report


def find_compose_file(start_dir: str) -> str | None:
    """Search current and parent directories for a compose file."""
    candidates = ['docker-compose.yml', 'docker-compose.yaml', 'compose.yml', 'compose.yaml']
    current = os.path.abspath(start_dir)
    for _ in range(4):  # max 4 levels up
        for name in candidates:
            path = os.path.join(current, name)
            if os.path.isfile(path):
                return path
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return None


def main():
    parser = argparse.ArgumentParser(
        prog='docker-compose-doctor',
        description='Diagnose and fix Docker Compose volume drift and broken bind mount paths.'
    )
    parser.add_argument(
        '-f', '--file',
        help='Path to docker-compose.yml (default: auto-detect)',
        default=None
    )
    parser.add_argument(
        '--fix',
        action='store_true',
        help='Auto-apply safe fixes: inject name: and patch bind mount paths'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what --fix would change without touching any files'
    )
    parser.add_argument(
        '--migrate-volumes',
        action='store_true',
        help='Copy orphaned volumes to new project name (Option B)'
    )
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output results as JSON'
    )
    args = parser.parse_args()

    if args.dry_run:
        args.fix = True

    # Locate compose file
    compose_path = args.file
    if not compose_path:
        compose_path = find_compose_file(os.getcwd())

    if not compose_path or not os.path.isfile(compose_path):
        report.console.print("[bold red]Error:[/bold red] No docker-compose.yml found. Use -f to specify a path.")
        sys.exit(1)

    compose_path = os.path.abspath(compose_path)

    # Parse
    try:
        project = parse_compose_file(compose_path)
    except Exception as e:
        report.console.print(f"[bold red]Error parsing compose file:[/bold red] {e}")
        sys.exit(1)

    report.print_header(
        compose_file=compose_path,
        project_name=project.effective_name,
        has_explicit_name=project.has_explicit_name
    )

    # Volume drift check
    all_volumes = list_docker_volumes()
    drift = detect_volume_drift(project, all_volumes)
    report.print_volume_drift_report(drift)

    # Bind mount path check
    path_issues = inspect_bind_mounts(project.bind_mounts)
    report.print_bind_mount_report(path_issues)

    has_issues = drift.has_drift or drift.orphaned_volumes or any(not i.exists for i in path_issues)
    report.print_summary(drift, path_issues)

    if args.fix and has_issues:
        report.print_fix_header(dry_run=args.dry_run)

        if drift.orphaned_volumes and drift.candidate_old_names:
            # Use the best candidate (first in list)
            old_project_name = drift.candidate_old_names[0]
            result = inject_project_name(compose_path, old_project_name, dry_run=args.dry_run)
            report.print_fix_result("Inject name:", result)

        broken_paths = [i for i in path_issues if not i.exists]
        if broken_paths:
            result = patch_bind_mount_paths(compose_path, path_issues, dry_run=args.dry_run)
            report.print_fix_result("Patch bind mount paths", result)

        if args.migrate_volumes and drift.orphaned_volumes:
            report.console.print()
            report.console.print("  [bold cyan]Migrating volumes...[/bold cyan]")
            # Build fix option B pairs
            fix_b_pairs = []
            old_project = drift.candidate_old_names[0] if drift.candidate_old_names else None
            if old_project:
                for vol_name in [v.name for v in project.named_volumes if not v.external]:
                    old_vol = f"{old_project}_{vol_name}"
                    new_vol = f"{drift.current_project}_{vol_name}"
                    fix_b_pairs.append((old_vol, new_vol))
            
            if fix_b_pairs:
                results = migrate_volumes(fix_b_pairs, dry_run=args.dry_run)
                for r in results:
                    report.print_fix_result(f"Copy {r['old']} → {r['new']}", r)

        if not args.dry_run:
            report.print_fix_footer()

    elif args.fix and not has_issues:
        report.console.print("  [green]Nothing to fix — environment is healthy.[/green]\n")

    if has_issues and not args.fix:
        sys.exit(1)
    sys.exit(0)


if __name__ == '__main__':
    main()

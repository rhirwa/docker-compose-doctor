"""
fix_engine.py — Apply automated fixes for Docker Compose drift.

Option A: Inject `name:` into compose file (instant, no data movement)
Option B: Copy orphaned volumes to new project name via alpine container
Option C: Patch broken bind mount paths in compose file
"""

import os
import re
import subprocess
import shutil
from datetime import datetime
from pathlib import Path

import yaml


# ─── Backup ───────────────────────────────────────────────────────────────────

def backup_compose_file(compose_path: str) -> str:
    """Create a timestamped backup of the compose file before any edits."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{compose_path}.backup_{ts}"
    shutil.copy2(compose_path, backup_path)
    return backup_path


# ─── Option A: Inject name: into compose file ─────────────────────────────────

def inject_project_name(compose_path: str, project_name: str, dry_run: bool = False) -> dict:
    """
    Inject `name: <project_name>` at the top of docker-compose.yml.
    Preserves all existing content and comments as much as possible.
    Returns a result dict with success, backup_path, and diff preview.
    """
    with open(compose_path, 'r') as f:
        original = f.read()

    # Check if name: already exists
    lines = original.splitlines()
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('name:') and not stripped.startswith('name: #'):
            current_val = stripped.split(':', 1)[1].strip()
            if current_val == project_name:
                return {
                    'success': True,
                    'already_set': True,
                    'message': f"name: {project_name} is already set."
                }
            else:
                # Replace existing name: line
                new_content = re.sub(
                    r'^name:\s*.+$',
                    f'name: {project_name}',
                    original,
                    flags=re.MULTILINE
                )
                if dry_run:
                    return {
                        'success': True,
                        'dry_run': True,
                        'preview': _diff_preview(original, new_content),
                        'message': f"Would update name: {current_val} → {project_name}"
                    }
                backup = backup_compose_file(compose_path)
                with open(compose_path, 'w') as f:
                    f.write(new_content)
                return {
                    'success': True,
                    'backup': backup,
                    'message': f"Updated name: {current_val} → {project_name}"
                }

    # No existing name: — prepend it
    new_content = f"name: {project_name}\n\n" + original

    if dry_run:
        return {
            'success': True,
            'dry_run': True,
            'preview': f"+ name: {project_name}",
            'message': f"Would inject name: {project_name} at top of file"
        }

    backup = backup_compose_file(compose_path)
    with open(compose_path, 'w') as f:
        f.write(new_content)

    return {
        'success': True,
        'backup': backup,
        'message': f"Injected name: {project_name} into {os.path.basename(compose_path)}"
    }


# ─── Option B: Copy volumes via alpine container ──────────────────────────────

def _run(cmd: list[str], capture: bool = True):
    return subprocess.run(cmd, capture_output=capture, text=True)


def volume_exists(vol_name: str) -> bool:
    r = _run(['docker', 'volume', 'inspect', vol_name])
    return r.returncode == 0


def copy_volume(old_vol: str, new_vol: str, dry_run: bool = False) -> dict:
    """
    Copy data from old_vol to new_vol using a temporary alpine container.
    Creates new_vol if it doesn't exist.
    """
    if not volume_exists(old_vol):
        return {'success': False, 'message': f"Source volume {old_vol} not found"}

    cmd = [
        'docker', 'run', '--rm',
        '-v', f'{old_vol}:/from',
        '-v', f'{new_vol}:/to',
        'alpine', 'sh', '-c', 'cp -av /from/. /to/'
    ]

    if dry_run:
        return {
            'success': True,
            'dry_run': True,
            'message': f"Would copy: {old_vol} → {new_vol}",
            'command': ' '.join(cmd)
        }

    result = _run(cmd, capture=True)
    if result.returncode == 0:
        return {
            'success': True,
            'message': f"Copied {old_vol} → {new_vol}",
            'output': result.stdout
        }
    else:
        return {
            'success': False,
            'message': f"Failed to copy {old_vol} → {new_vol}",
            'error': result.stderr
        }


def migrate_volumes(fix_b_pairs: list[tuple], dry_run: bool = False) -> list[dict]:
    """Run volume copy for all (old, new) pairs from drift detection."""
    results = []
    for old_vol, new_vol in fix_b_pairs:
        result = copy_volume(old_vol, new_vol, dry_run=dry_run)
        result['old'] = old_vol
        result['new'] = new_vol
        results.append(result)
    return results


# ─── Option C: Patch broken bind mount paths ──────────────────────────────────

def patch_bind_mount_paths(compose_path: str, path_issues: list, dry_run: bool = False) -> dict:
    """
    For each broken bind mount path that has a suggestion, update the compose file.
    Only patches paths where exactly one suggestion exists (safe auto-fix).
    """
    broken_with_suggestions = [
        i for i in path_issues
        if not i.exists and len(i.suggestions) == 1
    ]

    ambiguous = [
        i for i in path_issues
        if not i.exists and len(i.suggestions) > 1
    ]

    unfixable = [
        i for i in path_issues
        if not i.exists and len(i.suggestions) == 0
    ]

    if not broken_with_suggestions:
        return {
            'success': True,
            'patched': [],
            'ambiguous': [i.source_raw for i in ambiguous],
            'unfixable': [i.source_raw for i in unfixable],
            'message': 'No unambiguous path fixes available.'
        }

    with open(compose_path, 'r') as f:
        content = f.read()

    original = content
    patched = []

    for issue in broken_with_suggestions:
        old_path = issue.source_raw
        new_path = issue.suggestions[0]

        # Try to preserve relative paths if original was relative
        if not old_path.startswith('/') and not old_path.startswith('~'):
            compose_dir = os.path.dirname(os.path.abspath(compose_path))
            try:
                new_path = os.path.relpath(new_path, compose_dir)
                if not new_path.startswith('.'):
                    new_path = './' + new_path
            except ValueError:
                pass  # different drives on Windows, keep absolute

        if old_path in content:
            content = content.replace(old_path, new_path)
            patched.append((old_path, new_path))

    if not patched:
        return {
            'success': True,
            'patched': [],
            'message': 'No replaceable paths found in compose file.'
        }

    if dry_run:
        return {
            'success': True,
            'dry_run': True,
            'patched': patched,
            'preview': _diff_preview(original, content),
            'ambiguous': [i.source_raw for i in ambiguous],
            'unfixable': [i.source_raw for i in unfixable],
            'message': f"Would patch {len(patched)} path(s)"
        }

    backup = backup_compose_file(compose_path)
    with open(compose_path, 'w') as f:
        f.write(content)

    return {
        'success': True,
        'backup': backup,
        'patched': patched,
        'ambiguous': [i.source_raw for i in ambiguous],
        'unfixable': [i.source_raw for i in unfixable],
        'message': f"Patched {len(patched)} path(s) in {os.path.basename(compose_path)}"
    }


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _diff_preview(original: str, new: str) -> str:
    """Return a simple line-diff preview for dry-run output."""
    orig_lines = original.splitlines()
    new_lines = new.splitlines()
    preview = []
    for i, (o, n) in enumerate(zip(orig_lines, new_lines)):
        if o != n:
            preview.append(f"  - {o}")
            preview.append(f"  + {n}")
    # Handle added lines (e.g. name: prepended)
    if len(new_lines) > len(orig_lines):
        for line in new_lines[:len(new_lines) - len(orig_lines)]:
            preview.append(f"  + {line}")
    return '\n'.join(preview) if preview else "(no diff)"
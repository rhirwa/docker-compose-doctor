"""
path_inspector.py — Validate bind mount paths exist and suggest corrections.
"""

import os
from dataclasses import dataclass, field
from difflib import get_close_matches
from pathlib import Path
from typing import Optional


@dataclass
class PathIssue:
    service: str
    source_raw: str           # as written in compose file
    resolved_path: str        # absolute resolved path
    exists: bool
    suggestions: list[str] = field(default_factory=list)


def _find_suggestions(broken_path: str, max_suggestions: int = 3) -> list[str]:
    """
    Walk up directories to find similar paths.
    Checks sibling and cousin directories for fuzzy matches.
    """
    broken = Path(broken_path)
    target_name = broken.name

    # Walk up two levels to search siblings and cousins
    search_roots = []
    parent = broken.parent
    for _ in range(3):
        if parent.exists():
            search_roots.append(str(parent))
            break
        parent = parent.parent
        if str(parent) == parent.root:
            break

    # Also try grandparent
    if search_roots:
        gp = Path(search_roots[0]).parent
        if gp.exists() and str(gp) not in search_roots:
            search_roots.append(str(gp))

    candidates = []
    for root in search_roots:
        try:
            for entry in os.scandir(root):
                if entry.is_dir():
                    candidates.append(entry.path)
                    # One level deeper
                    try:
                        for sub in os.scandir(entry.path):
                            if sub.is_dir():
                                candidates.append(sub.path)
                    except PermissionError:
                        pass
        except PermissionError:
            pass

    if not candidates:
        return []

    candidate_names = [os.path.basename(c) for c in candidates]
    close = get_close_matches(target_name, candidate_names, n=max_suggestions, cutoff=0.5)

    result = []
    for match in close:
        for c in candidates:
            if os.path.basename(c) == match and c not in result:
                result.append(c)
                break

    return result[:max_suggestions]


def inspect_bind_mounts(bind_mounts) -> list[PathIssue]:
    """
    Check each bind mount's resolved source path exists on disk.
    For missing paths, attempt to find close matches.
    """
    issues = []
    for bm in bind_mounts:
        path = bm.resolved_source or bm.source
        exists = os.path.exists(path)
        suggestions = []
        if not exists:
            suggestions = _find_suggestions(path)
        issues.append(PathIssue(
            service=bm.service,
            source_raw=bm.source,
            resolved_path=path,
            exists=exists,
            suggestions=suggestions
        ))
    return issues

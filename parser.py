"""
parser.py — Parse docker-compose.yml and extract volume/bind mount information.
"""

import os
import re
import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class BindMount:
    service: str
    source: str  # raw from compose file
    target: str
    resolved_source: Optional[str] = None  # absolute path on host


@dataclass
class NamedVolume:
    name: str  # as declared in compose file
    external: bool = False
    external_name: Optional[str] = None


@dataclass
class ComposeProject:
    compose_file: str
    compose_dir: str
    declared_name: Optional[str]   # set via top-level `name:` key
    inferred_name: str              # derived from directory name
    services: list
    named_volumes: list[NamedVolume] = field(default_factory=list)
    bind_mounts: list[BindMount] = field(default_factory=list)

    @property
    def effective_name(self) -> str:
        return self.declared_name if self.declared_name else self.inferred_name

    @property
    def has_explicit_name(self) -> bool:
        return self.declared_name is not None


def _resolve_env_vars(value: str) -> str:
    """Resolve basic shell env vars in paths like $HOME or ${HOME}."""
    return os.path.expandvars(value)


def _infer_project_name(compose_dir: str) -> str:
    """
    Docker derives project name from directory name:
    lowercased, non-alphanumeric chars replaced with hyphens.
    """
    name = os.path.basename(compose_dir)
    name = name.lower()
    name = re.sub(r'[^a-z0-9]', '-', name)
    name = re.sub(r'-+', '-', name).strip('-')
    return name


def _parse_volume_string(vol_str: str, service: str, compose_dir: str) -> Optional[BindMount]:
    """
    Parse short-form volume string like './data:/app/data' or '/abs/path:/target'.
    Returns BindMount if it's a bind mount, None if it's a named volume reference.
    """
    parts = vol_str.split(':')
    if len(parts) < 2:
        return None

    source = parts[0]

    # Named volume references don't start with . / or ~
    if not (source.startswith('.') or source.startswith('/') or source.startswith('~')):
        return None

    target = parts[1]
    resolved = _resolve_env_vars(source)
    if resolved.startswith('.'):
        resolved = os.path.normpath(os.path.join(compose_dir, resolved))
    elif resolved.startswith('~'):
        resolved = os.path.expanduser(resolved)

    return BindMount(service=service, source=source, target=target, resolved_source=resolved)


def parse_compose_file(compose_path: str) -> ComposeProject:
    """
    Load and parse a docker-compose.yml file.
    Returns a ComposeProject with all volume and bind mount info extracted.
    """
    compose_path = os.path.abspath(compose_path)
    compose_dir = os.path.dirname(compose_path)

    with open(compose_path, 'r') as f:
        data = yaml.safe_load(f)

    if data is None:
        data = {}

    declared_name = data.get('name', None)
    inferred_name = _infer_project_name(compose_dir)
    services = list((data.get('services') or {}).keys())

    # Parse named volumes
    named_volumes = []
    for vol_name, vol_config in (data.get('volumes') or {}).items():
        vol_config = vol_config or {}
        is_external = bool(vol_config.get('external', False))
        external_name = None
        if is_external and isinstance(vol_config.get('external'), dict):
            external_name = vol_config['external'].get('name')
        named_volumes.append(NamedVolume(
            name=vol_name,
            external=is_external,
            external_name=external_name
        ))

    # Parse bind mounts from services
    bind_mounts = []
    for svc_name, svc_config in (data.get('services') or {}).items():
        svc_config = svc_config or {}
        for vol in (svc_config.get('volumes') or []):
            if isinstance(vol, str):
                bm = _parse_volume_string(vol, svc_name, compose_dir)
                if bm:
                    bind_mounts.append(bm)
            elif isinstance(vol, dict) and vol.get('type') == 'bind':
                source = _resolve_env_vars(vol.get('source', ''))
                if source.startswith('.'):
                    source = os.path.normpath(os.path.join(compose_dir, source))
                elif source.startswith('~'):
                    source = os.path.expanduser(source)
                bind_mounts.append(BindMount(
                    service=svc_name,
                    source=vol.get('source', ''),
                    target=vol.get('target', ''),
                    resolved_source=source
                ))

    return ComposeProject(
        compose_file=compose_path,
        compose_dir=compose_dir,
        declared_name=declared_name,
        inferred_name=inferred_name,
        services=services,
        named_volumes=named_volumes,
        bind_mounts=bind_mounts,
    )

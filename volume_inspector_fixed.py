"""
volume_inspector.py — Query Docker for existing volumes and detect project name drift.
"""

import subprocess
import json
from dataclasses import dataclass, field
from typing import Optional
from difflib import SequenceMatcher


@dataclass
class DockerVolume:
    name: str
    driver: str
    mountpoint: str
    labels: dict = field(default_factory=dict)

    @property
    def project_prefix(self) -> Optional[str]:
        """Extract project name prefix from Docker Compose volume name convention: <project>_<vol>"""
        if '_' in self.name:
            # Find the last underscore before the volume suffix
            # Common suffixes: _data, _postgres_data, _n8n_data, etc.
            suffixes = ['_data', '_postgres_data', '_n8n_data', '_mysql_data', '_mongo_data']
            
            for suffix in suffixes:
                if self.name.endswith(suffix):
                    return self.name[:-len(suffix)]
            
            # Fallback: split on last underscore
            return self.name.rsplit('_', 1)[0]
        return None


@dataclass
class VolumeDriftResult:
    has_drift: bool
    current_project: str
    orphaned_volumes: list[DockerVolume]       # exist under old name
    expected_volumes: list[str]                 # what compose file expects
    missing_volumes: list[str]                  # expected but not found in Docker
    candidate_old_names: list[str]              # probable old project names


def _run_docker(args: list[str]) -> tuple[int, str, str]:
    """Run docker command and return (code, stdout, stderr)."""
    result = subprocess.run(
        ['docker'] + args,
        capture_output=True, text=True
    )
    return result.returncode, result.stdout, result.stderr


def list_docker_volumes() -> list[DockerVolume]:
    """List all Docker volumes on the host."""
    code, out, err = _run_docker(['volume', 'ls', '--format', '{{json .}}'])
    if code != 0:
        return []

    volumes = []
    for line in out.strip().splitlines():
        if not line.strip():
            continue
        try:
            data = json.loads(line)
            # Inspect for mountpoint
            icode, iout, _ = _run_docker(['volume', 'inspect', data['Name'], '--format', '{{.Mountpoint}}'])
            mountpoint = iout.strip() if icode == 0 else ''
            volumes.append(DockerVolume(
                name=data['Name'],
                driver=data.get('Driver', 'local'),
                mountpoint=mountpoint,
                labels={}
            ))
        except (json.JSONDecodeError, KeyError):
            continue

    return volumes


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def detect_volume_drift(project, all_volumes: list[DockerVolume]) -> VolumeDriftResult:
    """
    Core drift detection:
    - Check if expected volumes (project_<vol>) exist in Docker
    - If not, look for similar prefixes that might be the old project name
    """
    current_name = project.effective_name
    named_vols = [v for v in project.named_volumes if not v.external]

    # What volume names Docker Compose would create
    expected_names = [f"{current_name}_{v.name}" for v in named_vols]

    # Which of those actually exist
    existing_names = {v.name for v in all_volumes}
    missing = [n for n in expected_names if n not in existing_names]

    # Always check for orphaned volumes with similar prefix (even if current volumes exist)
    compose_vol_suffixes = {v.name for v in named_vols}
    candidate_old_names = []
    orphaned = []

    for dv in all_volumes:
        if dv.project_prefix and dv.project_prefix != current_name:
            suffix = dv.name[len(dv.project_prefix) + 1:]
            if suffix in compose_vol_suffixes:
                sim = _similarity(dv.project_prefix, current_name)
                if sim > 0.4:  # reasonable similarity threshold
                    orphaned.append(dv)
                    if dv.project_prefix not in candidate_old_names:
                        candidate_old_names.append(dv.project_prefix)

    # Sort candidates by similarity descending
    candidate_old_names.sort(key=lambda x: _similarity(x, current_name), reverse=True)

    return VolumeDriftResult(
        has_drift=len(orphaned) > 0,
        current_project=current_name,
        orphaned_volumes=orphaned,
        expected_volumes=expected_names,
        missing_volumes=missing,
        candidate_old_names=candidate_old_names
    )

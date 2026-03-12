# docker-compose-doctor — Project Map

## The Real Problem (Story)
Developer renames a parent folder mid-build (common during project restructuring).
Docker Compose derives its **project name** from the directory name.
Old volumes were named: `old-folder_service_data`
New volumes expected: `new-folder_service_data`
Result: containers start silently with **empty volumes** — no error, no warning.
Data (n8n workflows, DB state, etc.) appears lost. It isn't — it's orphaned.

## Two Root Causes the Tool Handles

### Cause 1 — Project Name Drift (volume orphaning)
- Old volumes still exist, prefixed with old project name
- New project name creates fresh empty volumes
- Fix A (fastest): inject `name: <project>` into compose file — zero data movement
- Fix B (clean migration): copy old volume → new volume via alpine container

### Cause 2 — Bind Mount Path Drift
- Bind mount source paths in compose file no longer exist on disk
- Happens after folder renames, machine migrations, repo moves
- Fix: detect, report, suggest corrected paths using fuzzy directory matching

---

## Tool Architecture

```
docker-compose-doctor/
├── cli.py                  # Entry point — argparse CLI
├── parser.py               # Parse docker-compose.yml (PyYAML)
├── volume_inspector.py     # Query Docker API for existing volumes
├── path_inspector.py       # Check bind mount paths on disk
├── drift_detector.py       # Core logic — detect name drift + path drift
├── fix_engine.py           # Generate and optionally apply fixes
├── report.py               # Pretty terminal output (rich library)
└── README.md
```

---

## Core Detection Logic

### Step 1 — Parse Compose File
- Load `docker-compose.yml`
- Extract: project name (if set), services, volumes (named + bind mounts)
- Resolve all relative paths to absolute

### Step 2 — Inspect Docker State
- List all Docker volumes on host
- Filter volumes that match current project name prefix
- Filter volumes that match *similar* project name prefixes (drift candidates)

### Step 3 — Drift Detection
```
IF named volumes in compose file have no matching Docker volumes
AND volumes with similar prefix exist
→ PROJECT NAME DRIFT DETECTED
→ Candidate old volumes: [list]
→ Recommended fix: Option A (add name:) or Option B (copy volumes)
```

### Step 4 — Bind Mount Path Check
```
FOR each bind mount source path:
  IF path does not exist on disk:
    → PATH DRIFT DETECTED
    → Search parent directories for fuzzy matches
    → Suggest closest match
```

### Step 5 — Fix Engine (interactive)
```
Doctor presents findings:
  [!] Project name drift: 2 orphaned volumes found
      old name: livenfull-n8n
      new name: projects-n8n
      
  [!] Bind mount drift: 1 broken path
      expected: /Users/remy/projects/n8n/data
      found:    path does not exist
      closest:  /Users/remy/livenfull/n8n/data

Fix options:
  [1] Add 'name: livenfull-n8n' to compose file (instant, recommended)
  [2] Copy orphaned volumes to new project name
  [3] Update bind mount path in compose file
  [4] Show me the commands, I'll run them myself

Apply fixes? [y/N]
```

---

## CLI Interface

```bash
# Basic scan
docker-compose-doctor

# Scan specific file
docker-compose-doctor -f ./path/to/docker-compose.yml

# Auto-apply safe fixes (name injection + path updates)
docker-compose-doctor --fix

# Dry run — show what would be fixed
docker-compose-doctor --dry-run

# Full volume migration (data copy)
docker-compose-doctor --migrate-volumes

# Output JSON (for CI/scripting)
docker-compose-doctor --json
```

---

## Build Phases

### v0.1 — Core Diagnostic (ship first)
- [x] Parse compose file
- [x] Detect project name drift
- [x] Detect broken bind mount paths
- [x] Pretty terminal report
- [ ] No auto-fix yet — report only

### v0.2 — Fix Engine
- [ ] Option A: inject `name:` into compose file
- [ ] Path correction in compose file
- [ ] Dry-run mode

### v0.3 — Volume Migration
- [ ] Option B: copy volumes via alpine container
- [ ] Backup before any destructive action
- [ ] `--migrate-volumes` flag

### v1.0 — Polish + Publish
- [ ] pip installable (`pip install docker-compose-doctor`)
- [ ] Homebrew formula
- [ ] Imhotep Systems website page
- [ ] GitHub Actions integration (scan on PR)

---

## Tech Stack
- Language: Python 3.10+
- Docker interaction: `docker` Python SDK
- YAML parsing: PyYAML
- Terminal output: `rich`
- Fuzzy path matching: `difflib` (stdlib) or `thefuzz`
- Packaging: `pyproject.toml` + `hatchling`

---

## The LinkedIn Story Arc
1. Was restructuring my Livenfull project directory mid-build
2. Renamed parent folder — Docker Compose silently spun up with empty volumes
3. n8n workflows gone, DB state gone — no error thrown
4. Dug into Docker volume internals — data was there, just orphaned under old project name
5. Fixed it manually — but realized this is a silent failure pattern affecting every developer
6. Built docker-compose-doctor to automate detection and recovery
7. v0.1 ships this week — open source, Imhotep Systems

---

## Positioning
- Not a Docker replacement or wrapper
- A **diagnostic + recovery tool** for local development environment drift
- Sits alongside your workflow like `git status` for your Docker environment
- Target: developers using Docker Compose for local dev (n8n, Postgres, Redis, etc.)

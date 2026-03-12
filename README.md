# docker-compose-doctor

**Diagnose and recover from Docker Compose volume drift and broken bind mount paths.**

Built by [Imhotep Systems](https://imhotep.systems) — born from a real problem.

---

## The Problem

You renamed a project folder. Everything looks fine. You run `docker compose up`.

Your n8n workflows are gone. Your Postgres database is empty. No error. No warning.

What happened? Docker Compose derives its **project name** from the directory name. When the folder changed, Docker started looking for volumes prefixed with the new name — and created empty ones. Your data is still there, sitting in orphaned volumes under the old name.

This is a silent failure. `docker-compose-doctor` makes it loud, and fixable.

---

## Install

```bash
pip install docker-compose-doctor
```

Or run without installing:

```bash
pipx run docker-compose-doctor
```

---

## Usage

```bash
# Run in any directory with a docker-compose.yml
docker-compose-doctor

# Specify a file
docker-compose-doctor -f ./path/to/docker-compose.yml

# Output JSON (for CI/scripting)
docker-compose-doctor --json
```

---

## What It Detects

### 1. Project Name Drift (volume orphaning)

When a parent folder rename changes the inferred project name, Docker Compose creates new empty volumes instead of reusing existing ones.

```
✗ myproject_postgres_data  — not found in Docker

⚠ Orphaned volumes found — possible project name drift:
    • old-project_postgres_data  (/var/lib/docker/volumes/...)

Likely old project name: old-project

Fix options:

  Option A — Fastest. Lock the project name in your compose file:
    name: old-project

  Option B — Clean migration. Copy old volumes to new project name:
    docker run --rm \
      -v old-project_postgres_data:/from \
      -v myproject_postgres_data:/to \
      alpine sh -c "cp -av /from/. /to/"
```

### 2. Bind Mount Path Drift

When bind mount source paths in your compose file no longer exist on disk (folder renamed, machine migrated, repo moved).

```
✗ /Users/remy/old-folder/n8n/data  (n8n)
    path does not exist on disk
    Closest matches:
      → /Users/remy/projects/n8n/data
```

---

## Why Option A is Usually Better

Most developers don't know that `docker-compose.yml` supports a top-level `name:` key. Setting it explicitly decouples your project name from your directory structure — meaning you can rename, move, or reorganize your folders without ever losing volume data again.

```yaml
name: my-project  # locks project name regardless of folder

services:
  n8n:
    image: n8nio/n8n
    ...
```

---

## Roadmap

| Version | Features |
|---------|----------|
| v0.1 | Diagnostic report — volume drift + bind mount path check |
| v0.2 | `--fix` flag — auto-inject `name:`, auto-correct paths |
| v0.3 | `--migrate-volumes` — orchestrate Option B volume copy |
| v1.0 | Homebrew formula, pip stable release, CI integration |

---

## Contributing

Issues and PRs welcome. This tool was built because we hit this problem in production and couldn't find anything that solved it cleanly.

If you've hit Docker Compose volume drift in a way this tool doesn't handle yet, [open an issue](https://github.com/imhotep-systems/docker-compose-doctor/issues) — we want to know.

---

## License

MIT — [Imhotep Systems](https://imhotepsystems.com)

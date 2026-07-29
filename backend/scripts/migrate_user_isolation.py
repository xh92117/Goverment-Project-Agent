"""One-time migration: move legacy thread dirs and memory into per-user layout.

Usage:
    PYTHONPATH=. python scripts/migrate_user_isolation.py [--dry-run] [--user-id USER_ID]

The script is idempotent — re-running it after a successful migration is a no-op.
"""

import argparse
import logging
import os
import shutil
from pathlib import Path

from deerflow.config.paths import Paths, get_paths

logger = logging.getLogger(__name__)


def migrate_thread_dirs(
    paths: Paths,
    thread_owner_map: dict[str, str],
    *,
    default_user_id: str = "default",
    dry_run: bool = False,
) -> list[dict]:
    """Move legacy thread directories into per-user layout.

    Args:
        paths: Paths instance.
        thread_owner_map: Mapping of thread_id -> user_id from threads_meta table.
        dry_run: If True, only log what would happen.

    Returns:
        List of migration report entries.
    """
    report: list[dict] = []
    legacy_threads = paths.base_dir / "threads"
    if not legacy_threads.exists():
        logger.info("No legacy threads directory found — nothing to migrate.")
        return report

    for thread_dir in sorted(legacy_threads.iterdir()):
        if not thread_dir.is_dir():
            continue
        thread_id = thread_dir.name
        user_id = thread_owner_map.get(thread_id, default_user_id)
        dest = paths.thread_dir(thread_id, user_id=user_id)

        entry = {"thread_id": thread_id, "user_id": user_id, "action": ""}

        if dest.exists():
            conflicts_dir = paths.base_dir / "migration-conflicts" / thread_id
            entry["action"] = f"conflict -> {conflicts_dir}"
            if not dry_run:
                conflicts_dir.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(thread_dir), str(conflicts_dir))
            logger.warning("Conflict for thread %s: moved to %s", thread_id, conflicts_dir)
        else:
            entry["action"] = f"moved -> {dest}"
            if not dry_run:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(thread_dir), str(dest))
            logger.info("Migrated thread %s -> user %s", thread_id, user_id)

        report.append(entry)

    # Clean up empty legacy threads dir
    if not dry_run and legacy_threads.exists() and not any(legacy_threads.iterdir()):
        legacy_threads.rmdir()

    return report


def migrate_legacy_collection(
    paths: Paths,
    *,
    source_root,
    destination_root,
    category: str,
    dry_run: bool = False,
) -> list[dict]:
    """Move the direct children of one legacy workspace root safely.

    Projects and proposal drafts are directory collections rather than one
    atomic file. Existing destination entries win; legacy conflicts are kept
    under ``migration-conflicts/<category>/`` for manual review.
    """
    from pathlib import Path

    source = Path(source_root).resolve()
    destination = Path(destination_root).resolve()
    if source == destination or not source.exists():
        return []

    report: list[dict] = []
    for item in sorted(source.iterdir(), key=lambda path: path.name):
        dest = destination / item.name
        if dest.exists():
            conflict = paths.base_dir / "migration-conflicts" / category / item.name
            action = f"conflict -> {conflict}"
            if not dry_run:
                conflict.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(item), str(conflict))
        else:
            action = f"moved -> {dest}"
            if not dry_run:
                destination.mkdir(parents=True, exist_ok=True)
                shutil.move(str(item), str(dest))
        report.append({"name": item.name, "category": category, "action": action})

    if not dry_run and source.exists() and not any(source.iterdir()):
        source.rmdir()
    return report


def migrate_agents(
    paths: Paths,
    user_id: str = "default",
    *,
    dry_run: bool = False,
) -> list[dict]:
    """Move legacy custom-agent directories into per-user layout.

    Legacy layout:  ``{base_dir}/agents/{name}/``
    Per-user layout: ``{base_dir}/users/{user_id}/agents/{name}/``

    Pre-existing per-user agents take precedence: if a destination already
    exists for an agent name, the legacy copy is moved to
    ``{base_dir}/migration-conflicts/agents/{name}/`` for manual review.

    Args:
        paths: Paths instance.
        user_id: Target user to receive the legacy agents (defaults to
            ``"default"``, matching ``DEFAULT_USER_ID`` for no-auth setups).
        dry_run: If True, only log what would happen.

    Returns:
        List of migration report entries, one per legacy agent directory found.
    """
    report: list[dict] = []
    legacy_agents = paths.agents_dir
    if not legacy_agents.exists():
        logger.info("No legacy agents directory found — nothing to migrate.")
        return report

    for agent_dir in sorted(legacy_agents.iterdir()):
        if not agent_dir.is_dir():
            continue
        agent_name = agent_dir.name
        dest = paths.user_agent_dir(user_id, agent_name)

        entry = {"agent": agent_name, "user_id": user_id, "action": ""}

        if dest.exists():
            conflicts_dir = paths.base_dir / "migration-conflicts" / "agents" / agent_name
            entry["action"] = f"conflict -> {conflicts_dir}"
            if not dry_run:
                conflicts_dir.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(agent_dir), str(conflicts_dir))
            logger.warning("Conflict for agent %s: moved legacy copy to %s", agent_name, conflicts_dir)
        else:
            entry["action"] = f"moved -> {dest}"
            if not dry_run:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(agent_dir), str(dest))
            logger.info("Migrated agent %s -> user %s", agent_name, user_id)

        report.append(entry)

    # Clean up empty legacy agents dir
    if not dry_run and legacy_agents.exists() and not any(legacy_agents.iterdir()):
        legacy_agents.rmdir()

    return report


def migrate_memory(
    paths: Paths,
    user_id: str = "default",
    *,
    dry_run: bool = False,
) -> None:
    """Move legacy global memory.json into per-user layout.

    Args:
        paths: Paths instance.
        user_id: Target user to receive the legacy memory.
        dry_run: If True, only log.
    """
    legacy_mem = paths.base_dir / "memory.json"
    if not legacy_mem.exists():
        logger.info("No legacy memory.json found — nothing to migrate.")
        return

    dest = paths.user_memory_file(user_id)
    if dest.exists():
        legacy_backup = paths.base_dir / "memory.legacy.json"
        logger.warning("Destination %s exists; renaming legacy to %s", dest, legacy_backup)
        if not dry_run:
            legacy_mem.rename(legacy_backup)
        return

    logger.info("Migrating memory.json -> %s", dest)
    if not dry_run:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(legacy_mem), str(dest))


def _build_owner_map_from_db(paths: Paths, database_path: str | Path | None = None) -> dict[str, str]:
    """Query threads_meta table for thread_id -> user_id mapping.

    Uses raw sqlite3 to avoid async dependencies.
    """
    import sqlite3

    configured_env = os.getenv("AGENT_BASE_DB_PATH") or os.getenv("DEER_FLOW_DB_PATH")
    candidates = [
        Path(database_path).expanduser().resolve() if database_path else None,
        paths.base_dir / "data" / "agent_base.db",
        paths.base_dir / "data" / "deerflow.db",
        paths.base_dir / "agent_base.db",
        paths.base_dir / "deerflow.db",
        paths.base_dir / "deer-flow.db",
        Path(configured_env).expanduser().resolve() if configured_env else None,
    ]
    db_path = next((candidate for candidate in candidates if candidate is not None and candidate.exists()), candidates[1])
    if not db_path.exists():
        logger.info("No database found at %s — using empty owner map.", db_path)
        return {}

    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.execute("SELECT thread_id, user_id FROM threads_meta WHERE user_id IS NOT NULL")
        return {row[0]: row[1] for row in cursor.fetchall()}
    except sqlite3.OperationalError as e:
        logger.warning("Failed to query threads_meta: %s", e)
        return {}
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate DeerFlow data to per-user layout")
    parser.add_argument("--dry-run", action="store_true", help="Log actions without making changes")
    parser.add_argument(
        "--user-id",
        default="default",
        metavar="USER_ID",
        help=("User ID to claim un-owned legacy data (global memory.json and legacy custom agents). Defaults to 'default'. In multi-user installs, set this to the operator account that should inherit those legacy artifacts."),
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="Optional SQLite agent_base.db path used to resolve legacy thread owners.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    paths = get_paths()
    logger.info("Base directory: %s", paths.base_dir)
    logger.info("Dry run: %s", args.dry_run)
    logger.info("Claiming un-owned legacy data for user_id=%s", args.user_id)

    owner_map = _build_owner_map_from_db(paths, database_path=args.db_path)
    logger.info("Found %d thread ownership records in DB", len(owner_map))

    report = migrate_thread_dirs(
        paths,
        owner_map,
        default_user_id=args.user_id,
        dry_run=args.dry_run,
    )
    migrate_memory(paths, user_id=args.user_id, dry_run=args.dry_run)
    agent_report = migrate_agents(paths, user_id=args.user_id, dry_run=args.dry_run)

    from deerflow.government_project_workspace import (
        government_project_drafts_root,
        government_project_projects_root,
    )

    project_report = migrate_legacy_collection(
        paths,
        source_root=government_project_projects_root(),
        destination_root=paths.user_projects_dir(args.user_id),
        category="projects",
        dry_run=args.dry_run,
    )
    draft_report = migrate_legacy_collection(
        paths,
        source_root=government_project_drafts_root(),
        destination_root=paths.user_drafts_dir(args.user_id),
        category="proposal-drafts",
        dry_run=args.dry_run,
    )

    if report:
        logger.info("Thread migration report:")
        for entry in report:
            logger.info("  thread=%s user=%s action=%s", entry["thread_id"], entry["user_id"], entry["action"])
    else:
        logger.info("No threads to migrate.")

    if agent_report:
        logger.info("Agent migration report:")
        for entry in agent_report:
            logger.info("  agent=%s user=%s action=%s", entry["agent"], entry["user_id"], entry["action"])
    else:
        logger.info("No agents to migrate.")

    logger.info(
        "Legacy workspace migration: %d project item(s), %d proposal-draft item(s)",
        len(project_report),
        len(draft_report),
    )

    unowned = [e for e in report if e["thread_id"] not in owner_map]
    if unowned:
        logger.warning(
            "%d thread(s) had no owner and were assigned to '%s':",
            len(unowned),
            args.user_id,
        )
        for e in unowned:
            logger.warning("  %s", e["thread_id"])

    if agent_report:
        logger.warning(
            "%d legacy agent(s) were assigned to '%s'. If those agents belonged to other users, move them manually under {base_dir}/users/<user_id>/agents/.",
            len(agent_report),
            args.user_id,
        )


if __name__ == "__main__":
    main()

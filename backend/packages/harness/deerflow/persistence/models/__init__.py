"""ORM model registration entry point.

Importing this module ensures default ORM models are registered with
``Base.metadata`` so Alembic autogenerate detects base tables.

The actual ORM classes have moved to entity-specific subpackages:
- ``deerflow.persistence.thread_meta``
- ``deerflow.persistence.run``

``deerflow.persistence.feedback`` is intentionally not registered by default.
It remains as optional source code for projects that want to add a feedback or
audit extension without making the base runtime create a feedback table.

``deerflow.persistence.user`` is also optional. The Gateway imports it during
startup only when built-in local authentication is enabled.

``RunEventRow`` remains in ``deerflow.persistence.models.run_event`` because
its storage implementation lives in ``deerflow.runtime.events.store.db`` and
there is no matching entity directory.
"""

from deerflow.persistence.models.run_event import RunEventRow
from deerflow.persistence.run.model import RunRow
from deerflow.persistence.thread_meta.model import ThreadMetaRow

__all__ = ["RunEventRow", "RunRow", "ThreadMetaRow"]

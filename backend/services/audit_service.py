import json
from typing import Any

from models.audit_log import AuditLog
from sqlalchemy.orm import Session


def _serialize(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, default=str, sort_keys=True)


def record_audit_log(
    db: Session,
    *,
    actor_type: str,
    actor_id: str | int,
    action: str,
    entity_type: str,
    entity_id: str | int,
    old_value: Any = None,
    new_value: Any = None,
) -> AuditLog:
    audit_log = AuditLog(
        actor_type=actor_type,
        actor_id=str(actor_id),
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        old_value=_serialize(old_value),
        new_value=_serialize(new_value),
    )
    db.add(audit_log)
    return audit_log

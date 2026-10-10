from datetime import datetime, timezone

def current_on_call(schedule:dict, at:datetime|None=None):
    """Return a deterministic rotation member; full timezone-aware rotation calendars can be added later."""
    members=schedule.get("members") or []
    if not members: return None
    at=at or datetime.now(timezone.utc)
    hours=max(1,int(schedule.get("rotation_hours",168)))
    slot=int(at.timestamp() // (hours*3600))
    return members[slot % len(members)]

def escalation_targets(policy:dict):
    return policy.get("rules", []) if policy.get("enabled",True) else []

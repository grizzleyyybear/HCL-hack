"""Platform status tool. Area: data and tools."""
from app import db


# Return the status rows for all components, or for one component.
def check_platform_status(component: str | None = None) -> dict:
    sql = "SELECT component, status, incident_id, updated_at FROM platform_status"
    params = ()
    if component:
        sql += " WHERE component = ?"
        params = (component,)
    with db.connect() as conn:
        rows = [dict(r) for r in conn.execute(sql + " ORDER BY component", params)]
    if component and not rows:
        return {"error": "component_not_found"}
    return {"components": rows}

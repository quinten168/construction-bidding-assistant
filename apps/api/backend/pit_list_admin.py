"""
Feature 2 — pit list CRUD: add/update/remove a pit location in scratch.mn_pit_list (Supabase, see
docs/DATA_ACCESS_SCRATCH.md).

No FK dependents on this table (it's independent of bid_projects/bid_results/the registry per
docs/DATA_ACCESS_SCRATCH.md), so create/update/delete are plain statements with no referential
checks — the only integrity rule here is duplicate prevention on create.
"""
from __future__ import annotations

from . import ci_db
from .observability import get_logger

log = get_logger("bid_assistant.pit_list_admin")

FIELDS = ["name", "access", "county", "rating", "state", "access_type", "access_company"]


class ValidationError(ValueError):
    pass


class DuplicateWarning(Exception):
    """Not fatal — a possible-duplicate pit was found and `force` wasn't set. Callers surface
    `.payload` to the frontend, which re-calls with force=True to proceed anyway."""

    def __init__(self, payload: dict):
        self.payload = payload
        super().__init__(payload.get("message", "possible duplicate"))


def list_pits(search: str | None = None) -> list[dict]:
    sql = "select * from scratch.mn_pit_list"
    params: list = []
    if search:
        sql += " where name ilike %s or county ilike %s or state ilike %s"
        like = f"%{search}%"
        params += [like, like, like]
    sql += " order by county, name"
    with ci_db.get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def _check_access_company_in_registry(cur, access_company) -> None:
    """access_company must name a real registry entry — the Excel-filter picker in the UI already
    restricts input to this list; this is the DB-side backstop for direct API callers. Only checked
    when the field is actually present; it doesn't make the field required (PitIn in app.py does
    that at the system boundary), so it can't affect callers that omit it."""
    if not access_company:
        return
    norm = ci_db.normalize(access_company)
    cur.execute(
        "select 1 from scratch.competitor_name_registry "
        "where upper(regexp_replace(comp_name, '\\s+', ' ', 'g')) = %s limit 1",
        (norm,),
    )
    if cur.fetchone() is None:
        raise ValidationError(
            f"{access_company!r} is not in the competitor name registry — add it there first."
        )


def create_pit(fields: dict, force: bool = False) -> dict:
    latitude = float(fields["latitude"])
    longitude = float(fields["longitude"])
    name = str(fields.get("name") or "").strip()
    county = str(fields.get("county") or "").strip()

    with ci_db.get_conn() as conn, conn.cursor() as cur:
        _check_access_company_in_registry(cur, fields.get("access_company"))

        cur.execute(
            "select 1 from scratch.mn_pit_list where latitude = %s and longitude = %s",
            (latitude, longitude),
        )
        if cur.fetchone() is not None:
            raise ValidationError(
                f"A pit already exists at ({latitude}, {longitude}) — exact coordinate match."
            )

        if not force and name and county:
            cur.execute(
                "select name, latitude, longitude from scratch.mn_pit_list "
                "where lower(name) = lower(%s) and lower(county) = lower(%s)",
                (name, county),
            )
            existing = cur.fetchone()
            if existing is not None:
                raise DuplicateWarning({
                    "warning": "possible_duplicate",
                    "message": (
                        f"A pit named {existing['name']!r} already exists in {county} at "
                        f"({existing['latitude']}, {existing['longitude']}). Continue anyway?"
                    ),
                    "existing": existing,
                })

        cur.execute(
            """
            insert into scratch.mn_pit_list
                (latitude, longitude, name, access, county, rating, state, access_type,
                 access_company)
            values (%(latitude)s, %(longitude)s, %(name)s, %(access)s, %(county)s, %(rating)s,
                    %(state)s, %(access_type)s, %(access_company)s)
            """,
            {
                "latitude": latitude, "longitude": longitude,
                **{f: fields.get(f) for f in FIELDS},
            },
        )
    log.info("pit created: %s (%s, %s)", name, latitude, longitude)
    return {"latitude": latitude, "longitude": longitude}


def update_pit(latitude: float, longitude: float, fields: dict) -> dict:
    """Update a pit's fields. If the edit changes latitude/longitude themselves, the composite key
    can't be updated in place — this deletes the old key and creates a new one (still running the
    same duplicate check on the new key, via create_pit)."""
    new_lat = float(fields["latitude"]) if "latitude" in fields else latitude
    new_lon = float(fields["longitude"]) if "longitude" in fields else longitude

    if (new_lat, new_lon) != (latitude, longitude):
        merged = {**fields, "latitude": new_lat, "longitude": new_lon}
        delete_pit(latitude, longitude)
        return create_pit(merged, force=bool(fields.get("force")))

    set_cols = [f for f in FIELDS if f in fields]
    if not set_cols:
        return {"latitude": latitude, "longitude": longitude}

    set_clause = ", ".join(f"{c} = %({c})s" for c in set_cols)
    with ci_db.get_conn() as conn, conn.cursor() as cur:
        if "access_company" in fields:
            _check_access_company_in_registry(cur, fields.get("access_company"))
        cur.execute(
            f"update scratch.mn_pit_list set {set_clause}, updated_at = now() "
            "where latitude = %(latitude)s and longitude = %(longitude)s",
            {**{c: fields.get(c) for c in set_cols}, "latitude": latitude, "longitude": longitude},
        )
        if cur.rowcount == 0:
            raise ValidationError(f"No pit found at ({latitude}, {longitude}).")
    log.info("pit updated: (%s, %s)", latitude, longitude)
    return {"latitude": latitude, "longitude": longitude}


def delete_pit(latitude: float, longitude: float) -> None:
    with ci_db.get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "delete from scratch.mn_pit_list where latitude = %s and longitude = %s",
            (latitude, longitude),
        )
        if cur.rowcount == 0:
            raise ValidationError(f"No pit found at ({latitude}, {longitude}).")
    log.info("pit deleted: (%s, %s)", latitude, longitude)

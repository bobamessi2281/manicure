from __future__ import annotations

import aiosqlite
from dataclasses import dataclass
from datetime import date, datetime, time as dtime, timedelta, timezone
from typing import Any

from app.db import SCHEMA_SQL, utc_now_iso
from app.utils.time import parse_iso


@dataclass
class AppointmentRow:
    id: int
    client_tg_id: int
    client_username: str | None
    client_name: str
    client_phone_norm: str
    service_name: str
    duration_minutes: int
    start_at: str
    end_at: str
    status: str
    client_comment: str | None
    admin_reason: str | None
    proposed_start_at: str | None
    proposed_end_at: str | None
    created_at: str
    updated_at: str
    reminder_24_sent: int
    reminder_12_sent: int


def _dt_to_utc_z(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    u = dt.astimezone(timezone.utc).replace(microsecond=0)
    return u.strftime("%Y-%m-%dT%H:%M:%SZ")


def _row_to_appt(r: aiosqlite.Row) -> AppointmentRow:
    return AppointmentRow(
        id=r["id"],
        client_tg_id=r["client_tg_id"],
        client_username=r["client_username"],
        client_name=r["client_name"],
        client_phone_norm=r["client_phone_norm"],
        service_name=r["service_name"],
        duration_minutes=r["duration_minutes"],
        start_at=r["start_at"],
        end_at=r["end_at"],
        status=r["status"],
        client_comment=r["client_comment"],
        admin_reason=r["admin_reason"],
        proposed_start_at=r["proposed_start_at"],
        proposed_end_at=r["proposed_end_at"],
        created_at=r["created_at"],
        updated_at=r["updated_at"],
        reminder_24_sent=r["reminder_24_sent"],
        reminder_12_sent=r["reminder_12_sent"],
    )


class Database:
    def __init__(self, path: str) -> None:
        self.path = path

    async def init(self) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.executescript(SCHEMA_SQL)
            await db.commit()

    async def ensure_owner(self, tg_id: int, username: str | None) -> None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT id FROM admins WHERE tg_id = ?", (tg_id,)
            )
            row = await cur.fetchone()
            if row is None:
                await db.execute(
                    "INSERT INTO admins (tg_id, username, role) VALUES (?, ?, 'owner')",
                    (tg_id, username),
                )
            else:
                await db.execute(
                    "UPDATE admins SET username = COALESCE(?, username) WHERE tg_id = ?",
                    (username, tg_id),
                )
            await db.commit()

    async def get_admin_by_tg(self, tg_id: int) -> dict[str, Any] | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM admins WHERE tg_id = ?", (tg_id,)
            )
            row = await cur.fetchone()
            return dict(row) if row else None

    async def is_admin(self, tg_id: int) -> bool:
        return (await self.get_admin_by_tg(tg_id)) is not None

    async def is_owner(self, tg_id: int) -> bool:
        a = await self.get_admin_by_tg(tg_id)
        return bool(a and a.get("role") == "owner")

    async def add_admin(
        self, tg_id: int, username: str | None, role: str = "admin"
    ) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT INTO admins (tg_id, username, role)
                VALUES (?, ?, ?)
                ON CONFLICT(tg_id) DO UPDATE SET username = excluded.username, role = excluded.role
                """,
                (tg_id, username, role),
            )
            await db.commit()

    async def remove_admin_by_username(self, username: str) -> bool:
        uname = username.lstrip("@").strip().lower()
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "SELECT tg_id, role FROM admins WHERE lower(username) = ?",
                (uname,),
            )
            row = await cur.fetchone()
            if row is None:
                return False
            if row[1] == "owner":
                return False
            await db.execute("DELETE FROM admins WHERE lower(username) = ?", (uname,))
            await db.commit()
            return True

    async def remove_admin_by_tg_id(self, tg_id: int) -> bool:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "SELECT role FROM admins WHERE tg_id = ?", (tg_id,)
            )
            row = await cur.fetchone()
            if row is None or row[0] == "owner":
                return False
            await db.execute("DELETE FROM admins WHERE tg_id = ?", (tg_id,))
            await db.commit()
            return True

    async def list_admins(self) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT tg_id, username, role, created_at FROM admins ORDER BY id"
            )
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def insert_appointment(
        self,
        *,
        client_tg_id: int,
        client_username: str | None,
        client_name: str,
        client_phone_norm: str,
        service_name: str,
        duration_minutes: int,
        start_at: datetime,
        end_at: datetime,
        status: str,
        client_comment: str | None,
    ) -> int:
        now = utc_now_iso()
        sa = _dt_to_utc_z(start_at)
        ea = _dt_to_utc_z(end_at)
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                """
                INSERT INTO appointments (
                    client_tg_id, client_username, client_name, client_phone_norm,
                    service_name, duration_minutes, start_at, end_at, status,
                    client_comment, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    client_tg_id,
                    client_username,
                    client_name,
                    client_phone_norm,
                    service_name,
                    duration_minutes,
                    sa,
                    ea,
                    status,
                    client_comment,
                    now,
                ),
            )
            await db.commit()
            return int(cur.lastrowid)

    async def get_appointment(self, appt_id: int) -> AppointmentRow | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM appointments WHERE id = ?", (appt_id,)
            )
            row = await cur.fetchone()
            return _row_to_appt(row) if row else None

    async def update_appointment_times(
        self,
        appt_id: int,
        start_at: datetime,
        end_at: datetime,
        *,
        reset_reminders: bool = True,
    ) -> None:
        now = utc_now_iso()
        sa = _dt_to_utc_z(start_at)
        ea = _dt_to_utc_z(end_at)
        async with aiosqlite.connect(self.path) as db:
            if reset_reminders:
                await db.execute(
                    """
                    UPDATE appointments SET start_at = ?, end_at = ?, updated_at = ?,
                    reminder_24_sent = 0, reminder_12_sent = 0
                    WHERE id = ?
                    """,
                    (sa, ea, now, appt_id),
                )
            else:
                await db.execute(
                    """
                    UPDATE appointments SET start_at = ?, end_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (sa, ea, now, appt_id),
                )
            await db.commit()

    async def set_proposed_times(
        self,
        appt_id: int,
        proposed_start: datetime,
        proposed_end: datetime,
        status: str = "RESCHEDULE_PROPOSED",
    ) -> None:
        now = utc_now_iso()
        ps = _dt_to_utc_z(proposed_start)
        pe = _dt_to_utc_z(proposed_end)
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                UPDATE appointments SET proposed_start_at = ?, proposed_end_at = ?,
                status = ?, updated_at = ?, reminder_24_sent = 0, reminder_12_sent = 0
                WHERE id = ?
                """,
                (ps, pe, status, now, appt_id),
            )
            await db.commit()

    async def accept_reschedule(self, appt_id: int) -> None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT proposed_start_at, proposed_end_at FROM appointments WHERE id = ?",
                (appt_id,),
            )
            row = await cur.fetchone()
            if not row or not row["proposed_start_at"]:
                return
            now = utc_now_iso()
            await db.execute(
                """
                UPDATE appointments SET
                    start_at = proposed_start_at,
                    end_at = proposed_end_at,
                    proposed_start_at = NULL,
                    proposed_end_at = NULL,
                    status = 'CONFIRMED',
                    updated_at = ?,
                    reminder_24_sent = 0,
                    reminder_12_sent = 0
                WHERE id = ?
                """,
                (now, appt_id),
            )
            await db.commit()

    async def update_status(
        self,
        appt_id: int,
        status: str,
        admin_reason: str | None = None,
        clear_proposed: bool = False,
    ) -> None:
        now = utc_now_iso()
        async with aiosqlite.connect(self.path) as db:
            if clear_proposed:
                await db.execute(
                    """
                    UPDATE appointments SET status = ?, admin_reason = ?,
                    proposed_start_at = NULL, proposed_end_at = NULL,
                    updated_at = ? WHERE id = ?
                    """,
                    (status, admin_reason, now, appt_id),
                )
            else:
                await db.execute(
                    """
                    UPDATE appointments SET status = ?, admin_reason = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (status, admin_reason, now, appt_id),
                )
            await db.commit()

    async def set_reminder_flags(
        self, appt_id: int, r24: bool | None = None, r12: bool | None = None
    ) -> None:
        async with aiosqlite.connect(self.path) as db:
            if r24 is not None:
                await db.execute(
                    "UPDATE appointments SET reminder_24_sent = ? WHERE id = ?",
                    (1 if r24 else 0, appt_id),
                )
            if r12 is not None:
                await db.execute(
                    "UPDATE appointments SET reminder_12_sent = ? WHERE id = ?",
                    (1 if r12 else 0, appt_id),
                )
            await db.commit()

    async def list_pending(self) -> list[AppointmentRow]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT * FROM appointments WHERE status = 'PENDING'
                ORDER BY start_at
                """
            )
            rows = await cur.fetchall()
            return [_row_to_appt(r) for r in rows]

    async def list_appointments_starting_moscow_day(
        self, d: date, tz_name: str
    ) -> list[AppointmentRow]:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo(tz_name)
        day_start = datetime.combine(d, dtime.min, tzinfo=tz)
        day_end = day_start + timedelta(days=1)
        su = _dt_to_utc_z(day_start)
        eu = _dt_to_utc_z(day_end)
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT * FROM appointments
                WHERE start_at >= ? AND start_at < ?
                AND status NOT IN ('CANCELLED', 'DECLINED')
                ORDER BY start_at
                """,
                (su, eu),
            )
            rows = await cur.fetchall()
            return [_row_to_appt(r) for r in rows]

    async def fetch_appointments_overlapping_range(
        self,
        range_start: datetime,
        range_end: datetime,
        exclude_id: int | None = None,
    ) -> list[AppointmentRow]:
        su = _dt_to_utc_z(range_start)
        eu = _dt_to_utc_z(range_end)
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            sql = """
                SELECT * FROM appointments
                WHERE end_at > ? AND start_at < ?
                AND status NOT IN ('CANCELLED', 'DECLINED')
            """
            params: list[Any] = [su, eu]
            if exclude_id is not None:
                sql += " AND id != ?"
                params.append(exclude_id)
            cur = await db.execute(sql, params)
            rows = await cur.fetchall()
            return [_row_to_appt(r) for r in rows]

    async def count_phone_bookings_moscow_day(
        self,
        phone_norm: str,
        moscow_date: date,
        tz_name: str,
        exclude_id: int | None = None,
    ) -> int:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo(tz_name)
        day_start = datetime.combine(moscow_date, dtime.min, tzinfo=tz)
        day_end = day_start + timedelta(days=1)
        su = _dt_to_utc_z(day_start)
        eu = _dt_to_utc_z(day_end)
        async with aiosqlite.connect(self.path) as db:
            sql = """
                SELECT COUNT(*) FROM appointments
                WHERE client_phone_norm = ?
                AND start_at >= ? AND start_at < ?
                AND status IN ('PENDING', 'CONFIRMED', 'RESCHEDULE_PROPOSED')
            """
            params: list[Any] = [phone_norm, su, eu]
            if exclude_id is not None:
                sql += " AND id != ?"
                params.append(exclude_id)
            cur = await db.execute(sql, params)
            row = await cur.fetchone()
            return int(row[0]) if row else 0

    async def client_future_appointments(self, tg_id: int) -> list[AppointmentRow]:
        now = _dt_to_utc_z(datetime.now(timezone.utc))
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT * FROM appointments
                WHERE client_tg_id = ?
                AND end_at > ?
                AND status IN ('PENDING', 'CONFIRMED', 'RESCHEDULE_PROPOSED')
                ORDER BY start_at
                """,
                (tg_id, now),
            )
            rows = await cur.fetchall()
            return [_row_to_appt(r) for r in rows]

    async def list_upcoming_appointments_all(self) -> list[AppointmentRow]:
        """Все будущие записи/заявки (для админа, без фильтра по дате)."""
        now = _dt_to_utc_z(datetime.now(timezone.utc))
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT * FROM appointments
                WHERE end_at > ? AND status NOT IN ('CANCELLED', 'DECLINED')
                ORDER BY start_at
                """,
                (now,),
            )
            rows = await cur.fetchall()
            return [_row_to_appt(r) for r in rows]

    async def list_confirmed_future_for_reminders(self) -> list[AppointmentRow]:
        now = _dt_to_utc_z(datetime.now(timezone.utc))
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT * FROM appointments
                WHERE status = 'CONFIRMED' AND end_at > ?
                ORDER BY start_at
                """,
                (now,),
            )
            rows = await cur.fetchall()
            return [_row_to_appt(r) for r in rows]

    async def insert_blocked(
        self,
        start_at: datetime,
        end_at: datetime,
        created_by_username: str | None,
    ) -> int:
        now = utc_now_iso()
        sa = _dt_to_utc_z(start_at)
        ea = _dt_to_utc_z(end_at)
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                """
                INSERT INTO blocked_windows (start_at, end_at, created_by_username, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (sa, ea, created_by_username, now),
            )
            await db.commit()
            return int(cur.lastrowid)

    async def list_blocked_between(
        self, range_start: datetime, range_end: datetime
    ) -> list[dict[str, Any]]:
        su = _dt_to_utc_z(range_start)
        eu = _dt_to_utc_z(range_end)
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT * FROM blocked_windows
                WHERE end_at > ? AND start_at < ?
                ORDER BY start_at
                """,
                (su, eu),
            )
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def delete_blocked(self, block_id: int) -> bool:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "DELETE FROM blocked_windows WHERE id = ?", (block_id,)
            )
            await db.commit()
            return cur.rowcount > 0

    async def list_admin_tg_ids(self) -> list[int]:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("SELECT tg_id FROM admins")
            rows = await cur.fetchall()
            return [int(r[0]) for r in rows]


def blocking_intervals_utc(ap: AppointmentRow) -> list[tuple[datetime, datetime]]:
    out: list[tuple[datetime, datetime]] = []
    if ap.status in ("PENDING", "CONFIRMED"):
        out.append((parse_iso(ap.start_at), parse_iso(ap.end_at)))
    elif ap.status == "RESCHEDULE_PROPOSED":
        out.append((parse_iso(ap.start_at), parse_iso(ap.end_at)))
        if ap.proposed_start_at and ap.proposed_end_at:
            out.append(
                (parse_iso(ap.proposed_start_at), parse_iso(ap.proposed_end_at))
            )
    return out


def intervals_overlap(
    a0: datetime, a1: datetime, b0: datetime, b1: datetime
) -> bool:
    return a0 < b1 and b0 < a1

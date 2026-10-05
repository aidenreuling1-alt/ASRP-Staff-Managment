"""Run the development Discord bot with DISCORD_TOKEN set in the environment."""

import os
import json
import asyncio
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Generator
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks

PUNISHMENT_CHANNEL_ID = 1513827137109360712
PROMOTION_CHANNEL_ID = 1513157154474033269
ZTP_LOG_CHANNEL_ID = 1556373690248339497
UNDER_INVESTIGATION_ROLE_ID = 1517412418915930184
SUSPENDED_STAFF_ROLE_ID = 1514587990289158184
RETIRED_STAFF_ROLE_ID = 1513157147578597500
PUNISHMENT_ROLE_IDS: dict[str, tuple[int, int, int]] = {
    "Warning": (1520805516794921153, 1520805603776135322, 1521166004464517221),
    "Infraction": (1521166249155891322, 1521166315346329791, 1521166444287492128),
    "Strike": (1521166590001807470, 1521166665289830624, 1521166705257353287),
}
PUNISHMENT_ROLE_ID_SET = {
    role_id for role_ids in PUNISHMENT_ROLE_IDS.values() for role_id in role_ids
}
CASE_DATABASE_PATH = Path(__file__).with_name("staff_cases.sqlite3")
PUNISHMENT_BANNER_PATH = Path(__file__).parent / "assets" / "staff_discipline_banner.png"
PUNISHMENT_BANNER_FILENAME = "staff_discipline_banner.png"
PROMOTION_BANNER_PATH = Path(__file__).parent / "assets" / "staff_promotion_banner.png"
PROMOTION_BANNER_FILENAME = "staff_promotion_banner.png"
RETIREMENT_BANNER_PATH = Path(__file__).parent / "assets" / "staff_retirement_banner.png"
RETIREMENT_BANNER_FILENAME = "staff_retirement_banner.png"
MAX_REINSTATEMENTS = 2
try:
    EASTERN_TIME = ZoneInfo("America/New_York")
except ZoneInfoNotFoundError:
    EASTERN_TIME = None
    print(
        "Warning: tzdata is unavailable; using the Windows local timezone for "
        "Eastern timestamps. Install requirements.txt for explicit Eastern time."
    )
REVOCATION_OVERRIDE_ROLE_IDS = {
    1554595522101125120,
    1515750811244953600,
    1529572338901717273,
    1513830140289880115,
    1513157147741913227,
    1513157147779797043,
    1513157147779797044,
    1516349051271118958,
    1516348878788755578,
    1516348759242706944,
    1513829901004837016,
}

STAFF_ROLE_IDS: dict[str, int] = {
    "Staff Team": 1513157147683197023,
    "Moderation Team": 1514999940617736434,
    "Trial Moderator": 1513157147683197027,
    "Junior Moderator": 1513157147700232315,
    "Moderator": 1513157147700232316,
    "Senior Moderator": 1513513068712296549,
    "Administration Team": 1515749492799045733,
    "Trial Administrator": 1515749380731310141,
    "Junior Administrator": 1515749378147750101,
    "Administrator": 1515749375056412864,
    "Senior Administrator": 1515749371289927740,
    "HR": 1515749120814354573,
    "Internal Affairs Team": 1515750290605740242,
    "Trial Internal Affairs": 1515750280837337310,
    "Junior Internal Affairs": 1515750283236475021,
    "Internal Affairs": 1515750285367312524,
    "Senior Internal Affairs": 1515750287665528932,
    "Internal Affairs Director": 1515750289586520256,
    "SHR": 1554595522101125120,
    "Management Team": 1513157147741913222,
    "Trial Managment": 1515751170709389386,
    "Junior Managment": 1515751092003016937,
    "Managment": 1515751042145583206,
    "Senior Managment": 1515750966354251826,
    "Director Of Managment": 1515750811244953600,
    "Community Manager": 1529572338901717273,
    "Board Of Directors": 1513830140289880115,
    "Assistant Director": 1513157147741913227,
    "Deputy Director": 1513157147779797043,
    "Director": 1513157147779797044,
    "Ownership": 1516349051271118958,
    "Assistant Owner": 1516348878788755578,
    "Co Owner": 1516348759242706944,
    "Owner": 1513829901004837016
}
STAFF_ROLE_ID_SET = set(STAFF_ROLE_IDS.values())
IA_REVIEWER_ROLE_IDS = {
    1515750290605740242,
    1515750280837337310,
    1515750283236475021,
    1515750285367312524,
    1515750287665528932,
    1515750289586520256,
    1554595522101125120,
    1513157147741913222,
    1515751170709389386,
    1515751092003016937,
    1515751042145583206,
    1515750966354251826,
    1515750811244953600,
    1529572338901717273,
    1513830140289880115,
    1513157147741913227,
    1513157147779797043,
    1513157147779797044,
    1516349051271118958,
    1516348878788755578,
    1516348759242706944,
    1513829901004837016,
}
MGMT_REVIEWER_ROLE_IDS = {
    1513157147741913222,
    1515751170709389386,
    1515751092003016937,
    1515751042145583206,
    1515750966354251826,
    1515750811244953600,
    1529572338901717273,
    1513830140289880115,
    1513157147741913227,
    1513157147779797043,
    1513157147779797044,
    1516349051271118958,
    1516348878788755578,
    1516348759242706944,
    1513829901004837016,
}
BOD_REVIEWER_ROLE_IDS = {
    1513830140289880115,
    1516349051271118958,
    1516348878788755578,
    1516348759242706944,
    1513829901004837016,
}
OWNERSHIP_ROLE_IDS = {
    1516349051271118958,
    1516348878788755578,
    1516348759242706944,
    1513829901004837016,
}
DISCORD_REQUEST_ERRORS = (
    discord.HTTPException,
    aiohttp.ClientError,
    OSError,
    asyncio.TimeoutError,
)


@contextmanager
def database_connection() -> Generator[sqlite3.Connection, None, None]:
    connection = sqlite3.connect(CASE_DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    except sqlite3.Error:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database() -> None:
    with database_connection() as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS punishment_cases "
            "(case_id INTEGER PRIMARY KEY AUTOINCREMENT)"
        )
        existing_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(punishment_cases)")
        }
        columns = {
            "member_id": "INTEGER",
            "punishment": "TEXT",
            "reason": "TEXT",
            "appealable": "INTEGER",
            "appealable_by": "TEXT",
            "status": "TEXT NOT NULL DEFAULT 'active'",
            "message_id": "INTEGER",
            "created_at": "TEXT",
            "removed_role_ids": "TEXT",
            "guild_id": "INTEGER",
            "suspension_until": "TEXT",
            "demotion_old_rank_id": "INTEGER",
            "demotion_new_rank_id": "INTEGER",
            "demotion_added_role_ids": "TEXT",
            "termination_due_at": "TEXT",
        }
        for name, definition in columns.items():
            if name not in existing_columns:
                connection.execute(
                    f"ALTER TABLE punishment_cases ADD COLUMN {name} {definition}"
                )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS case_actions ("
            "action_id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "case_id INTEGER NOT NULL, action_type TEXT NOT NULL, "
            "actor_id INTEGER NOT NULL, target_id INTEGER NOT NULL, "
            "ticket_number TEXT, reason TEXT, result TEXT, "
            "created_at TEXT NOT NULL, message_id INTEGER, "
            "status TEXT NOT NULL DEFAULT 'pending')"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS promotion_cases ("
            "case_id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "member_id INTEGER NOT NULL, old_rank TEXT NOT NULL, "
            "new_rank_id INTEGER NOT NULL, reason TEXT NOT NULL, "
            "signed_name TEXT NOT NULL, issuer_id INTEGER NOT NULL, "
            "guild_id INTEGER NOT NULL, created_at TEXT NOT NULL, "
            "message_id INTEGER, status TEXT NOT NULL DEFAULT 'pending')"
        )
        existing_promotion_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(promotion_cases)")
        }
        promotion_columns = {
            "added_role_ids": "TEXT",
            "removed_role_ids": "TEXT",
            "roles_tracked": "INTEGER NOT NULL DEFAULT 0",
            "dm_sent": "INTEGER NOT NULL DEFAULT 0",
            "ticket_number": "TEXT",
            "action_type": "TEXT NOT NULL DEFAULT 'promotion'",
        }
        for name, definition in promotion_columns.items():
            if name not in existing_promotion_columns:
                connection.execute(
                    f"ALTER TABLE promotion_cases ADD COLUMN {name} {definition}"
                )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS ztp_cases ("
            "ztp_id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "member_id INTEGER NOT NULL, guild_id INTEGER NOT NULL, "
            "reason TEXT NOT NULL, duration_days INTEGER NOT NULL, "
            "starts_at TEXT NOT NULL, expires_at TEXT NOT NULL, "
            "issuer_id INTEGER NOT NULL, source TEXT NOT NULL, "
            "source_case_id INTEGER, triggered_case_id INTEGER, "
            "status TEXT NOT NULL DEFAULT 'active')"
        )
        existing_ztp_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(ztp_cases)")
        }
        ztp_columns = {
            "ended_at": "TEXT",
            "ended_by": "INTEGER",
        }
        for name, definition in ztp_columns.items():
            if name not in existing_ztp_columns:
                connection.execute(
                    f"ALTER TABLE ztp_cases ADD COLUMN {name} {definition}"
                )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS reinstatement_resets ("
            "reset_id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "member_id INTEGER NOT NULL, guild_id INTEGER NOT NULL, "
            "cutoff_case_id INTEGER NOT NULL, reset_by INTEGER NOT NULL, "
            "created_at TEXT NOT NULL)"
        )


def create_case_id() -> int:
    """Create a persistent case row and return its sequential case number."""
    initialize_database()
    with database_connection() as connection:
        cursor = connection.execute("INSERT INTO punishment_cases DEFAULT VALUES")
        if cursor.lastrowid is None:
            raise RuntimeError("Could not create a punishment case ID.")
        case_id = cursor.lastrowid
    return case_id


def get_case(case_id: int) -> sqlite3.Row | None:
    initialize_database()
    with database_connection() as connection:
        row = connection.execute(
            "SELECT * FROM punishment_cases WHERE case_id = ?",
            (case_id,),
        ).fetchone()
    return row


def get_member_punishment_cases(member_id: int, guild_id: int) -> list[sqlite3.Row]:
    initialize_database()
    with database_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM punishment_cases "
            "WHERE member_id = ? AND guild_id = ? "
            "AND punishment IS NOT NULL AND status != 'failed' "
            "ORDER BY case_id DESC",
            (member_id, guild_id),
        ).fetchall()
    return rows


def get_member_promotion_cases(member_id: int, guild_id: int) -> list[sqlite3.Row]:
    initialize_database()
    with database_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM promotion_cases WHERE member_id = ? AND guild_id = ? "
            "AND status != 'failed' ORDER BY case_id DESC",
            (member_id, guild_id),
        ).fetchall()
    return rows


def get_active_cases_for_member(member_id: int) -> list[sqlite3.Row]:
    initialize_database()
    with database_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM punishment_cases WHERE member_id = ? AND status = 'active'",
            (member_id,),
        ).fetchall()
    return rows


def get_active_punishment_counts(member_id: int) -> tuple[int, int]:
    initialize_database()
    with database_connection() as connection:
        rows = connection.execute(
            "SELECT punishment, COUNT(*) AS amount FROM punishment_cases "
            "WHERE member_id = ? AND status = 'active' "
            "AND punishment IN ('Strike', 'Infraction') GROUP BY punishment",
            (member_id,),
        ).fetchall()
    counts = {row["punishment"]: row["amount"] for row in rows}
    return counts.get("Strike", 0), counts.get("Infraction", 0)


def get_active_punishment_count(
    member_id: int,
    guild_id: int,
    punishment: str,
) -> int:
    initialize_database()
    with database_connection() as connection:
        row = connection.execute(
            "SELECT COUNT(*) AS amount FROM punishment_cases "
            "WHERE member_id = ? AND guild_id = ? AND punishment = ? AND status = 'active'",
            (member_id, guild_id, punishment),
        ).fetchone()
    return int(row["amount"]) if row is not None else 0


def get_punishment_role_plan(
    guild: discord.Guild,
    member: discord.Member,
    counts: dict[str, int],
) -> tuple[list[discord.Role], list[discord.Role]] | str:
    target_role_ids = {
        role_ids[min(max(counts.get(punishment, 0), 0), len(role_ids)) - 1]
        for punishment, role_ids in PUNISHMENT_ROLE_IDS.items()
        if counts.get(punishment, 0) > 0
    }
    current_role_ids = {
        role.id for role in member.roles if role.id in PUNISHMENT_ROLE_ID_SET
    }
    missing_role_ids = (target_role_ids | current_role_ids) - {
        role.id for role in guild.roles
    }
    if missing_role_ids:
        return (
            "I could not find all punishment-tier roles in this server: "
            + ", ".join(str(role_id) for role_id in sorted(missing_role_ids))
        )
    roles_to_add = [
        role for role_id in target_role_ids - current_role_ids
        if (role := guild.get_role(role_id)) is not None
    ]
    roles_to_remove = [
        role for role_id in current_role_ids - target_role_ids
        if (role := guild.get_role(role_id)) is not None
    ]
    return roles_to_add, roles_to_remove


def plan_punishment_escalation(
    member_id: int,
    guild_id: int,
    requested_punishment: str,
) -> tuple[str, dict[str, int], list[int]]:
    projected_counts = {
        punishment: get_active_punishment_count(member_id, guild_id, punishment)
        for punishment in PUNISHMENT_ROLE_IDS
    }
    case_punishment = requested_punishment
    converted_case_ids: list[int] = []
    while (
        case_punishment in {"Warning", "Infraction"}
        and projected_counts[case_punishment] >= 2
    ):
        with database_connection() as connection:
            previous_cases = connection.execute(
                "SELECT case_id FROM punishment_cases "
                "WHERE member_id = ? AND guild_id = ? AND punishment = ? AND status = 'active' "
                "ORDER BY case_id",
                (member_id, guild_id, case_punishment),
            ).fetchall()
        converted_case_ids.extend(row["case_id"] for row in previous_cases)
        projected_counts[case_punishment] = 0
        case_punishment = "Infraction" if case_punishment == "Warning" else "Strike"
    projected_counts[case_punishment] = projected_counts.get(case_punishment, 0) + 1
    return case_punishment, projected_counts, converted_case_ids


async def sync_punishment_roles(
    guild: discord.Guild,
    member: discord.Member,
) -> str | None:
    counts = {
        punishment: get_active_punishment_count(member.id, guild.id, punishment)
        for punishment in PUNISHMENT_ROLE_IDS
    }
    plan = get_punishment_role_plan(guild, member, counts)
    if isinstance(plan, str):
        return plan
    roles_to_add, roles_to_remove = plan
    if not roles_to_add and not roles_to_remove:
        return None
    bot_member = guild.me
    if (
        bot_member is None
        or not bot_member.guild_permissions.manage_roles
        or member.id == guild.owner_id
        or member.top_role >= bot_member.top_role
        or any(role >= bot_member.top_role for role in roles_to_add + roles_to_remove)
    ):
        return "The bot's permissions or role hierarchy prevents syncing punishment roles."
    updated_roles = [role for role in member.roles if role not in roles_to_remove]
    updated_roles.extend(role for role in roles_to_add if role not in updated_roles)
    try:
        await member.edit(
            roles=updated_roles,
            reason="Syncing punishment-tier roles with active case records",
        )
    except DISCORD_REQUEST_ERRORS as error:
        print(f"Could not sync punishment roles for member {member.id}: {error}")
        return "Discord could not sync this member's punishment-tier roles."
    return None


def get_active_suspensions() -> list[sqlite3.Row]:
    initialize_database()
    with database_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM punishment_cases WHERE punishment = 'Suspension' "
            "AND status = 'active' AND suspension_until IS NOT NULL"
        ).fetchall()
    now = datetime.now(EASTERN_TIME) if EASTERN_TIME else datetime.now().astimezone()
    return [
        row
        for row in rows
        if datetime.fromisoformat(row["suspension_until"]) <= now
    ]


def get_active_ztp(member_id: int, guild_id: int) -> sqlite3.Row | None:
    initialize_database()
    now = datetime.now(EASTERN_TIME) if EASTERN_TIME else datetime.now().astimezone()
    with database_connection() as connection:
        row = connection.execute(
            "SELECT * FROM ztp_cases WHERE member_id = ? AND guild_id = ? "
            "AND status = 'active' ORDER BY ztp_id DESC LIMIT 1",
            (member_id, guild_id),
        ).fetchone()
    if row is None:
        return None
    if datetime.fromisoformat(row["expires_at"]) <= now:
        with database_connection() as connection:
            connection.execute(
                "UPDATE ztp_cases SET status = 'completed' "
                "WHERE ztp_id = ? AND status = 'active'",
                (row["ztp_id"],),
            )
        return None
    return row


def format_ztp_id(ztp_id: int) -> str:
    return f"ZTP-{ztp_id:05d}"


def format_time_remaining(expires_at: str) -> str:
    expiration = datetime.fromisoformat(expires_at)
    now = datetime.now(expiration.tzinfo) if expiration.tzinfo else datetime.now()
    remaining_seconds = max(0, int((expiration - now).total_seconds()))
    days, remaining_seconds = divmod(remaining_seconds, 86400)
    hours, remaining_seconds = divmod(remaining_seconds, 3600)
    minutes = remaining_seconds // 60
    parts: list[str] = []
    if days:
        parts.append(f"{days} day(s)")
    if hours:
        parts.append(f"{hours} hour(s)")
    if minutes or not parts:
        parts.append(f"{minutes} minute(s)")
    return ", ".join(parts)


def create_ztp_case(
    member_id: int,
    guild_id: int,
    reason: str,
    duration_days: int,
    issuer_id: int,
    source: str,
    source_case_id: int | None,
    status: str = "active",
) -> int:
    initialize_database()
    starts_at = datetime.now(EASTERN_TIME) if EASTERN_TIME else datetime.now().astimezone()
    expires_at = starts_at + timedelta(days=duration_days)
    with database_connection() as connection:
        cursor = connection.execute(
            "INSERT INTO ztp_cases "
            "(member_id, guild_id, reason, duration_days, starts_at, expires_at, "
            "issuer_id, source, source_case_id, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                member_id,
                guild_id,
                reason,
                duration_days,
                starts_at.isoformat(),
                expires_at.isoformat(),
                issuer_id,
                source,
                source_case_id,
                status,
            ),
        )
        if cursor.lastrowid is None:
            raise RuntimeError("Could not create a ZTP ID.")
        return cursor.lastrowid


def get_ztp_case(ztp_id: int, guild_id: int) -> sqlite3.Row | None:
    initialize_database()
    with database_connection() as connection:
        return connection.execute(
            "SELECT * FROM ztp_cases WHERE ztp_id = ? AND guild_id = ?",
            (ztp_id, guild_id),
        ).fetchone()


def get_active_ztp_cases(guild_id: int) -> list[sqlite3.Row]:
    initialize_database()
    now = datetime.now(EASTERN_TIME) if EASTERN_TIME else datetime.now().astimezone()
    with database_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM ztp_cases WHERE guild_id = ? AND status = 'active' "
            "ORDER BY expires_at, ztp_id",
            (guild_id,),
        ).fetchall()
    active: list[sqlite3.Row] = []
    expired_ids: list[int] = []
    for row in rows:
        if datetime.fromisoformat(row["expires_at"]) <= now:
            expired_ids.append(row["ztp_id"])
        else:
            active.append(row)
    if expired_ids:
        with database_connection() as connection:
            connection.executemany(
                "UPDATE ztp_cases SET status = 'completed' "
                "WHERE ztp_id = ? AND status = 'active'",
                [(ztp_id,) for ztp_id in expired_ids],
            )
    return active


def can_review_appeal(member: discord.Member, appealable_by: str | None) -> bool:
    role_ids = {role.id for role in member.roles}
    if appealable_by == "IA+":
        return bool(role_ids & IA_REVIEWER_ROLE_IDS)
    if appealable_by == "MGMT+":
        return bool(role_ids & MGMT_REVIEWER_ROLE_IDS)
    if appealable_by == "BoD+":
        return bool(role_ids & BOD_REVIEWER_ROLE_IDS)
    return bool(role_ids & OWNERSHIP_ROLE_IDS)


def get_case_role_ids(case: sqlite3.Row) -> list[int]:
    try:
        role_ids = json.loads(case["removed_role_ids"] or "[]")
    except (json.JSONDecodeError, TypeError) as error:
        raise ValueError("This case has invalid saved role data.") from error
    if not isinstance(role_ids, list) or any(not isinstance(role_id, int) for role_id in role_ids):
        raise ValueError("This case has invalid saved role data.")
    return role_ids


async def restore_case_staff_roles(
    guild: discord.Guild,
    member: discord.Member,
    case: sqlite3.Row,
    special_role_ids: set[int],
) -> str | None:
    if case["removed_role_ids"] is None:
        return "This case has no saved staff-role history, so the roles cannot be safely restored."
    bot_member = guild.me
    if bot_member is None or not bot_member.guild_permissions.manage_roles:
        return "I need Manage Roles permission to restore this member."
    if member.id == guild.owner_id or member.top_role >= bot_member.top_role:
        return "The bot's role hierarchy prevents restoring this member's roles."
    try:
        saved_role_ids = get_case_role_ids(case)
    except ValueError as error:
        return str(error)
    roles_to_restore = [
        role for role_id in saved_role_ids if (role := guild.get_role(role_id)) is not None
    ]
    if any(role >= bot_member.top_role for role in roles_to_restore):
        return "Move the bot role above all the staff roles that need restoring."
    updated_roles = [
        role for role in member.roles
        if role.id not in STAFF_ROLE_ID_SET and role.id not in special_role_ids
    ]
    updated_roles.extend(role for role in roles_to_restore if role not in updated_roles)
    try:
        await member.edit(
            roles=updated_roles,
            reason=f"Restoring staff roles for case #{case['case_id']}",
        )
    except discord.HTTPException as error:
        print(f"Role restoration failed for case #{case['case_id']}: {error}")
        return "Discord could not restore the member's staff roles."
    return None


def eastern_timestamp() -> tuple[str, str]:
    now = (
        datetime.now(EASTERN_TIME)
        if EASTERN_TIME is not None
        else datetime.now().astimezone()
    )
    return now.isoformat(), now.strftime("%B %d, %Y at %I:%M %p %Z")


def get_layout_text_displays(
    layout: discord.ui.LayoutView,
) -> list[discord.ui.TextDisplay]:
    text_displays = [
        item
        for item in layout.walk_children()
        if isinstance(item, discord.ui.TextDisplay)
    ]
    for item in text_displays:
        if not isinstance(item.content, str):
            item.content = ""
    return text_displays


def build_punishment_view(
    member: discord.Member,
    punishment: str,
    reason: str,
    appealable: str,
    appealable_by: str,
    proof: str,
    issuer: discord.Member | discord.User,
    case_id: int,
    old_rank: discord.Role | None = None,
    new_rank: discord.Role | None = None,
) -> discord.ui.LayoutView:
    layout = discord.ui.LayoutView(timeout=None)
    container = discord.ui.Container(accent_color=discord.Color.from_rgb(54, 57, 63))
    gallery = discord.ui.MediaGallery()
    gallery.add_item(
        media=f"attachment://{PUNISHMENT_BANNER_FILENAME}",
        description="Arkansas State Roleplay Staff Discipline",
    )
    container.add_item(gallery)
    container.add_item(
        discord.ui.Separator(
            visible=True,
            spacing=discord.SeparatorSpacing.small,
        )
    )
    rank_details = (
        f"**Old Rank:** {old_rank.mention}\n**New Rank:** {new_rank.mention}\n"
        if old_rank is not None and new_rank is not None
        else ""
    )
    details = (
        "# Staff Discipline\n"
        "> **The high ranking team has decided to issue this punishment based on "
        "the member's actions. Please use the appeal process if eligible.**\n\n"
        f"**Staff member:** {member.mention}\n"
        f"**Punishment:** {punishment}\n"
        f"{rank_details}"
        f"**Reason:** {reason}\n"
        f"**Appealable:** {appealable}\n"
        f"**Appealable By:** {appealable_by}\n"
        f"**Proof:** {proof}\n"
        f"**Signed:** {issuer.mention}\n"
        f"*Case #{case_id}*"
    )
    container.add_item(discord.ui.TextDisplay(details))
    layout.add_item(container)
    return layout


def build_promotion_view(
    member: discord.Member | discord.User | str,
    old_rank: str,
    new_rank: discord.Role | str,
    reason: str,
    signed_name: str,
    case_id: int,
    revoked: bool = False,
    ztp_id: str | None = None,
    ztp_expires_at: str | None = None,
    ticket_number: str | None = None,
) -> discord.ui.LayoutView:
    layout = discord.ui.LayoutView(timeout=None)
    container = discord.ui.Container(accent_color=discord.Color.from_rgb(54, 57, 63))
    gallery = discord.ui.MediaGallery()
    gallery.add_item(
        media=f"attachment://{PROMOTION_BANNER_FILENAME}",
        description="Arkansas State Roleplay Staff Promotions",
    )
    container.add_item(gallery)
    container.add_item(
        discord.ui.Separator(
            visible=True,
            spacing=discord.SeparatorSpacing.small,
        )
    )
    member_mention = member if isinstance(member, str) else member.mention
    rank_mention = new_rank if isinstance(new_rank, str) else new_rank.mention
    if revoked:
        details = (
            "# Staff Promotion — REVOKED\n"
            f"~~**Promoted Member:** {member_mention}~~\n"
            f"~~**Old Rank:** {discord.utils.escape_markdown(old_rank)}~~\n"
            f"~~**New Rank:** {rank_mention}~~\n"
            f"~~**Reason:** {discord.utils.escape_markdown(reason)}~~\n"
            f"~~**Signed:** {discord.utils.escape_markdown(signed_name)}~~\n\n"
            f"*Promotion Case #{case_id} · Revoked*"
        )
    else:
        ticket_details = (
            f"**Ticket:** #{discord.utils.escape_markdown(ticket_number)}\n"
            if ticket_number is not None
            else ""
        )
        ztp_details = (
            "### ⚠️ Zero Tolerance Period (1 week): "
            f"Active until {ztp_expires_at}\n\n"
            "### Any punishment other than a warning during this period will be "
            "escalated to a **Demotion to Awaiting Training**, and your in-game "
            "permissions will be removed.\n\n"
            if ztp_id is not None and ztp_expires_at is not None
            else ""
        )
        details = (
            "# Staff Promotion\n"
            f"**Promoted Member:** {member_mention}\n"
            f"**Old Rank:** {discord.utils.escape_markdown(old_rank)}\n"
            f"**New Rank:** {rank_mention}\n"
            f"**Reason:** {discord.utils.escape_markdown(reason)}\n"
            f"{ticket_details}"
            f"**Signed:** {discord.utils.escape_markdown(signed_name)}\n\n"
            f"{ztp_details}"
            f"*Promotion Case #{case_id}*"
        )
    container.add_item(discord.ui.TextDisplay(details))
    layout.add_item(container)
    return layout


def build_retirement_view(
    member: discord.Member | discord.User | str,
    rank: str,
    ticket_number: str,
    discord_staff: bool,
    reinstatements_left: int,
    signed_name: str,
    case_id: int,
) -> discord.ui.LayoutView:
    layout = discord.ui.LayoutView(timeout=None)
    container = discord.ui.Container(accent_color=discord.Color.from_rgb(54, 57, 63))
    gallery = discord.ui.MediaGallery()
    gallery.add_item(
        media=f"attachment://{RETIREMENT_BANNER_FILENAME}",
        description="Arkansas State Roleplay Staff Retirements",
    )
    container.add_item(gallery)
    container.add_item(
        discord.ui.Separator(
            visible=True,
            spacing=discord.SeparatorSpacing.small,
        )
    )
    member_mention = member if isinstance(member, str) else member.mention
    member_name = (
        member.display_name
        if isinstance(member, discord.Member)
        else member.name
        if isinstance(member, discord.User)
        else member_mention
    )
    details = (
        f"> {member_mention} has officially retired from Arkansas State Roleplay.\n\n"
        "## Staff Retirement\n"
        f"> We would like to extend our sincere gratitude for the time, dedication, "
        f"and effort that {discord.utils.escape_markdown(member_name)} brought to the team. "
        "Their contributions have left a lasting impact, and they will always be "
        "part of our community's history.\n>\n"
        f"> We wish {discord.utils.escape_markdown(member_name)} all the best in their future "
        "endeavors and hope they continue to thrive in their personal and professional "
        "lives. Thank you for being a part of our team and for the positive influence "
        "you had on our community.\n\n"
        f"> **Staff member:** {member_mention}\n>\n"
        f"> **Rank:** {discord.utils.escape_markdown(rank)}\n>\n"
        f"> **Ticket:** #{discord.utils.escape_markdown(ticket_number)}\n>\n"
        f"> **Discord staff:** {'Yes' if discord_staff else 'No'}\n>\n"
        f"> **Reinstatements left:** {reinstatements_left}\n>\n"
        f"> **Signed:** {discord.utils.escape_markdown(signed_name)}\n\n"
        f"*Case #{case_id}*"
    )
    container.add_item(discord.ui.TextDisplay(details))
    layout.add_item(container)
    return layout


def get_promotion_role_changes(
    member: discord.Member,
    old_rank: str,
    new_rank: discord.Role,
) -> tuple[list[discord.Role], list[discord.Role]] | str:
    role_ids_to_add = {new_rank.id}
    role_ids_to_remove: set[int] = set()

    team_ranks = {
        "Moderation Team": (
            "Trial Moderator",
            "Junior Moderator",
            "Moderator",
            "Senior Moderator",
        ),
        "Administration Team": (
            "Trial Administrator",
            "Junior Administrator",
            "Administrator",
            "Senior Administrator",
        ),
        "Internal Affairs Team": (
            "Trial Internal Affairs",
            "Junior Internal Affairs",
            "Internal Affairs",
            "Senior Internal Affairs",
            "Internal Affairs Director",
        ),
        "Management Team": (
            "Trial Managment",
            "Junior Managment",
            "Managment",
            "Senior Managment",
            "Director Of Managment",
        ),
    }
    team_role_ids = {
        STAFF_ROLE_IDS[team_name] for team_name in team_ranks
    }

    normalized_old_rank = "".join(character for character in old_rank.casefold() if character.isalnum())
    old_rank_aliases = {
        "directorofinternalaffairs": "internalaffairsdirector",
    }
    normalized_old_rank = old_rank_aliases.get(normalized_old_rank, normalized_old_rank)
    former_staff = normalized_old_rank == "formerstaff"
    old_rank_name = next(
        (
            rank_name
            for rank_name in STAFF_ROLE_IDS
            if "".join(character for character in rank_name.casefold() if character.isalnum())
            == normalized_old_rank
            and any(rank_name in ranks for ranks in team_ranks.values())
        ),
        None,
    )
    if old_rank_name is None and not former_staff:
        return "Old Rank must match a configured staff rank so I can safely replace it."

    if former_staff:
        role_ids_to_remove.update(STAFF_ROLE_ID_SET)
        role_ids_to_remove.add(RETIRED_STAFF_ROLE_ID)
    elif old_rank_name is not None:
        role_ids_to_remove.add(STAFF_ROLE_IDS[old_rank_name])
    old_team_role_id = next(
        (
            STAFF_ROLE_IDS[team_name]
            for team_name, ranks in team_ranks.items()
            if old_rank_name is not None and old_rank_name in ranks
        ),
        None,
    )
    new_team_role_id = next(
        (
            STAFF_ROLE_IDS[team_name]
            for team_name, ranks in team_ranks.items()
            if any(STAFF_ROLE_IDS[rank_name] == new_rank.id for rank_name in ranks)
        ),
        None,
    )

    if old_team_role_id != new_team_role_id:
        role_ids_to_remove.update(team_role_ids)
    if new_team_role_id is not None:
        role_ids_to_add.add(new_team_role_id)

    if new_team_role_id == STAFF_ROLE_IDS["Internal Affairs Team"]:
        role_ids_to_add.add(STAFF_ROLE_IDS["HR"])
        role_ids_to_remove.add(STAFF_ROLE_IDS["SHR"])
    elif new_team_role_id == STAFF_ROLE_IDS["Management Team"]:
        role_ids_to_add.add(STAFF_ROLE_IDS["SHR"])
        role_ids_to_remove.add(STAFF_ROLE_IDS["HR"])
    else:
        role_ids_to_remove.update(
            {STAFF_ROLE_IDS["HR"], STAFF_ROLE_IDS["SHR"]}
        )

    current_role_ids = {role.id for role in member.roles}
    add_ids = role_ids_to_add - current_role_ids
    remove_ids = role_ids_to_remove & current_role_ids
    guild = member.guild
    missing_role_ids = [
        role_id
        for role_id in add_ids | remove_ids
        if guild.get_role(role_id) is None
    ]
    if missing_role_ids:
        return "I could not find all required promotion roles in this server."

    roles_to_add = [guild.get_role(role_id) for role_id in add_ids]
    roles_to_remove = [guild.get_role(role_id) for role_id in remove_ids]
    return (
        [role for role in roles_to_add if role is not None],
        [role for role in roles_to_remove if role is not None],
    )


def get_demotion_role_changes(
    member: discord.Member,
    old_rank: discord.Role,
    new_rank: discord.Role,
) -> tuple[list[discord.Role], list[discord.Role]] | str:
    if old_rank.id == new_rank.id:
        return "Old Rank and New Rank must be different."
    if old_rank.id not in STAFF_ROLE_ID_SET or new_rank.id not in STAFF_ROLE_ID_SET:
        return "Choose configured staff roles for both demotion ranks."
    if old_rank not in member.roles:
        return "The member does not currently have the selected Old Rank role."

    ia_rank_names = (
        "Trial Internal Affairs",
        "Junior Internal Affairs",
        "Internal Affairs",
        "Senior Internal Affairs",
        "Internal Affairs Director",
    )
    management_rank_names = (
        "Trial Managment",
        "Junior Managment",
        "Managment",
        "Senior Managment",
        "Director Of Managment",
    )
    ia_rank_ids = {STAFF_ROLE_IDS[name] for name in ia_rank_names}
    management_rank_ids = {STAFF_ROLE_IDS[name] for name in management_rank_names}
    old_is_ia = old_rank.id in ia_rank_ids
    new_is_ia = new_rank.id in ia_rank_ids
    old_is_management = old_rank.id in management_rank_ids
    new_is_management = new_rank.id in management_rank_ids

    role_ids_to_remove = {old_rank.id}
    role_ids_to_add = {new_rank.id}
    if old_is_ia and not new_is_ia:
        role_ids_to_remove.update(
            {STAFF_ROLE_IDS["Internal Affairs Team"], STAFF_ROLE_IDS["HR"]}
        )
    if new_is_ia and not old_is_ia:
        role_ids_to_add.update(
            {STAFF_ROLE_IDS["Internal Affairs Team"], STAFF_ROLE_IDS["HR"]}
        )
    if old_is_management and not new_is_management:
        role_ids_to_remove.add(STAFF_ROLE_IDS["SHR"])
    if new_is_management and not old_is_management:
        role_ids_to_add.add(STAFF_ROLE_IDS["SHR"])
        role_ids_to_remove.add(STAFF_ROLE_IDS["HR"])
    if old_is_management and not new_is_management and new_is_ia:
        role_ids_to_add.add(STAFF_ROLE_IDS["HR"])

    guild = member.guild
    missing_role_ids = [
        role_id
        for role_id in role_ids_to_add | role_ids_to_remove
        if guild.get_role(role_id) is None
    ]
    if missing_role_ids:
        return "I could not find all staff roles required for this demotion."
    current_role_ids = {role.id for role in member.roles}
    roles_to_add = [
        guild.get_role(role_id)
        for role_id in role_ids_to_add - current_role_ids
    ]
    roles_to_remove = [
        guild.get_role(role_id)
        for role_id in role_ids_to_remove & current_role_ids
    ]
    return (
        [role for role in roles_to_add if role is not None],
        [role for role in roles_to_remove if role is not None],
    )


def has_staff_role(member: discord.Member) -> bool:
    """Return whether a member holds any configured staff role."""
    return any(role.id in STAFF_ROLE_ID_SET for role in member.roles)


async def staff_only(interaction: discord.Interaction) -> bool:
    return isinstance(interaction.user, discord.Member) and has_staff_role(interaction.user)


async def respond_privately(interaction: discord.Interaction, message: str) -> None:
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


async def restore_roles_after_failed_punishment(
    member: discord.Member,
    original_roles: list[discord.Role],
    case_id: int,
) -> bool:
    try:
        await member.edit(
            roles=original_roles,
            reason=f"Rolling back failed punishment case #{case_id}",
        )
    except DISCORD_REQUEST_ERRORS as error:
        print(f"Could not roll back roles for failed case #{case_id}: {error}")
        return False
    return True


def create_action(
    case_id: int,
    action_type: str,
    actor_id: int,
    target_id: int,
    created_at: str,
    ticket_number: str | None = None,
    reason: str | None = None,
    result: str | None = None,
) -> int:
    initialize_database()
    with database_connection() as connection:
        cursor = connection.execute(
            "INSERT INTO case_actions "
            "(case_id, action_type, actor_id, target_id, ticket_number, reason, "
            "result, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (case_id, action_type, actor_id, target_id, ticket_number, reason, result, created_at),
        )
        if cursor.lastrowid is None:
            raise RuntimeError("Could not create the case action.")
        action_id = cursor.lastrowid
    return action_id


def get_pending_actions() -> list[sqlite3.Row]:
    initialize_database()
    with database_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM case_actions WHERE status = 'pending'"
        ).fetchall()
    return rows


async def fetch_case_message(
    guild: discord.Guild,
    case: sqlite3.Row,
) -> discord.Message | None:
    if case["message_id"] is None:
        return None
    channel = guild.get_channel(PUNISHMENT_CHANNEL_ID)
    if not isinstance(channel, discord.TextChannel):
        try:
            channel = await guild.fetch_channel(PUNISHMENT_CHANNEL_ID)
        except DISCORD_REQUEST_ERRORS as error:
            print(f"Could not fetch punishment channel for case #{case['case_id']}: {error}")
            return None
    if not isinstance(channel, discord.TextChannel):
        return None
    try:
        return await channel.fetch_message(case["message_id"])
    except DISCORD_REQUEST_ERRORS as error:
        print(f"Could not fetch message for case #{case['case_id']}: {error}")
        return None


async def set_original_case_marker(
    guild: discord.Guild,
    case: sqlite3.Row,
    marker: str | None,
) -> bool:
    message = await fetch_case_message(guild, case)
    if message is None or not message.flags.components_v2:
        return False
    layout = discord.ui.LayoutView.from_message(message, timeout=None)
    if not isinstance(layout, discord.ui.LayoutView):
        return False
    punishment_text = case["punishment"] or "Unknown"
    if marker in {"Revoked", "Appealed"}:
        punishment_text = f"~~{punishment_text}~~ — {marker}"
    elif marker == "Completed":
        punishment_text = f"{punishment_text} — Completed"
    for item in get_layout_text_displays(layout):
        if "**Punishment:**" in item.content:
            lines = item.content.splitlines()
            for index, line in enumerate(lines):
                if line.startswith("**Punishment:**"):
                    lines[index] = f"**Punishment:** {punishment_text}"
                    item.content = "\n".join(lines)
                    try:
                        await message.edit(
                            content=None,
                            embeds=[],
                            attachments=message.attachments,
                            view=layout,
                        )
                    except DISCORD_REQUEST_ERRORS as error:
                        print(
                            f"Could not update punishment marker for case "
                            f"#{case['case_id']}: {error}"
                        )
                        return False
                    return True
    return False


async def rollback_case_action(
    interaction: discord.Interaction,
    action: sqlite3.Row,
    case: sqlite3.Row,
) -> str | None:
    guild = interaction.guild
    if guild is None:
        return "This action can only be cancelled in the original server."

    if action["action_type"] == "revoke":
        target = guild.get_member(action["target_id"])
        if target is None:
            try:
                target = await guild.fetch_member(action["target_id"])
            except discord.HTTPException:
                return "I could not find the affected member to restore the punishment."
        role_punishment = case["punishment"] in {
            "Termination",
            "Under Investigation",
            "Suspension",
            "Demotion",
        }
        if role_punishment:
            bot_member = guild.me
            if bot_member is None or not bot_member.guild_permissions.manage_roles:
                return "I need Manage Roles permission to restore the punishment."
            if target.id == guild.owner_id or target.top_role >= bot_member.top_role:
                return "The bot's role hierarchy prevents restoring this punishment."
            if case["punishment"] == "Demotion":
                try:
                    removed_ids = {int(value) for value in json.loads(case["removed_role_ids"] or "[]")}
                    added_ids = {int(value) for value in json.loads(case["demotion_added_role_ids"] or "[]")}
                except (json.JSONDecodeError, TypeError, ValueError):
                    return "The demotion role history is invalid; cancellation was not applied."
                roles_to_keep = [role for role in target.roles if role.id not in removed_ids]
                for role_id in added_ids:
                    role = guild.get_role(role_id)
                    if role is None:
                        return "A demotion role is missing; cancellation was not applied."
                    if role not in roles_to_keep:
                        roles_to_keep.append(role)
            else:
                roles_to_keep = [
                    role for role in target.roles if role.id not in STAFF_ROLE_ID_SET
                ]
                special_role_id = (
                    UNDER_INVESTIGATION_ROLE_ID
                    if case["punishment"] == "Under Investigation"
                    else SUSPENDED_STAFF_ROLE_ID
                    if case["punishment"] == "Suspension"
                    else None
                )
                if special_role_id is not None:
                    special_role = guild.get_role(special_role_id)
                    if special_role is None:
                        return "The punishment role is missing; cancellation was not applied."
                    roles_to_keep = [
                        role for role in roles_to_keep if role.id != special_role_id
                    ]
                    roles_to_keep.append(special_role)
            try:
                await target.edit(
                    roles=roles_to_keep,
                    reason=f"Cancelled revocation for case #{case['case_id']}",
                )
            except discord.HTTPException as error:
                print(f"Could not restore revoked case #{case['case_id']}: {error}")
                return "Discord could not restore the original punishment roles."

    with database_connection() as connection:
        connection.execute(
            "UPDATE punishment_cases SET status = 'active' WHERE case_id = ?",
            (case["case_id"],),
        )
        connection.execute(
            "UPDATE case_actions SET status = 'cancelled' WHERE action_id = ?",
            (action["action_id"],),
        )
    await set_original_case_marker(guild, case, None)
    return None


class CaseActionView(discord.ui.View):
    def __init__(self, action_id: int, action_type: str, target_id: int) -> None:
        super().__init__(timeout=None)
        self.action_id = action_id
        self.target_id = target_id
        label = "Cancel Appeal" if action_type == "appeal" else "Cancel Revocation"
        button = discord.ui.Button(
            label=label,
            style=discord.ButtonStyle.danger,
            custom_id=f"case-action-cancel:{action_id}",
        )
        button.callback = self.cancel_action
        self.add_item(button)

    async def cancel_action(self, interaction: discord.Interaction) -> None:
        if interaction.user.id == self.target_id:
            await respond_privately(interaction, "You cannot cancel an action made about you.")
            return
        if not isinstance(interaction.user, discord.Member) or not has_staff_role(interaction.user):
            await respond_privately(interaction, "Only configured staff can cancel this action.")
            return

        await interaction.response.defer(ephemeral=True)
        initialize_database()
        with database_connection() as connection:
            action = connection.execute(
                "SELECT * FROM case_actions WHERE action_id = ? AND status = 'pending'",
                (self.action_id,),
            ).fetchone()
        if action is None:
            await respond_privately(interaction, "This action has already been cancelled.")
            return
        case = get_case(action["case_id"])
        if case is None:
            await respond_privately(interaction, "The related case record could not be found.")
            return

        error_message = await rollback_case_action(interaction, action, case)
        if error_message:
            await respond_privately(interaction, error_message)
            return
        guild = interaction.guild
        role_sync_warning = ""
        if guild is not None:
            target = guild.get_member(action["target_id"])
            if target is None:
                try:
                    target = await guild.fetch_member(action["target_id"])
                except discord.NotFound:
                    target = None
                except DISCORD_REQUEST_ERRORS as error:
                    role_sync_warning = f" Punishment-role sync failed: {error}"
            if target is not None:
                sync_error = await sync_punishment_roles(guild, target)
                if sync_error:
                    role_sync_warning = f" Punishment-role sync warning: {sync_error}"

        if interaction.message is not None:
            embeds = interaction.message.embeds
            if embeds:
                embed = discord.Embed.from_dict(embeds[0].to_dict())
                case_number = action["case_id"]
                action_label = "Appeal" if action["action_type"] == "appeal" else "Revocation"
                embed.title = f"Case #{case_number} {action_label} Cancelled"
                await interaction.message.edit(embed=embed, view=None)
            else:
                await interaction.message.edit(view=None)
        await respond_privately(
            interaction,
            f"Action for case #{case['case_id']} cancelled.{role_sync_warning}",
        )


class RevokeConfirmationView(discord.ui.View):
    def __init__(
        self,
        case_id: int,
        reason: str,
        result: str,
        requester_id: int,
        target_id: int,
    ) -> None:
        super().__init__(timeout=120)
        self.case_id = case_id
        self.reason = reason
        self.result = result
        self.requester_id = requester_id
        self.target_id = target_id
        confirm_button = discord.ui.Button(
            label="Confirm Revocation",
            style=discord.ButtonStyle.danger,
        )
        confirm_button.callback = self.confirm
        cancel_button = discord.ui.Button(
            label="Cancel",
            style=discord.ButtonStyle.secondary,
        )
        cancel_button.callback = self.cancel
        self.add_item(confirm_button)
        self.add_item(cancel_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.requester_id:
            await respond_privately(interaction, "Only the staff member who started this can confirm it.")
            return False
        return True

    async def confirm(self, interaction: discord.Interaction) -> None:
        await complete_revocation(
            interaction,
            self.case_id,
            self.reason,
            self.result,
            self.target_id,
        )
        if interaction.message is not None:
            await interaction.message.edit(
                content="Revocation confirmation submitted. See the private bot response.",
                view=None,
            )
        self.stop()

    async def cancel(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            content="Revocation cancelled. No case changes were made.",
            embed=None,
            view=None,
        )
        self.stop()


class InfractionAppealModal(discord.ui.Modal, title="Infraction Appeal"):
    case_number = discord.ui.TextInput(
        label="Infraction case number",
        placeholder="For example: 123",
        min_length=1,
        max_length=12,
    )
    reason = discord.ui.TextInput(
        label="Why do you have this infraction?",
        style=discord.TextStyle.paragraph,
        min_length=1,
        max_length=1000,
    )
    recurrence = discord.ui.TextInput(
        label="Will this happen again? Explain.",
        style=discord.TextStyle.paragraph,
        min_length=1,
        max_length=500,
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        member = interaction.user
        case_text = self.case_number.value.strip()
        if (
            guild is None
            or not isinstance(member, discord.Member)
            or not has_staff_role(member)
        ):
            await respond_privately(
                interaction,
                "Only current staff members can submit an infraction appeal.",
            )
            return
        if not case_text.isdigit() or int(case_text) < 1:
            await respond_privately(interaction, "Enter a valid positive case number.")
            return

        case_number = int(case_text)
        case = get_case(case_number)
        if (
            case is None
            or case["guild_id"] != guild.id
            or case["member_id"] != member.id
            or case["punishment"] not in {"Warning", "Infraction", "Strike"}
        ):
            await respond_privately(
                interaction,
                "That case was not found as an infraction or strike on your staff record.",
            )
            return
        if case["punishment"] == "Warning":
            await respond_privately(interaction, "Warnings are unappealable.")
            return
        if case["status"] != "active":
            await respond_privately(
                interaction,
                f"Case #{case_number} is not active and cannot be appealed.",
            )
            return
        if not case["appealable"] or case["appealable_by"] == "no":
            await respond_privately(
                interaction,
                "This case is non-appealable; please talk to Ownership.",
            )
            return

        ia_role = guild.get_role(STAFF_ROLE_IDS["Internal Affairs Team"])
        bot_member = guild.me
        if ia_role is None or bot_member is None:
            await respond_privately(
                interaction,
                "The Internal Affairs role or bot member could not be found.",
            )
            return
        if not bot_member.guild_permissions.manage_channels:
            await respond_privately(
                interaction,
                "I need Manage Channels permission to create an appeal ticket.",
            )
            return

        await interaction.response.defer(ephemeral=True)
        source_channel = interaction.channel
        category = (
            source_channel.category
            if isinstance(source_channel, discord.TextChannel)
            else None
        )
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True,
            ),
            ia_role: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_messages=True,
            ),
            bot_member: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_channels=True,
                manage_messages=True,
            ),
        }
        channel_name = f"appeal-{case_number}-{member.name.casefold()}"
        channel_name = "".join(
            character if character.isalnum() or character == "-" else "-"
            for character in channel_name
        ).strip("-")[:90]
        try:
            ticket_channel = await guild.create_text_channel(
                channel_name or f"appeal-{case_number}",
                category=category,
                overwrites=overwrites,
                topic=f"Private Internal Affairs appeal for case #{case_number}",
                reason=f"Staff infraction appeal submitted by {member} for case #{case_number}",
            )
        except discord.HTTPException as error:
            print(f"Could not create appeal ticket for case #{case_number}: {error}")
            await respond_privately(
                interaction,
                "I could not create the appeal ticket. Check the bot's channel permissions.",
            )
            return

        appeal_embed = discord.Embed(
            title=f"Staff Infraction Appeal — Case #{case_number}",
            description=f"**Appellant:** {member.mention}\n**Case:** #{case_number}",
            color=discord.Color.orange(),
            timestamp=datetime.now(EASTERN_TIME) if EASTERN_TIME else datetime.now().astimezone(),
        )
        appeal_embed.add_field(
            name="Why do they have this infraction?",
            value=discord.utils.escape_markdown(self.reason.value.strip())[:1024],
            inline=False,
        )
        appeal_embed.add_field(
            name="Will this happen again?",
            value=discord.utils.escape_markdown(self.recurrence.value.strip())[:1024],
            inline=False,
        )
        appeal_embed.set_footer(text="Internal Affairs: review this appeal in the ticket.")
        try:
            await ticket_channel.send(
                content=f"{ia_role.mention} {member.mention}",
                embed=appeal_embed,
                allowed_mentions=discord.AllowedMentions(
                    users=[member],
                    roles=[ia_role],
                ),
            )
        except discord.HTTPException as error:
            print(
                f"Appeal ticket channel {ticket_channel.id} was created but its "
                f"initial message failed: {error}"
            )
            await respond_privately(
                interaction,
                f"Ticket channel {ticket_channel.mention} was created, but I could not post its appeal details.",
            )
            return

        await respond_privately(
            interaction,
            f"Your Internal Affairs appeal ticket is ready: {ticket_channel.mention}",
        )


class StaffInformationView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)
        self.add_item(
            discord.ui.Button(
                label="Melony Join Link",
                style=discord.ButtonStyle.link,
                url="https://melon.ly/join/YGQOEW",
            )
        )
        self.add_item(
            discord.ui.Button(
                label="LOA Request",
                style=discord.ButtonStyle.link,
                url="https://melonly.xyz/my/loa/7470038197880229888",
            )
        )

    @discord.ui.button(
        label="Infraction Appeal",
        style=discord.ButtonStyle.primary,
        custom_id="staff-information:infraction-appeal",
    )
    async def infraction_appeal(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button,
    ) -> None:
        if _button.disabled:
            await respond_privately(interaction, "The infraction appeal button is unavailable.")
            return
        if not isinstance(interaction.user, discord.Member) or not has_staff_role(interaction.user):
            await respond_privately(
                interaction,
                "Only current staff members can submit an infraction appeal.",
            )
            return
        await interaction.response.send_modal(InfractionAppealModal())


def build_staff_information_embed() -> discord.Embed:
    return discord.Embed(
        title="Staff Information Center",
        description=(
            "Welcome to the Staff Information Center! This embed contains important "
            "information regarding staff responsibilities, expectations, and regulations. "
            "All staff members are expected to read, understand, and follow these "
            "guidelines at all times.\n\n"
            "### 📋 Staff Responsibilities\n"
            "- Enforce server rules fairly and professionally.\n"
            "- Assist players with questions, concerns, and reports.\n"
            "- Monitor in-game sessions and Discord channels.\n"
            "- Respond to staff requests and moderation situations.\n"
            "- Maintain a professional attitude while on duty.\n\n"
            "### ⚖️ Staff Expectations\n"
            "- Treat every member with respect.\n"
            "- Remain unbiased when handling punishments.\n"
            "- Never abuse staff permissions or commands.\n"
            "- Do not engage in arguments with community members.\n"
            "- Keep internal staff discussions confidential.\n"
            "- Follow the chain of command when escalating issues.\n\n"
            "### 🚨 Staff Regulations\n"
            "- **No Staff Abuse:** Permissions must only be used for legitimate staff duties.\n"
            "- **No Favoritism:** Friends and high-ranking members must follow the same rules.\n"
            "- **Proper Evidence:** Collect evidence when handling serious rule violations.\n"
            "- **Activity:** Remain active and communicate absences when necessary.\n"
            "- **Professionalism:** Represent the server positively in Discord and ERLC.\n\n"
            "### 📈 Promotions & Consequences\n"
            "Staff members may earn promotions through consistent activity, leadership, "
            "maturity, and quality moderation. Rule violations may result in a warning, "
            "strike, demotion, suspension, or termination, depending on severity.\n\n"
            "### 🛡️ Chain of Command\n"
            "Direct questions and concerns to your immediate supervisor. If the issue "
            "cannot be resolved, escalate it to the next appropriate rank. Do not bypass "
            "leadership without a valid reason."
        ),
        color=discord.Color.from_rgb(54, 57, 63),
    )


def get_case_action(case_id: int) -> sqlite3.Row | None:
    initialize_database()
    with database_connection() as connection:
        action = connection.execute(
            "SELECT * FROM case_actions WHERE case_id = ? AND status != 'failed' "
            "ORDER BY action_id DESC LIMIT 1",
            (case_id,),
        ).fetchone()
    return action


def extract_case_post_details(message: discord.Message | None) -> tuple[str, str]:
    if message is None or not message.flags.components_v2:
        return "Unavailable", "Unavailable"

    try:
        layout = discord.ui.LayoutView.from_message(message, timeout=None)
        text = "\n".join(
            display.content
            for display in get_layout_text_displays(layout)
            if isinstance(display.content, str)
        )
    except (TypeError, ValueError) as error:
        print(f"Could not read original discipline post {message.id}: {error}")
        return "Unavailable", "Unavailable"

    proof_match = re.search(r"^\*\*Proof:\*\*\s*(.*)$", text, re.MULTILINE)
    signed_match = re.search(r"^\*\*Signed:\*\*\s*(.+)$", text, re.MULTILINE)
    return (
        proof_match.group(1).strip() if proof_match else "Unavailable",
        signed_match.group(1).strip() if signed_match else "Unavailable",
    )


def format_case_created_at(value: str | None) -> str:
    if not value:
        return "Unknown"
    try:
        created_at = datetime.fromisoformat(value)
    except ValueError:
        return discord.utils.escape_markdown(value)
    if created_at.tzinfo is None:
        created_at = created_at.replace(
            tzinfo=EASTERN_TIME or datetime.now().astimezone().tzinfo
        )
    return f"<t:{int(created_at.timestamp())}:D>"


def truncate_case_detail(value: str, max_length: int = 950) -> str:
    cleaned = value.strip() or "Not recorded"
    if len(cleaned) > max_length:
        return cleaned[: max_length - 3] + "..."
    return cleaned


async def build_member_cases_embed(
    guild: discord.Guild,
    member: discord.Member,
    cases: list[sqlite3.Row],
    page: int,
    active_only: bool,
    own_record: bool = False,
) -> discord.Embed:
    visible_cases = [
        case for case in cases
        if not active_only or case["status"] == "active"
    ]
    page_count = max(1, (len(visible_cases) + 3) // 4)
    page = min(max(page, 0), page_count - 1)
    start = page * 4
    page_cases = visible_cases[start : start + 4]
    active_count = sum(case["status"] == "active" for case in cases)
    embed = discord.Embed(
        title=(
            "Your staff record"
            if own_record and not cases
            else f"{member.display_name}'s Staff Cases"
        ),
        description=(
            f"{member.mention} · 🟢 {active_count} active · "
            f"🔴 {len(cases) - active_count} inactive · {len(cases)} total"
        ),
        color=discord.Color.from_rgb(54, 57, 63),
    )
    if member.display_avatar:
        embed.set_thumbnail(url=member.display_avatar.url)

    if not page_cases:
        if active_only and cases:
            embed.add_field(
                name="No active cases",
                value="There are no active punishment cases to show.",
                inline=False,
            )
        else:
            embed.add_field(name="✨ Clean record", value="No cases on file. Keep it up.", inline=False)

    for case in page_cases:
        is_active = case["status"] == "active"
        status_dot = "🟢" if is_active else "🔴"
        punishment = discord.utils.escape_markdown(case["punishment"] or "Unknown")
        heading = f"{status_dot} Case #{case['case_id']} — {punishment}"
        case_status = "Active" if is_active else (case["status"] or "Inactive").replace("_", " ").title()
        lines = [
            f"**Status:** {case_status}",
            f"**Issued:** {format_case_created_at(case['created_at'])}",
            f"**Reason:** {discord.utils.escape_markdown(case['reason'] or 'Not recorded')}",
            f"**Appealable:** {'Yes' if case['appealable'] else 'No'}"
            + (
                f" · **Review rank:** {discord.utils.escape_markdown(case['appealable_by'])}"
                if case["appealable_by"] and case["appealable_by"] != "no"
                else ""
            ),
        ]

        message = await fetch_case_message(guild, case)
        proof, signed = extract_case_post_details(message)
        lines.extend(
            [
                f"**Proof:** {discord.utils.escape_markdown(proof)}",
                f"**Signed:** {signed}",
            ]
        )
        if case["punishment"] == "Suspension" and case["suspension_until"]:
            try:
                suspension_end = datetime.fromisoformat(case["suspension_until"])
                lines.append(f"**Suspension ends:** <t:{int(suspension_end.timestamp())}:F>")
            except ValueError:
                lines.append(
                    f"**Suspension ends:** {discord.utils.escape_markdown(case['suspension_until'])}"
                )
        if case["punishment"] == "Demotion":
            old_rank = guild.get_role(case["demotion_old_rank_id"])
            new_rank = guild.get_role(case["demotion_new_rank_id"])
            lines.append(f"**Old Rank:** {old_rank.mention if old_rank else 'Unavailable'}")
            lines.append(f"**New Rank:** {new_rank.mention if new_rank else 'Unavailable'}")

        action = get_case_action(case["case_id"])
        if action is not None:
            action_name = action["action_type"].title()
            lines.append(f"**{action_name} by:** <@{action['actor_id']}>")
            if action["ticket_number"]:
                lines.append(
                    f"**{action_name} ticket:** "
                    f"#{discord.utils.escape_markdown(action['ticket_number'])}"
                )
            if action["reason"]:
                lines.append(
                    f"**{action_name} reason:** "
                    f"{discord.utils.escape_markdown(action['reason'])}"
                )
            if action["result"]:
                lines.append(
                    f"**{action_name} result:** "
                    f"{discord.utils.escape_markdown(action['result'])}"
                )

        if not is_active:
            heading = f"🔴 ~~Case #{case['case_id']} — {punishment}~~"
            lines = [f"~~{line}~~" for line in lines]
        embed.add_field(
            name=truncate_case_detail(heading, 256),
            value=truncate_case_detail("\n".join(lines), 1024),
            inline=False,
        )

    shown = f"{min(start + 1, len(visible_cases))}-{min(start + len(page_cases), len(visible_cases))}"
    embed.set_footer(
        text=(
            f"Page {page + 1} of {page_count} · "
            f"{shown if page_cases else '0'} shown · "
            f"{'Active only' if active_only else 'All cases'}"
        )
    )
    return embed


class MemberCasesView(discord.ui.View):
    def __init__(
        self,
        guild: discord.Guild,
        member: discord.Member,
        cases: list[sqlite3.Row],
        requester_id: int,
    ) -> None:
        super().__init__(timeout=900)
        self.guild = guild
        self.member = member
        self.cases = cases
        self.requester_id = requester_id
        self.page = 0
        self.active_only = False
        self._update_buttons()

    def _visible_cases(self) -> list[sqlite3.Row]:
        return [
            case for case in self.cases
            if not self.active_only or case["status"] == "active"
        ]

    def _update_buttons(self) -> None:
        page_count = max(1, (len(self._visible_cases()) + 3) // 4)
        self.first_page.disabled = self.page == 0
        self.previous_page.disabled = self.page == 0
        self.next_page.disabled = self.page >= page_count - 1
        self.last_page.disabled = self.page >= page_count - 1
        self.toggle_active.label = "Show All" if self.active_only else "Active Only"

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.requester_id:
            await respond_privately(interaction, "Only the person who opened these cases can use these buttons.")
            return False
        return True

    async def _show_page(self, interaction: discord.Interaction) -> None:
        self._update_buttons()
        embed = await build_member_cases_embed(
            self.guild,
            self.member,
            self.cases,
            self.page,
            self.active_only,
        )
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="First", style=discord.ButtonStyle.secondary)
    async def first_page(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if button.disabled:
            await respond_privately(interaction, "That page control is currently unavailable.")
            return
        self.page = 0
        await self._show_page(interaction)

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary)
    async def previous_page(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if button.disabled:
            await respond_privately(interaction, "That page control is currently unavailable.")
            return
        self.page = max(0, self.page - 1)
        await self._show_page(interaction)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next_page(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if button.disabled:
            await respond_privately(interaction, "That page control is currently unavailable.")
            return
        page_count = max(1, (len(self._visible_cases()) + 3) // 4)
        self.page = min(page_count - 1, self.page + 1)
        await self._show_page(interaction)

    @discord.ui.button(label="Last", style=discord.ButtonStyle.secondary)
    async def last_page(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if button.disabled:
            await respond_privately(interaction, "That page control is currently unavailable.")
            return
        self.page = max(0, (len(self._visible_cases()) + 3) // 4 - 1)
        await self._show_page(interaction)

    @discord.ui.button(label="Active Only", style=discord.ButtonStyle.primary)
    async def toggle_active(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if button.disabled:
            await respond_privately(interaction, "That page control is currently unavailable.")
            return
        self.active_only = not self.active_only
        self.page = 0
        await self._show_page(interaction)

    @discord.ui.button(label="Dismiss", style=discord.ButtonStyle.danger)
    async def dismiss(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if button.disabled:
            await respond_privately(interaction, "This record is no longer available.")
            return
        await interaction.response.edit_message(
            content="Staff record dismissed.",
            embed=None,
            view=None,
        )
        self.stop()


def build_member_promotions_embed(
    guild: discord.Guild,
    member: discord.Member,
    cases: list[sqlite3.Row],
    page: int,
) -> discord.Embed:
    page_count = max(1, (len(cases) + 3) // 4)
    page = min(max(page, 0), page_count - 1)
    page_cases = cases[page * 4 : page * 4 + 4]
    active_count = sum(case["status"] == "published" for case in cases)
    embed = discord.Embed(
        title=f"{member.display_name}'s Promotion Cases",
        description=(
            f"{member.mention} · 🟢 {active_count} active · "
            f"🔴 {len(cases) - active_count} inactive · {len(cases)} total"
        ),
        color=discord.Color.from_rgb(54, 57, 63),
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    for case in page_cases:
        active = case["status"] == "published"
        new_rank = guild.get_role(case["new_rank_id"])
        new_rank_name = new_rank.mention if new_rank is not None else f"<@&{case['new_rank_id']}>"
        details = (
            f"**Status:** {'Active' if active else case['status'].replace('_', ' ').title()}\n"
            f"**Issued:** {format_case_created_at(case['created_at'])}\n"
            f"**Old Rank:** {discord.utils.escape_markdown(case['old_rank'])}\n"
            f"**New Rank:** {new_rank_name}\n"
            f"**Reason:** {discord.utils.escape_markdown(case['reason'])}\n"
            f"**Signed:** {discord.utils.escape_markdown(case['signed_name'])}"
        )
        if case["ticket_number"]:
            details += f"\n**Ticket:** #{discord.utils.escape_markdown(case['ticket_number'])}"
        case_type = "Reinstatement" if case["action_type"] == "reinstatement" else "Promotion"
        title = f"🟢 Case #{case['case_id']} — {case_type}" if active else (
            f"🔴 ~~Case #{case['case_id']} — {case_type}~~"
        )
        if not active:
            details = "\n".join(f"~~{line}~~" for line in details.splitlines())
        embed.add_field(
            name=truncate_case_detail(title, 256),
            value=truncate_case_detail(details, 1024),
            inline=False,
        )
    if not page_cases:
        embed.add_field(name="No promotion cases", value="No promotions are recorded.", inline=False)
    embed.set_footer(text=f"Page {page + 1} of {page_count} · {len(page_cases)} shown")
    return embed


class MemberPromotionsView(discord.ui.View):
    def __init__(
        self,
        guild: discord.Guild,
        member: discord.Member,
        cases: list[sqlite3.Row],
        requester_id: int,
    ) -> None:
        super().__init__(timeout=900)
        self.guild = guild
        self.member = member
        self.cases = cases
        self.requester_id = requester_id
        self.page = 0
        self._update_buttons()

    def _update_buttons(self) -> None:
        page_count = max(1, (len(self.cases) + 3) // 4)
        self.first_page.disabled = self.page == 0
        self.previous_page.disabled = self.page == 0
        self.next_page.disabled = self.page >= page_count - 1
        self.last_page.disabled = self.page >= page_count - 1

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.requester_id:
            await respond_privately(interaction, "Only the person who opened these promotions can use these buttons.")
            return False
        return True

    async def _show(self, interaction: discord.Interaction) -> None:
        self._update_buttons()
        await interaction.response.edit_message(
            embed=build_member_promotions_embed(
                self.guild, self.member, self.cases, self.page
            ),
            view=self,
        )

    @discord.ui.button(label="First", style=discord.ButtonStyle.secondary)
    async def first_page(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if button.disabled:
            await respond_privately(interaction, "That page control is currently unavailable.")
            return
        self.page = 0
        await self._show(interaction)

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary)
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if button.disabled:
            await respond_privately(interaction, "That page control is currently unavailable.")
            return
        self.page = max(0, self.page - 1)
        await self._show(interaction)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if button.disabled:
            await respond_privately(interaction, "That page control is currently unavailable.")
            return
        self.page = min(max(0, (len(self.cases) + 3) // 4 - 1), self.page + 1)
        await self._show(interaction)

    @discord.ui.button(label="Last", style=discord.ButtonStyle.secondary)
    async def last_page(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if button.disabled:
            await respond_privately(interaction, "That page control is currently unavailable.")
            return
        self.page = max(0, (len(self.cases) + 3) // 4 - 1)
        await self._show(interaction)

    @discord.ui.button(label="Dismiss", style=discord.ButtonStyle.danger)
    async def dismiss(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if button.disabled:
            await respond_privately(interaction, "This promotion record is no longer available.")
            return
        await interaction.response.edit_message(
            content="Promotion record dismissed.", embed=None, view=None
        )
        self.stop()


class WipeCasesConfirmationView(discord.ui.View):
    def __init__(self, member_id: int, requester_id: int) -> None:
        super().__init__(timeout=120)
        self.member_id = member_id
        self.requester_id = requester_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.requester_id:
            await respond_privately(interaction, "Only the staff member who started this wipe can confirm it.")
            return False
        return True

    @discord.ui.button(label="Confirm Case Wipe", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if button.disabled:
            await respond_privately(interaction, "This case wipe confirmation is no longer available.")
            return
        guild = interaction.guild
        actor = interaction.user
        if (
            guild is None
            or not isinstance(actor, discord.Member)
            or not any(role.id in BOD_REVIEWER_ROLE_IDS for role in actor.roles)
        ):
            await respond_privately(interaction, "Only Board of Directors and higher may confirm a case wipe.")
            return
        member = guild.get_member(self.member_id)
        if member is None:
            try:
                member = await guild.fetch_member(self.member_id)
            except DISCORD_REQUEST_ERRORS as error:
                await respond_privately(interaction, f"I could not load the member to sync their punishment roles: {error}")
                return

        with database_connection() as connection:
            promotion_ids = [
                row["case_id"]
                for row in connection.execute(
                    "SELECT case_id FROM promotion_cases WHERE member_id = ? AND guild_id = ?",
                    (member.id, guild.id),
                ).fetchall()
            ]
            case_ids = [
                row["case_id"]
                for row in connection.execute(
                    "SELECT case_id FROM punishment_cases WHERE member_id = ? AND guild_id = ?",
                    (member.id, guild.id),
                ).fetchall()
            ]
            if case_ids:
                connection.executemany(
                    "DELETE FROM case_actions WHERE case_id = ?",
                    [(case_id,) for case_id in case_ids],
                )
                connection.executemany(
                    "DELETE FROM punishment_cases WHERE case_id = ?",
                    [(case_id,) for case_id in case_ids],
                )
            if promotion_ids:
                connection.executemany(
                    "DELETE FROM ztp_cases WHERE source = 'promotion' AND source_case_id = ?",
                    [(case_id,) for case_id in promotion_ids],
                )
                connection.executemany(
                    "DELETE FROM promotion_cases WHERE case_id = ?",
                    [(case_id,) for case_id in promotion_ids],
                )

        role_error = await sync_punishment_roles(guild, member)
        result = (
            f"Deleted {len(case_ids)} punishment case(s) and {len(promotion_ids)} promotion case(s) "
            f"for {member.mention}."
        )
        if role_error:
            result += f" Case history was wiped, but punishment role cleanup failed: {role_error}"
        await interaction.response.edit_message(content=result, embed=None, view=None)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if button.disabled:
            await respond_privately(interaction, "This confirmation is no longer available.")
            return
        await interaction.response.edit_message(
            content="Case wipe cancelled. No records were changed.", embed=None, view=None
        )
        self.stop()


def get_guild_id() -> int | None:
    """Return the optional development guild ID, rejecting invalid values."""
    raw_guild_id = os.getenv("DISCORD_GUILD_ID")
    if raw_guild_id is None:
        return None

    raw_guild_id = raw_guild_id.strip()
    if not raw_guild_id:
        return None

    try:
        guild_id = int(raw_guild_id)
    except (TypeError, ValueError) as error:
        raise ValueError("DISCORD_GUILD_ID must be a numeric Discord server ID.") from error

    if guild_id <= 0:
        raise ValueError("DISCORD_GUILD_ID must be a positive Discord server ID.")

    return guild_id


class TestBot(commands.Bot):
    async def setup_hook(self) -> None:
        initialize_database()
        for action in get_pending_actions():
            action_type = action["action_type"]
            self.add_view(
                CaseActionView(
                    action["action_id"],
                    action_type,
                    action["target_id"],
                ),
                message_id=action["message_id"],
            )
        self.add_view(StaffInformationView())

        guild_id = get_guild_id()

        scopes: list[discord.Object | None] = [None]
        if guild_id is not None:
            scopes.append(discord.Object(id=guild_id))

        for guild in scopes:
            registered = await self.tree.fetch_commands(guild=guild)
            for command in registered:
                if command.name == "ping":
                    await command.delete()

        if guild_id is not None:
            guild = discord.Object(id=guild_id)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            print(f"Synced {len(synced)} command(s) to development server {guild_id}.")
            return

        synced = await self.tree.sync()
        print(f"Synced {len(synced)} global command(s).")


bot = TestBot(
    command_prefix=commands.when_mentioned,
    intents=discord.Intents.default(),
)


@bot.event
async def on_ready() -> None:
    if bot.user is not None:
        print(f"Bot is online as {bot.user} (ID: {bot.user.id}).")
    if not expire_staff_suspensions.is_running():
        expire_staff_suspensions.start()
    if not expire_strike_terminations.is_running():
        expire_strike_terminations.start()
    if not expire_ztp_records.is_running():
        expire_ztp_records.start()


async def terminate_for_ztp(
    guild: discord.Guild,
    member: discord.Member,
    issuer: discord.Member | discord.User,
    ztp_case: sqlite3.Row,
    triggering_case_id: int,
) -> str | None:
    ztp_id = ztp_case["ztp_id"]
    with database_connection() as connection:
        reserved = connection.execute(
            "UPDATE ztp_cases SET status = 'terminating' "
            "WHERE ztp_id = ? AND status = 'active'",
            (ztp_id,),
        )
        reservation_succeeded = reserved.rowcount == 1
    if not reservation_succeeded:
        return f"{format_ztp_id(ztp_id)} is no longer active."

    expires_at = datetime.fromisoformat(ztp_case["expires_at"])
    now = datetime.now(expires_at.tzinfo) if expires_at.tzinfo else datetime.now()
    if expires_at <= now:
        with database_connection() as connection:
            connection.execute(
                "UPDATE ztp_cases SET status = 'completed' "
                "WHERE ztp_id = ? AND status = 'terminating'",
                (ztp_id,),
            )
        return f"{format_ztp_id(ztp_id)} expired before the punishment was processed."

    triggering_case = get_case(triggering_case_id)
    if triggering_case is not None and triggering_case["punishment"] == "Termination":
        with database_connection() as connection:
            active_role_cases = connection.execute(
                "SELECT * FROM punishment_cases WHERE member_id = ? AND guild_id = ? "
                "AND status = 'active' AND punishment IN ('Suspension', 'Under Investigation')",
                (member.id, guild.id),
            ).fetchall()
        restore_role_ids = {
            role.id for role in member.roles if role.id in STAFF_ROLE_ID_SET
        }
        warnings: list[str] = []
        for active_case in active_role_cases:
            try:
                saved_role_ids = json.loads(active_case["removed_role_ids"] or "[]")
                restore_role_ids.update(
                    int(role_id)
                    for role_id in saved_role_ids
                    if int(role_id) in STAFF_ROLE_ID_SET
                )
            except (json.JSONDecodeError, TypeError, ValueError) as error:
                warnings.append(
                    f"active case #{active_case['case_id']} has invalid role history ({error})"
                )

        special_role_ids = {UNDER_INVESTIGATION_ROLE_ID, SUSPENDED_STAFF_ROLE_ID}
        special_roles = [
            role for role in member.roles if role.id in special_role_ids
        ]
        if special_roles:
            bot_member = guild.me
            if (
                bot_member is None
                or not bot_member.guild_permissions.manage_roles
                or any(role >= bot_member.top_role for role in special_roles)
            ):
                warnings.append("the bot could not remove a suspension/investigation role")
            else:
                try:
                    await member.edit(
                        roles=[role for role in member.roles if role.id not in special_role_ids],
                        reason=f"Completing ZTP termination {format_ztp_id(ztp_id)}",
                    )
                except DISCORD_REQUEST_ERRORS as error:
                    warnings.append(f"special-role removal failed ({error})")

        with database_connection() as connection:
            connection.execute(
                "UPDATE punishment_cases SET removed_role_ids = ? WHERE case_id = ?",
                (json.dumps(sorted(restore_role_ids)), triggering_case_id),
            )
            connection.execute(
                "UPDATE punishment_cases SET status = 'superseded' "
                "WHERE member_id = ? AND guild_id = ? AND status = 'active' "
                "AND punishment IN ('Suspension', 'Under Investigation')",
                (member.id, guild.id),
            )
            connection.execute(
                "UPDATE ztp_cases SET status = 'terminated', triggered_case_id = ? "
                "WHERE ztp_id = ? AND status = 'terminating'",
                (triggering_case_id, ztp_id),
            )
        for active_case in active_role_cases:
            await set_original_case_marker(guild, active_case, "Superseded by termination")
        log_error = await send_ztp_log(
            guild,
            discord.Embed(
                title=f"ZTP Triggered — {format_ztp_id(ztp_id)}",
                description=(
                    f"**Staff Member:** {member.mention}\n"
                    f"**Triggering Case:** #{triggering_case_id} — Termination\n"
                    f"**Reason:** {discord.utils.escape_markdown(ztp_case['reason'])}\n"
                    "**Outcome:** Staff roles were removed by the termination case."
                ),
                color=discord.Color.red(),
                timestamp=datetime.now(EASTERN_TIME) if EASTERN_TIME else datetime.now().astimezone(),
            ),
        )
        if log_error:
            warnings.append(log_error)
        return "; ".join(warnings) if warnings else None

    bot_member = guild.me
    if (
        bot_member is None
        or not bot_member.guild_permissions.manage_roles
        or member.id == guild.owner_id
        or member.top_role >= bot_member.top_role
    ):
        with database_connection() as connection:
            connection.execute(
                "UPDATE ztp_cases SET status = 'active' "
                "WHERE ztp_id = ? AND status = 'terminating'",
                (ztp_id,),
            )
        return "bot role permissions or hierarchy prevent role removal."

    log_channel = guild.get_channel(PUNISHMENT_CHANNEL_ID)
    if log_channel is None:
        try:
            log_channel = await guild.fetch_channel(PUNISHMENT_CHANNEL_ID)
        except DISCORD_REQUEST_ERRORS as error:
            with database_connection() as connection:
                connection.execute(
                    "UPDATE ztp_cases SET status = 'active' "
                    "WHERE ztp_id = ? AND status = 'terminating'",
                    (ztp_id,),
                )
            return f"punishment channel lookup failed: {error}"
    if not isinstance(log_channel, discord.TextChannel):
        with database_connection() as connection:
            connection.execute(
                "UPDATE ztp_cases SET status = 'active' "
                "WHERE ztp_id = ? AND status = 'terminating'",
                (ztp_id,),
            )
        return "the configured punishment channel is not a text channel."

    roles_to_remove = [role for role in member.roles if role.id in STAFF_ROLE_ID_SET]
    if any(role >= bot_member.top_role for role in roles_to_remove):
        with database_connection() as connection:
            connection.execute(
                "UPDATE ztp_cases SET status = 'active' "
                "WHERE ztp_id = ? AND status = 'terminating'",
                (ztp_id,),
            )
        return "the bot role is below a staff role that must be removed."

    with database_connection() as connection:
            active_role_cases = connection.execute(
                "SELECT * FROM punishment_cases WHERE member_id = ? AND guild_id = ? "
                "AND status = 'active' AND punishment IN ('Suspension', 'Under Investigation')",
                (member.id, guild.id),
            ).fetchall()
    staff_role_ids_to_restore = {role.id for role in roles_to_remove}
    for active_case in active_role_cases:
            try:
                saved_role_ids = json.loads(active_case["removed_role_ids"] or "[]")
                staff_role_ids_to_restore.update(
                    int(role_id)
                    for role_id in saved_role_ids
                    if int(role_id) in STAFF_ROLE_ID_SET
                )
            except (json.JSONDecodeError, TypeError, ValueError) as error:
                with database_connection() as connection:
                    connection.execute(
                        "UPDATE ztp_cases SET status = 'active' "
                        "WHERE ztp_id = ? AND status = 'terminating'",
                        (ztp_id,),
                    )
                return f"active case #{active_case['case_id']} has invalid saved role data: {error}"

    termination_case_id = create_case_id()
    triggering_punishment = (
        triggering_case["punishment"] if triggering_case is not None else "discipline"
    )
    termination_reason = (
        f"Automatic termination: received {triggering_punishment} "
        f"during ZTP {format_ztp_id(ztp_id)}."
    )
    created_at, _ = eastern_timestamp()
    with database_connection() as connection:
        connection.execute(
            "UPDATE punishment_cases SET member_id = ?, punishment = 'Termination', "
            "reason = ?, appealable = 0, appealable_by = 'no', status = 'pending', "
            "created_at = ?, removed_role_ids = ?, guild_id = ? WHERE case_id = ?",
            (
                member.id,
                termination_reason,
                created_at,
                json.dumps(sorted(staff_role_ids_to_restore)),
                guild.id,
                termination_case_id,
            ),
        )

    original_roles = list(member.roles)
    roles_to_remove_ids = STAFF_ROLE_ID_SET | {
        UNDER_INVESTIGATION_ROLE_ID,
        SUSPENDED_STAFF_ROLE_ID,
    }
    updated_roles = [
        role for role in original_roles if role.id not in roles_to_remove_ids
    ]
    try:
        await member.edit(
            roles=updated_roles,
            reason=f"Automatic ZTP termination {format_ztp_id(ztp_id)}",
        )
    except DISCORD_REQUEST_ERRORS as error:
        with database_connection() as connection:
            connection.execute(
                "UPDATE punishment_cases SET status = 'failed' WHERE case_id = ?",
                (termination_case_id,),
            )
            connection.execute(
                "UPDATE ztp_cases SET status = 'active' "
                "WHERE ztp_id = ? AND status = 'terminating'",
                (ztp_id,),
            )
        return f"Discord could not remove staff roles: {error}"

    try:
        message = await log_channel.send(
            view=build_punishment_view(
                member=member,
                punishment="Termination",
                reason=termination_reason,
                appealable="❌ No",
                appealable_by="❌",
                proof=f"Automatic ZTP termination · {format_ztp_id(ztp_id)}",
                issuer=issuer,
                case_id=termination_case_id,
            ),
            files=[discord.File(PUNISHMENT_BANNER_PATH, filename=PUNISHMENT_BANNER_FILENAME)],
            allowed_mentions=discord.AllowedMentions(users=[member]),
        )
    except DISCORD_REQUEST_ERRORS as error:
        rollback_succeeded = True
        try:
            await member.edit(
                roles=original_roles,
                reason=f"Rolling back unlogged ZTP termination case #{termination_case_id}",
            )
        except DISCORD_REQUEST_ERRORS as rollback_error:
            rollback_succeeded = False
            print(
                f"Could not roll back roles after failed ZTP termination "
                f"{format_ztp_id(ztp_id)}: {rollback_error}"
            )
        with database_connection() as connection:
            connection.execute(
                "UPDATE punishment_cases SET status = 'failed' WHERE case_id = ?",
                (termination_case_id,),
            )
            connection.execute(
                "UPDATE ztp_cases SET status = 'active' "
                "WHERE ztp_id = ? AND status = 'terminating'",
                (ztp_id,),
            )
        return (
            f"termination could not be logged: {error}"
            + ("" if rollback_succeeded else "; role rollback also failed")
        )

    with database_connection() as connection:
        connection.execute(
            "UPDATE punishment_cases SET status = 'active', message_id = ? "
            "WHERE case_id = ?",
            (message.id, termination_case_id),
        )
        connection.execute(
            "UPDATE punishment_cases SET termination_due_at = NULL "
            "WHERE member_id = ? AND guild_id = ? AND termination_due_at IS NOT NULL",
            (member.id, guild.id),
        )
        connection.execute(
            "UPDATE ztp_cases SET status = 'terminated', triggered_case_id = ? "
            "WHERE ztp_id = ? AND status = 'terminating'",
            (termination_case_id, ztp_id),
        )
        connection.execute(
            "UPDATE punishment_cases SET status = 'superseded' "
            "WHERE member_id = ? AND guild_id = ? AND status = 'active' "
            "AND punishment IN ('Suspension', 'Under Investigation')",
            (member.id, guild.id),
        )
    for active_case in active_role_cases:
        await set_original_case_marker(guild, active_case, "Superseded by ZTP termination")
    ztp_log_error = await send_ztp_log(
        guild,
        discord.Embed(
            title=f"ZTP Violation — {format_ztp_id(ztp_id)}",
            description=(
                f"**Staff Member:** {member.mention}\n"
                f"**ZTP Reason:** {discord.utils.escape_markdown(ztp_case['reason'])}\n"
                f"**Triggering Case:** #{triggering_case_id} — {triggering_punishment}\n"
                f"**Automatic Termination Case:** #{termination_case_id}\n"
                "**Outcome:** Staff roles were removed."
            ),
            color=discord.Color.red(),
            timestamp=datetime.now(EASTERN_TIME) if EASTERN_TIME else datetime.now().astimezone(),
        ),
    )
    try:
        await member.send(
            view=build_punishment_view(
                member=member,
                punishment="Termination",
                reason=termination_reason,
                appealable="❌ No",
                appealable_by="❌",
                proof=f"Automatic ZTP termination · {format_ztp_id(ztp_id)}",
                issuer=issuer,
                case_id=termination_case_id,
            ),
            files=[discord.File(PUNISHMENT_BANNER_PATH, filename=PUNISHMENT_BANNER_FILENAME)],
            allowed_mentions=discord.AllowedMentions(users=[member]),
        )
    except DISCORD_REQUEST_ERRORS as error:
        print(f"Could not DM automatic termination case #{termination_case_id}: {error}")
    if ztp_log_error:
        return (
            f"Automatic termination case #{termination_case_id} was applied, "
            f"but its ZTP log could not be sent: {ztp_log_error}"
        )
    return None


@tasks.loop(minutes=5)
async def expire_staff_suspensions() -> None:
    for case in get_active_suspensions():
        guild_id = case["guild_id"]
        guild = bot.get_guild(guild_id) if guild_id is not None else None
        if guild is None:
            print(f"Cannot expire suspension case #{case['case_id']}: guild is unavailable.")
            continue

        member = guild.get_member(case["member_id"])
        if member is None:
            try:
                member = await guild.fetch_member(case["member_id"])
            except discord.HTTPException as error:
                print(f"Cannot expire suspension case #{case['case_id']}: {error}")
                continue
        error_message = await restore_case_staff_roles(
            guild,
            member,
            case,
            {SUSPENDED_STAFF_ROLE_ID},
        )
        if error_message:
            print(f"Cannot expire suspension case #{case['case_id']}: {error_message}")
            continue

        with database_connection() as connection:
            updated = connection.execute(
                "UPDATE punishment_cases SET status = 'completed' "
                "WHERE case_id = ? AND status = 'active'",
                (case["case_id"],),
            )
        if updated.rowcount != 1:
            print(f"Suspension case #{case['case_id']} changed during expiry processing.")
            continue

        await set_original_case_marker(guild, case, "Completed")
        channel = guild.get_channel(PUNISHMENT_CHANNEL_ID)
        if not isinstance(channel, discord.TextChannel):
            continue
        original = await fetch_case_message(guild, case)
        if original is None:
            continue
        _, display_time = eastern_timestamp()
        embed = discord.Embed(
            title=f"Suspension Completed — Case #{case['case_id']}",
            description=f"{member.mention}'s staff suspension has ended and saved staff roles were restored.",
            color=discord.Color.green(),
            timestamp=datetime.now(EASTERN_TIME) if EASTERN_TIME else datetime.now().astimezone(),
        )
        embed.set_footer(text=display_time)
        try:
            await channel.send(
                embed=embed,
                reference=original,
                mention_author=False,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.HTTPException as error:
            print(f"Could not log suspension expiry for case #{case['case_id']}: {error}")


@tasks.loop(minutes=1)
async def expire_strike_terminations() -> None:
    initialize_database()
    now = datetime.now(EASTERN_TIME) if EASTERN_TIME else datetime.now().astimezone()
    with database_connection() as connection:
        cases = connection.execute(
            "SELECT * FROM punishment_cases WHERE punishment = 'Strike' "
            "AND status = 'active' AND termination_due_at IS NOT NULL"
        ).fetchall()

    terminated_member_ids: set[int] = set()
    for strike_case in cases:
        if strike_case["member_id"] in terminated_member_ids:
            continue
        due_at = datetime.fromisoformat(strike_case["termination_due_at"])
        if due_at > now:
            continue
        guild_id = strike_case["guild_id"]
        guild = bot.get_guild(guild_id) if guild_id is not None else None
        if guild is None:
            print(f"Cannot process strike termination for case #{strike_case['case_id']}: guild unavailable.")
            continue
        try:
            member = guild.get_member(strike_case["member_id"])
            if member is None:
                member = await guild.fetch_member(strike_case["member_id"])
        except DISCORD_REQUEST_ERRORS as error:
            print(f"Cannot load member for strike termination case #{strike_case['case_id']}: {error}")
            continue

        active_strikes = get_active_punishment_count(
            member.id, guild.id, "Strike"
        )
        if active_strikes < 3:
            with database_connection() as connection:
                connection.execute(
                    "UPDATE punishment_cases SET termination_due_at = NULL "
                    "WHERE member_id = ? AND guild_id = ? AND termination_due_at IS NOT NULL",
                    (member.id, guild.id),
                )
            role_error = await sync_punishment_roles(guild, member)
            if role_error:
                print(f"Could not update roles after strike appeal for member {member.id}: {role_error}")
            continue

        if not any(role.id in STAFF_ROLE_ID_SET for role in member.roles):
            with database_connection() as connection:
                connection.execute(
                    "UPDATE punishment_cases SET termination_due_at = NULL "
                    "WHERE member_id = ? AND guild_id = ? AND termination_due_at IS NOT NULL",
                    (member.id, guild.id),
                )
            continue

        bot_member = guild.me
        roles_to_remove = [
            role for role in member.roles
            if role.id in STAFF_ROLE_ID_SET | PUNISHMENT_ROLE_ID_SET
        ]
        if (
            bot_member is None
            or not bot_member.guild_permissions.manage_roles
            or member.id == guild.owner_id
            or member.top_role >= bot_member.top_role
            or any(role >= bot_member.top_role for role in roles_to_remove)
        ):
            print(
                f"Cannot apply strike termination for case #{strike_case['case_id']}: "
                "bot role permissions or hierarchy prevent role removal."
            )
            continue

        log_channel = guild.get_channel(PUNISHMENT_CHANNEL_ID)
        if not isinstance(log_channel, discord.TextChannel):
            try:
                log_channel = await guild.fetch_channel(PUNISHMENT_CHANNEL_ID)
            except DISCORD_REQUEST_ERRORS as error:
                print(f"Cannot access punishment channel for strike termination: {error}")
                continue
        if not isinstance(log_channel, discord.TextChannel):
            print("Configured punishment log channel is not a text channel; strike termination deferred.")
            continue

        termination_case_id = create_case_id()
        termination_reason = (
            f"Automatic termination: three active strikes remained after the 24-hour "
            f"appeal period following case #{strike_case['case_id']}."
        )
        created_at, _ = eastern_timestamp()
        original_roles = list(member.roles)
        saved_staff_role_ids = [
            role.id for role in roles_to_remove if role.id in STAFF_ROLE_ID_SET
        ]
        with database_connection() as connection:
            connection.execute(
                "UPDATE punishment_cases SET member_id = ?, punishment = 'Termination', "
                "reason = ?, appealable = 0, appealable_by = 'no', status = 'pending', "
                "created_at = ?, removed_role_ids = ?, guild_id = ? WHERE case_id = ?",
                (
                    member.id,
                    termination_reason,
                    created_at,
                    json.dumps(saved_staff_role_ids),
                    guild.id,
                    termination_case_id,
                ),
            )
        updated_roles = [
            role for role in original_roles
            if role.id not in STAFF_ROLE_ID_SET | PUNISHMENT_ROLE_ID_SET
        ]
        try:
            await member.edit(
                roles=updated_roles,
                reason=f"Automatic termination after three strikes, case #{termination_case_id}",
            )
        except DISCORD_REQUEST_ERRORS as error:
            with database_connection() as connection:
                connection.execute(
                    "UPDATE punishment_cases SET status = 'failed' WHERE case_id = ?",
                    (termination_case_id,),
                )
            print(f"Could not remove roles for automatic termination #{termination_case_id}: {error}")
            continue

        try:
            message = await log_channel.send(
                view=build_punishment_view(
                    member=member,
                    punishment="Termination",
                    reason=termination_reason,
                    appealable="❌ No",
                    appealable_by="❌",
                    proof=f"Automatic termination after the 24-hour strike appeal period · Case #{strike_case['case_id']}",
                    issuer=bot.user or member,
                    case_id=termination_case_id,
                ),
                files=[discord.File(PUNISHMENT_BANNER_PATH, filename=PUNISHMENT_BANNER_FILENAME)],
                allowed_mentions=discord.AllowedMentions(users=[member]),
            )
        except DISCORD_REQUEST_ERRORS as error:
            try:
                await member.edit(
                    roles=original_roles,
                    reason=f"Rolling back unlogged strike termination #{termination_case_id}",
                )
            except DISCORD_REQUEST_ERRORS as rollback_error:
                print(
                    f"Could not roll back roles after failed strike termination "
                    f"#{termination_case_id}: {rollback_error}"
                )
                with database_connection() as connection:
                    connection.execute(
                        "UPDATE punishment_cases SET status = 'needs_review' WHERE case_id = ?",
                        (termination_case_id,),
                    )
                continue
            with database_connection() as connection:
                connection.execute(
                    "UPDATE punishment_cases SET status = 'failed' WHERE case_id = ?",
                    (termination_case_id,),
                )
            print(f"Could not publish strike termination case #{termination_case_id}: {error}")
            continue

        with database_connection() as connection:
            connection.execute(
                "UPDATE punishment_cases SET status = 'active', message_id = ? WHERE case_id = ?",
                (message.id, termination_case_id),
            )
            connection.execute(
                "UPDATE punishment_cases SET termination_due_at = NULL "
                "WHERE member_id = ? AND guild_id = ? AND termination_due_at IS NOT NULL",
                (member.id, guild.id),
            )
        terminated_member_ids.add(member.id)
        try:
            await member.send(
                view=build_punishment_view(
                    member=member,
                    punishment="Termination",
                    reason=termination_reason,
                    appealable="❌ No",
                    appealable_by="❌",
                    proof=f"Automatic termination after the 24-hour strike appeal period · Case #{strike_case['case_id']}",
                    issuer=bot.user or member,
                    case_id=termination_case_id,
                ),
                files=[discord.File(PUNISHMENT_BANNER_PATH, filename=PUNISHMENT_BANNER_FILENAME)],
                allowed_mentions=discord.AllowedMentions(users=[member]),
            )
        except DISCORD_REQUEST_ERRORS as error:
            print(f"Could not DM automatic termination case #{termination_case_id}: {error}")


@tasks.loop(minutes=1)
async def expire_ztp_records() -> None:
    initialize_database()
    now = datetime.now(EASTERN_TIME) if EASTERN_TIME else datetime.now().astimezone()
    with database_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM ztp_cases WHERE status = 'active'"
        ).fetchall()
    for case in rows:
        if datetime.fromisoformat(case["expires_at"]) > now:
            continue
        with database_connection() as connection:
            updated = connection.execute(
                "UPDATE ztp_cases SET status = 'completed' "
                "WHERE ztp_id = ? AND status = 'active'",
                (case["ztp_id"],),
            )
        if updated.rowcount != 1:
            continue

        guild = bot.get_guild(case["guild_id"])
        if guild is None:
            print(
                f"ZTP {format_ztp_id(case['ztp_id'])} expired, but guild "
                f"{case['guild_id']} is unavailable for logging."
            )
            continue
        embed = discord.Embed(
            title=f"ZTP Expired — {format_ztp_id(case['ztp_id'])}",
            description=(
                f"**Staff Member:** <@{case['member_id']}>\n"
                f"**Reason:** {discord.utils.escape_markdown(case['reason'])}\n"
                f"**Original Duration:** {case['duration_days']} day(s)\n"
                "**Status:** Completed automatically at the scheduled end time."
            ),
            color=discord.Color.green(),
            timestamp=now,
        )
        log_error = await send_ztp_log(guild, embed)
        if log_error:
            print(f"Could not log ZTP expiry {format_ztp_id(case['ztp_id'])}: {log_error}")


@bot.tree.command(
    name="staff-information",
    description="Post the staff responsibilities, expectations, and regulations embed.",
)
@app_commands.guild_only()
@app_commands.check(staff_only)
async def staff_information(interaction: discord.Interaction) -> None:
    if interaction.guild is None:
        await respond_privately(interaction, "This command can only be used in a server.")
        return
    await interaction.response.send_message(
        embed=build_staff_information_embed(),
        view=StaffInformationView(),
        allowed_mentions=discord.AllowedMentions.none(),
    )


@bot.tree.command(
    name="view-all-cases",
    description="View a staff member's punishment history, four cases per page.",
)
@app_commands.guild_only()
@app_commands.check(staff_only)
@app_commands.describe(member="Staff member whose punishment history to view")
async def view_all_cases(
    interaction: discord.Interaction,
    member: discord.Member,
) -> None:
    guild = interaction.guild
    if guild is None:
        await respond_privately(interaction, "This command can only be used in a server.")
        return

    cases = get_member_punishment_cases(member.id, guild.id)
    view = MemberCasesView(guild, member, cases, interaction.user.id)
    embed = await build_member_cases_embed(
        guild,
        member,
        cases,
        page=0,
        active_only=False,
    )
    await interaction.response.send_message(
        embed=embed,
        view=view,
        ephemeral=True,
        allowed_mentions=discord.AllowedMentions.none(),
    )


@bot.tree.command(
    name="view-case",
    description="View one punishment case by its case number.",
)
@app_commands.guild_only()
@app_commands.check(staff_only)
@app_commands.describe(case_number="The case number to view")
async def view_case(
    interaction: discord.Interaction,
    case_number: int,
) -> None:
    guild = interaction.guild
    case = get_case(case_number) if case_number > 0 else None
    if guild is None or case is None or case["guild_id"] != guild.id or case["member_id"] is None:
        await respond_privately(interaction, "That case number was not found in this server.")
        return
    member = guild.get_member(case["member_id"])
    if member is None:
        try:
            member = await bot.fetch_user(case["member_id"])
        except DISCORD_REQUEST_ERRORS as error:
            print(f"Could not load member for case #{case_number}: {error}")
            await respond_privately(interaction, "I could not load the member attached to that case.")
            return
    embed = await build_member_cases_embed(guild, member, [case], 0, False)
    embed.set_footer(text=f"Case #{case_number}")
    await interaction.response.send_message(
        embed=embed,
        ephemeral=True,
        allowed_mentions=discord.AllowedMentions.none(),
    )


@bot.tree.command(
    name="my-cases",
    description="Privately view your own staff punishment record.",
)
@app_commands.guild_only()
async def my_cases(interaction: discord.Interaction) -> None:
    guild = interaction.guild
    if guild is None or not isinstance(interaction.user, discord.Member):
        await respond_privately(interaction, "This command can only be used in a server.")
        return
    cases = get_member_punishment_cases(interaction.user.id, guild.id)
    view = MemberCasesView(guild, interaction.user, cases, interaction.user.id)
    embed = await build_member_cases_embed(
        guild,
        interaction.user,
        cases,
        page=0,
        active_only=False,
        own_record=True,
    )
    await interaction.response.send_message(
        embed=embed,
        view=view,
        ephemeral=True,
        allowed_mentions=discord.AllowedMentions.none(),
    )


cases_group = app_commands.Group(
    name="cases",
    description="Manage and review staff case records.",
)


@cases_group.command(name="delete", description="Delete a punishment case by case number.")
@app_commands.guild_only()
@app_commands.describe(case_number="The punishment case to delete")
async def cases_delete(interaction: discord.Interaction, case_number: int) -> None:
    guild = interaction.guild
    actor = interaction.user
    if (
        guild is None
        or not isinstance(actor, discord.Member)
        or not any(role.id in BOD_REVIEWER_ROLE_IDS for role in actor.roles)
    ):
        await respond_privately(interaction, "Only Board of Directors and higher may delete case records.")
        return
    case = get_case(case_number) if case_number > 0 else None
    if case is None or case["guild_id"] != guild.id or case["member_id"] is None:
        await respond_privately(interaction, "That case number was not found in this server.")
        return
    member = guild.get_member(case["member_id"])
    if member is None:
        try:
            member = await guild.fetch_member(case["member_id"])
        except DISCORD_REQUEST_ERRORS as error:
            await respond_privately(
                interaction,
                f"Could not load the member to sync punishment roles; no case was deleted: {error}",
            )
            return

    with database_connection() as connection:
        connection.execute("DELETE FROM case_actions WHERE case_id = ?", (case_number,))
        deleted = connection.execute(
            "DELETE FROM punishment_cases WHERE case_id = ? AND guild_id = ?",
            (case_number, guild.id),
        )
    if deleted.rowcount != 1:
        await respond_privately(interaction, "The case changed before it could be deleted.")
        return
    role_error = await sync_punishment_roles(guild, member)
    await respond_privately(
        interaction,
        f"Deleted case #{case_number} from the database."
        + (f" Punishment role sync warning: {role_error}" if role_error else ""),
    )


@cases_group.command(name="edit", description="Edit a punishment case's saved details.")
@app_commands.guild_only()
@app_commands.choices(
    punishment=[
        app_commands.Choice(name="Warning", value="Warning"),
        app_commands.Choice(name="Infraction", value="Infraction"),
        app_commands.Choice(name="Strike", value="Strike"),
        app_commands.Choice(name="Retirement", value="Retirement"),
        app_commands.Choice(name="Demotion", value="Demotion"),
        app_commands.Choice(name="Termination", value="Termination"),
        app_commands.Choice(name="Suspension", value="Suspension"),
        app_commands.Choice(name="Under Investigation", value="Under Investigation"),
    ],
    appealable=[
        app_commands.Choice(name="Appealable", value="yes"),
        app_commands.Choice(name="Unappealable", value="no"),
    ],
    appealable_by=[
        app_commands.Choice(name="IA+", value="IA+"),
        app_commands.Choice(name="MGMT+", value="MGMT+"),
        app_commands.Choice(name="BoD+", value="BoD+"),
        app_commands.Choice(name="Ownership", value="ownership"),
    ],
)
@app_commands.describe(
    case_number="The case to edit",
    punishment="Replacement punishment type",
    reason="Replacement reason",
    appealable="Whether the case may be appealed",
    appealable_by="Minimum rank allowed to appeal",
)
async def cases_edit(
    interaction: discord.Interaction,
    case_number: int,
    punishment: app_commands.Choice[str] | None = None,
    reason: str | None = None,
    appealable: app_commands.Choice[str] | None = None,
    appealable_by: app_commands.Choice[str] | None = None,
) -> None:
    guild = interaction.guild
    actor = interaction.user
    if (
        guild is None
        or not isinstance(actor, discord.Member)
        or not any(role.id in BOD_REVIEWER_ROLE_IDS for role in actor.roles)
    ):
        await respond_privately(interaction, "Only Board of Directors and higher may edit case records.")
        return
    if reason is not None and (not reason.strip() or len(reason) > 1024):
        await respond_privately(interaction, "The replacement reason must be 1-1,024 characters.")
        return
    if all(value is None for value in (punishment, reason, appealable, appealable_by)):
        await respond_privately(interaction, "Provide at least one case field to edit.")
        return
    case = get_case(case_number) if case_number > 0 else None
    if case is None or case["guild_id"] != guild.id:
        await respond_privately(interaction, "That case number was not found in this server.")
        return
    new_punishment = punishment.value if punishment else case["punishment"]
    new_appealable = case["appealable"]
    if appealable is not None:
        new_appealable = int(appealable.value == "yes")
    if new_punishment == "Warning":
        new_appealable = 0
    new_appealable_by = (
        appealable_by.value if appealable_by is not None else case["appealable_by"]
    )
    if not new_appealable:
        new_appealable_by = "no"
    elif new_appealable_by == "no":
        await respond_privately(
            interaction,
            "An appealable case needs an appeal rank; choose IA+, MGMT+, BoD+, or Ownership.",
        )
        return
    if new_appealable_by == "ownership":
        new_appealable_by = "X"

    member = guild.get_member(case["member_id"]) if case["member_id"] is not None else None
    if member is None and case["member_id"] is not None:
        try:
            member = await guild.fetch_member(case["member_id"])
        except DISCORD_REQUEST_ERRORS as error:
            await respond_privately(interaction, f"Could not load the member for role synchronization: {error}")
            return
    old_values = (
        case["punishment"],
        case["reason"],
        case["appealable"],
        case["appealable_by"],
        case["termination_due_at"],
    )
    new_termination_due_at = case["termination_due_at"]
    if new_punishment != "Strike":
        new_termination_due_at = None
    elif case["status"] == "active" and new_termination_due_at is None:
        active_strikes = get_active_punishment_count(
            case["member_id"],
            guild.id,
            "Strike",
        )
        if case["punishment"] != "Strike":
            active_strikes += 1
        if active_strikes >= 3:
            now = datetime.now(EASTERN_TIME) if EASTERN_TIME else datetime.now().astimezone()
            new_termination_due_at = (now + timedelta(hours=24)).isoformat()
    with database_connection() as connection:
        updated = connection.execute(
            "UPDATE punishment_cases SET punishment = ?, reason = ?, appealable = ?, "
            "appealable_by = ?, termination_due_at = ? "
            "WHERE case_id = ? AND guild_id = ?",
            (
                new_punishment,
                reason.strip() if reason is not None else case["reason"],
                new_appealable,
                new_appealable_by,
                new_termination_due_at,
                case_number,
                guild.id,
            ),
        )
    if updated.rowcount != 1:
        await respond_privately(interaction, "The case changed before it could be edited.")
        return

    role_error = (
        await sync_punishment_roles(guild, member)
        if member is not None
        else None
    )
    if role_error:
        with database_connection() as connection:
            connection.execute(
                "UPDATE punishment_cases SET punishment = ?, reason = ?, appealable = ?, "
                "appealable_by = ?, termination_due_at = ? WHERE case_id = ?",
                (*old_values, case_number),
            )
        rollback_role_error = (
            await sync_punishment_roles(guild, member)
            if member is not None
            else None
        )
        await respond_privately(
            interaction,
            f"Case changes were rolled back because roles could not be synced: {role_error}"
            + (
                f" Previous roles could not be fully restored: {rollback_role_error}"
                if rollback_role_error
                else ""
            ),
        )
        return

    message = await fetch_case_message(guild, case)
    log_warning = ""
    if message is not None and message.flags.components_v2:
        layout = discord.ui.LayoutView.from_message(message, timeout=None)
        displays = get_layout_text_displays(layout)
        for display in displays:
            content = display.content
            content = re.sub(
                r"(?m)^(\*\*Punishment:\*\*\s*).*$",
                lambda match: match.group(1) + str(new_punishment),
                content,
            )
            content = re.sub(
                r"(?m)^(\*\*Reason:\*\*\s*).*$",
                lambda match: match.group(1)
                + (reason.strip() if reason is not None else str(case["reason"])),
                content,
            )
            content = re.sub(
                r"(?m)^(\*\*Appealable:\*\*\s*).*$",
                lambda match: match.group(1) + ("✅ Yes" if new_appealable else "❌ No"),
                content,
            )
            content = re.sub(
                r"(?m)^(\*\*Appealable By:\*\*\s*).*$",
                lambda match: match.group(1) + str(new_appealable_by),
                content,
            )
            display.content = content
        try:
            await message.edit(view=layout, allowed_mentions=discord.AllowedMentions.none())
        except DISCORD_REQUEST_ERRORS as error:
            print(f"Could not update edited case post #{case_number}: {error}")
            log_warning = " The original punishment post could not be updated."
    else:
        log_warning = " The original punishment post was unavailable."
    if new_termination_due_at and case["punishment"] != "Strike" and member is not None:
        try:
            await member.send(
                f"⚠️ Case #{case_number} was updated and you now have three active strikes. "
                f"If at least one strike is not appealed before "
                f"<t:{int(datetime.fromisoformat(new_termination_due_at).timestamp())}:F>, "
                "you will be automatically terminated. This notice is not an appealable warning.",
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except DISCORD_REQUEST_ERRORS as error:
            print(f"Could not DM the 24-hour strike notice for edited case #{case_number}: {error}")
            log_warning += " The 24-hour termination notice could not be DM'd."
    await respond_privately(interaction, f"Case #{case_number} updated.{log_warning}")


@cases_group.command(name="wipe", description="Wipe all punishment and promotion cases for a staff member.")
@app_commands.guild_only()
@app_commands.describe(member="Staff member whose case history will be removed")
async def cases_wipe(interaction: discord.Interaction, member: discord.Member) -> None:
    actor = interaction.user
    if (
        not isinstance(actor, discord.Member)
        or not any(role.id in BOD_REVIEWER_ROLE_IDS for role in actor.roles)
    ):
        await respond_privately(interaction, "Only Board of Directors and higher may wipe case records.")
        return
    await interaction.response.send_message(
        f"Confirm permanently deleting every punishment and promotion case for {member.mention}? "
        "This cannot be undone.",
        ephemeral=True,
        view=WipeCasesConfirmationView(member.id, actor.id),
        allowed_mentions=discord.AllowedMentions.none(),
    )


@cases_group.command(name="promotion", description="View every promotion case for a staff member.")
@app_commands.guild_only()
@app_commands.check(staff_only)
@app_commands.describe(member="Staff member whose promotion history to view")
async def cases_promotion(interaction: discord.Interaction, member: discord.Member) -> None:
    guild = interaction.guild
    if guild is None:
        await respond_privately(interaction, "This command can only be used in a server.")
        return
    cases = get_member_promotion_cases(member.id, guild.id)
    view = MemberPromotionsView(guild, member, cases, interaction.user.id)
    await interaction.response.send_message(
        embed=build_member_promotions_embed(guild, member, cases, 0),
        view=view,
        ephemeral=True,
        allowed_mentions=discord.AllowedMentions.none(),
    )


bot.tree.add_command(cases_group)


@bot.tree.command(
    name="staff-member-punish",
    description="Record a staff punishment and apply role changes when needed.",
)
@app_commands.guild_only()
@app_commands.check(staff_only)
@app_commands.choices(
    punishment=[
        app_commands.Choice(name="Infraction", value="Infraction"),
        app_commands.Choice(name="Strike", value="Strike"),
        app_commands.Choice(name="Warning", value="Warning"),
        app_commands.Choice(name="Demotion", value="Demotion"),
        app_commands.Choice(name="Termination", value="Termination"),
        app_commands.Choice(name="Under Investigation", value="Under Investigation"),
    ],
    appealable=[
        app_commands.Choice(name="✅ Yes", value="yes"),
        app_commands.Choice(name="❌ No", value="no"),
    ],
    appealable_by=[
        app_commands.Choice(name="IA+", value="IA+"),
        app_commands.Choice(name="MGMT+", value="MGMT+"),
        app_commands.Choice(name="BoD+", value="BoD+"),
        app_commands.Choice(name="❌ Not Appealable", value="no"),
    ],
)
@app_commands.describe(
    member="Staff member receiving the punishment",
    punishment="Punishment to issue",
    reason="Required reason for the punishment",
    appealable="Whether this punishment can be appealed",
    appealable_by="Minimum team that may review an appeal, or not appealable",
    proof="Proof channel, link, or confidentiality note (for example, Confidential to BoD+)",
    proof_image="Optional image attachment to include with the case",
    old_rank="The staff role being removed for a demotion",
    new_rank="The staff role replacing the old rank",
)
async def staff_member_punish(
    interaction: discord.Interaction,
    member: discord.Member,
    punishment: app_commands.Choice[str],
    reason: str,
    appealable: app_commands.Choice[str],
    appealable_by: app_commands.Choice[str],
    proof: str | None = None,
    proof_image: discord.Attachment | None = None,
    old_rank: discord.Role | None = None,
    new_rank: discord.Role | None = None,
) -> None:
    if len(reason) > 1024 or (proof is not None and len(proof) > 1024):
        await respond_privately(
            interaction,
            "Reason and proof text must each be 1,024 characters or fewer.",
        )
        return
    proof_parts = [proof] if proof else []
    if proof_image is not None:
        proof_parts.append(proof_image.url)
    if len("\n".join(proof_parts)) > 1024:
        await respond_privately(interaction, "The combined proof text and image link must be 1,024 characters or fewer.")
        return

    guild = interaction.guild
    if guild is None:
        await respond_privately(interaction, "This command can only be used in a server.")
        return
    case_punishment, projected_counts, converted_case_ids = plan_punishment_escalation(
        member.id,
        guild.id,
        punishment.value,
    )

    can_appeal = case_punishment != "Warning" and appealable.value == "yes"
    if case_punishment != "Warning" and can_appeal == (appealable_by.value == "no"):
        await respond_privately(
            interaction,
            "Choose an appeal reviewer for an appealable punishment, or choose ❌ "
            "Not Appealable when appealable is ❌ No.",
        )
        return
    case_reason = reason
    if case_punishment != punishment.value:
        case_reason = (
            f"Escalated to {case_punishment} after reaching three active "
            f"{punishment.value.lower()} cases. {reason}"
        )
    termination_due_at: str | None = None
    if case_punishment == "Strike" and projected_counts["Strike"] >= 3:
        now = datetime.now(EASTERN_TIME) if EASTERN_TIME else datetime.now().astimezone()
        termination_due_at = (now + timedelta(hours=24)).isoformat()
        deadline_timestamp = int(
            datetime.fromisoformat(termination_due_at).timestamp()
        )
        case_reason = (
            f"{case_reason}\n\n"
            "⚠️ **24-hour termination notice:** You currently have three active strikes. "
            f"If at least one strike is not appealed before <t:{deadline_timestamp}:F>, "
            "you will be automatically terminated. This notice is not an appealable warning."
        )
    if punishment.value == "Termination":
        projected_counts = {name: 0 for name in PUNISHMENT_ROLE_IDS}

    if punishment.value == "Demotion":
        if old_rank is None or new_rank is None:
            await respond_privately(
                interaction,
                "Old Rank and New Rank are required for a demotion.",
            )
            return
        role_changes = get_demotion_role_changes(member, old_rank, new_rank)
        if isinstance(role_changes, str):
            await respond_privately(interaction, role_changes)
            return
        demotion_roles_to_add, demotion_roles_to_remove = role_changes
    else:
        if old_rank is not None or new_rank is not None:
            await respond_privately(
                interaction,
                "Old Rank and New Rank can only be selected for a demotion.",
            )
            return
        demotion_roles_to_add = []
        demotion_roles_to_remove = []

    await interaction.response.defer(ephemeral=True)

    bot_member = guild.me
    if bot_member is None:
        await respond_privately(interaction, "I could not verify my server permissions.")
        return

    log_channel = guild.get_channel(PUNISHMENT_CHANNEL_ID)
    if log_channel is None:
        try:
            log_channel = await guild.fetch_channel(PUNISHMENT_CHANNEL_ID)
        except DISCORD_REQUEST_ERRORS as error:
            print(f"Could not load punishment log channel: {error}")
            await respond_privately(
                interaction,
                "I could not access the configured punishment log channel.",
            )
            return

    if not isinstance(log_channel, discord.TextChannel):
        await respond_privately(
            interaction,
            "The configured punishment log channel is missing or is not a text channel.",
        )
        return

    log_permissions = log_channel.permissions_for(bot_member)
    if not log_permissions.send_messages or not log_permissions.embed_links:
        await respond_privately(
            interaction,
            "I need Send Messages and Embed Links permissions in the punishment log channel.",
        )
        return

    staff_roles_to_remove = (
        [role for role in member.roles if role.id in STAFF_ROLE_ID_SET]
        if punishment.value in {"Termination", "Under Investigation"}
        else demotion_roles_to_remove
    )
    roles_to_remove = list(staff_roles_to_remove)
    roles_to_add: list[discord.Role] = []
    if punishment.value == "Demotion":
        roles_to_add = demotion_roles_to_add
    if punishment.value == "Under Investigation":
        investigation_role = guild.get_role(UNDER_INVESTIGATION_ROLE_ID)
        if investigation_role is None:
            await respond_privately(
                interaction,
                "The Under Investigation role ID is not present in this server.",
            )
            return
        roles_to_add.append(investigation_role)

    punishment_role_plan = get_punishment_role_plan(
        guild,
        member,
        projected_counts,
    )
    if isinstance(punishment_role_plan, str):
        await respond_privately(interaction, punishment_role_plan)
        return
    punishment_roles_to_add, punishment_roles_to_remove = punishment_role_plan
    roles_to_add.extend(punishment_roles_to_add)
    roles_to_remove.extend(punishment_roles_to_remove)
    if punishment.value == "Termination":
        punishment_roles_to_remove = [
            role for role in member.roles if role.id in PUNISHMENT_ROLE_ID_SET
        ]
        roles_to_remove.extend(punishment_roles_to_remove)

    changes_roles = punishment.value in {
        "Termination",
        "Under Investigation",
        "Demotion",
    } or bool(punishment_roles_to_add or punishment_roles_to_remove)
    if changes_roles:
        if not bot_member.guild_permissions.manage_roles:
            await respond_privately(interaction, "I need the Manage Roles permission.")
            return
        if member.id == guild.owner_id or member.top_role >= bot_member.top_role:
            await respond_privately(
                interaction,
                "I cannot change this member's roles because of the server role hierarchy.",
            )
            return
        if any(role >= bot_member.top_role for role in roles_to_remove + roles_to_add):
            await respond_privately(
                interaction,
                "Move my bot role above every staff role and the Under Investigation role.",
            )
            return

    appealable_text = "✅ Yes" if can_appeal else "❌ No"
    appeal_reviewer = appealable_by.value if can_appeal else "❌"
    original_roles = list(member.roles)
    case_id = create_case_id()
    created_at, _ = eastern_timestamp()
    saved_removed_role_ids = [
        role.id for role in staff_roles_to_remove
        if role.id in STAFF_ROLE_ID_SET
    ]
    with database_connection() as connection:
        connection.execute(
            "UPDATE punishment_cases SET member_id = ?, punishment = ?, reason = ?, "
            "appealable = ?, appealable_by = ?, status = 'pending', created_at = ?, "
            "removed_role_ids = ?, guild_id = ?, demotion_old_rank_id = ?, "
            "demotion_new_rank_id = ?, demotion_added_role_ids = ?, "
            "termination_due_at = ? WHERE case_id = ?",
            (
                member.id,
                case_punishment,
                case_reason,
                int(can_appeal),
                appeal_reviewer if can_appeal else "no",
                created_at,
                json.dumps(saved_removed_role_ids),
                guild.id,
                old_rank.id if punishment.value == "Demotion" and old_rank is not None else None,
                new_rank.id if punishment.value == "Demotion" and new_rank is not None else None,
                json.dumps([role.id for role in roles_to_add])
                if punishment.value == "Demotion"
                else None,
                termination_due_at,
                case_id,
            ),
        )

    if changes_roles:
        roles_to_remove_ids = {role.id for role in roles_to_remove}
        if punishment.value in {"Termination", "Under Investigation"}:
            roles_to_remove_ids.update(STAFF_ROLE_ID_SET)
            if punishment.value == "Termination":
                roles_to_remove_ids.update(PUNISHMENT_ROLE_ID_SET)
        updated_roles = [
            role for role in member.roles if role.id not in roles_to_remove_ids
        ]
        updated_roles.extend(role for role in roles_to_add if role not in updated_roles)
        try:
            await member.edit(
                roles=updated_roles,
                reason=f"{case_punishment} (case #{case_id}) by {interaction.user}",
            )
        except discord.Forbidden:
            with database_connection() as connection:
                connection.execute(
                    "UPDATE punishment_cases SET status = 'failed' WHERE case_id = ?",
                    (case_id,),
                )
            await respond_privately(
                interaction,
                f"Case #{case_id} was created, but Discord denied the role update. "
                "Check my Manage Roles permission and role position.",
            )
            return
        except discord.HTTPException as error:
            print(f"Role update failed for case #{case_id}: {error}")
            with database_connection() as connection:
                connection.execute(
                    "UPDATE punishment_cases SET status = 'failed' WHERE case_id = ?",
                    (case_id,),
                )
            await respond_privately(
                interaction,
                f"Case #{case_id} was created, but Discord failed the role update.",
            )
            return
        except DISCORD_REQUEST_ERRORS as error:
            print(f"Role update transport failed for case #{case_id}: {error}")
            try:
                refreshed_member = await guild.fetch_member(member.id)
            except DISCORD_REQUEST_ERRORS as refresh_error:
                print(f"Could not verify member roles for case #{case_id}: {refresh_error}")
                with database_connection() as connection:
                    connection.execute(
                        "UPDATE punishment_cases SET status = 'needs_review' WHERE case_id = ?",
                        (case_id,),
                    )
                await respond_privately(
                    interaction,
                    f"Discord's connection failed while applying case #{case_id}. "
                    "I could not verify the role update; check their roles before retrying.",
                )
                return

            refreshed_role_ids = {role.id for role in refreshed_member.roles}
            desired_role_ids = {role.id for role in updated_roles}
            original_role_ids = {role.id for role in original_roles}
            if refreshed_role_ids == desired_role_ids:
                member = refreshed_member
            elif refreshed_role_ids == original_role_ids:
                with database_connection() as connection:
                    connection.execute(
                        "UPDATE punishment_cases SET status = 'failed' WHERE case_id = ?",
                        (case_id,),
                    )
                await respond_privately(
                    interaction,
                    f"Discord did not apply the role changes for case #{case_id}. "
                    "No role changes were made; you can retry.",
                )
                return
            else:
                try:
                    await refreshed_member.edit(
                        roles=original_roles,
                        reason=f"Rolling back uncertain punishment case #{case_id}",
                    )
                except DISCORD_REQUEST_ERRORS as rollback_error:
                    print(
                        f"Could not roll back uncertain roles for case #{case_id}: "
                        f"{rollback_error}"
                    )
                    with database_connection() as connection:
                        connection.execute(
                            "UPDATE punishment_cases SET status = 'needs_review' WHERE case_id = ?",
                            (case_id,),
                        )
                    await respond_privately(
                        interaction,
                        f"Role changes for case #{case_id} are uncertain and rollback failed. "
                        "Check the member's roles before retrying.",
                    )
                    return
                with database_connection() as connection:
                    connection.execute(
                        "UPDATE punishment_cases SET status = 'failed' WHERE case_id = ?",
                        (case_id,),
                    )
                await respond_privately(
                    interaction,
                    f"Discord partially applied case #{case_id}; I restored the original roles. "
                    "You can retry the punishment.",
                )
                return

    punishment_view = build_punishment_view(
        member=member,
        punishment=case_punishment,
        reason=case_reason,
        appealable=appealable_text,
        appealable_by=appeal_reviewer,
        proof="\n".join(proof_parts) if proof_parts else "Not provided",
        issuer=interaction.user,
        case_id=case_id,
        old_rank=old_rank if punishment.value == "Demotion" else None,
        new_rank=new_rank if punishment.value == "Demotion" else None,
    )

    try:
        punishment_message = await log_channel.send(
            view=punishment_view,
            files=[discord.File(PUNISHMENT_BANNER_PATH, filename=PUNISHMENT_BANNER_FILENAME)],
            allowed_mentions=discord.AllowedMentions(users=[member]),
        )
    except discord.Forbidden:
        roles_restored = True
        if changes_roles:
            roles_restored = await restore_roles_after_failed_punishment(
                member,
                original_roles,
                case_id,
            )
        with database_connection() as connection:
            connection.execute(
                "UPDATE punishment_cases SET status = 'failed' WHERE case_id = ?",
                (case_id,),
            )
        await respond_privately(
            interaction,
            f"Case #{case_id} could not be logged because Discord denied the embed. "
            + (
                "The original roles were restored."
                if roles_restored
                else "I could not restore the original roles; please check the member's roles."
            ),
        )
        return
    except discord.HTTPException as error:
        print(f"Could not send punishment log for case #{case_id}: {error}")
        roles_restored = True
        if changes_roles:
            roles_restored = await restore_roles_after_failed_punishment(
                member,
                original_roles,
                case_id,
            )
        with database_connection() as connection:
            connection.execute(
                "UPDATE punishment_cases SET status = 'failed' WHERE case_id = ?",
                (case_id,),
            )
        await respond_privately(
            interaction,
            f"Case #{case_id} could not be logged. "
            + (
                "The original roles were restored."
                if roles_restored
                else "I could not restore the original roles; please check the member's roles."
            ),
        )
        return
    except DISCORD_REQUEST_ERRORS as error:
        print(f"Punishment log transport failed for case #{case_id}: {error}")
        with database_connection() as connection:
            connection.execute(
                "UPDATE punishment_cases SET status = 'needs_review' WHERE case_id = ?",
                (case_id,),
            )
        await respond_privately(
            interaction,
            f"Discord's connection failed while publishing case #{case_id}. "
            "The post may still have reached the channel, so check the punishment log "
            "and member's roles before retrying. The case is marked for review.",
        )
        return

    with database_connection() as connection:
        connection.execute(
            "UPDATE punishment_cases SET status = 'active', message_id = ? WHERE case_id = ?",
            (punishment_message.id, case_id),
        )
        if case_punishment == "Termination":
            connection.execute(
                "UPDATE punishment_cases SET termination_due_at = NULL "
                "WHERE member_id = ? AND guild_id = ? AND termination_due_at IS NOT NULL",
                (member.id, guild.id),
            )
        if converted_case_ids:
            connection.executemany(
                "UPDATE punishment_cases SET status = 'converted' "
                "WHERE case_id = ? AND status = 'active'",
                [(converted_case_id,) for converted_case_id in converted_case_ids],
            )
    for converted_case_id in converted_case_ids:
        converted_case = get_case(converted_case_id)
        if converted_case is not None:
            await set_original_case_marker(
                guild,
                converted_case,
                f"Converted to case #{case_id}",
            )

    triggered_ztp = None
    ztp_status_message = ""
    if case_punishment != "Warning":
        triggered_ztp = get_active_ztp(member.id, guild.id)
        if triggered_ztp is not None:
            termination_error = await terminate_for_ztp(
                guild,
                member,
                interaction.user,
                triggered_ztp,
                case_id,
            )
            if termination_error:
                ztp_status_message = (
                    f" ZTP {format_ztp_id(triggered_ztp['ztp_id'])} triggered, "
                    f"but termination/role cleanup needs attention: {termination_error}"
                )
                print(
                    f"ZTP {format_ztp_id(triggered_ztp['ztp_id'])} termination processing "
                    f"reported an issue after case #{case_id}: {termination_error}"
                )
            else:
                ztp_status_message = (
                    f" ZTP {format_ztp_id(triggered_ztp['ztp_id'])} triggered; "
                    "automatic termination was applied."
                )

    try:
        await member.send(
            view=build_punishment_view(
                member=member,
                punishment=case_punishment,
                reason=case_reason,
                appealable=appealable_text,
                appealable_by=appeal_reviewer,
                proof="\n".join(proof_parts) if proof_parts else "Not provided",
                issuer=interaction.user,
                case_id=case_id,
                old_rank=old_rank if punishment.value == "Demotion" else None,
                new_rank=new_rank if punishment.value == "Demotion" else None,
            ),
            files=[discord.File(PUNISHMENT_BANNER_PATH, filename=PUNISHMENT_BANNER_FILENAME)],
            allowed_mentions=discord.AllowedMentions(users=[member]),
        )
    except discord.Forbidden:
        await respond_privately(
            interaction,
            f"Punishment recorded and logged as case #{case_id}, but I couldn't DM "
            f"the member (their DMs may be closed).{ztp_status_message}",
        )
        return
    except discord.HTTPException as error:
        print(f"Could not DM case #{case_id} to member {member.id}: {error}")
        await respond_privately(
            interaction,
            f"Punishment recorded and logged as case #{case_id}, but Discord failed "
            f"to deliver the DM.{ztp_status_message}",
        )
        return
    except DISCORD_REQUEST_ERRORS as error:
        print(f"Discord transport failed while DMing case #{case_id} to member {member.id}: {error}")
        await respond_privately(
            interaction,
            f"Punishment recorded and logged as case #{case_id}, but Discord's connection "
            f"failed while sending the DM. The member may not have received it.{ztp_status_message}",
        )
        return

    await respond_privately(
        interaction,
        f"Punishment recorded, posted, and sent by DM. Case #{case_id}.{ztp_status_message}",
    )


@bot.tree.command(
    name="open-investigation",
    description="Remove staff roles and open an investigation for a member.",
)
@app_commands.guild_only()
@app_commands.check(staff_only)
@app_commands.describe(
    member="Staff member under investigation",
    reason="Reason for opening the investigation",
)
async def open_investigation(
    interaction: discord.Interaction,
    member: discord.Member,
    reason: str,
) -> None:
    await staff_member_punish.callback(
        interaction,
        member,
        app_commands.Choice(name="Under Investigation", value="Under Investigation"),
        reason,
        app_commands.Choice(name="❌ No", value="no"),
        app_commands.Choice(name="❌ Not Appealable", value="no"),
        None,
        None,
        None,
        None,
    )


@bot.tree.command(
    name="discipline-ui-remove",
    description="Close an investigation and restore the member's saved staff roles.",
)
@app_commands.guild_only()
@app_commands.check(staff_only)
@app_commands.describe(case_number="Active Under Investigation case to close")
async def discipline_ui_remove(
    interaction: discord.Interaction,
    case_number: int,
) -> None:
    guild = interaction.guild
    if guild is None:
        await respond_privately(interaction, "This command can only be used in a server.")
        return
    case = get_case(case_number)
    if (
        case is None
        or case["punishment"] != "Under Investigation"
        or case["status"] != "active"
        or case["guild_id"] != guild.id
    ):
        await respond_privately(
            interaction,
            "Provide an active Under Investigation case number from this server.",
        )
        return
    member = guild.get_member(case["member_id"])
    if member is None:
        try:
            member = await guild.fetch_member(case["member_id"])
        except discord.HTTPException:
            await respond_privately(interaction, "I could not find the investigated member.")
            return
    original_message = await fetch_case_message(guild, case)
    if original_message is None:
        await respond_privately(interaction, "I could not find the original investigation message.")
        return

    await interaction.response.defer(ephemeral=True)
    with database_connection() as connection:
        updated = connection.execute(
            "UPDATE punishment_cases SET status = 'processing' "
            "WHERE case_id = ? AND status = 'active'",
            (case_number,),
        )
    if updated.rowcount != 1:
        await respond_privately(interaction, "This case was changed by another action.")
        return

    error_message = await restore_case_staff_roles(
        guild,
        member,
        case,
        {UNDER_INVESTIGATION_ROLE_ID},
    )
    if error_message:
        with database_connection() as connection:
            connection.execute(
                "UPDATE punishment_cases SET status = 'active' "
                "WHERE case_id = ? AND status = 'processing'",
                (case_number,),
            )
        await respond_privately(interaction, error_message)
        return

    with database_connection() as connection:
        connection.execute(
            "UPDATE punishment_cases SET status = 'resolved' "
            "WHERE case_id = ? AND status = 'processing'",
            (case_number,),
        )
    await set_original_case_marker(guild, case, "Completed")
    _, display_time = eastern_timestamp()
    embed = discord.Embed(
        title=f"Investigation Completed — Case #{case_number}",
        description=f"{member.mention}'s investigation is complete. Saved staff roles were restored.",
        color=discord.Color.green(),
        timestamp=datetime.now(EASTERN_TIME) if EASTERN_TIME else datetime.now().astimezone(),
    )
    embed.set_footer(text=display_time)
    try:
        await original_message.reply(
            embed=embed,
            mention_author=False,
            allowed_mentions=discord.AllowedMentions.none(),
        )
    except discord.HTTPException as error:
        print(f"Could not log investigation completion for case #{case_number}: {error}")
        await respond_privately(
            interaction,
            f"Investigation closed and roles restored, but the completion reply failed for case #{case_number}.",
        )
        return
    await respond_privately(interaction, f"Investigation closed. Staff roles restored for case #{case_number}.")


@bot.tree.command(
    name="punishment-unappeal",
    description="Restore a punishment record that was previously appealed.",
)
@app_commands.guild_only()
@app_commands.check(staff_only)
@app_commands.describe(case_number="Appealed case to return to active status")
async def punishment_unappeal(
    interaction: discord.Interaction,
    case_number: int,
) -> None:
    guild = interaction.guild
    if guild is None:
        await respond_privately(interaction, "This command can only be used in a server.")
        return
    case = get_case(case_number)
    if (
        case is None
        or case["status"] != "appealed"
        or case["guild_id"] != guild.id
    ):
        await respond_privately(interaction, "That case is not an appealed case in this server.")
        return
    member = guild.get_member(case["member_id"])
    if member is None:
        try:
            member = await guild.fetch_member(case["member_id"])
        except discord.NotFound:
            member = None
        except DISCORD_REQUEST_ERRORS as error:
            await respond_privately(interaction, f"Could not load the member attached to this case: {error}")
            return
    original_message = await fetch_case_message(guild, case)
    if original_message is None:
        await respond_privately(interaction, "I could not find the original punishment message.")
        return

    await interaction.response.defer(ephemeral=True)
    with database_connection() as connection:
        updated = connection.execute(
            "UPDATE punishment_cases SET status = 'active' "
            "WHERE case_id = ? AND status = 'appealed'",
            (case_number,),
        )
        if updated.rowcount == 1:
            connection.execute(
                "UPDATE case_actions SET status = 'reversed' "
                "WHERE case_id = ? AND action_type = 'appeal' AND status = 'pending'",
                (case_number,),
            )
            action = connection.execute(
                "SELECT * FROM case_actions WHERE case_id = ? AND action_type = 'appeal' "
                "ORDER BY action_id DESC LIMIT 1",
                (case_number,),
            ).fetchone()
        else:
            action = None
    if updated.rowcount != 1:
        await respond_privately(interaction, "The appealed case was changed by another action.")
        return

    await set_original_case_marker(guild, case, None)
    appeal_log_unavailable = False
    if action is not None and action["message_id"] is not None:
        channel = guild.get_channel(PUNISHMENT_CHANNEL_ID)
        if channel is None:
            try:
                channel = await guild.fetch_channel(PUNISHMENT_CHANNEL_ID)
            except discord.NotFound:
                appeal_log_unavailable = True
                print(
                    f"Punishment channel {PUNISHMENT_CHANNEL_ID} was not found while "
                    f"reversing appeal for case #{case_number}."
                )
            except DISCORD_REQUEST_ERRORS as error:
                appeal_log_unavailable = True
                print(
                    f"Could not load punishment channel while reversing appeal for "
                    f"case #{case_number}: {error}"
                )
        if isinstance(channel, discord.TextChannel):
            try:
                action_message = await channel.fetch_message(action["message_id"])
                if action_message.embeds:
                    appeal_embed = discord.Embed.from_dict(action_message.embeds[0].to_dict())
                    appeal_embed.title = f"Case #{case_number} Appeal Reversed"
                    await action_message.edit(embed=appeal_embed, view=None)
            except discord.NotFound:
                appeal_log_unavailable = True
                print(
                    f"Appeal log message for case #{case_number} was deleted or is "
                    "no longer available; the unappeal will be recorded on the original case."
                )
            except discord.HTTPException as error:
                appeal_log_unavailable = True
                print(f"Could not update appeal log for case #{case_number}: {error}")
        elif channel is not None:
            appeal_log_unavailable = True
            print(
                f"Punishment channel {PUNISHMENT_CHANNEL_ID} is not a text channel; "
                f"could not update the appeal log for case #{case_number}."
            )
    _, display_time = eastern_timestamp()
    embed = discord.Embed(
        title=f"Punishment Restored — Case #{case_number}",
        description=f"{interaction.user.mention} returned this appealed punishment to the active record.",
        color=discord.Color.orange(),
        timestamp=datetime.now(EASTERN_TIME) if EASTERN_TIME else datetime.now().astimezone(),
    )
    embed.set_footer(text=display_time)
    try:
        await original_message.reply(
            embed=embed,
            mention_author=False,
            allowed_mentions=discord.AllowedMentions.none(),
        )
    except discord.HTTPException as error:
        print(f"Could not log unappeal for case #{case_number}: {error}")
        await respond_privately(
            interaction,
            f"Punishment record restored for case #{case_number}, but the log reply failed.",
        )
        return
    renewed_strike_deadline: str | None = None
    with database_connection() as connection:
        strike_state = connection.execute(
            "SELECT COUNT(*) AS amount, "
            "SUM(CASE WHEN termination_due_at IS NOT NULL THEN 1 ELSE 0 END) AS pending "
            "FROM punishment_cases WHERE member_id = ? AND guild_id = ? "
            "AND punishment = 'Strike' AND status = 'active'",
            (case["member_id"], guild.id),
        ).fetchone()
        if (
            strike_state is not None
            and strike_state["amount"] >= 3
            and not strike_state["pending"]
        ):
            now = datetime.now(EASTERN_TIME) if EASTERN_TIME else datetime.now().astimezone()
            renewed_strike_deadline = (now + timedelta(hours=24)).isoformat()
            connection.execute(
                "UPDATE punishment_cases SET termination_due_at = ? WHERE case_id = ("
                "SELECT case_id FROM punishment_cases WHERE member_id = ? AND guild_id = ? "
                "AND punishment = 'Strike' AND status = 'active' "
                "ORDER BY case_id DESC LIMIT 1)",
                (renewed_strike_deadline, case["member_id"], guild.id),
            )
    role_sync_error = (
        await sync_punishment_roles(guild, member)
        if member is not None
        else "The member has left the server; no punishment roles could be synced."
    )
    if strike_state is not None and strike_state["amount"] < 3:
        with database_connection() as connection:
            connection.execute(
                "UPDATE punishment_cases SET termination_due_at = NULL "
                "WHERE member_id = ? AND guild_id = ? AND termination_due_at IS NOT NULL",
                (case["member_id"], guild.id),
            )
    if renewed_strike_deadline is not None and member is not None:
        try:
            await member.send(
                "⚠️ Your appealed case was restored, leaving you with three active strikes. "
                f"If at least one strike is not appealed before "
                f"<t:{int(datetime.fromisoformat(renewed_strike_deadline).timestamp())}:F>, "
                "you will be automatically terminated. This notice is not an appealable warning.",
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except DISCORD_REQUEST_ERRORS as error:
            print(f"Could not DM renewed strike termination notice for case #{case_number}: {error}")
    await respond_privately(
        interaction,
        f"Punishment case #{case_number} is active again."
        + (
            " The original appeal log was unavailable, so the unappeal was recorded "
            "as a reply to the original punishment case."
            if appeal_log_unavailable
            else ""
        )
        + (f" Punishment role sync warning: {role_sync_error}" if role_sync_error else ""),
    )


@bot.tree.command(
    name="discipline-suspend",
    description="Suspend a staff member for up to four weeks.",
)
@app_commands.guild_only()
@app_commands.check(staff_only)
@app_commands.choices(
    weeks=[
        app_commands.Choice(name="1 week", value=1),
        app_commands.Choice(name="2 weeks", value=2),
        app_commands.Choice(name="3 weeks", value=3),
        app_commands.Choice(name="4 weeks", value=4),
    ],
)
@app_commands.describe(
    member="Staff member to suspend",
    weeks="Suspension duration (maximum four weeks)",
    reason="Reason for the suspension",
)
async def discipline_suspend(
    interaction: discord.Interaction,
    member: discord.Member,
    weeks: app_commands.Choice[int],
    reason: str,
) -> None:
    reason = reason.strip()
    if not reason or len(reason) > 1024:
        await respond_privately(interaction, "Enter a suspension reason between 1 and 1,024 characters.")
        return
    if weeks.value not in {1, 2, 3, 4}:
        await respond_privately(interaction, "Suspensions may only last from one to four weeks.")
        return
    guild = interaction.guild
    if guild is None:
        await respond_privately(interaction, "This command can only be used in a server.")
        return
    bot_member = guild.me
    if bot_member is None or not bot_member.guild_permissions.manage_roles:
        await respond_privately(interaction, "I need Manage Roles permission to suspend staff.")
        return
    suspension_role = guild.get_role(SUSPENDED_STAFF_ROLE_ID)
    if suspension_role is None:
        await respond_privately(interaction, "The configured Suspended Staff role is missing from this server.")
        return
    roles_to_remove = [role for role in member.roles if role.id in STAFF_ROLE_ID_SET]
    if not roles_to_remove:
        await respond_privately(interaction, "That member has no configured staff roles to suspend.")
        return
    if member.id == guild.owner_id or member.top_role >= bot_member.top_role:
        await respond_privately(interaction, "The bot's role hierarchy prevents suspending this member.")
        return
    if any(role >= bot_member.top_role for role in [*roles_to_remove, suspension_role]):
        await respond_privately(interaction, "Move the bot role above the staff and Suspended Staff roles.")
        return
    if any(
        case["member_id"] == member.id
        and case["guild_id"] == guild.id
        and case["status"] == "active"
        and case["punishment"] in {"Suspension", "Under Investigation"}
        for case in get_active_cases_for_member(member.id)
    ):
        await respond_privately(interaction, "This member already has an active suspension or investigation.")
        return

    log_channel = guild.get_channel(PUNISHMENT_CHANNEL_ID)
    if not isinstance(log_channel, discord.TextChannel):
        try:
            log_channel = await guild.fetch_channel(PUNISHMENT_CHANNEL_ID)
        except discord.HTTPException as error:
            print(f"Could not load punishment log channel: {error}")
            await respond_privately(interaction, "I could not access the punishment log channel.")
            return
    permissions = log_channel.permissions_for(bot_member)
    if not permissions.send_messages or not permissions.attach_files:
        await respond_privately(
            interaction,
            "I need Send Messages and Attach Files permissions in the punishment log channel.",
        )
        return

    await interaction.response.defer(ephemeral=True)
    now = datetime.now(EASTERN_TIME) if EASTERN_TIME else datetime.now().astimezone()
    expiry = now + timedelta(weeks=weeks.value)
    case_id = create_case_id()
    saved_role_ids = [role.id for role in roles_to_remove]
    with database_connection() as connection:
        connection.execute(
            "UPDATE punishment_cases SET member_id = ?, punishment = 'Suspension', "
            "reason = ?, appealable = 0, appealable_by = 'no', status = 'pending', "
            "message_id = NULL, created_at = ?, removed_role_ids = ?, guild_id = ?, "
            "suspension_until = ? WHERE case_id = ?",
            (
                member.id,
                reason,
                now.isoformat(),
                json.dumps(saved_role_ids),
                guild.id,
                expiry.isoformat(),
                case_id,
            ),
        )
    original_roles = list(member.roles)
    updated_roles = [role for role in member.roles if role.id not in STAFF_ROLE_ID_SET]
    if suspension_role not in updated_roles:
        updated_roles.append(suspension_role)
    try:
        await member.edit(roles=updated_roles, reason=f"Suspended for {weeks.value} week(s), case #{case_id}")
    except discord.HTTPException as error:
        print(f"Could not suspend member {member.id} for case #{case_id}: {error}")
        with database_connection() as connection:
            connection.execute(
                "UPDATE punishment_cases SET status = 'failed' WHERE case_id = ?",
                (case_id,),
            )
        await respond_privately(interaction, "Discord could not apply the suspension roles.")
        return

    appeal_end = expiry.strftime("%B %d, %Y at %I:%M %p %Z")
    punishment_view = build_punishment_view(
        member=member,
        punishment=f"Suspension — {weeks.value} week(s)",
        reason=f"{reason}\n\n**Duration:** {weeks.value} week(s)\n**Ends:** {appeal_end}",
        appealable="❌ No",
        appealable_by="❌",
        proof="Not provided",
        issuer=interaction.user,
        case_id=case_id,
    )
    try:
        punishment_message = await log_channel.send(
            view=punishment_view,
            files=[discord.File(PUNISHMENT_BANNER_PATH, filename=PUNISHMENT_BANNER_FILENAME)],
            allowed_mentions=discord.AllowedMentions(users=[member]),
        )
    except discord.HTTPException as error:
        print(f"Could not log suspension case #{case_id}: {error}")
        restored = await restore_roles_after_failed_punishment(member, original_roles, case_id)
        with database_connection() as connection:
            connection.execute(
                "UPDATE punishment_cases SET status = 'failed' WHERE case_id = ?",
                (case_id,),
            )
        await respond_privately(
            interaction,
            "The suspension could not be logged. "
            + ("Original roles were restored." if restored else "Original roles could not be restored; please check manually."),
        )
        return

    with database_connection() as connection:
        connection.execute(
            "UPDATE punishment_cases SET status = 'active', message_id = ? WHERE case_id = ?",
            (punishment_message.id, case_id),
        )
    ztp_status_message = ""
    triggered_ztp = get_active_ztp(member.id, guild.id)
    if triggered_ztp is not None:
        termination_error = await terminate_for_ztp(
            guild,
            member,
            interaction.user,
            triggered_ztp,
            case_id,
        )
        if termination_error:
            ztp_status_message = (
                f" ZTP {format_ztp_id(triggered_ztp['ztp_id'])} triggered, "
                f"but termination/role cleanup needs attention: {termination_error}"
            )
        else:
            ztp_status_message = (
                f" ZTP {format_ztp_id(triggered_ztp['ztp_id'])} triggered; "
                "automatic termination was applied."
            )
    try:
        await member.send(
            view=build_punishment_view(
                member=member,
                punishment=f"Suspension — {weeks.value} week(s)",
                reason=f"{reason}\n\n**Duration:** {weeks.value} week(s)\n**Ends:** {appeal_end}",
                appealable="❌ No",
                appealable_by="❌",
                proof="Not provided",
                issuer=interaction.user,
                case_id=case_id,
            ),
            files=[discord.File(PUNISHMENT_BANNER_PATH, filename=PUNISHMENT_BANNER_FILENAME)],
            allowed_mentions=discord.AllowedMentions(users=[member]),
        )
    except discord.HTTPException as error:
        print(f"Could not DM suspension case #{case_id} to member {member.id}: {error}")
        await respond_privately(
            interaction,
            f"Suspension case #{case_id} logged; the member DM could not be delivered."
            f"{ztp_status_message}",
        )
        return
    await respond_privately(
        interaction,
        f"Suspension logged as case #{case_id} for {weeks.value} week(s).{ztp_status_message}",
    )


@bot.tree.command(
    name="discipline-appeal",
    description="Record an approved staff discipline appeal against its case.",
)
@app_commands.guild_only()
@app_commands.check(staff_only)
@app_commands.describe(
    case_number="Case number of the punishment being appealed",
    appellant="Staff member whose appeal was approved",
    ticket_number="Ticket number where the appeal was handled",
)
async def discipline_appeal(
    interaction: discord.Interaction,
    case_number: int,
    appellant: discord.Member,
    ticket_number: str,
) -> None:
    if case_number < 1 or not ticket_number.strip() or len(ticket_number) > 80:
        await respond_privately(
            interaction,
            "Provide a valid case number and a ticket number of 1-80 characters.",
        )
        return
    guild = interaction.guild
    if guild is None:
        await respond_privately(interaction, "This command can only be used in a server.")
        return
    case = get_case(case_number)
    if case is None or case["member_id"] is None or case["punishment"] is None:
        await respond_privately(interaction, "That case does not exist or has no linked punishment record.")
        return
    if case["member_id"] != appellant.id:
        await respond_privately(interaction, "The appellant must be the member named in that case.")
        return
    if case["punishment"] == "Warning":
        await respond_privately(interaction, "Warnings are unappealable.")
        return
    if case["status"] != "active":
        await respond_privately(
            interaction,
            f"Case #{case_number} is not active (current status: {case['status']}).",
        )
        return
    if not isinstance(interaction.user, discord.Member):
        await respond_privately(interaction, "This command can only be used by a server member.")
        return
    if not can_review_appeal(interaction.user, case["appealable_by"]):
        if not case["appealable"] or case["appealable_by"] == "no":
            await respond_privately(
                interaction,
                "This case is non-appealable; please talk to Ownership.",
            )
        else:
            await respond_privately(
                interaction,
                "you are not a high enough rank to appeal this case",
            )
        return

    log_channel = guild.get_channel(PUNISHMENT_CHANNEL_ID)
    if not isinstance(log_channel, discord.TextChannel):
        try:
            log_channel = await guild.fetch_channel(PUNISHMENT_CHANNEL_ID)
        except discord.HTTPException as error:
            print(f"Could not load punishment log channel: {error}")
            await respond_privately(interaction, "I could not access the punishment log channel.")
            return
    if not isinstance(log_channel, discord.TextChannel):
        await respond_privately(interaction, "The configured punishment channel is not a text channel.")
        return
    original_message = await fetch_case_message(guild, case)
    if original_message is None:
        await respond_privately(interaction, "I could not find the original punishment message to reply to.")
        return

    await interaction.response.defer(ephemeral=True)
    created_at, display_time = eastern_timestamp()
    action_id = create_action(
        case_number,
        "appeal",
        interaction.user.id,
        appellant.id,
        created_at,
        ticket_number=ticket_number.strip(),
    )
    case_was_updated = False
    with database_connection() as connection:
        updated = connection.execute(
            "UPDATE punishment_cases SET status = 'appealed' "
            "WHERE case_id = ? AND status = 'active'",
            (case_number,),
        )
        if updated.rowcount != 1:
            connection.execute(
                "UPDATE case_actions SET status = 'failed' WHERE action_id = ?",
                (action_id,),
            )
        else:
            case_was_updated = True
    if not case_was_updated:
        await respond_privately(interaction, "This case was already changed by another action.")
        return
    strikes, infractions = get_active_punishment_counts(appellant.id)
    embed = discord.Embed(
        title=f"⚖️ Case #{case_number} Appealed Successfully",
        description=(
            f"This case has been appealed by {appellant.mention} via ticket "
            f"**#{discord.utils.escape_markdown(ticket_number)}**.\n\n"
            "**Action Taken**\n"
            "Record Cleared.\n"
            f"*Roles dynamically synced with DB: {strikes} Strike(s), "
            f"{infractions} Infraction(s).*"
        ),
        color=discord.Color.green(),
        timestamp=datetime.fromisoformat(created_at),
    )
    embed.set_footer(text=display_time)
    try:
        await set_original_case_marker(guild, case, "Appealed")
        action_message = await log_channel.send(
            embed=embed,
            reference=original_message,
            mention_author=False,
            view=CaseActionView(action_id, "appeal", appellant.id),
            allowed_mentions=discord.AllowedMentions.none(),
        )
    except discord.HTTPException as error:
        print(f"Could not publish appeal action for case #{case_number}: {error}")
        with database_connection() as connection:
            connection.execute(
                "UPDATE punishment_cases SET status = 'active' WHERE case_id = ?",
                (case_number,),
            )
            connection.execute(
                "UPDATE case_actions SET status = 'failed' WHERE action_id = ?",
                (action_id,),
            )
        await set_original_case_marker(guild, case, None)
        await respond_privately(interaction, "The appeal could not be posted; the case remains active.")
        return

    with database_connection() as connection:
        connection.execute(
            "UPDATE case_actions SET message_id = ? WHERE action_id = ?",
            (action_message.id, action_id),
        )
        active_strikes = connection.execute(
            "SELECT COUNT(*) AS amount FROM punishment_cases "
            "WHERE member_id = ? AND guild_id = ? AND punishment = 'Strike' AND status = 'active'",
            (appellant.id, guild.id),
        ).fetchone()
        if active_strikes is not None and active_strikes["amount"] < 3:
            connection.execute(
                "UPDATE punishment_cases SET termination_due_at = NULL "
                "WHERE member_id = ? AND guild_id = ? AND termination_due_at IS NOT NULL",
                (appellant.id, guild.id),
            )
    role_sync_error = await sync_punishment_roles(guild, appellant)
    await respond_privately(
        interaction,
        f"Appeal recorded for case #{case_number}."
        + (f" Punishment role sync warning: {role_sync_error}" if role_sync_error else ""),
    )


@bot.tree.command(
    name="discipline-revoke",
    description="Request confirmation to revoke a discipline case.",
)
@app_commands.guild_only()
@app_commands.check(staff_only)
@app_commands.describe(
    case_number="Case number to revoke",
    reason="Required reason for revoking the case",
    result="Required description of the outcome",
)
async def discipline_revoke(
    interaction: discord.Interaction,
    case_number: int,
    reason: str,
    result: str,
) -> None:
    reason = reason.strip()
    result = result.strip()
    if case_number < 1 or not reason or not result:
        await respond_privately(interaction, "Case number, reason, and result are required.")
        return
    if len(reason) > 1024 or len(result) > 1024:
        await respond_privately(interaction, "Reason and result must each be 1,024 characters or fewer.")
        return

    guild = interaction.guild
    if guild is None or not isinstance(interaction.user, discord.Member):
        await respond_privately(interaction, "This command can only be used by staff in a server.")
        return
    case = get_case(case_number)
    if case is None or case["member_id"] is None or case["punishment"] is None:
        await respond_privately(interaction, "That case does not exist or has no linked punishment record.")
        return
    if case["status"] != "active":
        await respond_privately(
            interaction,
            f"Case #{case_number} is not active (current status: {case['status']}).",
        )
        return
    if interaction.user.id == case["member_id"]:
        await respond_privately(interaction, "You cannot revoke a punishment issued against yourself.")
        return

    has_override = any(role.id in REVOCATION_OVERRIDE_ROLE_IDS for role in interaction.user.roles)
    if case["punishment"] != "Termination" and not has_override:
        await respond_privately(
            interaction,
            "Revocation should only be used for terminations. Other punishments require "
            "permission from SHR, BoD, or Ownership.",
        )
        return

    await interaction.response.send_message(
        f"Confirm revoking case #{case_number}?\n"
        "Revocation should only be used for terminations, except with permission from "
        "high ranks. This will restore the saved staff roles and mark the case revoked.",
        ephemeral=True,
        view=RevokeConfirmationView(
            case_number,
            reason,
            result,
            interaction.user.id,
            case["member_id"],
        ),
    )


async def complete_revocation(
    interaction: discord.Interaction,
    case_number: int,
    reason: str,
    result: str,
    target_id: int,
) -> None:
    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild
    actor = interaction.user
    if guild is None or not isinstance(actor, discord.Member):
        await respond_privately(interaction, "This confirmation must be used in the original server.")
        return

    case = get_case(case_number)
    if case is None or case["status"] != "active" or case["member_id"] != target_id:
        await respond_privately(interaction, "The case is no longer active or no longer matches this confirmation.")
        return
    has_override = any(role.id in REVOCATION_OVERRIDE_ROLE_IDS for role in actor.roles)
    if case["punishment"] != "Termination" and not has_override:
        await respond_privately(interaction, "High-rank permission is required to revoke this non-termination.")
        return

    target = guild.get_member(target_id)
    if target is None:
        try:
            target = await guild.fetch_member(target_id)
        except discord.HTTPException:
            await respond_privately(interaction, "I could not find the member to restore.")
            return
    bot_member = guild.me
    changes_roles = case["punishment"] in {
        "Termination",
        "Under Investigation",
        "Suspension",
        "Demotion",
    }
    if changes_roles and (
        bot_member is None or not bot_member.guild_permissions.manage_roles
    ):
        await respond_privately(interaction, "I need Manage Roles permission to restore staff roles.")
        return
    original_message = await fetch_case_message(guild, case)
    if original_message is None:
        await respond_privately(interaction, "I could not find the original punishment message to reply to.")
        return

    try:
        saved_role_ids = json.loads(case["removed_role_ids"] or "[]")
    except (json.JSONDecodeError, TypeError):
        await respond_privately(interaction, "This case has invalid saved role data; no changes were made.")
        return
    if changes_roles and case["removed_role_ids"] is None:
        await respond_privately(
            interaction,
            "This older case has no saved staff-role history, so I cannot safely restore its roles.",
        )
        return
    roles_to_restore = [
        role for role_id in saved_role_ids if (role := guild.get_role(role_id)) is not None
    ]
    demotion_added_role_ids: set[int] = set()
    demotion_added_roles: list[discord.Role] = []
    if case["punishment"] == "Demotion":
        try:
            demotion_added_role_ids = {
                int(role_id)
                for role_id in json.loads(case["demotion_added_role_ids"] or "[]")
            }
        except (json.JSONDecodeError, TypeError, ValueError):
            await respond_privately(interaction, "This demotion has invalid added-role data; no changes were made.")
            return
        if any(guild.get_role(role_id) is None for role_id in demotion_added_role_ids):
            await respond_privately(interaction, "A demotion role no longer exists; no changes were made.")
            return
        demotion_added_roles = [
            role
            for role_id in demotion_added_role_ids
            if (role := guild.get_role(role_id)) is not None
        ]
    if changes_roles and bot_member is not None and any(
        role >= bot_member.top_role
        for role in roles_to_restore + demotion_added_roles
    ):
        await respond_privately(interaction, "Move my bot role above the staff roles that need restoring.")
        return
    if changes_roles and (
        bot_member is not None
        and (target.id == guild.owner_id or target.top_role >= bot_member.top_role)
    ):
        await respond_privately(interaction, "The bot's role hierarchy prevents restoring this member.")
        return

    log_channel = guild.get_channel(PUNISHMENT_CHANNEL_ID)
    if not isinstance(log_channel, discord.TextChannel):
        try:
            log_channel = await guild.fetch_channel(PUNISHMENT_CHANNEL_ID)
        except discord.HTTPException as error:
            print(f"Could not load punishment log channel: {error}")
            await respond_privately(interaction, "I could not access the punishment channel.")
            return
    if not isinstance(log_channel, discord.TextChannel):
        await respond_privately(interaction, "The configured punishment channel is not a text channel.")
        return

    created_at, display_time = eastern_timestamp()
    action_id = create_action(
        case_number,
        "revoke",
        actor.id,
        target.id,
        created_at,
        reason=reason,
        result=result,
    )
    case_was_updated = False
    with database_connection() as connection:
        updated = connection.execute(
            "UPDATE punishment_cases SET status = 'revoked' "
            "WHERE case_id = ? AND status = 'active'",
            (case_number,),
        )
        if updated.rowcount != 1:
            connection.execute(
                "UPDATE case_actions SET status = 'failed' WHERE action_id = ?",
                (action_id,),
            )
        else:
            case_was_updated = True
    if not case_was_updated:
        await respond_privately(interaction, "This case was already changed by another action.")
        return

    if changes_roles:
        if case["punishment"] == "Demotion":
            new_roles = [
                role for role in target.roles if role.id not in demotion_added_role_ids
            ]
        else:
            new_roles = [
                role for role in target.roles if role.id not in STAFF_ROLE_ID_SET
            ]
            special_role_id = (
                UNDER_INVESTIGATION_ROLE_ID
                if case["punishment"] == "Under Investigation"
                else SUSPENDED_STAFF_ROLE_ID
                if case["punishment"] == "Suspension"
                else None
            )
            if special_role_id is not None:
                new_roles = [role for role in new_roles if role.id != special_role_id]
        new_roles.extend(role for role in roles_to_restore if role not in new_roles)
        try:
            await target.edit(
                roles=new_roles,
                reason=f"Revoked case #{case_number} by {actor}",
            )
        except discord.HTTPException as error:
            print(f"Could not restore staff roles for case #{case_number}: {error}")
            with database_connection() as connection:
                connection.execute(
                    "UPDATE punishment_cases SET status = 'active' WHERE case_id = ?",
                    (case_number,),
                )
                connection.execute(
                    "UPDATE case_actions SET status = 'failed' WHERE action_id = ?",
                    (action_id,),
                )
            await respond_privately(interaction, "Discord could not restore the staff roles; the case remains active.")
            return

    embed = discord.Embed(
        title=f"🛡️ Case #{case_number} Forcefully Revoked",
        description=f"This case has been revoked by {actor.mention}.",
        color=discord.Color.gold(),
        timestamp=datetime.fromisoformat(created_at),
    )
    embed.add_field(name="Reason", value=reason, inline=False)
    embed.add_field(name="Result", value=result, inline=False)
    embed.set_footer(text=display_time)

    try:
        await set_original_case_marker(guild, case, "Revoked")
        action_message = await log_channel.send(
            embed=embed,
            reference=original_message,
            mention_author=False,
            view=CaseActionView(action_id, "revoke", target.id),
            allowed_mentions=discord.AllowedMentions.none(),
        )
    except discord.HTTPException as error:
        print(f"Could not publish revocation for case #{case_number}: {error}")
        action = next((row for row in get_pending_actions() if row["action_id"] == action_id), None)
        if action is not None:
            rollback_error = await rollback_case_action(interaction, action, case)
            if rollback_error:
                print(f"Rollback failed for case #{case_number}: {rollback_error}")
                with database_connection() as connection:
                    connection.execute(
                        "UPDATE case_actions SET status = 'failed' WHERE action_id = ?",
                        (action_id,),
                    )
        else:
            with database_connection() as connection:
                connection.execute(
                    "UPDATE case_actions SET status = 'failed' WHERE action_id = ?",
                    (action_id,),
                )
        await respond_privately(interaction, "The revocation could not be logged; I attempted to restore the original case.")
        return

    with database_connection() as connection:
        connection.execute(
            "UPDATE case_actions SET message_id = ? WHERE action_id = ?",
            (action_message.id, action_id),
        )
    role_sync_error = await sync_punishment_roles(guild, target)
    await respond_privately(
        interaction,
        f"Case #{case_number} revoked. The case record remains in the log."
        + (f" Punishment role sync warning: {role_sync_error}" if role_sync_error else ""),
    )


@bot.tree.command(
    name="promote",
    description="Announce a staff promotion.",
)
@app_commands.guild_only()
@app_commands.describe(
    member="Staff member being promoted",
    old_rank="The member's current rank",
    new_rank="The rank they are being promoted to",
    reason="Reason for the promotion",
    signed_name="Name to display in the signed section",
    ztp="Add a one-week Zero Tolerance Period to this promotion",
)
async def promote(
    interaction: discord.Interaction,
    member: discord.Member,
    old_rank: app_commands.Range[str, 1, 100],
    new_rank: discord.Role,
    reason: app_commands.Range[str, 1, 1000],
    signed_name: app_commands.Range[str, 1, 100],
    ztp: bool = False,
) -> None:
    guild = interaction.guild
    issuer = interaction.user
    if guild is None or not isinstance(issuer, discord.Member):
        await respond_privately(interaction, "This command can only be used in a server.")
        return
    if not any(role.id in BOD_REVIEWER_ROLE_IDS for role in issuer.roles):
        await respond_privately(
            interaction,
            "Only Board of Directors and higher may use the promotion command.",
        )
        return
    if new_rank.id not in STAFF_ROLE_ID_SET:
        await respond_privately(interaction, "Choose a configured staff rank for the promotion.")
        return

    old_rank = old_rank.strip()
    reason = "Fast pass ztp" if ztp else reason.strip()
    signed_name = signed_name.strip()
    if not old_rank or not reason or not signed_name:
        await respond_privately(interaction, "Old rank, reason, and signed name are required.")
        return
    if ztp and get_active_ztp(member.id, guild.id) is not None:
        await respond_privately(interaction, "This staff member already has an active ZTP.")
        return
    if not PROMOTION_BANNER_PATH.is_file():
        await respond_privately(
            interaction,
            "The promotion banner is missing. Restore "
            "`assets/staff_promotion_banner.png` and try again.",
        )
        return

    promotion_channel = guild.get_channel(PROMOTION_CHANNEL_ID)
    if promotion_channel is None:
        try:
            promotion_channel = await guild.fetch_channel(PROMOTION_CHANNEL_ID)
        except discord.HTTPException as error:
            print(f"Could not load promotion channel {PROMOTION_CHANNEL_ID}: {error}")
            await respond_privately(interaction, "I could not access the promotion channel.")
            return
    if not isinstance(promotion_channel, discord.TextChannel):
        await respond_privately(interaction, "The configured promotion channel is not a text channel.")
        return

    bot_member = guild.me
    if (
        bot_member is None
        or not bot_member.guild_permissions.manage_roles
        or member.id == guild.owner_id
        or member.top_role >= bot_member.top_role
    ):
        await respond_privately(
            interaction,
            "I need Manage Roles permission and a role above the promoted member to assign promotion roles.",
        )
        return
    role_changes = get_promotion_role_changes(member, old_rank, new_rank)
    if isinstance(role_changes, str):
        await respond_privately(interaction, role_changes)
        return
    roles_to_add, roles_to_remove = role_changes
    if any(role >= bot_member.top_role for role in roles_to_add + roles_to_remove):
        await respond_privately(
            interaction,
            "Move my bot role above every role being added or removed for this promotion.",
        )
        return
    original_roles = list(member.roles)
    updated_roles = [
        role for role in original_roles if role not in roles_to_remove
    ]
    updated_roles.extend(role for role in roles_to_add if role not in updated_roles)

    await interaction.response.defer(ephemeral=True)
    created_at, _ = eastern_timestamp()
    initialize_database()
    with database_connection() as connection:
        cursor = connection.execute(
            "INSERT INTO promotion_cases "
            "(member_id, old_rank, new_rank_id, reason, signed_name, issuer_id, "
            "guild_id, created_at, added_role_ids, removed_role_ids, roles_tracked) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)",
            (
                member.id,
                old_rank,
                new_rank.id,
                reason,
                signed_name,
                issuer.id,
                guild.id,
                created_at,
                json.dumps([role.id for role in roles_to_add]),
                json.dumps([role.id for role in roles_to_remove]),
            ),
        )
        if cursor.lastrowid is None:
            raise RuntimeError("Could not create a promotion case ID.")
        case_id = cursor.lastrowid

    ztp_case_id: int | None = None
    ztp_expires_at: str | None = None
    if ztp:
        ztp_case_id = create_ztp_case(
            member.id,
            guild.id,
            "Fast pass ztp",
            7,
            issuer.id,
            "promotion",
            case_id,
            status="pending",
        )
        ztp_case = get_ztp_case(ztp_case_id, guild.id)
        if ztp_case is None:
            raise RuntimeError(f"Could not retrieve newly created ZTP {format_ztp_id(ztp_case_id)}.")
        ztp_expiration = datetime.fromisoformat(ztp_case["expires_at"])
        ztp_expires_at = (
            f"<t:{int(ztp_expiration.timestamp())}:F>"
        )

    try:
        await member.edit(
            roles=updated_roles,
            reason=f"Promotion case #{case_id} issued by {issuer}",
        )
    except discord.HTTPException as error:
        print(f"Could not apply promotion roles for case #{case_id}: {error}")
        with database_connection() as connection:
            connection.execute(
                "UPDATE promotion_cases SET status = 'failed' WHERE case_id = ?",
                (case_id,),
            )
            if ztp_case_id is not None:
                connection.execute(
                    "UPDATE ztp_cases SET status = 'failed' WHERE ztp_id = ?",
                    (ztp_case_id,),
                )
        await respond_privately(
            interaction,
            f"Promotion case #{case_id} was created, but Discord could not apply the promotion roles.",
        )
        return

    promotion_view = build_promotion_view(
        member=member,
        old_rank=old_rank,
        new_rank=new_rank,
        reason=reason,
        signed_name=signed_name,
        case_id=case_id,
        ztp_id=format_ztp_id(ztp_case_id) if ztp_case_id is not None else None,
        ztp_expires_at=ztp_expires_at,
    )
    try:
        promotion_message = await promotion_channel.send(
            view=promotion_view,
            files=[discord.File(PROMOTION_BANNER_PATH, filename=PROMOTION_BANNER_FILENAME)],
            allowed_mentions=discord.AllowedMentions(users=[member]),
        )
    except discord.HTTPException as error:
        print(f"Could not publish promotion case #{case_id}: {error}")
        roles_restored = True
        try:
            await member.edit(
                roles=original_roles,
                reason=f"Rolling back unpublished promotion case #{case_id}",
            )
        except discord.HTTPException as rollback_error:
            roles_restored = False
            print(f"Could not roll back roles for promotion case #{case_id}: {rollback_error}")
        with database_connection() as connection:
            connection.execute(
                "UPDATE promotion_cases SET status = 'failed' WHERE case_id = ?",
                (case_id,),
            )
            if ztp_case_id is not None:
                connection.execute(
                    "UPDATE ztp_cases SET status = 'failed' WHERE ztp_id = ?",
                    (ztp_case_id,),
                )
        await respond_privately(
            interaction,
            f"Promotion case #{case_id} could not be published."
            + (
                " The role update was rolled back."
                if roles_restored
                else " The announcement failed and the role update could not be rolled back; check the member's roles."
            ),
        )
        return

    with database_connection() as connection:
        connection.execute(
            "UPDATE promotion_cases SET status = 'published', message_id = ? WHERE case_id = ?",
            (promotion_message.id, case_id),
        )
        if ztp_case_id is not None:
            connection.execute(
                "UPDATE ztp_cases SET status = 'active' WHERE ztp_id = ? AND status = 'pending'",
                (ztp_case_id,),
            )
    ztp_log_error: str | None = None
    if ztp_case_id is not None:
        ztp_log_embed = build_ztp_embed(ztp_case, member.mention)
        ztp_log_embed.title = f"ZTP Started — {format_ztp_id(ztp_case_id)}"
        ztp_log_embed.add_field(
            name="Started By",
            value=issuer.mention,
            inline=False,
        )
        ztp_log_embed.add_field(
            name="Promotion Case",
            value=f"#{case_id}",
            inline=False,
        )
        ztp_log_error = await send_ztp_log(guild, ztp_log_embed)
    dm_sent = True
    try:
        await member.send(
            view=build_promotion_view(
                member=member,
                old_rank=old_rank,
                new_rank=new_rank,
                reason=reason,
                signed_name=signed_name,
                case_id=case_id,
                ztp_id=format_ztp_id(ztp_case_id) if ztp_case_id is not None else None,
                ztp_expires_at=ztp_expires_at,
            ),
            files=[discord.File(PROMOTION_BANNER_PATH, filename=PROMOTION_BANNER_FILENAME)],
            allowed_mentions=discord.AllowedMentions(users=[member]),
        )
    except discord.HTTPException as error:
        dm_sent = False
        print(f"Could not DM promotion case #{case_id} to member {member.id}: {error}")
    with database_connection() as connection:
        connection.execute(
            "UPDATE promotion_cases SET dm_sent = ? WHERE case_id = ?",
            (int(dm_sent), case_id),
        )
    await respond_privately(
        interaction,
        f"Promotion announced for {member.mention}. Promotion Case #{case_id}."
        + (
            f" ZTP {format_ztp_id(ztp_case_id)} is active until {ztp_expires_at}."
            if ztp_case_id is not None and ztp_expires_at is not None
            else ""
        )
        + (f" ZTP log warning: {ztp_log_error}" if ztp_log_error else "")
        + ("" if dm_sent else " I could not DM them; their privacy settings may block messages."),
    )


@bot.tree.command(
    name="retirement",
    description="Record a staff member's retirement.",
)
@app_commands.guild_only()
@app_commands.choices(
    discord_staff=[
        app_commands.Choice(name="Yes", value="yes"),
        app_commands.Choice(name="No", value="no"),
    ],
)
@app_commands.describe(
    member="Staff member who is retiring",
    rank="Their staff rank",
    ticket_number="Retirement ticket number",
    discord_staff="Whether they are Discord staff",
)
async def retirement(
    interaction: discord.Interaction,
    member: discord.Member,
    rank: app_commands.Range[str, 1, 100],
    ticket_number: app_commands.Range[str, 1, 80],
    discord_staff: app_commands.Choice[str],
) -> None:
    guild = interaction.guild
    issuer = interaction.user
    if guild is None or not isinstance(issuer, discord.Member):
        await respond_privately(interaction, "This command can only be used by staff in a server.")
        return
    if not any(role.id in BOD_REVIEWER_ROLE_IDS for role in issuer.roles):
        await respond_privately(
            interaction,
            "Only Board of Directors and higher may record a staff retirement.",
        )
        return
    rank = rank.strip()
    ticket_number = ticket_number.strip().lstrip("#").strip()
    if not rank or not ticket_number:
        await respond_privately(interaction, "Rank and ticket number are required.")
        return
    if not any(role.id in STAFF_ROLE_ID_SET for role in member.roles):
        await respond_privately(interaction, "The selected member has no staff roles to retire.")
        return
    if not RETIREMENT_BANNER_PATH.is_file():
        await respond_privately(
            interaction,
            "The retirement banner is missing. Restore "
            "`assets/staff_retirement_banner.png` and try again.",
        )
        return
    promotion_channel = guild.get_channel(PROMOTION_CHANNEL_ID)
    if promotion_channel is None:
        try:
            promotion_channel = await guild.fetch_channel(PROMOTION_CHANNEL_ID)
        except DISCORD_REQUEST_ERRORS as error:
            print(f"Could not load retirement announcement channel {PROMOTION_CHANNEL_ID}: {error}")
            await respond_privately(interaction, "I could not access the staff announcement channel.")
            return
    if not isinstance(promotion_channel, discord.TextChannel):
        await respond_privately(interaction, "The configured staff announcement channel is not a text channel.")
        return

    bot_member = guild.me
    staff_roles = [role for role in member.roles if role.id in STAFF_ROLE_ID_SET]
    retired_staff_role = guild.get_role(RETIRED_STAFF_ROLE_ID)
    if retired_staff_role is None:
        await respond_privately(
            interaction,
            f"The configured retired staff role ({RETIRED_STAFF_ROLE_ID}) is missing from this server.",
        )
        return
    if (
        bot_member is None
        or not bot_member.guild_permissions.manage_roles
        or member.id == guild.owner_id
        or member.top_role >= bot_member.top_role
        or any(role >= bot_member.top_role for role in staff_roles)
        or retired_staff_role >= bot_member.top_role
    ):
        await respond_privately(
            interaction,
            "I need Manage Roles permission and a role above the retiring member, their staff roles, "
            "and the retired staff role.",
        )
        return
    original_roles = list(member.roles)
    updated_roles = [role for role in original_roles if role.id not in STAFF_ROLE_ID_SET]
    if retired_staff_role not in updated_roles:
        updated_roles.append(retired_staff_role)
    await interaction.response.defer(ephemeral=True)
    created_at, _ = eastern_timestamp()
    case_id = create_case_id()
    reason = (
        f"Staff retirement; rank: {rank}; ticket: #{ticket_number}; "
        f"Discord staff: {'Yes' if discord_staff.value == 'yes' else 'No'}."
    )
    with database_connection() as connection:
        connection.execute(
            "UPDATE punishment_cases SET member_id = ?, punishment = 'Retirement', "
            "reason = ?, appealable = 0, appealable_by = 'no', status = 'pending', "
            "created_at = ?, removed_role_ids = ?, guild_id = ? WHERE case_id = ?",
            (
                member.id,
                reason,
                created_at,
                json.dumps([role.id for role in staff_roles]),
                guild.id,
                case_id,
            ),
        )
    used_reinstatements = get_member_reinstatement_count(member.id, guild.id)
    reinstatements_left = max(0, MAX_REINSTATEMENTS - used_reinstatements)
    try:
        await member.edit(
            roles=updated_roles,
            reason=f"Retirement case #{case_id} issued by {issuer}",
        )
    except DISCORD_REQUEST_ERRORS as error:
        print(f"Could not remove staff roles for retirement case #{case_id}: {error}")
        with database_connection() as connection:
            connection.execute(
                "UPDATE punishment_cases SET status = 'failed' WHERE case_id = ?",
                (case_id,),
            )
        await respond_privately(interaction, "Discord could not remove the member's staff roles.")
        return

    view = build_retirement_view(
        member=member,
        rank=rank,
        ticket_number=ticket_number,
        discord_staff=discord_staff.value == "yes",
        reinstatements_left=reinstatements_left,
        signed_name=issuer.mention,
        case_id=case_id,
    )
    try:
        message = await promotion_channel.send(
            view=view,
            files=[discord.File(RETIREMENT_BANNER_PATH, filename=RETIREMENT_BANNER_FILENAME)],
            allowed_mentions=discord.AllowedMentions(users=[member]),
        )
    except DISCORD_REQUEST_ERRORS as error:
        print(f"Could not publish retirement case #{case_id}: {error}")
        roles_restored = True
        try:
            await member.edit(
                roles=original_roles,
                reason=f"Rolling back unpublished retirement case #{case_id}",
            )
        except DISCORD_REQUEST_ERRORS as rollback_error:
            roles_restored = False
            print(f"Could not restore roles for retirement case #{case_id}: {rollback_error}")
        with database_connection() as connection:
            connection.execute(
                "UPDATE punishment_cases SET status = 'failed' WHERE case_id = ?",
                (case_id,),
            )
        await respond_privately(
            interaction,
            "The retirement could not be published."
            + (
                " Staff roles were restored."
                if roles_restored
                else " Role restoration also failed; check the member's roles."
            ),
        )
        return
    with database_connection() as connection:
        connection.execute(
            "UPDATE punishment_cases SET status = 'active', message_id = ? "
            "WHERE case_id = ? AND status = 'pending'",
            (message.id, case_id),
        )
    await respond_privately(
        interaction,
        f"Retirement announced for {member.mention}. Case #{case_id}; "
        f"{reinstatements_left} reinstatement(s) left.",
    )


def get_member_reinstatement_count(member_id: int, guild_id: int) -> int:
    initialize_database()
    with database_connection() as connection:
        row = connection.execute(
            "SELECT COUNT(*) AS amount FROM promotion_cases "
            "WHERE member_id = ? AND guild_id = ? AND action_type = 'reinstatement' "
            "AND status = 'published' AND case_id > COALESCE(("
            "SELECT cutoff_case_id FROM reinstatement_resets "
            "WHERE member_id = ? AND guild_id = ? ORDER BY reset_id DESC LIMIT 1"
            "), 0)",
            (member_id, guild_id, member_id, guild_id),
        ).fetchone()
    return 0 if row is None else int(row["amount"])


reinstatements_group = app_commands.Group(
    name="reinstatements",
    description="Manage reinstatement allowances.",
)


@reinstatements_group.command(
    name="reset",
    description="Reset a former staff member's reinstatement allowance to two.",
)
@app_commands.guild_only()
@app_commands.describe(member="Former staff member whose reinstatement count to reset")
async def reinstatements_reset(
    interaction: discord.Interaction,
    member: discord.Member,
) -> None:
    guild = interaction.guild
    actor = interaction.user
    if guild is None or not isinstance(actor, discord.Member):
        await respond_privately(interaction, "This command can only be used by staff in a server.")
        return
    if not any(role.id in BOD_REVIEWER_ROLE_IDS for role in actor.roles):
        await respond_privately(
            interaction,
            "Only Board of Directors and higher may reset reinstatements.",
        )
        return

    initialize_database()
    with database_connection() as connection:
        row = connection.execute(
            "SELECT COALESCE(MAX(case_id), 0) AS cutoff_case_id FROM promotion_cases "
            "WHERE member_id = ? AND guild_id = ? AND action_type = 'reinstatement' "
            "AND status = 'published'",
            (member.id, guild.id),
        ).fetchone()
        cutoff_case_id = 0 if row is None else int(row["cutoff_case_id"])
        created_at, _ = eastern_timestamp()
        connection.execute(
            "INSERT INTO reinstatement_resets "
            "(member_id, guild_id, cutoff_case_id, reset_by, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (member.id, guild.id, cutoff_case_id, actor.id, created_at),
        )

    await respond_privately(
        interaction,
        f"Reset {member.mention}'s reinstatement tracking. They now have "
        f"{MAX_REINSTATEMENTS} reinstatement(s) available.",
    )


bot.tree.add_command(reinstatements_group)


@bot.tree.command(
    name="reinstate",
    description="Reinstate a former staff member with a promotion announcement.",
)
@app_commands.guild_only()
@app_commands.describe(
    member="Former staff member to reinstate",
    new_rank="Staff rank they are receiving",
    ticket_number="Reinstatement ticket number",
)
async def reinstate(
    interaction: discord.Interaction,
    member: discord.Member,
    new_rank: discord.Role,
    ticket_number: app_commands.Range[str, 1, 80],
) -> None:
    guild = interaction.guild
    issuer = interaction.user
    if guild is None or not isinstance(issuer, discord.Member):
        await respond_privately(interaction, "This command can only be used by staff in a server.")
        return
    if not any(role.id in BOD_REVIEWER_ROLE_IDS for role in issuer.roles):
        await respond_privately(
            interaction,
            "Only Board of Directors and higher may reinstate staff members.",
        )
        return
    if new_rank.id not in STAFF_ROLE_ID_SET:
        await respond_privately(interaction, "Choose a configured staff rank for reinstatement.")
        return
    ticket_number = ticket_number.strip().lstrip("#").strip()
    if not ticket_number:
        await respond_privately(interaction, "A ticket number is required.")
        return
    with database_connection() as connection:
        previous_retirement = connection.execute(
            "SELECT 1 FROM punishment_cases WHERE member_id = ? AND guild_id = ? "
            "AND punishment = 'Retirement' AND status != 'failed' LIMIT 1",
            (member.id, guild.id),
        ).fetchone()
    if previous_retirement is None:
        await respond_privately(interaction, "This member has no retirement record to reinstate.")
        return
    used_reinstatements = get_member_reinstatement_count(member.id, guild.id)
    if used_reinstatements >= MAX_REINSTATEMENTS:
        await respond_privately(
            interaction,
            f"This member has used all {MAX_REINSTATEMENTS} reinstatements.",
        )
        return
    if any(role.id in STAFF_ROLE_ID_SET for role in member.roles):
        await respond_privately(interaction, "This member already has staff roles.")
        return
    if not PROMOTION_BANNER_PATH.is_file():
        await respond_privately(
            interaction,
            "The promotion banner is missing. Restore "
            "`assets/staff_promotion_banner.png` and try again.",
        )
        return
    promotion_channel = guild.get_channel(PROMOTION_CHANNEL_ID)
    if promotion_channel is None:
        try:
            promotion_channel = await guild.fetch_channel(PROMOTION_CHANNEL_ID)
        except DISCORD_REQUEST_ERRORS as error:
            print(f"Could not load reinstatement channel {PROMOTION_CHANNEL_ID}: {error}")
            await respond_privately(interaction, "I could not access the staff announcement channel.")
            return
    if not isinstance(promotion_channel, discord.TextChannel):
        await respond_privately(interaction, "The configured staff announcement channel is not a text channel.")
        return

    bot_member = guild.me
    if (
        bot_member is None
        or not bot_member.guild_permissions.manage_roles
        or member.id == guild.owner_id
        or member.top_role >= bot_member.top_role
    ):
        await respond_privately(
            interaction,
            "I need Manage Roles permission and a role above the reinstated member.",
        )
        return
    role_changes = get_promotion_role_changes(member, "Former Staff", new_rank)
    if isinstance(role_changes, str):
        await respond_privately(interaction, role_changes)
        return
    roles_to_add, roles_to_remove = role_changes
    if any(role >= bot_member.top_role for role in roles_to_add + roles_to_remove):
        await respond_privately(interaction, "Move my bot role above every role used for reinstatement.")
        return

    original_roles = list(member.roles)
    updated_roles = [role for role in original_roles if role not in roles_to_remove]
    updated_roles.extend(role for role in roles_to_add if role not in updated_roles)
    signed_name = issuer.mention
    await interaction.response.defer(ephemeral=True)
    created_at, _ = eastern_timestamp()
    initialize_database()
    with database_connection() as connection:
        cursor = connection.execute(
            "INSERT INTO promotion_cases "
            "(member_id, old_rank, new_rank_id, reason, signed_name, issuer_id, guild_id, "
            "created_at, added_role_ids, removed_role_ids, roles_tracked, ticket_number, action_type) "
            "VALUES (?, 'Former Staff', ?, 'Reinstatement', ?, ?, ?, ?, ?, ?, 1, ?, 'reinstatement')",
            (
                member.id,
                new_rank.id,
                signed_name,
                issuer.id,
                guild.id,
                created_at,
                json.dumps([role.id for role in roles_to_add]),
                json.dumps([role.id for role in roles_to_remove]),
                ticket_number,
            ),
        )
        if cursor.lastrowid is None:
            raise RuntimeError("Could not create a reinstatement case ID.")
        case_id = cursor.lastrowid
    try:
        await member.edit(
            roles=updated_roles,
            reason=f"Reinstatement case #{case_id} issued by {issuer}",
        )
    except DISCORD_REQUEST_ERRORS as error:
        print(f"Could not apply reinstatement roles for case #{case_id}: {error}")
        with database_connection() as connection:
            connection.execute(
                "UPDATE promotion_cases SET status = 'failed' WHERE case_id = ?",
                (case_id,),
            )
        await respond_privately(interaction, "Discord could not apply the reinstatement roles.")
        return

    view = build_promotion_view(
        member=member,
        old_rank="Former Staff",
        new_rank=new_rank,
        reason="Reinstatement",
        signed_name=signed_name,
        case_id=case_id,
        ticket_number=ticket_number,
    )
    try:
        message = await promotion_channel.send(
            view=view,
            files=[discord.File(PROMOTION_BANNER_PATH, filename=PROMOTION_BANNER_FILENAME)],
            allowed_mentions=discord.AllowedMentions(users=[member]),
        )
    except DISCORD_REQUEST_ERRORS as error:
        print(f"Could not publish reinstatement case #{case_id}: {error}")
        roles_restored = True
        try:
            await member.edit(
                roles=original_roles,
                reason=f"Rolling back unpublished reinstatement case #{case_id}",
            )
        except DISCORD_REQUEST_ERRORS as rollback_error:
            roles_restored = False
            print(f"Could not roll back roles for reinstatement case #{case_id}: {rollback_error}")
        with database_connection() as connection:
            connection.execute(
                "UPDATE promotion_cases SET status = 'failed' WHERE case_id = ?",
                (case_id,),
            )
        await respond_privately(
            interaction,
            "The reinstatement could not be published."
            + (
                " The role update was rolled back."
                if roles_restored
                else " The announcement failed and the role update could not be rolled back; check the member's roles."
            ),
        )
        return
    with database_connection() as connection:
        connection.execute(
            "UPDATE promotion_cases SET status = 'published', message_id = ? WHERE case_id = ?",
            (message.id, case_id),
        )
    dm_sent = True
    try:
        await member.send(
            view=build_promotion_view(
                member=member,
                old_rank="Former Staff",
                new_rank=new_rank,
                reason="Reinstatement",
                signed_name=signed_name,
                case_id=case_id,
                ticket_number=ticket_number,
            ),
            files=[discord.File(PROMOTION_BANNER_PATH, filename=PROMOTION_BANNER_FILENAME)],
            allowed_mentions=discord.AllowedMentions(users=[member]),
        )
    except DISCORD_REQUEST_ERRORS as error:
        dm_sent = False
        print(f"Could not DM reinstatement case #{case_id} to member {member.id}: {error}")
    with database_connection() as connection:
        connection.execute(
            "UPDATE promotion_cases SET dm_sent = ? WHERE case_id = ?",
            (int(dm_sent), case_id),
        )
    remaining = MAX_REINSTATEMENTS - used_reinstatements - 1
    await respond_privately(
        interaction,
        f"{member.mention} reinstated as {new_rank.mention}. Case #{case_id}; "
        f"{remaining} reinstatement(s) left."
        + ("" if dm_sent else " I could not DM them; their privacy settings may block messages."),
    )


class PromotionRevokeConfirmationView(discord.ui.View):
    def __init__(
        self,
        case_id: int,
        reason: str,
        result: str,
        requester_id: int,
        target_id: int,
    ) -> None:
        super().__init__(timeout=120)
        self.case_id = case_id
        self.reason = reason
        self.result = result
        self.requester_id = requester_id
        self.target_id = target_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.requester_id:
            await respond_privately(interaction, "Only the staff member who started this can confirm it.")
            return False
        return True

    @discord.ui.button(label="Confirm Promotion Revocation", style=discord.ButtonStyle.danger)
    async def confirm(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        button.disabled = True
        await complete_promotion_revocation(
            interaction,
            self.case_id,
            self.reason,
            self.result,
            self.target_id,
        )
        if interaction.message is not None:
            await interaction.message.edit(
                content="Promotion revocation submitted. See the private bot response.",
                view=None,
            )
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        button.disabled = True
        await interaction.response.edit_message(
            content="Promotion revocation cancelled. No changes were made.",
            view=None,
        )
        self.stop()


@bot.tree.command(
    name="promotion-revoke",
    description="Request confirmation to revoke a promotion case.",
)
@app_commands.guild_only()
@app_commands.check(staff_only)
@app_commands.describe(
    case_number="Promotion case number to revoke",
    reason="Required reason for revoking the promotion",
    result="Required description of the outcome",
)
async def promotion_revoke(
    interaction: discord.Interaction,
    case_number: int,
    reason: str,
    result: str,
) -> None:
    reason = reason.strip()
    result = result.strip()
    if case_number < 1 or not reason or not result:
        await respond_privately(interaction, "Case number, reason, and result are required.")
        return
    if len(reason) > 1024 or len(result) > 1024:
        await respond_privately(interaction, "Reason and result must each be 1,024 characters or fewer.")
        return

    guild = interaction.guild
    requester = interaction.user
    if guild is None or not isinstance(requester, discord.Member):
        await respond_privately(interaction, "This command can only be used by staff in a server.")
        return
    initialize_database()
    with database_connection() as connection:
        case = connection.execute(
            "SELECT * FROM promotion_cases WHERE case_id = ? AND guild_id = ?",
            (case_number, guild.id),
        ).fetchone()
    if case is None:
        await respond_privately(interaction, "That promotion case does not exist.")
        return
    if case["status"] != "published":
        await respond_privately(
            interaction,
            f"Promotion case #{case_number} is not active (current status: {case['status']}).",
        )
        return
    if case["member_id"] == requester.id:
        await respond_privately(interaction, "You cannot revoke a promotion issued to yourself.")
        return
    if not case["roles_tracked"] or case["added_role_ids"] is None or case["removed_role_ids"] is None:
        await respond_privately(
            interaction,
            "This older promotion has no saved role-change history, so it cannot be safely revoked automatically.",
        )
        return

    await interaction.response.send_message(
        f"Confirm revoking promotion case #{case_number}?\n"
        "This will remove roles granted by the promotion, restore any roles it removed, "
        "and mark the original announcement as revoked.",
        ephemeral=True,
        view=PromotionRevokeConfirmationView(
            case_number,
            reason,
            result,
            requester.id,
            case["member_id"],
        ),
    )


async def complete_promotion_revocation(
    interaction: discord.Interaction,
    case_number: int,
    reason: str,
    result: str,
    target_id: int,
) -> None:
    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild
    actor = interaction.user
    if guild is None or not isinstance(actor, discord.Member) or not has_staff_role(actor):
        await respond_privately(interaction, "This confirmation must be used by staff in the original server.")
        return

    with database_connection() as connection:
        case = connection.execute(
            "SELECT * FROM promotion_cases WHERE case_id = ? AND guild_id = ?",
            (case_number, guild.id),
        ).fetchone()
    if (
        case is None
        or case["status"] != "published"
        or case["member_id"] != target_id
        or not case["roles_tracked"]
        or case["added_role_ids"] is None
        or case["removed_role_ids"] is None
    ):
        await respond_privately(interaction, "The promotion is no longer active or has no safe role history.")
        return
    if actor.id == target_id:
        await respond_privately(interaction, "You cannot revoke a promotion issued to yourself.")
        return

    try:
        added_role_ids = {int(role_id) for role_id in json.loads(case["added_role_ids"])}
        removed_role_ids = {int(role_id) for role_id in json.loads(case["removed_role_ids"])}
    except (json.JSONDecodeError, TypeError, ValueError) as error:
        print(f"Invalid role history for promotion case #{case_number}: {error}")
        await respond_privately(interaction, "This promotion has invalid role history; no changes were made.")
        return

    target = guild.get_member(target_id)
    if target is None:
        try:
            target = await guild.fetch_member(target_id)
        except discord.HTTPException:
            await respond_privately(interaction, "I could not find the promoted member.")
            return
    original_message: discord.Message | None = None
    promotion_channel = guild.get_channel(PROMOTION_CHANNEL_ID)
    if promotion_channel is None:
        try:
            promotion_channel = await guild.fetch_channel(PROMOTION_CHANNEL_ID)
        except discord.HTTPException as error:
            print(f"Could not load promotion channel {PROMOTION_CHANNEL_ID}: {error}")
            await respond_privately(interaction, "I could not access the promotion channel.")
            return
    if not isinstance(promotion_channel, discord.TextChannel):
        await respond_privately(interaction, "The configured promotion channel is not a text channel.")
        return
    try:
        original_message = await promotion_channel.fetch_message(case["message_id"])
    except (discord.HTTPException, TypeError) as error:
        print(f"Could not find original promotion case #{case_number}: {error}")
        await respond_privately(interaction, "I could not find the original promotion announcement.")
        return

    bot_member = guild.me
    if bot_member is None or not bot_member.guild_permissions.manage_roles:
        await respond_privately(interaction, "I need Manage Roles permission to reverse promotion roles.")
        return
    if target.id == guild.owner_id or target.top_role >= bot_member.top_role:
        await respond_privately(interaction, "The bot's role hierarchy prevents reversing this promotion.")
        return
    roles_to_remove = [
        role for role_id in added_role_ids if (role := guild.get_role(role_id)) is not None
    ]
    roles_to_restore: list[discord.Role] = []
    for role_id in removed_role_ids:
        role = guild.get_role(role_id)
        if role is None:
            await respond_privately(
                interaction,
                f"Role {role_id} from this promotion's history no longer exists; no changes were made.",
            )
            return
        if role not in target.roles:
            roles_to_restore.append(role)
    if any(role >= bot_member.top_role for role in roles_to_remove + roles_to_restore):
        await respond_privately(interaction, "Move my bot role above the promotion roles to reverse.")
        return

    with database_connection() as connection:
        reserved = connection.execute(
            "UPDATE promotion_cases SET status = 'revoking' "
            "WHERE case_id = ? AND guild_id = ? AND status = 'published'",
            (case_number, guild.id),
        )
        reservation_succeeded = reserved.rowcount == 1
    if not reservation_succeeded:
        await respond_privately(interaction, "This promotion was changed by another action.")
        return

    original_roles = list(target.roles)
    updated_roles = [role for role in original_roles if role not in roles_to_remove]
    updated_roles.extend(role for role in roles_to_restore if role not in updated_roles)
    if roles_to_remove or roles_to_restore:
        try:
            await target.edit(
                roles=updated_roles,
                reason=f"Revoked promotion case #{case_number} by {actor}",
            )
        except discord.HTTPException as error:
            print(f"Could not reverse promotion roles for case #{case_number}: {error}")
            with database_connection() as connection:
                connection.execute(
                    "UPDATE promotion_cases SET status = 'published' WHERE case_id = ?",
                    (case_number,),
                )
            await respond_privately(interaction, "Discord could not reverse the promotion roles.")
            return

    new_rank = guild.get_role(case["new_rank_id"])
    revoked_view = build_promotion_view(
        member=f"<@{target_id}>",
        old_rank=case["old_rank"],
        new_rank=new_rank if new_rank is not None else f"<@&{case['new_rank_id']}>",
        reason=case["reason"],
        signed_name=case["signed_name"],
        case_id=case_number,
        revoked=True,
    )
    created_at, display_time = eastern_timestamp()
    embed = discord.Embed(
        title=f"Promotion Case #{case_number} Revoked",
        description=f"This promotion has been revoked by {actor.mention}.",
        color=discord.Color.gold(),
        timestamp=datetime.fromisoformat(created_at),
    )
    embed.add_field(name="Reason", value=reason, inline=False)
    embed.add_field(name="Result", value=result, inline=False)
    embed.set_footer(text=display_time)
    try:
        await original_message.edit(
            view=revoked_view,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        await original_message.reply(
            embed=embed,
            mention_author=False,
            allowed_mentions=discord.AllowedMentions.none(),
        )
    except discord.HTTPException as error:
        print(f"Could not log revocation for promotion case #{case_number}: {error}")
        roles_restored = True
        if roles_to_remove or roles_to_restore:
            try:
                await target.edit(
                    roles=original_roles,
                    reason=f"Rolling back failed promotion revocation for case #{case_number}",
                )
            except discord.HTTPException as rollback_error:
                roles_restored = False
                print(
                    f"Could not restore roles after failed promotion revocation "
                    f"for case #{case_number}: {rollback_error}"
                )
        try:
            await original_message.edit(
                view=build_promotion_view(
                    member=f"<@{target_id}>",
                    old_rank=case["old_rank"],
                    new_rank=new_rank if new_rank is not None else f"<@&{case['new_rank_id']}>",
                    reason=case["reason"],
                    signed_name=case["signed_name"],
                    case_id=case_number,
                ),
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.HTTPException as restore_error:
            print(f"Could not restore original promotion post #{case_number}: {restore_error}")
        with database_connection() as connection:
            connection.execute(
                "UPDATE promotion_cases SET status = 'published' WHERE case_id = ?",
                (case_number,),
            )
        await respond_privately(
            interaction,
            "The revocation could not be logged. "
            + (
                "Role changes were restored."
                if roles_restored
                else "Role rollback failed; check the promoted member's roles."
            ),
        )
        return

    with database_connection() as connection:
        revoked_ztps = connection.execute(
            "SELECT * FROM ztp_cases "
            "WHERE source = 'promotion' AND source_case_id = ? AND status = 'active'",
            (case_number,),
        ).fetchall()
        connection.execute(
            "UPDATE promotion_cases SET status = 'revoked' WHERE case_id = ?",
            (case_number,),
        )
        connection.execute(
            "UPDATE ztp_cases SET status = 'revoked' "
            "WHERE source = 'promotion' AND source_case_id = ? AND status = 'active'",
            (case_number,),
        )
    ztp_log_errors: list[str] = []
    if guild is not None:
        for ztp_case in revoked_ztps:
            log_error = await send_ztp_log(
                guild,
                discord.Embed(
                    title=f"ZTP Ended — {format_ztp_id(ztp_case['ztp_id'])}",
                    description=(
                        f"**Staff Member:** <@{ztp_case['member_id']}>\n"
                        f"**Ended By:** {interaction.user.mention}\n"
                        f"**Reason:** Associated promotion case #{case_number} was revoked.\n"
                        "**Status:** Revoked"
                    ),
                    color=discord.Color.dark_grey(),
                    timestamp=datetime.now(EASTERN_TIME) if EASTERN_TIME else datetime.now().astimezone(),
                ),
            )
            if log_error:
                ztp_log_errors.append(log_error)
    await respond_privately(
        interaction,
        f"Promotion case #{case_number} revoked."
        + (f" ZTP log warning: {'; '.join(ztp_log_errors)}" if ztp_log_errors else ""),
    )


def build_ztp_embed(case: sqlite3.Row, member_mention: str) -> discord.Embed:
        expires_at = datetime.fromisoformat(case["expires_at"])
        return discord.Embed(
            title=f"Zero Tolerance Period — {format_ztp_id(case['ztp_id'])}",
            description=(
                f"**Staff Member:** {member_mention}\n"
                f"**Reason:** {discord.utils.escape_markdown(case['reason'])}\n"
                f"**Original Duration:** {case['duration_days']} day(s)\n"
                f"**Time Remaining:** {format_time_remaining(case['expires_at'])}\n"
                f"**Ends:** {expires_at.strftime('%B %d, %Y at %I:%M %p %Z')}\n"
                f"**ZTP ID:** {format_ztp_id(case['ztp_id'])}"
            ),
            color=discord.Color.orange(),
            timestamp=datetime.now(EASTERN_TIME) if EASTERN_TIME else datetime.now().astimezone(),
        )


async def send_ztp_log(
    guild: discord.Guild,
    embed: discord.Embed,
) -> str | None:
    channel = guild.get_channel(ZTP_LOG_CHANNEL_ID)
    if channel is None:
        try:
            channel = await guild.fetch_channel(ZTP_LOG_CHANNEL_ID)
        except DISCORD_REQUEST_ERRORS as error:
            print(f"Could not access ZTP log channel {ZTP_LOG_CHANNEL_ID}: {error}")
            return "I could not access the configured ZTP log channel."
    if not isinstance(channel, discord.TextChannel):
        return "The configured ZTP log channel is not a text channel."
    try:
        await channel.send(
            embed=embed,
            allowed_mentions=discord.AllowedMentions.none(),
        )
    except DISCORD_REQUEST_ERRORS as error:
        print(f"Could not send ZTP log to channel {ZTP_LOG_CHANNEL_ID}: {error}")
        return "Discord could not send the ZTP log to the configured channel."
    return None


ztp_commands = app_commands.Group(
        name="ztp",
        description="Manage staff Zero Tolerance Periods.",
)


@ztp_commands.command(
        name="start",
        description="Start a Zero Tolerance Period for a staff member.",
)
@app_commands.guild_only()
@app_commands.check(staff_only)
@app_commands.choices(
        weeks=[
            app_commands.Choice(name="1 week", value=1),
            app_commands.Choice(name="2 weeks", value=2),
            app_commands.Choice(name="3 weeks", value=3),
            app_commands.Choice(name="4 weeks", value=4),
        ],
)
@app_commands.describe(
        member="Staff member to place on ZTP",
        reason="Reason for the Zero Tolerance Period",
        weeks="How long the ZTP will last",
)
async def ztp_start(
        interaction: discord.Interaction,
        member: discord.Member,
        reason: app_commands.Range[str, 1, 1024],
        weeks: app_commands.Choice[int],
) -> None:
        guild = interaction.guild
        issuer = interaction.user
        reason = reason.strip()
        if guild is None or not isinstance(issuer, discord.Member):
            await respond_privately(interaction, "This command can only be used by staff in a server.")
            return
        if not reason:
            await respond_privately(interaction, "A reason is required.")
            return
        if not has_staff_role(member):
            await respond_privately(interaction, "The selected member is not currently on the staff roster.")
            return
        if weeks.value not in {1, 2, 3, 4}:
            await respond_privately(interaction, "ZTP duration must be from one to four weeks.")
            return
        if get_active_ztp(member.id, guild.id) is not None:
            await respond_privately(interaction, "This staff member already has an active ZTP.")
            return

        channel = guild.get_channel(ZTP_LOG_CHANNEL_ID)
        if channel is None:
            try:
                channel = await guild.fetch_channel(ZTP_LOG_CHANNEL_ID)
            except DISCORD_REQUEST_ERRORS as error:
                print(f"Could not load ZTP log channel: {error}")
                await respond_privately(interaction, "I could not access the configured ZTP log channel.")
                return
        if not isinstance(channel, discord.TextChannel):
            await respond_privately(interaction, "The configured ZTP log channel is not a text channel.")
            return

        await interaction.response.defer(ephemeral=True)
        ztp_id = create_ztp_case(
            member.id,
            guild.id,
            reason,
            weeks.value * 7,
            issuer.id,
            "manual",
            None,
            status="pending",
        )
        case = get_ztp_case(ztp_id, guild.id)
        if case is None:
            raise RuntimeError(f"Could not retrieve newly created ZTP {format_ztp_id(ztp_id)}.")
        embed = build_ztp_embed(case, member.mention)
        embed.add_field(name="Started By", value=issuer.mention, inline=False)
        log_error = await send_ztp_log(guild, embed)
        if log_error:
            with database_connection() as connection:
                connection.execute(
                    "UPDATE ztp_cases SET status = 'failed' WHERE ztp_id = ?",
                    (ztp_id,),
                )
            await respond_privately(
                interaction,
                f"ZTP {format_ztp_id(ztp_id)} could not be logged: {log_error}",
            )
            return

        with database_connection() as connection:
            connection.execute(
                "UPDATE ztp_cases SET status = 'active' WHERE ztp_id = ? AND status = 'pending'",
                (ztp_id,),
            )
        try:
            await member.send(
                embed=build_ztp_embed(case, member.mention),
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.HTTPException as error:
            print(f"Could not DM ZTP {format_ztp_id(ztp_id)} to member {member.id}: {error}")
            await respond_privately(
                interaction,
                f"ZTP {format_ztp_id(ztp_id)} started and logged, but I could not DM the staff member.",
            )
            return
        await respond_privately(interaction, f"ZTP {format_ztp_id(ztp_id)} started.")


@ztp_commands.command(
        name="view",
        description="View a staff member's active ZTP.",
)
@app_commands.guild_only()
@app_commands.check(staff_only)
@app_commands.describe(member="Staff member whose active ZTP you want to view")
async def ztp_view(interaction: discord.Interaction, member: discord.Member) -> None:
        guild = interaction.guild
        if guild is None:
            await respond_privately(interaction, "This command can only be used in a server.")
            return
        case = get_active_ztp(member.id, guild.id)
        if case is None:
            await respond_privately(interaction, "That staff member has no active ZTP.")
            return
        await interaction.response.send_message(
            embed=build_ztp_embed(case, member.mention),
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )


@ztp_commands.command(
        name="list",
        description="List active ZTPs in this server.",
)
@app_commands.guild_only()
@app_commands.check(staff_only)
async def ztp_list(interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await respond_privately(interaction, "This command can only be used in a server.")
            return
        cases = get_active_ztp_cases(guild.id)
        if not cases:
            await respond_privately(interaction, "There are no active ZTPs.")
            return

        lines = [
            (
                f"**{format_ztp_id(case['ztp_id'])}** · <@{case['member_id']}>\n"
                f"Reason: {discord.utils.escape_markdown(case['reason'])}\n"
                f"Original: {case['duration_days']} day(s) · "
                f"Remaining: {format_time_remaining(case['expires_at'])}"
            )
            for case in cases
        ]
        pages: list[str] = []
        page = ""
        for line in lines:
            if page and len(page) + len(line) + 2 > 3500:
                pages.append(page)
                page = ""
            if len(line) > 3500:
                line = line[:3497] + "..."
            page = f"{page}\n\n{line}".strip()
        if page:
            pages.append(page)
        if len(pages) > 10:
            await respond_privately(
                interaction,
                f"There are {len(cases)} active ZTPs, too many to show in one response. "
                "Use `/ztp view` to inspect individual staff members.",
            )
            return
        await interaction.response.send_message(
            embeds=[
                discord.Embed(
                    title=f"Active ZTPs ({len(cases)})",
                    description=content,
                    color=discord.Color.orange(),
                )
                for content in pages
            ],
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )


@ztp_commands.command(
        name="duration",
        description="Extend or shorten a ZTP by a number of days.",
)
@app_commands.guild_only()
@app_commands.check(staff_only)
@app_commands.describe(
        ztp_id="ZTP ID, such as ZTP-00042",
        days="Days to change; use a negative number to shorten",
)
async def ztp_duration(
        interaction: discord.Interaction,
        ztp_id: app_commands.Range[str, 1, 16],
        days: app_commands.Range[int, -3650, 3650],
) -> None:
        guild = interaction.guild
        if guild is None:
            await respond_privately(interaction, "This command can only be used in a server.")
            return
        if days == 0:
            await respond_privately(interaction, "Choose a non-zero number of days.")
            return
        normalized_id = ztp_id.strip().upper()
        if normalized_id.startswith("ZTP-"):
            normalized_id = normalized_id[4:]
        if not normalized_id.isdigit():
            await respond_privately(interaction, "Enter a valid ZTP ID, such as ZTP-00042.")
            return
        case = get_ztp_case(int(normalized_id), guild.id)
        if case is None or case["status"] != "active":
            await respond_privately(interaction, "That ZTP does not exist or is not active.")
            return

        current_expiry = datetime.fromisoformat(case["expires_at"])
        now = datetime.now(current_expiry.tzinfo) if current_expiry.tzinfo else datetime.now()
        if current_expiry <= now:
            with database_connection() as connection:
                connection.execute(
                    "UPDATE ztp_cases SET status = 'completed' "
                    "WHERE ztp_id = ? AND status = 'active'",
                    (case["ztp_id"],),
                )
            await respond_privately(interaction, "That ZTP has already expired.")
            return
        expires_at = current_expiry + timedelta(days=days)
        new_status = "active" if expires_at > now else "completed"
        with database_connection() as connection:
            updated = connection.execute(
                "UPDATE ztp_cases SET expires_at = ?, status = ? "
                "WHERE ztp_id = ? AND status = 'active'",
                (expires_at.isoformat(), new_status, case["ztp_id"]),
            )
        if updated.rowcount != 1:
            await respond_privately(interaction, "This ZTP was changed by another action.")
            return
        change_word = "extended" if days > 0 else "shortened"
        log_embed = discord.Embed(
            title=f"ZTP Duration Changed — {format_ztp_id(case['ztp_id'])}",
            description=(
                f"**Staff Member:** <@{case['member_id']}>\n"
                f"**Changed By:** {interaction.user.mention}\n"
                f"**Change:** {change_word.title()} by {abs(days)} day(s)\n"
                f"**Reason:** {discord.utils.escape_markdown(case['reason'])}\n"
                f"**New End Time:** <t:{int(expires_at.timestamp())}:F>\n"
                f"**Status:** {new_status.title()}"
            ),
            color=discord.Color.orange(),
            timestamp=now,
        )
        log_error = await send_ztp_log(guild, log_embed)
        await respond_privately(
            interaction,
            f"ZTP {format_ztp_id(case['ztp_id'])} {change_word} by {abs(days)} day(s). "
            f"New end time: {expires_at.strftime('%B %d, %Y at %I:%M %p %Z')}."
            + (" The ZTP is now complete." if new_status == "completed" else "")
            + (f" ZTP log warning: {log_error}" if log_error else ""),
        )


@ztp_commands.command(
        name="end",
        description="End an active ZTP early.",
)
@app_commands.guild_only()
@app_commands.check(staff_only)
@app_commands.describe(ztp_id="ZTP ID to end, such as ZTP-00042")
async def ztp_end(
        interaction: discord.Interaction,
        ztp_id: app_commands.Range[str, 1, 16],
) -> None:
        guild = interaction.guild
        if guild is None or not isinstance(interaction.user, discord.Member):
            await respond_privately(interaction, "This command can only be used by staff in a server.")
            return
        normalized_id = ztp_id.strip().upper()
        if normalized_id.startswith("ZTP-"):
            normalized_id = normalized_id[4:]
        if not normalized_id.isdigit():
            await respond_privately(interaction, "Enter a valid ZTP ID, such as ZTP-00042.")
            return
        case = get_ztp_case(int(normalized_id), guild.id)
        if case is None:
            await respond_privately(interaction, "That ZTP does not exist.")
            return
        if case["status"] != "active":
            await respond_privately(
                interaction,
                f"ZTP {format_ztp_id(case['ztp_id'])} is not active (status: {case['status']}).",
            )
            return

        now = datetime.now(EASTERN_TIME) if EASTERN_TIME else datetime.now().astimezone()
        expires_at = datetime.fromisoformat(case["expires_at"])
        if expires_at <= now:
            with database_connection() as connection:
                connection.execute(
                    "UPDATE ztp_cases SET status = 'completed' "
                    "WHERE ztp_id = ? AND status = 'active'",
                    (case["ztp_id"],),
                )
            await respond_privately(
                interaction,
                f"ZTP {format_ztp_id(case['ztp_id'])} has already expired.",
            )
            return

        with database_connection() as connection:
            updated = connection.execute(
                "UPDATE ztp_cases SET status = 'ended', ended_at = ?, ended_by = ? "
                "WHERE ztp_id = ? AND guild_id = ? AND status = 'active'",
                (now.isoformat(), interaction.user.id, case["ztp_id"], guild.id),
            )
        if updated.rowcount != 1:
            await respond_privately(interaction, "This ZTP was changed by another action.")
            return
        ended_at = datetime.fromisoformat(now.isoformat())
        log_embed = discord.Embed(
            title=f"ZTP Ended Early — {format_ztp_id(case['ztp_id'])}",
            description=(
                f"**Staff Member:** <@{case['member_id']}>\n"
                f"**Ended By:** {interaction.user.mention}\n"
                f"**Reason:** {discord.utils.escape_markdown(case['reason'])}\n"
                f"**Original Duration:** {case['duration_days']} day(s)\n"
                f"**Ended At:** <t:{int(ended_at.timestamp())}:F>\n"
                "**Status:** Ended early"
            ),
            color=discord.Color.gold(),
            timestamp=now,
        )
        log_error = await send_ztp_log(guild, log_embed)
        await respond_privately(
            interaction,
            f"ZTP {format_ztp_id(case['ztp_id'])} ended early."
            + (f" ZTP log warning: {log_error}" if log_error else ""),
        )


bot.tree.add_command(ztp_commands)


@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError,
) -> None:
    if isinstance(error, app_commands.CheckFailure):
        message = "You need a configured staff role to use this command."
    else:
        print(f"Application command failed: {error}")
        message = "The command failed. Check the bot logs for details."
    await respond_privately(interaction, message)


def main() -> None:
    token = os.getenv("DISCORD_TOKEN")
    if token is None or not token.strip():
        raise RuntimeError(
            "DISCORD_TOKEN is not set. Set it to your bot token before starting the bot."
        )

    bot.run(token)


if __name__ == "__main__":
    main()

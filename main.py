import os
import re
import sqlite3
import time
import aiohttp
from contextlib import contextmanager
from collections.abc import Awaitable, Callable, Iterator
from datetime import datetime, timedelta, timezone
from io import BytesIO

import discord
from discord import app_commands
from discord.ext import commands, tasks


TICKET_TYPES = {
    "general_support": {
        "label": "General Support",
        "icon": "⚙️",
        "select_description": "⚙️ General questions, server help, access issues, and reports.",
        "description": "Use this ticket type for general questions, assistance, server-related issues, bug reports, in-game problems, questions about server rules or procedures, department applications, training, or reporting player rule violations. Please clearly explain your issue or question and provide screenshots or video evidence if applicable. Remain respectful toward staff members and allow them sufficient time to respond.",
        "welcome": "Use this ticket for general questions, access issues, or help with the server. Please describe what you need and include any useful details.",
        "role": "General Support",
        "category_id": 1527024705536655380,
    },
    "internal_affairs": {
        "label": "Internal Affairs",
        "icon": "🛡️",
        "select_description": "🛡️ Confidential reports about staff conduct or policy violations.",
        "description": "Use this ticket type to report staff misconduct, abuse of authority, department member complaints, violations of department policies, unprofessional behavior, or incidents requiring an official investigation. Please provide the names and ranks of the individuals involved, a detailed description of the incident, and any available screenshots, recordings, or other evidence. All information must be truthful, and tickets should not be used for personal arguments or false accusations. Information submitted should remain confidential and only be shared with authorized personnel.",
        "welcome": "Use this ticket to report a concern about member or staff conduct, or to discuss a policy issue. Keep the details relevant; this channel is only visible to you, Internal Affairs, and server administrators.",
        "role": "Internal Affairs",
        "category_id": 1527024993056194592,
    },
    "management_support": {
        "label": "Management",
        "icon": "⚖️",
        "select_description": "⚖️ Appeals, leadership concerns, and management decisions.",
        "description": "Use this ticket type for high-level concerns, appeals regarding significant administrative actions, complaints involving department leadership or management members, unresolved issues, questions about server administration, major suggestions, or requests requiring management approval. Please explain your concern clearly and professionally, include relevant details and evidence when available, and state what resolution or assistance you are requesting. Allow management sufficient time to review your ticket and make a decision.",
        "welcome": "Use this ticket for leadership questions, approvals, or issues that need management attention. Explain what decision or help you need and include relevant context.",
        "role": "Management",
        "category_id": 1527025120328155228,
    },
}

SESSION_DESCRIPTIONS = {
    "low": (
        "📉 **ARKANSAS STATE ROLEPLAY | SESSION LOW** — The current population within Arkansas State Roleplay is below our expected activity level. "
        "We encourage all available community members to join the server and help increase activity throughout the community. An active server allows for a more enjoyable and realistic roleplay experience for civilians, law enforcement, fire and rescue, and other departments. "
        "All members are encouraged to participate in appropriate roleplay scenarios, remain professional while in-game, and help maintain a welcoming environment for everyone. Department members should take this opportunity to respond to calls, conduct patrols, and participate in realistic scenarios while following all established server regulations. "
        "The current session remains active, and community members are encouraged to join and contribute to the session. Please remember that all server rules remain in effect regardless of the current player count. Staff members will continue monitoring the session to ensure that all roleplay activities remain organized and professional. "
        "**ARKANSAS STATE ROLEPLAY | Professionalism • Realism • Community**"
    ),
    "vote": (
        "🗳️ **ARKANSAS STATE ROLEPLAY | SESSION VOTE** — A session vote has been initiated by the Arkansas State Roleplay staff team to determine community interest in an upcoming roleplay session. "
        "This process allows staff to evaluate community activity and make an informed decision regarding session operations. During the voting period, members are encouraged to participate through the designated voting system. All votes will be reviewed once the voting period has concluded, and the staff team will use the results to determine the next appropriate steps for session operations. "
        "The purpose of this vote is to help determine whether there is sufficient interest and participation to support a successful session. All members are expected to follow community guidelines and refrain from spamming reactions, manipulating voting results, or interfering with the voting process. "
        "Voting results do not automatically guarantee that a session will begin, as staffing availability, server readiness, and other operational requirements must also be considered. Once the voting period has concluded, an official announcement will be issued regarding the outcome and any subsequent session preparations. "
       
       
        "**ARKANSAS STATE ROLEPLAY | Professionalism • Realism • Community**"
    ),
    "startup": (
        "🚨 **ARKANSAS STATE ROLEPLAY | SESSION STARTUP** — Arkansas State Roleplay is officially preparing to open a new roleplay session. "
        "All community members are encouraged to begin joining the designated game server and preparing for organized roleplay operations. Staff members will oversee the opening process to ensure that the session begins smoothly and that all participants are prepared to follow the community's established standards. "
        "All players are expected to familiarize themselves with the server rules, maintain appropriate conduct, and participate in realistic scenarios throughout the session. Law enforcement personnel, fire and rescue personnel, civilian roleplayers, and other approved department members should ensure that they are operating within their authorized roles and following all applicable departmental procedures. "
        "Random deathmatching, vehicle deathmatching, exploiting, trolling, and other prohibited activities are not permitted. All participants must follow server rules and staff instructions, while department members must follow their respective departmental guidelines and roleplay procedures. Civilians are expected to maintain realistic behavior and participate in appropriate scenarios. "
        "Disruptive behavior, intentional interference with roleplay operations, or repeated violations may result in disciplinary action. Staff members reserve the right to address violations and maintain order throughout the session. The cooperation of every participant is essential to maintaining a structured and enjoyable roleplay environment. "
        "Please remain patient during the initial setup period and follow any additional instructions issued by the staff team. We appreciate your participation and look forward to another successful session within Arkansas State Roleplay. "
       
       
        "**ARKANSAS STATE ROLEPLAY | Professionalism • Realism • Community**"
    ),
    "shutdown": (
        "🔒 **ARKANSAS STATE ROLEPLAY | SESSION SHUTDOWN** — The current Arkansas State Roleplay session has officially concluded. "
        "All scheduled roleplay operations are now ending, and participants are expected to follow any final instructions provided by the staff team. This announcement serves as formal notification that the active session is no longer operating. "
        "We would like to extend our appreciation to all community members, department personnel, civilian roleplayers, and staff members who contributed their time and effort throughout the session. Your participation helps maintain an active community and supports the continued development of organized, realistic, and enjoyable roleplay experiences. "
        "Please conclude any remaining in-game activities and follow instructions issued by session staff. Department members should ensure that any required reports, training records, or administrative matters are handled through the appropriate channels. Community members should continue to follow Discord rules and maintain respectful conduct outside of active sessions. "
        "Any concerns or incidents that occurred during the session should be reported through the appropriate support or staff reporting system. Information regarding future sessions will be distributed through official community announcements when available. "
        "We appreciate everyone's cooperation, professionalism, and commitment to Arkansas State Roleplay. Every session provides an opportunity to improve our community, strengthen our departments, and deliver a better roleplay experience for all participants. Thank you for being part of Arkansas State Roleplay, and we look forward to seeing everyone at a future session. "
       
       
        "**ARKANSAS STATE ROLEPLAY | Professionalism • Realism • Community**"
    ),
    "full": (
        "🚫 **ARKANSAS STATE ROLEPLAY | SESSION FULL** — The Arkansas State Roleplay game server has officially reached its maximum player capacity. "
        "At this time, the server cannot accommodate additional participants until an existing player leaves or an available slot becomes accessible. This notice is intended to inform community members of the current server status and provide guidance while capacity remains limited. "
        "Due to the current number of active participants, members who have not yet joined may experience difficulty accessing the server. Please remain patient and allow available spaces to open naturally. Repeated joining attempts, unnecessary staff messages, or requests for other participants to be removed are discouraged and may create unnecessary disruptions for both staff and players. "
        "Members should follow any official queue procedures if a queue system is available, monitor official announcements for updates regarding server availability, and continue following all community rules while waiting for access. Staff members will continue monitoring the session and managing any necessary administrative matters. "
        "Access to the server is subject to available capacity, established community procedures, and any additional requirements set by the session management team. We appreciate your continued interest in Arkansas State Roleplay and thank you for your patience and understanding while the server remains at maximum capacity. "
       
       
        "**ARKANSAS STATE ROLEPLAY | Professionalism • Realism • Community**"
    ),
}

DEPARTMENT_OVERVIEW = (
    "Welcome to the Whitelisted Departments information page for Arkansas State Roleplay. Whitelisted departments are specialized departments that require members to complete an application, meet specific requirements, and receive approval from authorized staff before gaining access. These departments are designed for members who demonstrate professionalism, maturity, responsibility, and a strong understanding of realistic roleplay procedures.\n\n"
    "Members interested in joining a whitelisted department must submit an application through the designated application system and provide accurate information. Applicants may be evaluated based on their roleplay experience, activity, knowledge of server rules, communication skills, and ability to follow departmental procedures. Some departments may require additional training, interviews, evaluations, or other qualifications before an applicant is accepted.\n\n"
    "All members of whitelisted departments are expected to maintain professional conduct, follow departmental guidelines, respect the chain of command, and represent Arkansas State Roleplay appropriately at all times. Department members must remain active, participate in required training sessions, follow all applicable server regulations, and comply with instructions issued by authorized department supervisors and staff members. Failure to meet departmental expectations or violations of community rules may result in disciplinary action, suspension, or removal from the department.\n\n"
    "Please understand that submitting an application does not guarantee acceptance. All applications are subject to review, and final decisions are made by the appropriate department leadership or authorized staff members. Members are expected to remain patient throughout the review process and refrain from pressuring staff for application results.\n\n"
    "📋 **IMPORTANT INFORMATION**\n"
    "• Applications must be completed accurately and honestly.\n"
    "• Applicants must meet the requirements established by their chosen department.\n"
    "• Department acceptance is not guaranteed.\n"
    "• Additional training or evaluations may be required.\n"
    "• Members must follow the chain of command and departmental regulations.\n"
    "• Misconduct, inactivity, or abuse of departmental privileges may result in disciplinary action.\n\n"
    "📌 **APPLICATION PROCESS**\n"
    "Interested members should locate the appropriate departmental application, review all requirements, and submit their application for consideration. Once a decision has been made, the applicant will be notified through the appropriate communication channel.\n\n"
    "Thank you for your interest in serving within the specialized departments of Arkansas State Roleplay. We appreciate your dedication to maintaining a professional, realistic, and organized roleplay community."
)
DEPARTMENT_FOOTER = "ARKANSAS STATE ROLEPLAY • Professionalism • Realism • Community"
STAFF_APPLICATION_URL = "https://melonly.xyz/dashboard/7470038197880229888/applications/7474473017955848192"
DEPARTMENT_MANAGEMENT_CHANNEL_ID = 1513827339203510292
DEPARTMENT_INVITES = {
    "fbi": {
        "name": "Arkansas Federal Bureau of Investigation",
        "emoji": "🔎",
        "category": "Whitelisted",
        "invite": "https://discord.gg/XwRauMhCDh",
    },
    "asp": {
        "name": "Arkansas State Police",
        "emoji": "🚓",
        "category": "Whitelisted",
        "invite": "https://discord.gg/Wvh3vfT9S8",
    },
    "pcso": {
        "name": "Pulaski County Sheriff's Office",
        "emoji": "⭐",
        "category": "Whitelisted",
        "invite": None,
    },
    "lrpd": {
        "name": "Little Rock Police Department",
        "emoji": "🚔",
        "category": "Non-whitelisted",
        "invite": "https://discord.gg/ayPmkhq8HB",
    },
    "fire": {
        "name": "Little Rock Fire Department",
        "emoji": "🚒",
        "category": "Non-whitelisted",
        "invite": "https://discord.gg/YD6Pg89aaQ",
    },
    "dot": {
        "name": "Little Rock DOT",
        "emoji": "🚧",
        "category": "Non-whitelisted",
        "invite": None,
    },
}


TICKET_STAFF_ROLE_IDS = {

    "general_support": {
        1515749492799045733,
        1515750290605740242,
        1513157147741913222,
        1513830140289880115,
        1516349051271118958,
    },
    "internal_affairs": {
        1515750290605740242,
        1513157147741913222,
        1513830140289880115,
        1516349051271118958,
    },
    "management_support": {
        1513157147741913222,
        1513830140289880115,
        1516349051271118958,
    },
}
TICKET_PING_ROLE_IDS = {
    ticket_type: role_ids - {1516349051271118958}
    for ticket_type, role_ids in TICKET_STAFF_ROLE_IDS.items()
}
TRANSCRIPT_CHANNEL_ID = 1544804372343562290
SERVICE_RATING_CHANNEL_ID = 1556075895465447485
ERLC_API_URL = "https://api.erlc.gg/v2/server"
ERLC_RETRY_AFTER = 0.0
ERLC_POLLING_DISABLED = False

DATABASE_PATH = os.getenv(
    "DATABASE_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "tickets.sqlite3"),
)
os.makedirs(os.path.dirname(DATABASE_PATH) or ".", exist_ok=True)


@contextmanager
def ticket_db_connection() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(DATABASE_PATH)
    try:
        yield connection
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def initialize_ticket_storage() -> None:
    with ticket_db_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tickets (
                channel_id INTEGER PRIMARY KEY,
                owner_id INTEGER NOT NULL,
                ticket_type TEXT NOT NULL,
                reminders_enabled INTEGER NOT NULL DEFAULT 1,
                last_activity TEXT NOT NULL,
                reminded_at TEXT,
                closed INTEGER NOT NULL DEFAULT 0,
                close_requested INTEGER NOT NULL DEFAULT 0,
                claimed_by INTEGER,
                priority TEXT NOT NULL DEFAULT 'Normal'
            )
            """
        )
        columns = {row[1] for row in connection.execute("PRAGMA table_info(tickets)")}
        if "claimed_by" not in columns:
            connection.execute("ALTER TABLE tickets ADD COLUMN claimed_by INTEGER")
        if "priority" not in columns:
            connection.execute("ALTER TABLE tickets ADD COLUMN priority TEXT NOT NULL DEFAULT 'Normal'")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS ticket_staff_activity (
                channel_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                display_name TEXT NOT NULL,
                claimed_at TEXT,
                helped_at TEXT,
                PRIMARY KEY (channel_id, user_id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS ticket_surveys (
                channel_id INTEGER PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                owner_id INTEGER NOT NULL,
                ticket_type TEXT NOT NULL,
                claimed_staff TEXT NOT NULL,
                helped_staff TEXT NOT NULL,
                rating INTEGER,
                submitted_by INTEGER
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS server_warnings (
                warning_id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                moderator_id INTEGER NOT NULL,
                moderator_name TEXT NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS ticket_internal_notes (
                note_id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id INTEGER NOT NULL,
                author_id INTEGER NOT NULL,
                author_name TEXT NOT NULL,
                note TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS session_panels (
                guild_id INTEGER PRIMARY KEY,
                channel_id INTEGER,
                message_id INTEGER,
                status TEXT NOT NULL DEFAULT 'Offline',
                join_code TEXT NOT NULL DEFAULT 'ARSRPP',
                live_players TEXT NOT NULL DEFAULT 'Waiting for API',
                queue_count TEXT NOT NULL DEFAULT 'Waiting for API',
                api_status TEXT NOT NULL DEFAULT 'Not connected',
                last_update TEXT NOT NULL DEFAULT 'Not connected',
                weekday_times TEXT NOT NULL DEFAULT 'Mon-Fri 3:00 PM-12:00 AM EST',
                weekend_times TEXT NOT NULL DEFAULT 'Sat-Sun 12:00 PM-1:00 AM EST'
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS session_vote_sessions (
                guild_id INTEGER PRIMARY KEY,
                channel_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                required_votes INTEGER NOT NULL,
                starter_id INTEGER NOT NULL,
                starting INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS session_vote_ballots (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            )
            """
        )
        session_columns = {row[1] for row in connection.execute("PRAGMA table_info(session_panels)")}
        if "weekday_times" not in session_columns:
            connection.execute(
                "ALTER TABLE session_panels ADD COLUMN weekday_times TEXT NOT NULL DEFAULT 'Mon-Fri 3:00 PM-12:00 AM EST'"
            )
        if "weekend_times" not in session_columns:
            connection.execute(
                "ALTER TABLE session_panels ADD COLUMN weekend_times TEXT NOT NULL DEFAULT 'Sat-Sun 12:00 PM-1:00 AM EST'"
            )
        connection.execute(
            "UPDATE session_panels SET weekday_times = ? WHERE weekday_times = 'No assigned time'",
            ("Mon-Fri 3:00 PM-12:00 AM EST",),
        )
        connection.execute(
            "UPDATE session_panels SET weekend_times = ? WHERE weekend_times = 'No assigned time'",
            ("Sat-Sun 12:00 PM-1:00 AM EST",),
        )


def add_server_warning(
    guild_id: int,
    user: discord.Member,
    moderator: discord.Member,
    reason: str,
) -> int:
    with ticket_db_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO server_warnings
                (guild_id, user_id, moderator_id, moderator_name, reason, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (guild_id, user.id, moderator.id, moderator.display_name, reason, utc_now().isoformat()),
        )
    return cursor.lastrowid


def get_server_warnings(guild_id: int, user_id: int) -> list[dict]:
    with ticket_db_connection() as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT warning_id, moderator_id, moderator_name, reason, created_at
            FROM server_warnings
            WHERE guild_id = ? AND user_id = ?
            ORDER BY warning_id DESC
            LIMIT 5
            """,
            (guild_id, user_id),
        ).fetchall()
    return [dict(row) for row in rows]


def clear_server_warnings(guild_id: int, user_id: int) -> int:
    with ticket_db_connection() as connection:
        cursor = connection.execute(
            "DELETE FROM server_warnings WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
    return cursor.rowcount


def ensure_session_state(guild_id: int) -> None:
    with ticket_db_connection() as connection:
        connection.execute(
            "INSERT OR IGNORE INTO session_panels (guild_id) VALUES (?)",
            (guild_id,),
        )


def get_session_state(guild_id: int) -> dict:
    ensure_session_state(guild_id)
    with ticket_db_connection() as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT * FROM session_panels WHERE guild_id = ?",
            (guild_id,),
        ).fetchone()
    return dict(row)


def update_session_state(guild_id: int, **values: str | int | None) -> None:
    allowed = {
        "channel_id",
        "message_id",
        "status",
        "join_code",
        "live_players",
        "queue_count",
        "api_status",
        "last_update",
        "weekday_times",
        "weekend_times",
    }
    if not values or not values.keys() <= allowed:
        raise ValueError("Unsupported session state field")
    ensure_session_state(guild_id)
    assignments = ", ".join(f"{field} = ?" for field in values)
    with ticket_db_connection() as connection:
        connection.execute(
            f"UPDATE session_panels SET {assignments} WHERE guild_id = ?",
            (*values.values(), guild_id),
        )


def create_session_vote(
    guild_id: int,
    channel_id: int,
    message_id: int,
    required_votes: int,
    starter_id: int,
) -> None:
    with ticket_db_connection() as connection:
        connection.execute("DELETE FROM session_vote_ballots WHERE guild_id = ?", (guild_id,))
        connection.execute(
            """
            INSERT OR REPLACE INTO session_vote_sessions
                (guild_id, channel_id, message_id, required_votes, starter_id, starting)
            VALUES (?, ?, ?, ?, ?, 0)
            """,
            (guild_id, channel_id, message_id, required_votes, starter_id),
        )


def get_session_vote(guild_id: int) -> dict | None:
    with ticket_db_connection() as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT * FROM session_vote_sessions WHERE guild_id = ?",
            (guild_id,),
        ).fetchone()
    return dict(row) if row else None


def get_session_vote_count(guild_id: int) -> int:
    with ticket_db_connection() as connection:
        return connection.execute(
            "SELECT COUNT(*) FROM session_vote_ballots WHERE guild_id = ?",
            (guild_id,),
        ).fetchone()[0]


def get_active_session_votes() -> list[dict]:
    with ticket_db_connection() as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT * FROM session_vote_sessions WHERE starting = 0"
        ).fetchall()
    return [dict(row) for row in rows]


def cast_session_vote(guild_id: int, user_id: int) -> tuple[bool, int]:
    with ticket_db_connection() as connection:
        vote = connection.execute(
            "SELECT starting FROM session_vote_sessions WHERE guild_id = ?",
            (guild_id,),
        ).fetchone()
        if vote is None or vote[0]:
            return False, 0
        cursor = connection.execute(
            "INSERT OR IGNORE INTO session_vote_ballots (guild_id, user_id) VALUES (?, ?)",
            (guild_id, user_id),
        )
        count = connection.execute(
            "SELECT COUNT(*) FROM session_vote_ballots WHERE guild_id = ?",
            (guild_id,),
        ).fetchone()[0]
    return cursor.rowcount == 1, count


def claim_session_vote_start(guild_id: int) -> bool:
    with ticket_db_connection() as connection:
        cursor = connection.execute(
            "UPDATE session_vote_sessions SET starting = 1 WHERE guild_id = ? AND starting = 0",
            (guild_id,),
        )
    return cursor.rowcount == 1


def clear_session_vote(guild_id: int) -> None:
    with ticket_db_connection() as connection:
        connection.execute("DELETE FROM session_vote_sessions WHERE guild_id = ?", (guild_id,))
        connection.execute("DELETE FROM session_vote_ballots WHERE guild_id = ?", (guild_id,))


def reset_session_vote_starting(guild_id: int) -> None:
    with ticket_db_connection() as connection:
        connection.execute(
            "UPDATE session_vote_sessions SET starting = 0 WHERE guild_id = ?",
            (guild_id,),
        )


def recover_session_votes() -> None:
    with ticket_db_connection() as connection:
        connection.execute("UPDATE session_vote_sessions SET starting = 0")


def get_ticket_state(channel_id: int) -> dict | None:
    with ticket_db_connection() as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT * FROM tickets WHERE channel_id = ?",
            (channel_id,),
        ).fetchone()
    return dict(row) if row else None


def register_ticket(
    channel_id: int,
    owner_id: int,
    ticket_type: str,
    last_activity: datetime | None = None,
) -> None:
    activity = (last_activity or utc_now()).astimezone(timezone.utc).isoformat()
    with ticket_db_connection() as connection:
        connection.execute(
            """
            INSERT OR IGNORE INTO tickets (channel_id, owner_id, ticket_type, last_activity)
            VALUES (?, ?, ?, ?)
            """,
            (channel_id, owner_id, ticket_type, activity),
        )


def record_ticket_activity(
    channel_id: int,
    owner_id: int,
    ticket_type: str,
    activity_at: datetime,
) -> None:
    activity = activity_at.astimezone(timezone.utc).isoformat()
    with ticket_db_connection() as connection:
        connection.execute(
            """
            INSERT INTO tickets (channel_id, owner_id, ticket_type, last_activity)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(channel_id) DO UPDATE SET
                owner_id = excluded.owner_id,
                ticket_type = excluded.ticket_type,
                last_activity = excluded.last_activity,
                reminded_at = NULL
            WHERE tickets.closed = 0
            """,
            (channel_id, owner_id, ticket_type, activity),
        )


def update_ticket_state(channel_id: int, **values: str | int | None) -> None:
    allowed_fields = {
        "owner_id",
        "ticket_type",
        "reminders_enabled",
        "last_activity",
        "reminded_at",
        "closed",
        "close_requested",
        "claimed_by",
        "priority",
    }
    if not values or not values.keys() <= allowed_fields:
        raise ValueError("Unsupported ticket state field")
    assignments = ", ".join(f"{field} = ?" for field in values)
    with ticket_db_connection() as connection:
        connection.execute(
            f"UPDATE tickets SET {assignments} WHERE channel_id = ?",
            (*values.values(), channel_id),
        )


def record_ticket_staff_activity(
    channel_id: int,
    member: discord.Member,
    *,
    claimed: bool = False,
    helped: bool = False,
) -> None:
    timestamp = utc_now().isoformat()
    claimed_at = timestamp if claimed else None
    helped_at = timestamp if helped else None
    with ticket_db_connection() as connection:
        connection.execute(
            """
            INSERT INTO ticket_staff_activity
                (channel_id, user_id, display_name, claimed_at, helped_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(channel_id, user_id) DO UPDATE SET
                display_name = excluded.display_name,
                claimed_at = COALESCE(ticket_staff_activity.claimed_at, excluded.claimed_at),
                helped_at = COALESCE(ticket_staff_activity.helped_at, excluded.helped_at)
            """,
            (channel_id, member.id, member.display_name, claimed_at, helped_at),
        )


def get_ticket_staff_summary(channel_id: int) -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
    with ticket_db_connection() as connection:
        rows = connection.execute(
            """
            SELECT user_id, display_name, claimed_at, helped_at
            FROM ticket_staff_activity
            WHERE channel_id = ?
            ORDER BY display_name COLLATE NOCASE
            """,
            (channel_id,),
        ).fetchall()
    claimed = [(row[0], row[1]) for row in rows if row[2] is not None]
    helped = [(row[0], row[1]) for row in rows if row[3] is not None]
    return claimed, helped


def add_ticket_note(channel_id: int, author: discord.Member, note: str) -> None:
    with ticket_db_connection() as connection:
        connection.execute(
            """
            INSERT INTO ticket_internal_notes (channel_id, author_id, author_name, note, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (channel_id, author.id, author.display_name, note, utc_now().isoformat()),
        )


def get_ticket_notes(channel_id: int) -> list[dict]:
    with ticket_db_connection() as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT note_id, author_id, author_name, note, created_at
            FROM ticket_internal_notes
            WHERE channel_id = ?
            ORDER BY note_id DESC
            LIMIT 5
            """,
            (channel_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def delete_ticket_note(channel_id: int, note_id: int) -> bool:
    with ticket_db_connection() as connection:
        cursor = connection.execute(
            "DELETE FROM ticket_internal_notes WHERE channel_id = ? AND note_id = ?",
            (channel_id, note_id),
        )
    return cursor.rowcount == 1


def create_ticket_survey(
    channel_id: int,
    guild_id: int,
    owner_id: int,
    ticket_type: str,
    claimed_staff: str,
    helped_staff: str,
) -> None:
    with ticket_db_connection() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO ticket_surveys
                (channel_id, guild_id, owner_id, ticket_type, claimed_staff, helped_staff, rating, submitted_by)
            VALUES (?, ?, ?, ?, ?, ?, NULL, NULL)
            """,
            (channel_id, guild_id, owner_id, ticket_type, claimed_staff, helped_staff),
        )


def get_pending_ticket_surveys() -> list[tuple[int, int]]:
    with ticket_db_connection() as connection:
        return connection.execute(
            "SELECT channel_id, owner_id FROM ticket_surveys WHERE rating IS NULL"
        ).fetchall()


def record_ticket_rating(channel_id: int, owner_id: int, rating: int, voter_id: int) -> dict | None:
    if not 1 <= rating <= 5:
        return None
    with ticket_db_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE ticket_surveys
            SET rating = ?, submitted_by = ?
            WHERE channel_id = ? AND owner_id = ? AND rating IS NULL
            """,
            (rating, voter_id, channel_id, owner_id),
        )
        if cursor.rowcount != 1:
            return None
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT * FROM ticket_surveys WHERE channel_id = ?",
            (channel_id,),
        ).fetchone()
    return dict(row) if row else None


async def ensure_ticket_tracking(channel: discord.TextChannel, owner_id: int, ticket_type: str) -> None:
    if get_ticket_state(channel.id) is not None:
        return

    last_activity = utc_now()
    try:
        async for message in channel.history(limit=100):
            if not message.author.bot:
                last_activity = message.created_at
                break
    except discord.HTTPException:
        pass
    register_ticket(channel.id, owner_id, ticket_type, last_activity)


initialize_ticket_storage()


def ticket_staff_roles(guild: discord.Guild, ticket_type: str) -> list[discord.Role]:
    return [
        role
        for role_id in TICKET_STAFF_ROLE_IDS[ticket_type]
        if (role := guild.get_role(role_id)) is not None
    ]


def ticket_ping_mentions(guild: discord.Guild, ticket_type: str) -> str:
    return " ".join(
        role.mention
        for role_id in TICKET_PING_ROLE_IDS[ticket_type]
        if (role := guild.get_role(role_id)) is not None
    )


async def apply_ticket_staff_permissions(
    channel: discord.TextChannel,
    guild: discord.Guild,
    ticket_type: str,
) -> None:
    allowed_role_ids = TICKET_STAFF_ROLE_IDS[ticket_type]
    configured_role_ids = set().union(*TICKET_STAFF_ROLE_IDS.values())
    for role_id in configured_role_ids:
        role = guild.get_role(role_id)
        if role is None:
            continue
        current = channel.overwrites_for(role)
        if role_id in allowed_role_ids:
            if any(
                permission is not True
                for permission in (
                    current.view_channel,
                    current.send_messages,
                    current.read_message_history,
                    current.attach_files,
                    current.embed_links,
                )
            ):
                await channel.set_permissions(
                    role,
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    attach_files=True,
                    embed_links=True,
                )
        elif current.view_channel is True or current.send_messages is True:
            await channel.set_permissions(
                role,
                view_channel=False,
                send_messages=False,
                read_message_history=False,
            )


def ticket_category(guild: discord.Guild, ticket_type: str) -> discord.CategoryChannel | None:
    category = guild.get_channel(TICKET_TYPES[ticket_type]["category_id"])
    return category if isinstance(category, discord.CategoryChannel) else None


def ticket_details(channel: discord.abc.GuildChannel) -> tuple[int, str] | None:
    if not isinstance(channel, discord.TextChannel):
        return None

    if channel.topic:
        values = dict(
            part.split("=", 1)
            for part in channel.topic.split(";")
            if "=" in part
        )
        try:
            owner_id = int(values["ticket-owner"])
            ticket_type = values["ticket-type"]
        except (KeyError, ValueError):
            pass
        else:
            if ticket_type in TICKET_TYPES:
                return owner_id, ticket_type

    state = get_ticket_state(channel.id)
    if state is None or state["ticket_type"] not in TICKET_TYPES:
        return None
    return state["owner_id"], state["ticket_type"]


def can_manage_ticket(
    user: discord.User | discord.Member,
    guild: discord.Guild | None,
    owner_id: int,
    ticket_type: str,
) -> bool:
    if user.id == owner_id:
        return True
    if not isinstance(user, discord.Member):
        return False
    if user.guild_permissions.manage_channels:
        return True
    return guild is not None and any(
        role.id in TICKET_STAFF_ROLE_IDS[ticket_type]
        for role in user.roles
    )


def build_ticket_panel_embed() -> discord.Embed:
    embed = discord.Embed(
        title="ARSRP Support Desk",
        description=(
            "**How can we help?**\n"
            "Choose the team that best fits your request. A private channel will be created for you and the assigned team.\n\n"
            "Include relevant details and any evidence that may help the team respond."
        ),
        color=discord.Color.from_rgb(43, 128, 117),
    )
    for ticket in TICKET_TYPES.values():
        embed.add_field(
            name=f"{ticket['icon']}  {ticket['label']}",
            value=ticket["description"],
            inline=False,
        )
    embed.set_footer(text="Select a ticket type below to continue")
    return embed


def resolve_ticket_type(value: str) -> str | None:
    normalized = re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
    for key, ticket in TICKET_TYPES.items():
        aliases = {
            key.replace("_", " "),
            ticket["label"].lower(),
            ticket["role"].lower(),
        }
        if normalized in aliases:
            return key
    return None


async def change_ticket_type(
    channel: discord.TextChannel,
    guild: discord.Guild,
    owner_id: int,
    current_type: str,
    new_type: str,
) -> str:
    category = ticket_category(guild, new_type)
    if category is None:
        return f"I couldn't find the configured category for {TICKET_TYPES[new_type]['label']}."
    missing_role_ids = TICKET_STAFF_ROLE_IDS[new_type] - {
        role.id for role in ticket_staff_roles(guild, new_type)
    }
    if missing_role_ids:
        missing_ids = ", ".join(str(role_id) for role_id in sorted(missing_role_ids))
        return f"I couldn't find these staff role IDs in this server: `{missing_ids}`."

    await apply_ticket_staff_permissions(channel, guild, new_type)
    owner = guild.get_member(owner_id)
    suffix = re.sub(r"[^a-z0-9]+", "-", owner.name.lower()).strip("-")[:20] if owner else str(owner_id)
    new_name = f"ticket-{new_type.replace('_', '-')}-{suffix or owner_id}"
    await channel.edit(
        name=new_name,
        category=category,
        topic=f"ticket-owner={owner_id};ticket-type={new_type}",
    )
    update_ticket_state(
        channel.id,
        ticket_type=new_type,
        last_activity=utc_now().isoformat(),
        reminded_at=None,
    )
    mentions = ticket_ping_mentions(guild, new_type)
    return f"Ticket moved to **{TICKET_TYPES[new_type]['label']}**. {mentions}"


async def set_ticket_member_access(
    channel: discord.TextChannel,
    member: discord.Member,
    allowed: bool,
) -> None:
    await channel.set_permissions(
        member,
        view_channel=allowed,
        send_messages=allowed,
        read_message_history=allowed,
        attach_files=allowed,
        embed_links=allowed,
    )


def is_ticket_staff(user: discord.User | discord.Member, guild: discord.Guild, ticket_type: str) -> bool:
    if not isinstance(user, discord.Member):
        return False
    if user.guild_permissions.manage_channels:
        return True
    return any(role.id in TICKET_STAFF_ROLE_IDS[ticket_type] for role in user.roles)


async def claim_ticket(channel: discord.TextChannel, claimer: discord.Member) -> str:
    details = ticket_details(channel)
    if details is None:
        return "Use this command inside a ticket channel."
    owner_id, ticket_type = details
    await ensure_ticket_tracking(channel, owner_id, ticket_type)
    state = get_ticket_state(channel.id)
    if state is None or state["closed"]:
        return "A closed ticket cannot be claimed."
    current_claimer = state["claimed_by"]
    if current_claimer == claimer.id:
        return "You already have this ticket claimed."
    if current_claimer is not None:
        return f"This ticket is already claimed by <@{current_claimer}>."
    update_ticket_state(channel.id, claimed_by=claimer.id)
    record_ticket_staff_activity(channel.id, claimer, claimed=True)
    return f"{claimer.mention} claimed this ticket."


async def unclaim_ticket(channel: discord.TextChannel, user: discord.Member) -> str:
    details = ticket_details(channel)
    if details is None:
        return "Use this command inside a ticket channel."
    owner_id, ticket_type = details
    await ensure_ticket_tracking(channel, owner_id, ticket_type)
    state = get_ticket_state(channel.id)
    if state is None or state["claimed_by"] is None:
        return "This ticket is not claimed."
    if state["claimed_by"] != user.id and not user.guild_permissions.manage_channels:
        return "Only the assigned staff member or a channel manager can unclaim this ticket."
    update_ticket_state(channel.id, claimed_by=None)
    return f"{user.mention} unclaimed this ticket."


async def get_ticket_status_embed(channel: discord.TextChannel) -> discord.Embed | None:
    details = ticket_details(channel)
    if details is None:
        return None
    owner_id, ticket_type = details
    await ensure_ticket_tracking(channel, owner_id, ticket_type)
    state = get_ticket_state(channel.id)
    if state is None:
        return None

    owner = channel.guild.get_member(owner_id)
    owner_text = owner.mention if owner else f"<@{owner_id}>"
    claimed_by = state["claimed_by"]
    claimer = channel.guild.get_member(claimed_by) if claimed_by else None
    claimed_text = claimer.mention if claimer else (f"<@{claimed_by}>" if claimed_by else "Unclaimed")
    last_activity = datetime.fromisoformat(state["last_activity"])
    status = "Closed" if state["closed"] else "Open"
    reminder_status = "Paused" if not state["reminders_enabled"] else "Active"

    embed = discord.Embed(
        title=f"{TICKET_TYPES[ticket_type]['icon']} Ticket Status",
        color=discord.Color.from_rgb(43, 128, 117),
    )
    embed.add_field(name="Type", value=TICKET_TYPES[ticket_type]["label"], inline=True)
    embed.add_field(name="Status", value=status, inline=True)
    embed.add_field(name="Priority", value=state["priority"], inline=True)
    embed.add_field(name="Opened by", value=owner_text, inline=True)
    embed.add_field(name="Claimed by", value=claimed_text, inline=True)
    embed.add_field(name="Inactivity reminders", value=reminder_status, inline=True)
    embed.add_field(name="Last activity", value=f"<t:{int(last_activity.timestamp())}:R>", inline=True)
    embed.add_field(
        name="Close request",
        value="Requested" if state["close_requested"] else "None",
        inline=True,
    )
    return embed


async def rename_ticket(channel: discord.TextChannel, requested_name: str) -> str:
    slug = re.sub(r"[^a-z0-9-]+", "-", requested_name.lower()).strip("-")
    slug = re.sub(r"-+", "-", slug).removeprefix("ticket-")
    if not slug:
        return "Enter a name containing letters or numbers."
    await channel.edit(name=f"ticket-{slug}"[:100], reason="Ticket renamed by staff")
    return f"Ticket renamed to `ticket-{slug[:93]}`."


async def set_ticket_priority(channel: discord.TextChannel, priority: str) -> str:
    normalized = priority.title()
    if normalized not in {"Low", "Normal", "High", "Urgent"}:
        return "Choose Low, Normal, High, or Urgent."
    details = ticket_details(channel)
    if details is None:
        return "Use this command inside a ticket channel."
    owner_id, ticket_type = details
    await ensure_ticket_tracking(channel, owner_id, ticket_type)
    state = get_ticket_state(channel.id)
    if state is None or state["closed"]:
        return "A closed ticket's priority cannot be changed."
    update_ticket_state(channel.id, priority=normalized)
    return f"Ticket priority set to **{normalized}**."


async def ping_ticket_owner(channel: discord.TextChannel, staff_member: discord.Member) -> str:
    details = ticket_details(channel)
    if details is None:
        return "Use this command inside a ticket channel."
    owner_id, _ = details
    if owner_id == staff_member.id:
        return "You are the ticket opener; this command is for staff follow-ups."
    await channel.send(
        f"<@{owner_id}> {staff_member.mention} from the support team is requesting your attention.",
        allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False),
    )
    return f"Notified <@{owner_id}>."


async def assign_ticket(channel: discord.TextChannel, assignee: discord.Member) -> str:
    details = ticket_details(channel)
    if details is None:
        return "Use this command inside a ticket channel."
    owner_id, ticket_type = details
    if not is_ticket_staff(assignee, channel.guild, ticket_type):
        return "The assigned member must belong to this ticket's staff team."
    await ensure_ticket_tracking(channel, owner_id, ticket_type)
    state = get_ticket_state(channel.id)
    if state is None or state["closed"]:
        return "A closed ticket cannot be assigned."
    previous_id = state["claimed_by"]
    update_ticket_state(channel.id, claimed_by=assignee.id)
    record_ticket_staff_activity(channel.id, assignee, claimed=True)
    if previous_id and previous_id != assignee.id:
        return f"Ticket reassigned from <@{previous_id}> to {assignee.mention}."
    return f"Ticket assigned to {assignee.mention}."


async def unassign_ticket(channel: discord.TextChannel) -> str:
    details = ticket_details(channel)
    if details is None:
        return "Use this command inside a ticket channel."
    owner_id, ticket_type = details
    await ensure_ticket_tracking(channel, owner_id, ticket_type)
    state = get_ticket_state(channel.id)
    if state is None or state["closed"]:
        return "A closed ticket cannot be unassigned."
    if state["claimed_by"] is None:
        return "This ticket isn't assigned to anyone."
    previous_id = state["claimed_by"]
    update_ticket_state(channel.id, claimed_by=None)
    return f"Ticket unassigned from <@{previous_id}>."


async def transfer_ticket_owner(channel: discord.TextChannel, new_owner: discord.Member) -> str:
    details = ticket_details(channel)
    if details is None:
        return "Use this command inside a ticket channel."
    old_owner_id, ticket_type = details
    if new_owner.id == old_owner_id:
        return "That member is already the ticket opener."

    old_owner = await get_ticket_owner_member(channel.guild, old_owner_id)
    if old_owner is None:
        return "I couldn't find the current ticket opener."
    await set_ticket_member_access(channel, new_owner, True)
    await channel.edit(
        topic=f"ticket-owner={new_owner.id};ticket-type={ticket_type}",
        reason=f"Ticket ownership transferred by staff to {new_owner}",
    )
    update_ticket_state(channel.id, owner_id=new_owner.id)
    await set_ticket_member_access(channel, old_owner, False)
    return f"Ticket ownership transferred to {new_owner.mention}."


async def change_ticket_helper_role(
    channel: discord.TextChannel,
    role: discord.Role,
    allowed: bool,
) -> str:
    details = ticket_details(channel)
    if details is None:
        return "Use this command inside a ticket channel."
    protected_roles = set().union(*TICKET_STAFF_ROLE_IDS.values())
    if role.is_default() or role.id in protected_roles:
        return "Core ticket access roles can't be changed with this command."
    await channel.set_permissions(
        role,
        view_channel=allowed,
        send_messages=allowed,
        read_message_history=allowed,
        attach_files=allowed,
        embed_links=allowed,
    )
    action = "added to" if allowed else "removed from"
    return f"Role {role.mention} {action} this ticket."


async def deny_ticket_close_request(channel: discord.TextChannel, staff_member: discord.Member, reason: str) -> str:
    details = ticket_details(channel)
    if details is None:
        return "Use this command inside a ticket channel."
    owner_id, _ = details
    await ensure_ticket_tracking(channel, owner_id, ticket_details(channel)[1])
    state = get_ticket_state(channel.id)
    if state is None or not state["close_requested"]:
        return "There is no pending close request."
    update_ticket_state(channel.id, close_requested=0)
    message = f"<@{owner_id}> Your close request was declined by {staff_member.mention}."
    if reason.strip():
        message += f" Reason: {reason.strip()}"
    await channel.send(
        message,
        allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False),
    )
    return "Close request declined and the opener was notified."


async def reset_ticket_reminder(channel: discord.TextChannel) -> str:
    details = ticket_details(channel)
    if details is None:
        return "Use this command inside a ticket channel."
    owner_id, ticket_type = details
    await ensure_ticket_tracking(channel, owner_id, ticket_type)
    state = get_ticket_state(channel.id)
    if state is None or state["closed"]:
        return "A closed ticket's inactivity timer cannot be reset."
    if not state["reminders_enabled"]:
        return "Inactivity reminders are paused; start reminders before resetting the timer."
    update_ticket_state(channel.id, last_activity=utc_now().isoformat(), reminded_at=None)
    return "The inactivity timer was reset; a new reminder can be sent after six idle hours."


async def build_ticket_access_embed(channel: discord.TextChannel) -> discord.Embed | None:
    if ticket_details(channel) is None:
        return None
    users: list[str] = []
    roles: list[str] = []
    for target, overwrite in channel.overwrites.items():
        if overwrite.view_channel is not True:
            continue
        if isinstance(target, discord.Role):
            roles.append(target.mention)
        elif isinstance(target, discord.Member):
            users.append(target.mention)
    users_text = "\n".join(users) or "None"
    roles_text = "\n".join(roles) or "None"
    if len(users_text) > 1000:
        users_text = f"{users_text[:997]}..."
    if len(roles_text) > 1000:
        roles_text = f"{roles_text[:997]}..."
    embed = discord.Embed(title="Ticket Access", color=discord.Color.from_rgb(43, 128, 117))
    embed.add_field(name="Users", value=users_text, inline=True)
    embed.add_field(name="Roles", value=roles_text, inline=True)
    return embed


async def get_ticket_owner_member(guild: discord.Guild, owner_id: int) -> discord.Member | None:
    member = guild.get_member(owner_id)
    if member is not None:
        return member
    try:
        return await guild.fetch_member(owner_id)
    except discord.HTTPException:
        return None


async def set_ticket_reminders(
    channel: discord.TextChannel,
    owner_id: int,
    ticket_type: str,
    enabled: bool,
) -> None:
    await ensure_ticket_tracking(channel, owner_id, ticket_type)
    update_ticket_state(
        channel.id,
        reminders_enabled=int(enabled),
        last_activity=utc_now().isoformat(),
        reminded_at=None,
    )


async def close_ticket_channel(
    channel: discord.TextChannel,
    owner_id: int,
    closed_by: str,
    automatic: bool = False,
    before_delete: Callable[[bool], Awaitable[None]] | None = None,
) -> str:
    details = ticket_details(channel)
    if details is None:
        return "I couldn't identify the ticket type, so I left the channel in place."
    _, ticket_type = details

    archive_channel = bot.get_channel(TRANSCRIPT_CHANNEL_ID)
    if archive_channel is None:
        try:
            archive_channel = await bot.fetch_channel(TRANSCRIPT_CHANNEL_ID)
        except discord.HTTPException as error:
            return f"I couldn't access the transcript channel, so the ticket was not deleted: {error}"
    if not isinstance(archive_channel, discord.TextChannel):
        return "The transcript destination must be a text channel; the ticket was not deleted."

    try:
        transcript, claimed_staff, helped_staff = await build_ticket_transcript(
            channel,
            owner_id,
            ticket_type,
            closed_by,
        )
    except discord.HTTPException as error:
        return f"I couldn't export the ticket history, so the ticket was not deleted: {error}"

    claimed_text = format_staff_list(claimed_staff)
    helped_text = format_staff_list(helped_staff)
    archive_embed = discord.Embed(
        title=f"Ticket Transcript: {channel.name}",
        color=discord.Color.from_rgb(43, 128, 117),
        timestamp=utc_now(),
    )
    archive_embed.add_field(name="Ticket type", value=TICKET_TYPES[ticket_type]["label"], inline=True)
    archive_embed.add_field(name="Opened by", value=f"<@{owner_id}>", inline=True)
    archive_embed.add_field(name="Closed by", value=closed_by, inline=True)
    archive_embed.add_field(name="Claimed by", value=claimed_text, inline=False)
    archive_embed.add_field(name="Staff who helped", value=helped_text, inline=False)
    try:
        await archive_channel.send(
            embed=archive_embed,
            file=discord.File(BytesIO(transcript), filename=f"{channel.name}-transcript.txt"),
            allowed_mentions=discord.AllowedMentions.none(),
        )
    except discord.HTTPException as error:
        return f"I couldn't save the transcript, so the ticket was not deleted: {error}"

    create_ticket_survey(
        channel.id,
        channel.guild.id,
        owner_id,
        ticket_type,
        claimed_text,
        helped_text,
    )
    owner = bot.get_user(owner_id)
    if owner is None:
        try:
            owner = await bot.fetch_user(owner_id)
        except discord.HTTPException:
            owner = None

    dm_sent = False
    if owner is not None:
        rating_embed = discord.Embed(
            title="Rate Your Support",
            description=(
                "How was the help you received? Choose a star rating below.\n\n"
                "⭐ 1 is bad service; ⭐⭐⭐⭐⭐ 5 is the best."
            ),
            color=discord.Color.gold(),
        )
        try:
            await owner.send(
                content="Your ticket transcript is attached. Please rate your support below.",
                file=discord.File(BytesIO(transcript), filename=f"{channel.name}-transcript.txt"),
                embed=rating_embed,
                view=TicketRatingView(channel.id, owner_id),
            )
            dm_sent = True
        except discord.HTTPException as error:
            print(f"Couldn't DM transcript for ticket {channel.id}: {error}")

    if before_delete is not None:
        try:
            await before_delete(dm_sent)
        except discord.HTTPException as error:
            return f"Transcript was saved, but I couldn't confirm the close before deletion: {error}"

    try:
        await channel.delete(reason=f"Ticket closed by {closed_by}; transcript archived")
    except discord.HTTPException as error:
        return f"Transcript was saved, but I couldn't delete the ticket channel: {error}"

    try:
        update_ticket_state(
            channel.id,
            closed=1,
            reminders_enabled=0,
            reminded_at=None,
            close_requested=0,
            claimed_by=None,
        )
    except sqlite3.Error as error:
        print(f"Ticket {channel.id} was deleted, but its local state could not be updated: {error}")

    if dm_sent:
        return "Transcript archived and sent by DM; the ticket channel was deleted."
    return "Transcript archived and the ticket channel was deleted, but I couldn't DM the opener."


async def reopen_ticket_channel(
    channel: discord.TextChannel,
    owner_id: int,
    ticket_type: str,
) -> str:
    category = ticket_category(channel.guild, ticket_type)
    if category is None:
        return f"I couldn't find the configured category for {TICKET_TYPES[ticket_type]['label']}."
    owner = await get_ticket_owner_member(channel.guild, owner_id)
    if owner is None:
        return "I couldn't find the ticket opener. Check that Server Members Intent is enabled."

    await set_ticket_member_access(channel, owner, True)
    open_name = channel.name.removeprefix("closed-")
    await channel.edit(
        name=open_name,
        category=category,
        reason="Ticket reopened",
    )
    update_ticket_state(
        channel.id,
        closed=0,
        reminders_enabled=1,
        last_activity=utc_now().isoformat(),
        reminded_at=None,
        close_requested=0,
        claimed_by=None,
    )
    await channel.send("This ticket has been reopened. The inactivity reminder is enabled again.")
    return "Ticket reopened."


async def request_ticket_close(channel: discord.TextChannel, requester: discord.abc.User) -> str:
    details = ticket_details(channel)
    if details is None:
        return "Use this command inside a ticket channel."
    owner_id, ticket_type = details
    await ensure_ticket_tracking(channel, owner_id, ticket_type)
    state = get_ticket_state(channel.id)
    if state and state["closed"]:
        return "This ticket is already closed."
    if state and state["close_requested"]:
        return "A close request has already been sent to the team."

    update_ticket_state(channel.id, close_requested=1)
    team_mention = ticket_ping_mentions(channel.guild, ticket_type) or "the support team"
    await channel.send(f"{team_mention}: {requester.mention} requested that this ticket be closed.")
    return "Your close request has been sent to the support team."


async def configure_ticket_reminders(
    channel: discord.TextChannel,
    owner_id: int,
    ticket_type: str,
    enabled: bool,
) -> str:
    await ensure_ticket_tracking(channel, owner_id, ticket_type)
    state = get_ticket_state(channel.id)
    if state and state["closed"]:
        return "This ticket is closed. Reopen it before changing reminders."
    if state and bool(state["reminders_enabled"]) == enabled:
        return f"Inactivity reminders are already {'enabled' if enabled else 'paused'}."

    await set_ticket_reminders(channel, owner_id, ticket_type, enabled)
    if enabled:
        return "Inactivity reminders are enabled. The six-hour timer starts now."
    return "Inactivity reminders are paused. This ticket will not auto-close."


async def latest_human_activity(channel: discord.TextChannel) -> datetime | None:
    async for message in channel.history(limit=100):
        if not message.author.bot:
            return message.created_at
    return None


async def reconcile_ticket_activity() -> None:
    for guild in bot.guilds:
        for channel in guild.text_channels:
            details = ticket_details(channel)
            if details is None:
                continue
            owner_id, ticket_type = details
            await ensure_ticket_tracking(channel, owner_id, ticket_type)
            state = get_ticket_state(channel.id)
            latest_activity = await latest_human_activity(channel)
            if (
                state is not None
                and latest_activity is not None
                and latest_activity > datetime.fromisoformat(state["last_activity"])
            ):
                record_ticket_activity(channel.id, owner_id, ticket_type, latest_activity)


@tasks.loop(minutes=5)
async def ticket_inactivity_monitor() -> None:
    now = utc_now()
    for guild in bot.guilds:
        for channel in guild.text_channels:
            details = ticket_details(channel)
            if details is None:
                continue
            owner_id, ticket_type = details
            try:
                await ensure_ticket_tracking(channel, owner_id, ticket_type)
                state = get_ticket_state(channel.id)
                if state is None or state["closed"] or not state["reminders_enabled"]:
                    continue

                if state["reminded_at"] is None:
                    last_activity = datetime.fromisoformat(state["last_activity"])
                    if now - last_activity >= timedelta(hours=6):
                        await channel.send(
                            f"<@{owner_id}> This ticket has been inactive for 6 hours. "
                            "Please reply within 12 hours to keep it open."
                        )
                        update_ticket_state(channel.id, reminded_at=now.isoformat())
                    continue

                reminded_at = datetime.fromisoformat(state["reminded_at"])
                if now - reminded_at >= timedelta(hours=12):
                    await close_ticket_channel(channel, owner_id, "the inactivity reminder", automatic=True)
            except (discord.HTTPException, sqlite3.Error) as error:
                print(f"Ticket inactivity check failed for channel {channel.id}: {error}")


@ticket_inactivity_monitor.before_loop
async def before_ticket_inactivity_monitor() -> None:
    await bot.wait_until_ready()
    try:
        await reconcile_ticket_activity()
    except (discord.HTTPException, sqlite3.Error) as error:
        print(f"Could not reconcile ticket activity on startup: {error}")


async def fetch_bloxlink_roblox_profile(
    guild_id: int,
    discord_user_id: int,
) -> tuple[dict | None, str | None]:
    api_key = os.getenv("BLOXLINK_API_KEY")
    if not api_key:
        return None, "Roblox account lookup unavailable: `BLOXLINK_API_KEY` isn't configured."

    timeout = aiohttp.ClientTimeout(total=8)
    mapping_url = (
        f"https://api.blox.link/v4/public/guilds/{guild_id}"
        f"/discord-to-roblox/{discord_user_id}"
    )
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(mapping_url, headers={"Authorization": api_key}) as response:
                if response.status == 404:
                    return None, "No Roblox account is linked to this Discord account through Bloxlink."
                if response.status != 200:
                    return None, f"Bloxlink lookup unavailable (HTTP {response.status})."
                mapping = await response.json(content_type=None)

            roblox_id = mapping.get("robloxID") or mapping.get("robloxId") or mapping.get("roblox_id")
            if not roblox_id:
                return None, "No Roblox account is linked to this Discord account through Bloxlink."

            async with session.get(f"https://users.roblox.com/v1/users/{roblox_id}") as response:
                if response.status != 200:
                    return {"id": str(roblox_id)}, f"Roblox profile details unavailable (HTTP {response.status})."
                profile = await response.json(content_type=None)
                profile["id"] = str(roblox_id)
                return profile, None
    except (aiohttp.ClientError, TimeoutError, ValueError) as error:
        print(f"Bloxlink/Roblox profile lookup failed for Discord user {discord_user_id}: {error}")
        return None, "Roblox account lookup is temporarily unavailable."


async def open_ticket(interaction: discord.Interaction, ticket_type: str) -> None:
    guild = interaction.guild
    if guild is None:
        await interaction.followup.send("Tickets can only be opened in a server.", ephemeral=True)
        return

    category = ticket_category(guild, ticket_type)
    if category is None:
        await interaction.followup.send(
            f"I couldn't find the configured category for {TICKET_TYPES[ticket_type]['label']}.",
            ephemeral=True,
        )
        return

    staff_roles = ticket_staff_roles(guild, ticket_type)
    found_role_ids = {role.id for role in staff_roles}
    missing_role_ids = TICKET_STAFF_ROLE_IDS[ticket_type] - found_role_ids
    if missing_role_ids:
        missing_ids = ", ".join(str(role_id) for role_id in sorted(missing_role_ids))
        await interaction.followup.send(
            f"I couldn't find these staff role IDs in this server: `{missing_ids}`.",
            ephemeral=True,
        )
        return

    bot_member = guild.me
    if bot_member is None:
        await interaction.followup.send("I couldn't identify my server member account.", ephemeral=True)
        return

    requester = interaction.user
    safe_name = re.sub(r"[^a-z0-9]+", "-", requester.name.lower()).strip("-")[:20]
    channel_name = f"ticket-{ticket_type.replace('_', '-')}-{safe_name or requester.id}"
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        requester: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            attach_files=True,
            embed_links=True,
        ),
        bot_member: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            manage_channels=True,
        ),
    }
    staff_overwrite = discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            attach_files=True,
            embed_links=True,
    )
    for staff_role in staff_roles:
        overwrites[staff_role] = staff_overwrite
    topic = f"ticket-owner={requester.id};ticket-type={ticket_type}"

    channel = await guild.create_text_channel(
        channel_name,
        category=category,
        topic=topic,
        overwrites=overwrites,
        reason=f"{TICKET_TYPES[ticket_type]['label']} ticket opened by {requester}",
    )
    register_ticket(channel.id, requester.id, ticket_type)
    embed = discord.Embed(
        title=TICKET_TYPES[ticket_type]["label"],
        description=TICKET_TYPES[ticket_type]["welcome"],
        color=discord.Color.blurple(),
    )
    discord_created = int(requester.created_at.timestamp())
    embed.add_field(name="Discord account", value=requester.mention, inline=False)
    embed.add_field(name="Username", value=f"`{requester.name}`", inline=True)
    embed.add_field(name="Display name", value=requester.display_name, inline=True)
    embed.add_field(name="Discord ID", value=f"`{requester.id}`", inline=True)
    embed.add_field(
        name="Discord account created",
        value=f"<t:{discord_created}:D> (<t:{discord_created}:R>)",
        inline=True,
    )
    if isinstance(requester, discord.Member) and requester.joined_at is not None:
        joined_at = int(requester.joined_at.timestamp())
        embed.add_field(
            name="Joined this server",
            value=f"<t:{joined_at}:D> (<t:{joined_at}:R>)",
            inline=True,
        )

    roblox_profile, lookup_note = await fetch_bloxlink_roblox_profile(guild.id, requester.id)
    if roblox_profile is not None:
        roblox_id = str(roblox_profile.get("id", "Unknown"))
        username = roblox_profile.get("name", "Unknown")
        display_name = roblox_profile.get("displayName", username)
        embed.add_field(name="Roblox username", value=f"`{username}`", inline=True)
        embed.add_field(name="Roblox display name", value=display_name, inline=True)
        embed.add_field(name="Roblox ID", value=f"`{roblox_id}`", inline=True)
        embed.add_field(name="Roblox profile", value=f"https://www.roblox.com/users/{roblox_id}/profile", inline=False)

        created_value = roblox_profile.get("created")
        if created_value:
            try:
                roblox_created = datetime.fromisoformat(created_value.replace("Z", "+00:00"))
                age_days = max(0, (utc_now() - roblox_created).days)
                created_timestamp = int(roblox_created.timestamp())
                embed.add_field(
                    name="Roblox account age",
                    value=f"{age_days:,} days (created <t:{created_timestamp}:D>)",
                    inline=True,
                )
            except (TypeError, ValueError):
                pass

        description = roblox_profile.get("description", "").strip()
        if description:
            if len(description) > 900:
                description = f"{description[:897]}..."
            embed.add_field(name="Roblox profile description", value=description, inline=False)
        embed.add_field(
            name="Roblox verified badge",
            value="Yes" if roblox_profile.get("hasVerifiedBadge") else "No",
            inline=True,
        )
    elif lookup_note:
        embed.add_field(name="Roblox account", value=lookup_note, inline=False)

    embed.set_thumbnail(url=requester.display_avatar.url)
    mentions = ticket_ping_mentions(guild, ticket_type)
    await channel.send(
        content=f"{requester.mention} {mentions}".strip(),
        embed=embed,
        allowed_mentions=discord.AllowedMentions(users=True, roles=True),
    )
    await interaction.followup.send(f"Your ticket is ready: {channel.mention}", ephemeral=True)


class TicketTypeSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label=ticket["label"],
                value=key,
                description=ticket["select_description"],
            )
            for key, ticket in TICKET_TYPES.items()
        ]
        super().__init__(
            placeholder="Choose a ticket type...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="ticket-panel:type-select",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            await open_ticket(interaction, self.values[0])
        except discord.Forbidden:
            await interaction.followup.send(
                "I need Manage Channels, Manage Roles, and permission to send messages to create tickets.",
                ephemeral=True,
            )


class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketTypeSelect())


def format_staff_list(staff: list[tuple[int, str]]) -> str:
    return ", ".join(f"{name} (<@{user_id}>)" for user_id, name in staff) or "None recorded"


async def build_ticket_transcript(
    channel: discord.TextChannel,
    owner_id: int,
    ticket_type: str,
    closed_by: str,
) -> tuple[bytes, list[tuple[int, str]], list[tuple[int, str]]]:
    state = get_ticket_state(channel.id)
    if state and state["claimed_by"]:
        claimer = channel.guild.get_member(state["claimed_by"])
        if claimer is not None:
            record_ticket_staff_activity(channel.id, claimer, claimed=True)

    lines = [
        f"Ticket: {channel.name}",
        f"Type: {TICKET_TYPES[ticket_type]['label']}",
        f"Opened by: {owner_id}",
        f"Closed by: {closed_by}",
        f"Exported at: {utc_now().isoformat()}",
        "",
        "Messages:",
        "",
    ]
    async for message in channel.history(limit=None, oldest_first=True):
        if isinstance(message.author, discord.Member) and is_ticket_staff(
            message.author,
            channel.guild,
            ticket_type,
        ):
            record_ticket_staff_activity(channel.id, message.author, helped=True)

        author_name = getattr(message.author, "display_name", message.author.name)
        lines.append(f"[{message.created_at.isoformat()}] {author_name} ({message.author.id})")
        lines.append(message.content or "[no text content]")
        for attachment in message.attachments:
            lines.append(f"Attachment: {attachment.filename} - {attachment.url}")
        for embed in message.embeds:
            if embed.title or embed.description:
                lines.append(f"Embed: {embed.title or ''} {embed.description or ''}".strip())
        lines.append("")

    claimed_staff, helped_staff = get_ticket_staff_summary(channel.id)
    lines[5:8] = [
        f"Claimed by: {format_staff_list(claimed_staff)}",
        f"Staff who helped: {format_staff_list(helped_staff)}",
        "",
        "Messages:",
        "",
    ]
    transcript = "\n".join(lines).encode("utf-8")
    return transcript, claimed_staff, helped_staff


class TicketRatingButton(discord.ui.Button):
    def __init__(self, ticket_channel_id: int, owner_id: int, rating: int):
        super().__init__(
            label=f"{rating} star" if rating == 1 else f"{rating} stars",
            emoji="⭐",
            style=discord.ButtonStyle.secondary,
            custom_id=f"ticket-rating:{ticket_channel_id}:{rating}",
        )
        self.ticket_channel_id = ticket_channel_id
        self.owner_id = owner_id
        self.rating = rating

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Only the ticket opener can submit this rating.", ephemeral=True)
            return

        survey = record_ticket_rating(
            self.ticket_channel_id,
            self.owner_id,
            self.rating,
            interaction.user.id,
        )
        if survey is None:
            await interaction.response.send_message("This ticket has already been rated.", ephemeral=True)
            return

        await interaction.response.edit_message(
            content=f"Thank you for rating the service {self.rating} / 5 stars.",
            view=None,
        )
        rating_channel = bot.get_channel(SERVICE_RATING_CHANNEL_ID)
        if rating_channel is None:
            try:
                rating_channel = await bot.fetch_channel(SERVICE_RATING_CHANNEL_ID)
            except discord.HTTPException as error:
                print(f"Couldn't find the service-rating channel: {error}")
                return
        if not isinstance(rating_channel, discord.TextChannel):
            print("The service-rating destination must be a text channel.")
            return

        report = discord.Embed(
            title="Ticket Service Rating",
            description=f"**Score:** {'⭐' * self.rating} ({self.rating}/5)",
            color=discord.Color.gold(),
            timestamp=utc_now(),
        )
        report.add_field(name="Voted by", value=f"{interaction.user.mention} ({interaction.user})", inline=False)
        report.add_field(name="Ticket type", value=TICKET_TYPES[survey["ticket_type"]]["label"], inline=True)
        report.add_field(name="Ticket ID", value=str(self.ticket_channel_id), inline=True)
        report.add_field(name="Claimed by", value=survey["claimed_staff"], inline=False)
        report.add_field(name="Staff who helped", value=survey["helped_staff"], inline=False)
        try:
            await rating_channel.send(
                embed=report,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.HTTPException as error:
            print(f"Couldn't post service rating for ticket {self.ticket_channel_id}: {error}")


class TicketRatingView(discord.ui.View):
    def __init__(self, ticket_channel_id: int, owner_id: int):
        super().__init__(timeout=None)
        for rating in range(1, 6):
            self.add_item(TicketRatingButton(ticket_channel_id, owner_id, rating))


def build_session_embed(guild: discord.Guild, state: dict) -> discord.Embed:
    status = state["status"]
    if status == "Online":
        color = discord.Color.green()
        status_text = "🟢 Online"
    elif status == "Low Population":
        color = discord.Color.orange()
        status_text = "🟠 Low Population"
    elif status == "Full":
        color = discord.Color.orange()
        status_text = "🟠 Full"
    else:
        color = discord.Color.red()
        status_text = "🔴 Offline"

    embed = discord.Embed(
        title="Session Information",
        description=(
            "This channel contains server session updates, including startups, shutdowns, and other announcements.\n\n"
            "To be notified when a session starts, assign yourself the **SSU Ping** role below. "
            "Do not join the server until an official startup announcement has been posted."
        ),
        color=color,
    )
    embed.set_author(name="Arkansas State Roleplay")
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)

    ping_role = discord.utils.get(guild.roles, name="SSU Ping")
    try:
        last_updated = datetime.fromisoformat(state["last_update"].replace("Z", "+00:00"))
        last_update_text = f"<t:{int(last_updated.timestamp())}:R>"
    except (TypeError, ValueError):
        last_update_text = f"`{state['last_update']}`"
    embed.add_field(
        name="Session Times",
        value=(
            "```text\n"
            f"Weekdays: {state['weekday_times']}\n"
            f"Weekends: {state['weekend_times']}\n"
            "```"
        ),
        inline=False,
    )
    embed.add_field(name="Session Pings", value=ping_role.mention if ping_role else "SSU Ping role not found", inline=False)
    embed.add_field(name="JOIN CODE", value=f"`{state['join_code']}`", inline=True)
    embed.add_field(name="LIVE PLAYERS", value=f"`{state['live_players']}`", inline=True)
    embed.add_field(name="JOIN QUEUE", value=f"`{state['queue_count']}`", inline=True)
    embed.add_field(
        name="API STATUS",
        value=f"`{state['api_status']}`\nLast updated: {last_update_text}",
        inline=True,
    )
    embed.add_field(name="SERVER STATUS", value=f"`{status_text}`", inline=True)
    embed.set_footer(text="Arkansas State Roleplay • Session status")
    return embed


def build_session_event_embed(guild: discord.Guild, title: str, description: str) -> discord.Embed:
    state = get_session_state(guild.id)
    embed = discord.Embed(
        title=f"Arkansas State Roleplay | {title}",
        description=description,
        color=discord.Color.from_rgb(232, 74, 95),
        timestamp=utc_now(),
    )
    embed.add_field(name="JOIN CODE", value=f"`{state['join_code']}`", inline=True)
    embed.add_field(name="SERVER STATUS", value=state["status"], inline=True)
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    embed.set_footer(text="Arkansas State Roleplay")
    return embed


async def update_session_panel(guild: discord.Guild) -> None:
    state = get_session_state(guild.id)
    if not state["channel_id"] or not state["message_id"]:
        return
    channel = bot.get_channel(state["channel_id"])
    if not isinstance(channel, discord.TextChannel):
        return
    try:
        message = await channel.fetch_message(state["message_id"])
        await message.edit(embed=build_session_embed(guild, state), view=SessionPingView())
    except discord.HTTPException as error:
        print(f"Couldn't update the session panel in guild {guild.id}: {error}")


def parse_erlc_session_data(data: dict) -> tuple[int, int, int, str | None]:
    current_players = data.get("CurrentPlayers")
    max_players = data.get("MaxPlayers")
    queue = data.get("Queue")
    join_key = data.get("JoinKey")
    if (
        isinstance(current_players, bool)
        or not isinstance(current_players, int)
        or isinstance(max_players, bool)
        or not isinstance(max_players, int)
        or not isinstance(queue, list)
    ):
        raise ValueError("ER:LC response is missing valid CurrentPlayers, MaxPlayers, or Queue fields")
    return current_players, max_players, len(queue), join_key if isinstance(join_key, str) and join_key else None


def update_erlc_poll_state(guild_id: int, *, players: str, queue: str, join_code: str | None, api_status: str) -> None:
    values: dict[str, str] = {
        "live_players": players,
        "queue_count": queue,
        "api_status": api_status,
        "last_update": utc_now().isoformat(),
    }
    if join_code is not None:
        values["join_code"] = join_code
    update_session_state(guild_id, **values)


@tasks.loop(seconds=60)
async def erlc_session_counter_monitor() -> None:
    global ERLC_RETRY_AFTER, ERLC_POLLING_DISABLED

    if ERLC_POLLING_DISABLED or time.monotonic() < ERLC_RETRY_AFTER:
        return

    server_key = os.getenv("ERLC_SERVER_KEY")
    if not server_key:
        for guild in bot.guilds:
            state = get_session_state(guild.id)
            if state["api_status"] != "Waiting for ER:LC API key":
                update_session_state(guild.id, api_status="Waiting for ER:LC API key")
                await update_session_panel(guild)
        return

    timeout = aiohttp.ClientTimeout(total=10)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                ERLC_API_URL,
                headers={"server-key": server_key},
                params={"Players": "true", "Queue": "true"},
            ) as response:
                if response.status == 429:
                    retry_after = float(response.headers.get("Retry-After", "60"))
                    ERLC_RETRY_AFTER = time.monotonic() + max(retry_after, 1.0)
                    for guild in bot.guilds:
                        update_session_state(guild.id, api_status=f"Rate limited; retrying in {int(retry_after)}s")
                        await update_session_panel(guild)
                    return
                if response.status in (401, 403):
                    ERLC_POLLING_DISABLED = True
                    for guild in bot.guilds:
                        update_session_state(guild.id, api_status="Unauthorized; check ERLC_SERVER_KEY")
                        await update_session_panel(guild)
                    print("ER:LC API rejected ERLC_SERVER_KEY; polling disabled to avoid repeated invalid requests.")
                    return
                if response.status != 200:
                    raise aiohttp.ClientResponseError(
                        response.request_info,
                        response.history,
                        status=response.status,
                        message="ER:LC status request failed",
                        headers=response.headers,
                    )
                data = await response.json(content_type=None)

        current_players, max_players, queue_count, join_key = parse_erlc_session_data(data)
        for guild in bot.guilds:
            update_erlc_poll_state(
                guild.id,
                players=f"{current_players} / {max_players}",
                queue=str(queue_count),
                join_code=join_key,
                api_status="Connected",
            )
            await update_session_panel(guild)
    except (aiohttp.ClientError, TimeoutError, ValueError, TypeError) as error:
        print(f"ER:LC session status poll failed: {error}")
        for guild in bot.guilds:
            update_session_state(guild.id, api_status="Connection error")
            await update_session_panel(guild)


@erlc_session_counter_monitor.before_loop
async def before_erlc_session_counter_monitor() -> None:
    await bot.wait_until_ready()


async def publish_session_startup(channel: discord.TextChannel, guild: discord.Guild) -> None:
    update_session_state(guild.id, status="Online", last_update=utc_now().isoformat())
    ping_role = discord.utils.get(guild.roles, name="SSU Ping")
    role_mention = ping_role.mention if ping_role else ""
    allowed_roles = [ping_role] if ping_role else False
    await channel.send(
        content=f"@here {role_mention} **Official session startup!** Join only after this announcement.".strip(),
        embed=build_session_event_embed(guild, "Session Startup", SESSION_DESCRIPTIONS["startup"]),
        allowed_mentions=discord.AllowedMentions(everyone=True, roles=allowed_roles),
    )
    await update_session_panel(guild)


class SessionPingButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Session Ping",
            emoji="🔔",
            style=discord.ButtonStyle.secondary,
            custom_id="session-ping:toggle",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.defer()
            return
        role = discord.utils.get(interaction.guild.roles, name="SSU Ping")
        if role is None:
            print("Session Ping button used, but the SSU Ping role was not found.")
            await interaction.response.defer()
            return
        try:
            await interaction.response.defer()
            if role in interaction.user.roles:
                await interaction.user.remove_roles(role, reason="Session ping role self-service")
            else:
                await interaction.user.add_roles(role, reason="Session ping role self-service")
        except discord.Forbidden:
            print("Couldn't toggle SSU Ping; the bot needs Manage Roles and a role above SSU Ping.")


class SessionPingView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(SessionPingButton())


def build_session_vote_embed(guild: discord.Guild, required_votes: int, vote_count: int) -> discord.Embed:
    embed = discord.Embed(
        title="Arkansas State Roleplay | Session Vote",
        description=SESSION_DESCRIPTIONS["vote"],
        color=discord.Color.from_rgb(232, 74, 95),
    )
    embed.add_field(name="Votes", value=f"**{vote_count} / {required_votes}**", inline=True)
    embed.add_field(name="Join code", value=f"`{get_session_state(guild.id)['join_code']}`", inline=True)
    embed.set_footer(text="Each server member can vote once")
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    return embed


class SessionVoteButton(discord.ui.Button):
    def __init__(self, guild_id: int):
        super().__init__(
            label="Vote for Session",
            emoji="✅",
            style=discord.ButtonStyle.success,
            custom_id=f"session-vote:cast:{guild_id}",
        )
        self.guild_id = guild_id

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.guild_id != self.guild_id:
            await interaction.response.defer()
            return
        vote = get_session_vote(self.guild_id)
        if vote is None:
            await interaction.response.defer()
            return
        inserted, count = cast_session_vote(self.guild_id, interaction.user.id)
        if not inserted:
            await interaction.response.defer()
            return
        if count < vote["required_votes"]:
            await interaction.response.edit_message(
                embed=build_session_vote_embed(interaction.guild, vote["required_votes"], count),
                view=SessionVoteView(self.guild_id),
            )
            return
        if not claim_session_vote_start(self.guild_id):
            await interaction.response.defer()
            return

        await interaction.response.defer()
        channel = bot.get_channel(vote["channel_id"])
        if not isinstance(channel, discord.TextChannel):
            reset_session_vote_starting(self.guild_id)
            return
        try:
            await publish_session_startup(channel, interaction.guild)
        except discord.HTTPException as error:
            print(f"Couldn't post vote-approved session startup in guild {self.guild_id}: {error}")
            reset_session_vote_starting(self.guild_id)
            return

        clear_session_vote(self.guild_id)
        try:
            await interaction.message.delete()
        except discord.HTTPException as error:
            print(f"Couldn't delete completed session vote message: {error}")


class SessionVoteView(discord.ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.add_item(SessionVoteButton(guild_id))


def build_department_panel_embed(guild: discord.Guild) -> discord.Embed:
    embed = discord.Embed(
        title="Whitelisted Departments | Information",
        description=DEPARTMENT_OVERVIEW,
        color=discord.Color.from_rgb(43, 128, 117),
    )
    embed.set_author(name="Arkansas State Roleplay")
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    embed.add_field(
        name="To claim or open a department",
        value=(
            f"Open a Management ticket in <#{DEPARTMENT_MANAGEMENT_CHANNEL_ID}>.\n"
            f"Channel ID: `{DEPARTMENT_MANAGEMENT_CHANNEL_ID}`"
        ),
        inline=False,
    )
    embed.set_footer(text=DEPARTMENT_FOOTER)
    return embed


def build_staff_application_embed(guild: discord.Guild) -> discord.Embed:
    embed = discord.Embed(
        title="Arkansas State Roleplay | Staff Applications",
        description=(
            "Welcome to the official Staff Applications page for Arkansas State Roleplay. We are always looking for dedicated, mature, and responsible individuals who are interested in helping manage our community and ensuring that all members have a positive and enjoyable roleplay experience. Our staff team plays an important role in maintaining order, enforcing community regulations, assisting members, and ensuring that sessions operate smoothly and professionally.\n\n"
            "Individuals interested in joining the staff team must complete the official staff application and provide honest, accurate, and detailed responses to all required questions. Applicants should demonstrate professionalism, strong communication skills, good judgment, activity, and a willingness to work alongside other staff members. Previous staffing experience may be beneficial, but applicants are expected to understand that being a staff member requires responsibility, patience, fairness, and dedication to the community.\n\n"
            "**📋 STAFF REQUIREMENTS**\n"
            "Applicants must have a good understanding of the server rules and community guidelines, maintain a respectful attitude toward all members, demonstrate maturity when handling difficult situations, and be willing to dedicate time to staff responsibilities. Applicants must also be able to follow instructions from higher-ranking staff members, communicate effectively, remain unbiased when handling reports, and use staff permissions appropriately. Abusing administrative commands, showing favoritism, leaking confidential staff information, or using staff privileges for personal benefit will not be tolerated.\n\n"
            "**📝 APPLICATION PROCESS**\n"
            "To begin the application process, submit your application through the designated application system and answer each question to the best of your ability. Once submitted, your application will be reviewed by the appropriate members of the management team. Depending on the circumstances, applicants may be contacted for an interview, additional questions, or further evaluation before a final decision is made. Please remain patient while your application is being reviewed, as processing times may vary depending on application volume and staff availability.\n\n"
            "**⚠️ IMPORTANT INFORMATION**\n"
            "Submitting an application does not guarantee acceptance into the staff team. All applications are reviewed based on the applicant's responses, qualifications, conduct, and overall suitability for the position. Providing false information, copying another person's application, repeatedly contacting staff about an application decision, or attempting to influence the review process may result in the application being denied. Applicants are expected to remain respectful regardless of the outcome.\n\n"
            "We appreciate your interest in becoming part of the Arkansas State Roleplay staff team. By applying, you are expressing your willingness to help support the community, assist its members, enforce its regulations fairly, and contribute to the continued growth and success of the server."
        ),
        color=discord.Color.from_rgb(43, 128, 117),
    )
    embed.set_author(name="Arkansas State Roleplay")
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    embed.set_footer(text=DEPARTMENT_FOOTER)
    return embed


def build_server_information_embed(guild: discord.Guild) -> discord.Embed:
    session = get_session_state(guild.id)
    embed = discord.Embed(
        title="Arkansas State Roleplay | Server Information",
        description=(
            "Welcome to **Arkansas State Roleplay (ARSRP)**, a Roblox ER:LC roleplay community focused on organized sessions, realistic scenarios, and a professional, welcoming experience. "
            "Use this guide to find session details, departments, applications, and support."
        ),
        color=discord.Color.from_rgb(43, 128, 117),
    )
    embed.set_author(name="Arkansas State Roleplay")
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)

    embed.add_field(
        name="📡 Current Session",
        value=(
            f"Status: `{session['status']}`\n"
            f"Join code: `{session['join_code']}`\n"
            f"Players: `{session['live_players']}`\n"
            f"Queue: `{session['queue_count']}`\n"
            f"Status feed: `{session['api_status']}`"
        ),
        inline=True,
    )
    embed.add_field(
        name="🕒 Session Schedule",
        value=(
            f"Weekdays: {session['weekday_times']}\n"
            f"Weekends: {session['weekend_times']}\n\n"
            "Wait for an official startup announcement before joining a session."
        ),
        inline=True,
    )
    embed.add_field(
        name="🏛️ Whitelisted Departments",
        value=(
            "• Arkansas Federal Bureau of Investigation\n"
            "• Arkansas State Police\n"
            "• Pulaski County Sheriff's Office *(coming soon)*\n\n"
            "Whitelisted departments require an application, qualifications, and approval. Acceptance is not guaranteed."
        ),
        inline=False,
    )
    embed.add_field(
        name="🚓 Other Departments",
        value=(
            "• Little Rock Police Department\n"
            "• Little Rock Fire Department\n"
            "• Little Rock DOT *(coming soon)*\n\n"
            "Use the department information panel to view available invitations and current details."
        ),
        inline=False,
    )
    embed.add_field(
        name="📝 Applications",
        value=(
            f"Staff applications: [Open the official application]({STAFF_APPLICATION_URL})\n"
            f"Department applications and access: open a Management ticket in <#{DEPARTMENT_MANAGEMENT_CHANNEL_ID}>."
        ),
        inline=False,
    )
    embed.add_field(
        name="🎫 Support",
        value=(
            "Open a ticket through the support panel and choose the team that best fits your request:\n"
            "• General Support: questions, access, or server help\n"
            "• Internal Affairs: confidential conduct or policy concerns\n"
            "• Management: leadership matters, approvals, or unresolved issues"
        ),
        inline=False,
    )
    embed.add_field(
        name="📖 Community Expectations",
        value=(
            "Keep roleplay realistic and cooperative, follow server and departmental rules, respect staff instructions and the chain of command, and treat other members professionally. "
            "Exploiting, trolling, disruptive behavior, or abusing department or staff privileges may lead to moderation action."
        ),
        inline=False,
    )
    embed.set_footer(text=DEPARTMENT_FOOTER)
    return embed


class StaffApplicationView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(
            discord.ui.Button(
                label="Open here",
                style=discord.ButtonStyle.link,
                url=STAFF_APPLICATION_URL,
            )
        )


class DepartmentSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label=department["name"],
                value=key,
                emoji=department["emoji"],
            )
            for key, department in DEPARTMENT_INVITES.items()
        ]
        super().__init__(
            placeholder="Choose a department to receive its invitation...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="department-panel:select",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        department = DEPARTMENT_INVITES[self.values[0]]
        invite = department["invite"]
        dm_embed = discord.Embed(
            title=f"{department['name']} | Department Invitation",
            color=discord.Color.from_rgb(43, 128, 117),
        )
        if invite:
            dm_embed.description = (
                f"Thank you for your interest in **{department['name']}** within Arkansas State Roleplay.\n\n"
                "Use the invitation below to visit the department's Discord server. Please review its requirements and follow the application and onboarding instructions provided by its leadership. "
                "Joining the department server or submitting an application does not guarantee acceptance."
            )
            dm_embed.add_field(name="Department", value=department["category"], inline=True)
            dm_embed.add_field(name="Invitation", value=f"[Join {department['name']}]({invite})", inline=False)
        else:
            dm_embed.description = (
                f"Thank you for your interest in **{department['name']}** within Arkansas State Roleplay.\n\n"
                "The department invitation is not available yet. Please watch the official Arkansas State Roleplay announcements for updates."
            )
            dm_embed.add_field(name="Status", value="Coming soon", inline=True)
        dm_embed.set_footer(text=DEPARTMENT_FOOTER)

        try:
            await interaction.user.send(embed=dm_embed, allowed_mentions=discord.AllowedMentions.none())
        except discord.Forbidden:
            await interaction.response.send_message(
                "I couldn't DM the department information. Enable direct messages from server members and try again.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            f"I sent the {department['name']} information to your DMs.",
            ephemeral=True,
        )


class DepartmentPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(DepartmentSelect())


class TicketBot(commands.Bot):
    async def setup_hook(self) -> None:
        self.add_view(TicketPanelView())
        self.add_view(SessionPingView())
        self.add_view(DepartmentPanelView())
        await self.tree.sync()
        for channel_id, owner_id in get_pending_ticket_surveys():
            self.add_view(TicketRatingView(channel_id, owner_id))
        recover_session_votes()
        for vote in get_active_session_votes():
            self.add_view(SessionVoteView(vote["guild_id"]), message_id=vote["message_id"])
        ticket_inactivity_monitor.start()
        erlc_session_counter_monitor.start()

    async def on_ready(self) -> None:
        print(f"Logged in as {self.user}")
        for guild in self.guilds:
            for channel in guild.text_channels:
                details = ticket_details(channel)
                if details is None:
                    continue
                _, ticket_type = details
                try:
                    await apply_ticket_staff_permissions(channel, guild, ticket_type)
                except discord.HTTPException as error:
                    print(f"Couldn't sync staff access for ticket {channel.id}: {error}")

    async def on_message(self, message: discord.Message) -> None:
        if not message.author.bot and isinstance(message.channel, discord.TextChannel):
            details = ticket_details(message.channel)
            if details is not None:
                owner_id, ticket_type = details
                record_ticket_activity(
                    message.channel.id,
                    owner_id,
                    ticket_type,
                    message.created_at,
                )
                if isinstance(message.author, discord.Member) and is_ticket_staff(
                    message.author,
                    message.guild,
                    ticket_type,
                ):
                    record_ticket_staff_activity(message.channel.id, message.author, helped=True)
        await self.process_commands(message)

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.CommandNotFound):
            return
        if isinstance(error, commands.MissingPermissions):
            permissions = ", ".join(permission.replace("_", " ") for permission in error.missing_permissions)
            message = f"You need these permissions: {permissions}."
        elif isinstance(error, commands.BotMissingPermissions):
            permissions = ", ".join(permission.replace("_", " ") for permission in error.missing_permissions)
            message = f"I need these permissions: {permissions}."
        elif isinstance(error, commands.MissingRequiredArgument):
            message = f"Missing required argument: `{error.param.name}`."
        elif isinstance(error, commands.BadArgument):
            message = "I couldn't understand one of the command arguments. Check the command and try again."
        else:
            print(f"Prefix command failed: {error}")
            message = "The command failed. Check the arguments and bot permissions."
        try:
            await ctx.send(message, ephemeral=ctx.interaction is not None)
        except discord.HTTPException as send_error:
            print(f"Couldn't send command error: {send_error}")


intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = TicketBot(command_prefix=commands.when_mentioned_or("!"), intents=intents)


@bot.tree.command(name="ticket-panel", description="Post the support ticket menu here.")
@app_commands.guild_only()
@app_commands.checks.has_permissions(manage_guild=True)
async def ticket_panel(interaction: discord.Interaction) -> None:
    await interaction.response.send_message(embed=build_ticket_panel_embed(), view=TicketPanelView())


@bot.command(name="ticket-panel")
@commands.guild_only()
@commands.has_guild_permissions(manage_guild=True)
async def ticket_panel_prefix(ctx: commands.Context) -> None:
    await ctx.send(embed=build_ticket_panel_embed(), view=TicketPanelView())


@bot.tree.command(name="ticket-escalate", description="Change this ticket to another support team.")
@app_commands.guild_only()
@app_commands.choices(
    ticket_type=[
        app_commands.Choice(name=ticket["label"], value=key)
        for key, ticket in TICKET_TYPES.items()
    ]
)
async def ticket_escalate(
    interaction: discord.Interaction,
    ticket_type: app_commands.Choice[str],
) -> None:
    details = ticket_details(interaction.channel)
    if details is None:
        await interaction.response.send_message("Use this command inside a ticket channel.", ephemeral=True)
        return

    owner_id, current_type = details
    if not can_manage_ticket(interaction.user, interaction.guild, owner_id, current_type):
        await interaction.response.send_message("You don't have permission to manage this ticket.", ephemeral=True)
        return
    if ticket_type.value == current_type:
        await interaction.response.send_message("This ticket is already assigned to that team.", ephemeral=True)
        return

    guild = interaction.guild
    if guild is None:
        return
    channel = interaction.channel
    assert isinstance(channel, discord.TextChannel)
    result = await change_ticket_type(channel, guild, owner_id, current_type, ticket_type.value)
    await interaction.response.send_message(result)


@bot.command(name="ticket-escalate")
@commands.guild_only()
async def ticket_escalate_prefix(ctx: commands.Context, *, ticket_type: str) -> None:
    details = ticket_details(ctx.channel)
    new_type = resolve_ticket_type(ticket_type)
    if details is None:
        await ctx.send("Use this command inside a ticket channel.")
        return
    if new_type is None:
        await ctx.send("Choose General Support, Internal Affairs, or Management.")
        return

    owner_id, current_type = details
    if not can_manage_ticket(ctx.author, ctx.guild, owner_id, current_type):
        await ctx.send("You don't have permission to manage this ticket.")
        return
    if new_type == current_type:
        await ctx.send("This ticket is already assigned to that team.")
        return

    channel = ctx.channel
    assert isinstance(channel, discord.TextChannel)
    result = await change_ticket_type(channel, ctx.guild, owner_id, current_type, new_type)
    await ctx.send(result)


@bot.tree.command(name="ticket-add", description="Give a member access to this ticket.")
@app_commands.guild_only()
async def ticket_add(interaction: discord.Interaction, member: discord.Member) -> None:
    details = ticket_details(interaction.channel)
    if details is None:
        await interaction.response.send_message("Use this command inside a ticket channel.", ephemeral=True)
        return
    owner_id, ticket_type = details
    if not can_manage_ticket(interaction.user, interaction.guild, owner_id, ticket_type):
        await interaction.response.send_message("You don't have permission to manage this ticket.", ephemeral=True)
        return
    channel = interaction.channel
    assert isinstance(channel, discord.TextChannel)
    await set_ticket_member_access(channel, member, True)
    await interaction.response.send_message(f"Added {member.mention} to this ticket.")


@bot.command(name="ticket-add")
@commands.guild_only()
async def ticket_add_prefix(ctx: commands.Context, member: discord.Member) -> None:
    details = ticket_details(ctx.channel)
    if details is None:
        await ctx.send("Use this command inside a ticket channel.")
        return
    owner_id, ticket_type = details
    if not can_manage_ticket(ctx.author, ctx.guild, owner_id, ticket_type):
        await ctx.send("You don't have permission to manage this ticket.")
        return
    channel = ctx.channel
    assert isinstance(channel, discord.TextChannel)
    await set_ticket_member_access(channel, member, True)
    await ctx.send(f"Added {member.mention} to this ticket.")


@bot.tree.command(name="ticket-remove", description="Remove a member's access to this ticket.")
@app_commands.guild_only()
async def ticket_remove(interaction: discord.Interaction, member: discord.Member) -> None:
    details = ticket_details(interaction.channel)
    if details is None:
        await interaction.response.send_message("Use this command inside a ticket channel.", ephemeral=True)
        return
    owner_id, ticket_type = details
    if member.id == owner_id:
        await interaction.response.send_message("The ticket opener can't be removed from their own ticket.", ephemeral=True)
        return
    if not can_manage_ticket(interaction.user, interaction.guild, owner_id, ticket_type):
        await interaction.response.send_message("You don't have permission to manage this ticket.", ephemeral=True)
        return
    channel = interaction.channel
    assert isinstance(channel, discord.TextChannel)
    await set_ticket_member_access(channel, member, False)
    await interaction.response.send_message(f"Removed {member.mention} from this ticket.")


@bot.command(name="ticket-remove")
@commands.guild_only()
async def ticket_remove_prefix(ctx: commands.Context, member: discord.Member) -> None:
    details = ticket_details(ctx.channel)
    if details is None:
        await ctx.send("Use this command inside a ticket channel.")
        return
    owner_id, ticket_type = details
    if member.id == owner_id:
        await ctx.send("The ticket opener can't be removed from their own ticket.")
        return
    if not can_manage_ticket(ctx.author, ctx.guild, owner_id, ticket_type):
        await ctx.send("You don't have permission to manage this ticket.")
        return
    channel = ctx.channel
    assert isinstance(channel, discord.TextChannel)
    await set_ticket_member_access(channel, member, False)
    await ctx.send(f"Removed {member.mention} from this ticket.")


@bot.tree.command(name="ticket-close-request", description="Ask the support team to close this ticket.")
@app_commands.guild_only()
async def ticket_close_request(interaction: discord.Interaction) -> None:
    details = ticket_details(interaction.channel)
    if details is None:
        await interaction.response.send_message("Use this command inside a ticket channel.", ephemeral=True)
        return
    owner_id, ticket_type = details
    if not can_manage_ticket(interaction.user, interaction.guild, owner_id, ticket_type):
        await interaction.response.send_message("You don't have permission to request changes to this ticket.", ephemeral=True)
        return
    channel = interaction.channel
    assert isinstance(channel, discord.TextChannel)
    result = await request_ticket_close(channel, interaction.user)
    await interaction.response.send_message(result, ephemeral=True)


@bot.command(name="ticket-close-request")
@commands.guild_only()
async def ticket_close_request_prefix(ctx: commands.Context) -> None:
    details = ticket_details(ctx.channel)
    if details is None:
        await ctx.send("Use this command inside a ticket channel.")
        return
    owner_id, ticket_type = details
    if not can_manage_ticket(ctx.author, ctx.guild, owner_id, ticket_type):
        await ctx.send("You don't have permission to request changes to this ticket.")
        return
    channel = ctx.channel
    assert isinstance(channel, discord.TextChannel)
    await ctx.send(await request_ticket_close(channel, ctx.author))


@bot.tree.command(name="ticket-close", description="Close this ticket and make it read-only for its opener.")
@app_commands.guild_only()
async def ticket_close(interaction: discord.Interaction) -> None:
    details = ticket_details(interaction.channel)
    if details is None:
        await interaction.response.send_message("Use this command inside a ticket channel.", ephemeral=True)
        return
    owner_id, ticket_type = details
    guild = interaction.guild
    if guild is None or not is_ticket_staff(interaction.user, guild, ticket_type):
        await interaction.response.send_message("Only the assigned team or a channel manager can close a ticket.", ephemeral=True)
        return
    channel = interaction.channel
    assert isinstance(channel, discord.TextChannel)
    await ensure_ticket_tracking(channel, owner_id, ticket_type)
    state = get_ticket_state(channel.id)
    if state and state["closed"]:
        await interaction.response.send_message("This ticket is already closed.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True, thinking=True)

    async def acknowledge_before_delete(dm_sent: bool) -> None:
        delivery = "The transcript was DM'd to the opener." if dm_sent else "The opener's DM could not be delivered."
        await interaction.edit_original_response(
            content=f"Transcript archived. {delivery} Deleting the ticket channel now."
        )

    result = await close_ticket_channel(
        channel,
        owner_id,
        interaction.user.mention,
        before_delete=acknowledge_before_delete,
    )
    if not result.startswith("Transcript archived"):
        try:
            await interaction.edit_original_response(content=result)
        except discord.HTTPException as error:
            print(f"Couldn't report ticket close result for {channel.id}: {error}")


@bot.command(name="ticket-close")
@commands.guild_only()
async def ticket_close_prefix(ctx: commands.Context) -> None:
    details = ticket_details(ctx.channel)
    if details is None:
        await ctx.send("Use this command inside a ticket channel.")
        return
    owner_id, ticket_type = details
    if not is_ticket_staff(ctx.author, ctx.guild, ticket_type):
        await ctx.send("Only the assigned team or a channel manager can close a ticket.")
        return
    channel = ctx.channel
    assert isinstance(channel, discord.TextChannel)
    await ensure_ticket_tracking(channel, owner_id, ticket_type)
    state = get_ticket_state(channel.id)
    if state and state["closed"]:
        await ctx.send("This ticket is already closed.")
        return
    await ctx.send("Preparing transcript and closing this ticket...")
    result = await close_ticket_channel(channel, owner_id, ctx.author.mention)
    if "was not deleted" in result or "couldn't delete" in result:
        await ctx.send(result)


@bot.tree.command(name="ticket-reopen", description="Reopen a closed ticket and restart inactivity reminders.")
@app_commands.guild_only()
async def ticket_reopen(interaction: discord.Interaction) -> None:
    details = ticket_details(interaction.channel)
    if details is None:
        await interaction.response.send_message("Use this command inside a ticket channel.", ephemeral=True)
        return
    owner_id, ticket_type = details
    if not can_manage_ticket(interaction.user, interaction.guild, owner_id, ticket_type):
        await interaction.response.send_message("You don't have permission to reopen this ticket.", ephemeral=True)
        return
    channel = interaction.channel
    assert isinstance(channel, discord.TextChannel)
    await ensure_ticket_tracking(channel, owner_id, ticket_type)
    state = get_ticket_state(channel.id)
    if state is None or not state["closed"]:
        await interaction.response.send_message("This ticket is not closed.", ephemeral=True)
        return
    await interaction.response.send_message(
        await reopen_ticket_channel(channel, owner_id, ticket_type),
        ephemeral=True,
    )


@bot.command(name="ticket-reopen")
@commands.guild_only()
async def ticket_reopen_prefix(ctx: commands.Context) -> None:
    details = ticket_details(ctx.channel)
    if details is None:
        await ctx.send("Use this command inside a ticket channel.")
        return
    owner_id, ticket_type = details
    if not can_manage_ticket(ctx.author, ctx.guild, owner_id, ticket_type):
        await ctx.send("You don't have permission to reopen this ticket.")
        return
    channel = ctx.channel
    assert isinstance(channel, discord.TextChannel)
    await ensure_ticket_tracking(channel, owner_id, ticket_type)
    state = get_ticket_state(channel.id)
    if state is None or not state["closed"]:
        await ctx.send("This ticket is not closed.")
        return
    await ctx.send(await reopen_ticket_channel(channel, owner_id, ticket_type))


@bot.tree.command(name="ticket-reminder-stop", description="Pause automatic inactivity reminders for this ticket.")
@app_commands.guild_only()
async def ticket_reminder_stop(interaction: discord.Interaction) -> None:
    details = ticket_details(interaction.channel)
    if details is None:
        await interaction.response.send_message("Use this command inside a ticket channel.", ephemeral=True)
        return
    owner_id, ticket_type = details
    if not can_manage_ticket(interaction.user, interaction.guild, owner_id, ticket_type):
        await interaction.response.send_message("You don't have permission to change this ticket's reminders.", ephemeral=True)
        return
    channel = interaction.channel
    assert isinstance(channel, discord.TextChannel)
    await interaction.response.send_message(
        await configure_ticket_reminders(channel, owner_id, ticket_type, False),
        ephemeral=True,
    )


@bot.command(name="ticket-reminder-stop")
@commands.guild_only()
async def ticket_reminder_stop_prefix(ctx: commands.Context) -> None:
    details = ticket_details(ctx.channel)
    if details is None:
        await ctx.send("Use this command inside a ticket channel.")
        return
    owner_id, ticket_type = details
    if not can_manage_ticket(ctx.author, ctx.guild, owner_id, ticket_type):
        await ctx.send("You don't have permission to change this ticket's reminders.")
        return
    channel = ctx.channel
    assert isinstance(channel, discord.TextChannel)
    await ctx.send(await configure_ticket_reminders(channel, owner_id, ticket_type, False))


@bot.tree.command(name="ticket-reminder-start", description="Resume inactivity reminders for this ticket.")
@app_commands.guild_only()
async def ticket_reminder_start(interaction: discord.Interaction) -> None:
    details = ticket_details(interaction.channel)
    if details is None:
        await interaction.response.send_message("Use this command inside a ticket channel.", ephemeral=True)
        return
    owner_id, ticket_type = details
    if not can_manage_ticket(interaction.user, interaction.guild, owner_id, ticket_type):
        await interaction.response.send_message("You don't have permission to change this ticket's reminders.", ephemeral=True)
        return
    channel = interaction.channel
    assert isinstance(channel, discord.TextChannel)
    await interaction.response.send_message(
        await configure_ticket_reminders(channel, owner_id, ticket_type, True),
        ephemeral=True,
    )


@bot.command(name="ticket-reminder-start")
@commands.guild_only()
async def ticket_reminder_start_prefix(ctx: commands.Context) -> None:
    details = ticket_details(ctx.channel)
    if details is None:
        await ctx.send("Use this command inside a ticket channel.")
        return
    owner_id, ticket_type = details
    if not can_manage_ticket(ctx.author, ctx.guild, owner_id, ticket_type):
        await ctx.send("You don't have permission to change this ticket's reminders.")
        return
    channel = ctx.channel
    assert isinstance(channel, discord.TextChannel)
    await ctx.send(await configure_ticket_reminders(channel, owner_id, ticket_type, True))


@bot.tree.command(name="ticket-claim", description="Claim this ticket for yourself.")
@app_commands.guild_only()
async def ticket_claim(interaction: discord.Interaction) -> None:
    details = ticket_details(interaction.channel)
    guild = interaction.guild
    if details is None or guild is None:
        await interaction.response.send_message("Use this command inside a ticket channel.", ephemeral=True)
        return
    _, ticket_type = details
    if not is_ticket_staff(interaction.user, guild, ticket_type):
        await interaction.response.send_message("Only the assigned team or a channel manager can claim tickets.", ephemeral=True)
        return
    channel = interaction.channel
    assert isinstance(channel, discord.TextChannel)
    await interaction.response.send_message(await claim_ticket(channel, interaction.user))


@bot.command(name="ticket-claim")
@commands.guild_only()
async def ticket_claim_prefix(ctx: commands.Context) -> None:
    details = ticket_details(ctx.channel)
    if details is None or ctx.guild is None:
        await ctx.send("Use this command inside a ticket channel.")
        return
    _, ticket_type = details
    if not is_ticket_staff(ctx.author, ctx.guild, ticket_type):
        await ctx.send("Only the assigned team or a channel manager can claim tickets.")
        return
    channel = ctx.channel
    assert isinstance(channel, discord.TextChannel)
    await ctx.send(await claim_ticket(channel, ctx.author))


@bot.tree.command(name="ticket-unclaim", description="Release your claim on this ticket.")
@app_commands.guild_only()
async def ticket_unclaim(interaction: discord.Interaction) -> None:
    details = ticket_details(interaction.channel)
    guild = interaction.guild
    if details is None or guild is None:
        await interaction.response.send_message("Use this command inside a ticket channel.", ephemeral=True)
        return
    _, ticket_type = details
    if not is_ticket_staff(interaction.user, guild, ticket_type):
        await interaction.response.send_message("Only the assigned team or a channel manager can unclaim tickets.", ephemeral=True)
        return
    channel = interaction.channel
    assert isinstance(channel, discord.TextChannel)
    await interaction.response.send_message(await unclaim_ticket(channel, interaction.user))


@bot.command(name="ticket-unclaim")
@commands.guild_only()
async def ticket_unclaim_prefix(ctx: commands.Context) -> None:
    details = ticket_details(ctx.channel)
    if details is None or ctx.guild is None:
        await ctx.send("Use this command inside a ticket channel.")
        return
    _, ticket_type = details
    if not is_ticket_staff(ctx.author, ctx.guild, ticket_type):
        await ctx.send("Only the assigned team or a channel manager can unclaim tickets.")
        return
    channel = ctx.channel
    assert isinstance(channel, discord.TextChannel)
    await ctx.send(await unclaim_ticket(channel, ctx.author))


@bot.tree.command(name="ticket-info", description="Show the status and activity for this ticket.")
@app_commands.guild_only()
async def ticket_info(interaction: discord.Interaction) -> None:
    channel = interaction.channel
    if not isinstance(channel, discord.TextChannel):
        await interaction.response.send_message("Use this command inside a ticket channel.", ephemeral=True)
        return
    embed = await get_ticket_status_embed(channel)
    if embed is None:
        await interaction.response.send_message("Use this command inside a ticket channel.", ephemeral=True)
        return
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.command(name="ticket-info")
@commands.guild_only()
async def ticket_info_prefix(ctx: commands.Context) -> None:
    channel = ctx.channel
    if not isinstance(channel, discord.TextChannel):
        await ctx.send("Use this command inside a ticket channel.")
        return
    embed = await get_ticket_status_embed(channel)
    if embed is None:
        await ctx.send("Use this command inside a ticket channel.")
        return
    await ctx.send(embed=embed)


@bot.tree.command(name="ticket-priority", description="Set this ticket's priority.")
@app_commands.guild_only()
@app_commands.choices(
    priority=[
        app_commands.Choice(name=level, value=level.lower())
        for level in ("Low", "Normal", "High", "Urgent")
    ]
)
async def ticket_priority(
    interaction: discord.Interaction,
    priority: app_commands.Choice[str],
) -> None:
    details = ticket_details(interaction.channel)
    guild = interaction.guild
    if details is None or guild is None:
        await interaction.response.send_message("Use this command inside a ticket channel.", ephemeral=True)
        return
    _, ticket_type = details
    if not is_ticket_staff(interaction.user, guild, ticket_type):
        await interaction.response.send_message("Only the assigned team or a channel manager can set priority.", ephemeral=True)
        return
    channel = interaction.channel
    assert isinstance(channel, discord.TextChannel)
    await interaction.response.send_message(
        await set_ticket_priority(channel, priority.value),
        ephemeral=True,
    )


@bot.command(name="ticket-priority")
@commands.guild_only()
async def ticket_priority_prefix(ctx: commands.Context, priority: str) -> None:
    details = ticket_details(ctx.channel)
    if details is None or ctx.guild is None:
        await ctx.send("Use this command inside a ticket channel.")
        return
    _, ticket_type = details
    if not is_ticket_staff(ctx.author, ctx.guild, ticket_type):
        await ctx.send("Only the assigned team or a channel manager can set priority.")
        return
    channel = ctx.channel
    assert isinstance(channel, discord.TextChannel)
    await ctx.send(await set_ticket_priority(channel, priority))


@bot.tree.command(name="ticket-ping-owner", description="Notify the ticket opener that staff need their attention.")
@app_commands.guild_only()
async def ticket_ping_owner(interaction: discord.Interaction) -> None:
    details = ticket_details(interaction.channel)
    guild = interaction.guild
    if details is None or guild is None:
        await interaction.response.send_message("Use this command inside a ticket channel.", ephemeral=True)
        return
    _, ticket_type = details
    if not is_ticket_staff(interaction.user, guild, ticket_type):
        await interaction.response.send_message("Only the assigned team or a channel manager can ping the opener.", ephemeral=True)
        return
    channel = interaction.channel
    assert isinstance(channel, discord.TextChannel)
    await interaction.response.send_message(await ping_ticket_owner(channel, interaction.user), ephemeral=True)


@bot.command(name="ticket-ping-owner")
@commands.guild_only()
async def ticket_ping_owner_prefix(ctx: commands.Context) -> None:
    details = ticket_details(ctx.channel)
    if details is None or ctx.guild is None:
        await ctx.send("Use this command inside a ticket channel.")
        return
    _, ticket_type = details
    if not is_ticket_staff(ctx.author, ctx.guild, ticket_type):
        await ctx.send("Only the assigned team or a channel manager can ping the opener.")
        return
    channel = ctx.channel
    assert isinstance(channel, discord.TextChannel)
    await ctx.send(await ping_ticket_owner(channel, ctx.author))


@bot.tree.command(name="ticket-rename", description="Rename this ticket channel.")
@app_commands.guild_only()
async def ticket_rename(interaction: discord.Interaction, new_name: str) -> None:
    details = ticket_details(interaction.channel)
    guild = interaction.guild
    if details is None or guild is None:
        await interaction.response.send_message("Use this command inside a ticket channel.", ephemeral=True)
        return
    _, ticket_type = details
    if not is_ticket_staff(interaction.user, guild, ticket_type):
        await interaction.response.send_message("Only the assigned team or a channel manager can rename tickets.", ephemeral=True)
        return
    channel = interaction.channel
    assert isinstance(channel, discord.TextChannel)
    await interaction.response.send_message(await rename_ticket(channel, new_name), ephemeral=True)


@bot.command(name="ticket-rename")
@commands.guild_only()
async def ticket_rename_prefix(ctx: commands.Context, *, new_name: str) -> None:
    details = ticket_details(ctx.channel)
    if details is None or ctx.guild is None:
        await ctx.send("Use this command inside a ticket channel.")
        return
    _, ticket_type = details
    if not is_ticket_staff(ctx.author, ctx.guild, ticket_type):
        await ctx.send("Only the assigned team or a channel manager can rename tickets.")
        return
    channel = ctx.channel
    assert isinstance(channel, discord.TextChannel)
    await ctx.send(await rename_ticket(channel, new_name))


def partition_purge_messages(
    messages: list[discord.Message],
    now: datetime | None = None,
) -> tuple[list[discord.Message], int]:
    cutoff = (now or utc_now()) - timedelta(days=14)
    deletable = [message for message in messages if message.created_at >= cutoff]
    return deletable, len(messages) - len(deletable)


@bot.hybrid_command(name="purge", description="Bulk-delete up to 100 messages less than 14 days old.")
@app_commands.describe(amount="Number of recent messages to delete (1-100)")
@commands.guild_only()
@commands.has_permissions(manage_messages=True)
@commands.bot_has_permissions(manage_messages=True)
async def purge_messages(ctx: commands.Context, amount: int) -> None:
    if not 1 <= amount <= 100:
        await ctx.send("Choose an amount from 1 to 100.", ephemeral=ctx.interaction is not None)
        return
    if not isinstance(ctx.channel, discord.TextChannel):
        await ctx.send("This command only works in text channels.", ephemeral=ctx.interaction is not None)
        return
    if ctx.interaction is not None:
        await ctx.defer(ephemeral=True)
    recent_messages: list[discord.Message] = []
    async for message in ctx.channel.history(limit=amount):
        recent_messages.append(message)
    deletable, skipped_old = partition_purge_messages(recent_messages)
    if deletable:
        await ctx.channel.delete_messages(
            deletable,
            reason=f"Message cleanup requested by {ctx.author}",
        )
    result = f"Deleted {len(deletable)} recent message(s)."
    if skipped_old:
        result += f" Skipped {skipped_old} message(s) older than 14 days to avoid individual-delete rate limits."
    await ctx.send(
        result,
        ephemeral=ctx.interaction is not None,
        delete_after=8 if ctx.interaction is None else None,
    )


@bot.hybrid_command(name="slowmode", description="Set this channel's slowmode in seconds.")
@app_commands.describe(seconds="Slowmode delay from 0 to 21600 seconds")
@commands.guild_only()
@commands.has_permissions(manage_channels=True)
@commands.bot_has_permissions(manage_channels=True)
async def set_slowmode(ctx: commands.Context, seconds: int) -> None:
    if not 0 <= seconds <= 21600:
        await ctx.send("Slowmode must be between 0 and 21600 seconds.", ephemeral=ctx.interaction is not None)
        return
    if not isinstance(ctx.channel, discord.TextChannel):
        await ctx.send("This command only works in text channels.", ephemeral=ctx.interaction is not None)
        return
    await ctx.channel.edit(slowmode_delay=seconds, reason=f"Slowmode changed by {ctx.author}")
    result = "Slowmode is off." if seconds == 0 else f"Slowmode set to {seconds} second(s)."
    await ctx.send(result, ephemeral=ctx.interaction is not None)


@bot.hybrid_command(name="lock", description="Stop regular members from sending messages in this channel.")
@commands.guild_only()
@commands.has_permissions(manage_channels=True)
@commands.bot_has_permissions(manage_channels=True)
async def lock_channel(ctx: commands.Context) -> None:
    if not isinstance(ctx.channel, discord.TextChannel):
        await ctx.send("This command only works in text channels.", ephemeral=ctx.interaction is not None)
        return
    await ctx.channel.set_permissions(
        ctx.guild.default_role,
        send_messages=False,
        send_messages_in_threads=False,
        reason=f"Channel locked by {ctx.author}",
    )
    await ctx.send("Channel locked for members who don't have an explicit channel override.")


@bot.hybrid_command(name="unlock", description="Restore this channel's inherited send permissions.")
@commands.guild_only()
@commands.has_permissions(manage_channels=True)
@commands.bot_has_permissions(manage_channels=True)
async def unlock_channel(ctx: commands.Context) -> None:
    if not isinstance(ctx.channel, discord.TextChannel):
        await ctx.send("This command only works in text channels.", ephemeral=ctx.interaction is not None)
        return
    await ctx.channel.set_permissions(
        ctx.guild.default_role,
        send_messages=None,
        send_messages_in_threads=None,
        reason=f"Channel unlocked by {ctx.author}",
    )
    await ctx.send("Channel send permissions now inherit from its category.")


async def clear_session_command_acknowledgement(ctx: commands.Context) -> None:
    if ctx.interaction is not None:
        try:
            await ctx.interaction.delete_original_response()
        except discord.NotFound:
            pass


@bot.hybrid_command(name="department-panel", description="Post the whitelisted and non-whitelisted department directory.")
@commands.guild_only()
@commands.has_guild_permissions(manage_guild=True)
async def department_panel(ctx: commands.Context) -> None:
    if not isinstance(ctx.channel, discord.TextChannel):
        await ctx.send("Post the department panel in a text channel.")
        return
    await ctx.send(embed=build_department_panel_embed(ctx.guild), view=DepartmentPanelView())


@bot.hybrid_command(name="server-info", description="Post the Arkansas State Roleplay information panel.")
@commands.guild_only()
@commands.has_guild_permissions(manage_guild=True)
async def server_info_panel(ctx: commands.Context) -> None:
    if not isinstance(ctx.channel, discord.TextChannel):
        await ctx.send("Post the server information panel in a text channel.")
        return
    await ctx.send(embed=build_server_information_embed(ctx.guild))


@bot.hybrid_command(name="staff-application-panel", description="Post the Arkansas State Roleplay staff application panel.")
@commands.guild_only()
@commands.has_guild_permissions(manage_guild=True)
async def staff_application_panel(ctx: commands.Context) -> None:
    if not isinstance(ctx.channel, discord.TextChannel):
        await ctx.send("Post the staff application panel in a text channel.")
        return
    await ctx.send(embed=build_staff_application_embed(ctx.guild), view=StaffApplicationView())


@bot.hybrid_command(name="session-embed", description="Post or replace the session status panel here.")
@app_commands.describe(join_code="Roblox private server join code")
@commands.guild_only()
@commands.has_guild_permissions(manage_guild=True)
async def session_embed(ctx: commands.Context, join_code: str = "ARSRPP") -> None:
    if not isinstance(ctx.channel, discord.TextChannel):
        await ctx.send("Post the session panel in a text channel.", ephemeral=False)
        return
    join_code = join_code.strip()
    if not join_code or len(join_code) > 100:
        await ctx.send("Join code must be between 1 and 100 characters.", ephemeral=False)
        return
    if ctx.interaction is not None:
        await ctx.defer()

    state = get_session_state(ctx.guild.id)
    update_session_state(ctx.guild.id, join_code=join_code)
    state["join_code"] = join_code
    existing_message = None
    if state["channel_id"] and state["message_id"]:
        existing_channel = bot.get_channel(state["channel_id"])
        if isinstance(existing_channel, discord.TextChannel):
            try:
                existing_message = await existing_channel.fetch_message(state["message_id"])
            except discord.NotFound:
                existing_message = None

    if existing_message is not None and existing_channel.id == ctx.channel.id:
        await existing_message.edit(embed=build_session_embed(ctx.guild, state), view=SessionPingView())
        await clear_session_command_acknowledgement(ctx)
        return

    message = await ctx.send(embed=build_session_embed(ctx.guild, state), view=SessionPingView())
    update_session_state(ctx.guild.id, channel_id=ctx.channel.id, message_id=message.id)


@bot.hybrid_command(name="session-startup", description="Post the official session startup and notify SSU pings.")
@commands.guild_only()
@commands.has_guild_permissions(manage_guild=True)
async def session_startup(ctx: commands.Context) -> None:
    if not isinstance(ctx.channel, discord.TextChannel):
        await ctx.send("Post session announcements in a text channel.", ephemeral=False)
        return
    if ctx.interaction is not None:
        await ctx.defer()
    await publish_session_startup(ctx.channel, ctx.guild)
    await clear_session_command_acknowledgement(ctx)


@bot.hybrid_command(name="session-shutdown", description="Mark the session offline and update the panel without an announcement.")
@commands.guild_only()
@commands.has_guild_permissions(manage_guild=True)
async def session_shutdown(ctx: commands.Context) -> None:
    if not isinstance(ctx.channel, discord.TextChannel):
        await ctx.send("Post session announcements in a text channel.", ephemeral=False)
        return
    if ctx.interaction is not None:
        await ctx.defer()
    update_session_state(
        ctx.guild.id,
        status="Offline",
        last_update=utc_now().isoformat(),
    )
    await ctx.channel.send(
        embed=build_session_event_embed(ctx.guild, "Session Shutdown", SESSION_DESCRIPTIONS["shutdown"]),
    )
    await update_session_panel(ctx.guild)
    await clear_session_command_acknowledgement(ctx)


@bot.hybrid_command(name="session-low", description="Mark the session as low population and post a notice.")
@commands.guild_only()
@commands.has_guild_permissions(manage_guild=True)
async def session_low(ctx: commands.Context, *, note: str = "") -> None:
    if not isinstance(ctx.channel, discord.TextChannel):
        await ctx.send("Post session announcements in a text channel.", ephemeral=False)
        return
    if ctx.interaction is not None:
        await ctx.defer()
    update_session_state(
        ctx.guild.id,
        status="Low Population",
        last_update=utc_now().isoformat(),
    )
    description = SESSION_DESCRIPTIONS["low"]
    if note.strip():
        description = f"{description}\n\n{note.strip()[:1000]}"
    await ctx.channel.send(embed=build_session_event_embed(ctx.guild, "Low Population", description))
    await update_session_panel(ctx.guild)
    await clear_session_command_acknowledgement(ctx)


@bot.hybrid_command(name="session-full", description="Mark the server full and post a capacity notice.")
@commands.guild_only()
@commands.has_guild_permissions(manage_guild=True)
async def session_full(ctx: commands.Context, *, note: str = "") -> None:
    if not isinstance(ctx.channel, discord.TextChannel):
        await ctx.send("Post session announcements in a text channel.", ephemeral=False)
        return
    if ctx.interaction is not None:
        await ctx.defer()
    update_session_state(
        ctx.guild.id,
        status="Full",
        last_update=utc_now().isoformat(),
    )
    description = SESSION_DESCRIPTIONS["full"]
    if note.strip():
        description = f"{description}\n\n{note.strip()[:1000]}"
    await ctx.channel.send(embed=build_session_event_embed(ctx.guild, "Session Full", description))
    await update_session_panel(ctx.guild)
    await clear_session_command_acknowledgement(ctx)


@bot.hybrid_command(name="session-vote", description="Start a vote with a required number of votes for startup.")
@app_commands.describe(required_votes="Unique votes required before startup is announced")
@commands.guild_only()
@commands.has_guild_permissions(manage_guild=True)
async def session_vote(ctx: commands.Context, required_votes: int) -> None:
    if not isinstance(ctx.channel, discord.TextChannel):
        await ctx.send("Start a session vote in a text channel.", ephemeral=False)
        return
    if not 1 <= required_votes <= 500:
        await ctx.send("Required votes must be between 1 and 500.", ephemeral=False)
        return
    state = get_session_state(ctx.guild.id)
    if state["status"] == "Online":
        await ctx.send("The session is already marked online.", ephemeral=False)
        return
    current_vote = get_session_vote(ctx.guild.id)
    if current_vote is not None:
        await ctx.send("A session vote is already active in this server.", ephemeral=False)
        return
    if ctx.interaction is not None:
        await ctx.defer()

    message = await ctx.channel.send(
        embed=build_session_vote_embed(ctx.guild, required_votes, 0),
        view=SessionVoteView(ctx.guild.id),
    )
    create_session_vote(ctx.guild.id, ctx.channel.id, message.id, required_votes, ctx.author.id)
    await clear_session_command_acknowledgement(ctx)


@bot.hybrid_command(name="session-counts", description="Manually update the live player and join-queue counters.")
@app_commands.describe(players="Current live player count", queue="Current join queue count")
@commands.guild_only()
@commands.has_guild_permissions(manage_guild=True)
async def session_counts(ctx: commands.Context, players: int, queue: int) -> None:
    if not 0 <= players <= 100000 or not 0 <= queue <= 100000:
        await ctx.send("Player and queue counts must be between 0 and 100000.", ephemeral=False)
        return
    if ctx.interaction is not None:
        await ctx.defer()
    update_session_state(
        ctx.guild.id,
        live_players=str(players),
        queue_count=str(queue),
        api_status="Manual update",
        last_update=utc_now().isoformat(),
    )
    await update_session_panel(ctx.guild)
    await clear_session_command_acknowledgement(ctx)


@bot.hybrid_command(name="session-join-code", description="Change the join code shown on the session panel.")
@app_commands.describe(code="New server join code")
@commands.guild_only()
@commands.has_guild_permissions(manage_guild=True)
async def session_join_code(ctx: commands.Context, *, code: str) -> None:
    code = code.strip()
    if not code or len(code) > 100:
        await ctx.send("Join code must be between 1 and 100 characters.", ephemeral=False)
        return
    if ctx.interaction is not None:
        await ctx.defer()
    update_session_state(ctx.guild.id, join_code=code)
    await update_session_panel(ctx.guild)
    await clear_session_command_acknowledgement(ctx)


@bot.hybrid_command(name="session-times", description="Set weekday and weekend session schedules.")
@app_commands.describe(weekday_times="Displayed weekday session schedule", weekend_times="Displayed weekend schedule")
@commands.guild_only()
@commands.has_guild_permissions(manage_guild=True)
async def session_times(ctx: commands.Context, weekday_times: str, *, weekend_times: str) -> None:
    weekday_times = weekday_times.strip()
    weekend_times = weekend_times.strip()
    if not weekday_times or not weekend_times or len(weekday_times) > 100 or len(weekend_times) > 100:
        await ctx.send("Both schedules are required and must be 100 characters or fewer.", ephemeral=False)
        return
    if ctx.interaction is not None:
        await ctx.defer()
    update_session_state(
        ctx.guild.id,
        weekday_times=weekday_times,
        weekend_times=weekend_times,
    )
    await update_session_panel(ctx.guild)
    await clear_session_command_acknowledgement(ctx)


@bot.hybrid_command(name="session-vote-status", description="Show the active startup vote and its progress.")
@commands.guild_only()
@commands.has_guild_permissions(manage_guild=True)
async def session_vote_status(ctx: commands.Context) -> None:
    vote = get_session_vote(ctx.guild.id)
    if vote is None:
        await ctx.send("There is no active session vote.", ephemeral=False)
        return
    count = get_session_vote_count(ctx.guild.id)
    embed = build_session_vote_embed(ctx.guild, vote["required_votes"], count)
    embed.add_field(name="Started by", value=f"<@{vote['starter_id']}>", inline=True)
    embed.add_field(name="Vote channel", value=f"<#{vote['channel_id']}>", inline=True)
    await ctx.send(embed=embed, ephemeral=False)


@bot.hybrid_command(name="session-vote-cancel", description="Cancel the active startup vote.")
@commands.guild_only()
@commands.has_guild_permissions(manage_guild=True)
async def session_vote_cancel(ctx: commands.Context) -> None:
    vote = get_session_vote(ctx.guild.id)
    if vote is None:
        await ctx.send("There is no active session vote.", ephemeral=False)
        return
    if ctx.interaction is not None:
        await ctx.defer()
    channel = bot.get_channel(vote["channel_id"])
    if isinstance(channel, discord.TextChannel):
        try:
            message = await channel.fetch_message(vote["message_id"])
            await message.delete()
        except discord.HTTPException:
            pass
    clear_session_vote(ctx.guild.id)
    await clear_session_command_acknowledgement(ctx)


@bot.hybrid_command(name="session-notice", description="Post a custom session announcement embed.")
@app_commands.describe(title="Short notice heading", message="Announcement text")
@commands.guild_only()
@commands.has_guild_permissions(manage_guild=True)
async def session_notice(ctx: commands.Context, title: str, *, message: str) -> None:
    title = title.strip()
    message = message.strip()
    if not title or len(title) > 200 or not message or len(message) > 3500:
        await ctx.send("Provide a title up to 200 characters and a message up to 3500 characters.", ephemeral=False)
        return
    embed = build_session_event_embed(ctx.guild, title, message)
    await ctx.send(embed=embed)


@bot.hybrid_command(name="announce", description="Post an announcement in this channel.")
@commands.guild_only()
@commands.has_guild_permissions(manage_guild=True)
@commands.bot_has_permissions(send_messages=True, embed_links=True)
async def announce(ctx: commands.Context, *, message: str) -> None:
    announcement = message.strip()
    if not announcement or len(announcement) > 4000:
        await ctx.send("Announcement text must be between 1 and 4000 characters.", ephemeral=ctx.interaction is not None)
        return
    embed = discord.Embed(
        title="Server Announcement",
        description=announcement,
        color=discord.Color.from_rgb(43, 128, 117),
        timestamp=utc_now(),
    )
    embed.set_footer(text=f"Posted by {ctx.author.display_name}")
    await ctx.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())


@bot.hybrid_command(name="warn", description="Issue and log a warning for a server member.")
@app_commands.describe(member="Member to warn", reason="Reason for the warning")
@commands.guild_only()
@commands.has_permissions(moderate_members=True)
async def warn_member(ctx: commands.Context, member: discord.Member, *, reason: str) -> None:
    reason = reason.strip()
    if not reason:
        await ctx.send("A warning reason is required.", ephemeral=ctx.interaction is not None)
        return
    if len(reason) > 1000:
        await ctx.send("Keep warning reasons under 1000 characters.", ephemeral=ctx.interaction is not None)
        return
    warning_id = add_server_warning(ctx.guild.id, member, ctx.author, reason)
    warning_embed = discord.Embed(
        title="Server Warning",
        description=reason,
        color=discord.Color.orange(),
        timestamp=utc_now(),
    )
    warning_embed.add_field(name="Warning ID", value=str(warning_id), inline=True)
    warning_embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
    try:
        await member.send(embed=warning_embed)
        dm_status = "The member was sent a DM."
    except discord.HTTPException:
        dm_status = "The warning was logged, but the member's DMs could not be delivered."
    await ctx.send(f"Warning #{warning_id} logged for {member.mention}. {dm_status}", ephemeral=ctx.interaction is not None)


@bot.hybrid_command(name="warnings", description="View a member's five most recent server warnings.")
@commands.guild_only()
@commands.has_permissions(moderate_members=True)
async def list_warnings(ctx: commands.Context, member: discord.Member) -> None:
    warnings = get_server_warnings(ctx.guild.id, member.id)
    embed = discord.Embed(
        title=f"Warnings: {member.display_name}",
        color=discord.Color.orange(),
    )
    if not warnings:
        embed.description = "No warnings are recorded for this member."
    else:
        for warning in warnings:
            reason = warning["reason"]
            if len(reason) > 800:
                reason = f"{reason[:797]}..."
            embed.add_field(
                name=f"Warning #{warning['warning_id']} | <t:{int(datetime.fromisoformat(warning['created_at']).timestamp())}:R>",
                value=f"{reason}\nModerator: <@{warning['moderator_id']}>",
                inline=False,
            )
    await ctx.send(embed=embed, ephemeral=ctx.interaction is not None)


@bot.hybrid_command(name="clear-warnings", description="Clear all logged warnings for a member.")
@commands.guild_only()
@commands.has_guild_permissions(manage_guild=True)
async def clear_member_warnings(ctx: commands.Context, member: discord.Member) -> None:
    deleted = clear_server_warnings(ctx.guild.id, member.id)
    await ctx.send(f"Cleared {deleted} warning(s) for {member.mention}.", ephemeral=ctx.interaction is not None)


@bot.hybrid_command(name="ticket-assign", description="Assign this ticket to a staff member.")
@app_commands.describe(member="Staff member taking responsibility for this ticket")
@commands.guild_only()
async def ticket_assign(ctx: commands.Context, member: discord.Member) -> None:
    channel = ctx.channel
    details = ticket_details(channel)
    if details is None or not isinstance(channel, discord.TextChannel):
        await ctx.send("Use this command inside a ticket channel.", ephemeral=ctx.interaction is not None)
        return
    _, ticket_type = details
    if not is_ticket_staff(ctx.author, channel.guild, ticket_type):
        await ctx.send("Only the assigned team or a channel manager can assign tickets.", ephemeral=ctx.interaction is not None)
        return
    await ctx.send(await assign_ticket(channel, member), ephemeral=ctx.interaction is not None)


@bot.hybrid_command(name="ticket-unassign", description="Remove the current staff assignment from this ticket.")
@commands.guild_only()
async def ticket_unassign(ctx: commands.Context) -> None:
    channel = ctx.channel
    details = ticket_details(channel)
    if details is None or not isinstance(channel, discord.TextChannel):
        await ctx.send("Use this command inside a ticket channel.", ephemeral=ctx.interaction is not None)
        return
    _, ticket_type = details
    if not is_ticket_staff(ctx.author, channel.guild, ticket_type):
        await ctx.send("Only the assigned team or a channel manager can unassign tickets.", ephemeral=ctx.interaction is not None)
        return
    await ctx.send(await unassign_ticket(channel), ephemeral=ctx.interaction is not None)


@bot.hybrid_command(name="ticket-transfer-owner", description="Transfer this ticket to a different opener.")
@app_commands.describe(member="The new ticket opener")
@commands.guild_only()
async def ticket_transfer_owner(ctx: commands.Context, member: discord.Member) -> None:
    channel = ctx.channel
    details = ticket_details(channel)
    if details is None or not isinstance(channel, discord.TextChannel):
        await ctx.send("Use this command inside a ticket channel.", ephemeral=ctx.interaction is not None)
        return
    _, ticket_type = details
    if not is_ticket_staff(ctx.author, channel.guild, ticket_type):
        await ctx.send("Only the assigned team or a channel manager can transfer ticket ownership.", ephemeral=ctx.interaction is not None)
        return
    await ctx.send(await transfer_ticket_owner(channel, member), ephemeral=ctx.interaction is not None)


@bot.hybrid_command(name="ticket-add-role", description="Give a helper role access to this ticket.")
@app_commands.describe(role="Role to give ticket access")
@commands.guild_only()
async def ticket_add_role(ctx: commands.Context, role: discord.Role) -> None:
    channel = ctx.channel
    details = ticket_details(channel)
    if details is None or not isinstance(channel, discord.TextChannel):
        await ctx.send("Use this command inside a ticket channel.", ephemeral=ctx.interaction is not None)
        return
    _, ticket_type = details
    if not is_ticket_staff(ctx.author, channel.guild, ticket_type):
        await ctx.send("Only the assigned team or a channel manager can change ticket roles.", ephemeral=ctx.interaction is not None)
        return
    await ctx.send(await change_ticket_helper_role(channel, role, True), ephemeral=ctx.interaction is not None)


@bot.hybrid_command(name="ticket-remove-role", description="Remove a helper role's access to this ticket.")
@app_commands.describe(role="Role to remove from this ticket")
@commands.guild_only()
async def ticket_remove_role(ctx: commands.Context, role: discord.Role) -> None:
    channel = ctx.channel
    details = ticket_details(channel)
    if details is None or not isinstance(channel, discord.TextChannel):
        await ctx.send("Use this command inside a ticket channel.", ephemeral=ctx.interaction is not None)
        return
    _, ticket_type = details
    if not is_ticket_staff(ctx.author, channel.guild, ticket_type):
        await ctx.send("Only the assigned team or a channel manager can change ticket roles.", ephemeral=ctx.interaction is not None)
        return
    await ctx.send(await change_ticket_helper_role(channel, role, False), ephemeral=ctx.interaction is not None)


@bot.hybrid_command(name="ticket-transcript", description="Export this open ticket's transcript to the archive.")
@commands.guild_only()
async def ticket_transcript(ctx: commands.Context) -> None:
    channel = ctx.channel
    details = ticket_details(channel)
    if details is None or not isinstance(channel, discord.TextChannel):
        await ctx.send("Use this command inside a ticket channel.", ephemeral=ctx.interaction is not None)
        return
    owner_id, ticket_type = details
    if not is_ticket_staff(ctx.author, channel.guild, ticket_type):
        await ctx.send("Only the assigned team or a channel manager can export transcripts.", ephemeral=ctx.interaction is not None)
        return
    if ctx.interaction is not None:
        await ctx.defer(ephemeral=True)
    archive = bot.get_channel(TRANSCRIPT_CHANNEL_ID)
    if archive is None:
        try:
            archive = await bot.fetch_channel(TRANSCRIPT_CHANNEL_ID)
        except discord.HTTPException:
            await ctx.send("I couldn't access the transcript archive channel.", ephemeral=ctx.interaction is not None)
            return
    if not isinstance(archive, discord.TextChannel):
        await ctx.send("The transcript destination must be a text channel.", ephemeral=ctx.interaction is not None)
        return

    transcript, claimed_staff, helped_staff = await build_ticket_transcript(
        channel,
        owner_id,
        ticket_type,
        f"Manual export by {ctx.author}",
    )
    embed = discord.Embed(
        title=f"Live Ticket Transcript: {channel.name}",
        color=discord.Color.from_rgb(43, 128, 117),
        timestamp=utc_now(),
    )
    embed.add_field(name="Ticket type", value=TICKET_TYPES[ticket_type]["label"], inline=True)
    embed.add_field(name="Opened by", value=f"<@{owner_id}>", inline=True)
    embed.add_field(name="Exported by", value=ctx.author.mention, inline=True)
    embed.add_field(name="Claimed by", value=format_staff_list(claimed_staff), inline=False)
    embed.add_field(name="Staff who helped", value=format_staff_list(helped_staff), inline=False)
    await archive.send(
        embed=embed,
        file=discord.File(BytesIO(transcript), filename=f"{channel.name}-transcript.txt"),
        allowed_mentions=discord.AllowedMentions.none(),
    )
    await ctx.send(f"Transcript exported to <#{TRANSCRIPT_CHANNEL_ID}>.", ephemeral=ctx.interaction is not None)


@bot.hybrid_command(name="ticket-note", description="Save a private staff-only note on this ticket.")
@commands.guild_only()
async def ticket_note(ctx: commands.Context, *, note: str) -> None:
    channel = ctx.channel
    details = ticket_details(channel)
    if details is None or not isinstance(channel, discord.TextChannel):
        await ctx.send("Use this command inside a ticket channel.", ephemeral=ctx.interaction is not None)
        return
    _, ticket_type = details
    if not is_ticket_staff(ctx.author, channel.guild, ticket_type):
        await ctx.send("Only the assigned team or a channel manager can add staff notes.", ephemeral=ctx.interaction is not None)
        return
    note = note.strip()
    if not note or len(note) > 1500:
        await ctx.send("A note is required and must be 1500 characters or fewer.", ephemeral=ctx.interaction is not None)
        return
    add_ticket_note(channel.id, ctx.author, note)
    await ctx.send("Private staff note saved. Use `ticket-notes` to view it.", ephemeral=ctx.interaction is not None)


@bot.hybrid_command(name="ticket-notes", description="View the latest private staff notes for this ticket.")
@commands.guild_only()
async def ticket_notes(ctx: commands.Context) -> None:
    channel = ctx.channel
    details = ticket_details(channel)
    if details is None or not isinstance(channel, discord.TextChannel):
        await ctx.send("Use this command inside a ticket channel.", ephemeral=ctx.interaction is not None)
        return
    _, ticket_type = details
    if not is_ticket_staff(ctx.author, channel.guild, ticket_type):
        await ctx.send("Only the assigned team or a channel manager can view staff notes.", ephemeral=ctx.interaction is not None)
        return

    notes = get_ticket_notes(channel.id)
    embed = discord.Embed(title=f"Staff Notes: {channel.name}", color=discord.Color.dark_teal())
    if not notes:
        embed.description = "No staff notes have been saved."
    else:
        for item in notes:
            created_at = datetime.fromisoformat(item["created_at"])
            note_text = item["note"]
            if len(note_text) > 900:
                note_text = f"{note_text[:897]}..."
            embed.add_field(
                name=f"{item['author_name']} | <t:{int(created_at.timestamp())}:R>",
                value=f"{note_text}\nNote ID: {item['note_id']}",
                inline=False,
            )
    if ctx.interaction is not None:
        await ctx.send(embed=embed, ephemeral=True)
        return
    try:
        await ctx.author.send(embed=embed)
        await ctx.send("I sent the private staff notes to your DMs.", delete_after=8)
    except discord.HTTPException:
        await ctx.send("I couldn't DM the notes. Enable DMs from server members to view them.")


@bot.hybrid_command(name="ticket-note-delete", description="Delete a staff note by its note ID.")
@app_commands.describe(note_id="Note ID shown by ticket-notes")
@commands.guild_only()
async def ticket_note_delete(ctx: commands.Context, note_id: int) -> None:
    channel = ctx.channel
    details = ticket_details(channel)
    if details is None or not isinstance(channel, discord.TextChannel):
        await ctx.send("Use this command inside a ticket channel.", ephemeral=ctx.interaction is not None)
        return
    _, ticket_type = details
    if not is_ticket_staff(ctx.author, channel.guild, ticket_type):
        await ctx.send("Only the assigned team or a channel manager can delete staff notes.", ephemeral=ctx.interaction is not None)
        return
    if note_id < 1:
        await ctx.send("Note ID must be a positive number.", ephemeral=ctx.interaction is not None)
        return
    deleted = delete_ticket_note(channel.id, note_id)
    result = f"Deleted staff note #{note_id}." if deleted else "That note ID doesn't exist in this ticket."
    await ctx.send(result, ephemeral=ctx.interaction is not None)


@bot.hybrid_command(name="ticket-close-deny", description="Decline a pending request to close this ticket.")
@app_commands.describe(reason="Optional explanation for the ticket opener")
@commands.guild_only()
async def ticket_close_deny(ctx: commands.Context, *, reason: str = "") -> None:
    channel = ctx.channel
    details = ticket_details(channel)
    if details is None or not isinstance(channel, discord.TextChannel):
        await ctx.send("Use this command inside a ticket channel.", ephemeral=ctx.interaction is not None)
        return
    _, ticket_type = details
    if not is_ticket_staff(ctx.author, channel.guild, ticket_type):
        await ctx.send("Only the assigned team or a channel manager can decline close requests.", ephemeral=ctx.interaction is not None)
        return
    result = await deny_ticket_close_request(channel, ctx.author, reason)
    await ctx.send(result, ephemeral=ctx.interaction is not None)


@bot.hybrid_command(name="ticket-reminder-reset", description="Restart the six-hour inactivity timer.")
@commands.guild_only()
async def ticket_reminder_reset(ctx: commands.Context) -> None:
    channel = ctx.channel
    details = ticket_details(channel)
    if details is None or not isinstance(channel, discord.TextChannel):
        await ctx.send("Use this command inside a ticket channel.", ephemeral=ctx.interaction is not None)
        return
    _, ticket_type = details
    if not is_ticket_staff(ctx.author, channel.guild, ticket_type):
        await ctx.send("Only the assigned team or a channel manager can reset ticket reminders.", ephemeral=ctx.interaction is not None)
        return
    await ctx.send(await reset_ticket_reminder(channel), ephemeral=ctx.interaction is not None)


@bot.hybrid_command(name="ticket-access", description="Show who can view this ticket channel.")
@commands.guild_only()
async def ticket_access(ctx: commands.Context) -> None:
    channel = ctx.channel
    details = ticket_details(channel)
    if details is None or not isinstance(channel, discord.TextChannel):
        await ctx.send("Use this command inside a ticket channel.", ephemeral=ctx.interaction is not None)
        return
    _, ticket_type = details
    if not is_ticket_staff(ctx.author, channel.guild, ticket_type):
        await ctx.send("Only the assigned team or a channel manager can inspect ticket access.", ephemeral=ctx.interaction is not None)
        return
    embed = await build_ticket_access_embed(channel)
    await ctx.send(embed=embed, ephemeral=ctx.interaction is not None)


@bot.tree.error
async def ticket_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError,
) -> None:
    command_name = interaction.command.name if interaction.command is not None else ""
    ephemeral = not command_name.startswith("session-")
    if isinstance(error, app_commands.MissingPermissions):
        permissions = ", ".join(permission.replace("_", " ") for permission in error.missing_permissions)
        message = f"You need these permissions to run the command: {permissions}."
    else:
        print(f"Ticket command failed: {error}")
        message = "The command failed. Check that I have permission to manage ticket channels."

    try:
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=ephemeral)
        else:
            await interaction.response.send_message(message, ephemeral=ephemeral)
    except discord.NotFound:
        print(f"Couldn't send command error because the interaction message no longer exists: {error}")


def main() -> None:
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        token = input("Enter your Discord bot token (input will be visible): ").strip()
    if not token:
        raise SystemExit("A Discord bot token is required.")
    bot.run(token)


if __name__ == "__main__":
    main()
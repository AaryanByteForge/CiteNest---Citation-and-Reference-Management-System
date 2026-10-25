"""
Authentication and Session Module (IAuth) for CiteNest.
Handles registration, password hashing, login, session verification, and logout.
"""

import uuid
import datetime
from typing import Optional, Dict, Any, Tuple
from database import get_db, hash_password, verify_password
from models import UserRole, AccountStatus


class AuthService:
    """Implements IAuth interface."""

    @staticmethod
    def register(name: str, email: str, password: str, role: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        name = name.strip()
        email = email.strip().lower()
        password = password.strip()

        if not name:
            return False, "Full Name is required.", None
        if not email or "@" not in email:
            return False, "A valid email address is required.", None
        if len(password) < 6:
            return False, "Password must be at least 6 characters long.", None
        if role not in [UserRole.STUDENT.value, UserRole.RESEARCHER.value]:
            return False, "Invalid role selected for registration.", None

        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT userId FROM users WHERE LOWER(email) = ?;", (email,))
            if cursor.fetchone():
                return False, "An account with this email already exists.", None

            # Generate next userId (e.g. U103...)
            cursor.execute("SELECT userId FROM users WHERE userId LIKE 'U%' ORDER BY LENGTH(userId) DESC, userId DESC LIMIT 1;")
            last_user = cursor.fetchone()
            if last_user:
                try:
                    num = int(last_user[0].replace("U", "")) + 1
                    user_id = f"U{num}"
                except Exception:
                    user_id = f"U{uuid.uuid4().hex[:4]}"
            else:
                user_id = "U101"

            pw_hash = hash_password(password)
            now = datetime.datetime.now(datetime.timezone.utc).isoformat()

            cursor.execute("""
                INSERT INTO users (userId, name, email, passwordHash, role, accountStatus, createdDate)
                VALUES (?, ?, ?, ?, ?, ?, ?);
            """, (user_id, name, email, pw_hash, role, AccountStatus.ACTIVE.value, now))

            # Audit log
            log_id = f"LOG-{uuid.uuid4().hex[:6].upper()}"
            cursor.execute("""
                INSERT INTO audit_logs (logId, actorId, action, timestamp)
                VALUES (?, ?, ?, ?);
            """, (log_id, user_id, f"User registration successful: {name} ({role})", now))

            conn.commit()

            return True, "Registration successful.", {
                "userId": user_id,
                "name": name,
                "email": email,
                "role": role,
                "accountStatus": AccountStatus.ACTIVE.value,
                "createdDate": now
            }

    @staticmethod
    def login(email: str, password: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        email = email.strip().lower()
        password = password.strip()

        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE LOWER(email) = ?;", (email,))
            row = cursor.fetchone()

            if not row or not verify_password(password, row["passwordHash"]):
                # Clear non-revealing error message (FR-004)
                return False, "Invalid email or password", None

            if row["accountStatus"] == AccountStatus.SUSPENDED.value:
                return False, "Account is suspended. Please contact administrator.", None

            session_id = f"SESS-{uuid.uuid4().hex}"
            now = datetime.datetime.now(datetime.timezone.utc).isoformat()

            cursor.execute("""
                INSERT INTO sessions (sessionId, userId, startedAt)
                VALUES (?, ?, ?);
            """, (session_id, row["userId"], now))

            # Audit log
            log_id = f"LOG-{uuid.uuid4().hex[:6].upper()}"
            cursor.execute("""
                INSERT INTO audit_logs (logId, actorId, action, timestamp)
                VALUES (?, ?, ?, ?);
            """, (log_id, row["userId"], f"User logged in from session {session_id[:12]}...", now))

            conn.commit()

            user_data = {
                "userId": row["userId"],
                "name": row["name"],
                "email": row["email"],
                "role": row["role"],
                "accountStatus": row["accountStatus"],
                "createdDate": row["createdDate"],
                "sessionId": session_id
            }
            return True, "Login successful.", user_data

    @staticmethod
    def verify_session(session_id: str) -> Optional[Dict[str, Any]]:
        """Verifies session and returns associated user data if valid."""
        if not session_id:
            return None

        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT u.userId, u.name, u.email, u.role, u.accountStatus, u.createdDate, s.sessionId, s.startedAt
                FROM sessions s
                JOIN users u ON s.userId = u.userId
                WHERE s.sessionId = ?;
            """, (session_id,))
            row = cursor.fetchone()
            if not row:
                return None
            if row["accountStatus"] == AccountStatus.SUSPENDED.value:
                return None
            return dict(row)

    @staticmethod
    def logout(session_id: str) -> bool:
        if not session_id:
            return True

        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT userId FROM sessions WHERE sessionId = ?;", (session_id,))
            row = cursor.fetchone()
            user_id = row["userId"] if row else "UNKNOWN"

            cursor.execute("DELETE FROM sessions WHERE sessionId = ?;", (session_id,))
            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            log_id = f"LOG-{uuid.uuid4().hex[:6].upper()}"
            cursor.execute("""
                INSERT INTO audit_logs (logId, actorId, action, timestamp)
                VALUES (?, ?, ?, ?);
            """, (log_id, user_id, "User logged out", now))
            conn.commit()
            return True

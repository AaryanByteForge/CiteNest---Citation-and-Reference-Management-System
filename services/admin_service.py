"""
Dashboard and Administration Module (Administrator / AuditLog / Dashboard) for CiteNest.
Provides user-level dashboard statistics and admin-only management and immutable audit logs.
"""

import uuid
import datetime
from typing import List, Dict, Any, Optional, Tuple
from database import get_db
from models import UserRole, AccountStatus


class AdminService:
    """Handles Dashboard analytics and Admin Portal operations."""

    @staticmethod
    def get_user_dashboard(user_id: str) -> Dict[str, Any]:
        with get_db() as conn:
            cursor = conn.cursor()

            # Reference counts
            cursor.execute("SELECT COUNT(*) FROM references_tab WHERE ownerId = ?;", (user_id,))
            total_refs = cursor.fetchone()[0]

            cursor.execute("""
                SELECT type, COUNT(*) as count
                FROM references_tab
                WHERE ownerId = ?
                GROUP BY type;
            """, (user_id,))
            type_counts = {r["type"]: r["count"] for r in cursor.fetchall()}

            # Collection counts
            cursor.execute("SELECT COUNT(*) FROM collections WHERE ownerId = ?;", (user_id,))
            total_cols = cursor.fetchone()[0]

            # Document counts
            cursor.execute("SELECT COUNT(*) FROM documents WHERE ownerId = ?;", (user_id,))
            total_docs = cursor.fetchone()[0]

            # User Collections with counts
            cursor.execute("""
                SELECT c.collectionId, c.name, COUNT(cm.membershipId) AS refCount
                FROM collections c
                LEFT JOIN collection_memberships cm ON c.collectionId = cm.collectionId
                WHERE c.ownerId = ?
                GROUP BY c.collectionId
                ORDER BY c.name ASC;
            """, (user_id,))
            collections = [dict(r) for r in cursor.fetchall()]

            # Recent documents
            cursor.execute("""
                SELECT documentId, title, citationStyle, state, lastModifiedDate
                FROM documents
                WHERE ownerId = ?
                ORDER BY lastModifiedDate DESC LIMIT 5;
            """, (user_id,))
            recent_docs = [dict(r) for r in cursor.fetchall()]

            # Recent references
            cursor.execute("""
                SELECT referenceId, title, type, authors, year, lifecycleState
                FROM references_tab
                WHERE ownerId = ?
                ORDER BY createdDate DESC LIMIT 5;
            """, (user_id,))
            recent_refs = [dict(r) for r in cursor.fetchall()]

            return {
                "totalReferences": total_refs,
                "totalCollections": total_cols,
                "totalDocuments": total_docs,
                "typeBreakdown": {
                    "Journal Article": type_counts.get("Journal Article", 0),
                    "Book": type_counts.get("Book", 0),
                    "Website": type_counts.get("Website", 0),
                },
                "collections": collections,
                "recentDocuments": recent_docs,
                "recentReferences": recent_refs
            }

    @staticmethod
    def get_system_metrics() -> Dict[str, Any]:
        with get_db() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM users;")
            total_users = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM users WHERE accountStatus = 'Active';")
            active_users = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM users WHERE accountStatus = 'Suspended';")
            suspended_users = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM references_tab;")
            total_references = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM collections;")
            total_collections = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM documents;")
            total_documents = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM exported_files;")
            total_exports = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM audit_logs;")
            total_logs = cursor.fetchone()[0]

            return {
                "totalUsers": total_users,
                "activeUsers": active_users,
                "suspendedUsers": suspended_users,
                "totalReferences": total_references,
                "totalCollections": total_collections,
                "totalDocuments": total_documents,
                "totalExports": total_exports,
                "totalLogs": total_logs
            }

    @staticmethod
    def get_all_users() -> List[Dict[str, Any]]:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT userId, name, email, role, accountStatus, createdDate,
                       (SELECT COUNT(*) FROM references_tab WHERE ownerId = users.userId) as referenceCount,
                       (SELECT COUNT(*) FROM documents WHERE ownerId = users.userId) as documentCount
                FROM users
                ORDER BY createdDate DESC;
            """)
            return [dict(r) for r in cursor.fetchall()]

    @staticmethod
    def update_user_status(admin_id: str, target_user_id: str, new_status: str) -> Tuple[bool, str]:
        if new_status not in [AccountStatus.ACTIVE.value, AccountStatus.SUSPENDED.value]:
            return False, "Invalid account status."

        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM users WHERE userId = ?;", (target_user_id,))
            user = cursor.fetchone()
            if not user:
                return False, "User not found."

            cursor.execute("UPDATE users SET accountStatus = ? WHERE userId = ?;", (new_status, target_user_id))

            # If suspending, invalidate all sessions
            if new_status == AccountStatus.SUSPENDED.value:
                cursor.execute("DELETE FROM sessions WHERE userId = ?;", (target_user_id,))

            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            log_id = f"LOG-{uuid.uuid4().hex[:6].upper()}"
            cursor.execute("""
                INSERT INTO audit_logs (logId, actorId, action, timestamp)
                VALUES (?, ?, ?, ?);
            """, (log_id, admin_id, f"Admin updated user {target_user_id} status to '{new_status}'", now))

            conn.commit()
            return True, f"User {user['name']} status updated to {new_status}."

    @staticmethod
    def update_user_role(admin_id: str, target_user_id: str, new_role: str) -> Tuple[bool, str]:
        if new_role not in [UserRole.STUDENT.value, UserRole.RESEARCHER.value, UserRole.ADMINISTRATOR.value]:
            return False, "Invalid role specified."

        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM users WHERE userId = ?;", (target_user_id,))
            user = cursor.fetchone()
            if not user:
                return False, "User not found."

            cursor.execute("UPDATE users SET role = ? WHERE userId = ?;", (new_role, target_user_id))

            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            log_id = f"LOG-{uuid.uuid4().hex[:6].upper()}"
            cursor.execute("""
                INSERT INTO audit_logs (logId, actorId, action, timestamp)
                VALUES (?, ?, ?, ?);
            """, (log_id, admin_id, f"Admin changed user {target_user_id} role to '{new_role}'", now))

            conn.commit()
            return True, f"User {user['name']} role updated to {new_role}."

    @staticmethod
    def delete_user(admin_id: str, target_user_id: str) -> Tuple[bool, str]:
        if admin_id == target_user_id:
            return False, "Cannot delete your own administrator account."

        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM users WHERE userId = ?;", (target_user_id,))
            user = cursor.fetchone()
            if not user:
                return False, "User not found."

            name = user["name"]
            # Cascade deletes handle sessions, documents, references, etc.
            cursor.execute("DELETE FROM users WHERE userId = ?;", (target_user_id,))

            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            log_id = f"LOG-{uuid.uuid4().hex[:6].upper()}"
            cursor.execute("""
                INSERT INTO audit_logs (logId, actorId, action, timestamp)
                VALUES (?, ?, ?, ?);
            """, (log_id, admin_id, f"Admin deleted user account {target_user_id} ({name})", now))

            conn.commit()
            return True, f"User {name} deleted successfully."

    @staticmethod
    def get_audit_logs(query: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        with get_db() as conn:
            cursor = conn.cursor()
            if query and query.strip():
                q = f"%{query.strip()}%"
                cursor.execute("""
                    SELECT logId, actorId, action, timestamp
                    FROM audit_logs
                    WHERE logId LIKE ? OR actorId LIKE ? OR action LIKE ?
                    ORDER BY timestamp DESC LIMIT ?;
                """, (q, q, q, limit))
            else:
                cursor.execute("""
                    SELECT logId, actorId, action, timestamp
                    FROM audit_logs
                    ORDER BY timestamp DESC LIMIT ?;
                """, (limit,))

            return [dict(r) for r in cursor.fetchall()]

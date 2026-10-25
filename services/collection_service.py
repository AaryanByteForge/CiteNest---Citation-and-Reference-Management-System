"""
Collection Module (ICollection) for CiteNest.
Manages project collections and CollectionMembership links with composition integrity.
"""

import uuid
import datetime
from typing import List, Dict, Any, Optional, Tuple
from database import get_db
from models import ReferenceLifecycleState


class CollectionService:
    """Implements ICollection interface."""

    @staticmethod
    def get_user_collections(owner_id: str) -> List[Dict[str, Any]]:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT c.collectionId, c.name, c.ownerId, c.createdDate,
                       COUNT(cm.membershipId) AS referenceCount
                FROM collections c
                LEFT JOIN collection_memberships cm ON c.collectionId = cm.collectionId
                WHERE c.ownerId = ?
                GROUP BY c.collectionId
                ORDER BY c.name ASC;
            """, (owner_id,))
            return [dict(r) for r in cursor.fetchall()]

    @staticmethod
    def create_collection(owner_id: str, name: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        name = name.strip()
        if not name:
            return False, "Collection name cannot be empty.", None

        with get_db() as conn:
            cursor = conn.cursor()
            # Check duplicate name for same user
            cursor.execute("SELECT collectionId FROM collections WHERE ownerId = ? AND LOWER(name) = ?;", (owner_id, name.lower()))
            if cursor.fetchone():
                return False, f"A collection named '{name}' already exists in your library.", None

            # Generate C-ID (e.g. C11)
            cursor.execute("SELECT collectionId FROM collections WHERE collectionId LIKE 'C%' ORDER BY LENGTH(collectionId) DESC, collectionId DESC LIMIT 1;")
            last_c = cursor.fetchone()
            if last_c:
                try:
                    num = int(last_c[0].replace("C", "")) + 1
                    col_id = f"C{num}"
                except Exception:
                    col_id = f"C{uuid.uuid4().hex[:4].upper()}"
            else:
                col_id = "C10"

            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            cursor.execute("""
                INSERT INTO collections (collectionId, name, ownerId, createdDate)
                VALUES (?, ?, ?, ?);
            """, (col_id, name, owner_id, now))

            # Audit log
            log_id = f"LOG-{uuid.uuid4().hex[:6].upper()}"
            cursor.execute("""
                INSERT INTO audit_logs (logId, actorId, action, timestamp)
                VALUES (?, ?, ?, ?);
            """, (log_id, owner_id, f"Created collection '{name}' ({col_id})", now))

            conn.commit()

            return True, "Collection created successfully.", {
                "collectionId": col_id,
                "name": name,
                "ownerId": owner_id,
                "createdDate": now,
                "referenceCount": 0
            }

    @staticmethod
    def rename_collection(owner_id: str, collection_id: str, new_name: str) -> Tuple[bool, str]:
        new_name = new_name.strip()
        if not new_name:
            return False, "Collection name cannot be empty."

        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM collections WHERE collectionId = ? AND ownerId = ?;", (collection_id, owner_id))
            col = cursor.fetchone()
            if not col:
                return False, "Collection not found or access denied."

            cursor.execute("UPDATE collections SET name = ? WHERE collectionId = ?;", (new_name, collection_id))
            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            log_id = f"LOG-{uuid.uuid4().hex[:6].upper()}"
            cursor.execute("""
                INSERT INTO audit_logs (logId, actorId, action, timestamp)
                VALUES (?, ?, ?, ?);
            """, (log_id, owner_id, f"Renamed collection {collection_id} to '{new_name}'", now))

            conn.commit()
            return True, "Collection renamed successfully."

    @staticmethod
    def delete_collection(owner_id: str, collection_id: str) -> Tuple[bool, str]:
        """
        Deletes collection and its CollectionMembership records.
        Composition Rule: NEVER deletes underlying references!
        """
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM collections WHERE collectionId = ? AND ownerId = ?;", (collection_id, owner_id))
            col = cursor.fetchone()
            if not col:
                return False, "Collection not found or access denied."

            col_name = col["name"]

            # Fetch references in this collection to recalculate lifecycleState
            cursor.execute("SELECT referenceId FROM collection_memberships WHERE collectionId = ?;", (collection_id,))
            ref_ids = [r[0] for r in cursor.fetchall()]

            # Delete memberships first (composition)
            cursor.execute("DELETE FROM collection_memberships WHERE collectionId = ?;", (collection_id,))
            cursor.execute("DELETE FROM collections WHERE collectionId = ?;", (collection_id,))

            # Check each affected reference's lifecycleState
            for r_id in ref_ids:
                cursor.execute("SELECT COUNT(*) FROM citations WHERE referenceId = ?;", (r_id,))
                is_cited = cursor.fetchone()[0] > 0
                if is_cited:
                    state = ReferenceLifecycleState.CITED.value
                else:
                    cursor.execute("SELECT COUNT(*) FROM collection_memberships WHERE referenceId = ?;", (r_id,))
                    has_other_col = cursor.fetchone()[0] > 0
                    state = ReferenceLifecycleState.IN_COLLECTION.value if has_other_col else ReferenceLifecycleState.STORED.value

                cursor.execute("UPDATE references_tab SET lifecycleState = ? WHERE referenceId = ?;", (state, r_id))

            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            log_id = f"LOG-{uuid.uuid4().hex[:6].upper()}"
            cursor.execute("""
                INSERT INTO audit_logs (logId, actorId, action, timestamp)
                VALUES (?, ?, ?, ?);
            """, (log_id, owner_id, f"Deleted collection '{col_name}' ({collection_id})", now))

            conn.commit()
            return True, f"Collection '{col_name}' deleted. Underlying references preserved in library."

    @staticmethod
    def add_reference_to_collection(owner_id: str, collection_id: str, reference_id: str) -> Tuple[bool, str]:
        with get_db() as conn:
            cursor = conn.cursor()
            # Verify ownership of both collection and reference
            cursor.execute("SELECT collectionId FROM collections WHERE collectionId = ? AND ownerId = ?;", (collection_id, owner_id))
            if not cursor.fetchone():
                return False, "Collection not found or access denied."

            cursor.execute("SELECT lifecycleState FROM references_tab WHERE referenceId = ? AND ownerId = ?;", (reference_id, owner_id))
            ref = cursor.fetchone()
            if not ref:
                return False, "Reference not found or access denied."

            # Check if already a member
            cursor.execute("SELECT membershipId FROM collection_memberships WHERE collectionId = ? AND referenceId = ?;", (collection_id, reference_id))
            if cursor.fetchone():
                return True, "Reference is already in this collection."

            mem_id = f"M{uuid.uuid4().hex[:5].upper()}"
            cursor.execute("""
                INSERT INTO collection_memberships (membershipId, collectionId, referenceId)
                VALUES (?, ?, ?);
            """, (mem_id, collection_id, reference_id))

            # Update lifecycle state if not Cited
            if ref["lifecycleState"] != ReferenceLifecycleState.CITED.value:
                cursor.execute("""
                    UPDATE references_tab SET lifecycleState = ? WHERE referenceId = ?;
                """, (ReferenceLifecycleState.IN_COLLECTION.value, reference_id))

            conn.commit()
            return True, "Reference added to collection."

    @staticmethod
    def remove_reference_from_collection(owner_id: str, collection_id: str, reference_id: str) -> Tuple[bool, str]:
        with get_db() as conn:
            cursor = conn.cursor()
            # Verify ownership
            cursor.execute("SELECT collectionId FROM collections WHERE collectionId = ? AND ownerId = ?;", (collection_id, owner_id))
            if not cursor.fetchone():
                return False, "Collection not found or access denied."

            cursor.execute("DELETE FROM collection_memberships WHERE collectionId = ? AND referenceId = ?;", (collection_id, reference_id))

            # Re-evaluate lifecycleState
            cursor.execute("SELECT COUNT(*) FROM citations WHERE referenceId = ?;", (reference_id,))
            is_cited = cursor.fetchone()[0] > 0
            if is_cited:
                new_state = ReferenceLifecycleState.CITED.value
            else:
                cursor.execute("SELECT COUNT(*) FROM collection_memberships WHERE referenceId = ?;", (reference_id,))
                has_other = cursor.fetchone()[0] > 0
                new_state = ReferenceLifecycleState.IN_COLLECTION.value if has_other else ReferenceLifecycleState.STORED.value

            cursor.execute("UPDATE references_tab SET lifecycleState = ? WHERE referenceId = ?;", (new_state, reference_id))

            conn.commit()
            return True, "Reference removed from collection."

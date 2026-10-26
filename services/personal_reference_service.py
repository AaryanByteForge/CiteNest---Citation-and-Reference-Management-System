"""
Personal Reference Service for CiteNest.

Application Layer service that manages references stored in each user's
personal SQLite database (user_databases/<userId>.db).

Isolation guarantee:
    - The database path is computed from the authenticated user_id only.
    - No path or file name is ever accepted from the frontend.
    - Authentication is handled by the central DB (citenest.db) before
      any method here is called.
"""

import uuid
import datetime
from typing import Dict, Any, List, Optional, Tuple
from database import get_user_db
from validators import ReferenceValidator


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class PersonalReferenceService:
    """CRUD for a user's personal reference database."""

    # -----------------------------------------------------------------
    # Read
    # -----------------------------------------------------------------

    @staticmethod
    def get_references(
        user_id: str,
        query: Optional[str] = None,
        ref_type: Optional[str] = None,
        year: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Returns the user's personal references, optionally filtered.
        Each result carries referenceSource='PERSONAL'.
        """
        with get_user_db(user_id) as conn:
            sql = "SELECT * FROM personal_references WHERE 1=1"
            params: List[Any] = []

            if ref_type and ref_type != "All":
                sql += " AND type = ?"
                params.append(ref_type)

            if year and year != "All":
                sql += " AND year = ?"
                params.append(year)

            sql += " ORDER BY createdDate DESC"
            cursor = conn.execute(sql, params)
            rows = [dict(r) for r in cursor.fetchall()]

        q_clean = (query or "").strip().lower()
        results = []
        for item in rows:
            if q_clean:
                if not any(
                    q_clean in (item.get(f) or "").lower()
                    for f in ("title", "authors", "year", "keywords", "journalName", "siteName")
                ):
                    continue
            item["referenceSource"] = "PERSONAL"
            item["ownerId"] = user_id          # virtual field for downstream compatibility
            item["lifecycleState"] = "Stored"  # personal refs don't track lifecycle in central DB
            item["collections"] = []
            results.append(item)

        return results

    @staticmethod
    def get_reference_by_id(user_id: str, reference_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetches a single personal reference.  Returns None if not found.
        Access is restricted to the owning user because the DB itself is user-scoped.
        """
        with get_user_db(user_id) as conn:
            cursor = conn.execute(
                "SELECT * FROM personal_references WHERE referenceId = ?",
                (reference_id,)
            )
            row = cursor.fetchone()

        if not row:
            return None
        item = dict(row)
        item["referenceSource"] = "PERSONAL"
        item["ownerId"] = user_id
        item["lifecycleState"] = "Stored"
        item["collections"] = []
        return item

    # -----------------------------------------------------------------
    # Create
    # -----------------------------------------------------------------

    @staticmethod
    def add_reference(
        user_id: str, data: Dict[str, Any]
    ) -> Tuple[bool, str, Dict[str, str], Optional[Dict[str, Any]]]:
        """
        Validates and inserts a personal reference.
        Returns (success, message, errors, created_ref).
        """
        is_valid, errors = ReferenceValidator.validate(data)
        if not is_valid:
            return False, "Validation failed. Please correct the highlighted errors.", errors, None

        ref_id = f"PR-{uuid.uuid4().hex[:8].upper()}"
        now = _now()

        with get_user_db(user_id) as conn:
            conn.execute("""
                INSERT INTO personal_references (
                    referenceId, type, title, authors, year,
                    journalName, volumeIssue, pages, publisher, editionPlace,
                    siteName, url, accessDate, keywords, createdDate
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                ref_id,
                data.get("type"),
                (data.get("title") or "").strip(),
                (data.get("authors") or "").strip(),
                str(data.get("year") or "").strip(),
                (data.get("journalName") or "").strip() or None,
                (data.get("volumeIssue") or "").strip() or None,
                (data.get("pages") or "").strip() or None,
                (data.get("publisher") or "").strip() or None,
                (data.get("editionPlace") or "").strip() or None,
                (data.get("siteName") or "").strip() or None,
                (data.get("url") or "").strip() or None,
                (data.get("accessDate") or "").strip() or None,
                (data.get("keywords") or "").strip(),
                now,
            ))
            conn.commit()

        created = PersonalReferenceService.get_reference_by_id(user_id, ref_id)
        return True, "Personal reference saved successfully.", {}, created

    # -----------------------------------------------------------------
    # Update
    # -----------------------------------------------------------------

    @staticmethod
    def edit_reference(
        user_id: str, reference_id: str, data: Dict[str, Any]
    ) -> Tuple[bool, str, Dict[str, str], Optional[Dict[str, Any]]]:
        """Re-validates and updates a personal reference."""
        is_valid, errors = ReferenceValidator.validate(data)
        if not is_valid:
            return False, "Validation failed. Please correct the highlighted errors.", errors, None

        with get_user_db(user_id) as conn:
            cursor = conn.execute(
                "SELECT referenceId FROM personal_references WHERE referenceId = ?",
                (reference_id,)
            )
            if not cursor.fetchone():
                return False, "Personal reference not found.", {}, None

            conn.execute("""
                UPDATE personal_references SET
                    type=?, title=?, authors=?, year=?,
                    journalName=?, volumeIssue=?, pages=?,
                    publisher=?, editionPlace=?, siteName=?,
                    url=?, accessDate=?, keywords=?
                WHERE referenceId=?
            """, (
                data.get("type"),
                (data.get("title") or "").strip(),
                (data.get("authors") or "").strip(),
                str(data.get("year") or "").strip(),
                (data.get("journalName") or "").strip() or None,
                (data.get("volumeIssue") or "").strip() or None,
                (data.get("pages") or "").strip() or None,
                (data.get("publisher") or "").strip() or None,
                (data.get("editionPlace") or "").strip() or None,
                (data.get("siteName") or "").strip() or None,
                (data.get("url") or "").strip() or None,
                (data.get("accessDate") or "").strip() or None,
                (data.get("keywords") or "").strip(),
                reference_id,
            ))
            conn.commit()

        updated = PersonalReferenceService.get_reference_by_id(user_id, reference_id)
        return True, "Personal reference updated.", {}, updated

    # -----------------------------------------------------------------
    # Delete
    # -----------------------------------------------------------------

    @staticmethod
    def delete_reference(user_id: str, reference_id: str) -> Tuple[bool, str]:
        """Deletes a personal reference.  Access is restricted by DB scope."""
        with get_user_db(user_id) as conn:
            cursor = conn.execute(
                "SELECT title FROM personal_references WHERE referenceId = ?",
                (reference_id,)
            )
            row = cursor.fetchone()
            if not row:
                return False, "Personal reference not found."

            title = row["title"]
            conn.execute(
                "DELETE FROM personal_references WHERE referenceId = ?",
                (reference_id,)
            )
            conn.commit()

        return True, f"Personal reference '{title}' deleted."

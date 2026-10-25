"""
Reference Management Module (IReference + ReferenceValidator) and SearchService for CiteNest.
Handles CRUD, validation, cascading citation cleanup, and multi-facet search/filtering.
"""

import uuid
import datetime
import json
import re
from typing import List, Dict, Any, Optional, Tuple
from database import get_db
from models import ReferenceLifecycleState, DocumentLifecycleState, CitationStyle
from validators import ReferenceValidator
from formatters import CitationEngine


class ReferenceService:
    """Implements IReference interface with cascading deletion safeguards."""

    @staticmethod
    def get_references(
        owner_id: str,
        query: Optional[str] = None,
        ref_type: Optional[str] = None,
        year: Optional[str] = None,
        collection_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        with get_db() as conn:
            cursor = conn.cursor()

            sql = """
                SELECT r.*,
                       GROUP_CONCAT(c.collectionId) AS collectionIds,
                       GROUP_CONCAT(c.name) AS collectionNames
                FROM references_tab r
                LEFT JOIN collection_memberships cm ON r.referenceId = cm.referenceId
                LEFT JOIN collections c ON cm.collectionId = c.collectionId
                WHERE r.ownerId = ?
            """
            params: List[Any] = [owner_id]

            if ref_type and ref_type != "All":
                sql += " AND r.type = ?"
                params.append(ref_type)

            if year and year != "All":
                sql += " AND r.year = ?"
                params.append(year)

            sql += " GROUP BY r.referenceId"

            if collection_id and collection_id != "All":
                # Filter by collection membership
                sql += " HAVING INSTR(',' || IFNULL(collectionIds, '') || ',', ',' || ? || ',') > 0"
                params.append(collection_id)

            sql += " ORDER BY r.createdDate DESC;"

            cursor.execute(sql, params)
            rows = cursor.fetchall()

            results = []
            q_clean = (query or "").strip().lower()

            for r in rows:
                item = dict(r)
                # Parse collection arrays
                c_ids = item["collectionIds"].split(",") if item.get("collectionIds") else []
                c_names = item["collectionNames"].split(",") if item.get("collectionNames") else []
                item["collections"] = [
                    {"collectionId": cid, "name": cnames}
                    for cid, cnames in zip(c_ids, c_names)
                ]

                # In-memory query match for keywords, title, authors, year (FR-015)
                if q_clean:
                    title_m = q_clean in (item.get("title") or "").lower()
                    author_m = q_clean in (item.get("authors") or "").lower()
                    year_m = q_clean in str(item.get("year") or "").lower()
                    kw_m = q_clean in (item.get("keywords") or "").lower()
                    journal_m = q_clean in (item.get("journalName") or "").lower()
                    site_m = q_clean in (item.get("siteName") or "").lower()

                    if not (title_m or author_m or year_m or kw_m or journal_m or site_m):
                        continue

                results.append(item)

            return results

    @staticmethod
    def get_reference_by_id(owner_id: str, reference_id: str) -> Optional[Dict[str, Any]]:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT r.*,
                       GROUP_CONCAT(c.collectionId) AS collectionIds,
                       GROUP_CONCAT(c.name) AS collectionNames
                FROM references_tab r
                LEFT JOIN collection_memberships cm ON r.referenceId = cm.referenceId
                LEFT JOIN collections c ON cm.collectionId = c.collectionId
                WHERE r.referenceId = ? AND r.ownerId = ?
                GROUP BY r.referenceId;
            """, (reference_id, owner_id))
            row = cursor.fetchone()
            if not row:
                return None
            item = dict(row)
            c_ids = item["collectionIds"].split(",") if item.get("collectionIds") else []
            c_names = item["collectionNames"].split(",") if item.get("collectionNames") else []
            item["collections"] = [
                {"collectionId": cid, "name": cnames}
                for cid, cnames in zip(c_ids, c_names)
            ]
            return item

    @staticmethod
    def add_reference(owner_id: str, data: Dict[str, Any]) -> Tuple[bool, str, Dict[str, str], Optional[Dict[str, Any]]]:
        """
        Validates and adds a new reference.
        Returns: (success: bool, message: str, errors: dict, created_ref: dict)
        """
        is_valid, errors = ReferenceValidator.validate(data)
        if not is_valid:
            return False, "Validation failed. Please correct the highlighted errors.", errors, None

        with get_db() as conn:
            cursor = conn.cursor()

            # Generate next referenceId (e.g., R58...)
            cursor.execute("SELECT referenceId FROM references_tab WHERE referenceId LIKE 'R%' ORDER BY LENGTH(referenceId) DESC, referenceId DESC LIMIT 1;")
            last_r = cursor.fetchone()
            if last_r:
                try:
                    num = int(last_r[0].replace("R", "")) + 1
                    ref_id = f"R{num}"
                except Exception:
                    ref_id = f"R{uuid.uuid4().hex[:4].upper()}"
            else:
                ref_id = "R55"

            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            target_collection_id = data.get("collectionId")

            lifecycle_state = ReferenceLifecycleState.IN_COLLECTION.value if target_collection_id else ReferenceLifecycleState.STORED.value

            cursor.execute("""
                INSERT INTO references_tab (
                    referenceId, ownerId, type, title, authors, year,
                    journalName, volumeIssue, pages, publisher, editionPlace,
                    siteName, url, accessDate, keywords, lifecycleState, createdDate
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                ref_id,
                owner_id,
                data.get("type"),
                (data.get("title") or "").strip(),
                (data.get("authors") or "").strip(),
                str(data.get("year") or "").strip(),
                (data.get("journalName") or "").strip() if data.get("journalName") else None,
                (data.get("volumeIssue") or "").strip() if data.get("volumeIssue") else None,
                (data.get("pages") or "").strip() if data.get("pages") else None,
                (data.get("publisher") or "").strip() if data.get("publisher") else None,
                (data.get("editionPlace") or "").strip() if data.get("editionPlace") else None,
                (data.get("siteName") or "").strip() if data.get("siteName") else None,
                (data.get("url") or "").strip() if data.get("url") else None,
                (data.get("accessDate") or "").strip() if data.get("accessDate") else None,
                (data.get("keywords") or "").strip(),
                lifecycle_state,
                now
            ))

            # Optional collection assignment
            if target_collection_id:
                mem_id = f"M{uuid.uuid4().hex[:5].upper()}"
                cursor.execute("""
                    INSERT INTO collection_memberships (membershipId, collectionId, referenceId)
                    VALUES (?, ?, ?);
                """, (mem_id, target_collection_id, ref_id))

            # Audit log
            log_id = f"LOG-{uuid.uuid4().hex[:6].upper()}"
            cursor.execute("""
                INSERT INTO audit_logs (logId, actorId, action, timestamp)
                VALUES (?, ?, ?, ?);
            """, (log_id, owner_id, f"Added reference {ref_id}: '{(data.get('title') or '')[:40]}'", now))

            conn.commit()

            created = ReferenceService.get_reference_by_id(owner_id, ref_id)
            return True, "Reference saved successfully.", {}, created

    @staticmethod
    def edit_reference(owner_id: str, reference_id: str, data: Dict[str, Any]) -> Tuple[bool, str, Dict[str, str], Optional[Dict[str, Any]]]:
        """
        Re-validates and updates a stored reference.
        If reference is already cited in any documents, automatically refreshes
        in-text citations and bibliographies across those documents (FR-009).
        """
        is_valid, errors = ReferenceValidator.validate(data)
        if not is_valid:
            return False, "Validation failed. Please correct the highlighted errors.", errors, None

        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM references_tab WHERE referenceId = ? AND ownerId = ?;", (reference_id, owner_id))
            existing = cursor.fetchone()
            if not existing:
                return False, "Reference not found or access denied.", {}, None

            cursor.execute("""
                UPDATE references_tab SET
                    type = ?,
                    title = ?,
                    authors = ?,
                    year = ?,
                    journalName = ?,
                    volumeIssue = ?,
                    pages = ?,
                    publisher = ?,
                    editionPlace = ?,
                    siteName = ?,
                    url = ?,
                    accessDate = ?,
                    keywords = ?
                WHERE referenceId = ? AND ownerId = ?;
            """, (
                data.get("type"),
                (data.get("title") or "").strip(),
                (data.get("authors") or "").strip(),
                str(data.get("year") or "").strip(),
                (data.get("journalName") or "").strip() if data.get("journalName") else None,
                (data.get("volumeIssue") or "").strip() if data.get("volumeIssue") else None,
                (data.get("pages") or "").strip() if data.get("pages") else None,
                (data.get("publisher") or "").strip() if data.get("publisher") else None,
                (data.get("editionPlace") or "").strip() if data.get("editionPlace") else None,
                (data.get("siteName") or "").strip() if data.get("siteName") else None,
                (data.get("url") or "").strip() if data.get("url") else None,
                (data.get("accessDate") or "").strip() if data.get("accessDate") else None,
                (data.get("keywords") or "").strip(),
                reference_id,
                owner_id
            ))

            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            log_id = f"LOG-{uuid.uuid4().hex[:6].upper()}"
            cursor.execute("""
                INSERT INTO audit_logs (logId, actorId, action, timestamp)
                VALUES (?, ?, ?, ?);
            """, (log_id, owner_id, f"Edited reference {reference_id}: '{(data.get('title') or '')[:40]}'", now))

            conn.commit()

        # Refresh affected documents (FR-009)
        ReferenceService._refresh_citing_documents(owner_id, reference_id)

        updated = ReferenceService.get_reference_by_id(owner_id, reference_id)
        return True, "Reference updated and citing documents refreshed.", {}, updated

    @staticmethod
    def check_cascade_citations(owner_id: str, reference_id: str) -> Dict[str, Any]:
        """
        Checks whether the reference is currently cited in any documents.
        Returns: {
            "isCited": bool,
            "citingDocuments": [{"documentId": str, "title": str}]
        }
        """
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT d.documentId, d.title
                FROM citations c
                JOIN documents d ON c.documentId = d.documentId
                WHERE c.referenceId = ? AND d.ownerId = ?;
            """, (reference_id, owner_id))
            citing_docs = [dict(r) for r in cursor.fetchall()]

            return {
                "isCited": len(citing_docs) > 0,
                "citingDocuments": citing_docs,
                "referenceId": reference_id
            }

    @staticmethod
    def delete_reference(owner_id: str, reference_id: str) -> Tuple[bool, str]:
        """
        Performs cascading citation cleanup:
        - Removes every inline citation of this reference from all citing documents.
        - Automatically regenerates each affected document's bibliography.
        - If an affected document has 0 remaining citations, transitions state back to "In Progress".
        - Removes CollectionMembership links.
        - Deletes reference record.
        """
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT title FROM references_tab WHERE referenceId = ? AND ownerId = ?;", (reference_id, owner_id))
            ref = cursor.fetchone()
            if not ref:
                return False, "Reference not found or access denied."

            ref_title = ref["title"]

            # Find all citing document IDs
            cursor.execute("""
                SELECT DISTINCT documentId FROM citations WHERE referenceId = ?;
            """, (reference_id,))
            affected_doc_ids = [r[0] for r in cursor.fetchall()]

            # 1. Remove citations for this reference
            cursor.execute("DELETE FROM citations WHERE referenceId = ?;", (reference_id,))

            # 2. Remove collection memberships
            cursor.execute("DELETE FROM collection_memberships WHERE referenceId = ?;", (reference_id,))

            # 3. Delete reference
            cursor.execute("DELETE FROM references_tab WHERE referenceId = ? AND ownerId = ?;", (reference_id, owner_id))

            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            log_id = f"LOG-{uuid.uuid4().hex[:6].upper()}"
            cursor.execute("""
                INSERT INTO audit_logs (logId, actorId, action, timestamp)
                VALUES (?, ?, ?, ?);
            """, (log_id, owner_id, f"Deleted reference {reference_id}: '{ref_title[:40]}' (cascading cleanup on {len(affected_doc_ids)} docs)", now))

            conn.commit()

        # Clean document bodies and regenerate bibliographies
        from services.document_service import DocumentService
        for doc_id in affected_doc_ids:
            DocumentService.clean_and_refresh_document_after_reference_delete(owner_id, doc_id, reference_id)

        return True, f"Reference '{ref_title}' deleted and citing documents cleaned up."

    @staticmethod
    def _refresh_citing_documents(owner_id: str, reference_id: str):
        """Regenerates inline citations and bibliographies in citing documents after an edit."""
        from services.document_service import DocumentService
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT d.documentId
                FROM citations c
                JOIN documents d ON c.documentId = d.documentId
                WHERE c.referenceId = ? AND d.ownerId = ?;
            """, (reference_id, owner_id))
            docs = cursor.fetchall()

        for d in docs:
            DocumentService.recompile_document_citations(owner_id, d["documentId"])

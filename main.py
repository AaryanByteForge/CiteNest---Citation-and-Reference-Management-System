"""
CiteNest Main Application & REST API Service.
Integrates all modules, interfaces, and static Single Page Application hosting.
"""

import os
from typing import Optional, Dict, Any
from fastapi import FastAPI, Request, HTTPException, Depends, Header, Query, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from database import init_db, seed_demo_data
from services.auth_service import AuthService
from services.reference_service import ReferenceService
from services.collection_service import CollectionService
from services.document_service import DocumentService
from services.export_service import ExportService
from services.admin_service import AdminService
from models import UserRole

# Ensure DB is ready
init_db()

app = FastAPI(title="CiteNest Citation & Reference Management System", version="1.0.0")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Security & Session Verification Dependency (NFR-004) ---

def get_current_user(
    request: Request,
    authorization: Optional[str] = Header(None),
    x_session_id: Optional[str] = Header(None),
    session_id: Optional[str] = Query(None)
) -> Dict[str, Any]:
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
    elif x_session_id:
        token = x_session_id.strip()
    elif session_id:
        token = session_id.strip()

    if not token:
        raise HTTPException(status_code=401, detail="Authentication session required.")

    user = AuthService.verify_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Session expired or invalid. Please log in.")

    return user


def require_admin(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    if user.get("role") != UserRole.ADMINISTRATOR.value:
        raise HTTPException(status_code=403, detail="Administrator privileges required.")
    return user


# --- Request Schemas ---

class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str
    role: str


class LoginRequest(BaseModel):
    email: str
    password: str


class CreateCollectionRequest(BaseModel):
    name: str


class RenameCollectionRequest(BaseModel):
    name: str


class CreateDocumentRequest(BaseModel):
    title: str
    citationStyle: Optional[str] = "APA"


class SaveDocumentRequest(BaseModel):
    title: str
    content: str
    citationStyle: str


class InsertCitationRequest(BaseModel):
    referenceId: str
    contentWithToken: Optional[str] = None


class SwitchStyleRequest(BaseModel):
    citationStyle: str


class UpdateUserStatusRequest(BaseModel):
    accountStatus: str


class UpdateUserRoleRequest(BaseModel):
    role: str


# --- 1. Authentication Endpoints (IAuth) ---

@app.post("/api/auth/register")
def register(req: RegisterRequest):
    success, msg, user = AuthService.register(req.name, req.email, req.password, req.role)
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"success": True, "message": msg, "user": user}


@app.post("/api/auth/login")
def login(req: LoginRequest):
    success, msg, user_data = AuthService.login(req.email, req.password)
    if not success:
        raise HTTPException(status_code=401, detail=msg)
    return {"success": True, "message": msg, "user": user_data}


@app.get("/api/auth/me")
def get_me(user: Dict[str, Any] = Depends(get_current_user)):
    return {"success": True, "user": user}


@app.post("/api/auth/logout")
def logout(user: Dict[str, Any] = Depends(get_current_user)):
    AuthService.logout(user["sessionId"])
    return {"success": True, "message": "Logged out successfully."}


@app.post("/api/auth/reset-demo")
def reset_demo():
    seed_demo_data(force_reset=True)
    return {"success": True, "message": "CiteNest database reset to standard demo data (UML Object Diagram & Annex F)."}


# --- 2. Dashboard Endpoints ---

@app.get("/api/dashboard")
def get_dashboard(user: Dict[str, Any] = Depends(get_current_user)):
    data = AdminService.get_user_dashboard(user["userId"])
    return {"success": True, "data": data}


# --- 3. Reference Management & Search (IReference + SearchService) ---

@app.get("/api/references")
def list_references(
    query: Optional[str] = None,
    type: Optional[str] = None,
    year: Optional[str] = None,
    collectionId: Optional[str] = None,
    user: Dict[str, Any] = Depends(get_current_user)
):
    refs = ReferenceService.get_references(
        owner_id=user["userId"],
        query=query,
        ref_type=type,
        year=year,
        collection_id=collectionId
    )
    return {"success": True, "references": refs}


@app.get("/api/references/{ref_id}")
def get_reference(ref_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    ref = ReferenceService.get_reference_by_id(user["userId"], ref_id)
    if not ref:
        raise HTTPException(status_code=404, detail="Reference not found.")
    return {"success": True, "reference": ref}


@app.post("/api/references")
def create_reference(data: Dict[str, Any], user: Dict[str, Any] = Depends(get_current_user)):
    success, msg, errors, created = ReferenceService.add_reference(user["userId"], data)
    if not success:
        return Response(
            content='{"success": false, "message": "' + msg + '", "errors": ' + str(errors).replace("'", '"') + '}',
            status_code=422,
            media_type="application/json"
        )
    return {"success": True, "message": msg, "reference": created}


@app.put("/api/references/{ref_id}")
def update_reference(ref_id: str, data: Dict[str, Any], user: Dict[str, Any] = Depends(get_current_user)):
    success, msg, errors, updated = ReferenceService.edit_reference(user["userId"], ref_id, data)
    if not success:
        return Response(
            content='{"success": false, "message": "' + msg + '", "errors": ' + str(errors).replace("'", '"') + '}',
            status_code=422,
            media_type="application/json"
        )
    return {"success": True, "message": msg, "reference": updated}


@app.get("/api/references/{ref_id}/cascade-check")
def cascade_check(ref_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    check = ReferenceService.check_cascade_citations(user["userId"], ref_id)
    return {"success": True, "cascade": check}


@app.delete("/api/references/{ref_id}")
def delete_reference(ref_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    success, msg = ReferenceService.delete_reference(user["userId"], ref_id)
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"success": True, "message": msg}


# --- 4. Collections (ICollection) ---

@app.get("/api/collections")
def list_collections(user: Dict[str, Any] = Depends(get_current_user)):
    cols = CollectionService.get_user_collections(user["userId"])
    return {"success": True, "collections": cols}


@app.post("/api/collections")
def create_collection(req: CreateCollectionRequest, user: Dict[str, Any] = Depends(get_current_user)):
    success, msg, col = CollectionService.create_collection(user["userId"], req.name)
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"success": True, "message": msg, "collection": col}


@app.put("/api/collections/{col_id}")
def rename_collection(col_id: str, req: RenameCollectionRequest, user: Dict[str, Any] = Depends(get_current_user)):
    success, msg = CollectionService.rename_collection(user["userId"], col_id, req.name)
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"success": True, "message": msg}


@app.delete("/api/collections/{col_id}")
def delete_collection(col_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    success, msg = CollectionService.delete_collection(user["userId"], col_id)
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"success": True, "message": msg}


@app.post("/api/collections/{col_id}/references/{ref_id}")
def add_ref_to_collection(col_id: str, ref_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    success, msg = CollectionService.add_reference_to_collection(user["userId"], col_id, ref_id)
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"success": True, "message": msg}


@app.delete("/api/collections/{col_id}/references/{ref_id}")
def remove_ref_from_collection(col_id: str, ref_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    success, msg = CollectionService.remove_reference_from_collection(user["userId"], col_id, ref_id)
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"success": True, "message": msg}


# --- 5. Document Editor & Citation Insertion (IDocument / IBibliography) ---

@app.get("/api/documents")
def list_documents(user: Dict[str, Any] = Depends(get_current_user)):
    docs = DocumentService.get_user_documents(user["userId"])
    return {"success": True, "documents": docs}


@app.get("/api/documents/{doc_id}")
def get_document(doc_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    doc = DocumentService.get_document_by_id(user["userId"], doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    return {"success": True, "document": doc}


@app.post("/api/documents")
def create_document(req: CreateDocumentRequest, user: Dict[str, Any] = Depends(get_current_user)):
    success, msg, doc = DocumentService.create_document(user["userId"], req.title, req.citationStyle or "APA")
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"success": True, "message": msg, "document": doc}


@app.put("/api/documents/{doc_id}")
def save_document(doc_id: str, req: SaveDocumentRequest, user: Dict[str, Any] = Depends(get_current_user)):
    success, msg, doc = DocumentService.save_document(user["userId"], doc_id, req.title, req.content, req.citationStyle)
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"success": True, "message": msg, "document": doc}


@app.delete("/api/documents/{doc_id}")
def delete_document(doc_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    success, msg = DocumentService.delete_document(user["userId"], doc_id)
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"success": True, "message": msg}


@app.post("/api/documents/{doc_id}/citations")
def insert_citation(doc_id: str, req: InsertCitationRequest, user: Dict[str, Any] = Depends(get_current_user)):
    success, msg, doc = DocumentService.insert_citation(
        owner_id=user["userId"],
        document_id=doc_id,
        reference_id=req.referenceId,
        content_with_token=req.contentWithToken
    )
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"success": True, "message": msg, "document": doc}


@app.delete("/api/documents/{doc_id}/citations/{citation_id}")
def remove_citation(doc_id: str, citation_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    success, msg, doc = DocumentService.remove_citation(user["userId"], doc_id, citation_id)
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"success": True, "message": msg, "document": doc}


@app.post("/api/documents/{doc_id}/style")
def switch_citation_style(doc_id: str, req: SwitchStyleRequest, user: Dict[str, Any] = Depends(get_current_user)):
    success, msg, doc = DocumentService.change_citation_style(user["userId"], doc_id, req.citationStyle)
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"success": True, "message": msg, "document": doc}


# --- 6. Export (IExport) ---

@app.get("/api/documents/{doc_id}/export")
def export_document_endpoint(
    doc_id: str,
    format: str = Query("PDF"),
    standalone: bool = Query(False),
    user: Dict[str, Any] = Depends(get_current_user)
):
    success, err, file_bytes, file_name, mime_type = ExportService.export_document(
        owner_id=user["userId"],
        document_id=doc_id,
        export_format=format,
        standalone_bibliography=standalone
    )
    if not success:
        raise HTTPException(status_code=400, detail=err)

    return Response(
        content=file_bytes,
        media_type=mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="{file_name}"',
            "Access-Control-Expose-Headers": "Content-Disposition"
        }
    )


# --- 7. Admin & Audit Portal ---

@app.get("/api/admin/metrics")
def admin_metrics(admin: Dict[str, Any] = Depends(require_admin)):
    metrics = AdminService.get_system_metrics()
    return {"success": True, "metrics": metrics}


@app.get("/api/admin/users")
def admin_list_users(admin: Dict[str, Any] = Depends(require_admin)):
    users = AdminService.get_all_users()
    return {"success": True, "users": users}


@app.put("/api/admin/users/{target_id}/status")
def admin_update_user_status(target_id: str, req: UpdateUserStatusRequest, admin: Dict[str, Any] = Depends(require_admin)):
    success, msg = AdminService.update_user_status(admin["userId"], target_id, req.accountStatus)
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"success": True, "message": msg}


@app.put("/api/admin/users/{target_id}/role")
def admin_update_user_role(target_id: str, req: UpdateUserRoleRequest, admin: Dict[str, Any] = Depends(require_admin)):
    success, msg = AdminService.update_user_role(admin["userId"], target_id, req.role)
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"success": True, "message": msg}


@app.delete("/api/admin/users/{target_id}")
def admin_delete_user(target_id: str, admin: Dict[str, Any] = Depends(require_admin)):
    success, msg = AdminService.delete_user(admin["userId"], target_id)
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"success": True, "message": msg}


@app.get("/api/admin/audit-logs")
def admin_audit_logs(query: Optional[str] = None, limit: int = 100, admin: Dict[str, Any] = Depends(require_admin)):
    logs = AdminService.get_audit_logs(query, limit)
    return {"success": True, "logs": logs}


# --- Static Files & SPA Route ---

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def serve_index():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "CiteNest API is running. UI building..."}

"""Progress and retry API for document AI term extraction."""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.providers import PROVIDERS
from app.models.database import Document, Project, ModelConfig
from app.services.term_discovery import ACTIVE, resolve_model, queue_document, run_document_discovery

router = APIRouter(prefix="/terminology/project", tags=["术语识别"])


class DiscoveryRequest(BaseModel):
    provider: str = Field(default="", max_length=100)
    model: str = Field(default="", max_length=200)


@router.get("/{project_id}/discovery")
def discovery_status(project_id: int, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    options = []
    for row in db.query(ModelConfig).filter_by(is_active=True).all():
        if row.provider in PROVIDERS and getattr(settings, f"{row.provider}_api_key", ""):
            options.append({"provider": row.provider, "model": row.model_id, "label": row.name or row.model_id})
    for provider, defaults in PROVIDERS.items():
        model = settings.custom_model_id if provider == "custom" else defaults["model"]
        if getattr(settings, f"{provider}_api_key", "") and model and not any(o["provider"] == provider and o["model"] == model for o in options):
            options.append({"provider": provider, "model": model, "label": f"{provider} · {model}"})
    selected = None
    try:
        provider, model = resolve_model(project)
        selected = {"provider": provider, "model": model}
        if not any(o["provider"] == provider and o["model"] == model for o in options):
            options.insert(0, {**selected, "label": f"{provider} · {model}"})
    except ValueError:
        pass
    return {"models": options, "selected_model": selected, "documents": [
        {"id": d.id, "filename": d.original_filename, "parse_status": d.parse_status,
         "parse_error": d.parse_error, "analysis": d.terminology_analysis or {"status": "not_started"}}
        for d in db.query(Document).filter_by(project_id=project_id).order_by(Document.created_at).all()
    ]}


@router.post("/{project_id}/discovery")
def start_discovery(project_id: int, data: DiscoveryRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    try:
        provider, model = resolve_model(project, data.provider, data.model)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    docs = db.query(Document).filter_by(project_id=project_id).all()
    queued = []
    for doc in docs:
        if (doc.terminology_analysis or {}).get("status") == "done":
            continue
        if queue_document(db, doc, provider, model):
            queued.append(doc.id)
            background_tasks.add_task(run_document_discovery, doc.id)
    return {"queued_document_ids": queued, "message": "任务已开始，可在术语页查看进度" if queued else "没有待处理文档，任务可能已完成、运行中或尚未解析"}

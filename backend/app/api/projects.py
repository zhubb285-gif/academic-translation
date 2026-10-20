"""
项目管理 API
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from app.core.database import get_db
from app.models.database import Project, Journal
from app.schemas.schemas import ProjectCreate, ProjectUpdate, ProjectResponse

router = APIRouter(prefix="/projects", tags=["项目管理"])


@router.post("", response_model=ProjectResponse, summary="创建翻译项目")
def create_project(data: ProjectCreate, db: Session = Depends(get_db)):
    if data.journal_id and not db.get(Journal, data.journal_id):
        raise HTTPException(status_code=400, detail="目标期刊不存在")
    project = Project(**data.model_dump())
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("", response_model=List[ProjectResponse], summary="获取所有项目")
def list_projects(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    return db.query(Project).order_by(Project.updated_at.desc()).offset(skip).limit(limit).all()


@router.get("/{project_id}", response_model=ProjectResponse, summary="获取项目详情")
def get_project(project_id: int, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


@router.put("/{project_id}", response_model=ProjectResponse, summary="更新项目信息")
def update_project(project_id: int, data: ProjectUpdate, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    values = data.model_dump(exclude_unset=True)
    if values.get("journal_id") and not db.get(Journal, values["journal_id"]):
        raise HTTPException(status_code=400, detail="目标期刊不存在")
    for field, value in values.items():
        if value is None and field != "journal_id":
            continue
        setattr(project, field, value)
    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}", summary="删除项目")
def delete_project(project_id: int, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    from app.models.database import Decision, ReviewIssue, QualityReport, TerminologyEntry, SourceEvidence, Segment, Document

    # 彻底清理所有子级关联数据
    db.query(Decision).filter(Decision.project_id == project_id).delete()
    db.query(ReviewIssue).filter(ReviewIssue.project_id == project_id).delete()
    db.query(QualityReport).filter(QualityReport.project_id == project_id).delete()

    terms = db.query(TerminologyEntry).filter(TerminologyEntry.project_id == project_id).all()
    for t in terms:
        db.query(SourceEvidence).filter(SourceEvidence.term_id == t.id).delete()
    db.query(TerminologyEntry).filter(TerminologyEntry.project_id == project_id).delete()
    db.query(Segment).filter(Segment.project_id == project_id).delete()
    db.query(Document).filter(Document.project_id == project_id).delete()

    db.delete(project)
    db.commit()
    return {"success": True, "message": "项目已删除"}


@router.get("/{project_id}/stats", summary="获取项目统计信息")
def get_project_stats(project_id: int, db: Session = Depends(get_db)):
    from app.models.database import Segment, ReviewIssue
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    from sqlalchemy import func
    stats = db.query(
        func.count(Segment.id).label("total"),
        func.sum(
            (Segment.translated_text != None).cast(db.bind.dialect.ischema_names.get("INTEGER", int))
            if False else 1
        ).label("translated"),
    ).filter(Segment.project_id == project_id).first()

    segments = db.query(Segment).filter(Segment.project_id == project_id).all()
    total = len(segments)
    translated = sum(1 for s in segments if s.translated_text)
    approved = sum(1 for s in segments if s.status == "approved")
    flagged = sum(1 for s in segments if s.has_flag)

    issues = db.query(ReviewIssue).filter(ReviewIssue.project_id == project_id).all()

    return {
        "project_id": project_id,
        "segments": {
            "total": total,
            "translated": translated,
            "approved": approved,
            "flagged": flagged,
            "pending": total - translated,
        },
        "issues": {
            "total": len(issues),
            "by_severity": {
                "critical": sum(1 for i in issues if i.severity == "critical"),
                "major": sum(1 for i in issues if i.severity == "major"),
                "minor": sum(1 for i in issues if i.severity == "minor"),
            },
            "by_status": {
                "pending": sum(1 for i in issues if i.human_status == "pending"),
                "resolved": sum(1 for i in issues if i.human_status in ("accepted", "rejected", "modified")),
            },
        },
        "progress_percent": round(translated / total * 100, 1) if total > 0 else 0,
    }

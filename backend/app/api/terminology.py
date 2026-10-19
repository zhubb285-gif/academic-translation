"""
术语管理 API
术语创建、查证记录、信源证据、确认状态管理
"""
import json
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.database import TerminologyEntry, SourceEvidence
from app.schemas.schemas import (
    TermCreate, TermUpdate, TermResponse,
    EvidenceCreate, EvidenceResponse,
)
from app.services.source_research import source_research_service
from app.services.source_links import present_card, source_link, search_link
from app.services.source_catalog import find_source, source_catalog

router = APIRouter(prefix="/terminology", tags=["术语管理"])


@router.get("/{term_id}/sources", summary="按术语生成完整一级到三级信源检索清单")
def get_term_sources(term_id: int, candidate: str = "", db: Session = Depends(get_db)):
    term = db.query(TerminologyEntry).filter(TerminologyEntry.id == term_id).first()
    if not term:
        raise HTTPException(status_code=404, detail="术语不存在")
    return {"term": term.source_term, "sources": source_catalog(term.source_term, candidate)}


@router.post("/project/{project_id}", response_model=TermResponse, summary="创建术语条目")
def create_term(project_id: int, data: TermCreate, db: Session = Depends(get_db)):
    # 检查是否已存在
    existing = db.query(TerminologyEntry).filter(
        TerminologyEntry.project_id == project_id,
        TerminologyEntry.source_term == data.source_term,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"术语「{data.source_term}」已存在")

    term = TerminologyEntry(project_id=project_id, **data.model_dump())
    db.add(term)
    db.commit()
    db.refresh(term)
    return _term_to_response(term, db)


@router.get("/project/{project_id}", summary="获取项目所有术语")
def list_terms(
    project_id: int,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    query = db.query(TerminologyEntry).filter(TerminologyEntry.project_id == project_id)
    if status:
        query = query.filter(TerminologyEntry.status == status)
    terms = query.order_by(TerminologyEntry.created_at.desc()).all()
    return [_term_to_response(t, db) for t in terms]


@router.get("/{term_id}", summary="获取术语详情（含证据）")
def get_term(term_id: int, db: Session = Depends(get_db)):
    term = db.query(TerminologyEntry).filter(TerminologyEntry.id == term_id).first()
    if not term:
        raise HTTPException(status_code=404, detail="术语不存在")
    return _term_to_response(term, db)


@router.put("/{term_id}", summary="更新术语状态/确认译法")
def update_term(term_id: int, data: TermUpdate, db: Session = Depends(get_db)):
    term = db.query(TerminologyEntry).filter(TerminologyEntry.id == term_id).first()
    if not term:
        raise HTTPException(status_code=404, detail="术语不存在")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(term, field, value)
    db.commit()
    db.refresh(term)
    return _term_to_response(term, db)


@router.delete("/{term_id}", summary="删除术语")
def delete_term(term_id: int, db: Session = Depends(get_db)):
    term = db.query(TerminologyEntry).filter(TerminologyEntry.id == term_id).first()
    if not term:
        raise HTTPException(status_code=404, detail="术语不存在")
    db.delete(term)
    db.commit()
    return {"success": True}


@router.post("/{term_id}/auto-research", summary="自动读取术语在线词条，区分完整与核心词证据")
async def auto_research_term(term_id: int, db: Session = Depends(get_db)):
    term = db.query(TerminologyEntry).filter(TerminologyEntry.id == term_id).first()
    if not term:
        raise HTTPException(status_code=404, detail="术语不存在")

    research_result = await source_research_service.execute_progressive_research(
        source_term=term.source_term,
        domain=term.domain
    )

    evidences = research_result.get("evidences", [])
    cards = research_result.get("cards", [])
    decomposition = research_result.get("decomposition", [])
    is_exact = research_result.get("is_exact", False)

    candidates = list(term.candidate_translations or [])
    for c in research_result.get("candidates", []):
        if c and c not in candidates:
            candidates.append(c)

    # 查重集合
    existing_keys = {
        (e.source_url, e.candidate_translation)
        for e in db.query(SourceEvidence).filter(SourceEvidence.term_id == term.id).all()
    }

    added_count = 0
    for ev_data in evidences:
        cand = (ev_data.get("candidate_translation") or "").strip()
        key = (ev_data.get("source_url"), cand or None)
        if key in existing_keys:
            continue

        evidence = SourceEvidence(
            term_id=term.id,
            source_level=ev_data["source_level"],
            source_type=ev_data.get("source_type"),
            source_name=ev_data.get("source_name"),
            source_url=ev_data.get("source_url"),
            evidence_text=ev_data.get("evidence_text"),
            candidate_translation=cand or None,
            published_date=ev_data.get("published_date"),
            is_valid=ev_data.get("is_valid", False),
            verified_by="auto:termonline-v2" if ev_data.get("source_checked") else None,
            verified_at=datetime.utcnow() if ev_data.get("source_checked") else None,
        )
        db.add(evidence)
        existing_keys.add(key)
        added_count += 1

    term.candidate_translations = candidates

    # Finding an entry does not replace the user's final translation decision.

    # 将结构化卡片与拆解过程存入 notes 字段（JSON 格式），使前端随时可重现完整的证据卡
    notes_payload = {
        "source_verification_version": research_result.get("source_verification_version"),
        "lookup_trace": research_result.get("lookup_trace", []),
        "is_exact": is_exact,
        "match_type": research_result.get("match_type"),
        "core_term": research_result.get("core_term"),
        "decomposition": decomposition,
        "recommendation_reason": research_result.get("recommendation_reason"),
        "cards": cards,
        "workflow_steps": [
            {"step": 1, "name": "完整词语检索", "desc": "搜索完整词条", "status": "hit" if is_exact else "unverified"},
            {"step": 2, "name": "语义拆解分析", "desc": "识别核心专业术语与范围限定", "status": "skipped" if is_exact else "done"},
            {"step": 3, "name": "官方出处核对", "desc": "仅将实际读取的条目作为证据；其他来源需继续核对", "status": "done" if evidences else "pending"},
            {"step": 4, "name": "证据卡生成", "desc": "整理推荐译法、适用领域、原文、链接、推荐理由", "status": "done"}
        ]
    }
    term.notes = json.dumps(notes_payload, ensure_ascii=False)

    db.commit()
    db.refresh(term)
    return {
        "success": True,
        "added_evidence_count": added_count,
        "term": _term_to_response(term, db)
    }



# ============================================================
# 信源证据 API
# ============================================================

@router.post("/{term_id}/evidence", response_model=EvidenceResponse, summary="添加信源证据")
def add_evidence(term_id: int, data: EvidenceCreate, db: Session = Depends(get_db)):
    term = db.query(TerminologyEntry).filter(TerminologyEntry.id == term_id).first()
    if not term:
        raise HTTPException(status_code=404, detail="术语不存在")

    source = find_source(data.source_url or "", data.source_name or "")
    if source and source["blocked"]:
        raise HTTPException(status_code=400, detail="该网站属于三级弱源，不能添加为译法证据，请使用一级或二级来源")
    values = data.model_dump()
    if source:
        values["source_level"] = source["source_level"]
        values["source_url"] = data.source_url or source["url"]
    evidence = SourceEvidence(term_id=term_id, **values)
    db.add(evidence)

    # 自动更新术语的候选译法列表
    candidates = term.candidate_translations or []
    if data.candidate_translation and data.candidate_translation not in candidates:
        candidates.append(data.candidate_translation)
        term.candidate_translations = candidates

    db.commit()
    db.refresh(evidence)
    return _evidence_to_response(evidence, term.source_term)


@router.get("/{term_id}/evidence", response_model=List[EvidenceResponse], summary="获取术语所有证据")
def list_evidence(term_id: int, db: Session = Depends(get_db)):
    term = db.query(TerminologyEntry).filter(TerminologyEntry.id == term_id).first()
    if not term:
        raise HTTPException(status_code=404, detail="术语不存在")
    evidences = db.query(SourceEvidence).filter(
        SourceEvidence.term_id == term_id
    ).order_by(SourceEvidence.source_level).all()
    return [_evidence_to_response(e, term.source_term) for e in evidences]


@router.put("/evidence/{evidence_id}/verify", summary="确认/标记证据有效性")
def verify_evidence(
    evidence_id: int,
    is_valid: bool = True,
    verifier: str = "user",
    db: Session = Depends(get_db),
):
    ev = db.query(SourceEvidence).filter(SourceEvidence.id == evidence_id).first()
    if not ev:
        raise HTTPException(status_code=404, detail="证据不存在")
    source = find_source(ev.source_url or "", ev.source_name or "")
    if is_valid and source and source["blocked"]:
        raise HTTPException(status_code=400, detail="三级弱源不能标记为有效译法证据")
    ev.is_valid = is_valid
    ev.verified_by = verifier
    ev.verified_at = datetime.utcnow()
    db.commit()
    return {"success": True, "is_valid": is_valid}


@router.post("/{term_id}/confirm", summary="确认术语最终译法")
def confirm_term(
    term_id: int,
    confirmed_translation: str,
    db: Session = Depends(get_db),
):
    term = db.query(TerminologyEntry).filter(TerminologyEntry.id == term_id).first()
    if not term:
        raise HTTPException(status_code=404, detail="术语不存在")
    term.confirmed_translation = confirmed_translation
    term.status = "confirmed"
    db.commit()
    return {"success": True, "confirmed_translation": confirmed_translation}


# ============================================================
# 辅助函数
# ============================================================

def _evidence_to_response(evidence: SourceEvidence, term: str) -> dict:
    """Use the same current-term links on create, list, and detail responses."""
    result = EvidenceResponse.model_validate(evidence).model_dump()
    source = find_source(evidence.source_url or "", evidence.source_name or "")
    url = evidence.source_url or (source["url"] if source else "")
    result["original_url"] = url if source_link(url, term)["source_url"] else ""
    result.update(source_link(url, term, evidence.candidate_translation or ""))
    result.update(search_link(url, term, evidence.candidate_translation or ""))
    result["source_blocked"] = bool(source and source["blocked"])
    if source:
        result["source_level"] = source["source_level"]
        if evidence.source_name == source.get("original_name"):
            result["source_name"] = source["name"]
    result["source_checked"] = bool(evidence.verified_at and evidence.is_valid and evidence.evidence_text
                                    and result["link_kind"] == "entry" and not result["source_blocked"])
    return result


def _term_to_response(term: TerminologyEntry, db: Session) -> dict:
    evidences = db.query(SourceEvidence).filter(
        SourceEvidence.term_id == term.id
    ).order_by(SourceEvidence.source_level).all()

    cards = []
    decomposition = None
    parsed_meta = {}
    if term.notes:
        try:
            parsed_meta = json.loads(term.notes)
            if isinstance(parsed_meta, dict):
                cards = parsed_meta.get("cards", [])
                decomposition = parsed_meta.get("decomposition")
            else:
                parsed_meta = {"raw_notes": term.notes}
        except Exception:
            parsed_meta = {"raw_notes": term.notes}

    # Historical claims do not prove that a source page was actually retrieved.
    if not cards and evidences:
        for ev in evidences:
            cards.append({
                "recommended_translation": ev.candidate_translation or term.confirmed_translation or "",
                "domain": term.domain or "通用学术",
                "evidence_text": ev.evidence_text or "",
                "source_url": ev.source_url or "",
                "source_name": ev.source_name or ev.source_type or "权威信源",
                "source_level": ev.source_level,
                "recommendation_reason": "人工记录的来源，请打开详情核对。",
                "match_type": "manual",
                "status_tag": "人工已核对" if ev.verified_at and ev.is_valid else "待查证",
                "source_checked": bool(ev.verified_at and ev.is_valid),
                "decomposition": None
            })

    v2 = parsed_meta.get("source_verification_version") == 2
    if not v2 and decomposition:
        decomposition = [{**part, "evidence": "历史语言分析，待重新查证"} for part in decomposition if isinstance(part, dict)]
    cards = [present_card(card, term.source_term, trusted=(v2 or card.get("match_type") == "manual") and card.get("source_checked", False)) for card in cards]

    return {
        "id": term.id,
        "source_term": term.source_term,
        "domain": term.domain,
        "candidate_translations": term.candidate_translations or [],
        "confirmed_translation": term.confirmed_translation,
        "status": term.status.value if hasattr(term.status, "value") else str(term.status),
        "notes": term.notes,
        "created_at": term.created_at,
        "cards": cards,
        "decomposition": decomposition,
        "research_summary": parsed_meta,
        "evidence": [_evidence_to_response(e, term.source_term) for e in evidences],
    }

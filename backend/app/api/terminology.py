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
from app.models.database import TerminologyEntry, SourceEvidence, Project, Journal
from app.services.source_catalog import source_catalog, find_source
from app.schemas.schemas import (
    TermCreate, TermUpdate, TermResponse,
    EvidenceCreate, EvidenceResponse,
)
from app.services.source_research import source_research_service
from app.services.source_links import present_card, source_link, search_link

router = APIRouter(prefix="/terminology", tags=["术语管理"])


@router.get("/{term_id}/sources", summary="按术语生成信源检索清单")
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


@router.post("/{term_id}/auto-research", summary="依据信源优先级自动检索权威证据")
async def auto_research_term(term_id: int, db: Session = Depends(get_db)):
    term = db.query(TerminologyEntry).filter(TerminologyEntry.id == term_id).first()
    if not term:
        raise HTTPException(status_code=404, detail="术语不存在")

    project = db.get(Project, term.project_id)
    journal = db.get(Journal, project.journal_id) if project and project.journal_id else None
    previous_notes = _notes(term.notes)
    occurrences = previous_notes.get("ai_extraction", [])
    source_context = "\n".join(item.get("context", "") for item in occurrences[:3] if isinstance(item, dict))
    research_result = await source_research_service.execute_progressive_research(
        source_term=term.source_term,
        domain=term.domain or (project.domain if project else None),
        context="\n".join(filter(None, [source_context, project.description if project else None])),
        candidates=list(term.candidate_translations or []),
        preferred_journal=journal.name if journal else "",
    )
    term.domain = research_result.get("domain") or term.domain

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
            is_valid=ev_data.get("is_valid", bool(ev_data.get("source_checked"))),
            verified_by="auto:journal-research-v3" if ev_data.get("source_checked") else None,
            verified_at=datetime.utcnow() if ev_data.get("source_checked") else None,
        )
        db.add(evidence)
        existing_keys.add(key)
        added_count += 1

    term.candidate_translations = candidates

    # Finding an entry does not replace the user's final translation decision.

    # 将结构化卡片与拆解过程存入 notes 字段（JSON 格式），使前端随时可重现完整的证据卡
    previous_notes = _notes(term.notes)
    notes_payload = {
        "user_notes": previous_notes.get("user_notes", ""),
        "human_decisions": previous_notes.get("human_decisions", []),
        "ai_extraction": previous_notes.get("ai_extraction", []),
        "source_verification_version": research_result.get("source_verification_version"),
        "lookup_trace": research_result.get("lookup_trace", []),
        "is_exact": is_exact,
        "match_type": research_result.get("match_type"),
        "core_term": research_result.get("core_term"),
        "decomposition": decomposition,
        "recommendation_reason": research_result.get("recommendation_reason"),
        "cards": cards,
        "comparison_status": research_result.get("comparison_status"),
        "requires_human_decision": True,
        "coverage_note": research_result.get("coverage_note"),
        "policy": research_result.get("policy"),
        "workflow_steps": [
            {"step": 1, "name": "期刊文章优先检索", "desc": "从实际全文或摘要中查找英文用法", "status": "hit" if research_result.get("journal_cards") else "unverified"},
            {"step": 2, "name": "逐级查找信源", "desc": "一级起查，完整命中停止向二级查找，三级禁用", "status": "done"},
            {"step": 3, "name": "两侧原文对比", "desc": "区分英文出现、核心词出处与完整双语对应", "status": "done" if evidences else "pending"},
            {"step": 4, "name": "人工最终裁决", "desc": "确认译法、理由与证据快照", "status": "pending"}
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

    values = data.model_dump()
    source = find_source(data.source_url or "", data.source_name or "")
    if data.source_level >= 3 or (source and source["blocked"]):
        raise HTTPException(status_code=400, detail="三级及以下信源不可作为译法证据")
    if source:
        values["source_level"] = source["source_level"]
    # Manually pasted text is not automatically a verified quotation.
    evidence = SourceEvidence(term_id=term_id, is_valid=False, **values)
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
    if is_valid and (ev.source_level >= 3 or (source and source["blocked"])):
        raise HTTPException(status_code=400, detail="三级及以下信源不能标记为可采信")
    if is_valid and (not ev.evidence_text or not ev.candidate_translation or source_link(ev.source_url or "", "", ev.candidate_translation)["link_kind"] != "entry"):
        raise HTTPException(status_code=400, detail="请先填写来源详情页、证据原文和对应英文，搜索结果页不能标记为已核验证据")
    if source:
        ev.source_level = source["source_level"]
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
    reason: str = "",
):
    term = db.query(TerminologyEntry).filter(TerminologyEntry.id == term_id).first()
    if not term:
        raise HTTPException(status_code=404, detail="术语不存在")
    confirmed_translation = confirmed_translation.strip()
    if not confirmed_translation:
        raise HTTPException(status_code=400, detail="请填写最终译法")
    metadata = _notes(term.notes)
    card_assessments = {(card.get("source_url"), card.get("recommended_translation")): card
                        for card in metadata.get("cards", []) if isinstance(card, dict)}
    history = metadata.get("human_decisions", [])
    history.append({"translation": confirmed_translation, "previous_translation": term.confirmed_translation,
                    "reason": reason.strip(), "decided_at": datetime.utcnow().isoformat(),
                    "evidence_snapshot": [{"source_url": e.source_url, "translation": e.candidate_translation,
                                           "quote": e.evidence_text, "source_level": e.source_level,
                                           "assessment": card_assessments.get((e.source_url, e.candidate_translation), {}).get("recommendation_reason"),
                                           "match_type": card_assessments.get((e.source_url, e.candidate_translation), {}).get("match_type")}
                                          for e in term.evidence if e.is_valid and e.source_level < 3
                                          and not (find_source(e.source_url or "", e.source_name or "") or {}).get("blocked")]})
    metadata["human_decisions"] = history
    metadata["requires_human_decision"] = False
    term.notes = json.dumps(metadata, ensure_ascii=False)
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
    result.update(source_link(evidence.source_url or "", term, evidence.candidate_translation or ""))
    result.update(search_link(evidence.source_url or "", term, evidence.candidate_translation or ""))
    result["source_checked"] = bool(evidence.verified_at and evidence.is_valid)
    source = find_source(evidence.source_url or "", evidence.source_name or "")
    result["source_blocked"] = evidence.source_level >= 3 or bool(source and source["blocked"])
    result["source_checked"] = result["source_checked"] and not result["source_blocked"]
    result["evidence_group"] = "journal" if evidence.source_type == "journal_usage" else "authority"
    return result


def _notes(value: str | None) -> dict:
    try:
        data = json.loads(value or "{}")
        return data if isinstance(data, dict) else {"user_notes": value or ""}
    except (TypeError, ValueError):
        return {"user_notes": value or ""}


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
                "decomposition": None,
                "evidence_group": "journal" if ev.source_type == "journal_usage" else "authority",
            })

    v2 = parsed_meta.get("source_verification_version") in (2, 3)
    if not v2 and decomposition:
        decomposition = [{**part, "evidence": "历史语言分析，待重新查证"} for part in decomposition if isinstance(part, dict)]
    # Notes are user-editable: a version flag in notes cannot authenticate a quotation.
    by_key = {(e.source_url, e.candidate_translation): e for e in evidences}
    safe_cards = []
    for card in cards:
        if not isinstance(card, dict):
            continue
        record = by_key.get((card.get("source_url"), card.get("recommended_translation")))
        trusted = bool(record and record.verified_at and record.is_valid and record.evidence_text == card.get("evidence_text"))
        safe_cards.append(present_card(card, term.source_term, trusted=trusted and (v2 or card.get("match_type") == "manual")))
    cards = safe_cards
    # Reflect human invalidation on persisted cards rather than resurrecting an auto quote.
    for card in cards:
        record = by_key.get((card.get("source_url"), card.get("recommended_translation")))
        if record and not record.is_valid:
            card.update(source_checked=False, evidence_text="", status_tag="已标记无效", source_blocked=True)

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
        "journal_cards": [c for c in cards if c.get("evidence_group") == "journal"],
        "authority_cards": [c for c in cards if c.get("evidence_group") != "journal"],
        "decomposition": decomposition,
        "research_summary": parsed_meta,
        "evidence": [_evidence_to_response(e, term.source_term) for e in evidences],
    }

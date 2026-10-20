"""期刊优先术语查证：实际文章用法 → 一级信源 → 二级信源 → 人工裁决。
信源分级以项目 sources.json 为准；三级仅列出，不参与检索或采信。
期刊英文表达与中文术语的含义对应由人工核定。
"""
import json
import re
import logging
from typing import List, Dict, Optional, Any
import httpx
import html
from urllib.parse import urlencode
from app.services.source_links import source_link
from app.services.journal_library import search_usage, CATALOG
from app.services.source_catalog import source_catalog, SOURCES
from app.services.catalog_retriever import retrieve_level

from app.core.config import settings

logger = logging.getLogger(__name__)

# ============================================================
# 专业领域预设权威信源库 (Source Repositories)
# ============================================================

AUTHORITY_SOURCES_REGISTRY = SOURCES

# 常见领域关键词映射
DOMAIN_KEYWORDS = {
    "地质资源与地质工程": ["地震", "地层", "勘探", "盆地", "断层", "沉积", "岩性", "构造", "测井"],
    "马克思主义理论": ["马克思", "唯物", "辩证", "剩余价值", "生产关系", "历史唯物主义"],
    "法学": ["法学", "法律", "侵权", "刑法", "民法", "行政法", "诉讼", "法治", "知识产权"],
    "计算机科学": ["神经网络", "深度学习", "注意力机制", "强化学习", "算法", "分类器", "大语言模型", "特征提取", "嵌入", "多模态"],
    "石油与天然气工程": ["水力压裂", "储层", "压裂液", "固井", "完井", "钻井", "渗透率", "孔隙度", "采收率", "页岩气"],
    "材料科学": ["晶粒", "晶相", "抗拉强度", "屈服极限", "退火", "淬火", "复合材料", "聚合物", "纳米管", "显微硬度"],
    "生物医学": ["靶点", "细胞因子", "受体", "转录", "表达", "克隆", "表型", "基因组", "凋亡", "抗体"],
    "环境科学": ["碳中和", "温室气体", "富营养化", "降解", "生物质", "颗粒物", "重金属", "生命周期评估"],
}

# 离线候选译法，仅用于检索提示，不作为官方出处或证据。
TERM_TRANSLATION_HINTS = {'水力压裂': ['hydraulic fracturing'], '四川石油学院': ['Sichuan Petroleum Institute'], '西南石油学院': ['Southwest Petroleum Institute'], '西南石油大学': ['Southwest Petroleum University'], '三牙轮钻头': ['tri-cone bit'], '双一流': ['Double First-Class initiative'], '脱贫攻坚楷模': ['National Model for Poverty Alleviation'], '射流破碎钻头': ['jet breaking bit'], '天然气水合物固态流化试采': ['solid fluidized trial production of natural gas hydrate'], '注意力机制': ['attention mechanism'], '天然气水合物': ['natural gas hydrate'], '生命周期评价': ['Life Cycle Assessment (LCA)']}
TERM_TRANSLATION_HINTS.update({
    "深度学习": ["deep learning"], "神经网络": ["neural network"], "机器学习": ["machine learning"],
    "储层": ["reservoir"], "渗透率": ["permeability"], "孔隙度": ["porosity"], "页岩气": ["shale gas"],
    "采收率": ["oil recovery"], "钻井液": ["drilling fluid"], "固井": ["cementing"],
    "地震反演": ["seismic inversion"], "地质勘探": ["geological exploration"], "沉积盆地": ["sedimentary basin"],
    "碳捕集": ["carbon capture"], "催化剂": ["catalyst"], "纳米材料": ["nanomaterials"],
})


class SourceResearchService:
    """权威信源查证与检索服务"""

    def infer_domain(self, term: str, context: Optional[str] = None) -> str:
        """根据术语及上下文推断学科领域"""
        text = f"{term} {context or ''}"
        for domain, keywords in DOMAIN_KEYWORDS.items():
            for kw in keywords:
                if kw in text:
                    return domain
        return "通用学术"

    def _scope_mismatch(self, entry: dict, domain: str) -> bool:
        """Flag clearly different specialist dictionaries; do not equate spelling with meaning."""
        name = entry.get("source_name", "")
        scopes = [
            (("石油", "天然气", "地质", "地球", "勘探"), ("石油", "天然气", "地质", "海洋", "地理", "化学", "化工", "矿业", "能源", "煤炭", "测绘")),
            (("计算机", "人工智能", "软件"), ("计算机", "信息", "自动", "电子", "通信", "数学", "人工智能")),
            (("法学", "法律", "法理"), ("法律", "法学", "法治")),
            (("马克思", "政治理论"), ("马克思", "政治", "哲学", "社会科学")),
        ]
        known = ("石油", "地质", "海洋", "计算机", "信息", "生物", "医学", "冶金", "材料", "化学", "化工", "数学", "法律", "法学", "哲学", "政治", "生态", "农学", "动物", "植物", "物理", "机械")
        for domain_words, compatible in scopes:
            if any(word in domain for word in domain_words) and any(word in name for word in known):
                return not any(word in name for word in compatible)
        return False

    def get_registered_sources_for_domain(self, domain: str) -> List[Dict[str, Any]]:
        """按优先级升序返回适用于该领域的权威信源表"""
        # Domain-specific availability is described by each source; no second six-source registry.
        return sorted((dict(source) for source in AUTHORITY_SOURCES_REGISTRY if not source["blocked"]), key=lambda item: item["source_level"])

    # ============================================================
    # 4步渐进式查证流水线实现
    # ============================================================

    async def _lookup_official(self, term: str) -> Dict[str, Any]:
        """Read public TermOnline entries; only the 审定公布 database counts as level 1."""
        try:
            async with httpx.AsyncClient(timeout=12.0, headers={
                "Referer": "https://www.termonline.cn/",
                "Origin": "https://www.termonline.cn",
                "User-Agent": "AcademicTranslation/1.0",
            }) as client:
                # The site's public database bootstrap is also required for anonymous search.
                bootstrap = await client.get(
                    "https://api.termonline.cn/main-serve/business/tm/tmDatabase/listFront",
                    params={"pageNo": 1, "pageSize": 10},
                )
                bootstrap.raise_for_status()
                response = await client.get(
                    "https://api.termonline.cn/main-serve/business/tm/tmWord/allSearch",
                    params={"term": term, "match": 2, "sources": "", "pubYears": "",
                            "pageSize": 20, "pageNo": 1, "baseId": 1},
                )
                response.raise_for_status()
                payload = response.json()
                if not payload.get("success") or not isinstance(payload.get("result"), dict):
                    raise ValueError("Invalid public terminology response")
            entries = []
            for group in payload["result"].get("searchResult", []):
                if group.get("id") != "00000000000000000000000000000000":
                    continue
                for item in group.get("result", {}).get("tmWordList", []):
                    clean = lambda value: html.unescape(re.sub(r"<[^>]+>", "", str(value or ""))).strip()
                    if clean(item.get("cn")) != term.strip() or not item.get("id"):
                        continue
                    english = clean(item.get("en"))
                    if not english:
                        continue
                    url = "https://www.termonline.cn/wordDetail?" + urlencode({
                        "termName": clean(item["cn"]), "subject": item["id"], "base": 1,
                    })
                    entries.append({
                        "source_level": 1, "source_type": "术语在线·审定公布名词库",
                        "source_name": "全国科学技术名词审定委员会 · " + clean(item.get("source")),
                        "source_url": url, "candidate_translation": english,
                        "evidence_text": f"规范用词：{term}；英文：{english}。" + clean(item.get("definition")),
                        "published_date": clean(item.get("publishYear")),
                        "is_valid": True, "source_checked": True,
                    })
            return {"status": "found" if entries else "no_exact_match", "entries": entries[:4]}
        except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
            logger.warning("TermOnline lookup failed: %s", type(exc).__name__)
            return {"status": "unavailable", "entries": []}

    async def step2_semantic_decompose(
        self,
        term: str,
        domain: str,
        context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        第2步：没找到时，自动拆解并继续查
        系统结合原句识别：核心专业术语 与 环境/范围/工况限定词
        然后自动查询核心术语、相关表达和同领域权威资料，无需用户手动修改搜索词
        """
        # 1. 尝试大模型智能语义拆解
        llm_res = await self._query_llm_for_decomposition(term, domain, context)
        if llm_res and llm_res.get("core_term"):
            return llm_res

        # 2. 学术知识图谱/规则引擎启发式拆解
        return self._heuristic_decompose(term, domain)

    async def _query_llm_for_decomposition(
        self,
        term: str,
        domain: str,
        context: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """调用大模型执行上下文感知学术复合术语拆解"""
        api_key = settings.deepseek_api_key or settings.openai_api_key or settings.custom_api_key
        base_url = settings.deepseek_base_url if settings.deepseek_api_key else (settings.custom_base_url or settings.openai_base_url)
        model = "deepseek-chat" if settings.deepseek_api_key else (settings.custom_model_id or settings.default_translation_model)

        if not api_key:
            return None

        prompt = f"""请分析学术术语「{term}」（领域：{domain}，上下文：{context or '无'}），
给出核心术语及候选英译。你只提供语言建议，不具备联网查证能力，不要声称官方收录，
不要生成来源、引文、定义证据或网站链接。不确定时将译法留空。
仅输出 JSON：{{"core_term":"核心中文词", "core_translation":"候选英文",
"combined_translation":"完整候选英文", "alt_translation":"备选英文",
"components":[{{"part":"组成部分", "role":"作用", "en":"候选英文", "evidence":"模型建议，待查证"}}]}}"""
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You suggest academic translations without claiming to retrieve evidence."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1,
            "max_tokens": 1000
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(f"{base_url.rstrip('/')}/chat/completions", headers=headers, json=payload)
                if resp.status_code == 200:
                    raw_text = resp.json()["choices"][0]["message"]["content"].strip()
                    raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
                    raw_text = re.sub(r"\s*```$", "", raw_text)
                    return json.loads(raw_text)
        except Exception as e:
            logger.warning(f"LLM 术语拆解请求失败: {e}")
        return None

    def _heuristic_decompose(self, term: str, domain: str) -> Dict[str, Any]:
        """离线知识图谱驱动的学术构词形态拆解引擎"""
        # 预设已知核心学术术语库
        core_dictionary = {'天然气水合物': {'en': 'natural gas hydrate'}, '三牙轮钻头': {'en': 'tri-cone bit'}, '射流破碎钻头': {'en': 'jet breaking bit'}, '固态流化试采': {'en': 'solid fluidized trial production'}, '钻井液': {'en': 'drilling fluid'}, '压裂液': {'en': 'fracturing fluid'}, '页岩气': {'en': 'shale gas'}, '固井': {'en': 'cementing'}, '油气': {'en': 'oil and gas'}}

        # 预设已知限定修饰词与语义角色
        modifiers_dict = [
            ("海洋", "环境或范围限定", "marine", "oceanic"),
            ("深海", "作业水深与海洋环境限定", "deepwater", "deep-sea"),
            ("深水", "作业水深环境限定", "deepwater", "deep-water"),
            ("超深层", "储层埋藏深度限定", "ultra-deep", None),
            ("浅层", "储层层位深度限定", "shallow", None),
            ("高压", "物理工况参数限定", "high-pressure", None),
            ("特高压", "工况等级限定", "ultra-high-voltage", None),
            ("智能化", "技术实现方式限定", "intelligent", "smart"),
            ("绿色", "环保属性限定", "green", "sustainable"),
            ("多级", "结构构造限定", "multi-stage", None),
            ("水平井", "井型轨迹限定", "horizontal well", None),
            ("旋流", "流体流动形态限定", "cyclonic / vortex", None),
        ]

        found_core = None
        matched_core_key = ""
        for k, v in core_dictionary.items():
            if k in term:
                found_core = v
                matched_core_key = k
                break

        components = []
        combined_en = ""
        alt_en = ""

        if found_core:
            prefix_part = term.replace(matched_core_key, "").strip()

            # 匹配修饰限定
            matched_mod = None
            for mod_cn, role, en_main, en_alt in modifiers_dict:
                if mod_cn in prefix_part or mod_cn == prefix_part:
                    matched_mod = (mod_cn, role, en_main, en_alt)
                    break

            if matched_mod:
                mod_cn, role, en_main, en_alt = matched_mod
                components = [
                    {"part": matched_core_key, "role": "核心专业术语", "en": found_core["en"], "evidence": "本地词表建议，待查证"},
                    {"part": mod_cn, "role": role, "en": f"{en_main}{' / ' + en_alt if en_alt else ''}", "evidence": "学术惯用环境/范围限定搭配"}
                ]
                combined_en = f"{en_main} {found_core['en']}"
                if en_alt:
                    alt_en = f"{en_alt} {found_core['en']}"
            else:
                # 无法识别特定修饰词，直接保留
                components = [
                    {"part": matched_core_key, "role": "核心专业术语", "en": found_core["en"], "evidence": "本地词表建议，待查证"},
                    {"part": prefix_part or "限定词", "role": "范围或属性限定", "en": prefix_part, "evidence": "上下文特定限定"}
                ]
                combined_en = f"{prefix_part} {found_core['en']}"
        else:
            # 基础切分
            matched_core_key = term
            combined_en = term
            components = [
                {"part": term, "role": "核心专业术语", "en": term, "evidence": "待进一步查证"}
            ]

        return {
            "core_term": matched_core_key,
            "core_translation": found_core["en"] if found_core else combined_en,
            "combined_translation": combined_en,
            "alt_translation": alt_en,
            "domain": domain,
            "components": components,

        }

    async def _lookup_secondary(self, candidates: List[str], domain: str) -> Dict[str, Any]:
        """Retrieve actual OSTI abstracts, never infer a Chinese-English equivalence."""
        if any(w in domain for w in ("马克思", "法学", "法律", "政治理论")):
            return {"status": "not_applicable", "entries": []}
        entries, failed = [], False
        async with httpx.AsyncClient(timeout=15) as client:
            for candidate in candidates[:2]:
                if not candidate or re.search(r"[\u4e00-\u9fff]", candidate):
                    continue
                try:
                    response = await client.get("https://www.osti.gov/api/v1/records", params={"search": '"' + candidate + '"', "rows": 5})
                    response.raise_for_status()
                    rows = response.json()
                    if not isinstance(rows, list):
                        raise ValueError("Invalid OSTI response")
                    for row in rows:
                        text = html.unescape(re.sub(r"<[^>]+>", " ", row.get("description") or ""))
                        match = re.search(r"(?<!\w)" + re.escape(candidate) + r"(?!\w)", text, re.I)
                        if not match or not str(row.get("osti_id", "")).isdigit():
                            continue
                        quote = text[max(0, match.start()-120):match.end()+230].strip()
                        entries.append({"source_level": 2, "source_type": "secondary_usage", "source_name": "OSTI 美国能源部文献库",
                                        "source_url": "https://www.osti.gov/biblio/" + str(row["osti_id"]),
                                        "title": row.get("title"), "evidence_text": quote, "candidate_translation": candidate,
                                        "source_checked": True, "is_valid": True, "match_type": "english_usage",
                                        "published_date": row.get("publication_date"), "evidence_group": "authority",
                                        "recommendation_reason": "已读取 OSTI 摘要中的完整英文用法，不能据此自动认定中英对应；同库多篇文章也不等于两个独立信源。"})
                except (httpx.HTTPError, ValueError, TypeError):
                    failed = True
        return {"status": "found_usage" if entries else "unavailable" if failed else "no_exact_match", "entries": entries[:5]}

    async def execute_progressive_research(
        self, source_term: str, domain: Optional[str] = None, context: Optional[str] = None,
        candidates: Optional[List[str]] = None, preferred_journal: str = "",
    ) -> Dict[str, Any]:
        """Journal-first usage retrieval, then tier 1 / tier 2 evidence and human comparison."""
        inferred_domain = domain or self.infer_domain(source_term, context)
        candidate_list = list(dict.fromkeys([*(candidates or []), *TERM_TRANSLATION_HINTS.get(source_term, [])]))
        candidate_list = [c.strip() for c in candidate_list if c and not re.search(r"[\u4e00-\u9fff]", c)]
        decomp = None
        if not candidate_list and re.search(r"[\u4e00-\u9fff]", source_term):
            decomp = await self.step2_semantic_decompose(source_term, inferred_domain, context)
            for value in (decomp.get("combined_translation"), decomp.get("alt_translation")):
                if value and not re.search(r"[\u4e00-\u9fff]", value) and value not in candidate_list:
                    candidate_list.append(value)
        # Candidate generation is language analysis; the first source searched is the journal library.
        journal_cards = search_usage(source_term, candidate_list, inferred_domain, preferred_journal)
        trace = [{"stage": "journal", "source": "11刊实际文本库", "term": source_term,
                  "status": "found_usage" if journal_cards else "no_usage_match", "count": len(journal_cards)}]
        # Run tier 1 even after journal hits, so both sides can be compared as requested.
        lookup = await self._lookup_official(source_term)
        exact = any(not self._scope_mismatch(entry, inferred_domain) for entry in lookup["entries"])
        trace.append({"stage": "tier1", "term": source_term, "source": "术语在线·审定公布名词库", "status": "found_other_domain" if lookup["entries"] and not exact else lookup["status"]})
        authority = [{**entry, "evidence_group": "authority", "match_type": "domain_mismatch" if self._scope_mismatch(entry, inferred_domain) else "exact",
                      "recommendation_reason": f"词形命中，但词条来自「{entry.get('source_name', '')}」，与当前「{inferred_domain}」领域不一致，不能直接证明本专业译法；将继续查找二级证据。" if self._scope_mismatch(entry, inferred_domain) else "已读取完整中英词条。请将其定义、专业领域与期刊语境对照，再由人工决定译法。"} for entry in lookup["entries"]]
        for entry in authority:
            if entry["candidate_translation"] not in candidate_list:
                candidate_list.append(entry["candidate_translation"])
        if exact:
            # Newly retrieved canonical English enables a supplementary journal query.
            journal_cards = search_usage(source_term, candidate_list, inferred_domain, preferred_journal)
            trace.append({"stage": "journal_supplement", "term": source_term, "source": "用一级词条英译补查期刊", "status": "found_usage" if journal_cards else "no_usage_match", "count": len(journal_cards)})
        core_term, decomposition = source_term, []
        catalogue = source_catalog(source_term, candidate_list[0] if candidate_list else "")
        if not exact:
            if lookup["entries"] and not decomp:
                decomp = {"core_term": source_term, "components": []}
            decomp = decomp or await self.step2_semantic_decompose(source_term, inferred_domain, context)
            core_term = decomp.get("core_term") or source_term
            decomposition = [{**part, "evidence": "语言分析建议，待查证"} for part in (decomp.get("components") or [])]
            for value in (decomp.get("combined_translation"), decomp.get("alt_translation")):
                if value and not re.search(r"[\u4e00-\u9fff]", value) and value not in candidate_list:
                    candidate_list.append(value)
            if core_term != source_term:
                core = await self._lookup_official(core_term)
                trace.append({"stage": "tier1_core", "term": core_term, "source": "术语在线·审定公布名词库", "status": core["status"]})
                authority.extend({**entry, "evidence_group": "authority", "match_type": "core_only",
                                  "recommendation_reason": f"仅证明核心词「{core_term}」，不能证明完整术语「{source_term}」。"} for entry in core["entries"])
            journal_cards = search_usage(source_term, candidate_list, inferred_domain, preferred_journal)
            primary_pages, primary_trace = await retrieve_level(catalogue, 1, source_term, candidate_list, {"T1-06"})
            authority.extend(primary_pages)
            trace.extend(primary_trace)
            secondary = await self._lookup_secondary(candidate_list, inferred_domain)
            authority.extend(secondary["entries"])
            trace.append({"stage": "tier2", "term": source_term, "source": "OSTI 原始记录", "status": secondary["status"], "count": len(secondary["entries"])})
            secondary_pages, secondary_trace = await retrieve_level(catalogue, 2, source_term, candidate_list, {"T2-09"})
            authority.extend(secondary_pages)
            trace.extend(secondary_trace)
        else:
            trace.append({"stage": "tier2", "source": "二级信源", "status": "skipped_tier1_found"})
        for card in authority:
            card.update({"recommended_translation": card["candidate_translation"], "domain": inferred_domain,
                         "status_tag": "完整官方词条" if card["match_type"] == "exact" else "领域不符·不可直接采用" if card["match_type"] == "domain_mismatch" else "仅核心词有出处" if card["match_type"] == "core_only" else "信源英文用法·待核对"})
        retrieved_ids = {t.get("source_id") for t in trace}
        for source in catalogue:
            if source["id"] in retrieved_ids:
                continue
            if source["source_level"] == 3:
                status = "excluded"
            elif source["id"] == "T1-06":
                continue
            elif source["id"] == "T2-09" and not exact:
                continue
            elif exact:
                status = "skipped_tier1_found"
            else:
                status = "manual_required"
            trace.append({"stage": f"tier{source['source_level']}", "source": source["name"], "source_id": source["id"], "status": status})
        journal_candidates = {c["recommended_translation"].casefold().strip() for c in journal_cards}
        official_candidates = {c["recommended_translation"].casefold().strip() for c in authority if c["match_type"] == "exact"}
        comparison = "agreement" if journal_candidates & official_candidates else "different_candidates" if journal_cards and official_candidates else "usage_both" if journal_cards and authority else "journal_only" if journal_cards else "authority_only" if authority else "no_evidence"
        reason = "期刊英文用法与完整官方词条存在相同候选，仍需人工核对定义与语境。" if comparison == "agreement" else "请对照两侧原文作人工裁决；英文出现、核心词命中或入口链接均不等于完整中英对应。"
        return {"source_term": source_term, "domain": inferred_domain, "is_exact": exact, "match_type": "exact" if exact else "unverified",
                "core_term": core_term, "decomposition": decomposition, "candidates": candidate_list,
                "recommended_translation": "", "recommendation_reason": reason,
                "cards": journal_cards + authority, "journal_cards": journal_cards, "authority_cards": authority,
                "evidences": journal_cards + authority, "lookup_trace": trace, "comparison_status": comparison,
                "requires_human_decision": True, "coverage_note": CATALOG["coverage_note"],
                "policy": "期刊优先；一级起查；一级完整命中则不查二级；三级不采用；期刊与信源同时命中仍须人工裁决。",
                "source_verification_version": 3}

    async def search_term_evidence(
        self,
        source_term: str,
        domain: Optional[str] = None,
        context: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """向后兼容的证据检索接口（统一委托给 execute_progressive_research）"""
        res = await self.execute_progressive_research(source_term, domain, context)
        return res.get("evidences", [])

    def verify_evidence_support(
        self,
        candidate_en: str,
        evidence_text: str
    ) -> Dict[str, Any]:
        """
        检验网页文本是否真正支持该候选译法：
        区分仅出现相似单词（弱共现）与真正提供定义/对应译法（强证据）
        """
        if not candidate_en or not evidence_text:
            return {"valid": False, "confidence": 0.0, "reason": "候选词或证据文本为空"}

        candidate_clean = candidate_en.lower().strip()
        evidence_clean = evidence_text.lower()

        # 检查是否包含完整词组
        if candidate_clean in evidence_clean:
            # 进一步检查是否有定义性或对应性表述
            definitional_cues = ["refers to", "defined as", "is a", "means", "【定义】", "指", "又称", "译为"]
            has_cue = any(cue in evidence_clean for cue in definitional_cues)
            confidence = 0.95 if has_cue else 0.75
            return {
                "valid": True,
                "confidence": confidence,
                "is_definitional": has_cue,
                "reason": "包含完整术语短语，且具有明确对应/定义语境" if has_cue else "包含完整术语短语"
            }

        # 单词部分匹配
        tokens = candidate_clean.split()
        if len(tokens) > 1:
            matched_tokens = [t for t in tokens if t in evidence_clean]
            if len(matched_tokens) == len(tokens):
                return {
                    "valid": True,
                    "confidence": 0.6,
                    "is_definitional": False,
                    "reason": "词组中所有单词均在证据中出现，但非连续出现，需人工复核"
                }

        return {
            "valid": False,
            "confidence": 0.2,
            "reason": f"证据文本中未找到完整术语「{candidate_en}」的明确对应支持"
        }


source_research_service = SourceResearchService()

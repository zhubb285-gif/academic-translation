"""
权威信源查证服务 (Source Research Service)
遵循《翻译质量保障流程总表》信源优先级：
一级信源：官方词典、权威机构定义（如全国科学技术名词审定委员会、IUPAC等）
二级信源：国际/国家行业标准（ISO、IEC、GB/T、ASTM）
三级信源：权威专业期刊（Nature, Science, IEEE, ACM, Elsevier）
四级信源：权威媒体、高校教材
五级信源：专业参考资料

提供：
1. 术语学科领域自动识别
2. 多级权威信源候选检索与证据提取
3. 证据验证（区分"出现单词"与"证实译法"）
"""
import json
import re
import logging
from typing import List, Dict, Optional, Any
import httpx
import html
from urllib.parse import urlencode
from app.services.source_links import source_link

from app.core.config import settings

logger = logging.getLogger(__name__)

# ============================================================
# 专业领域预设权威信源库 (Source Repositories)
# ============================================================

AUTHORITY_SOURCES_REGISTRY = [
    {
        "id": "term_online",
        "name": "全国科学技术名词审定委员会 (TermOnline)",
        "source_level": 1,
        "source_type": "国家权威机构名词库",
        "domain": "通用科技",
        "url": "https://www.termonline.cn",
        "reliability": "最高（国家规范名词）"
    },
    {
        "id": "iso_standards",
        "name": "ISO 国际标准化组织术语库 (ISO OBP)",
        "source_level": 2,
        "source_type": "国际标准",
        "domain": "工程技术/通用",
        "url": "https://www.iso.org/obp",
        "reliability": "高（国际标准定义）"
    },
    {
        "id": "ieee_explore",
        "name": "IEEE Xplore Standards Dictionary",
        "source_level": 2,
        "source_type": "行业权威标准",
        "domain": "电子信息/计算机/通信",
        "url": "https://ieeexplore.ieee.org",
        "reliability": "高（行业权威定义）"
    },
    {
        "id": "nature_terms",
        "name": "Nature Research Subject Areas & Glossaries",
        "source_level": 3,
        "source_type": "顶级学术期刊",
        "domain": "综合科学/生物医药/化学/物理",
        "url": "https://www.nature.com",
        "reliability": "高（同行评议顶级文献）"
    },
    {
        "id": "acm_dl",
        "name": "ACM Digital Library Computing Classification System",
        "source_level": 3,
        "source_type": "专业学会期刊与分类体系",
        "domain": "计算机科学与技术",
        "url": "https://dl.acm.org",
        "reliability": "高（学术共同体共识）"
    },
    {
        "id": "ncbi_mesh",
        "name": "NCBI MeSH (Medical Subject Headings)",
        "source_level": 1,
        "source_type": "国家医学图书馆主题词表",
        "domain": "生物医药/临床医学",
        "url": "https://www.ncbi.nlm.nih.gov/mesh",
        "reliability": "最高（医学国际通用标准）"
    }
]

# 常见领域关键词映射
DOMAIN_KEYWORDS = {
    "计算机科学": ["神经网络", "深度学习", "注意力机制", "强化学习", "算法", "分类器", "大语言模型", "特征提取", "嵌入", "多模态"],
    "石油与天然气工程": ["水力压裂", "储层", "压裂液", "固井", "完井", "钻井", "渗透率", "孔隙度", "采收率", "页岩气"],
    "材料科学": ["晶粒", "晶相", "抗拉强度", "屈服极限", "退火", "淬火", "复合材料", "聚合物", "纳米管", "显微硬度"],
    "生物医学": ["靶点", "细胞因子", "受体", "转录", "表达", "克隆", "表型", "基因组", "凋亡", "抗体"],
    "环境科学": ["碳中和", "温室气体", "富营养化", "降解", "生物质", "颗粒物", "重金属", "生命周期评估"],
}

# 离线候选译法，仅用于检索提示，不作为官方出处或证据。
TERM_TRANSLATION_HINTS = {'水力压裂': ['hydraulic fracturing'], '四川石油学院': ['Sichuan Petroleum Institute'], '西南石油学院': ['Southwest Petroleum Institute'], '西南石油大学': ['Southwest Petroleum University'], '三牙轮钻头': ['tri-cone bit'], '双一流': ['Double First-Class initiative'], '脱贫攻坚楷模': ['National Model for Poverty Alleviation'], '射流破碎钻头': ['jet breaking bit'], '天然气水合物固态流化试采': ['solid fluidized trial production of natural gas hydrate'], '注意力机制': ['attention mechanism'], '天然气水合物': ['natural gas hydrate'], '生命周期评价': ['Life Cycle Assessment (LCA)']}


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

    def get_registered_sources_for_domain(self, domain: str) -> List[Dict[str, Any]]:
        """按优先级升序返回适用于该领域的权威信源表"""
        matched = []
        for src in AUTHORITY_SOURCES_REGISTRY:
            if domain in src["domain"] or "通用" in src["domain"]:
                matched.append(src)
        # 按照信源等级 1 级 -> 2 级 -> 3 级排序
        return sorted(matched, key=lambda x: x["source_level"])

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

    async def execute_progressive_research(
        self, source_term: str, domain: Optional[str] = None, context: Optional[str] = None
    ) -> Dict[str, Any]:
        """Retrieve real official entries, then distinguish core evidence from full-term suggestions."""
        inferred_domain = domain or self.infer_domain(source_term, context)
        lookup = await self._lookup_official(source_term)
        exact = bool(lookup["entries"])
        decomposition = []
        core_term = source_term
        candidates = []
        evidences = lookup["entries"]
        trace = [{"term": source_term, "source": "术语在线·审定公布名词库", "status": lookup["status"]}]
        if not exact:
            decomp = await self.step2_semantic_decompose(source_term, inferred_domain, context)
            core_term = decomp.get("core_term") or source_term
            decomposition = decomp.get("components") or []
            for component in decomposition:
                component["evidence"] = "语言分析建议，待查证"
            for value in (decomp.get("combined_translation"), decomp.get("alt_translation")):
                if value and not re.search(r"[\u4e00-\u9fff]", value) and value not in candidates:
                    candidates.append(value)
            # A local demonstration dictionary supplies hints, never official evidence.
            if source_term in TERM_TRANSLATION_HINTS and not candidates:
                candidates = list(TERM_TRANSLATION_HINTS[source_term])
            if core_term != source_term:
                core_lookup = await self._lookup_official(core_term)
                evidences = core_lookup["entries"]
                trace.append({"term": core_term, "source": "术语在线·审定公布名词库", "status": core_lookup["status"]})
        cards = []
        for evidence in evidences:
            en = evidence["candidate_translation"]
            if exact and en not in candidates:
                candidates.append(en)
            cards.append({
                **evidence, **source_link(evidence["source_url"], core_term, en),
                "recommended_translation": en, "domain": inferred_domain,
                "source_checked": True, "match_type": "exact" if exact else "core_only",
                "status_tag": "完整官方词条" if exact else "仅核心词有出处",
                "recommendation_reason": "已从术语在线审定公布名词库读取完整中英词条，可在信源检索结果中核对。" if exact else f"此原文仅证明核心词「{core_term}」的译法，不证明完整组合「{source_term}」。",
            })
        if not exact:
            for candidate in candidates:
                cards.append({
                    "recommended_translation": candidate, "domain": inferred_domain,
                    "source_name": "术语在线检索入口", "source_level": 1,
                    **source_link("https://www.termonline.cn", source_term, candidate),
                    "source_checked": False, "evidence_text": "", "match_type": "unverified",
                    "status_tag": "候选译法·待查证",
                    "recommendation_reason": "尚未取得完整词条的可核对出处。此处是候选译法，检索链接已带入中文词语；不能作为官方译法证明。",
                })
        if not cards:
            cards.append({
                "recommended_translation": "", "domain": inferred_domain,
                "source_name": "术语在线检索入口", "source_level": 1,
                **source_link("https://www.termonline.cn", source_term),
                "source_checked": False, "evidence_text": "", "match_type": "unverified",
                "status_tag": "待查证", "recommendation_reason": "未取得可核对的官方词条。检索入口已带入此词，网站不可访问时不代表没有收录。",
            })
        return {
            "source_term": source_term, "domain": inferred_domain, "is_exact": exact,
            "match_type": "exact" if exact else "unverified", "core_term": core_term,
            "decomposition": decomposition, "candidates": candidates,
            "recommended_translation": candidates[0] if candidates else "",
            "recommendation_reason": cards[0]["recommendation_reason"],
            "cards": cards, "evidences": evidences, "lookup_trace": trace,
            "source_verification_version": 2,
        }

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

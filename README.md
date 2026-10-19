# 论文中译英质量保障平台 (Academic Translation Quality Assurance Platform)

> 面向中文学术论文的中译英、期刊风格适配、权威信源查证和多模型独立质量校对平台。
> 开发中的全栈系统；具体能力以实际运行与验证结果为准。

## 当前状态

- 包含 Vue 前端和 FastAPI 后端；真实模型翻译与校对需要有效的模型服务配置。
- 期刊风格目前通过提示词约束实现，尚未交付经过训练和评测的期刊专用模型。
- `backend/training/prepare_data.py` 当前生成少量示例数据；`train_lora.py` 仅保存配置，尚未执行实际训练；`evaluate.py` 当前是示例自比较，不是模型能力评测。
- 仓库不包含本机密钥、数据库、上传文稿、导出文件、数据集和模型权重。克隆后项目列表为空属于正常情况。

---

## 🛠️ 技术架构

- **前端架构**：Vue 3 + TypeScript + Vite + Element Plus + Pinia + Vue Router
- **后端架构**：Python 3.11+ + FastAPI + SQLAlchemy + Uvicorn
- **数据存储**：SQLite (嵌入式即开即用，无缝迁移 PostgreSQL)
- **质量保障层**：
  - **A0 原文预处理与稳定段落编号**：`S001`, `S002`, `S003`...
  - **信源分级权威证据查证**：一级官方机构 > 二级国际/国家标准 > 三级专业期刊 > 四级权威教材 > 五级参考信源
  - **期刊官方指南风格约束注入**：英美拼写规范、篇幅控制、时态/语态规则
  - **跨厂商多模型 MQM 互审**：Accuracy, Fluency, Terminology, Style, Locale 结构化评测
  - **确定性规则自检**：数字一致性（0 容错）、已核定术语一致率（目标 ≥ 98%）、段落与公式完整性
  - **全套成果与复现归档导出**：纯英文 Word 稿、双语逐段对照稿、术语与信源证据表、MQM 错误清单、过程审计归档包 (.zip)

---

## 🚀 极速启动与运行

首次安装（需要 Python 3.11+ 和适用于 Vite 8 的 Node.js，建议 Node.js 22.12+）：

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
cd ../frontend
npm ci
cd ..
```

按需在 `backend/.env` 配置模型服务，然后启动下面的脚本。请勿上传 `.env`。

### 方式一：一键脚本启动（推荐）

在项目根目录下直接运行：
```bash
./start.sh
```

### 方式二：手动分步启动

#### 1. 启动后端 API 服务
```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```
- API 服务地址：`http://127.0.0.1:8000`
- Swagger 交互式文档：`http://127.0.0.1:8000/docs`

#### 2. 启动前端页面
另开终端窗口执行：
```bash
cd frontend
npm run dev
```
- 前端访问地址：`http://localhost:5173`

---

## 📂 项目代码目录结构

```text
academic-translation/
├── backend/
│   ├── app/
│   │   ├── main.py                    # FastAPI 统一服务入口
│   │   ├── core/
│   │   │   ├── config.py              # Pydantic 核心环境配置 (.env)
│   │   │   ├── database.py            # SQLite / ORM 引擎与会话
│   │   │   └── seed.py                # 预置顶级期刊与模型配置种子
│   │   ├── models/
│   │   │   └── database.py            # 10 张核心业务表 SQLAlchemy ORM
│   │   ├── schemas/
│   │   │   └── schemas.py             # 请求与响应 Pydantic 模型
│   │   ├── services/
│   │   │   ├── document_parser.py     # DOCX / PDF / TXT 结构化解析与段落编号
│   │   │   ├── source_research.py     # 权威信源多级检索与证据支撑检验
│   │   │   ├── journal_style.py       # 期刊风格指南约束与合规性检查
│   │   │   ├── translation_service.py # 多厂商翻译模型接入与 FLAG 标记
│   │   │   ├── mqm_review.py          # 独立跨厂商 MQM 质量评审
│   │   │   ├── quality_checker.py     # 确定性数字、术语、完整性规则检查
│   │   │   └── export_service.py      # Word / Excel / ZIP 成果与审计包导出
│   │   └── api/
│   │       ├── projects.py            # 项目 CRUD 与进度统计
│   │       ├── documents.py           # 文档上传与异步解析
│   │       ├── translation.py         # 逐段/批量翻译与编辑
│   │       ├── terminology.py         # 术语管理、逐级查证与证据管理
│   │       ├── other.py               # 期刊库、模型配置、MQM 校对与报告
│   │       └── export.py              # 全流程文档与归档导出下载
│   ├── training/
│   │   ├── prepare_data.py            # 示例数据生成（待实现真实语料处理）
│   │   ├── train_lora.py              # LoRA 配置框架（待实现实际训练）
│   │   └── evaluate.py                # 示例评测（待接入实际模型输出）
│   ├── data/                          # 数据库、上传文档与衍生文件存储
│   ├── .env                           # API Key 与模型端点私有配置
│   └── requirements.txt               # 后端依赖清单
├── frontend/
│   ├── src/
│   │   ├── views/
│   │   │   ├── HomeView.vue           # 首页与论文项目看板
│   │   │   ├── ProjectDetailView.vue  # 项目概览、文档上传与期刊选择
│   │   │   ├── TranslateView.vue      # 中英双栏对照翻译工作台
│   │   │   ├── TerminologyView.vue    # 术语逐级查证与信源证据库
│   │   │   ├── ProofreadView.vue      # 多模型 MQM 校对、质量报告与成果导出
│   │   │   ├── JournalsView.vue       # 目标期刊官方投稿指南库
│   │   │   └── ModelsView.vue         # 翻译/校对模型提供商与元信息管理
│   │   ├── api/index.ts               # Axios 统一 API 客户端
│   │   ├── router/index.ts            # Vue Router 路由
│   │   └── App.vue                    # 平台主应用框架
│   └── package.json                   # 前端依赖配置
├── start.sh                           # 一键启动脚本
└── README.md                          # 系统开发与使用说明
```

---

## 🔑 AI 模型 API Key 配置

在 `backend/.env` 文件中填入你的 API Key 即可（无需写入前端）：
```ini
# OpenAI
OPENAI_API_KEY="sk-..."
OPENAI_BASE_URL="https://api.openai.com/v1"

# DeepSeek
DEEPSEEK_API_KEY="sk-..."
DEEPSEEK_BASE_URL="https://api.deepseek.com/v1"

# Anthropic Claude
ANTHROPIC_API_KEY="sk-ant-..."
```
系统支持使用不同模型分别作为翻译模型与校对模型，实现跨厂商独立互审。

# Doc Intelligence

Free, open-source, self-hosted AI-powered document analysis and ERPNext automation for Frappe / ERPNext. No plans, no limits — every feature is always on for every user.

Upload a PDF, DOCX, or photo and instantly get an AI-generated summary, key entity extraction, table parsing, and unlimited Q&A. Then go further — create draft ERPNext records (Item, Supplier, Customer, Employee, Address, Quotation, Sales Order, Purchase Order, Material Request) directly from the document, or turn a supplier invoice into a draft Purchase Invoice complete with independent financial validation, fuzzy supplier matching, and duplicate-invoice detection.

Everything is self-hosted: your documents and your API keys stay on your own Frappe site. Bring your own keys for whichever LLM providers you want — Groq, Gemini, Cerebras, OpenRouter, Mistral, DeepSeek, OpenAI, or Claude — with automatic fallback between them.

## Compatibility

This build is for **Frappe / ERPNext v16.x** and Python 3.14. It is not installed on v14 or v15.

```bash
bench get-app doc_intelligence https://github.com/roysbike/nexterp-doc-intelligence
```

CI (`.github/workflows/ci.yml`) runs the test suite against the Frappe `version-16` branch.

## Features

**Document intelligence**
- Detects the file itself: PDF with a text layer, scanned PDF, DOCX (including tables), TXT/CSV, and images (JPG/PNG/WEBP/GIF/TIFF/BMP)
- A scanned PDF is rendered and read by a vision model. An empty text layer is not sent to the model as a blank document
- Editable analysis prompt in Provider Settings, with a built-in UAE VAT tax-invoice checklist
- Automatic summary, key entities/parties, dates, amounts, and clauses
- Extracts and renders tabular data (e.g. invoice line items) found in documents
- Answers free-text questions about any uploaded document
- Compares two documents side-by-side
- In-browser camera capture — single photo or multi-page (auto-combined into one PDF), from both the portal and the Desk form

**ERPNext automation**
- Create draft Item / Supplier / Customer / Employee / Address records from a document, with fuzzy duplicate matching (exact-then-fuzzy string similarity, refuses to auto-pick when multiple records are ambiguously close)
- Create draft Quotation / Sales Order / Purchase Order / Material Request from a document, with the same party-matching plus independent recalculation of line-item totals against the AI-reported total
- Create a draft Purchase Invoice from a supplier invoice, with:
  - Independent financial validation — recalculates subtotal/tax/grand total from extracted line items and flags a mismatch beyond a 2% tolerance
  - Fuzzy supplier matching with ambiguity detection
  - Duplicate invoice detection (same bill number + supplier), with a hard server-side block unless explicitly confirmed

**Ask ERPNext — plain-English queries, safely**
- Desk page (`Ask ERPNext`) to ask natural-language questions about your ERP data
- Schema-aware planning: the AI plans against real DocType metadata, not guessed fields
- Structured JSON query plans, validated against an explicit allow-list before anything runs
- Permission-safe reads via `frappe.get_list()` as the current user — no `ignore_permissions`, no raw SQL, no generated Python
- Optional draft record creation (Customer, Supplier, Item, Task, ToDo, Contact, Lead) with an explicit on-screen **Approve / Cancel** step — nothing is written until you approve
- Demo prompts for quick screenshots or a first try: *"Show unpaid invoices older than 30 days"*, *"Show low-stock items"*, *"How many sales orders were created this week?"*, and more
- Full audit trail of every question, plan, and outcome in **DI Copilot Log**

**Platform**
- Multi-provider LLM routing with automatic fallback, so a rate-limited provider doesn't block processing
- Provider health dashboard (24h success rate per provider)
- Full REST API for integration with external systems
- PWA — installable, with offline document-list caching

## Architecture

Classic Frappe custom app + decoupled Vue 3 SPA:

- **Backend** (`doc_intelligence/doc_intelligence/`) — DocTypes, whitelisted REST API (`api/__init__.py`), the multi-provider LLM engine (`llm_engine.py`), the financial-validation/fuzzy-matching module (`validation.py`), and the Ask ERPNext planner/validator/executor (`copilot.py`).
- **Frontend** (`frontend/`) — Vue 3 + Vite + Pinia + Vue Router + Dexie (PWA offline cache), built to `doc_intelligence/public/doc_intelligence_app/` and served at `/doc-intelligence`.
- Legacy Desk Pages (`di-dashboard`, `di-provider-settings`) work alongside the SPA if you prefer working from inside Desk.

See `DEPLOY.md` for build/deploy steps.

## Разбор файла и промпт

Тип файла определяется сам, по расширению и по заголовку файла. В карточке документа это поле `source_format`.

| Файл | Как читается | Что видно в карточке |
| --- | --- | --- |
| PDF с текстовым слоем | Текст достаётся локально, без модели | `pdf-text` |
| PDF-скан, в котором нельзя выделить строки | Страницы рисуются и отправляются в vision-модель | `pdf-scan` |
| JPG, PNG, WEBP, GIF | Сразу в vision-модель | `jpeg`, `png`, `webp`, `gif` |
| TIFF, BMP | Сначала в JPEG, затем в vision-модель | `tiff`, `bmp` |
| DOCX | Абзацы и ячейки таблиц | `docx` |
| TXT, CSV | Как текст | `text`, `csv` |

Старый Word `.doc` не читается. Сохрани его как DOCX или PDF. Скан длиннее 8 страниц обрезается, в тексте будет пометка, сколько страниц пропущено.

Для скана нужен провайдер, который видит картинку: OpenRouter, Gemini, Claude или OpenAI с моделью, принимающей изображения. Модель вроде бесплатной Llama картинку не прочитает, и документ станет Failed с текстом причины в сводке.

Промпт правится в `/doc-intelligence/provider-settings`, блок **Analysis prompt**, и в Desk: Doc Intelligence Settings → Analysis Prompt. Пустое поле при сохранении возвращает встроенный список. Этот список проверяет поля налогового счёта ОАЭ (Tax Invoice, стороны, TRN, номер, дата, строки, ставка и сумма НДС, итог), запрещает додумывать отсутствующие цифры и не считает PDF электронным инвойсом или сдачей в FTA. Текст файла к промпту дописывается сам, ключи JSON менять не нужно.

Разбор ответа использует не меньше 4000 токенов, чтобы таблица строк не обрывалась. Кнопка Purchase Invoice больше не требует вручную передать дату оплаты и примечание: пустая дата оплаты берётся из даты счёта, валюта и счёт расходов берутся из выбранной компании.

## Стоимость в AED

На карточке документа, рядом с числом токенов, показывается стоимость в дирхамах. Сумма складывается из распознавания страниц, разбора и последующих вопросов по этому документу.

Цифру в долларах берём из ответа провайдера. OpenRouter отдаёт её в поле `usage.cost` ([Usage Accounting](https://openrouter.ai/docs/cookbook/administration/usage-accounting)). Дирхамы считаются как доллары умножить на **AED per USD** в настройках. По умолчанию стоит официальный фиксированный курс **3.6725**. Его можно сменить в том же экране Provider Settings.

Если провайдер цену не присылает (прямой OpenAI, Gemini, Claude и остальные), на карточке остаются только токены. Сумма в AED для них не подставляется.

## Installation

```bash
bench get-app doc_intelligence https://github.com/roysbike/nexterp-doc-intelligence
bench --site yoursite.localhost install-app doc_intelligence
bench --site yoursite.localhost migrate
pip install openai anthropic pypdf python-docx pymupdf --break-system-packages
cd apps/doc_intelligence/frontend && yarn install && yarn build
cd ~/frappe-bench
bench build --app doc_intelligence
bench restart
```

## First-Time Setup

1. Go to `/doc-intelligence/provider-settings` (System Manager only)
2. Expand a provider and paste in an API key — Groq, Gemini, Cerebras, Mistral, and DeepSeek all have usable free tiers
3. Click **Save Settings** → **Test All Providers**
4. Add that provider's id to **Enabled Providers**, e.g. `groq,gemini,cerebras,claude`
5. Go to `/doc-intelligence/home` → **Upload Document**
6. Wait for status = **Ready**, then try Ask a Question, Compare, and Create ERPNext Record
7. In Desk, open **Ask ERPNext** (search bar or the Doc Intelligence workspace) and try one of the demo prompts, e.g. *"Show unpaid invoices"*

## License

MIT — see `LICENSE`.

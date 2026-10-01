# Doc Intelligence

[English](#english) | [Русский](#русский)

## English

Free, open-source, self-hosted AI document analysis and ERPNext automation for Frappe / ERPNext. No plans, no limits — every feature is always on for every user.

Upload a PDF, DOCX, or photo and get an AI summary, key entities, parsed tables, and Q&A. From the same document you can create draft ERPNext records (Item, Supplier, Customer, Employee, Address, Quotation, Sales Order, Purchase Order, Material Request), or turn a supplier invoice into a draft Purchase Invoice with financial checks, fuzzy supplier matching, and duplicate detection.

Documents and API keys stay on your own Frappe site. Bring keys for Groq, Gemini, Cerebras, OpenRouter, Mistral, DeepSeek, OpenAI, or Claude. If one provider is rate-limited, the next enabled provider is tried.

### Compatibility

This build is for **Frappe / ERPNext v16.x** and Python 3.14. It is not installed on v14 or v15.

```bash
bench get-app doc_intelligence https://github.com/roysbike/nexterp-doc-intelligence
```

CI (`.github/workflows/ci.yml`) runs the test suite against the Frappe `version-16` branch.

### Features

**Document intelligence**

- Detects the file from its extension and header: text PDF, scanned PDF, DOCX (including tables), TXT/CSV, and images (JPG/PNG/WEBP/GIF/TIFF/BMP)
- A scanned PDF is rendered and read by a vision model. An empty text layer is not sent to the model as a blank document
- Editable analysis prompt in Provider Settings, with a built-in UAE VAT tax-invoice checklist
- Summary, parties, dates, amounts, and clauses
- Tables from the document, such as invoice lines
- Free-text questions about an uploaded document
- Side-by-side comparison of two documents
- In-browser camera capture, one photo or several pages combined into one PDF, from the portal and from the Desk form

**ERPNext automation**

- Draft Item, Supplier, Customer, Employee, and Address records, with exact-then-fuzzy matching that refuses to guess when several records are close
- Draft Quotation, Sales Order, Purchase Order, and Material Request, with the same party matching and a recalculation of line totals against the total reported by the model
- Draft Purchase Invoice from a supplier invoice:
  - Recalculates subtotal, tax, and grand total from the lines and flags a mismatch beyond 2%
  - Fuzzy supplier matching that stops when the match is ambiguous
  - Duplicate detection on the same bill number and supplier, blocked on the server unless you confirm it

**Ask ERPNext**

- Desk page for natural-language questions about ERP data
- The plan is built from real DocType metadata, not guessed field names
- The plan is JSON and is checked against an allow-list before it runs
- Reads go through `frappe.get_list()` as the current user: no `ignore_permissions`, no raw SQL, no generated Python
- Optional drafts (Customer, Supplier, Item, Task, ToDo, Contact, Lead) only after you press **Approve**. Cancel writes nothing
- Demo prompts include *"Show unpaid invoices older than 30 days"*, *"Show low-stock items"*, and *"How many sales orders were created this week?"*
- Every question, plan, and outcome is stored in **DI Copilot Log**

**Platform**

- Several LLM providers, tried in the order you set
- Provider health for the last 24 hours
- REST API
- Installable PWA with an offline cache of the document list

### Architecture

Frappe app plus a separate Vue 3 SPA:

- **Backend** (`doc_intelligence/doc_intelligence/`) — DocTypes, whitelisted API (`api/__init__.py`), LLM engine (`llm_engine.py`), financial checks and fuzzy matching (`validation.py`), and the Ask ERPNext planner (`copilot.py`).
- **Frontend** (`frontend/`) — Vue 3, Vite, Pinia, Vue Router, and Dexie. The build is committed under `doc_intelligence/public/doc_intelligence_app/` and served at `/doc-intelligence`.
- Older Desk pages (`di-dashboard`, `di-provider-settings`) stay available next to the SPA.

Build and deploy steps are in `DEPLOY.md`.

### How a file is read

The file kind is chosen from the extension and the file header. The document card shows it as `source_format`.

| File | How it is read | Card label |
| --- | --- | --- |
| PDF with a text layer | Text is extracted locally, without a model | `pdf-text` |
| Scanned PDF (the lines cannot be selected) | Pages are rendered and sent to a vision model | `pdf-scan` |
| JPG, PNG, WEBP, GIF | Sent straight to a vision model | `jpeg`, `png`, `webp`, `gif` |
| TIFF, BMP | Converted to JPEG, then sent to a vision model | `tiff`, `bmp` |
| DOCX | Paragraphs and table cells | `docx` |
| TXT, CSV | Read as text | `text`, `csv` |

Legacy Word `.doc` is not read. Save it as DOCX or PDF. A scan longer than 8 pages is cut off, and the extracted text says how many pages were skipped.

A scan needs a provider that can see images: OpenRouter, Gemini, Claude, or OpenAI with an image model. A text-only model such as the free Llama does not read the picture. The document is marked Failed, and the summary explains why.

Edit the prompt at `/doc-intelligence/provider-settings`, block **Analysis prompt**, or in Desk under Doc Intelligence Settings → Analysis Prompt. Saving an empty field restores the built-in checklist. That checklist looks for the fields of a UAE tax invoice (the words Tax Invoice, parties, TRN, number, date, lines, VAT rate, VAT amount, and the amount due). It does not invent missing figures, and it does not treat a PDF as a PINT-AE e-invoice or as a filing to the FTA. The file text is appended for you. Do not rename the JSON keys.

Analysis requests use at least 4000 completion tokens so a long line table is not cut off. Creating a Purchase Invoice does not require you to send a due date and remarks: a missing due date becomes the invoice date, and currency and the expense account come from the selected company.

### Cost in AED

The document card shows the cost in dirhams next to the token count. The figure adds up page recognition, the analysis, and later questions about that same document.

The dollar amount comes from the provider response. OpenRouter returns it in `usage.cost` ([Usage Accounting](https://openrouter.ai/docs/cookbook/administration/usage-accounting)). Dirhams are that amount times **AED per USD** in settings. The default is the official peg, **3.6725**. Change it on the same Provider Settings screen.

If the provider does not return a price (direct OpenAI, Gemini, Claude, and the others), the card shows tokens only. No AED amount is filled in for those calls.

### Installation

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

### First-time setup

1. Open `/doc-intelligence/provider-settings` (System Manager only).
2. Expand a provider and paste an API key. Groq, Gemini, Cerebras, Mistral, and DeepSeek have usable free tiers.
3. Click **Save Settings**, then **Test All Providers**.
4. Put that provider's id in **Enabled Providers**, for example `openrouter` or `groq,gemini,claude`.
5. Open `/doc-intelligence/home` and upload a document.
6. Wait until the status is **Ready**, then try a question, a comparison, and **Create ERPNext Record**.
7. In Desk, open **Ask ERPNext** and try a demo prompt, for example *"Show unpaid invoices"*.

### License

MIT. See `LICENSE`.

## Русский

Свободный самохостинг: разбор документов и черновики ERPNext на своём сайте Frappe. Тарифов нет, все функции включены.

Загрузите PDF, DOCX или фото и получите сводку, стороны, таблицы и ответы на вопросы. Из того же файла можно создать черновики Item, Supplier, Customer, Employee, Address, Quotation, Sales Order, Purchase Order и Material Request или собрать черновик Purchase Invoice по счёту поставщика: с пересчётом сумм, поиском поставщика и проверкой дубликата.

Документы и ключи API остаются на вашем сайте. Подходят Groq, Gemini, Cerebras, OpenRouter, Mistral, DeepSeek, OpenAI и Claude. Если один провайдер упёрся в лимит, берётся следующий из списка.

### Совместимость

Эта сборка для **Frappe / ERPNext v16.x** и Python 3.14. На v14 и v15 она не ставится.

```bash
bench get-app doc_intelligence https://github.com/roysbike/nexterp-doc-intelligence
```

CI (`.github/workflows/ci.yml`) гоняет тесты на ветке Frappe `version-16`.

### Возможности

**Разбор документов**

- Тип файла определяется по расширению и заголовку: PDF с текстом, PDF-скан, DOCX вместе с таблицами, TXT/CSV и картинки JPG, PNG, WEBP, GIF, TIFF, BMP
- Скан рисуется постранично и уходит в модель, которая видит изображение. Пустой текстовый слой в модель как «пустой документ» не отправляется
- Промпт разбора редактируется в настройках. Встроенный текст — проверка полей налогового счёта ОАЭ
- Сводка, стороны, даты, суммы и условия
- Таблицы из документа, в том числе строки счёта
- Вопросы по загруженному файлу
- Сравнение двух документов
- Снимок с камеры в браузере: один кадр или несколько страниц в один PDF, и в портале, и в форме Desk

**Записи ERPNext**

- Черновики Item, Supplier, Customer, Employee и Address. Сначала точное совпадение, потом похожее имя. Если рядом несколько записей, выбор не делается
- Черновики Quotation, Sales Order, Purchase Order и Material Request, с тем же поиском стороны и пересчётом строк против итога, который назвала модель
- Черновик Purchase Invoice из счёта поставщика:
  - Подытог, налог и итог пересчитываются по строкам. Расхождение больше 2% помечается
  - Поиск поставщика останавливается, если совпадение неоднозначно
  - Тот же номер счёта у того же поставщика блокируется на сервере, пока вы сами не подтвердите повтор

**Ask ERPNext**

- Страница Desk для вопросов к данным ERP обычным языком
- План строится по настоящим полям DocType, а не по выдуманным именам
- План — это JSON, и он проверяется по списку разрешённых действий до запуска
- Чтение идёт через `frappe.get_list()` от имени текущего пользователя: без `ignore_permissions`, без сырого SQL и без сгенерированного Python
- Черновики Customer, Supplier, Item, Task, ToDo, Contact и Lead создаются только после **Approve**. Cancel ничего не пишет
- Примеры запросов: *«Show unpaid invoices older than 30 days»*, *«Show low-stock items»*, *«How many sales orders were created this week?»*
- Вопрос, план и результат пишутся в **DI Copilot Log**

**Платформа**

- Несколько LLM-провайдеров в заданном порядке
- Состояние провайдеров за последние 24 часа
- REST API
- PWA со списком документов, доступным без сети

### Архитектура

Приложение Frappe и отдельное Vue 3 SPA:

- **Сервер** (`doc_intelligence/doc_intelligence/`) — DocType, API (`api/__init__.py`), движок моделей (`llm_engine.py`), проверка сумм и поиск имён (`validation.py`), планировщик Ask ERPNext (`copilot.py`).
- **Интерфейс** (`frontend/`) — Vue 3, Vite, Pinia, Vue Router и Dexie. Сборка лежит в репозитории: `doc_intelligence/public/doc_intelligence_app/`, адрес `/doc-intelligence`.
- Старые страницы Desk (`di-dashboard`, `di-provider-settings`) работают рядом со SPA.

Сборка и выкладка описаны в `DEPLOY.md`.

### Как читается файл

Тип берётся из расширения и из заголовка файла. На карточке это поле `source_format`.

| Файл | Как читается | Подпись на карточке |
| --- | --- | --- |
| PDF с текстовым слоем | Текст достаётся локально, без модели | `pdf-text` |
| PDF-скан, строки нельзя выделить | Страницы рисуются и уходят в vision-модель | `pdf-scan` |
| JPG, PNG, WEBP, GIF | Сразу в vision-модель | `jpeg`, `png`, `webp`, `gif` |
| TIFF, BMP | Сначала JPEG, затем vision-модель | `tiff`, `bmp` |
| DOCX | Абзацы и ячейки таблиц | `docx` |
| TXT, CSV | Как текст | `text`, `csv` |

Старый Word `.doc` не читается. Сохраните его как DOCX или PDF. Скан длиннее 8 страниц обрезается, в тексте будет пометка, сколько страниц пропущено.

Для скана нужен провайдер, который видит картинку: OpenRouter, Gemini, Claude или OpenAI с моделью для изображений. Текстовая модель, например бесплатная Llama, картинку не прочитает. Документ станет Failed, а в сводке будет причина.

Промпт правится на `/doc-intelligence/provider-settings`, блок **Analysis prompt**, и в Desk: Doc Intelligence Settings → Analysis Prompt. Пустое поле при сохранении возвращает встроенный список. Список проверяет поля налогового счёта ОАЭ (слова Tax Invoice, стороны, TRN, номер, дата, строки, ставка и сумма НДС, итог). Отсутствующие цифры не додумываются. PDF не считается электронным инвойсом PINT-AE и не считается сдачей в FTA. Текст файла дописывается сам. Ключи JSON менять не нужно.

На разбор ответа уходит не меньше 4000 токенов, чтобы длинная таблица не обрывалась. Кнопка Purchase Invoice не требует отдельно передать дату оплаты и примечание: пустая дата оплаты берётся из даты счёта, валюта и счёт расходов берутся из выбранной компании.

### Стоимость в AED

На карточке документа рядом с токенами показана стоимость в дирхамах. В неё входят распознавание страниц, разбор и следующие вопросы по этому же документу.

Сумма в долларах берётся из ответа провайдера. OpenRouter отдаёт её в `usage.cost` ([Usage Accounting](https://openrouter.ai/docs/cookbook/administration/usage-accounting)). Дирхамы — это доллары, умноженные на **AED per USD** в настройках. По умолчанию официальный фиксированный курс **3.6725**. Его можно сменить на том же экране Provider Settings.

Если провайдер цену не присылает (прямой OpenAI, Gemini, Claude и остальные), на карточке остаются только токены. Сумма в AED для таких вызовов не подставляется.

### Установка

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

### Первый запуск

1. Откройте `/doc-intelligence/provider-settings` (только System Manager).
2. Раскройте провайдера и вставьте ключ API. У Groq, Gemini, Cerebras, Mistral и DeepSeek есть пригодный бесплатный уровень.
3. Нажмите **Save Settings**, затем **Test All Providers**.
4. Впишите id провайдера в **Enabled Providers**, например `openrouter` или `groq,gemini,claude`.
5. Откройте `/doc-intelligence/home` и загрузите документ.
6. Дождитесь статуса **Ready**, затем задайте вопрос, сравните документы и нажмите **Create ERPNext Record**.
7. В Desk откройте **Ask ERPNext** и попробуйте пример, например *«Show unpaid invoices»*.

### Лицензия

MIT. Смотрите `LICENSE`.

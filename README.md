# MediBot backend

## Project layout

```text
MediBot-Code_Alchemists/
├── constants.txt                 # Shared settings in JSON format
├── README.md
├── requirements.txt
├── backend/
│   ├── config/settings.py        # Loads constants.txt
│   ├── models/schemas.py         # Medicine/extraction schema
│   ├── llm/
│   │   ├── extractor.py          # Extracts medicines and intents
│   │   └── chatbot.py            # Answers general-health questions
│   ├── safety/safety_guard.py    # Blocks, clarifies, and checks schedules
│   ├── services/
│   │   ├── response.py           # Routes responses and builds comparisons
│   │   └── price.py              # Reads pharmacy prices
│   ├── data/
│   │   ├── medicine_database.py  # Shared JSON lookup
│   │   ├── medicines_final.json
│   │   └── pharmacy_products.json
│   └── cli/
│       ├── safety_cli.py         # Interactive terminal tester
│       └── demo.py               # Extraction demo
├── tests/
└── examples/price_response.json
```

Python package folders also contain `__init__.py`. The virtual environment and
Git metadata remain in `.venv/` and `.git/` at the project root.

## Shared constants

`constants.txt` is a JSON object, loaded by `backend/config/settings.py`; it is
the source for model defaults and options, history limits, prompts, intent
policies, schedule rules, disclaimers/messages, pharmacy hosts/search URLs,
data paths, request limits, matching patterns, and price-comparison settings.
Edit it as valid JSON and restart the running process to reload changes.
Environment overrides (`OLLAMA_HOST`, `OLLAMA_MODEL`, `OLLAMA_CHAT_MODEL`) still
take precedence over defaults. Data paths resolve relative to the project root,
so they do not depend on the current working directory.

Python function names, JSON field names, response action/status identifiers,
and pharmacy-specific response field names remain part of the implementation.
Medicine records and product-URL mappings remain in `backend/data/`; they are
datasets rather than shared settings.

## Setup

Requires Python 3.11 or newer. Run these commands from the project root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

For the interactive tester, install Ollama, start its local server, and pull the model:

```powershell
ollama pull qwen3:8b
.\.venv\Scripts\python.exe -m backend.cli.safety_cli
```

The default server is `http://localhost:11434`. Override `OLLAMA_HOST` and
`OLLAMA_MODEL` through environment variables if needed. The extractor demo is
available with `python -m backend.llm.extractor` or the compatibility entry point
`python -m backend.cli.demo`.

`backend/llm/chatbot.py` answers `general_health` questions using Ollama. It uses the
same host and default model as extraction; `OLLAMA_CHAT_MODEL` can override the
answering model separately. Both extraction and answering require a running
Ollama server with the configured model available.

Both model calls default to `qwen3:8b` with thinking disabled. The initial context
limit is 2,048 tokens to leave more memory for inference on a 6 GB GPU. Increase
`ollama.options.num_ctx` in `constants.txt` if longer requests or conversations
are truncated, then check GPU memory usage and latency again. Restart the backend
after configuration changes. Remove or update any existing `OLLAMA_MODEL` or
`OLLAMA_CHAT_MODEL` environment overrides if they point to a different model.

## Troubleshooting Ollama on another laptop

The chat message `I couldn't process your request. Please try again.` means the
backend caught an exception. Its terminal logs the traceback; the browser message
alone cannot distinguish a connection failure, missing model, timeout, or invalid
extraction JSON. Downloading a model does not verify the application's connection.

Run these checks in PowerShell from the project root on the affected laptop:

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade -r requirements.txt
ollama --version
ollama list
Invoke-RestMethod http://localhost:11434/api/tags
```

The Python `ollama` client must be version 0.5 or newer because both model calls
use the `think` argument. Older clients can raise
`TypeError: Client.chat() got an unexpected keyword argument 'think'` before
contacting the server. Update the Ollama desktop application separately if it is
outdated. If the tags request cannot connect, open Ollama or run `ollama serve`
in a separate terminal. If `qwen3:8b` is absent from the list, pull that exact tag
with `ollama pull qwen3:8b`.

Set the intended configuration in the terminal used to start the backend:

```powershell
$env:OLLAMA_HOST = 'http://localhost:11434'
$env:OLLAMA_MODEL = 'qwen3:8b'
$env:OLLAMA_CHAT_MODEL = 'qwen3:8b'
.\.venv\Scripts\python.exe -m backend.api
```

`localhost` refers to the machine running the Python backend. These settings
assume the backend and Ollama run on the same laptop. Restart the backend after
updating dependencies or environment variables. To test extraction directly and
see its exception without the chat error handler, run:

```powershell
.\.venv\Scripts\python.exe -c "from backend.llm.extractor import extract_query; print(extract_query('hi how are you').model_dump_json(indent=2))"
```

A timeout may mean model loading or CPU inference exceeded the configured
120-second Ollama timeout. Check the traceback and `ollama ps` before changing
timeouts. A JSON validation error means the model response failed the extraction
schema; it is not evidence that the server is unreachable.

## Request handling

- Schedule X is checked first in `backend/safety/safety_guard.py`, including
  mixed or ambiguous requests. It returns `action="block"`, `reason="schedule_x"`,
  and a direct message: the configured blocked-intent message when applicable,
  otherwise `Please consult a doctor.` No response handlers run.
- Prescribing, prescription-status, diagnosis, interaction, usage instructions,
  availability, and unrelated intents are blocked after the Schedule X check,
  including mixed requests. Clarification does not affect their blocking.
- Other requests with `needs_clarification=true` return the extractor's question.
  A non-empty question is required. When clarification is unnecessary the
  question must be null. These consistency checks are skipped for blocked intents.
- Declared non-blocked intents continue to response routing after clarification
  and medicine checks. `other` is blocked by the current policy.
- Supported requests without a medicine or with a blank medicine name ask for
  the missing name. General-health-only requests do not require a medicine.
- `continue_to_response=true` means safety checks and medicine lookup passed
  and response handlers may run. It does not authorize dispensing. This replaces
  the previous `continue_to_classification` field, since lookup is now in safety.

`backend/models/schemas.py` owns the schema and intent policies, `backend/llm/extractor.py`
calls Ollama, and `backend/safety/safety_guard.py` checks the validated extraction.
`backend/data/medicine_database.py` provides shared JSON lookup for safety and substitutes.
The CLI returns an error result if extraction or validation fails and logs the
exception locally for diagnosis.

## Response routing

The interactive tester calls `backend.services.response.handle_response()`, which runs
the safety check and dispatches only after a `continue` action. It returns blocking or clarification messages immediately;
otherwise, it returns a `response` action with a `results` list for every intent.
When a lookup needs clarification, reply with the full product name and strength.
The CLI and HTTP server retain the pending intents, medicine details, clarification
reason, and candidate products. The model returns a structured turn update:
medicine-only replies keep the intent; `instead` replaces intents; `also` adds
intents; a separate request replaces the pending task. The backend merges these
updates and validates the resulting products before dispatch. Strength-only replies
are interpreted using the stored medicine details. A supplied product is checked
by the database rather than repeating the previous medicine question.

Repeated clarification without progress first explains the obstacle, then ends
the pending task after two unsuccessful follow-up replies and asks for a fresh
complete request. Missing regulatory data returns an error that requires a dataset
correction. Completing or blocking a request clears pending state; failed model
or service calls preserve it for retry. A medicine supplied without an intent asks
what information the user wants.
While that intent question is pending, exact replies such as `prices`, `uses`,
`side effects`, and `alternatives` fill the intent directly, preserving the medicine
without another extraction call. The reply aliases are in
`clarification_intent_replies` in `constants.txt`. Longer or mixed requests still
use model extraction, and all replies pass the existing safety checks.

Ambiguous or unmatched medicines now offer up to ten clickable database products.
Choices search product names and exact ingredient names, put single-ingredient
products first, and label combinations with their additional ingredients. Within
those groups, matching product names precede ingredient-only matches. Products
with restricted, unverified, or conflicting regulatory/database records are omitted.
Users can still type an exact product if it is not among the displayed choices.
If extraction omits every medicine from a medicine-specific request, the backend
also checks the latest message for literal database product and ingredient names.
This fallback also recognizes short brands such as `Dolo` and brand/form requests
such as `Dolo tablet` with an omitted strength. It preserves stated strengths and
does not infer a medicine from symptoms. Product choices can appear during intent
clarification too; selecting a product retains it while the missing intent is requested.

The frontend sends a choice to `POST /api/select` with `session_id`, `request_id`,
`product_id`, and `selection_offer`. IDs are bound to that session's current
clarification. The backend replaces only the unresolved medicine, retains the
active intents, and runs the normal safety checks and response routing without
another extraction call. Successful selection retries return the cached response.
Changing the task invalidates earlier offers; previous buttons become inactive.

| Intent | Handler |
| --- | --- |
| `price_comparison` | Fetch prices for the original medicine and its verified substitutes |
| `availability` | Blocked at the safety stage; no price or availability handler runs |
| `prescription_status` | Blocked at the safety stage |
| `alternative_search` | Fetch prices for the original medicine and its verified substitutes |
| `side_effects` | Return the JSON `side_effects` field |
| `uses_of_medicine` | Return the JSON `uses` field |
| `general_health` | `backend.llm.chatbot.get_response(message, previous_messages=...)` |

The dataset is `backend/data/medicines_final.json` and is cached on first
lookup. Every mentioned medicine is resolved before any handler runs, including
price and medicine-related general health. Ambiguous or unknown products request
clarification rather than choosing a product. Empty fields return `no_data`.
The general-health chatbot returns answer text in `results[].data`. Its prompt
limits answers to general educational health information and excludes diagnosis,
prescribing, dosage, and medicine-interaction advice. Connection or model failures
propagate to the CLI's error response; they are not presented as successful answers.

Duplicate medicine records differing only in normalized name formatting are
treated as one record when every other field agrees. Conflicting
records with the same normalized product name return an explicit error rather
than an unresolvable clarification loop. A supplied strength can be verified
against a single-ingredient composition when the product name omits units.
Missing composition strengths cannot establish a strength match or savings.

Ingredient-only requests such as `price of Diclofenac` offer verified product
choices even when a matching product-name prefix has conflicting records. Exact
conflicting products remain errors and are excluded from choices; selection still
runs the normal safety checks. A generic ingredient does not automatically select
the first matching injection, tablet, or other formulation.

The database cleanup removed 84 incomplete records only where a complete-strength
record existed under the same normalized name, leaving 245,984 records. Records
without a complete counterpart were retained. `backend/data/medicine_cleanup_report.json`
contains the removed records, their original indices, retained complete counterparts,
and before/after file hashes. Restart the backend to reload the cached database.

The regulatory category comes from the dataset. Schedule H and Schedule G
responses include a top-level `disclaimer`: `Please consult a doctor.` The
frontend must display this with the response data. If any requested medicine
matches Schedule X, the entire request returns a `block` action with `reason="schedule_x"`
with a direct message and no results, and no downstream service runs. The CLI
and frontend display the configured blocked-intent message when applicable, or
`Please consult a doctor.` for otherwise supported requests. The Schedule X check runs before intent blocking and clarification.
Safety attaches H/G disclaimers to its messages and response routing retains them
on final data responses; included H/G substitutes also trigger the disclaimer.

Price comparisons and alternative searches omit Schedule X and unverified substitutes before returning
names or fetching prices. Included H/G substitutes also trigger the disclaimer.
Unknown regulatory labels return a data-verification error. General-health requests without
medicines need no regulatory lookup. These are application routing rules using
the dataset labels; they do not authorize dispensing. The HTTP server uses these same routing rules.

## Pharmacy prices

`backend/services/price.py` makes read-only HTTPS requests to public pages and returns
JSON-ready product quotes. It uses the Python standard library; no new package
or browser installation is required. No stock, PIN-code, delivery-time, login,
cart, or checkout requests are made.

| Pharmacy | Current integration |
| --- | --- |
| Apollo | Apollo Pharmacy public product-page structured offers; product URLs from the catalogue |
| PharmEasy | Public search/product pages and embedded product pricing |
| Tata 1mg | Public product pages and embedded pricing; product URLs from the catalogue |
| Netmeds | Public search pages and embedded product pricing |
| MedPlus Mart | `integration_required` until a usable structured product page or partner integration is supplied |

Apollo uses the Apollo Pharmacy site, rather than an Apollo 24|7 private API.
These are website readers, not contracted pharmacy APIs. Sites can change their
markup or deny requests. Failures appear per pharmacy (`network_error`,
`access_denied`, `parse_error`, `product_not_found`, or `integration_required`);
other pharmacy results remain available. A row's `status="ok"` means its price
was read, not that it is in stock.

`backend/data/pharmacy_products.json` maps exact database product names to verified
HTTPS product-page URLs. It contains initial Apollo and Tata 1mg mappings for
Augmentin 625 Duo, Moxikind-CV 625, and verified Dolo 650 links. Add further names/URLs for those sources
as needed. Public search discovery is attempted when there is no mapping, but
their current search pages may return no server-rendered product data. Apollo
and Tata 1mg now fall back to headless public-page rendering for product links.
Install the updated `requirements.txt`; by default this uses installed Microsoft
Edge. On systems without Edge, run `python -m playwright install chromium` and
set `MEDIBOT_BROWSER_CHANNEL` to an empty string. Set `MEDIBOT_BROWSER_PRICES=0`
to disable browser discovery. The fallback uses at most two simultaneous browsers,
bounded navigation waits, and up to three exact matching product links per search.
Apollo OTC cards and their pack-count URLs are supported. Verified links are
cached in memory for one hour (failed discovery for two minutes); prices are fetched
again. Access restrictions remain failures, and exact product identity is checked
on the destination page. Missing prices show a reason in the UI. MedPlus
also accepts catalogue URLs if the supplied page exposes a structured offer.
URLs and redirects must stay on the configured pharmacy domain.

Ingredient requests such as `uses of paracetamol` or `price of paracetamol 500mg
tablets` offer matching database products. Selecting one retains the requested
uses, side-effects, or price intent. Strength filters apply to the named ingredient,
including in combinations; combinations are identified in the choices. A generic
ingredient does not automatically select an arbitrary brand or formulation.

Try the price reader without Ollama:

```powershell
.\.venv\Scripts\python.exe -m backend.services.price "Augmentin 625 Duo Tablet" "Moxikind-CV 625 Tablet"
```

For full routing, `handle_response()` returns `results[].data[]` comparison
objects for both price and alternative intents. Each comparison contains:

- `original`: name, composition, regulatory label, and pharmacy quotes.
- `alternatives`: the same information plus `composition_match` and `savings`.
- `verified_composition_matches`: count based on the local composition records.

Each product's `prices.quotes[]` includes the pharmacy, price, MRP when exposed,
pack size, per-unit price when known, product link, observation time, and offer
conditions. Missing prices are null, never invented. Explicit conditional offers
are marked and excluded from savings; PharmEasy's separately exposed assured
price is preferred over its conditional best offer. Fees and delivery costs are
not included. All public prices must be confirmed at pharmacy checkout.

Savings compare the cheapest non-conditional unit prices at the same pharmacy,
only when ingredient/strength records and dosage form/release markers match.
Different pack quantities are normalized per tablet/capsule. No savings are
computed from missing composition, unknown pack quantities, or conditional
prices. A composition match is a dataset comparison, not medical interchangeability.

The frontend displays quotes, conditions and missing prices, preserves H/G
disclaimers, and displays the direct Schedule X blocking message. Each comparison
also returns `max_savings`: the single largest unconditional percentage discount
across the original and matching alternatives at all quoted pharmacies. It uses
`(MRP - price) / MRP * 100` with the selected quote's own pack MRP, and includes
the medicine, pharmacy, price, MRP, amount saved, pack size, and source link.
Alternatives must match ingredients, strengths, dosage form and release markers.
Missing/invalid MRPs and conditional offers are excluded; no eligible discount
returns `null` and hides the card. Exact ties retain the first quote. This ranks
discount percentages, not lowest unit cost; delivery fees are excluded. Existing
per-pharmacy, per-unit savings remain.

`examples/price_response.json` contains an actual observed response for Augmentin
with both price and alternative intents. Its prices are a dated reference for
the frontend structure, not live data; rerun the backend to refresh quotes.

Run the routing tests without Ollama:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The tests cover HTTP sessions and the CLI conversation flow using mocked extraction, as well as
medicine routing and pharmacy parsers. They do not prove real model extraction;
that requires the Ollama server and the configured model to be available.


## Run the connected application

Start Ollama with the configured model, then start the backend from the project root:

```powershell
.\.venv\Scripts\python.exe -m backend.api
```

In a second terminal:

```powershell
cd Frontend
npm.cmd ci
npm.cmd run dev
```

Open http://localhost:5173. No account or sign-in is needed. Acknowledge the
medical disclaimer and send a message. Vite proxies `/api` to the Python server
at http://127.0.0.1:8000. `GET /api/health` is a server liveness check; it does not
verify Ollama or pharmacy connectivity. Production hosting needs to forward
`/api` to this backend on the same origin.

`POST /api/chat` accepts `message`, a UUID `request_id`, and an optional UUID
`session_id`. It returns `{session_id, result}`. The frontend creates a fresh
anonymous session on New chat, handles block/clarify/error/response separately,
and waits for the server to complete safety checks and routing. No raw extraction
or internal `continue` result is sent to the frontend. Schedule X returns a
blocking message without medicine details; the frontend renders this direct reply.

Conversation state is shared by `backend/services/conversation.py` and the CLI.
`backend/services/sessions.py` keeps bounded, expiring in-memory sessions and
serializes requests within each session. Retries reuse the request ID, avoiding
repeated model calls or history changes for completed requests. Errors can be
retried. New chat cancels waiting in the browser and ignores late responses;
server work already running may finish in the old session.

Run one backend worker for this in-memory implementation. Restarting the server
or 30 minutes of inactivity clears a session. Shared durable session storage is
needed before scaling to multiple workers. The API is intended for local use;
public hosting also needs deployment access controls and abuse limits.

API limits, ports, session settings, frontend timeout, and shared messages are in
`constants.txt`. Vite exposes only the public frontend settings and API limits,
not the model prompts. Restart both servers after editing configuration.

Frontend verification:

```powershell
cd Frontend
npm.cmd test
npm.cmd run lint
npm.cmd run build
```

These tests mock model output and external pharmacy requests. Live answers still
require Ollama; pharmacy price completeness remains dependent on public pages
and the configured product catalogue.

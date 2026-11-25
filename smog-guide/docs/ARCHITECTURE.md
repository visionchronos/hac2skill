# SmogGuide – Architecture

## Layer diagram

```
┌──────────────────────────────────────────────────────────┐
│  main.py  (composition root – wires concrete impls)      │
├──────────────────────────────────────────────────────────┤
│  api/     FastAPI routing, schemas, error mapping        │
│           imports: services, domain, utils               │
├──────────────────────────────────────────────────────────┤
│  services/  I/O, LLM, external HTTP, orchestration       │
│           imports: domain, prompts, utils                │
├──────────────────────────────────────────────────────────┤
│  prompts/   LLM prompt string builders                   │
│           imports: domain, utils                         │
├──────────────────────────────────────────────────────────┤
│  domain/    Pure business logic, frozen models, rules    │
│           imports: stdlib, pydantic, pyyaml, utils       │
├──────────────────────────────────────────────────────────┤
│  utils/     Shared helpers – errors, cache, constants    │
│           imports: stdlib only                           │
└──────────────────────────────────────────────────────────┘
```

Dependencies point **inward only**. No layer imports from a layer above it.
Collaborators are injected through `typing.Protocol` interfaces defined in `services/protocols.py`.

---

## Allowed-import table

| Layer     | May import                                              | Must NOT import                        |
|-----------|---------------------------------------------------------|----------------------------------------|
| `utils`   | stdlib                                                  | smogguide.*, fastapi, httpx, LLM SDKs |
| `domain`  | stdlib, pydantic, pyyaml, smogguide.utils               | services, api, prompts, fastapi, httpx, LLM SDKs |
| `prompts` | smogguide.domain, smogguide.utils, stdlib               | services, api, fastapi, httpx          |
| `services`| smogguide.domain, smogguide.prompts, smogguide.utils, httpx, LLM SDKs | smogguide.api, fastapi |
| `api`     | smogguide.services, smogguide.domain, smogguide.utils, fastapi | — |
| `main`    | everything (composition root)                           | — |

---

## Request data flow

```
Client POST /api/advice
        │
        ▼
api/routes.py          – validate request schema, call service
        │
        ▼
services/geocoding.py  – resolve location string → (lat, lon)
        │
        ▼
services/air_quality.py – fetch AQI for coordinates (cached)
        │
        ▼
domain/aqi.py          – classify raw AQI → AQIBand (CPCB scale)
        │
        ▼
domain/rules.py        – generate Recommendations from band + household profile
        │
        ▼
domain/impact.py       – attach estimated impact ranges to each recommendation
        │
        ▼
services/llm.py        – reword with LLM (or return template fallback if no key)
        │
        ▼
api/routes.py          – serialize and return JSON response
```

---

## Decisions

### Rules decide, LLM explains
All health-critical advice (masks, outdoor exposure limits, ventilation windows) is
produced by the deterministic rules engine in `domain/`. The LLM is only permitted to
reword already-computed recommendations. It must never invent medical claims, specific
numbers, or thresholds. The app must work fully with `SMOGGUIDE_LLM_PROVIDER=none`.

### No database
User health data (household profile) and free-text notes are sensitive and untrusted.
They are processed in memory for a single request and never persisted. There is no
database dependency.

### CPCB categories
AQI classification uses the official **Central Pollution Control Board (CPCB), India**
breakpoint scale (Good 0–50, Satisfactory 51–100, Moderate 101–200, Poor 201–300,
Very Poor 301–400, Severe 401+). This is the statutory scale used by all Indian
government air quality stations and displayed on the CPCB dashboard.

### Protocol-based dependency injection
Services expose `typing.Protocol` interfaces (`AQIProvider`, `LLMRewriter`, etc.)
defined in `services/protocols.py`. Concrete implementations are wired together in
`main.py` only. This allows unit tests to substitute fake providers without patching
internals, keeps layers loosely coupled, and enforces the "no business logic in main"
rule by making main purely a wiring module.

---

## How to add a new recommendation

1. Add an entry to `data/recommendations.yaml` with its AQI band, affected profiles,
   advice text template, estimated reduction range, and source/rationale.
2. Add or extend a rule in `domain/rules.py` to select the new entry for the right
   conditions.
3. Add a unit test in `tests/unit/test_rules.py` covering the new rule's conditions.
4. Run `make check` to verify no boundaries or type constraints are broken.

---

## How to run checks

```bash
make install   # install package + dev deps
make check     # lint + typecheck + test
make run       # start dev server on :8000
```

# Market Research Tool — Backend

FastAPI backend that turns a company name into a structured market analysis.
The core logic lives in `app/pipeline.py` and is testable on its own; FastAPI
(`app/main.py`) is a thin wrapper around it.

```
backend/
├── app/
│   ├── __init__.py     # package marker (empty)
│   ├── main.py         # FastAPI app: /health, /analyze
│   ├── schemas.py      # request/response models (the API contract)
│   └── pipeline.py     # core logic — currently a placeholder
├── requirements.txt
├── .env.example
└── .gitignore
```

## Setup

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                # then add your real OPENROUTER_API_KEY
```

## Run

```bash
uvicorn app.main:app --reload
```

Then open http://localhost:8000/docs to fire `/analyze` straight from the browser.

## Test the core logic in isolation (no server)

```bash
python -m app.pipeline "Stripe"
```

## Status

`pipeline.run` calls OpenRouter through its OpenAI-compatible API and validates
the structured response against `MarketAnalysis`. Next step: add retrieval
(RAG) over your data sources before the structured LLM call.

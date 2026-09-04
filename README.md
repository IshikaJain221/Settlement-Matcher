# Settlement Matcher

Reconciliation agent for the Razorpay AI Buildathon 2026 — Track 04 (AI Finance Controller).

Matches internal order records against bank settlements, resolves what it can automatically
(rules first, then AI-assisted reasoning for the tricky cases), and reports an honest exception
list for anything it can't explain.

## Project structure

```
settlement-matcher/
├── backend/
│   ├── main.py            FastAPI app (all endpoints)
│   ├── models.py          Data structures
│   ├── repository.py      Repository pattern — the only place that touches CSVs
│   ├── matchers.py        Strategy + Chain of Responsibility — the matching engine
│   ├── qa.py               Grounded Q&A over records
│   └── data_generator.py  Synthetic data generator
├── frontend/               Next.js app (landing page + dashboard)
├── data/
│   ├── internal_orders.csv
│   └── bank_settlements.csv
└── README.md
```

## Running it locally

**1. Backend**
```bash
cd backend
pip install fastapi uvicorn pydantic
uvicorn main:app --reload --port 8000
```

**2. Frontend** (separate terminal)
```bash
cd frontend
npm install
npm run dev
```

Then open http://localhost:3000 — click "Run reconciliation" on the dashboard.

## Regenerating the dataset

```bash
cd backend
python data_generator.py --count 80 --seed 42 --out ../data
```

## Design patterns used

- **Strategy** — RuleBasedMatcher and AIAssistedMatcher share one interface; interchangeable.
- **Chain of Responsibility** — records pass from the rule matcher to the AI matcher only if unresolved.
- **Repository** — all CSV/data access goes through one module (`repository.py`).
- **Adapter** — the Q&A layer reuses the FinSight AI retrieval pattern, adapted to structured records.

See the architecture and "explained simply" documents for the full write-up.

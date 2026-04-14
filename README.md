# Sach

AI-powered misinformation detection platform that verifies claims against retrieved evidence using RAG (Retrieval Augmented Generation).

## How It Works

1. **Query** - Submit a claim or statement to verify
2. **Retrieval** - FAISS vector search finds relevant sources from the knowledge base
3. **Verification** - LLM analyzes the claim against retrieved evidence
4. **Response** - Returns truth score, verdict, and explanation

## Tech Stack

- **FastAPI** - Web framework
- **FAISS** - Vector similarity search
- **LLM Routing** - Supports Ollama (local) or OpenRouter (cloud)
- **RAG Pipeline** - Retrieval Augmented Generation for fact-checking

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your API keys
```

## Configuration

Edit `config.yaml` to configure:

- **Ollama** - Local model settings (default: `mistral` at `http://localhost:11434`)
- **OpenRouter** - Cloud model settings (via `OPENROUTER_API_KEY` and `OPENROUTER_MODEL` in `.env`)
- **Retrieval** - FAISS index path and top_k results count

## Usage

```bash
# Index documents
python scripts/index_documents.py

# Run server
python -m app.main
```

API available at `http://localhost:8000`

### Endpoints

- `POST /verify` - Verify a claim
- `GET /health` - Health check

### Example Request

```bash
curl -X POST http://localhost:8000/verify \
  -H "Content-Type: application/json" \
  -d '{"query": "Your claim here", "use_cloud": false}'
```

### Example Response

```json
{
  "query": "Your claim here",
  "truth_score": 0.85,
  "verdict": "Likely True",
  "explanation": "Multiple sources confirm...",
  "sources": [...],
  "model_used": "mistral",
  "latency_ms": 234.5
}
```

## Architecture

```
app/
├── api/          # FastAPI routes
├── core/         # Exception handling
├── llm/          # LLM router (Ollama/OpenRouter)
├── models/       # Pydantic request/response models
└── pipeline/     # Core logic: embedding, retrieval, verification
```

## License

MIT
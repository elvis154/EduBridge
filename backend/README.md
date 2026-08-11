Backend (FastAPI) README

Setup:
1. cd backend
2. python3 -m venv .venv
3. source .venv/bin/activate
4. pip install -r requirements.txt
5. cp .env.example .env and set GEMINI_API_KEY if available
   - Optionally change GEMINI_MODEL or use OPENAI_API_KEY instead
6. uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   - Make sure to run this command from the `backend` directory so `app` imports resolve correctly.

To verify the backend loaded keys, open:
- http://localhost:8000/health

Endpoints:
- POST /upload (multipart form, file field 'file') -> {doc_id, text_excerpt}
- POST /ask (json {doc_id, question}) -> {answer, model, history}
- GET /docs/{doc_id}/history -> {history}

Notes:
- Uploaded PDFs are saved under backend/uploads as <doc_id>.pdf
- Chat history stored in SQLite by default at backend/chat_history.db
- The backend prefers GEMINI_API_KEY when set, and will fall back to OPENAI_API_KEY.
- If Gemini returns an authorization error, verify that GEMINI_API_KEY has access to the requested Gemini model.
- If no valid API key is available, the app will still attempt a local document-based fallback to answer simple questions.
- Do not commit your API keys to source control.

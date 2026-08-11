AI-Powered Document Reader

This repository scaffolds a Full Stack AI Document Reader: FastAPI backend + React frontend.

Quickstart (recommended):

1. Backend
   - cd backend
   - python3 -m venv .venv
   - source .venv/bin/activate
   - pip install -r requirements.txt
   - Copy .env.example to .env and set OPENAI_API_KEY if you have one
   - uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

2. Frontend (development)
   - cd frontend
   - npm install
   - npm run dev

Notes:
- The backend exposes endpoints:
  - POST /upload : multipart/form-data file -> extracts text and returns doc_id
  - POST /ask : JSON {doc_id, question} -> returns LLM answer and updated chat history
  - GET /docs/{doc_id}/history -> chat history for document

- LLM integration prefers GEMINI_API_KEY for Google Gemini and falls back to OPENAI_API_KEY if provided.
- PDF extraction uses PyPDF2; scanned PDFs (OCR) are not implemented but can be added with pytesseract + pillow.

See backend/README.md and frontend/README.md for more details.

import os
import shutil
import sys
import uuid
import asyncio
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime

from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from pydantic import BaseModel, Field


# ============================================================
# PATH SETUP
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


# ============================================================
# APPLICATION IMPORTS
# ============================================================

from app.pdf_utils import extract_text_from_pdf

from app.llm_client import (
    generate_answer,
    get_llm_stats,
    clear_cache,
)

from app import database


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


# ============================================================
# DIRECTORIES
# ============================================================

UPLOAD_DIR = BASE_DIR / "uploads"
TEXT_DIR = BASE_DIR / "extracted_text"

UPLOAD_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

TEXT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# FASTAPI APPLICATION
# ============================================================

app = FastAPI(
    title="EduBridge AI Document Reader API",
    description="Upload PDF documents and ask questions using AI.",
    version="3.1.0",
)


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        # Local development
        "http://localhost:5173",

        # Vercel production frontend
        "https://edu-bridge-six-eta.vercel.app",

        # Previous frontend deployment
        "https://edubridge-frontend.onrender.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# DATABASE
# ============================================================

try:
    database.init_db()
    logger.info("Database initialized successfully.")

except Exception as e:
    logger.exception(
        "Database initialization failed: %s",
        e,
    )


# ============================================================
# REQUEST / RESPONSE MODELS
# ============================================================

class AskRequest(BaseModel):
    doc_id: str
    question: str
    use_cache: bool = True


class AskResponse(BaseModel):
    answer: str

    model: str = "unknown"

    confidence: Optional[float] = None

    processing_time_ms: Optional[float] = None

    suggested_questions: list = Field(
        default_factory=list
    )

    history: list = Field(
        default_factory=list
    )

    fallback_from: Optional[str] = None

    structured_data: dict = Field(
        default_factory=dict
    )

    formatted_answer: Optional[str] = None

    citations: list = Field(
        default_factory=list
    )


class UploadResponse(BaseModel):
    doc_id: str

    filename: str

    text_excerpt: str

    word_count: int

    character_count: int


class HistoryResponse(BaseModel):
    history: list = Field(
        default_factory=list
    )

    total_messages: int


class ClearCacheResponse(BaseModel):
    status: str

    message: str


# ============================================================
# ROOT ROUTE
# ============================================================

@app.get("/")
async def root():

    return {
        "status": "online",
        "service": "EduBridge AI Document Reader API",
        "version": "3.1.0",
        "message": "EduBridge backend is running successfully.",
        "docs": "/docs",
        "health": "/health",
    }


# ============================================================
# API INFO
# ============================================================

@app.get("/api")
async def api_info():

    return {
        "service": "EduBridge API",
        "status": "online",
        "version": "3.1.0",
        "endpoints": {
            "health": "/health",
            "upload": "/upload",
            "ask": "/ask",
            "docs": "/docs",
            "stats": "/stats",
        },
    }


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def get_pdf_path(doc_id: str) -> Path:

    return UPLOAD_DIR / f"{doc_id}.pdf"


def get_text_path(doc_id: str) -> Path:

    return TEXT_DIR / f"{doc_id}.txt"


def document_exists(doc_id: str) -> bool:

    return get_pdf_path(doc_id).exists()


# ============================================================
# LOAD DOCUMENT TEXT
# ============================================================

def load_document_text(doc_id: str) -> str:

    text_path = get_text_path(doc_id)

    # --------------------------------------------------------
    # Try cached extracted text first
    # --------------------------------------------------------

    if text_path.exists():

        try:

            text = text_path.read_text(
                encoding="utf-8"
            )

            if text.strip():
                return text

        except Exception as e:

            logger.warning(
                "Could not read cached text for %s: %s",
                doc_id,
                e,
            )

    # --------------------------------------------------------
    # Fall back to PDF
    # --------------------------------------------------------

    pdf_path = get_pdf_path(doc_id)

    if not pdf_path.exists():

        raise FileNotFoundError(
            "Document not found"
        )

    text = extract_text_from_pdf(
        str(pdf_path)
    )

    if not text or len(text.strip()) < 10:

        raise ValueError(
            "Document contains no extractable text"
        )

    # --------------------------------------------------------
    # Save extracted text
    # --------------------------------------------------------

    try:

        text_path.write_text(
            text,
            encoding="utf-8",
        )

    except Exception as e:

        logger.warning(
            "Could not save extracted text: %s",
            e,
        )

    return text


# ============================================================
# BUILD CHAT HISTORY
# ============================================================

def build_history(doc_id: str) -> list:

    rows = database.get_history(doc_id)

    history = []

    for row in rows:

        # ----------------------------------------------------
        # SQLAlchemy ORM object
        # ----------------------------------------------------

        if hasattr(row, "timestamp"):

            timestamp = getattr(
                row,
                "timestamp",
                None,
            )

            role = getattr(
                row,
                "role",
                "",
            )

            message = getattr(
                row,
                "message",
                "",
            )

        # ----------------------------------------------------
        # SQLAlchemy Row / Tuple
        # ----------------------------------------------------

        else:

            try:

                mapping = getattr(
                    row,
                    "_mapping",
                    None,
                )

                if mapping is not None:

                    timestamp = mapping.get(
                        "timestamp",
                        mapping.get(
                            "created_at",
                            None,
                        ),
                    )

                    role = mapping.get(
                        "role",
                        "",
                    )

                    message = mapping.get(
                        "message",
                        mapping.get(
                            "content",
                            "",
                        ),
                    )

                else:

                    timestamp = row[0]

                    role = row[1]

                    message = row[2]

            except Exception as e:

                logger.warning(
                    "Could not parse history row: %s",
                    e,
                )

                continue

        # ----------------------------------------------------
        # Format timestamp
        # ----------------------------------------------------

        if timestamp is None:

            timestamp = ""

        elif hasattr(
            timestamp,
            "isoformat",
        ):

            timestamp = timestamp.isoformat()

        else:

            timestamp = str(timestamp)

        # ----------------------------------------------------
        # Add history
        # ----------------------------------------------------

        history.append(
            {
                "timestamp": timestamp,
                "role": str(role),
                "message": str(message),
            }
        )

    return history


# ============================================================
# UPLOAD PDF
# ============================================================

@app.post(
    "/upload",
    response_model=UploadResponse,
)
async def upload_pdf(
    file: UploadFile = File(...),
):

    if not file.filename:

        raise HTTPException(
            status_code=400,
            detail="Filename is required",
        )

    # --------------------------------------------------------
    # PDF validation
    # --------------------------------------------------------

    if not file.filename.lower().endswith(".pdf"):

        raise HTTPException(
            status_code=400,
            detail="Only PDF files are supported",
        )

    doc_id = str(uuid.uuid4())

    pdf_path = get_pdf_path(doc_id)

    text_path = get_text_path(doc_id)

    try:

        # ----------------------------------------------------
        # Save PDF
        # ----------------------------------------------------

        with open(
            pdf_path,
            "wb",
        ) as output_file:

            shutil.copyfileobj(
                file.file,
                output_file,
            )

        logger.info(
            "PDF saved: %s",
            pdf_path,
        )

        # ----------------------------------------------------
        # Extract text
        # ----------------------------------------------------

        text = extract_text_from_pdf(
            str(pdf_path)
        )

        if not text or len(text.strip()) < 10:

            raise HTTPException(
                status_code=400,
                detail=(
                    "The PDF contains no extractable text. "
                    "It may be scanned or image-based."
                ),
            )

        # ----------------------------------------------------
        # Save extracted text
        # ----------------------------------------------------

        text_path.write_text(
            text,
            encoding="utf-8",
        )

        cleaned_text = text.strip()

        word_count = len(
            cleaned_text.split()
        )

        character_count = len(
            cleaned_text
        )

        excerpt = cleaned_text[:1000]

        # ----------------------------------------------------
        # Save upload history
        # ----------------------------------------------------

        database.add_chat_entry(
            doc_id,
            "system",
            "Document uploaded successfully.",
        )

        database.add_chat_entry(
            doc_id,
            "system",
            f"Document contains approximately {word_count} words.",
        )

        logger.info(
            "Document uploaded successfully: %s",
            doc_id,
        )

        return UploadResponse(
            doc_id=doc_id,
            filename=file.filename,
            text_excerpt=excerpt,
            word_count=word_count,
            character_count=character_count,
        )

    except HTTPException:

        if pdf_path.exists():
            pdf_path.unlink()

        if text_path.exists():
            text_path.unlink()

        raise

    except Exception as e:

        logger.exception(
            "Upload failed: %s",
            e,
        )

        if pdf_path.exists():
            pdf_path.unlink()

        if text_path.exists():
            text_path.unlink()

        raise HTTPException(
            status_code=500,
            detail=f"Failed to process PDF: {str(e)}",
        )


# ============================================================
# ASK QUESTION
# ============================================================

@app.post(
    "/ask",
    response_model=AskResponse,
)
async def ask_question(
    req: AskRequest,
):

    try:

        # ----------------------------------------------------
        # Validate question
        # ----------------------------------------------------

        question = req.question.strip()

        if not question:

            raise HTTPException(
                status_code=400,
                detail="Question cannot be empty",
            )

        if len(question) > 2000:

            raise HTTPException(
                status_code=400,
                detail="Question is too long",
            )

        # ----------------------------------------------------
        # Check document
        # ----------------------------------------------------

        if not document_exists(req.doc_id):

            raise HTTPException(
                status_code=404,
                detail="Document not found",
            )

        logger.info(
            "ASK REQUEST | Document: %s | Question: %s",
            req.doc_id,
            question,
        )

        # ----------------------------------------------------
        # Load document
        # ----------------------------------------------------

        text = load_document_text(
            req.doc_id
        )

        if not text or len(text.strip()) < 10:

            raise HTTPException(
                status_code=400,
                detail=(
                    "Document contains no extractable text"
                ),
            )

        logger.info(
            "Document loaded. Characters: %s",
            len(text),
        )

        # ----------------------------------------------------
        # Save user question
        # ----------------------------------------------------

        database.add_chat_entry(
            req.doc_id,
            "user",
            question,
        )

        # ----------------------------------------------------
        # Generate AI answer
        # ----------------------------------------------------

        logger.info(
            "Calling generate_answer()..."
        )

        llm_resp = await asyncio.to_thread(
            generate_answer,
            question=question,
            context=text,
            use_cache=req.use_cache,
        )

        logger.info(
            "LLM response received."
        )

        # ----------------------------------------------------
        # Validate response
        # ----------------------------------------------------

        if not isinstance(
            llm_resp,
            dict,
        ):

            raise RuntimeError(
                "generate_answer() returned "
                f"{type(llm_resp)}, expected dict"
            )

        # ----------------------------------------------------
        # Extract response fields
        # ----------------------------------------------------

        answer = llm_resp.get(
            "answer",
            "I could not generate an answer.",
        )

        model = llm_resp.get(
            "model",
            "unknown",
        )

        confidence = llm_resp.get(
            "confidence"
        )

        processing_time = llm_resp.get(
            "processing_time_ms"
        )

        suggested_questions = llm_resp.get(
            "suggested_questions",
            [],
        )

        fallback_from = llm_resp.get(
            "fallback_from"
        )

        structured_data = llm_resp.get(
            "structured_data",
            {},
        )

        formatted_answer = llm_resp.get(
            "formatted_answer"
        )

        citations = llm_resp.get(
            "citations",
            [],
        )

        # ----------------------------------------------------
        # Ensure correct types
        # ----------------------------------------------------

        if not isinstance(
            answer,
            str,
        ):

            answer = str(answer)

        if not isinstance(
            suggested_questions,
            list,
        ):

            suggested_questions = []

        if not isinstance(
            structured_data,
            dict,
        ):

            structured_data = {}

        if not isinstance(
            citations,
            list,
        ):

            citations = []

        # ----------------------------------------------------
        # Save assistant answer
        # ----------------------------------------------------

        database.add_chat_entry(
            req.doc_id,
            "assistant",
            answer,
        )

        # ----------------------------------------------------
        # Build history
        # ----------------------------------------------------

        history = build_history(
            req.doc_id
        )

        # ----------------------------------------------------
        # Return response
        # ----------------------------------------------------

        return AskResponse(
            answer=answer,
            model=model,
            confidence=confidence,
            processing_time_ms=processing_time,
            suggested_questions=suggested_questions,
            history=history,
            fallback_from=fallback_from,
            structured_data=structured_data,
            formatted_answer=formatted_answer,
            citations=citations,
        )

    except HTTPException:

        raise

    except RuntimeError as e:

        logger.warning(
            "Runtime error in ask endpoint: %s",
            e,
        )

        raise HTTPException(
            status_code=503,
            detail=f"AI model unavailable: {str(e)}",
        )

    except Exception as e:

        logger.exception(
            "Question processing failed: %s",
            e,
        )

        raise HTTPException(
            status_code=500,
            detail=str(e),
        )


# ============================================================
# GET CHAT HISTORY
# ============================================================

@app.get(
    "/docs/{doc_id}/history",
    response_model=HistoryResponse,
)
async def get_history(
    doc_id: str,
):

    if not document_exists(doc_id):

        raise HTTPException(
            status_code=404,
            detail="Document not found",
        )

    try:

        history = build_history(
            doc_id
        )

        return HistoryResponse(
            history=history,
            total_messages=len(history),
        )

    except Exception as e:

        logger.exception(
            "Failed to get history: %s",
            e,
        )

        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve chat history",
        )


# ============================================================
# DELETE DOCUMENT
# ============================================================

@app.delete(
    "/docs/{doc_id}"
)
async def delete_document(
    doc_id: str,
):

    pdf_path = get_pdf_path(
        doc_id
    )

    text_path = get_text_path(
        doc_id
    )

    file_deleted = False

    text_deleted = False

    # --------------------------------------------------------
    # Delete PDF
    # --------------------------------------------------------

    if pdf_path.exists():

        try:

            pdf_path.unlink()

            file_deleted = True

        except Exception as e:

            logger.error(
                "Failed to delete PDF: %s",
                e,
            )

    # --------------------------------------------------------
    # Delete extracted text
    # --------------------------------------------------------

    if text_path.exists():

        try:

            text_path.unlink()

            text_deleted = True

        except Exception as e:

            logger.error(
                "Failed to delete extracted text: %s",
                e,
            )

    # --------------------------------------------------------
    # Delete chat history
    # --------------------------------------------------------

    try:

        database.clear_history(
            doc_id
        )

    except Exception as e:

        logger.error(
            "Failed to clear history: %s",
            e,
        )

    logger.info(
        "Document deleted: %s",
        doc_id,
    )

    return {
        "status": "success",
        "message": "Document and chat history deleted",
        "file_deleted": file_deleted,
        "text_deleted": text_deleted,
    }


# ============================================================
# CLEAR CACHE
# ============================================================

@app.post(
    "/cache/clear",
    response_model=ClearCacheResponse,
)
async def clear_response_cache():

    try:

        clear_cache()

        logger.info(
            "LLM cache cleared"
        )

        return ClearCacheResponse(
            status="success",
            message="LLM response cache cleared successfully",
        )

    except Exception as e:

        logger.exception(
            "Failed to clear cache: %s",
            e,
        )

        raise HTTPException(
            status_code=500,
            detail="Failed to clear cache",
        )


# ============================================================
# LLM STATS
# ============================================================

@app.get(
    "/stats"
)
async def get_stats():

    try:

        return get_llm_stats()

    except Exception as e:

        logger.exception(
            "Failed to get LLM stats: %s",
            e,
        )

        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve LLM statistics",
        )


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get(
    "/health"
)
async def health_check():

    return {
        "status": "healthy",

        "timestamp": datetime.now().isoformat(),

        "gemini_key_loaded": bool(
            os.environ.get(
                "GEMINI_API_KEY"
            )
        ),

        "openai_key_loaded": bool(
            os.environ.get(
                "OPENAI_API_KEY"
            )
        ),

        "gemini_model": os.environ.get(
            "GEMINI_MODEL",
            "gemini-flash-latest",
        ),

        "openai_model": os.environ.get(
            "OPENAI_MODEL",
            "gpt-5-mini",
        ),

        "upload_dir_exists": UPLOAD_DIR.exists(),

        "text_dir_exists": TEXT_DIR.exists(),

        "database_initialized": True,
    }


# ============================================================
# EXCEPTION HANDLERS
# ============================================================

@app.exception_handler(
    HTTPException
)
async def http_exception_handler(
    request: Request,
    exc: HTTPException,
):

    logger.warning(
        "HTTP %s: %s",
        exc.status_code,
        exc.detail,
    )

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail
        },
    )


@app.exception_handler(
    Exception
)
async def general_exception_handler(
    request: Request,
    exc: Exception,
):

    logger.exception(
        "Unhandled exception: %s",
        exc,
    )

    return JSONResponse(
        status_code=500,
        content={
            "detail": (
                "An unexpected error occurred. "
                "Please try again."
            )
        },
    )


# ============================================================
# START SERVER
# ============================================================

if __name__ == "__main__":

    import uvicorn

    port = int(
        os.environ.get(
            "PORT",
            "8000",
        )
    )

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        log_level="info",
    )
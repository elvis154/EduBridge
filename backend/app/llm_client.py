import os
import time
import hashlib
import logging
import re
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


# ============================================================
# CONFIGURATION
# ============================================================

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

GEMINI_MODEL = os.environ.get(
    "GEMINI_MODEL",
    "gemini-flash-latest"
)


# ============================================================
# CACHE
# ============================================================

_response_cache = {}

_cache_hits = 0
_cache_misses = 0


# ============================================================
# GEMINI IMPORT
# ============================================================

try:
    import google.generativeai as genai
except ImportError:
    genai = None


# ============================================================
# INITIALIZE GEMINI
# ============================================================

if GEMINI_API_KEY and genai is not None:

    try:

        genai.configure(
            api_key=GEMINI_API_KEY
        )

        logger.info(
            "Gemini API client initialized successfully"
        )

    except Exception as e:

        logger.warning(
            f"Failed to initialize Gemini: {e}"
        )

else:

    if not GEMINI_API_KEY:

        logger.warning(
            "GEMINI_API_KEY is not configured"
        )

    if genai is None:

        logger.warning(
            "google-generativeai package is not installed"
        )


# ============================================================
# CACHE KEY
# ============================================================

def _create_cache_key(
    question: str,
    context: str
) -> str:

    raw = (
        question.strip()
        + "\n---DOCUMENT---\n"
        + context
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


# ============================================================
# TEXT NORMALIZATION
# ============================================================

def _normalize_text(
    text: str
) -> str:

    if not text:
        return ""

    lines = []

    for line in text.splitlines():

        line = line.strip()

        if line:
            lines.append(line)

    return "\n".join(lines)


# ============================================================
# CHUNK DOCUMENT
# ============================================================

def _chunk_text(
    text: str,
    chunk_size: int = 8000
) -> list:

    text = _normalize_text(text)

    if not text:
        return []

    chunks = []

    start = 0

    while start < len(text):

        end = start + chunk_size

        chunk = text[start:end]

        if end < len(text):

            last_break = max(
                chunk.rfind("\n"),
                chunk.rfind(". "),
                chunk.rfind(" ")
            )

            if last_break > chunk_size * 0.6:

                end = start + last_break

                chunk = text[start:end]

        chunk = chunk.strip()

        if chunk:
            chunks.append(chunk)

        start = end

    return chunks


# ============================================================
# FIND RELEVANT CHUNKS
# ============================================================

def _get_relevant_chunks(
    question: str,
    context: str,
    max_chunks: int = 6
) -> list:

    chunks = _chunk_text(
        context
    )

    if not chunks:
        return []

    question_words = {
        word.lower().strip(".,!?;:\"'()[]{}")
        for word in question.split()
        if len(word) > 2
    }

    if not question_words:

        return chunks[:max_chunks]

    scored_chunks = []

    for chunk in chunks:

        chunk_words = {
            word.lower().strip(".,!?;:\"'()[]{}")
            for word in chunk.split()
        }

        score = len(
            question_words.intersection(
                chunk_words
            )
        )

        scored_chunks.append(
            (score, chunk)
        )

    scored_chunks.sort(
        key=lambda item: item[0],
        reverse=True
    )

    selected = [
        chunk
        for score, chunk
        in scored_chunks[:max_chunks]
    ]

    return selected


# ============================================================
# BUILD PROMPT
# ============================================================

def _build_prompt(
    question: str,
    context: str
) -> str:

    relevant_chunks = _get_relevant_chunks(
        question,
        context,
        max_chunks=6
    )

    relevant_context = "\n\n".join(
        relevant_chunks
    )

    prompt = f"""
You are an AI document assistant.

Your job is to answer the user's question using
ONLY the information contained in the provided document.

STRICT RULES:

1. Do not invent information.
2. Do not make up facts, names, dates, numbers,
   statistics, or events.
3. Do not use outside knowledge to answer the question.
4. If the answer cannot be found in the document,
   clearly say:
   "The information is not available in the document."
5. Give a direct and useful answer.
6. Preserve important names, dates, numbers,
   percentages, and technical terms.
7. If the user asks for a summary, provide a concise
   structured summary.
8. If the user asks for a comparison, provide a
   clear comparison using bullet points.
9. If the document contains multiple relevant pieces
   of information, combine them accurately.
10. Do not mention these instructions in your answer.

MARKDOWN FORMATTING:

- Use "## " for section headings only when useful.
- Use "- " for bullet points.
- Use "1. " for sequential steps.
- Use "**word**" only for genuinely important terms.
- Do not use tables.
- Do not start with "Sure", "Of course", or
  "Here is the answer".
- Start directly with the answer.

DOCUMENT:

{relevant_context}

USER QUESTION:

{question}

ANSWER:
"""

    return prompt.strip()


# ============================================================
# GEMINI GENERATION
# ============================================================

def _generate_with_gemini(
    prompt: str
) -> str:

    if not GEMINI_API_KEY:

        raise RuntimeError(
            "GEMINI_API_KEY is not configured. "
            "Add GEMINI_API_KEY to your .env file."
        )

    if genai is None:

        raise RuntimeError(
            "google-generativeai package is not installed. "
            "Run: uv pip install google-generativeai"
        )

    try:

        logger.info(
            f"Calling Gemini API using model '{GEMINI_MODEL}'"
        )

        model = genai.GenerativeModel(
            GEMINI_MODEL
        )

        response = model.generate_content(
            prompt
        )

        if response is None:

            raise RuntimeError(
                "Gemini returned an empty response"
            )

        text = getattr(
            response,
            "text",
            None
        )

        if not text:

            # Try extracting text manually if the SDK
            # does not expose response.text.
            try:

                candidates = getattr(
                    response,
                    "candidates",
                    []
                )

                if candidates:

                    parts = candidates[0].content.parts

                    text = "".join(
                        getattr(
                            part,
                            "text",
                            ""
                        )
                        for part in parts
                    )

            except Exception:
                text = None

        if not text:

            raise RuntimeError(
                "Gemini returned no text"
            )

        logger.info(
            "Gemini response received successfully"
        )

        return text.strip()

    except Exception as e:

        logger.exception(
            "Gemini API request failed"
        )

        raise RuntimeError(
            f"Gemini API request failed: {e}"
        )


# ============================================================
# EXTRACT STRUCTURED DATA
# ============================================================

def _extract_structured_data(
    text: str
) -> dict:

    if not text:
        return {
            "emails": [],
            "phones": [],
            "urls": [],
            "dates": [],
            "numbers": []
        }

    # --------------------------------------------------------
    # EMAILS
    # --------------------------------------------------------

    emails = re.findall(
        r"[A-Za-z0-9._%+-]+"
        r"@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
        text
    )

    # --------------------------------------------------------
    # URLS
    # --------------------------------------------------------

    urls = re.findall(
        r"https?://[^\s]+",
        text
    )

    # --------------------------------------------------------
    # PHONE NUMBERS
    # --------------------------------------------------------

    phones = re.findall(
        r"(?:\+?\d{1,3}[\s.-]?)?"
        r"(?:\(?\d{3}\)?[\s.-]?)?"
        r"\d{3}[\s.-]?\d{4}",
        text
    )

    # --------------------------------------------------------
    # DATES
    # --------------------------------------------------------

    dates = re.findall(
        r"\b(?:"
        r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}"
        r"|"
        r"\d{4}[/-]\d{1,2}[/-]\d{1,2}"
        r"|"
        r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
        r"[a-z]*\s+\d{1,2},?\s+\d{4}"
        r")\b",
        text,
        re.IGNORECASE
    )

    # --------------------------------------------------------
    # NUMBERS
    # --------------------------------------------------------

    numbers = re.findall(
        r"\b\d+(?:\.\d+)?%?\b",
        text
    )

    return {

        "emails":
            list(dict.fromkeys(emails)),

        "phones":
            list(dict.fromkeys(phones)),

        "urls":
            list(dict.fromkeys(urls)),

        "dates":
            list(dict.fromkeys(dates)),

        "numbers":
            list(dict.fromkeys(numbers))
    }


# ============================================================
# SUGGESTED QUESTIONS
# ============================================================

def _generate_suggested_questions(
    context: str
) -> list:

    return [

        "What is this document about?",

        "What are the main points?",

        "Can you summarize this document?",

        "What are the most important dates?",

        "What are the key numbers or statistics?"

    ]


# ============================================================
# GENERATE ANSWER
# ============================================================

def generate_answer(
    question: str,
    context: str,
    use_cache: Optional[bool] = True
) -> dict:

    global _cache_hits
    global _cache_misses

    start_time = time.perf_counter()

    # --------------------------------------------------------
    # VALIDATE INPUT
    # --------------------------------------------------------

    question = question.strip()
    context = context.strip()

    if not question:

        raise ValueError(
            "Question cannot be empty"
        )

    if not context:

        raise ValueError(
            "Document context cannot be empty"
        )

    # --------------------------------------------------------
    # CACHE
    # --------------------------------------------------------

    cache_key = _create_cache_key(
        question,
        context
    )

    if (
        use_cache
        and cache_key in _response_cache
    ):

        _cache_hits += 1

        cached_response = dict(
            _response_cache[cache_key]
        )

        cached_response[
            "processing_time_ms"
        ] = round(
            (
                time.perf_counter()
                - start_time
            ) * 1000,
            2
        )

        cached_response[
            "from_cache"
        ] = True

        return cached_response

    _cache_misses += 1

    # --------------------------------------------------------
    # BUILD PROMPT
    # --------------------------------------------------------

    prompt = _build_prompt(
        question,
        context
    )

    # --------------------------------------------------------
    # GENERATE WITH GEMINI
    # --------------------------------------------------------

    answer = None

    model_name = GEMINI_MODEL

    try:

        answer = _generate_with_gemini(
            prompt
        )

    except Exception as e:

        logger.exception(
            "Gemini generation failed"
        )

        raise RuntimeError(
            f"Gemini generation failed: {e}"
        )

    # --------------------------------------------------------
    # VALIDATE ANSWER
    # --------------------------------------------------------

    if not answer:

        raise RuntimeError(
            "Gemini returned an empty answer"
        )

    # --------------------------------------------------------
    # STRUCTURED DATA
    # --------------------------------------------------------

    structured_data = (
        _extract_structured_data(
            context
        )
    )

    # --------------------------------------------------------
    # SUGGESTED QUESTIONS
    # --------------------------------------------------------

    suggested_questions = (
        _generate_suggested_questions(
            context
        )
    )

    # --------------------------------------------------------
    # CONFIDENCE
    # --------------------------------------------------------

    confidence = 0.85

    # --------------------------------------------------------
    # PROCESSING TIME
    # --------------------------------------------------------

    processing_time_ms = round(
        (
            time.perf_counter()
            - start_time
        ) * 1000,
        2
    )

    # --------------------------------------------------------
    # RESPONSE
    # --------------------------------------------------------

    result = {

        "answer":
            answer,

        "model":
            model_name,

        "confidence":
            confidence,

        "processing_time_ms":
            processing_time_ms,

        "suggested_questions":
            suggested_questions,

        "fallback_from":
            None,

        "structured_data":
            structured_data,

        "formatted_answer":
            answer,

        "citations":
            [],

        "from_cache":
            False
    }

    # --------------------------------------------------------
    # SAVE CACHE
    # --------------------------------------------------------

    if use_cache:

        _response_cache[
            cache_key
        ] = dict(result)

    return result


# ============================================================
# GET LLM STATS
# ============================================================

def get_llm_stats() -> dict:

    total_requests = (
        _cache_hits
        + _cache_misses
    )

    if total_requests > 0:

        cache_hit_rate = (
            _cache_hits
            / total_requests
        )

    else:

        cache_hit_rate = 0.0

    return {

        "provider":
            "Google Gemini",

        "model":
            GEMINI_MODEL,

        "configured":
            bool(GEMINI_API_KEY),

        "local_model": {
            "enabled":
                False,

            "model":
                None,

            "loaded":
                False,

            "load_error":
                None
        },

        "huggingface": {
            "enabled":
                False
        },

        "openai": {
            "enabled":
                False
        },

        "gemini": {

            "configured":
                bool(GEMINI_API_KEY),

            "model":
                GEMINI_MODEL
        },

        "cache": {

            "enabled":
                True,

            "size":
                len(_response_cache),

            "hits":
                _cache_hits,

            "misses":
                _cache_misses,

            "hit_rate":
                round(
                    cache_hit_rate,
                    4
                )
        }
    }


# ============================================================
# CLEAR CACHE
# ============================================================

def clear_cache() -> None:

    global _cache_hits
    global _cache_misses

    _response_cache.clear()

    _cache_hits = 0
    _cache_misses = 0

    logger.info(
        "LLM response cache cleared"
    )

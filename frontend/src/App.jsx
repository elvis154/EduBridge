
import React, {
  useEffect,
  useRef,
  useState,
} from "react";

import axios from "axios";

import {
  Upload,
  FileText,
  Send,
  Loader2,
  Copy,
  Check,
  Trash2,
  ChevronDown,
  ChevronUp,
  MessageSquare,
  Plus,
} from "lucide-react";

import "./App.css";

const API_URL =
  import.meta.env.VITE_API_URL ||
  "http://localhost:8000";

/* ============================================================
   MARKDOWN INLINE RENDERER
============================================================ */

function renderInline(text, keyPrefix) {
  const parts = text
    .split(/(\*\*[^\*]+\*\*)/g)
    .filter(Boolean);

  return parts.map((part, i) => {
    if (
      part.startsWith("**") &&
      part.endsWith("**") &&
      part.length > 3
    ) {
      return (
        <strong
          key={`${keyPrefix}-b-${i}`}
          className="font-semibold text-gray-900"
        >
          {part.slice(2, -2)}
        </strong>
      );
    }

    return (
      <React.Fragment key={`${keyPrefix}-t-${i}`}>
        {part}
      </React.Fragment>
    );
  });
}

/* ============================================================
   FORMATTED ANSWER
============================================================ */

function FormattedAnswer({
  text,
  className = "",
}) {
  if (!text) return null;

  const lines = text
    .replace(/\r\n/g, "\n")
    .split("\n");

  const blocks = [];

  let list = null;

  const flushList = () => {
    if (list) {
      blocks.push(list);
      list = null;
    }
  };

  lines.forEach((rawLine, idx) => {
    const line = rawLine.trim();

    if (!line) {
      flushList();
      return;
    }

    const headingMatch =
      line.match(/^#{1,3}\s+(.*)/);

    const bulletMatch =
      line.match(/^[-*]\s+(.*)/);

    const orderedMatch =
      line.match(/^\d+[.)]\s+(.*)/);

    if (headingMatch) {
      flushList();

      blocks.push({
        type: "heading",
        content: headingMatch[1],
        key: idx,
      });
    } else if (bulletMatch) {
      if (!list || list.type !== "ul") {
        flushList();

        list = {
          type: "ul",
          items: [],
        };
      }

      list.items.push(
        bulletMatch[1]
      );
    } else if (orderedMatch) {
      if (!list || list.type !== "ol") {
        flushList();

        list = {
          type: "ol",
          items: [],
        };
      }

      list.items.push(
        orderedMatch[1]
      );
    } else {
      flushList();

      blocks.push({
        type: "p",
        content: line,
        key: idx,
      });
    }
  });

  flushList();

  return (
    <div className={className}>
      {blocks.map((block, i) => {
        if (block.type === "heading") {
          return (
            <h3
              key={i}
              className="mb-2 mt-5 text-base font-semibold text-gray-900 first:mt-0"
            >
              {renderInline(
                block.content,
                i
              )}
            </h3>
          );
        }

        if (block.type === "ul") {
          return (
            <ul
              key={i}
              className="my-3 list-disc space-y-2 pl-5"
            >
              {block.items.map(
                (item, j) => (
                  <li key={j}>
                    {renderInline(
                      item,
                      `${i}-${j}`
                    )}
                  </li>
                )
              )}
            </ul>
          );
        }

        if (block.type === "ol") {
          return (
            <ol
              key={i}
              className="my-3 list-decimal space-y-2 pl-5"
            >
              {block.items.map(
                (item, j) => (
                  <li key={j}>
                    {renderInline(
                      item,
                      `${i}-${j}`
                    )}
                  </li>
                )
              )}
            </ol>
          );
        }

        return (
          <p
            key={i}
            className="mb-3 last:mb-0"
          >
            {renderInline(
              block.content,
              i
            )}
          </p>
        );
      })}
    </div>
  );
}

/* ============================================================
   THINKING DOTS
============================================================ */

function ThinkingIndicator() {
  return (
    <div className="flex items-center gap-1.5">
      <span className="thinking-dot" />
      <span className="thinking-dot thinking-dot-delay-1" />
      <span className="thinking-dot thinking-dot-delay-2" />
    </div>
  );
}

/* ============================================================
   APP
============================================================ */

export default function App() {
  const [file, setFile] =
    useState(null);

  const [docId, setDocId] =
    useState("");

  const [question, setQuestion] =
    useState("");

  const [answer, setAnswer] =
    useState("");

  const [
    formattedAnswer,
    setFormattedAnswer,
  ] = useState("");

  const [
    structuredData,
    setStructuredData,
  ] = useState({});

  const [
    suggestedQuestions,
    setSuggestedQuestions,
  ] = useState([]);

  const [respModel, setRespModel] =
    useState("");

  const [
    respConfidence,
    setRespConfidence,
  ] = useState(null);

  const [history, setHistory] =
    useState([]);

  const [uploading, setUploading] =
    useState(false);

  const [asking, setAsking] =
    useState(false);

  const [copied, setCopied] =
    useState(false);

  const [status, setStatus] =
    useState("");

  const [showHistory, setShowHistory] =
    useState(true);

  const fileInputRef =
    useRef(null);

  const questionInputRef =
    useRef(null);

  const chatContainerRef =
    useRef(null);

  /* ============================================================
     AUTO FOCUS
  ============================================================ */

  useEffect(() => {
    if (docId) {
      setTimeout(() => {
        questionInputRef.current?.focus();
      }, 400);
    }
  }, [docId]);

  /* ============================================================
     AUTO SCROLL CHAT
  ============================================================ */

  useEffect(() => {
    if (!docId) return;

    const container =
      chatContainerRef.current;

    if (!container) return;

    requestAnimationFrame(() => {
      container.scrollTo({
        top: container.scrollHeight,
        behavior: "smooth",
      });
    });
  }, [
    history,
    asking,
    formattedAnswer,
    docId,
  ]);

  /* ============================================================
     FILE SELECTION
  ============================================================ */

  const handleFileChange = (
    event
  ) => {
    const selectedFile =
      event.target.files?.[0];

    if (!selectedFile) return;

    if (
      !selectedFile.name
        .toLowerCase()
        .endsWith(".pdf")
    ) {
      setStatus(
        "Only PDF files are supported."
      );

      setFile(null);
      return;
    }

    if (
      selectedFile.size >
      50 * 1024 * 1024
    ) {
      setStatus(
        "File size must be less than 50MB."
      );

      setFile(null);
      return;
    }

    setFile(selectedFile);
    setStatus("");
  };

  /* ============================================================
     UPLOAD DOCUMENT
  ============================================================ */

  const uploadDocument =
    async () => {
      if (!file) {
        setStatus(
          "Please select a PDF first."
        );

        return;
      }

      setUploading(true);

      setStatus(
        "Reading document..."
      );

      const formData =
        new FormData();

      formData.append(
        "file",
        file
      );

      try {
        const response =
          await axios.post(
            `${API_URL}/upload`,
            formData,
            {
              timeout: 120000,
            }
          );

        const data =
          response.data || {};

        setDocId(
          data.doc_id || ""
        );

        setAnswer("");

        setFormattedAnswer("");

        setStructuredData({});

        setSuggestedQuestions([]);

        setQuestion("");

        setHistory([]);

        setRespModel("");

        setRespConfidence(null);

        setShowHistory(true);

        const wordCount =
          data.word_count || 0;

        if (wordCount) {
          setStatus(
            `Document ready • ${wordCount.toLocaleString()} words`
          );
        } else {
          setStatus(
            "Document ready"
          );
        }
      } catch (error) {
        console.error(
          "Upload error:",
          error
        );

        const message =
          error?.response?.data
            ?.detail ||
          error?.message ||
          "Failed to upload document.";

        setStatus(message);
      } finally {
        setUploading(false);
      }
    };

  /* ============================================================
     ASK QUESTION
  ============================================================ */

  const askQuestion =
    async () => {
      await askQuestionInternal();
    };

  const askQuestionInternal =
    async (
      overrideQuestion = ""
    ) => {
      if (!docId) {
        setStatus(
          "Please upload a document first."
        );

        return;
      }

      const q =
        overrideQuestion.trim() ||
        question.trim();

      if (!q) {
        setStatus(
          "Please enter a question."
        );

        return;
      }

      if (q.length > 2000) {
        setStatus(
          "Question is too long. Please keep it under 2000 characters."
        );

        return;
      }

      setAsking(true);

      setStatus("");

      /*
       * Immediately add the user question
       * so it animates from the right.
       */

      const temporaryUserMessage = {
        role: "user",
        message: q,
        timestamp:
          new Date().toISOString(),
        temporary: true,
      };

      setHistory((prev) => [
        ...prev,
        temporaryUserMessage,
      ]);

      setQuestion("");

      try {
        const response =
          await axios.post(
            `${API_URL}/ask`,
            {
              doc_id: docId,
              question: q,
              use_cache: true,
            },
            {
              timeout: 120000,
            }
          );

        const resp =
          response.data || {};

        const generatedAnswer =
          resp.formatted_answer ||
          resp.answer ||
          "I couldn't find an answer to that question in the document.";

        setAnswer(
          resp.answer || ""
        );

        setFormattedAnswer(
          generatedAnswer
        );

        setStructuredData(
          resp.structured_data || {}
        );

        setSuggestedQuestions(
          Array.isArray(
            resp.suggested_questions
          )
            ? resp.suggested_questions
            : []
        );

        setRespModel(
          resp.model || ""
        );

        setRespConfidence(
          resp.confidence ?? null
        );

        /*
         * Use backend history as the
         * source of truth after response.
         */

        setHistory(
          Array.isArray(
            resp.history
          )
            ? resp.history
            : []
        );

        setTimeout(() => {
          questionInputRef.current?.focus();
        }, 200);
      } catch (error) {
        console.error(
          "Question error:",
          error
        );

        let message =
          error?.response?.data
            ?.detail ||
          error?.message ||
          "Failed to generate an answer.";

        if (
          error?.response?.status ===
          500
        ) {
          message =
            error?.response?.data
              ?.detail ||
            "Server error while generating the answer. Check your backend terminal.";
        }

        setStatus(message);

        /*
         * Remove temporary user
         * message if request failed.
         */

        setHistory((prev) =>
          prev.filter(
            (item) =>
              !item.temporary
          )
        );
      } finally {
        setAsking(false);
      }
    };

  /* ============================================================
     SUGGESTION
  ============================================================ */

  const handleSuggestionClick =
    (suggestion) => {
      if (!suggestion || asking)
        return;

      askQuestionInternal(
        suggestion
      );
    };

  /* ============================================================
     DELETE
  ============================================================ */

  const deleteDocument =
    async () => {
      if (!docId) return;

      const confirmed =
        window.confirm(
          "Delete this document and its conversation?"
        );

      if (!confirmed) return;

      try {
        await axios.delete(
          `${API_URL}/docs/${docId}`,
          {
            timeout: 30000,
          }
        );

        resetApplication();

        setStatus(
          "Document deleted."
        );
      } catch (error) {
        console.error(
          "Delete error:",
          error
        );

        setStatus(
          error?.response?.data
            ?.detail ||
            "Failed to delete document."
        );
      }
    };

  /* ============================================================
     RESET
  ============================================================ */

  const resetApplication =
    () => {
      setFile(null);

      setDocId("");

      setQuestion("");

      setAnswer("");

      setFormattedAnswer("");

      setStructuredData({});

      setSuggestedQuestions([]);

      setRespModel("");

      setRespConfidence(null);

      setHistory([]);

      setStatus("");

      setShowHistory(true);

      setCopied(false);

      if (
        fileInputRef.current
      ) {
        fileInputRef.current.value =
          "";
      }
    };

  /* ============================================================
     COPY
  ============================================================ */

  const copyAnswer = async () => {
    const textToCopy =
      formattedAnswer ||
      answer;

    if (!textToCopy) return;

    try {
      await navigator.clipboard.writeText(
        textToCopy
      );

      setCopied(true);

      setTimeout(() => {
        setCopied(false);
      }, 2000);
    } catch (error) {
      console.error(
        "Copy failed:",
        error
      );

      setStatus(
        "Failed to copy answer."
      );
    }
  };

  /* ============================================================
     KEYBOARD
  ============================================================ */

  const handleKeyDown =
    (event) => {
      if (
        event.key === "Enter" &&
        !event.shiftKey &&
        !event.nativeEvent
          .isComposing
      ) {
        event.preventDefault();

        if (!asking) {
          askQuestion();
        }
      }
    };

  /* ============================================================
     CONVERSATION
  ============================================================ */

  const conversationMessages =
    history.filter(
      (item) =>
        item.role === "user" ||
        item.role === "assistant"
    );

  /* ============================================================
     RENDER
  ============================================================ */

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-gray-50 text-gray-900">

      {/* ======================================================
          HEADER
      ====================================================== */}

      <header className="flex h-16 flex-shrink-0 items-center justify-between border-b border-gray-200 bg-white px-5">

        <div className="flex items-center gap-3">

          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gray-900">
            <FileText className="h-4 w-4 text-white" />
          </div>

          <div>
            <h1 className="text-sm font-semibold tracking-tight">
              Document AI
            </h1>

            <p className="text-xs text-gray-500">
              Ask questions about your documents
            </p>
          </div>

        </div>

        {docId && (
          <div className="flex items-center gap-2">

            <button
              onClick={resetApplication}
              disabled={
                asking ||
                uploading
              }
              className="button-animation flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-gray-500 hover:bg-gray-100 hover:text-gray-800 disabled:opacity-50"
            >
              <Plus className="h-4 w-4" />

              <span className="hidden sm:block">
                New
              </span>
            </button>

            <button
              onClick={
                deleteDocument
              }
              disabled={
                asking ||
                uploading
              }
              className="button-animation flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-gray-500 hover:bg-red-50 hover:text-red-600 disabled:opacity-50"
            >
              <Trash2 className="h-4 w-4" />

              <span className="hidden sm:block">
                Delete
              </span>
            </button>

          </div>
        )}

      </header>

      {/* ======================================================
          UPLOAD SCREEN
      ====================================================== */}

      {!docId && (
        <main className="flex flex-1 items-center justify-center overflow-y-auto px-5 py-10">

          <section className="upload-transition mx-auto w-full max-w-2xl">

            <div className="mb-8 text-center">

              <h2 className="text-3xl font-semibold tracking-tight text-gray-900 sm:text-4xl">
                Ask your document anything.
              </h2>

              <p className="mx-auto mt-3 max-w-lg text-sm leading-6 text-gray-500">
                Upload a PDF and ask questions.
                Answers are generated using
                the content of your document.
              </p>

            </div>

            <div
              onClick={() =>
                !uploading &&
                fileInputRef.current?.click()
              }
              className={`group rounded-2xl border-2 border-dashed border-gray-300 bg-white px-6 py-14 text-center transition-all duration-300 ${
                uploading
                  ? "cursor-not-allowed opacity-60"
                  : "cursor-pointer hover:-translate-y-1 hover:border-gray-500 hover:bg-gray-50 hover:shadow-lg"
              }`}
            >

              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,application/pdf"
                className="hidden"
                onChange={
                  handleFileChange
                }
                disabled={uploading}
              />

              <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-xl bg-gray-100 transition-all duration-300 group-hover:scale-105 group-hover:bg-gray-200">
                <Upload className="h-6 w-6 text-gray-600" />
              </div>

              <h3 className="mt-5 text-sm font-medium text-gray-900">
                {file
                  ? file.name
                  : "Upload a PDF document"}
              </h3>

              <p className="mt-2 text-xs text-gray-500">
                {file
                  ? `${(
                      file.size /
                      1024 /
                      1024
                    ).toFixed(2)} MB`
                  : "Click to browse • Maximum 50MB"}
              </p>

            </div>

            {file && (
              <button
                onClick={(event) => {
                  event.stopPropagation();

                  uploadDocument();
                }}
                disabled={uploading}
                className="button-animation mt-4 flex w-full items-center justify-center gap-2 rounded-xl bg-gray-900 px-5 py-3.5 text-sm font-medium text-white hover:bg-gray-800 disabled:opacity-50"
              >

                {uploading ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />

                    Processing document...
                  </>
                ) : (
                  <>
                    <FileText className="h-4 w-4" />

                    Analyze Document
                  </>
                )}

              </button>
            )}

            {status && (
              <div className="mt-5 rounded-lg bg-gray-100 px-4 py-3 text-center text-sm text-gray-600">
                {status}
              </div>
            )}

          </section>

        </main>
      )}

      {/* ======================================================
          CHAT APPLICATION
      ====================================================== */}

      {docId && (
        <div className="flex min-h-0 flex-1 overflow-hidden">

          {/* ==================================================
              LEFT CHAT HISTORY
          ================================================== */}

          <aside
            className={`hidden w-72 flex-shrink-0 border-r border-gray-200 bg-white lg:flex lg:flex-col ${
              showHistory
                ? ""
                : "lg:hidden"
            }`}
          >

            <div className="flex items-center justify-between border-b border-gray-100 px-4 py-4">

              <div className="flex items-center gap-2">

                <MessageSquare className="h-4 w-4 text-gray-500" />

                <span className="text-sm font-semibold">
                  Conversation
                </span>

              </div>

              <span className="text-xs text-gray-400">
                {conversationMessages.length}
              </span>

            </div>

            <div className="flex-1 overflow-y-auto px-3 py-3">

              {conversationMessages.length ===
              0 ? (
                <div className="px-3 py-8 text-center">

                  <MessageSquare className="mx-auto h-6 w-6 text-gray-300" />

                  <p className="mt-3 text-xs text-gray-400">
                    Your conversation
                    will appear here.
                  </p>

                </div>
              ) : (
                <div className="space-y-1">

                  {conversationMessages.map(
                    (
                      item,
                      index
                    ) => {

                      const isUser =
                        item.role ===
                        "user";

                      return (
                        <div
                          key={`${index}-${item.timestamp || ""}`}
                          className={`history-item rounded-lg px-3 py-3 ${
                            isUser
                              ? "hover:bg-gray-50"
                              : "bg-gray-50"
                          }`}
                        >

                          <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-gray-400">
                            {isUser
                              ? "You"
                              : "AI"}
                          </p>

                          <p className="line-clamp-3 text-xs leading-5 text-gray-600">
                            {item.message}
                          </p>

                        </div>
                      );
                    }
                  )}

                </div>
              )}

            </div>

          </aside>

          {/* ==================================================
              MAIN CHAT
          ================================================== */}

          <main className="relative flex min-w-0 flex-1 flex-col overflow-hidden">

            {/* DOCUMENT BAR */}

            <div className="flex flex-shrink-0 items-center justify-between border-b border-gray-200 bg-white px-5 py-3">

              <div className="flex min-w-0 items-center gap-3">

                <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg bg-gray-100">
                  <FileText className="h-4 w-4 text-gray-600" />
                </div>

                <div className="min-w-0">

                  <p className="truncate text-sm font-medium text-gray-900">
                    {file?.name ||
                      "Document"}
                  </p>

                  <p className="text-xs text-green-600">
                    Document ready
                  </p>

                </div>

              </div>

              <button
                onClick={() =>
                  setShowHistory(
                    !showHistory
                  )
                }
                className="button-animation rounded-lg p-2 text-gray-400 hover:bg-gray-100 hover:text-gray-700 lg:hidden"
              >
                {showHistory ? (
                  <ChevronUp className="h-4 w-4" />
                ) : (
                  <ChevronDown className="h-4 w-4" />
                )}
              </button>

            </div>

            {/* =================================================
                CHAT SCROLL AREA
            ================================================= */}

            <div
              ref={chatContainerRef}
              className="chat-scroll flex-1 overflow-y-auto"
            >

              <div className="mx-auto w-full max-w-3xl px-5 py-8">

                {/* EMPTY STATE */}

                {conversationMessages.length ===
                  0 &&
                  !asking && (
                    <div className="empty-chat-animation flex min-h-[50vh] items-center justify-center">

                      <div className="text-center">

                        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-gray-100">
                          <MessageSquare className="h-5 w-5 text-gray-500" />
                        </div>

                        <h2 className="mt-4 text-lg font-semibold text-gray-900">
                          Ask about your document
                        </h2>

                        <p className="mx-auto mt-2 max-w-sm text-sm leading-6 text-gray-500">
                          Ask a question about
                          anything inside your
                          uploaded PDF.
                        </p>

                      </div>

                    </div>
                  )}

                {/* =================================================
                    MESSAGES
                ================================================= */}

                <div className="space-y-8">

                  {conversationMessages.map(
                    (
                      item,
                      index
                    ) => {

                      const isUser =
                        item.role ===
                        "user";

                      return (
                        <div
                          key={`${index}-${item.timestamp || ""}`}
                          className={
                            isUser
                              ? "message-user"
                              : "message-ai"
                          }
                        >

                          {isUser ? (
                            <div className="flex justify-end">

                              <div className="max-w-[80%] rounded-2xl rounded-br-md bg-gray-900 px-4 py-3 text-sm leading-6 text-white shadow-sm">
                                {item.message}
                              </div>

                            </div>
                          ) : (
                            <div className="flex gap-3">

                              <div className="mt-1 flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-lg bg-gray-900">
                                <FileText className="h-3.5 w-3.5 text-white" />
                              </div>

                              <div className="min-w-0 flex-1">

                                <div className="mb-1 flex items-center justify-between">

                                  <span className="text-xs font-semibold text-gray-900">
                                    Document AI
                                  </span>

                                  {index ===
                                    conversationMessages.length -
                                      1 &&
                                    formattedAnswer && (
                                      <button
                                        onClick={
                                          copyAnswer
                                        }
                                        className="button-animation rounded-lg p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-700"
                                      >
                                        {copied ? (
                                          <Check className="h-3.5 w-3.5 text-green-600" />
                                        ) : (
                                          <Copy className="h-3.5 w-3.5" />
                                        )}
                                      </button>
                                    )}

                                </div>

                                <FormattedAnswer
                                  text={
                                    item.message
                                  }
                                  className="break-words text-sm leading-7 text-gray-700"
                                />

                              </div>

                            </div>
                          )}

                        </div>
                      );
                    }
                  )}

                  {/* =================================================
                      THINKING
                  ================================================= */}

                  {asking && (
                    <div className="message-ai flex gap-3">

                      <div className="mt-1 flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-lg bg-gray-900">
                        <FileText className="h-3.5 w-3.5 text-white" />
                      </div>

                      <div className="flex items-center gap-3">

                        <span className="text-xs font-semibold text-gray-900">
                          Document AI
                        </span>

                        <ThinkingIndicator />

                      </div>

                    </div>
                  )}

                  {/* =================================================
                      LATEST ANSWER EXTRA DETAILS
                  ================================================= */}

                  {!asking &&
                    formattedAnswer && (
                      <div className="latest-answer-animation ml-10">

                        {(respModel ||
                          respConfidence !==
                            null) && (
                          <div className="mb-4 flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-400">

                            {respModel && (
                              <span>
                                Model:{" "}
                                {respModel}
                              </span>
                            )}

                            {respConfidence !==
                              null && (
                              <span>
                                Confidence:{" "}
                                {(
                                  respConfidence *
                                  100
                                ).toFixed(
                                  0
                                )}
                                %
                              </span>
                            )}

                          </div>
                        )}

                        {/* STRUCTURED DATA */}

                        {structuredData &&
                          Object.keys(
                            structuredData
                          ).length >
                            0 && (
                            <div className="mb-6 rounded-xl border border-gray-200 bg-white p-4">

                              <p className="mb-3 text-sm font-semibold text-gray-900">
                                Extracted data
                              </p>

                              <div className="grid gap-3 sm:grid-cols-2">

                                {[
                                  [
                                    "Emails",
                                    structuredData.emails,
                                  ],
                                  [
                                    "Phones",
                                    structuredData.phones,
                                  ],
                                  [
                                    "URLs",
                                    structuredData.urls,
                                  ],
                                  [
                                    "Dates",
                                    structuredData.dates,
                                  ],
                                  [
                                    "Numbers",
                                    structuredData.numbers,
                                  ],
                                ].map(
                                  (
                                    [
                                      label,
                                      values,
                                    ],
                                    i
                                  ) =>
                                    Array.isArray(
                                      values
                                    ) &&
                                    values.length >
                                      0 && (
                                      <div
                                        key={
                                          label
                                        }
                                        className={`structured-card rounded-lg bg-gray-50 px-3 py-3 ${
                                          label ===
                                          "Numbers"
                                            ? "sm:col-span-2"
                                            : ""
                                        }`}
                                      >

                                        <div className="text-xs font-medium text-gray-600">
                                          {
                                            label
                                          }
                                        </div>

                                        <div className="mt-1 break-words text-sm text-gray-700">
                                          {values.join(
                                            ", "
                                          )}
                                        </div>

                                      </div>
                                    )
                                )}

                              </div>

                            </div>
                          )}

                        {/* SUGGESTIONS */}

                        {suggestedQuestions.length >
                          0 && (
                          <div className="border-t border-gray-200 pt-5">

                            <p className="mb-3 text-sm font-semibold text-gray-900">
                              Try these
                            </p>

                            <div className="flex flex-wrap gap-2">

                              {suggestedQuestions.map(
                                (
                                  suggestion,
                                  index
                                ) => (
                                  <button
                                    key={
                                      index
                                    }
                                    onClick={() =>
                                      handleSuggestionClick(
                                        suggestion
                                      )
                                    }
                                    disabled={
                                      asking
                                    }
                                    style={{
                                      animationDelay: `${
                                        index *
                                        80
                                      }ms`,
                                    }}
                                    className="suggestion-animation button-animation rounded-full border border-gray-200 bg-white px-3 py-1.5 text-xs text-gray-700 hover:bg-gray-100 disabled:opacity-50"
                                  >
                                    {
                                      suggestion
                                    }
                                  </button>
                                )
                              )}

                            </div>

                          </div>
                        )}

                      </div>
                    )}

                </div>

              </div>

            </div>

            {/* =================================================
                STATUS
            ================================================= */}

            {status && (
              <div className="absolute bottom-24 left-1/2 z-20 w-[calc(100%-2rem)] max-w-2xl -translate-x-1/2 rounded-lg border border-gray-200 bg-white px-4 py-3 text-center text-xs text-gray-600 shadow-lg">
                {status}
              </div>
            )}

            {/* =================================================
                INPUT AREA
            ================================================= */}

            <div className="flex-shrink-0 border-t border-gray-200 bg-white px-4 py-4">

              <div className="mx-auto w-full max-w-3xl">

                <div className="question-box rounded-2xl border border-gray-300 bg-white p-3 shadow-sm transition-all duration-200 focus-within:border-gray-400 focus-within:shadow-md">

                  <textarea
                    ref={
                      questionInputRef
                    }
                    value={question}
                    onChange={(event) =>
                      setQuestion(
                        event.target
                          .value
                      )
                    }
                    onKeyDown={
                      handleKeyDown
                    }
                    placeholder="Ask anything about this document..."
                    rows={2}
                    disabled={asking}
                    className="w-full resize-none border-0 bg-transparent px-2 py-1 text-sm leading-6 text-gray-800 outline-none placeholder:text-gray-400 disabled:opacity-50"
                  />

                  <div className="mt-2 flex items-center justify-between">

                    <span className="hidden text-xs text-gray-400 sm:block">
                      Enter to ask • Shift +
                      Enter for new line
                    </span>

                    <button
                      onClick={
                        askQuestion
                      }
                      disabled={
                        asking ||
                        !question.trim()
                      }
                      className="button-animation ml-auto flex items-center gap-2 rounded-xl bg-gray-900 px-4 py-2.5 text-sm font-medium text-white hover:bg-gray-800 disabled:cursor-not-allowed disabled:opacity-40"
                    >

                      {asking ? (
                        <>
                          <Loader2 className="h-4 w-4 animate-spin" />
                          Thinking...
                        </>
                      ) : (
                        <>
                          <Send className="h-4 w-4" />
                          Ask
                        </>
                      )}

                    </button>

                  </div>

                </div>

                <p className="mt-2 text-center text-[10px] text-gray-400">
                  Answers are generated
                  from the uploaded
                  document.
                </p>

              </div>

            </div>

          </main>

        </div>
      )}

      {/* ======================================================
          FOOTER ONLY FOR UPLOAD SCREEN
      ====================================================== */}

      {!docId && (
        <footer className="flex-shrink-0 border-t border-gray-200 bg-white">

          <div className="mx-auto max-w-4xl px-5 py-5 text-center">

            <p className="text-xs text-gray-400">
              Document AI
            </p>

            <p className="mt-1 text-xs text-gray-400">
              Answers are generated from
              the uploaded document.
            </p>

          </div>

        </footer>
      )}

    </div>
  );
}
 
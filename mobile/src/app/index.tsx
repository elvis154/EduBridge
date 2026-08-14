import React, { useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  FlatList,
  Keyboard,
  KeyboardAvoidingView,
  Platform,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import * as DocumentPicker from "expo-document-picker";
import axios from "axios";

const API_URL = "https://edubridge-production-06b1.up.railway.app";

console.log("EduBridge API:", API_URL);

type HistoryItem = {
  timestamp?: string;
  role: string;
  message: string;
  temporary?: boolean;
};

type StructuredData = {
  emails?: string[];
  phones?: string[];
  urls?: string[];
  dates?: string[];
  numbers?: string[];
};

type UploadResponse = {
  doc_id: string;
  filename: string;
  text_excerpt?: string;
  word_count?: number;
  character_count?: number;
};

type AskResponse = {
  answer?: string;
  formatted_answer?: string;
  model?: string;
  confidence?: number | null;
  processing_time_ms?: number | null;
  suggested_questions?: string[];
  history?: HistoryItem[];
  structured_data?: StructuredData;
  fallback_from?: string | null;
  citations?: any[];
};

function safeString(value: any): string {
  if (value === null || value === undefined) {
    return "";
  }

  if (typeof value === "string") {
    return value;
  }

  if (
    typeof value === "number" ||
    typeof value === "boolean" ||
    typeof value === "bigint"
  ) {
    return String(value);
  }

  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function getErrorMessage(error: any): string {
  if (!error) {
    return "Something went wrong.";
  }

  if (typeof error === "string") {
    return error;
  }

  if (error?.code === "ECONNABORTED") {
    return "Connection timed out. Please try again.";
  }

  if (
    error?.code === "ERR_NETWORK" ||
    error?.message === "Network Error"
  ) {
    return `Cannot reach the backend.

Backend:
${API_URL}

Please check your internet connection and try again.`;
  }

  const responseData = error?.response?.data;

  if (responseData) {
    if (typeof responseData === "string") {
      return responseData;
    }

    if (typeof responseData.detail === "string") {
      return responseData.detail;
    }

    if (Array.isArray(responseData.detail)) {
      return responseData.detail
        .map((item: any) => {
          if (typeof item === "string") {
            return item;
          }

          if (item?.msg) {
            return safeString(item.msg);
          }

          return safeString(item);
        })
        .join("\n");
    }

    if (
      responseData.detail &&
      typeof responseData.detail === "object"
    ) {
      if (responseData.detail.msg) {
        return safeString(responseData.detail.msg);
      }

      return safeString(responseData.detail);
    }

    if (responseData.message) {
      return safeString(responseData.message);
    }

    return safeString(responseData);
  }

  if (error?.message) {
    return safeString(error.message);
  }

  return "Something went wrong.";
}

function renderSimpleMarkdown(text: string) {
  if (!text) {
    return null;
  }

  const lines = safeString(text)
    .replace(/\r\n/g, "\n")
    .split("\n");

  return lines.map((line, index) => {
    const trimmed = line.trim();

    if (!trimmed) {
      return <View key={`empty-${index}`} style={styles.emptyLine} />;
    }

    if (trimmed.startsWith("### ")) {
      return (
        <Text key={`h3-${index}`} style={styles.heading3}>
          {trimmed.substring(4)}
        </Text>
      );
    }

    if (trimmed.startsWith("## ")) {
      return (
        <Text key={`h2-${index}`} style={styles.heading2}>
          {trimmed.substring(3)}
        </Text>
      );
    }

    if (trimmed.startsWith("# ")) {
      return (
        <Text key={`h1-${index}`} style={styles.heading1}>
          {trimmed.substring(2)}
        </Text>
      );
    }

    if (trimmed.startsWith("- ") || trimmed.startsWith("* ")) {
      return (
        <View key={`bullet-${index}`} style={styles.bulletRow}>
          <Text style={styles.bullet}>•</Text>

          <Text style={styles.answerText}>
            {trimmed.substring(2)}
          </Text>
        </View>
      );
    }

    const orderedMatch = trimmed.match(/^\d+[.)]\s+(.+)$/);

    if (orderedMatch) {
      const numberMatch = trimmed.match(/^\d+/);

      return (
        <View key={`ordered-${index}`} style={styles.bulletRow}>
          <Text style={styles.numberBullet}>
            {numberMatch?.[0] || "1"}.
          </Text>

          <Text style={styles.answerText}>
            {orderedMatch[1]}
          </Text>
        </View>
      );
    }

    return (
      <Text key={`text-${index}`} style={styles.answerText}>
        {trimmed}
      </Text>
    );
  });
}

export default function HomeScreen() {
  const [file, setFile] =
    useState<DocumentPicker.DocumentPickerAsset | null>(null);

  const [docId, setDocId] = useState("");
  const [question, setQuestion] = useState("");
  const [history, setHistory] = useState<HistoryItem[]>([]);

  const [uploading, setUploading] = useState(false);
  const [asking, setAsking] = useState(false);
  const [status, setStatus] = useState("");

  const [structuredData, setStructuredData] =
    useState<StructuredData>({});

  const [suggestedQuestions, setSuggestedQuestions] =
    useState<string[]>([]);

  const [model, setModel] = useState("");
  const [confidence, setConfidence] =
    useState<number | null>(null);

  const [backendStatus, setBackendStatus] = useState<
    "checking" | "online" | "offline"
  >("checking");

  const flatListRef = useRef<FlatList>(null);

  useEffect(() => {
    checkBackend();
  }, []);

  useEffect(() => {
    if (history.length > 0 && flatListRef.current) {
      setTimeout(() => {
        flatListRef.current?.scrollToEnd({
          animated: true,
        });
      }, 150);
    }
  }, [history, asking]);

  const checkBackend = async () => {
    setBackendStatus("checking");

    try {
      const response = await axios.get(`${API_URL}/health`, {
        timeout: 15000,
      });

      console.log("Backend response:", response.data);

      setBackendStatus("online");
      setStatus("");
    } catch (error) {
      console.error("Backend unavailable:", error);

      setBackendStatus("offline");

      setStatus(
        `Backend unavailable.

Server:
${API_URL}

Please check your internet connection.`
      );
    }
  };

  const pickPDF = async () => {
    if (uploading) {
      return;
    }

    try {
      const result = await DocumentPicker.getDocumentAsync({
        type: "application/pdf",
        copyToCacheDirectory: true,
        multiple: false,
      });

      if (result.canceled) {
        return;
      }

      const selected = result.assets?.[0];

      if (!selected) {
        return;
      }

      const filename = selected.name || "";

      if (!filename.toLowerCase().endsWith(".pdf")) {
        Alert.alert(
          "Invalid file",
          "Please select a PDF file."
        );
        return;
      }

      if (
        selected.size &&
        selected.size > 50 * 1024 * 1024
      ) {
        Alert.alert(
          "File too large",
          "Maximum file size is 50MB."
        );
        return;
      }

      setFile(selected);
      setStatus("");
    } catch (error) {
      console.error("Document picker error:", error);

      setStatus("Unable to select the document.");
    }
  };

  const uploadDocument = async () => {
    if (!file) {
      Alert.alert(
        "Select a document",
        "Please select a PDF first."
      );
      return;
    }

    if (backendStatus !== "online") {
      Alert.alert(
        "Backend unavailable",
        "Please wait until the backend is connected."
      );
      return;
    }

    setUploading(true);
    setStatus("Uploading and analyzing document...");

    try {
      const formData = new FormData();

      if (
        Platform.OS === "web" &&
        (file as any).file
      ) {
        formData.append(
          "file",
          (file as any).file,
          file.name || "document.pdf"
        );
      } else {
        formData.append(
          "file",
          {
            uri: file.uri,
            name: file.name || "document.pdf",
            type: file.mimeType || "application/pdf",
          } as any
        );
      }

      const response =
        await axios.post<UploadResponse>(
          `${API_URL}/upload`,
          formData,
          {
            timeout: 180000,
          }
        );

      const data = response.data;

      setDocId(safeString(data.doc_id));
      setHistory([]);
      setQuestion("");
      setStructuredData({});
      setSuggestedQuestions([]);
      setModel("");
      setConfidence(null);

      setStatus(
        `Document ready • ${(
          data.word_count || 0
        ).toLocaleString()} words`
      );
    } catch (error: any) {
      console.error("Upload error:", error);

      const message = getErrorMessage(error);

      setStatus(message);

      Alert.alert("Upload failed", message);
    } finally {
      setUploading(false);
    }
  };

  const askQuestion = async (
    overrideQuestion?: string
  ) => {
    if (!docId) {
      Alert.alert(
        "No document",
        "Please upload a PDF first."
      );
      return;
    }

    if (backendStatus !== "online") {
      Alert.alert(
        "Backend unavailable",
        "Please check your connection."
      );
      return;
    }

    const q =
      overrideQuestion?.trim() ||
      question.trim();

    if (!q) {
      return;
    }

    if (q.length > 2000) {
      Alert.alert(
        "Question too long",
        "Please keep your question under 2000 characters."
      );
      return;
    }

    if (asking) {
      return;
    }

    setAsking(true);
    setQuestion("");
    setStatus("");

    Keyboard.dismiss();

    const temporaryMessage: HistoryItem = {
      role: "user",
      message: q,
      timestamp: new Date().toISOString(),
      temporary: true,
    };

    setHistory((previous) => [
      ...previous,
      temporaryMessage,
    ]);

    try {
      const response =
        await axios.post<AskResponse>(
          `${API_URL}/ask`,
          {
            doc_id: docId,
            question: q,
            use_cache: true,
          },
          {
            timeout: 180000,
            headers: {
              "Content-Type": "application/json",
            },
          }
        );

      const data = response.data;

      setModel(safeString(data.model));

      setConfidence(
        typeof data.confidence === "number"
          ? data.confidence
          : null
      );

      setStructuredData(
        data.structured_data &&
          typeof data.structured_data === "object"
          ? data.structured_data
          : {}
      );

      setSuggestedQuestions(
        Array.isArray(data.suggested_questions)
          ? data.suggested_questions.map((item) =>
              safeString(item)
            )
          : []
      );

      if (Array.isArray(data.history)) {
        const safeHistory = data.history.map(
          (item: any) => ({
            timestamp: safeString(
              item?.timestamp
            ),
            role: safeString(item?.role),
            message: safeString(item?.message),
          })
        );

        setHistory(safeHistory);
      } else {
        const answer =
          data.formatted_answer ||
          data.answer ||
          "I couldn't find an answer.";

        setHistory((previous) => [
          ...previous.filter(
            (item) => !item.temporary
          ),
          {
            role: "assistant",
            message: safeString(answer),
            timestamp: new Date().toISOString(),
          },
        ]);
      }
    } catch (error: any) {
      console.error("Question error:", error);

      const message = getErrorMessage(error);

      setStatus(message);

      setHistory((previous) =>
        previous.filter(
          (item) => !item.temporary
        )
      );

      Alert.alert(
        "Question failed",
        message
      );
    } finally {
      setAsking(false);
    }
  };

  const handleSuggestion = (
    suggestion: string
  ) => {
    if (!suggestion || asking) {
      return;
    }

    askQuestion(safeString(suggestion));
  };

  const copyText = async (text: string) => {
    const value = safeString(text);

    try {
      if (
        Platform.OS === "web" &&
        typeof navigator !== "undefined" &&
        navigator.clipboard
      ) {
        await navigator.clipboard.writeText(value);

        Alert.alert(
          "Copied",
          "Answer copied to clipboard."
        );

        return;
      }

      Alert.alert(
        "Copy",
        "Copy is available in the web version."
      );
    } catch (error) {
      console.error("Copy failed:", error);

      Alert.alert(
        "Copy failed",
        "Could not copy the answer."
      );
    }
  };

  const resetApplication = () => {
    setFile(null);
    setDocId("");
    setQuestion("");
    setHistory([]);
    setUploading(false);
    setAsking(false);
    setStatus("");
    setStructuredData({});
    setSuggestedQuestions([]);
    setModel("");
    setConfidence(null);
  };

  const deleteDocument = () => {
    if (!docId) {
      return;
    }

    Alert.alert(
      "Delete document?",
      "This will delete the document and conversation.",
      [
        {
          text: "Cancel",
          style: "cancel",
        },
        {
          text: "Delete",
          style: "destructive",
          onPress: async () => {
            try {
              await axios.delete(
                `${API_URL}/docs/${docId}`,
                {
                  timeout: 30000,
                }
              );

              resetApplication();
            } catch (error: any) {
              console.error(
                "Delete error:",
                error
              );

              Alert.alert(
                "Delete failed",
                getErrorMessage(error)
              );
            }
          },
        },
      ]
    );
  };

  const conversation = history.filter(
    (item) =>
      item.role === "user" ||
      item.role === "assistant"
  );

  if (!docId) {
    return (
      <SafeAreaView style={styles.safeArea}>
        <ScrollView
          contentContainerStyle={
            styles.uploadContainer
          }
          keyboardShouldPersistTaps="handled"
        >
          <View style={styles.logo}>
            <Text style={styles.logoText}>
              PDF
            </Text>
          </View>

          <Text style={styles.title}>
            Ask your document anything.
          </Text>

          <Text style={styles.subtitle}>
            Upload a PDF and ask questions
            about its contents.
          </Text>

          <View
            style={
              styles.backendStatusContainer
            }
          >
            <View
              style={[
                styles.backendStatusDot,
                backendStatus ===
                  "online" &&
                  styles.statusOnline,
                backendStatus ===
                  "offline" &&
                  styles.statusOffline,
                backendStatus ===
                  "checking" &&
                  styles.statusChecking,
              ]}
            />

            <Text
              style={
                styles.backendStatusText
              }
            >
              {backendStatus ===
                "online" &&
                "Backend connected"}

              {backendStatus ===
                "offline" &&
                "Backend offline"}

              {backendStatus ===
                "checking" &&
                "Checking backend..."}
            </Text>

            {backendStatus ===
              "offline" && (
              <TouchableOpacity
                onPress={
                  checkBackend
                }
                style={
                  styles.retryButton
                }
              >
                <Text
                  style={
                    styles.retryButtonText
                  }
                >
                  Retry
                </Text>
              </TouchableOpacity>
            )}
          </View>

          <TouchableOpacity
            activeOpacity={0.8}
            onPress={pickPDF}
            disabled={uploading}
            style={[
              styles.uploadBox,
              uploading &&
                styles.disabled,
            ]}
          >
            <View
              style={
                styles.uploadIcon
              }
            >
              <Text
                style={
                  styles.uploadIconText
                }
              >
                ↑
              </Text>
            </View>

            <Text
              style={
                styles.uploadTitle
              }
            >
              {file
                ? safeString(file.name)
                : "Select a PDF document"}
            </Text>

            <Text
              style={
                styles.uploadSubtitle
              }
            >
              {file
                ? `${(
                    (file.size || 0) /
                    1024 /
                    1024
                  ).toFixed(2)} MB`
                : "PDF files up to 50MB"}
            </Text>
          </TouchableOpacity>

          {file && (
            <TouchableOpacity
              activeOpacity={0.8}
              onPress={
                uploadDocument
              }
              disabled={
                uploading ||
                backendStatus !==
                  "online"
              }
              style={[
                styles.primaryButton,
                (uploading ||
                  backendStatus !==
                    "online") &&
                  styles.disabled,
              ]}
            >
              {uploading ? (
                <ActivityIndicator
                  color="#ffffff"
                />
              ) : (
                <Text
                  style={
                    styles.primaryButtonText
                  }
                >
                  Analyze Document
                </Text>
              )}
            </TouchableOpacity>
          )}

          {status ? (
            <View
              style={
                styles.statusBox
              }
            >
              <Text
                style={
                  styles.statusText
                }
              >
                {safeString(status)}
              </Text>
            </View>
          ) : null}

          <View style={styles.footer}>
            <Text
              style={
                styles.footerText
              }
            >
              EduBridge AI
            </Text>

            <Text
              style={
                styles.footerSubtext
              }
            >
              Answers are generated
              from your uploaded
              document.
            </Text>
          </View>
        </ScrollView>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safeArea}>
      <KeyboardAvoidingView
        style={styles.container}
        behavior={
          Platform.OS === "ios"
            ? "padding"
            : undefined
        }
        keyboardVerticalOffset={
          Platform.OS === "ios"
            ? 90
            : 0
        }
      >
        <View style={styles.header}>
          <View
            style={styles.headerLeft}
          >
            <View
              style={
                styles.smallLogo
              }
            >
              <Text
                style={
                  styles.smallLogoText
                }
              >
                PDF
              </Text>
            </View>

            <View
              style={
                styles.headerTextContainer
              }
            >
              <Text
                numberOfLines={1}
                style={
                  styles.headerTitle
                }
              >
                {file?.name ||
                  "Document"}
              </Text>

              <Text
                style={
                  styles.headerStatus
                }
              >
                Document ready
              </Text>
            </View>
          </View>

          <View
            style={
              styles.headerActions
            }
          >
            <TouchableOpacity
              onPress={
                resetApplication
              }
              style={
                styles.iconButton
              }
            >
              <Text
                style={
                  styles.iconText
                }
              >
                ×
              </Text>
            </TouchableOpacity>

            <TouchableOpacity
              onPress={
                deleteDocument
              }
              style={
                styles.iconButton
              }
            >
              <Text
                style={
                  styles.deleteIcon
                }
              >
                🗑
              </Text>
            </TouchableOpacity>
          </View>
        </View>

        <FlatList
          ref={flatListRef}
          data={conversation}
          keyExtractor={(item, index) =>
            `${index}-${safeString(
              item.timestamp
            )}`
          }
          contentContainerStyle={
            styles.chatContent
          }
          keyboardShouldPersistTaps="handled"
          ListEmptyComponent={
            !asking ? (
              <View
                style={
                  styles.emptyChat
                }
              >
                <Text
                  style={
                    styles.emptyIcon
                  }
                >
                  ?
                </Text>

                <Text
                  style={
                    styles.emptyTitle
                  }
                >
                  Ask about your
                  document
                </Text>

                <Text
                  style={
                    styles.emptySubtitle
                  }
                >
                  Ask anything about
                  the uploaded PDF.
                </Text>
              </View>
            ) : null
          }
          renderItem={({
            item,
          }) => {
            const isUser =
              item.role === "user";

            const message =
              safeString(item.message);

            return (
              <View
                style={
                  isUser
                    ? styles.userMessageContainer
                    : styles.aiMessageContainer
                }
              >
                {isUser ? (
                  <View
                    style={
                      styles.userBubble
                    }
                  >
                    <Text
                      style={
                        styles.userText
                      }
                    >
                      {message}
                    </Text>
                  </View>
                ) : (
                  <View
                    style={
                      styles.aiRow
                    }
                  >
                    <View
                      style={
                        styles.aiIcon
                      }
                    >
                      <Text
                        style={
                          styles.aiIconText
                        }
                      >
                        AI
                      </Text>
                    </View>

                    <View
                      style={
                        styles.aiContent
                      }
                    >
                      <View
                        style={
                          styles.aiHeader
                        }
                      >
                        <Text
                          style={
                            styles.aiName
                          }
                        >
                          Document AI
                        </Text>

                        <TouchableOpacity
                          onPress={() =>
                            copyText(
                              message
                            )
                          }
                        >
                          <Text
                            style={
                              styles.copyText
                            }
                          >
                            Copy
                          </Text>
                        </TouchableOpacity>
                      </View>

                      {renderSimpleMarkdown(
                        message
                      )}
                    </View>
                  </View>
                )}
              </View>
            );
          }}
          ListFooterComponent={
            <View>
              {asking && (
                <View
                  style={
                    styles.aiRow
                  }
                >
                  <View
                    style={
                      styles.aiIcon
                    }
                  >
                    <Text
                      style={
                        styles.aiIconText
                      }
                    >
                      AI
                    </Text>
                  </View>

                  <View
                    style={
                      styles.thinkingContainer
                    }
                  >
                    <Text
                      style={
                        styles.aiName
                      }
                    >
                      Document AI
                    </Text>

                    <ActivityIndicator
                      size="small"
                      color="#111111"
                      style={{
                        marginTop: 8,
                      }}
                    />

                    <Text
                      style={
                        styles.thinkingText
                      }
                    >
                      Thinking...
                    </Text>
                  </View>
                </View>
              )}

              {!asking &&
                (model ||
                  confidence !== null) && (
                  <View
                    style={
                      styles.metadata
                    }
                  >
                    {model ? (
                      <Text
                        style={
                          styles.metadataText
                        }
                      >
                        Model:{" "}
                        {safeString(model)}
                      </Text>
                    ) : null}

                    {confidence !==
                      null && (
                      <Text
                        style={
                          styles.metadataText
                        }
                      >
                        Confidence:{" "}
                        {(
                          confidence * 100
                        ).toFixed(0)}
                        %
                      </Text>
                    )}
                  </View>
                )}

              {structuredData &&
                Object.keys(
                  structuredData
                ).length > 0 && (
                  <View
                    style={
                      styles.structuredBox
                    }
                  >
                    <Text
                      style={
                        styles.structuredTitle
                      }
                    >
                      Extracted data
                    </Text>

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
                      ([label, values]) => {
                        if (
                          !Array.isArray(
                            values
                          ) ||
                          values.length === 0
                        ) {
                          return null;
                        }

                        return (
                          <View
                            key={safeString(
                              label
                            )}
                            style={
                              styles.dataRow
                            }
                          >
                            <Text
                              style={
                                styles.dataLabel
                              }
                            >
                              {safeString(
                                label
                              )}
                            </Text>

                            <Text
                              style={
                                styles.dataValue
                              }
                            >
                              {values
                                .map(
                                  (
                                    value
                                  ) =>
                                    safeString(
                                      value
                                    )
                                )
                                .join(", ")}
                            </Text>
                          </View>
                        );
                      }
                    )}
                  </View>
                )}

              {suggestedQuestions.length >
                0 && (
                <View
                  style={
                    styles.suggestions
                  }
                >
                  <Text
                    style={
                      styles.suggestionsTitle
                    }
                  >
                    Try these
                  </Text>

                  <ScrollView
                    horizontal
                    showsHorizontalScrollIndicator={
                      false
                    }
                  >
                    {suggestedQuestions.map(
                      (
                        suggestion,
                        index
                      ) => (
                        <TouchableOpacity
                          key={`${index}-${suggestion}`}
                          onPress={() =>
                            handleSuggestion(
                              suggestion
                            )
                          }
                          disabled={asking}
                          style={
                            styles.suggestion
                          }
                        >
                          <Text
                            style={
                              styles.suggestionText
                            }
                          >
                            {safeString(
                              suggestion
                            )}
                          </Text>
                        </TouchableOpacity>
                      )
                    )}
                  </ScrollView>
                </View>
              )}
            </View>
          }
        />

        {status ? (
          <View
            style={
              styles.chatStatus
            }
          >
            <Text
              style={
                styles.chatStatusText
              }
            >
              {safeString(status)}
            </Text>
          </View>
        ) : null}

        <View
          style={
            styles.inputArea
          }
        >
          <View
            style={
              styles.inputBox
            }
          >
            <TextInput
              value={question}
              onChangeText={
                setQuestion
              }
              placeholder="Ask anything about this document..."
              placeholderTextColor="#999999"
              multiline
              editable={
                !asking &&
                backendStatus ===
                  "online"
              }
              style={
                styles.textInput
              }
              maxLength={2000}
              returnKeyType="send"
              onSubmitEditing={() =>
                askQuestion()
              }
            />

            <TouchableOpacity
              onPress={() =>
                askQuestion()
              }
              disabled={
                asking ||
                !question.trim() ||
                backendStatus !==
                  "online"
              }
              style={[
                styles.sendButton,
                (asking ||
                  !question.trim() ||
                  backendStatus !==
                    "online") &&
                  styles.sendDisabled,
              ]}
            >
              {asking ? (
                <ActivityIndicator
                  size="small"
                  color="#ffffff"
                />
              ) : (
                <Text
                  style={
                    styles.sendIcon
                  }
                >
                  ↑
                </Text>
              )}
            </TouchableOpacity>
          </View>

          <Text
            style={
              styles.inputHint
            }
          >
            Answers are generated
            from the uploaded document.
          </Text>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: "#f8f8f8",
  },

  container: {
    flex: 1,
    backgroundColor: "#f8f8f8",
  },

  uploadContainer: {
    flexGrow: 1,
    justifyContent: "center",
    paddingHorizontal: 24,
    paddingVertical: 40,
  },

  logo: {
    width: 58,
    height: 58,
    borderRadius: 16,
    backgroundColor: "#111111",
    alignItems: "center",
    justifyContent: "center",
    alignSelf: "center",
    marginBottom: 24,
  },

  logoText: {
    color: "#ffffff",
    fontSize: 15,
    fontWeight: "800",
  },

  title: {
    fontSize: 30,
    fontWeight: "700",
    color: "#111111",
    textAlign: "center",
  },

  subtitle: {
    fontSize: 15,
    lineHeight: 23,
    color: "#777777",
    textAlign: "center",
    marginTop: 10,
    marginBottom: 32,
  },

  backendStatusContainer: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 20,
    padding: 10,
    backgroundColor: "#f0f0f0",
    borderRadius: 10,
  },

  backendStatusDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    marginRight: 8,
  },

  statusOnline: {
    backgroundColor: "#16a34a",
  },

  statusOffline: {
    backgroundColor: "#dc2626",
  },

  statusChecking: {
    backgroundColor: "#f59e0b",
  },

  backendStatusText: {
    fontSize: 12,
    color: "#555555",
    flex: 1,
  },

  retryButton: {
    paddingHorizontal: 12,
    paddingVertical: 5,
    backgroundColor: "#111111",
    borderRadius: 6,
  },

  retryButtonText: {
    color: "#ffffff",
    fontSize: 11,
    fontWeight: "600",
  },

  uploadBox: {
    borderWidth: 2,
    borderStyle: "dashed",
    borderColor: "#d0d0d0",
    borderRadius: 18,
    backgroundColor: "#ffffff",
    paddingVertical: 45,
    paddingHorizontal: 20,
    alignItems: "center",
  },

  uploadIcon: {
    width: 60,
    height: 60,
    borderRadius: 16,
    backgroundColor: "#f0f0f0",
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 18,
  },

  uploadIconText: {
    fontSize: 30,
    color: "#555555",
    fontWeight: "700",
  },

  uploadTitle: {
    fontSize: 16,
    fontWeight: "600",
    color: "#222222",
    textAlign: "center",
  },

  uploadSubtitle: {
    fontSize: 13,
    color: "#888888",
    marginTop: 8,
  },

  primaryButton: {
    height: 52,
    borderRadius: 14,
    backgroundColor: "#111111",
    marginTop: 16,
    alignItems: "center",
    justifyContent: "center",
    flexDirection: "row",
  },

  primaryButtonText: {
    color: "#ffffff",
    fontSize: 15,
    fontWeight: "600",
  },

  disabled: {
    opacity: 0.5,
  },

  statusBox: {
    marginTop: 18,
    padding: 14,
    borderRadius: 10,
    backgroundColor: "#eeeeee",
  },

  statusText: {
    textAlign: "center",
    color: "#555555",
    fontSize: 13,
    lineHeight: 19,
  },

  footer: {
    alignItems: "center",
    marginTop: 40,
  },

  footerText: {
    fontSize: 12,
    color: "#999999",
  },

  footerSubtext: {
    fontSize: 11,
    color: "#aaaaaa",
    marginTop: 4,
    textAlign: "center",
  },

  header: {
    height: 64,
    backgroundColor: "#ffffff",
    borderBottomWidth: 1,
    borderBottomColor: "#e5e5e5",
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 16,
  },

  headerLeft: {
    flexDirection: "row",
    alignItems: "center",
    flex: 1,
  },

  smallLogo: {
    width: 36,
    height: 36,
    borderRadius: 10,
    backgroundColor: "#111111",
    alignItems: "center",
    justifyContent: "center",
    marginRight: 10,
  },

  smallLogoText: {
    color: "#ffffff",
    fontSize: 9,
    fontWeight: "800",
  },

  headerTextContainer: {
    flex: 1,
  },

  headerTitle: {
    fontSize: 14,
    fontWeight: "600",
    color: "#111111",
  },

  headerStatus: {
    fontSize: 11,
    color: "#16a34a",
    marginTop: 2,
  },

  headerActions: {
    flexDirection: "row",
  },

  iconButton: {
    width: 40,
    height: 40,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 10,
  },

  iconText: {
    fontSize: 28,
    fontWeight: "300",
    color: "#555555",
  },

  deleteIcon: {
    fontSize: 20,
    color: "#555555",
  },

  chatContent: {
    paddingHorizontal: 16,
    paddingTop: 20,
    paddingBottom: 30,
  },

  emptyChat: {
    minHeight: 450,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 30,
  },

  emptyIcon: {
    width: 52,
    height: 52,
    borderRadius: 26,
    backgroundColor: "#eeeeee",
    textAlign: "center",
    fontSize: 26,
    color: "#777777",
    paddingTop: 9,
  },

  emptyTitle: {
    fontSize: 18,
    fontWeight: "700",
    color: "#222222",
    marginTop: 14,
  },

  emptySubtitle: {
    fontSize: 14,
    color: "#888888",
    textAlign: "center",
    marginTop: 7,
    lineHeight: 21,
  },

  userMessageContainer: {
    alignItems: "flex-end",
    marginBottom: 22,
  },

  userBubble: {
    maxWidth: "82%",
    backgroundColor: "#111111",
    borderRadius: 18,
    borderBottomRightRadius: 5,
    paddingHorizontal: 15,
    paddingVertical: 11,
  },

  userText: {
    color: "#ffffff",
    fontSize: 14,
    lineHeight: 21,
  },

  aiMessageContainer: {
    marginBottom: 24,
  },

  aiRow: {
    flexDirection: "row",
    alignItems: "flex-start",
  },

  aiIcon: {
    width: 29,
    height: 29,
    borderRadius: 8,
    backgroundColor: "#111111",
    alignItems: "center",
    justifyContent: "center",
    marginRight: 10,
    marginTop: 1,
  },

  aiIconText: {
    color: "#ffffff",
    fontSize: 8,
    fontWeight: "800",
  },

  aiContent: {
    flex: 1,
  },

  aiHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 6,
  },

  aiName: {
    fontSize: 12,
    fontWeight: "700",
    color: "#222222",
  },

  copyText: {
    fontSize: 11,
    color: "#777777",
  },

  answerText: {
    fontSize: 14,
    lineHeight: 23,
    color: "#444444",
    marginBottom: 7,
  },

  heading1: {
    fontSize: 20,
    fontWeight: "700",
    color: "#111111",
    marginBottom: 10,
  },

  heading2: {
    fontSize: 18,
    fontWeight: "700",
    color: "#111111",
    marginBottom: 9,
  },

  heading3: {
    fontSize: 16,
    fontWeight: "700",
    color: "#111111",
    marginBottom: 8,
  },

  bulletRow: {
    flexDirection: "row",
    alignItems: "flex-start",
    marginBottom: 7,
  },

  bullet: {
    width: 20,
    fontSize: 16,
    color: "#555555",
  },

  numberBullet: {
    width: 25,
    fontSize: 14,
    color: "#555555",
  },

  emptyLine: {
    height: 5,
  },

  thinkingContainer: {
    flex: 1,
    paddingTop: 6,
  },

  thinkingText: {
    fontSize: 12,
    color: "#999999",
    marginTop: 4,
  },

  metadata: {
    flexDirection: "row",
    marginLeft: 40,
    marginTop: 5,
    marginBottom: 20,
  },

  metadataText: {
    fontSize: 11,
    color: "#999999",
    marginRight: 16,
  },

  structuredBox: {
    marginLeft: 40,
    marginBottom: 20,
    padding: 15,
    borderWidth: 1,
    borderColor: "#e2e2e2",
    borderRadius: 14,
    backgroundColor: "#ffffff",
  },

  structuredTitle: {
    fontSize: 14,
    fontWeight: "700",
    color: "#222222",
    marginBottom: 10,
  },

  dataRow: {
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: "#eeeeee",
  },

  dataLabel: {
    fontSize: 11,
    fontWeight: "600",
    color: "#777777",
    marginBottom: 3,
  },

  dataValue: {
    fontSize: 13,
    color: "#444444",
    lineHeight: 19,
  },

  suggestions: {
    marginLeft: 40,
    marginBottom: 10,
  },

  suggestionsTitle: {
    fontSize: 14,
    fontWeight: "700",
    color: "#222222",
    marginBottom: 10,
  },

  suggestion: {
    borderWidth: 1,
    borderColor: "#dddddd",
    borderRadius: 20,
    paddingHorizontal: 13,
    paddingVertical: 9,
    marginRight: 8,
    backgroundColor: "#ffffff",
  },

  suggestionText: {
    fontSize: 12,
    color: "#555555",
  },

  chatStatus: {
    position: "absolute",
    bottom: 95,
    left: 20,
    right: 20,
    padding: 12,
    borderRadius: 10,
    backgroundColor: "#ffffff",
    borderWidth: 1,
    borderColor: "#dddddd",
  },

  chatStatusText: {
    textAlign: "center",
    fontSize: 12,
    color: "#555555",
    lineHeight: 18,
  },

  inputArea: {
    backgroundColor: "#ffffff",
    borderTopWidth: 1,
    borderTopColor: "#e5e5e5",
    paddingHorizontal: 12,
    paddingTop: 10,
    paddingBottom:
      Platform.OS === "ios" ? 8 : 10,
  },

  inputBox: {
    minHeight: 52,
    borderWidth: 1,
    borderColor: "#cccccc",
    borderRadius: 16,
    backgroundColor: "#ffffff",
    flexDirection: "row",
    alignItems: "flex-end",
    paddingLeft: 12,
    paddingVertical: 7,
    paddingRight: 7,
  },

  textInput: {
    flex: 1,
    minHeight: 38,
    maxHeight: 110,
    fontSize: 14,
    color: "#333333",
    paddingTop: 8,
    paddingBottom: 8,
    paddingRight: 8,
  },

  sendButton: {
    width: 40,
    height: 40,
    borderRadius: 12,
    backgroundColor: "#111111",
    alignItems: "center",
    justifyContent: "center",
  },

  sendDisabled: {
    opacity: 0.35,
  },

  sendIcon: {
    color: "#ffffff",
    fontSize: 22,
    fontWeight: "700",
  },

  inputHint: {
    textAlign: "center",
    fontSize: 9,
    color: "#aaaaaa",
    marginTop: 6,
  },
});
import axios from "axios";

const API_URL = "http://192.168.1.10:8000";

const api = axios.create({
  baseURL: API_URL,
  timeout: 120000,
});

export const uploadDocument = async (formData) => {
  return api.post("/upload", formData, {
    headers: {
      "Content-Type": "multipart/form-data",
    },
  });
};

export const askQuestion = async (
  docId,
  question
) => {
  return api.post("/ask", {
    doc_id: docId,
    question,
    use_cache: true,
  });
};

export const getHistory = async (docId) => {
  return api.get(`/docs/${docId}/history`);
};

export default api;
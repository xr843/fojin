import api from "./client";

export interface ChatAttachmentMeta {
  id: number;
  filename: string;
  size_bytes: number;
  char_count: number;
  preview: string;
}

/**
 * Upload a chat attachment to the backend. The backend extracts text from
 * supported types (PDF/TXT/MD/DOCX/CSV/HTML) and returns a metadata record;
 * the caller passes `id` along with the next chat request via
 * `attachment_ids`, after which the backend marks the attachment consumed.
 */
export async function uploadChatAttachment(file: File): Promise<ChatAttachmentMeta> {
  const form = new FormData();
  form.append("file", file);
  const { data } = await api.post<ChatAttachmentMeta>(
    "/chat/attachments",
    form,
    {
      headers: { "Content-Type": "multipart/form-data" },
      // Parsing PDFs/DOCX is CPU-bound; default 15s axios timeout trips on
      // larger files even when the backend is healthy.
      timeout: 60000,
    },
  );
  return data;
}

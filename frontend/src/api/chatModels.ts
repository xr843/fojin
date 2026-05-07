import api from "./client";

export interface ChatModelOption {
  id: string;
  provider: string;
  label: string;
  description: string;
  vision: boolean;
  available: boolean;
  requires_byok: boolean;
}

export async function fetchChatModels(): Promise<ChatModelOption[]> {
  const { data } = await api.get<ChatModelOption[]>("/chat/models");
  return data;
}

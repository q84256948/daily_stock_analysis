import apiClient from './index';
import { API_BASE_URL } from '../utils/constants';
import { createApiError, isApiRequestError, parseApiError } from './error';
import type { ChatSessionItem, ChatSessionMessage } from './agent';

export interface ChanlunChatStreamOptions {
  signal?: AbortSignal;
}

export interface ChanlunChatRequest {
  message: string;
  session_id?: string;
  context?: unknown;
}

export const chanlunApi = {
  async getChatSessions(limit = 50): Promise<ChatSessionItem[]> {
    const response = await apiClient.get<{ sessions: ChatSessionItem[] }>(
      '/api/v1/chanlun/chat/sessions',
      { params: { limit } },
    );
    return response.data.sessions;
  },

  async getChatSessionMessages(sessionId: string): Promise<ChatSessionMessage[]> {
    const response = await apiClient.get<{ messages: ChatSessionMessage[] }>(
      `/api/v1/chanlun/chat/sessions/${sessionId}`,
    );
    return response.data.messages;
  },

  async deleteChatSession(sessionId: string): Promise<void> {
    await apiClient.delete(`/api/v1/chanlun/chat/sessions/${sessionId}`);
  },

  async chatStream(
    payload: ChanlunChatRequest,
    options?: ChanlunChatStreamOptions,
  ): Promise<Response> {
    const base = API_BASE_URL || '';
    const url = `${base}/api/v1/chanlun/chat/stream`;
    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        credentials: 'include',
        signal: options?.signal,
      });

      if (response.ok) {
        return response;
      }

      const contentType = response.headers.get('content-type') || '';
      let responseData: unknown = null;
      if (contentType.includes('application/json')) {
        responseData = await response.json().catch(() => null);
      } else {
        responseData = await response.text().catch(() => null);
      }

      const parsed = parseApiError({
        response: {
          status: response.status,
          statusText: response.statusText,
          data: responseData,
        },
      });
      throw createApiError(parsed, {
        response: {
          status: response.status,
          statusText: response.statusText,
          data: responseData,
        },
      });
    } catch (error: unknown) {
      if (isApiRequestError(error)) {
        throw error;
      }
      if (error instanceof Error && error.name === 'AbortError') {
        throw error;
      }

      const parsed = parseApiError(error);
      throw createApiError(parsed, { cause: error });
    }
  },
};

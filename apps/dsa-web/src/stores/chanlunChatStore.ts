import { createAgentChatStore } from './agentChatStore';
import { chanlunApi } from '../api/chanlunChat';

export const useChanlunChatStore = createAgentChatStore({
  api: chanlunApi,
  storageKey: 'dsa_chanlun_session_id',
  routePath: '/chanlun',
});

export type { Message, ProgressStep } from './agentChatStore';

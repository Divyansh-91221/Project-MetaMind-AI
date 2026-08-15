import { api } from './api';
import type { ChatMessage, CopilotResponse } from '@/types';

export const copilotApi = {
  /**
   * Ask the Copilot. `entityUrn` passes page context (the asset the user is viewing) so the
   * agent can resolve pronouns like "this table" without guessing.
   */
  chat: (message: string, options: { conversationId?: string; history?: ChatMessage[]; entityUrn?: string } = {}) =>
    api.post<CopilotResponse>('/copilot/chat', {
      message,
      conversation_id: options.conversationId,
      history: (options.history ?? []).map(({ role, content }) => ({ role, content })),
      entity_urn: options.entityUrn,
    }),

  examples: () => api.get<string[]>('/copilot/examples'),

  tools: () => api.get<Array<{ name: string; description: string; arguments: string }>>('/copilot/tools'),
};

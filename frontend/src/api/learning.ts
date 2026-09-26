import type { components } from './generated/openapi'
import { apiRequest } from './client'

export type LearningSession = components['LearningSessionResponse']
export type LearningQuestion = components['LearningQuestionResponse']
export type LearningFeedback = components['LearningFeedbackResponse']
export type LearningCitation = components['LearningCitationResponse']

export function createLearningSession(
  input: { knowledgeBaseId: string; topic: string; goalText: string },
  clientRequestId: string,
): Promise<LearningSession> {
  return apiRequest('/api/v1/learning-sessions', {
    method: 'POST',
    headers: { 'Idempotency-Key': clientRequestId },
    body: JSON.stringify({
      knowledge_base_id: input.knowledgeBaseId,
      topic: input.topic,
      goal_text: input.goalText,
      goal_type: 'CUSTOM',
      target_question_count: 1,
      client_request_id: clientRequestId,
    }),
  })
}

export function getLearningSession(learningSessionId: string): Promise<LearningSession> {
  return apiRequest(`/api/v1/learning-sessions/${learningSessionId}`)
}

export function submitLearningAttempt(
  questionId: string,
  input: { selectedOption: string; expectedQuestionVersion: number },
  clientRequestId: string,
): Promise<LearningFeedback> {
  return apiRequest(`/api/v1/learning-questions/${questionId}/attempts`, {
    method: 'POST',
    headers: { 'Idempotency-Key': clientRequestId },
    body: JSON.stringify({
      selected_option: input.selectedOption,
      expected_question_version: input.expectedQuestionVersion,
      client_request_id: clientRequestId,
    }),
  })
}

import type { components } from './generated/openapi'
import { apiRequest } from './client'

export type LearningSession = components['LearningSessionResponse']
export type LearningQuestion = components['LearningQuestionResponse']
export type LearningFeedback = components['LearningFeedbackResponse']
export type LearningCitation = components['LearningCitationResponse']

export type LearningProviderPlan = {
  generation_mode: string
  provider: string
  requested_model: string | null
  requires_charge_confirmation: boolean
  requires_provider_key: boolean
  budget_notice: string | null
  budget_blocks?: boolean
  outbound_summary: string
  question_estimate: {
    checked_on: string
    estimated_usd_ceiling: string
    disclaimer: string
  }
  feedback_estimate: {
    checked_on: string
    estimated_usd_ceiling: string
    disclaimer: string
  }
}

export function getLearningProviderPlan(): Promise<LearningProviderPlan> {
  return apiRequest('/api/v1/learning/provider-plan')
}

export function createLearningSession(
  input: {
    knowledgeBaseId: string
    topic: string
    goalText: string
    targetQuestionCount?: number
    confirmProviderCharge?: boolean
  },
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
      target_question_count: input.targetQuestionCount ?? 1,
      client_request_id: clientRequestId,
      confirm_provider_charge: input.confirmProviderCharge === true,
    }),
  })
}

export function createNextLearningQuestion(
  learningSessionId: string,
  input: { expectedSessionVersion: number; confirmProviderCharge?: boolean },
  clientRequestId: string,
): Promise<LearningSession> {
  return apiRequest(`/api/v1/learning-sessions/${learningSessionId}/next-question`, {
    method: 'POST',
    headers: { 'Idempotency-Key': clientRequestId },
    body: JSON.stringify({
      expected_session_version: input.expectedSessionVersion,
      client_request_id: clientRequestId,
      confirm_provider_charge: input.confirmProviderCharge === true,
    }),
  })
}

export function finishLearningSession(
  learningSessionId: string,
  expectedSessionVersion: number,
  clientRequestId: string,
): Promise<LearningSession> {
  return apiRequest(`/api/v1/learning-sessions/${learningSessionId}/finish`, {
    method: 'POST',
    headers: { 'Idempotency-Key': clientRequestId },
    body: JSON.stringify({ expected_session_version: expectedSessionVersion }),
  })
}

export function getLearningSession(learningSessionId: string): Promise<LearningSession> {
  return apiRequest(`/api/v1/learning-sessions/${learningSessionId}`)
}

export function submitLearningAttempt(
  questionId: string,
  input: { selectedOption: string; expectedQuestionVersion: number; confirmProviderCharge?: boolean },
  clientRequestId: string,
): Promise<LearningFeedback> {
  return apiRequest(`/api/v1/learning-questions/${questionId}/attempts`, {
    method: 'POST',
    headers: { 'Idempotency-Key': clientRequestId },
    body: JSON.stringify({
      selected_option: input.selectedOption,
      expected_question_version: input.expectedQuestionVersion,
      client_request_id: clientRequestId,
      confirm_provider_charge: input.confirmProviderCharge === true,
    }),
  })
}

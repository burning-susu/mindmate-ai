import { apiRequest } from './client'

export type CapabilityState = 'supported' | 'unsupported' | 'unknown'

export type ConsentStatus = {
  current_version: string
  accepted: boolean
  version: string | null
  accepted_at: string | null
}

export type ConnectionProbe = {
  status: 'success' | 'failed'
  checked_at: string
  requested_model: string
  resolved_model: string | null
  stream_supported: CapabilityState
  usage_supported: CapabilityState
  structured_output_supported: CapabilityState
  provider_request_id: string | null
  response_fingerprint: string | null
  usage: Record<string, number> | null
  error_code: string | null
  error_detail: string | null
  retryable: boolean | null
}

export type GenerationMode = 'mock' | 'deepseek'

export type CostEstimate = {
  checked_on: string
  model: string
  pricing_url: string
  rate_assumption: string
  input_usd_per_million_tokens: string
  output_usd_per_million_tokens: string
  knowledge_input_token_cap: number
  knowledge_output_token_cap: number
  knowledge_question_estimated_usd_ceiling: string
  probe_output_token_cap: number
  probe_estimated_usd_ceiling: string
  disclaimer: string
}

export type AiProviderStatus = {
  provider: string
  display_name: string
  configured: boolean
  credential_store: {
    available: boolean
    type: string
    error_code: string | null
  }
  requested_model: string
  consent: ConsentStatus
  probe: ConnectionProbe | null
  source_url: string
  pricing_url: string
  generation_mode?: GenerationMode
  cost_estimate?: CostEstimate
}

export function getAiProviderStatus(signal?: AbortSignal) {
  return apiRequest<AiProviderStatus>('/api/v1/ai/provider', { signal })
}

export function saveAiProviderKey(apiKey: string) {
  return apiRequest<AiProviderStatus>('/api/v1/ai/provider/key', {
    method: 'POST',
    body: JSON.stringify({ api_key: apiKey }),
  })
}

export function deleteAiProviderKey() {
  return apiRequest<AiProviderStatus>('/api/v1/ai/provider/key', { method: 'DELETE' })
}

export function testAiProviderConnection(confirmExternalTransfer: boolean) {
  return apiRequest<AiProviderStatus>('/api/v1/ai/provider/test', {
    method: 'POST',
    body: JSON.stringify({ confirm_external_transfer: confirmExternalTransfer }),
  })
}

export function setAiGenerationMode(mode: GenerationMode) {
  return apiRequest<AiProviderStatus>('/api/v1/ai/provider/generation-mode', {
    method: 'POST',
    body: JSON.stringify({ mode }),
  })
}

export function acceptExternalAiConsent(version: string) {
  return apiRequest<ConsentStatus>('/api/v1/ai/consent', {
    method: 'POST',
    body: JSON.stringify({ version }),
  })
}

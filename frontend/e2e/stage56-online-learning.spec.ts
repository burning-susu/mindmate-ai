import { mkdirSync } from 'node:fs'
import { expect, test, type Page } from '@playwright/test'
import process from 'node:process'

const knowledgeBaseId = process.env.STAGE56_REAL_KB_ID
const evidenceDir = process.env.STAGE56_EVIDENCE_DIR

type OnlineLearningSession = {
  learning_session_id: string
  provider: string
  live_model_called: boolean
  question: {
    question_id: string
    prompt_text: string
    feedback: unknown
  } & {
    options: Array<{ option_id: string; label: string }>
  }
}

test.beforeEach(() => {
  test.skip(!knowledgeBaseId, '需要由隔离的第五十六批测试服务准备合成知识库。')
  if (evidenceDir) mkdirSync(evidenceDir, { recursive: true })
})

async function providerCalls(page: Page) {
  const response = await page.request.get('/api/v1/testing/provider-fixture/calls')
  expect(response.ok()).toBe(true)
  return (await response.json()).calls as Array<{
    provider: string
    host: string
    requested_model: string
    request_kind: string
    authorization_present: boolean
  }>
}

async function configureOnlineProviders(page: Page) {
  await page.goto('/settings')
  await expect(page.getByRole('heading', { name: '设置' })).toBeVisible()

  await page.getByLabel('DeepSeek API Key').fill('stage56-deepseek-fixture-key')
  await page.getByRole('button', { name: '保存 Key' }).click()
  await expect(page.getByLabel('DeepSeek API Key')).toHaveValue('')
  await page.getByLabel(/我已阅读本版本外发说明/).check()
  await page.getByRole('button', { name: '确认并记录说明版本' }).click()

  await page.getByLabel('OpenAI API Key').fill('stage56-openai-fixture-key')
  await page.getByRole('button', { name: '保存 OpenAI Key' }).click()
  await expect(page.getByLabel('OpenAI API Key')).toHaveValue('')
  await page.getByLabel(/我已阅读 OpenAI 外发说明/).check()
  await page.getByRole('button', { name: '确认 OpenAI 外发说明' }).click()
}

async function createOnlineQuestion(page: Page, provider: 'deepseek' | 'openai_gpt6_sol') {
  await page.goto(`/learning/new?knowledge_base_id=${knowledgeBaseId}`)
  await page.getByLabel('学习主题').fill('API 单次请求超时时间')
  await page.getByLabel('学习目标').fill('记住资料中的请求超时值')
  await expect(page.getByText(/不超过 .* 美元/)).toBeVisible()

  const callsBefore = await providerCalls(page)
  await expect(page.getByRole('button', { name: '创建并开始' })).toBeDisabled()
  expect(await providerCalls(page)).toEqual(callsBefore)
  await page.getByLabel(/我确认本次向 .* 出题可能产生费用/).check()

  const createResponsePromise = page.waitForResponse((response) =>
    response.request().method() === 'POST' && new URL(response.url()).pathname === '/api/v1/learning-sessions',
  )
  await page.getByRole('button', { name: '创建并开始' }).click()
  const createResponse = await createResponsePromise
  expect(createResponse.status()).toBe(200)
  const created = await createResponse.json() as OnlineLearningSession
  expect(created.provider).toBe(provider === 'deepseek' ? 'DEEPSEEK' : 'OPENAI')
  expect(created.live_model_called).toBe(true)
  expect(created.question.feedback).toBeNull()
  expect(JSON.stringify(created)).not.toContain('answer_key')
  expect(JSON.stringify(created)).not.toContain('excerpt')
  await expect(page.getByText(created.question.prompt_text)).toBeVisible()
  if (evidenceDir) {
    await page.screenshot({ path: `${evidenceDir}/${provider}-question.png`, fullPage: true })
  }
  return { created, callsAfterQuestion: await providerCalls(page) }
}

async function submitOnlineAnswer(page: Page, created: OnlineLearningSession, provider: 'DEEPSEEK' | 'OPENAI') {
  await page.getByRole('radio', { name: '30 秒' }).check()
  await expect(page.getByRole('button', { name: '提交答案' })).toBeDisabled()
  const callsBefore = await providerCalls(page)
  await page.getByLabel(/我确认把当前答案和必要依据发给/).check()
  const attemptResponsePromise = page.waitForResponse((response) =>
    response.request().method() === 'POST' && /\/learning-questions\/[^/]+\/attempts$/.test(new URL(response.url()).pathname),
  )
  await page.getByRole('button', { name: '提交答案' }).click()
  const attemptResponse = await attemptResponsePromise
  expect(attemptResponse.status()).toBe(200)
  const attempt = await attemptResponse.json() as {
    result: string
    provider: string
    live_model_called: boolean
    citations: Array<{ file_name: string }>
    attempt_id: string
  }
  expect(attempt.result).toBe('CORRECT')
  expect(attempt.provider).toBe(provider)
  expect(attempt.live_model_called).toBe(true)
  expect(attempt.citations[0].file_name).toBe('服务超时策略.txt')
  await expect(page.getByLabel('作答反馈')).toContainText('结果：正确')
  await expect(page.getByLabel('作答反馈')).toContainText('30 秒')
  await expect(page.getByRole('button', { name: '[1] 服务超时策略.txt' })).toBeVisible()

  const calls = await providerCalls(page)
  expect(calls.length).toBe(callsBefore.length + 1)
  expect(calls.at(-1)?.provider).toBe(provider)
  expect(calls.at(-1)?.request_kind).toBe('feedback')
  await page.reload()
  const restored = await page.request.get(`/api/v1/learning-sessions/${created.learning_session_id}`)
  expect(restored.ok()).toBe(true)
  const reloaded = await restored.json() as { question: { feedback: { attempt_id: string } } }
  expect(reloaded.question.feedback.attempt_id).toBe(attempt.attempt_id)
  expect((await providerCalls(page)).length).toBe(calls.length)
  if (evidenceDir) {
    await page.screenshot({ path: `${evidenceDir}/${provider.toLowerCase()}-feedback-restored.png`, fullPage: true })
  }
}

test('real browser confirms separate DeepSeek and OpenAI learning operations', async ({ page }) => {
  test.setTimeout(180_000)
  await configureOnlineProviders(page)

  await page.getByRole('button', { name: '使用 DeepSeek 在线生成' }).click()
  const deepseek = await createOnlineQuestion(page, 'deepseek')
  expect(deepseek.callsAfterQuestion).toHaveLength(1)
  await expect(page.getByText(/服务 DEEPSEEK/)).toBeVisible()

  await page.goto('/settings')
  await page.getByRole('button', { name: '使用 OpenAI GPT-6 Sol' }).click()
  await page.goto(`/learning/session/${deepseek.created.learning_session_id}`)
  await expect(page.getByText(/服务 DEEPSEEK/)).toBeVisible()
  await submitOnlineAnswer(page, deepseek.created, 'DEEPSEEK')

  await page.goto('/settings')
  await page.getByRole('button', { name: '使用 OpenAI GPT-6 Sol' }).click()
  const openai = await createOnlineQuestion(page, 'openai_gpt6_sol')
  expect(openai.callsAfterQuestion).toHaveLength(3)
  expect(openai.callsAfterQuestion.at(-1)?.provider).toBe('OPENAI')
  await submitOnlineAnswer(page, openai.created, 'OPENAI')

  const calls = await providerCalls(page)
  expect(calls.map((item) => `${item.provider}:${item.request_kind}`)).toEqual([
    'DEEPSEEK:question',
    'DEEPSEEK:feedback',
    'OPENAI:question',
    'OPENAI:feedback',
  ])
  expect(calls.every((item) => item.authorization_present)).toBe(true)
  expect(calls.every((item) => item.host === 'api.deepseek.com' || item.host === 'api.openai.com')).toBe(true)
  expect(calls.some((item) => item.requested_model === 'deepseek-flash')).toBe(true)
  expect(calls.some((item) => item.requested_model === 'gpt-6-sol')).toBe(true)
  expect(await page.evaluate(() => performance.getEntriesByType('resource').some((entry) => /api\.(deepseek|openai)\.com/.test(entry.name)))).toBe(false)
})

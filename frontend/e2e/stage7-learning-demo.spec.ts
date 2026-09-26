import { mkdirSync } from 'node:fs'
import { expect, test, type Page } from '@playwright/test'
import process from 'node:process'

const knowledgeBaseId = process.env.STAGE7_REAL_KB_ID
const evidenceDir = process.env.STAGE7_EVIDENCE_DIR
const topic = 'API 单次请求超时时间是多少秒？'
const goal = '记住资料中的唯一超时值'
const unsupportedTopic = '南极冰芯中氮同位素的具体丰度百分比是多少？'

test.beforeEach(() => {
  test.skip(!knowledgeBaseId, '请先准备固定真实 READY 知识库。')
  if (evidenceDir) mkdirSync(evidenceDir, { recursive: true })
})

async function readSession(page: Page, sessionId: string) {
  const response = await page.request.get(`/api/v1/learning-sessions/${sessionId}`)
  expect(response.ok()).toBe(true)
  return response.json()
}

test('真实知识库完成一题反馈、刷新恢复，并拒绝无证据主题', async ({ page }) => {
  test.setTimeout(180_000)
  await page.goto(`/knowledge-bases/${knowledgeBaseId}`)
  await expect(page.getByText('索引就绪').first()).toBeVisible()
  await page.getByRole('button', { name: '基于此知识库学习' }).click()
  await expect(page.getByRole('heading', { name: '基于知识库的一题演示' })).toBeVisible()
  await expect(page.getByText('本地规则模拟演示，未调用真实 DeepSeek。学习出题不读取聊天设置里的在线模式。')).toBeVisible()

  await page.getByRole('textbox', { name: '学习主题' }).fill(topic)
  await page.getByRole('textbox', { name: '学习目标' }).fill(goal)
  const createResponsePromise = page.waitForResponse((response) =>
    response.request().method() === 'POST' && new URL(response.url()).pathname === '/api/v1/learning-sessions',
  )
  await page.getByRole('button', { name: '创建并开始' }).click()
  const createResponse = await createResponsePromise
  expect(createResponse.status()).toBe(200)
  const created = await createResponse.json()
  expect(created.live_model_called).toBe(false)
  expect(created.model).toBe('learning-demo-fixture-v1')
  expect(created.status).toBe('IN_PROGRESS')
  expect(created.question.feedback).toBeNull()
  expect(JSON.stringify(created)).not.toContain('answer_key')
  await expect(page).toHaveURL(new RegExp(`/learning/session/${created.learning_session_id}$`))
  await expect(page.getByText(created.question.prompt_text)).toBeVisible()
  await expect(page.getByRole('radio')).toHaveCount(4)
  const labels = created.question.options.map((option: { label: string }) => option.label)
  await expect(page.getByRole('button', { name: '提交答案' })).toBeDisabled()
  await page.getByRole('radio', { name: labels[0] }).check()
  const attemptPromise = page.waitForResponse((response) =>
    response.request().method() === 'POST' && /\/learning-questions\/[^/]+\/attempts$/.test(new URL(response.url()).pathname),
  )
  await page.getByRole('button', { name: '提交答案' }).click()
  const attemptResponse = await attemptPromise
  expect(attemptResponse.status()).toBe(200)
  const attempt = await attemptResponse.json()
  const resultText = attempt.result === 'CORRECT' ? '正确' : attempt.result === 'INCORRECT' ? '不正确' : attempt.result
  await expect(page.getByLabel('作答反馈')).toContainText(`结果：${resultText}`)
  await expect(page.getByLabel('作答反馈')).toContainText(attempt.explanation)
  expect(attempt.citations[0].file_name).toBe('服务超时策略.txt')
  await page.getByRole('button', { name: '[1] 服务超时策略.txt' }).click()
  const source = page.getByRole('complementary', { name: '引用 1' })
  await expect(source).toContainText('服务超时策略.txt')
  await expect(source).toContainText(attempt.citations[0].excerpt)
  if (evidenceDir) await page.screenshot({ path: `${evidenceDir}/learning-feedback.png`, fullPage: true })

  await page.reload()
  const restored = await readSession(page, created.learning_session_id)
  await expect(page.getByLabel('作答反馈')).toContainText(restored.question.feedback.explanation)
  await expect(page.getByLabel('作答反馈')).toContainText(`结果：${resultText}`)
  expect(restored.question.feedback.attempt_id).toBe(attempt.attempt_id)

  await page.goto(`/learning/new?knowledge_base_id=${knowledgeBaseId}`)
  await page.getByRole('textbox', { name: '学习主题' }).fill(unsupportedTopic)
  await page.getByRole('textbox', { name: '学习目标' }).fill('核对资料不足')
  const refusedPromise = page.waitForResponse((response) =>
    response.request().method() === 'POST' && new URL(response.url()).pathname === '/api/v1/learning-sessions',
  )
  await page.getByRole('button', { name: '创建并开始' }).click()
  const refusedResponse = await refusedPromise
  expect(refusedResponse.status()).toBe(200)
  const refused = await refusedResponse.json()
  expect(refused.status).toBe('FAILED')
  expect(refused.failure_code).toBe('EVIDENCE_INSUFFICIENT')
  expect(refused.question).toBeNull()
  await expect(page.getByRole('alert')).toContainText(refused.failure_detail)
  await expect(page.getByRole('radio')).toHaveCount(0)
  await expect(page.getByRole('link', { name: '返回修改主题' })).toBeVisible()
})

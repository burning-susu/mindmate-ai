import { mkdirSync, writeFileSync } from 'node:fs'
import { expect, test, type Locator, type Page } from '@playwright/test'
import process from 'node:process'

const knowledgeBaseId = process.env.STAGE6_REAL_KB_ID
const expectedIndexVersionId = process.env.STAGE6_REAL_INDEX_VERSION_ID
const evidenceDir = process.env.STAGE6_REAL_EVIDENCE_DIR
const positiveQuestion = 'API 单次请求超时时间是多少秒？'
const negativeQuestion = '南极冰芯中氮同位素的具体丰度百分比是多少？'

function normalizeRenderedAnswer(content: string): string {
  return content
    .split(/\n{2,}/)
    .map((paragraph) => paragraph.replace(/\s+/g, ' ').trim())
    .filter((paragraph) => paragraph.length > 0)
    .join('\n')
}

async function expectVisibleAnswer(answer: Locator, content: string) {
  const expected = normalizeRenderedAnswer(content)
  await expect.poll(
    async () => normalizeRenderedAnswer(await answer.innerText()),
    { timeout: 30_000 },
  ).toBe(expected)
}

async function waitForCompletedOperation(page: Page, operationId: string) {
  const deadline = Date.now() + 30_000
  let payload
  while (Date.now() < deadline) {
    const response = await page.request.get(`/api/v1/ai-operations/${operationId}`)
    expect(response.ok()).toBe(true)
    payload = await response.json()
    if (!['QUEUED', 'RUNNING', 'STOPPING'].includes(payload.status)) return payload
    await page.waitForTimeout(200)
  }
  throw new Error(`operation ${operationId} did not finish`)
}

test.beforeEach(() => {
  test.skip(!knowledgeBaseId || !expectedIndexVersionId, '请先准备固定真实 READY 知识库。')
  if (evidenceDir) mkdirSync(evidenceDir, { recursive: true })
})

test('真实 READY 知识库问答、引用定位、刷新恢复与资料不足', async ({ page }) => {
  await page.goto(`/knowledge-bases/${knowledgeBaseId}`)
  await expect(page.getByText('索引就绪').first()).toBeVisible()
  await page.getByRole('button', { name: '基于此知识库提问' }).click()
  await expect(page.getByText('知识库模式')).toBeVisible()
  await expect(page.getByText('范围：第二十五批·固定资料主库', { exact: true })).toBeVisible()

  const send = async (question: string) => {
    await page.getByRole('textbox', { name: '消息内容' }).fill(question)
    const responsePromise = page.waitForResponse((response) =>
      response.request().method() === 'POST' &&
      /\/api\/v1\/(conversations|conversations\/[^/]+\/messages)$/.test(new URL(response.url()).pathname),
    )
    await page.getByRole('button', { name: '发送' }).click()
    const response = await responsePromise
    expect(response.status()).toBe(202)
    return response.json()
  }

  const eventsResponsePromise = page.waitForResponse((response) =>
    /\/api\/v1\/ai-operations\/[^/]+\/events/.test(new URL(response.url()).pathname),
  )
  const first = await send(positiveQuestion)
  const eventsResponse = await eventsResponsePromise
  expect(eventsResponse.status()).toBe(200)
  const firstResult = await waitForCompletedOperation(page, first.operation_id)
  expect(firstResult.status).toBe('COMPLETED')
  const answers = page.locator('[aria-label="AI 回答"]')
  await expectVisibleAnswer(answers.first(), firstResult.assistant_message.content)
  await expect(page.getByRole('button', { name: '打开引用 1' })).toBeVisible()
  expect(firstResult.answer_version.citations[0].index_version_id).toBe(expectedIndexVersionId)
  expect(firstResult.answer_version.citations[0].file_name).toBe('服务超时策略.txt')
  expect(firstResult.answer_version.citations[0].source_status).toBe('AVAILABLE')
  await page.getByRole('button', { name: '打开引用 1' }).click()
  const source = page.getByRole('complementary', { name: '引用 1' })
  await expect(source).toContainText('服务超时策略.txt')
  await expect(source).toContainText('30 秒')
  await expect(source).toContainText('第 1-12 行')
  await expect(source.getByRole('link', { name: '打开文件详情' })).toHaveAttribute('href', /\/files\//)
  const fileDetailHref = await source.getByRole('link', { name: '打开文件详情' }).getAttribute('href')
  expect(fileDetailHref).toBe(`/files/${firstResult.answer_version.citations[0].file_id}`)
  if (evidenceDir) await page.screenshot({ path: `${evidenceDir}/positive-citation.png`, fullPage: true })

  await page.reload()
  await expectVisibleAnswer(page.locator('[aria-label="AI 回答"]').first(), firstResult.assistant_message.content)
  await expect(page.getByRole('button', { name: '打开引用 1' })).toBeVisible()
  const persistedMessagesResponse = await page.request.get(`/api/v1/conversations/${first.conversation_id}/messages`)
  expect(persistedMessagesResponse.ok()).toBe(true)
  const persistedMessages = await persistedMessagesResponse.json()
  expect(persistedMessages.items[1].content).toBe(firstResult.assistant_message.content)
  expect(normalizeRenderedAnswer(persistedMessages.items[1].content)).toBe(
    normalizeRenderedAnswer(firstResult.assistant_message.content),
  )
  expect(persistedMessages.items[1].citations[0].citation_id).toBe(firstResult.answer_version.citations[0].citation_id)
  await page.getByRole('button', { name: '打开引用 1' }).click()
  await expect(page.getByRole('complementary', { name: '引用 1' })).toContainText('服务超时策略.txt')
  await page.goto(`/chat/${first.conversation_id}`)
  await expectVisibleAnswer(page.locator('[aria-label="AI 回答"]').first(), persistedMessages.items[1].content)
  await expect(page.getByRole('button', { name: '打开引用 1' })).toBeVisible()

  const second = await send(positiveQuestion)
  const secondResult = await waitForCompletedOperation(page, second.operation_id)
  expect(secondResult.status).toBe('COMPLETED')
  await expect(page.getByRole('button', { name: '打开引用 1' })).toHaveCount(2)
  await expect(page.getByText('知识库模式')).toBeVisible()

  const third = await send(negativeQuestion)
  const negativeResult = await waitForCompletedOperation(page, third.operation_id)
  expect(negativeResult.status).toBe('COMPLETED')
  expect(negativeResult.error_code).toBe('EVIDENCE_INSUFFICIENT')
  expect(negativeResult.answer_version.citations).toHaveLength(0)
  expect(negativeResult.assistant_message.citations).toHaveLength(0)
  const negativeAnswer = page.locator('[aria-label="AI 回答"]').last()
  await expectVisibleAnswer(negativeAnswer, negativeResult.assistant_message.content)
  await expect(negativeAnswer.getByRole('button', { name: /打开引用/ })).toHaveCount(0)
  await expect(negativeAnswer).toContainText('资料不足')
  if (evidenceDir) await page.screenshot({ path: `${evidenceDir}/negative-insufficient.png`, fullPage: true })
  if (evidenceDir) writeFileSync(`${evidenceDir}/browser-operations.json`, JSON.stringify({
    knowledge_base_id: knowledgeBaseId,
    expected_index_version_id: expectedIndexVersionId,
    conversation_id: first.conversation_id,
    positive: {
      question: positiveQuestion,
      status: firstResult.status,
      error_code: firstResult.error_code,
      answer_version_id: firstResult.answer_version.answer_version_id,
      content: firstResult.assistant_message.content,
      citations: firstResult.answer_version.citations,
    },
    second_round: {
      status: secondResult.status,
      citations: secondResult.answer_version.citations,
    },
    negative: {
      question: negativeQuestion,
      status: negativeResult.status,
      error_code: negativeResult.error_code,
      content: negativeResult.assistant_message.content,
      citation_count: negativeResult.answer_version.citations.length,
    },
  }, null, 2), 'utf8')
})

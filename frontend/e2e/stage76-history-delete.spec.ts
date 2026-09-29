import { mkdirSync } from 'node:fs'
import { expect, test, type Page } from '@playwright/test'

const conversationId = 'stage76-conversation-1'
const learningId = 'stage76-learning-1'

async function installHistoryMock(page: Page) {
  const requests: string[] = []
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const method = request.method()
    let payload: unknown = { status: 'ok' }

    if (url.pathname.endsWith('/health')) {
      payload = { status: 'ok', version: 'stage76-mock' }
    } else if (url.pathname.endsWith('/system/session')) {
      payload = { status: 'ready' }
    } else if (url.pathname.endsWith('/history/conversations')) {
      payload = {
        items: [{
          conversation_id: conversationId,
          title: '阶段七十六对话记录',
          summary: 'Mock 验收对象',
          current_mode: 'GENERAL_CHAT',
          scope_name: null,
          status: 'ACTIVE',
          source_status: 'NOT_APPLICABLE',
          message_count: 2,
          created_at: '2026-09-29T08:00:00Z',
          updated_at: '2026-09-29T08:05:00Z',
          row_version: 3,
          locations: [],
        }],
        next_cursor: null,
      }
    } else if (url.pathname.endsWith('/history/learning-sessions')) {
      payload = {
        items: [{
          learning_session_id: learningId,
          topic: '阶段七十六学习记录',
          goal_type: 'CUSTOM',
          scope_name: 'Mock 演示库',
          scope_file_count: 1,
          status: 'IN_PROGRESS',
          source_status: 'AVAILABLE',
          answered_count: 0,
          target_question_count: 1,
          created_at: '2026-09-29T08:00:00Z',
          updated_at: '2026-09-29T08:05:00Z',
          row_version: 5,
          locations: [],
        }],
        next_cursor: null,
      }
    } else if (url.pathname.endsWith('/history/trash')) {
      const learning = url.searchParams.get('object_type') === 'learning_session'
      payload = {
        items: [{
          object_type: learning ? 'learning_session' : 'conversation',
          object_id: learning ? learningId : conversationId,
          title: learning ? '阶段七十六学习记录' : '阶段七十六对话记录',
          deleted_at: '2026-09-29T08:10:00Z',
          row_version: learning ? 6 : 4,
        }],
        next_cursor: null,
      }
    } else if (method === 'DELETE') {
      requests.push(`${method} ${url.pathname}${url.search}`)
      if (url.pathname.endsWith('/permanent')) {
        await new Promise((resolve) => setTimeout(resolve, 150))
        payload = url.pathname.includes('/learning-sessions/')
          ? { learning_session_id: learningId, status: 'PURGED' }
          : { conversation_id: conversationId, status: 'PURGED' }
      } else if (url.pathname.includes('/learning-sessions/')) {
        payload = { learning_session_id: learningId, topic: '阶段七十六学习记录', row_version: 6 }
      } else {
        payload = { conversation_id: conversationId, title: '阶段七十六对话记录', row_version: 4 }
      }
    }

    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(payload) })
  })
  return requests
}

test('conversation and learning history confirmations work with isolated mock data', async ({ page }) => {
  const requests = await installHistoryMock(page)
  mkdirSync('test-results', { recursive: true })
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.goto('/history')

  const conversationTrash = page.getByRole('button', { name: '移入回收站' })
  await expect(conversationTrash).toBeVisible()
  await conversationTrash.click()
  let dialog = page.getByRole('dialog', { name: '移入回收站' })
  await expect(dialog).toContainText('阶段七十六对话记录')
  await expect(dialog).toContainText('可以从回收站恢复')
  await expect(dialog).toContainText('不会删除来源文件或知识库')
  await expect(dialog.locator(':focus')).toHaveCount(1)
  expect(await dialog.evaluate((element) => element.contains(document.activeElement))).toBe(true)
  await page.screenshot({ path: 'test-results/stage76-history-dialog-desktop.png' })
  await page.keyboard.press('Escape')
  await expect(dialog).not.toBeVisible()
  expect(requests).toHaveLength(0)

  await conversationTrash.click()
  dialog = page.getByRole('dialog', { name: '移入回收站' })
  await dialog.getByRole('button', { name: '移入回收站' }).click()
  await expect(dialog).not.toBeVisible()
  expect(requests.filter((request) => request.includes(`/conversations/${conversationId}?`))).toHaveLength(1)

  await page.goto('/history?view=trash')
  await page.getByRole('button', { name: '永久删除' }).click()
  dialog = page.getByRole('dialog', { name: '确认永久删除' })
  await expect(dialog).toContainText('此操作无法撤销')
  await expect(dialog).toContainText('只删除对应历史记录')
  await expect(dialog).toContainText('不会删除来源文件或知识库')
  await expect(dialog.getByLabel('确认词')).toHaveCount(0)
  await page.screenshot({ path: 'test-results/stage76-history-purge-desktop.png' })
  const conversationPurge = dialog.getByRole('button', { name: '永久删除' })
  await conversationPurge.dblclick()
  await expect(dialog).not.toBeVisible()
  expect(requests.filter((request) => request.includes(`/conversations/${conversationId}/permanent`))).toHaveLength(1)

  await page.goto('/history?tab=learning')
  const learningTrash = page.getByRole('button', { name: '移入回收站' })
  await expect(learningTrash).toBeVisible()
  await learningTrash.click()
  dialog = page.getByRole('dialog', { name: '移入回收站' })
  await expect(dialog).toContainText('阶段七十六学习记录')
  await dialog.getByRole('button', { name: '移入回收站' }).click()
  await expect(dialog).not.toBeVisible()
  expect(requests.filter((request) => request.includes(`/learning-sessions/${learningId}?`))).toHaveLength(1)

  await page.goto('/history?tab=learning&view=trash')
  await page.getByRole('button', { name: '永久删除' }).click()
  dialog = page.getByRole('dialog', { name: '确认永久删除' })
  await expect(dialog).toContainText('阶段七十六学习记录')
  await expect(dialog.getByLabel('确认词')).toHaveCount(0)
  await dialog.getByRole('button', { name: '取消' }).click()
  await expect(dialog).not.toBeVisible()
  expect(requests.filter((request) => request.includes(`/learning-sessions/${learningId}/permanent`))).toHaveLength(0)

  await page.getByRole('button', { name: '永久删除' }).click()
  dialog = page.getByRole('dialog', { name: '确认永久删除' })
  await dialog.getByRole('button', { name: '永久删除' }).click()
  await expect(dialog).not.toBeVisible()
  expect(requests.filter((request) => request.includes(`/learning-sessions/${learningId}/permanent`))).toHaveLength(1)
  expect(requests).toHaveLength(4)
})

test('history delete dialog stays centered and within a narrow viewport', async ({ page }) => {
  await installHistoryMock(page)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/history?tab=learning')
  await page.getByRole('button', { name: '移入回收站' }).click()
  const dialog = page.getByRole('dialog', { name: '移入回收站' })
  await expect(dialog).toBeVisible()

  const geometry = await dialog.evaluate((element) => {
    const rect = element.getBoundingClientRect()
    return {
      left: rect.left,
      right: rect.right,
      top: rect.top,
      bottom: rect.bottom,
      viewportWidth: window.innerWidth,
      viewportHeight: window.innerHeight,
      documentWidth: document.documentElement.scrollWidth,
    }
  })
  expect(geometry.left).toBeGreaterThanOrEqual(0)
  expect(geometry.right).toBeLessThanOrEqual(geometry.viewportWidth)
  expect(geometry.top).toBeGreaterThanOrEqual(0)
  expect(geometry.bottom).toBeLessThanOrEqual(geometry.viewportHeight)
  expect(geometry.documentWidth).toBeLessThanOrEqual(geometry.viewportWidth)
  await page.screenshot({ path: 'test-results/stage76-history-dialog-mobile.png' })
})

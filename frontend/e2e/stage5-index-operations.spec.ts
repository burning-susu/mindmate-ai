import { expect, test } from '@playwright/test'
import { mkdirSync } from 'node:fs'
import process from 'node:process'

const knowledgeBaseId = process.env.STAGE5_INDEX_OPS_KB_ID
const evidenceDir = process.env.STAGE5_INDEX_OPS_EVIDENCE_DIR

async function readIndexStatus(page: import('@playwright/test').Page) {
  return page.evaluate(async (id) => {
    const response = await fetch(`/api/v1/knowledge-bases/${id}/index-status`, { cache: 'no-store' })
    if (!response.ok) throw new Error(`索引状态 API 返回 ${response.status}`)
    return response.json() as Promise<{
      status: string
      active_index_version_id: string | null
      target_index_version_id: string | null
      target_index_version_status: string | null
      operation_in_progress: boolean
      embedding_model_state: string
      failures: Array<{ file_id: string; reason_code: string; retryable: boolean }>
      tasks: Array<{ task_id: string; task_type: string; status: string }>
    }>
  }, knowledgeBaseId)
}

test.beforeEach(() => {
  test.skip(!knowledgeBaseId, '请先准备隔离的固定 READY 知识库。')
  if (evidenceDir) mkdirSync(evidenceDir, { recursive: true })
})

test('真实重建创建持久任务并完成新索引版本', async ({ page }) => {
  test.setTimeout(240_000)
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.goto(`/knowledge-bases/${knowledgeBaseId}`)
  await expect(page.getByRole('heading', { name: '索引状态与任务' })).toBeVisible()

  const initial = await readIndexStatus(page)
  expect(initial.status).toBe('READY')
  expect(initial.active_index_version_id).toBeTruthy()
  expect(['READY', 'MISSING_OFFLINE']).toContain(initial.embedding_model_state)
  const oldVersionId = initial.active_index_version_id
  await expect(page.locator('.index-workbench__model-state')).toContainText(
    initial.embedding_model_state === 'READY' ? '本地 Embedding 模型可用' : '本地 Embedding 模型缺失',
  )

  const rebuildResponse = page.waitForResponse(
    (response) => response.url().includes(`/knowledge-bases/${knowledgeBaseId}/index/rebuild`) && response.request().method() === 'POST',
  )
  page.once('dialog', (dialog) => dialog.accept())
  await page.getByRole('button', { name: '重建当前知识库索引' }).click()
  const submittedRebuild = await rebuildResponse
  expect(submittedRebuild.status()).toBe(202)
  const rebuildTask = await submittedRebuild.json() as { task_id: string; task_type: string }
  expect(rebuildTask.task_type).toBe('INDEX_PREPROCESS')

  await expect.poll(async () => {
    const current = await readIndexStatus(page)
    return current.active_index_version_id !== oldVersionId
      && current.active_index_version_id !== null
      && current.active_index_version_status === 'READY'
      && current.operation_in_progress === false
  }, { timeout: 180_000, intervals: [500, 1000, 2000] }).toBe(true)
  const rebuilt = await readIndexStatus(page)
  expect(rebuilt.status).toBe('READY')
  expect(rebuilt.active_index_version_id).not.toBe(oldVersionId)
  expect(rebuilt.failures).toEqual([])
  expect(rebuilt.tasks.some((task) => task.task_id === rebuildTask.task_id && task.status === 'COMPLETED')).toBe(true)
  await expect(page.locator('.index-workbench > .section-heading p')).toHaveText('索引就绪')

  await page.setViewportSize({ width: 390, height: 844 })
  const overflow = await page.evaluate(() => {
    const viewportWidth = document.documentElement.clientWidth
    const offenders = Array.from(document.querySelectorAll('body *'))
      .map((element) => {
        const bounds = element.getBoundingClientRect()
        return {
          tag: element.tagName,
          className: typeof element.className === 'string' ? element.className : '',
          left: Math.round(bounds.left),
          right: Math.round(bounds.right),
          width: Math.round(bounds.width),
          scrollWidth: element.scrollWidth,
          clientWidth: element.clientWidth,
          text: (element.textContent ?? '').trim().slice(0, 80),
        }
      })
      .filter((element) => element.right > viewportWidth + 1 || element.left < -1)
      .slice(0, 12)
    return {
      hasOverflow: document.documentElement.scrollWidth > viewportWidth,
      documentWidth: document.documentElement.scrollWidth,
      viewportWidth,
      offenders,
    }
  })
  expect(overflow.hasOverflow, JSON.stringify(overflow)).toBe(false)
  if (evidenceDir) await page.screenshot({ path: `${evidenceDir}/index-operations-mobile.png`, fullPage: true })
})

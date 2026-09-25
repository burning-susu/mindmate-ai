import { expect, test } from '@playwright/test'
import { mkdirSync } from 'node:fs'
import process from 'node:process'

const enabled = process.env.STAGE5_MODEL_INSTALL === '1'
const evidenceDir = process.env.STAGE5_MODEL_INSTALL_EVIDENCE_DIR

test('用户主动安装固定 ONNX 模型后可建立真实本地索引', async ({ page }) => {
  test.skip(!enabled, '真实模型下载验收需使用新的隔离数据目录显式启用。')
  test.setTimeout(900_000)
  if (evidenceDir) mkdirSync(evidenceDir, { recursive: true })
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.goto('/knowledge-bases/new')

  const seeded = await page.evaluate(async () => {
    const runId = crypto.randomUUID()
    const session = await fetch('/api/v1/system/session', { method: 'POST' })
    if (!session.ok) throw new Error('本地会话初始化失败')
    const knowledgeBaseResponse = await fetch('/api/v1/knowledge-bases', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Idempotency-Key': `stage5-model-kb-${runId}` },
      body: JSON.stringify({
        name: 'Embedding 安装验收',
        description: '隔离的本地模型安装与索引验收资料',
        icon: 'book-open',
        color: '#176b87',
      }),
    })
    if (!knowledgeBaseResponse.ok) throw new Error(`知识库建立失败：${knowledgeBaseResponse.status}`)
    const knowledgeBase = await knowledgeBaseResponse.json() as { knowledge_base_id: string }

    const form = new FormData()
    form.append('files', new File(
      [`本地 ONNX 模型通过固定 revision 与 SHA-256 校验后，知识库才开始建立向量索引。${runId}`],
      `模型安装验收-${runId.slice(0, 8)}.txt`,
      { type: 'text/plain' },
    ))
    const importResponse = await fetch('/api/v1/file-imports', {
      method: 'POST',
      headers: { 'Idempotency-Key': `stage5-model-file-${runId}` },
      body: form,
    })
    if (!importResponse.ok) throw new Error(`测试资料导入失败：${importResponse.status}`)
    const imported = await importResponse.json() as { items: Array<{ file_id: string }> }
    const fileId = imported.items[0]?.file_id
    if (!fileId) throw new Error('测试资料未创建本地文件记录')
    return { knowledgeBaseId: knowledgeBase.knowledge_base_id, fileId }
  })

  await expect.poll(async () => page.evaluate(async (fileId) => {
    const response = await fetch('/api/v1/files?limit=100&sort=updated_at', { cache: 'no-store' })
    const payload = await response.json() as { items: Array<{ file_id: string; status: string }> }
    return payload.items.find((item) => item.file_id === fileId)?.status
  }, seeded.fileId), { timeout: 60_000, intervals: [500, 1000] }).toBe('PARSED')

  const memberTask = await page.evaluate(async ({ knowledgeBaseId, fileId }) => {
    const response = await fetch(`/api/v1/knowledge-bases/${knowledgeBaseId}/files`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Idempotency-Key': `stage5-model-member-${crypto.randomUUID()}` },
      body: JSON.stringify({ file_ids: [fileId] }),
    })
    if (!response.ok) throw new Error(`知识库成员加入失败：${response.status}`)
    return response.json() as Promise<{ task_id: string }>
  }, seeded)
  await expect.poll(async () => page.evaluate(async (taskId) => {
    const response = await fetch(`/api/v1/tasks/${taskId}`, { cache: 'no-store' })
    const payload = await response.json() as { status: string }
    return payload.status
  }, memberTask.task_id), { timeout: 30_000, intervals: [200, 500] }).toBe('COMPLETED')

  await page.goto(`/knowledge-bases/${seeded.knowledgeBaseId}`)
  await expect(page.getByRole('heading', { name: '索引状态与任务' })).toBeVisible()
  let beforeInstall = await page.evaluate(async () => {
    const response = await fetch('/api/v1/embedding-model', { cache: 'no-store' })
    return response.json() as Promise<{ state: string; total_size_bytes: number; downloaded_bytes: number }>
  })
  if (!['MISSING', 'READY'].includes(beforeInstall.state)) {
    await expect.poll(async () => page.evaluate(async () => {
      const response = await fetch('/api/v1/embedding-model', { cache: 'no-store' })
      return (await response.json() as { state: string }).state
    }), { timeout: 30_000, intervals: [250, 500, 1000] }).toMatch(/^(MISSING|READY)$/)
    beforeInstall = await page.evaluate(async () => {
      const response = await fetch('/api/v1/embedding-model', { cache: 'no-store' })
      return response.json() as Promise<{ state: string; total_size_bytes: number; downloaded_bytes: number }>
    })
  }
  expect(beforeInstall.total_size_bytes).toBe(95_291_718)
  if (beforeInstall.state === 'MISSING') {
    expect(beforeInstall.downloaded_bytes).toBe(0)
    await expect(page.getByRole('button', { name: '下载并安装模型' })).toBeVisible()
    const installResponsePromise = page.waitForResponse(
      (response) => response.url().endsWith('/api/v1/embedding-model/install') && response.request().method() === 'POST',
    )
    await page.getByRole('button', { name: '下载并安装模型' }).click()
    const installResponse = await installResponsePromise
    expect(installResponse.status()).toBe(202)
    await expect(page.getByRole('progressbar', { name: '模型下载进度' })).toBeVisible({ timeout: 120_000 })
    await expect.poll(async () => Number(await page.getByRole('progressbar', { name: '模型下载进度' }).getAttribute('value')),
      { timeout: 120_000, intervals: [250, 500, 1000] },
    ).toBeGreaterThan(0)
    if (evidenceDir) await page.screenshot({ path: `${evidenceDir}/model-download-progress.png`, fullPage: true })

    await expect.poll(async () => page.evaluate(async () => {
      const response = await fetch('/api/v1/embedding-model', { cache: 'no-store' })
      const payload = await response.json() as { state: string; downloaded_bytes: number; total_size_bytes: number }
      return { ...payload }
    }), { timeout: 600_000, intervals: [500, 1000, 2000] }).toMatchObject({
      state: 'READY',
      downloaded_bytes: 95_291_718,
      total_size_bytes: 95_291_718,
    })
  } else {
    expect(beforeInstall.state).toBe('READY')
    expect(beforeInstall.downloaded_bytes).toBe(95_291_718)
    await expect(page.getByRole('button', { name: '下载并安装模型' })).toHaveCount(0)
  }
  await expect(page.getByText('许可：MIT（依据 BAAI 上游；Xenova 未单独声明）')).toBeVisible()
  await expect(page.getByText('本地 Embedding 模型可用').first()).toBeVisible()

  const rebuildResponsePromise = page.waitForResponse(
    (response) => response.url().includes(`/knowledge-bases/${seeded.knowledgeBaseId}/index/rebuild`) && response.request().method() === 'POST',
  )
  page.once('dialog', (dialog) => dialog.accept())
  await page.getByRole('button', { name: '重建当前知识库索引' }).click()
  const rebuildResponse = await rebuildResponsePromise
  expect(rebuildResponse.status()).toBe(202)

  await expect.poll(async () => page.evaluate(async (knowledgeBaseId) => {
    const response = await fetch(`/api/v1/knowledge-bases/${knowledgeBaseId}/index-status`, { cache: 'no-store' })
    const payload = await response.json() as {
      status: string
      active_index_version_status: string | null
      operation_in_progress: boolean
      tasks: Array<{ task_type: string; status: string }>
    }
    return payload.status === 'READY'
      && payload.active_index_version_status === 'READY'
      && payload.operation_in_progress === false
      && payload.tasks.some((task) => task.task_type === 'INDEX_EMBED' && task.status === 'COMPLETED')
  }, seeded.knowledgeBaseId), { timeout: 180_000, intervals: [500, 1000, 2000] }).toBe(true)

  await page.setViewportSize({ width: 390, height: 844 })
  await expect(page.locator('.index-workbench__model-state')).toContainText('本地 Embedding 模型可用')
  const mobile = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    document: document.documentElement.scrollWidth,
  }))
  expect(mobile.document).toBeLessThanOrEqual(mobile.viewport)
  if (evidenceDir) await page.screenshot({ path: `${evidenceDir}/model-index-ready-mobile.png`, fullPage: true })
})

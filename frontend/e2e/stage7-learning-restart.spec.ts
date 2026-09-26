import { execFileSync, spawn } from 'node:child_process'
import { mkdirSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { expect, test, type Page } from '@playwright/test'

const knowledgeBaseId = process.env.STAGE7_REAL_KB_ID
const evidenceDir = process.env.STAGE7_EVIDENCE_DIR
const dataDir = process.env.STAGE7_DATA_DIR
const apiPort = process.env.STAGE7_API_PORT ?? '8001'
const webPort = process.env.MINDMATE_WEB_PORT ?? '5174'
const topic = 'API 单次请求超时时间是多少秒？'
const goal = '记住资料中的唯一超时值'
const unsupportedTopic = '南极冰芯中氮同位素的具体丰度百分比是多少？'
const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..')
const python = path.join(repoRoot, 'backend', '.venv', 'Scripts', 'python.exe')

test.beforeEach(() => {
  test.skip(!knowledgeBaseId || !dataDir, '请先用 scripts/demo.ps1 在隔离数据根准备固定 READY 知识库。')
  const userData = path.join(process.env.LOCALAPPDATA ?? '', 'MindMateAI')
  if (path.resolve(dataDir ?? '').toLowerCase() === path.resolve(userData).toLowerCase()) {
    throw new Error('拒绝使用默认用户数据目录。')
  }
  if (evidenceDir) mkdirSync(evidenceDir, { recursive: true })
})

function listenerPid(port: string) {
  const output = execFileSync('netstat.exe', ['-ano', '-p', 'tcp'], { encoding: 'utf8' })
  const match = output.match(new RegExp(`127\\.0\\.0\\.1:${port}\\s+\\S+\\s+LISTENING\\s+(\\d+)`))
  return match ? Number(match[1]) : null
}

function learningCounts() {
  const database = path.join(dataDir ?? '', 'database', 'mindmate.db')
  const script = [
    'import json, sqlite3, sys',
    'connection = sqlite3.connect(sys.argv[1], timeout=5)',
    'print(json.dumps({',
    '"sessions": connection.execute("select count(*) from learning_sessions").fetchone()[0],',
    '"attempts": connection.execute("select count(*) from learning_attempts").fetchone()[0],',
    '"feedbacks": connection.execute("select count(*) from learning_feedbacks").fetchone()[0],',
    '}))',
  ].join('\n')
  return JSON.parse(execFileSync(python, ['-c', script, database], { encoding: 'utf8' })) as {
    sessions: number
    attempts: number
    feedbacks: number
  }
}

async function healthOk() {
  try {
    const response = await fetch(`http://127.0.0.1:${apiPort}/api/v1/health`)
    if (!response.ok) return false
    const body = await response.json() as { status?: string }
    return body.status === 'ok'
  } catch {
    return false
  }
}

function startBackend() {
  const child = spawn(python, ['-m', 'uvicorn', 'mindmate.main:app', '--host', '127.0.0.1', '--port', apiPort], {
    cwd: path.join(repoRoot, 'backend'),
    env: {
      ...process.env,
      MINDMATE_DATA_DIR: dataDir,
      MINDMATE_PROVIDER_MODE: 'mock',
      MINDMATE_API_PORT: apiPort,
      MINDMATE_ALLOWED_ORIGINS: JSON.stringify([
        `http://127.0.0.1:${webPort}`,
        `http://localhost:${webPort}`,
      ]),
    },
    detached: true,
    stdio: 'ignore',
    windowsHide: true,
  })
  child.unref()
}

async function readSession(page: Page, sessionId: string) {
  const response = await page.request.get(`/api/v1/learning-sessions/${sessionId}`)
  expect(response.ok()).toBe(true)
  return response.json()
}

test('同一学习会话在后端进程重启后保持题目、作答和引用', async ({ page }) => {
  test.setTimeout(240_000)
  await page.goto(`/knowledge-bases/${knowledgeBaseId}`)
  await expect(page.getByText('索引就绪').first()).toBeVisible()
  await page.getByRole('button', { name: '基于此知识库学习' }).click()
  await expect(page.getByText('本地规则模拟演示，未调用真实 DeepSeek。学习出题不读取聊天设置里的在线模式。')).toBeVisible()
  await page.getByRole('textbox', { name: '学习主题' }).fill(topic)
  await page.getByRole('textbox', { name: '学习目标' }).fill(goal)
  const createResponsePromise = page.waitForResponse((response) =>
    response.request().method() === 'POST' && new URL(response.url()).pathname === '/api/v1/learning-sessions',
  )
  await page.getByRole('button', { name: '创建并开始' }).click()
  const created = await (await createResponsePromise).json()
  expect(created.live_model_called).toBe(false)
  expect(created.model).toBe('learning-demo-fixture-v1')
  const sessionUrl = `/learning/session/${created.learning_session_id}`
  await expect(page).toHaveURL(new RegExp(`${sessionUrl}$`))
  const labels = created.question.options.map((option: { label: string }) => option.label)
  await page.getByRole('radio', { name: labels[0] }).check()
  const attemptPromise = page.waitForResponse((response) =>
    response.request().method() === 'POST' && /\/learning-questions\/[^/]+\/attempts$/.test(new URL(response.url()).pathname),
  )
  await page.getByRole('button', { name: '提交答案' }).click()
  const attempt = await (await attemptPromise).json()
  const resultText = attempt.result === 'CORRECT' ? '正确' : '不正确'
  await expect(page.getByLabel('作答反馈')).toContainText(`结果：${resultText}`)
  await expect(page.getByLabel('作答反馈')).toContainText(attempt.explanation)
  const before = learningCounts()
  const oldPid = listenerPid(apiPort)
  expect(oldPid).not.toBeNull()

  execFileSync('taskkill.exe', ['/PID', String(oldPid), '/F'])
  await expect.poll(() => listenerPid(apiPort), { timeout: 20_000 }).toBeNull()
  await expect.poll(healthOk, { timeout: 20_000 }).toBe(false)
  expect(listenerPid(apiPort)).toBeNull()

  await page.goto(sessionUrl)
  await expect(page.getByRole('alert')).toContainText('学习会话暂时读不到')
  await expect(page.getByRole('button', { name: '重新读取' })).toBeVisible()
  await expect(page.getByRole('radio')).toHaveCount(0)

  startBackend()
  await expect.poll(() => listenerPid(apiPort), { timeout: 40_000 }).not.toBeNull()
  const newPid = listenerPid(apiPort)
  expect(newPid).not.toBe(oldPid)
  await expect.poll(healthOk, { timeout: 40_000 }).toBe(true)

  await page.getByRole('button', { name: '重新读取' }).click()
  await expect(page.getByText(created.question.prompt_text)).toBeVisible()
  for (const label of labels) {
    await expect(page.getByRole('radio', { name: label })).toBeVisible()
  }
  await expect(page.getByRole('radio', { name: labels[0] })).toBeChecked()
  await expect(page.getByLabel('作答反馈')).toContainText(`你的答案：${labels[0]}`)
  await expect(page.getByLabel('作答反馈')).toContainText(`结果：${resultText}`)
  await expect(page.getByLabel('作答反馈')).toContainText(attempt.explanation)
  const restored = await readSession(page, created.learning_session_id)
  expect(restored.learning_session_id).toBe(created.learning_session_id)
  expect(restored.question.question_id).toBe(created.question.question_id)
  expect(restored.question.prompt_text).toBe(created.question.prompt_text)
  expect(restored.question.feedback.attempt_id).toBe(attempt.attempt_id)
  expect(restored.question.feedback.selected_option).toBe(attempt.selected_option)
  expect(restored.question.feedback.result).toBe(attempt.result)
  expect(restored.question.feedback.explanation).toBe(attempt.explanation)
  expect(restored.question.feedback.citations[0].file_name).toBe(attempt.citations[0].file_name)
  expect(restored.question.feedback.citations[0].excerpt).toBe(attempt.citations[0].excerpt)
  expect(restored.live_model_called).toBe(false)
  const after = learningCounts()
  expect(after).toEqual(before)

  await page.getByRole('button', { name: `[1] ${attempt.citations[0].file_name}` }).click()
  const source = page.getByRole('complementary', { name: '引用 1' })
  await expect(source).toContainText(attempt.citations[0].file_name)
  await expect(source).toContainText(attempt.citations[0].excerpt)
  await source.getByRole('link', { name: '打开文件详情' }).click()
  await expect(page.getByRole('heading', { name: attempt.citations[0].file_name })).toBeVisible()
  await expect(page.locator('.text-preview')).toContainText('30 秒')
  if (evidenceDir) {
    await page.screenshot({ path: path.join(evidenceDir, 'learning-restart-file.png'), fullPage: true })
  }

  await page.goto(`/learning/new?knowledge_base_id=${knowledgeBaseId}`)
  await page.getByRole('textbox', { name: '学习主题' }).fill(unsupportedTopic)
  await page.getByRole('textbox', { name: '学习目标' }).fill('核对资料不足')
  const refusedPromise = page.waitForResponse((response) =>
    response.request().method() === 'POST' && new URL(response.url()).pathname === '/api/v1/learning-sessions',
  )
  await page.getByRole('button', { name: '创建并开始' }).click()
  const refused = await (await refusedPromise).json()
  expect(refused.status).toBe('FAILED')
  expect(refused.failure_code).toBe('EVIDENCE_INSUFFICIENT')
  expect(refused.question).toBeNull()
  await expect(page.getByRole('radio')).toHaveCount(0)
  await expect(page.getByLabel('作答反馈')).toHaveCount(0)

  if (evidenceDir) {
    writeFileSync(path.join(evidenceDir, 'learning-restart.json'), JSON.stringify({
      old_pid: oldPid,
      new_pid: newPid,
      learning_session_id: created.learning_session_id,
      question_id: created.question.question_id,
      attempt_id: attempt.attempt_id,
      selected_label: labels[0],
      result: attempt.result,
      citation_file: attempt.citations[0].file_name,
      counts_before_restart: before,
      counts_after_restart: after,
      live_model_called: false,
      model: 'learning-demo-fixture-v1',
    }, null, 2))
  }
})

test('演示入口再次打开同一学习会话', async ({ page }) => {
  const sessionId = process.env.STAGE7_SAVED_SESSION_ID
  test.skip(!sessionId || !knowledgeBaseId, '请先完成一题并记下会话 ID。')
  test.setTimeout(120_000)
  await page.goto(`/learning/session/${sessionId}`)
  await expect(page.getByText('本地规则模拟演示，未调用真实 DeepSeek。学习出题不读取聊天设置里的在线模式。')).toBeVisible()
  await expect(page.getByText(topic)).toBeVisible()
  await expect(page.getByLabel('作答反馈')).toContainText('结果：不正确')
  await expect(page.getByRole('button', { name: '[1] 服务超时策略.txt' })).toBeVisible()
  const restored = await readSession(page, sessionId ?? '')
  expect(restored.learning_session_id).toBe(sessionId)
  expect(restored.live_model_called).toBe(false)
  expect(restored.model).toBe('learning-demo-fixture-v1')
  expect(restored.question.feedback.citations[0].file_name).toBe('服务超时策略.txt')
})

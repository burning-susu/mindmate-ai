import { mkdirSync } from 'node:fs'
import { test, expect } from '@playwright/test'
import process from 'node:process'

const knowledgeBaseId = process.env.STAGE5_READY_KB_ID
const expectedIndexVersionId = process.env.STAGE5_READY_INDEX_VERSION_ID
const evidenceDir = process.env.STAGE5_READY_EVIDENCE_DIR
const primaryQuestion = 'API 单次请求超时时间是多少秒？'
const outsideQuestion = '南极冰芯中氮同位素的具体丰度百分比是多少？'
const retrievalPath = `/api/v1/knowledge-bases/${knowledgeBaseId}/retrieval-tests`

async function submitByKeyboard(page: import('@playwright/test').Page, text: string) {
    const question = page.getByRole('textbox', { name: '测试问题' })
    await question.fill(text)
    await question.press('Tab')
    const submit = page.getByRole('button', { name: '测试检索' })
    await expect(submit).toBeFocused()
    await submit.press('Enter')
}

test.beforeEach(() => {
    test.skip(
        !knowledgeBaseId || !expectedIndexVersionId,
        '请先运行固定 READY 样本准备脚本并设置报告中的 ID。',
    )
    if (evidenceDir) mkdirSync(evidenceDir, { recursive: true })
})

test('桌面与窄屏通过真实 API 显示当前 READY 候选', async ({ page }) => {
    const checkViewport = async (width: number, height: number, screenshotName: string) => {
        await page.setViewportSize({ width, height })
        await page.goto(`/knowledge-bases/${knowledgeBaseId}`)
        await expect(page.getByRole('heading', { name: '测试检索' })).toBeVisible()
        await expect(page.getByText('索引就绪').first()).toBeVisible()

        const responsePromise = page.waitForResponse(
            (response) => response.url().includes(retrievalPath) && response.request().method() === 'POST',
        )
        await submitByKeyboard(page, primaryQuestion)
        const response = await responsePromise
        expect(response.status()).toBe(200)
        const payload = await response.json()

        expect(payload.knowledge_base_id).toBe(knowledgeBaseId)
        expect(payload.index_version_id).toBe(expectedIndexVersionId)
        expect(['supported', 'insufficient']).toContain(payload.status)
        expect(payload.candidates.length).toBeGreaterThan(0)
        expect(payload.candidates.length).toBeLessThanOrEqual(8)
        const targetCandidate = payload.candidates.find(
            (candidate: { file_name: string }) => candidate.file_name === '服务超时策略.txt',
        )
        expect(targetCandidate).toBeDefined()
        expect(
            payload.candidates.every(
                (candidate: { file_name: string }) => candidate.file_name === '服务超时策略.txt',
            ),
        ).toBe(true)
        expect(targetCandidate?.excerpt).toContain('30 秒')
        expect(targetCandidate?.location.line_start).not.toBeNull()
        expect(payload).not.toHaveProperty('answer')
        expect(payload).not.toHaveProperty('citations')

        const candidate = page.locator('.retrieval-candidate').filter({ hasText: '服务超时策略.txt' }).first()
        await expect(page.locator('.retrieval-result__titleline')).toContainText(
            payload.status === 'supported' ? '找到可能支持的资料' : '资料不足',
        )
        await expect(candidate).toContainText('30 秒')
        await expect(candidate).toContainText(`行号：${targetCandidate?.location.line_start}`)
        if (evidenceDir) await page.screenshot({ path: `${evidenceDir}/${screenshotName}`, fullPage: true })

        if (width < 500) {
            const hasHorizontalOverflow = await page.evaluate(
                () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
            )
            expect(hasHorizontalOverflow).toBe(false)
        }
    }

    await checkViewport(1440, 1000, 'retrieval-desktop.png')
    await checkViewport(390, 844, 'retrieval-narrow.png')
})

test('资料外问题明确显示资料不足，不产生答案或伪引用', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1000 })
    await page.goto(`/knowledge-bases/${knowledgeBaseId}`)
    const responsePromise = page.waitForResponse(
        (response) => response.url().includes(retrievalPath) && response.request().method() === 'POST',
    )
    await submitByKeyboard(page, outsideQuestion)
    const response = await responsePromise
    expect(response.status()).toBe(200)
    const payload = await response.json()

    expect(payload.status).toBe('insufficient')
    expect(payload.candidates.length).toBeLessThanOrEqual(8)
    expect(
        payload.candidates.every(
            (candidate: { file_name: string }) => candidate.file_name === '服务超时策略.txt',
        ),
    ).toBe(true)
    expect(payload).not.toHaveProperty('answer')
    expect(payload).not.toHaveProperty('citations')
    await expect(page.locator('.retrieval-result__titleline')).toContainText('资料不足')
    await expect(page.locator('.retrieval-result')).not.toContainText('答案：')
    if (evidenceDir)
        await page.screenshot({ path: `${evidenceDir}/retrieval-out-of-scope.png`, fullPage: true })
})

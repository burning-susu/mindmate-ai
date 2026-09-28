import { chromium } from '@playwright/test'
import { createHash } from 'node:crypto'
import { mkdir, readdir, readFile } from 'node:fs/promises'
import { spawnSync } from 'node:child_process'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url))
const frontendDirectory = path.resolve(scriptDirectory, '..')
const repoRoot = path.resolve(frontendDirectory, '..')
const backendDirectory = path.join(repoRoot, 'backend')
const baseUrl = process.env.MINDMATE_BROWSER_BASE_URL || 'http://127.0.0.1:5186'
const dataDirectory = process.env.MINDMATE_BROWSER_DATA_DIR
const artifactDirectory = process.env.MINDMATE_BROWSER_ARTIFACT_DIR
const python = process.env.MINDMATE_BROWSER_PYTHON ||
  path.join(backendDirectory, '.venv', 'Scripts', 'python.exe')

if (!dataDirectory || !artifactDirectory) {
  throw new Error('Set MINDMATE_BROWSER_DATA_DIR and MINDMATE_BROWSER_ARTIFACT_DIR to isolated build directories.')
}

const profileDirectory = path.join(artifactDirectory, 'chrome-profile')
const downloadsDirectory = path.join(artifactDirectory, 'downloads')
const savedDownloadsDirectory = path.join(artifactDirectory, 'verified-downloads')
await mkdir(profileDirectory, { recursive: true })
await mkdir(downloadsDirectory, { recursive: true })
await mkdir(savedDownloadsDirectory, { recursive: true })

const context = await chromium.launchPersistentContext(profileDirectory, {
  channel: 'chrome',
  headless: false,
  acceptDownloads: true,
  downloadsPath: downloadsDirectory,
  viewport: { width: 1440, height: 1000 },
})

try {
  const page = context.pages()[0] || await context.newPage()
  await page.goto(`${baseUrl}/settings`, { waitUntil: 'domcontentloaded' })
  await page.getByRole('heading', { name: '设置' }).waitFor()

  const createResponsePromise = page.waitForResponse((response) =>
    response.url().endsWith('/api/v1/backups') && response.request().method() === 'POST',
  )
  await page.getByRole('button', { name: '创建备份' }).click()
  const createResponse = await createResponsePromise
  if (createResponse.status() !== 202) {
    throw new Error(`Create request returned HTTP ${createResponse.status()}.`)
  }
  const created = await createResponse.json()

  await page.reload({ waitUntil: 'domcontentloaded' })
  const deadline = Date.now() + 90_000
  let backup
  while (Date.now() < deadline) {
    const result = await page.evaluate(async () => {
      const response = await fetch('/api/v1/backups', { cache: 'no-store' })
      if (!response.ok) throw new Error(`Backup list returned HTTP ${response.status}.`)
      return response.json()
    })
    backup = result.items.find((item) => item.backup_id === created.backup_id)
    if (backup?.status === 'COMPLETED' || backup?.status === 'FAILED') break
    await page.waitForTimeout(250)
  }
  if (backup?.status !== 'COMPLETED') {
    throw new Error(`Backup did not complete after refresh (status: ${backup?.status || 'missing'}).`)
  }
  const backupItem = page.locator('.settings-backup-item').first()
  const downloadButton = backupItem.getByRole('button', { name: '下载备份包' })
  await downloadButton.waitFor({ state: 'visible' })
  const uiDeadline = Date.now() + 90_000
  while (Date.now() < uiDeadline) {
    const label = (await backupItem.locator('strong').innerText()).trim()
    if (label === '已完成' && await downloadButton.isEnabled()) break
    await page.waitForTimeout(250)
  }
  const finalLabel = (await backupItem.locator('strong').innerText()).trim()
  if (finalLabel !== '已完成' || !(await downloadButton.isEnabled())) {
    throw new Error(`Latest backup row is not downloadable (status: ${finalLabel}).`)
  }
  await page.screenshot({
    path: path.join(artifactDirectory, 'settings-backup-completed.png'),
    fullPage: true,
  })
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    downloadButton.click(),
  ])
  const downloadedPath = path.join(
    savedDownloadsDirectory,
    `${created.backup_id}-${download.suggestedFilename()}`,
  )
  await download.saveAs(downloadedPath)

  const archiveNames = (await readdir(path.join(dataDirectory, 'backups')))
    .filter((name) => name.endsWith('.mindmate-backup'))
  const sourceName = archiveNames.find((name) => name.includes(created.backup_id))
  if (!sourceName) throw new Error('The server-side archive for the created backup is missing.')
  const sourcePath = path.join(dataDirectory, 'backups', sourceName)
  const sourceHash = createHash('sha256').update(await readFile(sourcePath)).digest('hex')
  const downloadedHash = createHash('sha256').update(await readFile(downloadedPath)).digest('hex')
  if (sourceHash !== downloadedHash) throw new Error('Downloaded bytes differ from the server-side archive.')

  const verifyCode = [
    'import json, sys',
    'from pathlib import Path',
    'from mindmate.application.local_backup import verify_backup_archive',
    'manifest = verify_backup_archive(Path(sys.argv[1]))',
    'print(json.dumps({"file_count": manifest["file_count"], "includes_secrets": manifest["includes_secrets"], "includes_vectors": manifest["includes_vectors"], "verified": True}))',
  ].join('; ')
  const verification = spawnSync(python, ['-c', verifyCode, downloadedPath], {
    cwd: backendDirectory,
    encoding: 'utf8',
    env: {
      ...process.env,
      PYTHONPATH: [path.join(backendDirectory, 'src'), process.env.PYTHONPATH]
        .filter(Boolean)
        .join(path.delimiter),
    },
  })
  if (verification.status !== 0) {
    throw new Error(`Offline archive verification failed: ${verification.stderr || verification.stdout}`)
  }
  const verified = JSON.parse(verification.stdout.trim())
  if (!verified.verified || verified.includes_secrets || verified.includes_vectors) {
    throw new Error('Offline verification returned an unsafe archive manifest.')
  }

  console.log(`BROWSER=Chrome`)
  console.log(`CREATE_HTTP=${createResponse.status()}`)
  console.log(`REFRESH_STATUS=${backup.status}`)
  console.log(`DOWNLOAD=PASS`)
  console.log(`SOURCE_BYTES_MATCH=${sourceHash === downloadedHash}`)
  console.log(`OFFLINE_VERIFY=${JSON.stringify(verified)}`)
} finally {
  await context.close()
}

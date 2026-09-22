import { beforeEach, describe, expect, it, vi } from 'vitest'

describe('stage 4 versioned folder and tag API', () => {
  beforeEach(() => {
    vi.resetModules()
    vi.unstubAllGlobals()
  })

  it('carries row versions for folder and tag mutations and keeps returned versions', async () => {
    const calls: Array<[RequestInfo | URL, RequestInit | undefined]> = []
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      calls.push([input, init])
      const url = String(input)
      if (url.includes('/system/session')) return new Response(JSON.stringify({ status: 'ready' }), { status: 200, headers: { 'Content-Type': 'application/json' } })
      if (url.includes('/folders/folder-1') && init?.method === 'PATCH') return new Response(JSON.stringify({ folder_id: 'folder-1', parent_folder_id: null, name: '新名称', file_count: 0, row_version: 4, created_at: '2026-09-22T00:00:00Z', updated_at: '2026-09-22T00:00:01Z' }), { status: 200, headers: { 'Content-Type': 'application/json' } })
      if (url.includes('/tags/tag-1') && init?.method === 'PATCH') return new Response(JSON.stringify({ tag_id: 'tag-1', name: '重点', color: null, row_version: 6, created_at: '2026-09-22T00:00:00Z', updated_at: '2026-09-22T00:00:01Z' }), { status: 200, headers: { 'Content-Type': 'application/json' } })
      return new Response(JSON.stringify({ status: 'DELETED' }), { status: 200, headers: { 'Content-Type': 'application/json' } })
    }))
    const { deleteFolder, deleteTag, updateFolder, updateTag } = await import('../api/files')

    const updatedFolder = await updateFolder('folder-1', 3, '新名称')
    const updatedTag = await updateTag('tag-1', 5, { color: null })
    await deleteFolder(updatedFolder, 'TRASH_RECURSIVE')
    await deleteTag(updatedTag)

    expect(updatedFolder.row_version).toBe(4)
    expect(updatedTag.row_version).toBe(6)
    expect(JSON.parse(String(calls[1][1]?.body))).toMatchObject({ row_version: 3 })
    expect(JSON.parse(String(calls[2][1]?.body))).toMatchObject({ row_version: 5 })
    expect(String(calls[3][0])).toContain('expected_version=4')
    expect(String(calls[4][0])).toContain('expected_version=6')
  })
})

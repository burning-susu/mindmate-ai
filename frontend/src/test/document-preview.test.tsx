import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import DocumentPreview from '../components/DocumentPreview'

const { apiRequestBlobMock } = vi.hoisted(() => ({ apiRequestBlobMock: vi.fn() }))

vi.mock('../api/client', async (importOriginal) => ({
  ...await importOriginal<typeof import('../api/client')>(),
  apiRequestBlob: apiRequestBlobMock,
}))

describe('DocumentPreview', () => {
  afterEach(() => {
    apiRequestBlobMock.mockReset()
    vi.restoreAllMocks()
    delete (URL as unknown as Record<string, unknown>).createObjectURL
    delete (URL as unknown as Record<string, unknown>).revokeObjectURL
  })

  it('shows the local original PDF layout even when text extraction is unavailable', () => {
    render(<DocumentPreview fileId="pdf-1" documentType="PDF" contentAvailable previewAvailable={false} text="" metadata={null} />)

    expect(screen.getByTitle('PDF 原版式预览')).toHaveAttribute('src', '/api/v1/files/pdf-1/content#navpanes=0&zoom=page-fit')
    expect(screen.getByText(/扫描版文字识别暂不支持/)).toBeInTheDocument()
  })

  it('renders the converted Word PDF and keeps extracted text secondary', async () => {
    const createObjectURL = vi.fn(() => 'blob:docx-preview')
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: createObjectURL })
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() })
    apiRequestBlobMock.mockResolvedValue(new Blob(['%PDF-fixture'], { type: 'application/pdf' }))
    render(<DocumentPreview fileId="docx-1" documentType="DOCX" contentAvailable previewAvailable text={'标题\n正文内容\n项目\t结果\nA\t通过'} metadata={{ paragraph_count: 2, table_count: 1 }} />)

    expect(screen.getByRole('status')).toHaveTextContent('正在转换文档预览')
    expect(await screen.findByTitle('Word 原版式预览')).toHaveAttribute('src', 'blob:docx-preview#navpanes=0&zoom=page-width')
    expect(screen.getByText('Word 文档 · 自动适配预览区域')).toBeInTheDocument()
    expect(screen.getByText('查看提取文本')).toBeInTheDocument()
    expect(screen.queryByRole('cell', { name: '通过' })).not.toBeInTheDocument()
  })

  it('renders the converted PowerPoint PDF and keeps extracted text secondary', async () => {
    const createObjectURL = vi.fn(() => 'blob:pptx-preview')
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: createObjectURL })
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() })
    apiRequestBlobMock.mockResolvedValue(new Blob(['%PDF-fixture'], { type: 'application/pdf' }))
    render(<DocumentPreview fileId="pptx-1" documentType="PPTX" contentAvailable previewAvailable text={'标题\n要点一\n要点二'} metadata={{ slide_count: 2 }} />)

    expect(screen.getByRole('status')).toHaveTextContent('正在转换文档预览')
    expect(await screen.findByTitle('PowerPoint 原版式预览')).toHaveAttribute('src', 'blob:pptx-preview#navpanes=0&zoom=page-fit')
    expect(screen.getByText('共 2 张幻灯片 · 自动适配预览区域')).toBeInTheDocument()
    expect(screen.getByText('查看提取文本')).toBeInTheDocument()
    expect(screen.queryByText('文本块 1')).not.toBeInTheDocument()
  })

  it('shows the conversion error and does not render fake slide cards', async () => {
    apiRequestBlobMock.mockRejectedValue(new Error('LibreOffice 未安装'))
    render(<DocumentPreview fileId="pptx-2" documentType="PPTX" contentAvailable previewAvailable text="辅助文本" metadata={{ slide_count: 1 }} />)

    expect(await screen.findByRole('alert')).toHaveTextContent('无法生成幻灯片版式预览')
    expect(screen.queryByTitle('PowerPoint 原版式预览')).not.toBeInTheDocument()
    expect(screen.getByText('查看提取文本')).toBeInTheDocument()
  })

  it.each([
    ['PPT', 'deck-old', 'PowerPoint 原版式预览', '共 2 张幻灯片 · 自动适配预览区域'],
  ] as const)('renders %s as its converted original-layout PDF', async (documentType, fileId, title, description) => {
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: vi.fn(() => `blob:${documentType}`) })
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() })
    apiRequestBlobMock.mockResolvedValue(new Blob(['%PDF-fixture'], { type: 'application/pdf' }))
    render(<DocumentPreview fileId={fileId} documentType={documentType} contentAvailable previewAvailable text="提取的辅助文本" metadata={{ slide_count: 2, sheet_count: 3 }} />)

    expect(await screen.findByTitle(title)).toHaveAttribute('src', `blob:${documentType}#navpanes=0&zoom=page-fit`)
    expect(screen.getByText(description)).toBeInTheDocument()
    expect(apiRequestBlobMock).toHaveBeenCalledWith(`/api/v1/files/${fileId}/${documentType.toLowerCase()}-preview`, expect.any(Object))
    expect(screen.getByText('查看提取文本')).toBeInTheDocument()
  })

  it('renders XLSX as a sandboxed worksheet and switches sheets', async () => {
    apiRequestBlobMock.mockResolvedValue(new Blob(['<html><body><table></table></body></html>'], { type: 'text/html' }))
    render(<DocumentPreview fileId="xlsx-1" documentType="XLSX" contentAvailable previewAvailable text="A1\tkey" metadata={{ sheet_count: 2, xlsx_sheets: ['翻译表', '术语表'] }} />)

    const frame = await screen.findByTitle('翻译表 Excel 原版式预览')
    expect(frame).toHaveAttribute('src', '/api/v1/files/xlsx-1/xlsx-preview/0')
    expect(frame).toHaveAttribute('sandbox', '')
    expect(screen.getByRole('tab', { name: '翻译表' })).toHaveAttribute('aria-selected', 'true')
    fireEvent.click(screen.getByRole('tab', { name: '术语表' }))

    expect(await screen.findByTitle('术语表 Excel 原版式预览')).toHaveAttribute('src', '/api/v1/files/xlsx-1/xlsx-preview/1')
    expect(apiRequestBlobMock).toHaveBeenCalledWith('/api/v1/files/xlsx-1/xlsx-preview/1', expect.any(Object))
  })

  it('prefers the embedded native XMind preview and falls back to the topic tree', () => {
    const { container } = render(<DocumentPreview fileId="xmind-1" documentType="XMIND" contentAvailable previewAvailable text="root branch leaf" metadata={{ sheet_count: 1, topic_count: 4, xmind_outline: [{ title: '工作计划', root: { title: '年度目标', children: [{ title: '第一季度', children: [{ title: '完成项目', children: [] }] }, { title: '第二季度', children: [] }] } }] }} />)

    expect(screen.getByRole('article', { name: 'XMind 思维导图结构' })).toBeInTheDocument()
    expect(screen.getByText('1 个工作表 · 4 个主题节点')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: '工作计划 XMind 原版式预览' })).toHaveAttribute('src', '/api/v1/files/xmind-1/xmind-thumbnail')
    expect(screen.getByRole('link', { name: '打开原尺寸' })).toHaveAttribute('href', '/api/v1/files/xmind-1/xmind-thumbnail')
    fireEvent.error(screen.getByRole('img', { name: '工作计划 XMind 原版式预览' }))
    expect(screen.getByRole('heading', { level: 3, name: '工作计划' })).toBeInTheDocument()
    expect(screen.getByRole('treeitem', { name: /第一季度/ })).toBeInTheDocument()
    expect(screen.getByText('完成项目')).toBeInTheDocument()
    expect(container.querySelector('.xmind-map__side--left')).toHaveTextContent('第一季度')
    expect(container.querySelector('.xmind-map__side--right')).toHaveTextContent('第二季度')
  })

  it('keeps plain text readable without monospace source styling', () => {
    const { container } = render(<DocumentPreview fileId="txt-1" documentType="TXT" contentAvailable previewAvailable text={'第一段\n第二段'} metadata={null} />)

    expect(container.querySelector('.plain-document-preview')).toHaveTextContent('第一段 第二段')
    expect(container.querySelector('pre')).toBeNull()
  })
})

import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import DocumentPreview from '../components/DocumentPreview'

describe('DocumentPreview', () => {
  it('shows the local original PDF layout even when text extraction is unavailable', () => {
    render(<DocumentPreview fileId="pdf-1" documentType="PDF" contentAvailable previewAvailable={false} text="" metadata={null} />)

    expect(screen.getByTitle('PDF 原版式预览')).toHaveAttribute('src', '/api/v1/files/pdf-1/content#navpanes=0&zoom=100')
    expect(screen.getByText(/扫描版文字识别暂不支持/)).toBeInTheDocument()
  })

  it('formats extracted Word paragraphs and tabular rows for reading', () => {
    render(<DocumentPreview fileId="docx-1" documentType="DOCX" contentAvailable previewAvailable text={'标题\n正文内容\n项目\t结果\nA\t通过'} metadata={{ paragraph_count: 2, table_count: 1 }} />)

    expect(screen.getByLabelText('Word 文档解析内容')).toBeInTheDocument()
    expect(screen.getByText('提取 2 段文字 · 1 个表格')).toBeInTheDocument()
    expect(screen.getByRole('cell', { name: '通过' })).toBeInTheDocument()
  })

  it('labels PowerPoint text as extracted content and shows slide count', () => {
    render(<DocumentPreview fileId="pptx-1" documentType="PPTX" contentAvailable previewAvailable text={'标题\n要点一\n要点二'} metadata={{ slide_count: 2 }} />)

    expect(screen.getByLabelText('PowerPoint 幻灯片解析内容')).toBeInTheDocument()
    expect(screen.getByText('共 2 张幻灯片 · 以下为提取文本块，原始版式请打开原文查看')).toBeInTheDocument()
    expect(screen.getByText('要点二')).toBeInTheDocument()
  })

  it('keeps plain text readable without monospace source styling', () => {
    const { container } = render(<DocumentPreview fileId="txt-1" documentType="TXT" contentAvailable previewAvailable text={'第一段\n第二段'} metadata={null} />)

    expect(container.querySelector('.plain-document-preview')).toHaveTextContent('第一段 第二段')
    expect(container.querySelector('pre')).toBeNull()
  })
})

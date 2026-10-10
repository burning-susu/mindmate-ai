import { FileText } from 'lucide-react'

type ParsedMetadata = {
  page_count?: number
  paragraph_count?: number
  table_count?: number
  slide_count?: number
  line_count?: number
  character_count?: number
}

function WordDocumentPreview({ text, metadata }: { text: string; metadata: ParsedMetadata | null | undefined }) {
  const lines = text.split(/\r?\n/)
  const blocks: Array<{ type: 'paragraph'; text: string } | { type: 'table'; rows: string[][] }> = []
  let tableRows: string[][] = []
  const flushTable = () => {
    if (tableRows.length) blocks.push({ type: 'table', rows: tableRows })
    tableRows = []
  }

  for (const line of lines) {
    if (line.includes('\t')) {
      tableRows.push(line.split('\t'))
    } else {
      flushTable()
      if (line.trim()) blocks.push({ type: 'paragraph', text: line.trim() })
    }
  }
  flushTable()

  return (
    <article className="office-document-preview" aria-label="Word 文档解析内容">
      <div className="office-document-preview__meta">提取 {metadata?.paragraph_count ?? blocks.filter((block) => block.type === 'paragraph').length} 段文字 · {metadata?.table_count ?? tableRows.length} 个表格</div>
      <div className="office-document-preview__page">
        {blocks.map((block, index) => block.type === 'paragraph'
          ? <p key={`paragraph-${index}`}>{block.text}</p>
          : <div className="markdown-table-wrap" key={`table-${index}`}><table><tbody>{block.rows.map((row, rowIndex) => <tr key={`row-${rowIndex}`}>{row.map((cell, cellIndex) => <td key={`cell-${cellIndex}`}>{cell}</td>)}</tr>)}</tbody></table></div>)}
      </div>
    </article>
  )
}

function PowerPointDocumentPreview({ text, metadata }: { text: string; metadata: ParsedMetadata | null | undefined }) {
  const blocks = text.split(/\r?\n/).map((line) => line.trim()).filter(Boolean)
  return (
    <article className="slide-document-preview" aria-label="PowerPoint 幻灯片解析内容">
      <div className="office-document-preview__meta">共 {metadata?.slide_count ?? 0} 张幻灯片 · 以下为提取文本块，原始版式请打开原文查看</div>
      <ol className="slide-document-preview__blocks">{blocks.map((block, index) => <li key={`shape-${index}`}><span>文本块 {index + 1}</span><p>{block}</p></li>)}</ol>
    </article>
  )
}

export default function DocumentPreview({
  fileId,
  documentType,
  contentAvailable,
  previewAvailable,
  text,
  metadata,
}: {
  fileId: string
  documentType: string
  contentAvailable: boolean
  previewAvailable: boolean
  text: string
  metadata: ParsedMetadata | null | undefined
}) {
  if (documentType === 'PDF') {
    return contentAvailable ? (
      <div className="pdf-document-preview" aria-label="PDF 原版式预览">
        <iframe title="PDF 原版式预览" src={`/api/v1/files/${fileId}/content#navpanes=0&zoom=100`} />
        {!previewAvailable ? <p className="document-preview-note"><FileText size={15} aria-hidden="true" />此 PDF 没有可提取的文本，仍可查看原始页面；扫描版文字识别暂不支持。</p> : null}
        {previewAvailable ? <details className="pdf-document-preview__text"><summary>查看提取文本</summary><pre className="text-preview">{text}</pre></details> : null}
      </div>
    ) : <div className="detail-empty"><FileText size={20} aria-hidden="true" /><span>原始 PDF 文件当前不可用。</span></div>
  }

  if (!previewAvailable) return <div className="detail-empty"><FileText size={20} aria-hidden="true" /><span>当前文件还没有可用的解析文本。</span></div>
  if (documentType === 'DOCX') return <WordDocumentPreview text={text} metadata={metadata} />
  if (documentType === 'PPTX') return <PowerPointDocumentPreview text={text} metadata={metadata} />
  return <div className="plain-document-preview">{text}</div>
}

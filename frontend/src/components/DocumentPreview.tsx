import { ExternalLink, FileText, LoaderCircle } from 'lucide-react'
import { useEffect, useState } from 'react'

import { apiRequestBlob, ApiError, LocalBackendUnavailableError } from '../api/client'

type ParsedMetadata = {
  page_count?: number
  paragraph_count?: number
  table_count?: number
  slide_count?: number
  sheet_count?: number
  topic_count?: number
  xmind_outline?: XMindSheet[]
  line_count?: number
  character_count?: number
}

type XMindTopic = { title: string; children: XMindTopic[] }
type XMindSheet = { title: string; root: XMindTopic | null }

function TopicTree({ topics, nested = false }: { topics: XMindTopic[]; nested?: boolean }) {
  if (topics.length === 0) return null
  return <ul role={nested ? 'group' : 'tree'}>{topics.map((topic, index) => <li role="treeitem" aria-expanded={topic.children.length ? true : undefined} key={`${topic.title}-${index}`}><span>{topic.title}</span><TopicTree topics={topic.children} nested /></li>)}</ul>
}

function XMindBranches({ topics }: { topics: XMindTopic[] }) {
  if (topics.length === 0) return <div className="xmind-map__empty-side" aria-hidden="true" />
  return (
    <div className="xmind-map__branch-list" role="group">
      {topics.map((topic, index) => (
        <div className="xmind-map__branch" role="treeitem" aria-expanded={topic.children.length ? true : undefined} key={`${topic.title}-${index}`}>
          <span>{topic.title}</span>
          <TopicTree topics={topic.children} nested />
        </div>
      ))}
    </div>
  )
}

function XMindDocumentPreview({ fileId, metadata }: { fileId: string; metadata: ParsedMetadata | null | undefined }) {
  const [thumbnailUnavailable, setThumbnailUnavailable] = useState(false)
  const sheets = metadata?.xmind_outline ?? []
  const thumbnailUrl = `/api/v1/files/${fileId}/xmind-thumbnail`
  return (
    <article className="xmind-document-preview" aria-label="XMind 思维导图结构">
      <div className="office-document-preview__meta">{metadata?.sheet_count ?? sheets.length} 个工作表 · {metadata?.topic_count ?? 0} 个主题节点</div>
      {!thumbnailUnavailable && sheets.length > 0 ? (
        <>
          <div className="xmind-native-preview__actions"><a className="quiet-button" href={thumbnailUrl} target="_blank" rel="noreferrer"><ExternalLink size={15} aria-hidden="true" />打开原尺寸</a></div>
          <div className="xmind-native-preview">
            <img src={thumbnailUrl} alt={`${sheets[0].title} XMind 原版式预览`} onError={() => setThumbnailUnavailable(true)} />
          </div>
        </>
      ) : <div className="xmind-document-preview__sheets">
        {sheets.map((sheet, index) => (
          <section key={`${sheet.title}-${index}`} aria-labelledby={`xmind-sheet-${index}`}>
            <h3 id={`xmind-sheet-${index}`}>{sheet.title}</h3>
            {sheet.root ? (
              <div className="xmind-map-scroll">
                <div className="xmind-map" role="tree" aria-label={sheet.title}>
                  <div className="xmind-map__side xmind-map__side--left"><XMindBranches topics={sheet.root.children.filter((_, branchIndex) => branchIndex % 2 === 0)} /></div>
                  <strong className="xmind-map__root" role="treeitem" aria-expanded={sheet.root.children.length > 0 || undefined}>{sheet.root.title}</strong>
                  <div className="xmind-map__side xmind-map__side--right"><XMindBranches topics={sheet.root.children.filter((_, branchIndex) => branchIndex % 2 === 1)} /></div>
                </div>
              </div>
            ) : <p>此工作表没有可显示的主题。</p>}
          </section>
        ))}
      </div>}
    </article>
  )
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

function PowerPointDocumentPreview({ fileId, text, metadata }: { fileId: string; text: string; metadata: ParsedMetadata | null | undefined }) {
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    let active = true
    let objectUrl: string | null = null
    void apiRequestBlob(`/api/v1/files/${fileId}/pptx-preview`, { signal: controller.signal })
      .then((blob) => {
        if (!active) return
        objectUrl = URL.createObjectURL(blob)
        setPreviewUrl(objectUrl)
      })
      .catch((reason: unknown) => {
        if (!active) return
        if (reason instanceof ApiError) setError(reason.problem.detail)
        else if (reason instanceof LocalBackendUnavailableError) setError(reason.message)
        else setError('无法生成幻灯片版式预览，请打开原文查看。')
      })
    return () => {
      active = false
      controller.abort()
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [fileId])

  return (
    <article className="slide-document-preview" aria-label="PowerPoint 幻灯片原版式预览">
      <div className="office-document-preview__meta">共 {metadata?.slide_count ?? 0} 张幻灯片 · 本地转换为 PDF 预览</div>
      {previewUrl ? <iframe title="PowerPoint 原版式预览" src={`${previewUrl}#navpanes=0&zoom=100`} />
        : error ? <div className="detail-empty" role="alert"><FileText size={18} aria-hidden="true" /><span>{error}</span></div>
          : <div className="detail-empty" role="status"><LoaderCircle size={18} className="spin" aria-hidden="true" /><span>正在转换幻灯片预览…</span></div>}
      {text ? <details className="pdf-document-preview__text"><summary>查看提取文本</summary><pre className="text-preview">{text}</pre></details> : null}
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

  if (documentType === 'PPTX') return <PowerPointDocumentPreview key={fileId} fileId={fileId} text={text} metadata={metadata} />
  if (!previewAvailable) return <div className="detail-empty"><FileText size={20} aria-hidden="true" /><span>当前文件还没有可用的解析文本。</span></div>
  if (documentType === 'DOCX') return <WordDocumentPreview text={text} metadata={metadata} />
  if (documentType === 'XMIND') return metadata?.xmind_outline ? <XMindDocumentPreview fileId={fileId} metadata={metadata} /> : <div className="detail-empty"><FileText size={20} aria-hidden="true" /><span>XMind 主题结构无法读取。</span></div>
  return <div className="plain-document-preview">{text}</div>
}

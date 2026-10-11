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
  xlsx_sheets?: string[]
  xmind_outline?: XMindSheet[]
  line_count?: number
  character_count?: number
}

type XMindTopic = { title: string; children: XMindTopic[] }
type XMindSheet = { title: string; root: XMindTopic | null }

function getOfficePdfZoom(documentType: 'DOCX' | 'PPT' | 'PPTX') {
  return documentType === 'DOCX' ? 'page-width' : 'page-fit'
}

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

function OfficeDocumentPreview({ fileId, text, metadata, documentType }: { fileId: string; text: string; metadata: ParsedMetadata | null | undefined; documentType: 'DOCX' | 'PPT' | 'PPTX' }) {
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const isPresentation = documentType === 'PPT' || documentType === 'PPTX'
  const previewTitle = documentType === 'DOCX' ? 'Word 原版式预览' : isPresentation ? 'PowerPoint 原版式预览' : 'Excel 原版式预览'
  const previewPath = `/api/v1/files/${fileId}/${documentType.toLowerCase()}-preview`
  const previewDescription = documentType === 'DOCX' ? 'Word 文档' : isPresentation ? `共 ${metadata?.slide_count ?? 0} 张幻灯片` : `共 ${metadata?.sheet_count ?? 0} 个工作表`
  const zoomMode = getOfficePdfZoom(documentType)

  useEffect(() => {
    const controller = new AbortController()
    let active = true
    let objectUrl: string | null = null
    void apiRequestBlob(previewPath, { signal: controller.signal })
      .then((blob) => {
        if (!active) return
        objectUrl = URL.createObjectURL(blob)
        setPreviewUrl(objectUrl)
      })
      .catch((reason: unknown) => {
        if (!active) return
        if (reason instanceof ApiError) setError(reason.problem.detail)
        else if (reason instanceof LocalBackendUnavailableError) setError(reason.message)
        else setError(`无法生成${isPresentation ? '幻灯片' : 'Word'}版式预览，请打开原文查看。`)
      })
    return () => {
      active = false
      controller.abort()
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [documentType, fileId, isPresentation, previewPath])

  return (
    <article className="office-layout-preview" aria-label={previewTitle}>
      <div className="office-document-preview__meta">{previewDescription} · 自动适配预览区域</div>
      {previewUrl ? <iframe title={previewTitle} src={`${previewUrl}#navpanes=0&zoom=${zoomMode}`} />
        : error ? <div className="detail-empty" role="alert"><FileText size={18} aria-hidden="true" /><span>{error}</span></div>
          : <div className="detail-empty" role="status"><LoaderCircle size={18} className="spin" aria-hidden="true" /><span>正在转换文档预览…</span></div>}
      {text ? <details className="pdf-document-preview__text"><summary>查看提取文本</summary><pre className="text-preview">{text}</pre></details> : null}
    </article>
  )
}

function XlsxSheetFrame({ fileId, sheetIndex, sheetName }: { fileId: string; sheetIndex: number; sheetName: string }) {
  const [previewReady, setPreviewReady] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const previewPath = `/api/v1/files/${fileId}/xlsx-preview/${sheetIndex}`

  useEffect(() => {
    const controller = new AbortController()
    let active = true
    void apiRequestBlob(previewPath, { signal: controller.signal })
      .then(() => {
        if (active) setPreviewReady(true)
      })
      .catch((reason: unknown) => {
        if (!active) return
        if (reason instanceof ApiError) setError(reason.problem.detail)
        else if (reason instanceof LocalBackendUnavailableError) setError(reason.message)
        else setError('无法生成工作表预览，请打开原文件查看。')
      })
    return () => {
      active = false
      controller.abort()
    }
  }, [previewPath])

  if (previewReady) return <iframe title={`${sheetName} Excel 原版式预览`} src={previewPath} sandbox="" referrerPolicy="no-referrer" />
  if (error) return <div className="detail-empty" role="alert"><FileText size={18} aria-hidden="true" /><span>{error}</span></div>
  return <div className="detail-empty" role="status"><LoaderCircle size={18} className="spin" aria-hidden="true" /><span>正在读取工作表…</span></div>
}

function XlsxDocumentPreview({ fileId, text, metadata }: { fileId: string; text: string; metadata: ParsedMetadata | null | undefined }) {
  const sheetCount = Math.max(1, metadata?.sheet_count ?? 1)
  const sheets = metadata?.xlsx_sheets?.length
    ? metadata.xlsx_sheets
    : Array.from({ length: sheetCount }, (_, index) => `工作表 ${index + 1}`)
  const [activeSheet, setActiveSheet] = useState(0)

  return <article className="office-layout-preview xlsx-layout-preview" aria-label="Excel 工作表预览">
    <div className="office-document-preview__meta">{sheets.length} 个工作表 · 保留单元格布局预览</div>
    {sheets.length > 1 && <div className="xlsx-sheet-tabs" role="tablist" aria-label="工作表">
      {sheets.map((sheet, index) => <button type="button" role="tab" aria-selected={activeSheet === index} key={`${sheet}-${index}`} onClick={() => setActiveSheet(index)}>{sheet}</button>)}
    </div>}
    <XlsxSheetFrame key={`${fileId}-${activeSheet}`} fileId={fileId} sheetIndex={activeSheet} sheetName={sheets[activeSheet] ?? '工作表'} />
    {text ? <details className="pdf-document-preview__text"><summary>查看提取文本</summary><pre className="text-preview">{text}</pre></details> : null}
  </article>
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
        <iframe title="PDF 原版式预览" src={`/api/v1/files/${fileId}/content#navpanes=0&zoom=page-fit`} />
        {!previewAvailable ? <p className="document-preview-note"><FileText size={15} aria-hidden="true" />此 PDF 没有可提取的文本，仍可查看原始页面；扫描版文字识别暂不支持。</p> : null}
        {previewAvailable ? <details className="pdf-document-preview__text"><summary>查看提取文本</summary><pre className="text-preview">{text}</pre></details> : null}
      </div>
    ) : <div className="detail-empty"><FileText size={20} aria-hidden="true" /><span>原始 PDF 文件当前不可用。</span></div>
  }

  if (documentType === 'XLSX') return <XlsxDocumentPreview key={`${fileId}-${documentType}`} fileId={fileId} text={text} metadata={metadata} />
  if (documentType === 'DOCX' || documentType === 'PPT' || documentType === 'PPTX') return <OfficeDocumentPreview key={`${fileId}-${documentType}`} fileId={fileId} text={text} metadata={metadata} documentType={documentType} />
  if (!previewAvailable) return <div className="detail-empty"><FileText size={20} aria-hidden="true" /><span>当前文件还没有可用的解析文本。</span></div>
  if (documentType === 'XMIND') return metadata?.xmind_outline ? <XMindDocumentPreview fileId={fileId} metadata={metadata} /> : <div className="detail-empty"><FileText size={20} aria-hidden="true" /><span>XMind 主题结构无法读取。</span></div>
  return <div className="plain-document-preview">{text}</div>
}

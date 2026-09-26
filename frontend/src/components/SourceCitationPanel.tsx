import { ExternalLink, FileText, X } from 'lucide-react'

import { sourceStatusLabel } from './sourceStatus'

export type SourceCitationView = {
  display_number: number
  file_name: string
  file_id?: string | null
  excerpt?: string | null
  source_status: string
  can_open_source: boolean
  heading_path?: string[] | null
  page_start?: number | null
  page_end?: number | null
  slide_number?: number | null
  line_start?: number | null
  line_end?: number | null
}

function citationLocation(citation: SourceCitationView): string {
  const location: string[] = []
  if (citation.heading_path?.length) location.push(citation.heading_path.join(' / '))
  if (citation.page_start) location.push(`第 ${citation.page_start}${citation.page_end && citation.page_end !== citation.page_start ? `-${citation.page_end}` : ''} 页`)
  if (citation.slide_number) location.push(`第 ${citation.slide_number} 张`)
  if (citation.line_start) location.push(`第 ${citation.line_start}${citation.line_end && citation.line_end !== citation.line_start ? `-${citation.line_end}` : ''} 行`)
  return location.join(' · ') || '未提供结构定位'
}

export function CitedText({
  text,
  citations,
  onCitation,
}: {
  text: string
  citations: SourceCitationView[]
  onCitation: (citation: SourceCitationView) => void
}) {
  const citationByNumber = new Map(citations.map((citation) => [citation.display_number, citation]))
  return (
    <>
      {text.split(/(\[\d+\])/g).map((part, partIndex) => {
        const match = part.match(/^\[(\d+)\]$/)
        const citation = match ? citationByNumber.get(Number(match[1])) : undefined
        return citation ? (
          <button className="citation-link" type="button" key={`${part}-${partIndex}`} onClick={() => onCitation(citation)} aria-label={`打开引用 ${citation.display_number}`}>[{citation.display_number}]</button>
        ) : (
          <span key={`${part}-${partIndex}`}>{part}</span>
        )
      })}
    </>
  )
}

export function SourceCitationPanel({ citation, onClose }: { citation: SourceCitationView; onClose: () => void }) {
  const unavailable = citation.source_status !== 'AVAILABLE'
  return (
    <aside className="citation-panel" aria-label={`引用 ${citation.display_number}`}>
      <div className="citation-panel__header">
        <div>
          <span className="eyebrow">引用 {citation.display_number}</span>
          <strong>{citation.file_name}</strong>
        </div>
        <button className="icon-button" type="button" onClick={onClose} aria-label="关闭引用"><X size={16} /></button>
      </div>
      <div className="citation-panel__location"><FileText size={14} aria-hidden="true" />{citationLocation(citation)}</div>
      {unavailable ? (
        <p className="citation-panel__unavailable">来源状态：{sourceStatusLabel(citation.source_status)}。历史摘录不能当作当前资料仍可用。</p>
      ) : null}
      {citation.excerpt ? (
        <p className="citation-panel__excerpt">{unavailable ? `历史摘录：${citation.excerpt}` : citation.excerpt}</p>
      ) : unavailable ? null : (
        <p className="citation-panel__excerpt">当前来源没有可展示摘录。</p>
      )}
      {citation.can_open_source && citation.file_id ? (
        <a className="quiet-button citation-panel__open" href={`/files/${citation.file_id}`}><ExternalLink size={14} />打开文件详情</a>
      ) : null}
    </aside>
  )
}

import { AlertCircle, CheckCircle2, LoaderCircle, RefreshCw, Search, ShieldAlert } from 'lucide-react'
import { type FormEvent, useEffect, useRef, useState } from 'react'

import {
  runKnowledgeBaseRetrievalTest,
  type KnowledgeBaseItem,
  type RetrievalTestCandidate,
  type RetrievalTestLocation,
  type RetrievalTestResponse,
} from '../api/knowledgeBases'

const statusMeta = {
  supported: {
    label: '找到可能支持的资料',
    className: 'supported',
    description: '这些候选资料通过了本地证据门控，可继续由后续流程处理。它们不是回答或正式引用。',
  },
  insufficient: {
    label: '资料不足',
    className: 'insufficient',
    description: '当前候选资料不足以支持这个问题，请缩小问题范围或补充资料。',
  },
  unavailable: {
    label: '检索暂不可用',
    className: 'unavailable',
    description: '本地服务或索引暂时不可用，请根据下面的信号处理后重试。',
  },
} as const

const reasonLabels: Record<string, string> = {
  SUPPORTING_CANDIDATE_FOUND: '候选资料通过证据门控',
  EMPTY_RESULTS: '没有召回候选资料',
  RETRIEVAL_CHANNEL_FAILED: '检索通道失败',
  VECTOR_ROUTE_NOT_REQUESTED: '向量通道未参与',
  TITLE_ONLY_MATCH: '命中只出现在标题',
  NUMERIC_ANSWER_VALUE_NOT_FOUND: '未找到问题中的数值内容',
  VECTOR_SIMILARITY_BELOW_THRESHOLD: '向量相似度低于阈值',
  BODY_ANCHOR_COVERAGE_LOW: '正文锚点覆盖不足',
  TOP_K_CONTRACT_VIOLATION: '候选数量不符合检索约束',
  INDEX_VERSION_NOT_AVAILABLE: '没有活动 READY 索引',
  MODEL_MISSING_OFFLINE: '本地模型不可用，未下载新模型',
  EMBEDDING_CONFIG_UNVERIFIED: 'Embedding 配置未通过校验',
  FTS_INDEX_NOT_READY: '关键词索引尚未就绪',
  VECTOR_INDEX_NOT_READY: '向量索引尚未就绪',
  RETRIEVAL_SCOPE_CHANGED: '检索范围在请求期间发生变化',
}

const sourceKindLabels: Record<string, string> = {
  pdf_page: 'PDF 页',
  pptx_slide: 'PPTX 幻灯片',
  txt_line: '文本行',
  markdown_line: 'Markdown 行',
  docx_block: 'DOCX 结构块',
}

const rankingReasonLabels: Record<string, string> = {
  RRF_FTS: '关键词通道参与融合',
  RRF_VECTOR: '向量通道参与融合',
  EXACT_PHRASE: '完整短语命中',
  EXACT_TERM: '完整词项命中',
  same_file: '同文件候选受到轻微多样性调整',
}

function formatScore(value: number | null | undefined) {
  return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(6) : '无'
}

function formatRank(value: number | null | undefined) {
  return typeof value === 'number' && value > 0 ? String(value) : '无'
}

function formatRange(start: number | null | undefined, end: number | null | undefined, unit: string) {
  const validStart = typeof start === 'number' && start > 0 ? start : null
  const validEnd = typeof end === 'number' && end > 0 ? end : null
  if (validStart === null && validEnd === null) return '无'
  if (validStart !== null && validEnd !== null && validStart !== validEnd) return `${validStart}-${validEnd}${unit}`
  return `${validStart ?? validEnd}${unit}`
}

function locationSignals(location: RetrievalTestLocation) {
  const signals: string[] = []
  if (location.heading_path.length > 0) signals.push(`标题：${location.heading_path.join(' / ')}`)
  const page = formatRange(location.page_start, location.page_end, ' 页')
  if (page !== '无') signals.push(`页码：${page}`)
  if (typeof location.slide_number === 'number' && location.slide_number > 0) signals.push(`幻灯片：${location.slide_number}`)
  const line = formatRange(location.line_start, location.line_end, ' 行')
  if (line !== '无') signals.push(`行号：${line}`)
  if (typeof location.source_kind === 'string' && location.source_kind.trim()) {
    signals.push(`来源：${sourceKindLabels[location.source_kind] ?? location.source_kind}`)
  }
  if (location.sequence_number > 0) signals.push(`片段序号：${location.sequence_number}`)
  return signals.length > 0 ? signals : ['定位：无']
}

function reasonLabel(reason: string) {
  if (reasonLabels[reason]) return reasonLabels[reason]
  if (reason.startsWith('PARTIAL')) return '部分资料可用'
  return reason
}

function rankingReasonLabel(reason: string) {
  if (rankingReasonLabels[reason]) return rankingReasonLabels[reason]
  if (reason.startsWith('adjacent_overlap:')) return '相邻内容重叠受到轻微调整'
  return reason
}

function unavailableMessage(response: RetrievalTestResponse) {
  const code = response.retrieval_error_code
  if (code === 'INDEX_VERSION_NOT_AVAILABLE') return '当前知识库没有活动 READY 索引，完成索引后再试。'
  if (code === 'MODEL_MISSING_OFFLINE') return '本地 Embedding 模型不可用；本次请求没有触发下载。'
  if (code === 'EMBEDDING_CONFIG_UNVERIFIED') return '当前 Embedding 配置未通过校验，暂不能开始检索。'
  if (code === 'FTS_INDEX_NOT_READY') return '关键词索引尚未就绪，请等待索引完成后重试。'
  if (code === 'VECTOR_INDEX_NOT_READY') return '向量索引尚未就绪，请等待索引完成后重试。'
  if (code === 'RETRIEVAL_SCOPE_CHANGED') return '知识库成员或活动索引在检索期间发生变化，请重新提交问题。'
  if (code === 'FTS_QUERY_FAILED' || code === 'VECTOR_DATABASE_UNAVAILABLE') return '本地检索通道发生故障，请稍后重试。'
  return response.local_message ?? '本地服务或索引不可用，请稍后重试。'
}

function requestErrorMessage(error: unknown) {
  return error instanceof Error && error.message ? error.message : '检索请求失败，请重试。'
}

function RetrievalCandidate({ candidate }: { candidate: RetrievalTestCandidate }) {
  const channels = [
    candidate.fts_rank !== null || candidate.bm25 !== null
      ? `关键词通道：rank ${formatRank(candidate.fts_rank)} · BM25 ${formatScore(candidate.bm25)}`
      : null,
    candidate.vector_rank !== null || candidate.cosine_similarity !== null || candidate.cosine_distance !== null
      ? `向量通道：rank ${formatRank(candidate.vector_rank)} · 余弦相似度 ${formatScore(candidate.cosine_similarity)} · 距离 ${formatScore(candidate.cosine_distance)}`
      : null,
  ].filter((item): item is string => item !== null)

  return <article className="retrieval-candidate">
    <div className="retrieval-candidate__header">
      <div className="retrieval-candidate__title">
        <span className="retrieval-rank">最终排名 {formatRank(candidate.rank)}</span>
        <h3>{candidate.file_name || '未命名文件'}</h3>
      </div>
      <span className="retrieval-candidate__id">文件来源 {candidate.file_id}</span>
    </div>
    <div className="retrieval-location" aria-label="来源位置">
      {locationSignals(candidate.location).map((signal) => <span key={signal}>{signal}</span>)}
    </div>
    <p className="retrieval-excerpt">{candidate.excerpt || '无'}</p>
    <div className="retrieval-metrics">
      <div><span>通道信号</span><strong>{channels.length > 0 ? channels.join('；') : '无'}</strong></div>
      <div><span>融合排序分数</span><strong>{formatScore(candidate.rrf_score)}</strong></div>
      <div><span>最终排序分数</span><strong>{formatScore(candidate.ranking_score)}</strong></div>
      <div><span>精确匹配加成</span><strong>{formatScore(candidate.exact_match_bonus)}</strong></div>
      <div><span>多样性调整</span><strong>{formatScore(candidate.diversity_adjustment)}</strong></div>
    </div>
    {(candidate.exact_match_fields.length > 0 || candidate.ranking_reasons.length > 0) && <div className="retrieval-explanations">
      {candidate.exact_match_fields.length > 0 && <div><span>精确命中</span><p>{candidate.exact_match_fields.join('、')}</p></div>}
      {candidate.ranking_reasons.length > 0 && <div><span>排序说明</span><p>{candidate.ranking_reasons.map(rankingReasonLabel).join('；')}</p></div>}
    </div>}
  </article>
}

function RetrievalResult({ response, onRetry }: { response: RetrievalTestResponse; onRetry: () => void }) {
  const meta = statusMeta[response.status]
  const candidates = response.candidates.slice(0, 8)
  const statusDescription = response.status === 'unavailable'
    ? unavailableMessage(response)
    : response.local_message ?? meta.description

  return <div className={`retrieval-result retrieval-result--${meta.className}`}>
    <div className="retrieval-result__summary" role="status" aria-live="polite">
      <div className="retrieval-result__titleline">
        {response.status === 'supported' ? <CheckCircle2 size={18} aria-hidden="true" /> : response.status === 'unavailable' ? <ShieldAlert size={18} aria-hidden="true" /> : <AlertCircle size={18} aria-hidden="true" />}
        <strong>{meta.label}</strong>
      </div>
      <p>{statusDescription}</p>
      {response.status === 'unavailable' && <button className="quiet-button" type="button" onClick={onRetry}><RefreshCw size={15} aria-hidden="true" />重新检索</button>}
    </div>

    <dl className="retrieval-signal-grid">
      <div><dt>活动索引</dt><dd>{response.index_version_id ? 'READY 版本' : '无'}</dd></div>
      <div><dt>候选资料</dt><dd>{candidates.length > 0 ? `${candidates.length} / ${response.final_candidate_limit}` : '无'}</dd></div>
      <div><dt>不同来源</dt><dd>{response.distinct_source_count > 0 ? response.distinct_source_count : '无'}</dd></div>
      <div><dt>问题类型</dt><dd>{response.question_type || '无'}</dd></div>
      <div><dt>排序规则</dt><dd>{response.ranking_algorithm_version || '无'}</dd></div>
      <div><dt>证据规则</dt><dd>{response.evidence_rules_version || '无'}</dd></div>
    </dl>

    {response.reason_codes.length > 0 && <div className="retrieval-reasons"><h3>检索信号</h3><ul>{response.reason_codes.map((reason) => <li key={reason}>{reasonLabel(reason)}</li>)}</ul></div>}
    {response.suggestions.length > 0 && <div className="retrieval-suggestions"><h3>处理建议</h3><ul>{response.suggestions.map((suggestion) => <li key={suggestion}>{suggestion}</li>)}</ul></div>}

    {candidates.length > 0 ? <div className="retrieval-candidates"><div className="retrieval-candidates__heading"><h3>候选资料</h3><span>最多展示 8 条</span></div>{candidates.map((candidate) => <RetrievalCandidate candidate={candidate} key={candidate.chunk_id} />)}</div> : <div className="retrieval-empty"><strong>{response.status === 'insufficient' ? '没有可展示的候选资料' : '当前没有可展示的候选资料'}</strong><span>{response.status === 'insufficient' ? '检索结果为空或证据不足，页面不会将其转换为回答。' : '请根据上面的检索信号处理索引或服务状态。'}</span></div>}
  </div>
}

export default function KnowledgeBaseRetrievalPanel({ item }: { item: KnowledgeBaseItem }) {
  const [question, setQuestion] = useState('')
  const [pending, setPending] = useState(false)
  const [result, setResult] = useState<RetrievalTestResponse | null>(null)
  const [error, setError] = useState<unknown>(null)
  const requestSequence = useRef(0)
  const abortController = useRef<AbortController | null>(null)

  useEffect(() => () => {
    requestSequence.current += 1
    abortController.current?.abort()
    abortController.current = null
  }, [])

  const invalidateCurrentRequest = () => {
    requestSequence.current += 1
    abortController.current?.abort()
    abortController.current = null
    setPending(false)
    setResult(null)
    setError(null)
  }

  const submitQuestion = (event?: FormEvent) => {
    event?.preventDefault()
    const normalizedQuestion = question.trim()
    if (!normalizedQuestion || pending) return

    abortController.current?.abort()
    const controller = new AbortController()
    abortController.current = controller
    const sequence = requestSequence.current + 1
    requestSequence.current = sequence
    setPending(true)
    setResult(null)
    setError(null)

    void runKnowledgeBaseRetrievalTest(item.knowledge_base_id, { question: normalizedQuestion }, controller.signal)
      .then((response) => {
        if (sequence !== requestSequence.current) return
        setResult(response)
      })
      .catch((requestError: unknown) => {
        if (sequence !== requestSequence.current || (requestError instanceof DOMException && requestError.name === 'AbortError')) return
        setError(requestError)
      })
      .finally(() => {
        if (sequence !== requestSequence.current) return
        abortController.current = null
        setPending(false)
      })
  }

  const statusLabel = item.status === 'READY' ? '索引就绪' : item.status === 'PARTIAL' ? '部分资料可用' : item.status === 'PREPARING' ? '成员待索引' : item.status === 'EMPTY' ? '索引待开放' : item.status
  const fileSummary = item.file_count > 0 && item.available_file_count < item.file_count
    ? `当前 ${item.available_file_count} / ${item.file_count} 个文件可用于检索。`
    : item.file_count > 0 ? `${item.file_count} 个文件处于当前知识库范围。` : '当前知识库还没有成员文件。'

  return <section className="detail-section retrieval-panel" aria-labelledby="retrieval-test-heading">
    <div className="section-heading"><div><h2 id="retrieval-test-heading">测试检索</h2><p>高级诊断工具：只查看本地候选和检索信号，不生成回答或正式引用。</p></div><span className={`file-status ${item.status === 'READY' ? 'file-status--ready' : item.status === 'PARTIAL' ? 'file-status--parsed' : 'file-status--queued'}`}>{statusLabel}</span></div>
    <p className="retrieval-scope-note">{fileSummary}</p>
    <form className="retrieval-form" onSubmit={submitQuestion}>
      <label htmlFor="retrieval-question">测试问题</label>
      <textarea id="retrieval-question" value={question} maxLength={2000} rows={4} placeholder="输入一个要在当前知识库中查找的问题" onChange={(event) => { setQuestion(event.target.value); invalidateCurrentRequest() }} />
      <div className="retrieval-form__footer"><span>{question.length} / 2000</span><button className="primary-button" type="submit" disabled={pending || !question.trim()}>{pending ? <LoaderCircle size={16} aria-hidden="true" className="spin" /> : <Search size={16} aria-hidden="true" />}{pending ? '正在检索' : '测试检索'}</button></div>
    </form>
    {pending && <div className="retrieval-loading" role="status" aria-live="polite"><LoaderCircle size={17} aria-hidden="true" className="spin" />正在查询当前活动索引…</div>}
    {error !== null && <div className="inline-error retrieval-error" role="alert"><AlertCircle size={16} aria-hidden="true" /><span>{requestErrorMessage(error)}</span><button className="quiet-button" type="button" onClick={() => submitQuestion()} disabled={pending}><RefreshCw size={14} aria-hidden="true" />重试</button></div>}
    {result && <RetrievalResult response={result} onRetry={() => submitQuestion()} />}
  </section>
}

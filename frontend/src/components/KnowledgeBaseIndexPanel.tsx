import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, Check, Download, LoaderCircle, RefreshCw, RotateCcw, X } from 'lucide-react'

import {
  cancelKnowledgeBaseTask,
  getEmbeddingModelStatus,
  getKnowledgeBaseIndexStatus,
  installEmbeddingModel,
  rebuildKnowledgeBaseIndex,
  retryFailedIndexFiles,
  type EmbeddingModelStatus,
  type KnowledgeBaseIndexStatus,
  type KnowledgeBaseItem,
} from '../api/knowledgeBases'

const activeTaskStates = new Set(['QUEUED', 'RUNNING', 'INTERRUPTED'])

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    EMPTY: '空知识库',
    PREPARING: '正在准备索引',
    PARTIAL: '部分资料可用',
    READY: '索引就绪',
    FAILED: '索引失败',
    NEEDS_REBUILD: '需要重建',
  }
  return labels[status] ?? status
}

function taskTypeLabel(taskType: string) {
  const labels: Record<string, string> = {
    INDEX_PREPROCESS: '准备文件',
    INDEX_CHUNK: '生成切片',
    INDEX_EMBED: '生成向量',
    INDEX_FTS: '建立关键词索引',
  }
  return labels[taskType] ?? taskType
}

function modelStateLabel(status: string) {
  if (status === 'READY') return '本地 Embedding 模型可用'
  if (status === 'MISSING') return '本地 Embedding 模型尚未安装'
  if (status === 'MISSING_OFFLINE') return '离线且本地模型尚未安装'
  if (status === 'QUEUED') return '模型安装任务等待开始'
  if (status === 'RECOVERING' || status === 'PREPARING') return '正在恢复模型安装'
  if (status === 'DOWNLOADING') return '正在下载本地模型'
  if (status === 'VERIFYING') return '正在校验本地模型'
  if (status === 'CANCELLED') return '模型安装已取消'
  if (status === 'FAILED') return '模型安装失败'
  if (status === 'CORRUPT') return '本地 Embedding 模型校验失败'
  return '本地 Embedding 模型状态未知'
}

function formatBytes(value: number) {
  return `${new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 1 }).format(value / 1024 / 1024)} MiB`
}

function modelTaskActive(status: EmbeddingModelStatus | undefined) {
  return Boolean(status?.can_cancel)
}

function failedTaskMessage(status: KnowledgeBaseIndexStatus) {
  if (status.target_index_version_status === 'FAILED') return '新版本构建失败，活动版本仍保留。'
  if (status.tasks.some((task) => task.task_type === 'INDEX_EMBED' && task.status === 'FAILED')) {
    return 'Embedding 阶段失败；请检查本地模型状态和失败文件诊断。'
  }
  return null
}

export default function KnowledgeBaseIndexPanel({ item }: { item: KnowledgeBaseItem }) {
  const queryClient = useQueryClient()
  const queryKey = ['knowledge-base-index-status', item.knowledge_base_id]
  const query = useQuery({
    queryKey,
    queryFn: ({ signal }) => getKnowledgeBaseIndexStatus(item.knowledge_base_id, signal),
    staleTime: 0,
    refetchOnMount: 'always',
    refetchInterval: (current) => current.state.data?.operation_in_progress ? 1500 : false,
    refetchIntervalInBackground: false,
  })
  const modelQuery = useQuery({
    queryKey: ['embedding-model-status'],
    queryFn: ({ signal }) => getEmbeddingModelStatus(signal),
    staleTime: 0,
    refetchOnMount: 'always',
    refetchInterval: (current) => current.state.data?.can_cancel || current.state.data?.state === 'VERIFYING' ? 750 : false,
    refetchIntervalInBackground: false,
  })
  const refresh = () => queryClient.invalidateQueries({ queryKey })
  const refreshModel = () => Promise.all([
    queryClient.invalidateQueries({ queryKey: ['embedding-model-status'] }),
    queryClient.invalidateQueries({ queryKey }),
  ])
  const retryMutation = useMutation({
    mutationFn: (fileIds: string[]) => retryFailedIndexFiles(item.knowledge_base_id, fileIds),
    onSuccess: refresh,
  })
  const rebuildMutation = useMutation({
    mutationFn: () => rebuildKnowledgeBaseIndex(item.knowledge_base_id),
    onSuccess: refresh,
  })
  const cancelMutation = useMutation({
    mutationFn: (taskId: string) => cancelKnowledgeBaseTask(taskId),
    onSuccess: refresh,
  })
  const installModelMutation = useMutation({
    mutationFn: installEmbeddingModel,
    onSuccess: refreshModel,
  })
  const cancelModelMutation = useMutation({
    mutationFn: cancelKnowledgeBaseTask,
    onSuccess: refreshModel,
  })

  const status = query.data
  const model = modelQuery.data
  const retryableFailures = status?.failures.filter((failure) => failure.retryable) ?? []
  const visibleTasks = status?.tasks.filter((task) => task.task_type.startsWith('INDEX_')).slice(0, 6) ?? []
  const submitRetry = () => retryMutation.mutate(retryableFailures.map((failure) => failure.file_id))
  const submitRebuild = () => {
    const accepted = window.confirm(
      `重建“${item.name}”的索引？当前 ${status?.file_counts.total ?? item.file_count} 个文件都将进入新版本构建，可能需要数分钟。已有活动版本会继续用于检索；只有新版本完整校验通过后才切换，失败时保留旧版本。`,
    )
    if (accepted) rebuildMutation.mutate()
  }
  const cancelModelInstall = () => {
    const taskId = model?.task_id
    if (taskId) cancelModelMutation.mutate(taskId)
  }
  const requestError = retryMutation.error ?? rebuildMutation.error ?? cancelMutation.error
  const modelRequestError = installModelMutation.error ?? cancelModelMutation.error

  return <section className="detail-section index-workbench" aria-labelledby="index-workbench-title">
    <div className="section-heading">
      <div>
        <h2 id="index-workbench-title">索引状态与任务</h2>
        {status && <p>{statusLabel(status.status)}</p>}
      </div>
      <button className="icon-button" type="button" title="刷新索引状态" aria-label="刷新索引状态" onClick={() => void query.refetch()} disabled={query.isFetching}>
        <RefreshCw size={16} aria-hidden="true" />
      </button>
    </div>

    {query.isLoading && <div className="detail-empty"><LoaderCircle size={18} aria-hidden="true" />正在读取索引状态</div>}
    {query.isError && <div className="inline-error" role="alert">索引状态读取失败。<button className="quiet-button" type="button" onClick={() => void query.refetch()}>重试</button></div>}

    {status && <>
      <div className="index-workbench__counts" aria-label="知识库文件索引计数">
        <div><strong>{status.file_counts.available}</strong><span>可用</span></div>
        <div><strong>{status.file_counts.processing}</strong><span>处理中</span></div>
        <div><strong>{status.file_counts.failed}</strong><span>失败</span></div>
      </div>

      <dl className="index-workbench__versions">
        <div><dt>活动版本</dt><dd>{status.active_index_version_id ?? '暂无'}{status.active_index_version_status && ` · ${status.active_index_version_status}`}</dd></div>
        {status.target_index_version_id && <div><dt>构建目标</dt><dd>{status.target_index_version_id} · {status.target_stage ?? status.target_index_version_status}</dd></div>}
      </dl>

      {status.active_index_version_id && status.target_index_version_id && <p className="index-workbench__note">新版本构建期间，当前活动版本仍可用于检索。</p>}
      {status.active_index_version_id && status.target_index_version_status === 'FAILED' && <p className="index-workbench__note">计数中的可用文件来自活动版本，失败文件来自未激活的新版本；活动版本仍可用于检索。</p>}
      {status.embedding_model_state !== 'READY' && status.active_index_version_id && <p className="index-workbench__note">当前活动索引仍可用于检索；新模型仅影响后续索引构建。</p>}
      {failedTaskMessage(status) && <div className="index-workbench__model" role="status"><AlertTriangle size={16} aria-hidden="true" /><span>{failedTaskMessage(status)}</span></div>}

      {status.failures.length > 0 && <div className="index-workbench__failures" aria-label="失败文件列表">
        <h3>失败文件</h3>
        {status.failures.map((failure) => <div className="index-workbench__failure" key={failure.file_id}>
          <div><strong>{failure.display_name}</strong><span>{failure.stage} · {failure.message}</span><small>原因码：{failure.reason_code}{failure.diagnostic_id ? ` · 诊断 ID：${failure.diagnostic_id}` : ''}</small></div>
          {failure.retryable ? <span className="index-workbench__retryable">可重试</span> : <span className="index-workbench__blocked">需先处理</span>}
        </div>)}
      </div>}

      {visibleTasks.length > 0 && <div className="index-workbench__tasks" aria-label="索引后台任务">
        <h3>后台任务</h3>
        {visibleTasks.map((task) => <div className="index-workbench__task" key={task.task_id}>
          <div><strong>{taskTypeLabel(task.task_type)}</strong><span>{task.phase ?? task.status}{task.progress !== null && task.progress !== undefined ? ` · ${task.progress}%` : ''}</span><small>诊断 ID：{task.diagnostic_id}</small>{task.message && <small>{task.message}</small>}</div>
          {activeTaskStates.has(task.status) && <button className="icon-button" type="button" title="取消此后台任务" aria-label={`取消${taskTypeLabel(task.task_type)}`} disabled={cancelMutation.isPending} onClick={() => cancelMutation.mutate(task.task_id)}><X size={16} aria-hidden="true" /></button>}
          {task.status === 'COMPLETED' && <Check size={16} aria-label="已完成" />}
        </div>)}
      </div>}

      {requestError && <div className="inline-error" role="alert">{requestError instanceof Error ? requestError.message : '索引操作未提交。'}<button className="quiet-button" type="button" onClick={() => { retryMutation.reset(); rebuildMutation.reset(); cancelMutation.reset(); void query.refetch() }}>重新加载状态</button></div>}

      <section className="index-workbench__model-install" aria-labelledby="embedding-model-title">
        <div className="index-workbench__model-heading">
          <div>
            <h3 id="embedding-model-title">本地 Embedding 模型</h3>
            {model && <p>{modelStateLabel(model.state)}</p>}
          </div>
          {model?.state === 'READY' && <Check size={17} aria-label="模型已校验" />}
          {modelTaskActive(model) && <button className="icon-button" type="button" title="取消模型安装" aria-label="取消模型安装" disabled={cancelModelMutation.isPending} onClick={cancelModelInstall}><X size={16} aria-hidden="true" /></button>}
        </div>
        {modelQuery.isLoading && <div className="detail-empty"><LoaderCircle size={16} aria-hidden="true" />正在读取模型状态</div>}
        {modelQuery.isError && <div className="inline-error" role="alert">模型状态读取失败。<button className="quiet-button" type="button" onClick={() => void modelQuery.refetch()}>重试</button></div>}
        {model && <>
          <div className="index-workbench__model-meta">
            <span>{formatBytes(model.total_size_bytes)}</span>
            <span>许可：{model.license}（依据 BAAI 上游；Xenova 未单独声明）</span>
            <span>文件只下载到本机</span>
          </div>
          <p className="index-workbench__model-sources">
            来源：<a href={model.base_model_url} target="_blank" rel="noreferrer">{model.base_model_id}</a>
            {' · ONNX：'}<a href={model.artifact_url} target="_blank" rel="noreferrer">{model.artifact_repository_id}</a>
          </p>
          <details className="index-workbench__model-revisions">
            <summary>固定版本与校验指纹</summary>
            <dl>
              <div><dt>基础 revision</dt><dd>{model.base_revision}</dd></div>
              <div><dt>ONNX revision</dt><dd>{model.artifact_revision}</dd></div>
              <div><dt>SHA-256 指纹</dt><dd>{model.artifact_fingerprint}</dd></div>
            </dl>
          </details>
          {modelTaskActive(model) && <div className="index-workbench__model-progress" role="status">
            <div className="index-workbench__model-progress-heading">
              <span>{modelStateLabel(model.state)}{model.current_file ? ` · ${model.current_file}` : ''}</span>
              <span>{formatBytes(model.downloaded_bytes)} / {formatBytes(model.total_size_bytes)}</span>
            </div>
            <progress aria-label="模型下载进度" value={model.downloaded_bytes} max={model.total_size_bytes} />
          </div>}
          {model.error_code && <p className="index-workbench__model-error" role="alert">{model.state === 'MISSING_OFFLINE' ? '当前无法连接模型来源。' : '模型安装未完成。'}原因码：{model.error_code}{model.diagnostic_id && ` · 诊断 ID：${model.diagnostic_id}`}</p>}
          {modelRequestError && <div className="inline-error" role="alert">{modelRequestError instanceof Error ? modelRequestError.message : '模型操作未完成。'}<button className="quiet-button" type="button" onClick={() => { installModelMutation.reset(); cancelModelMutation.reset(); void modelQuery.refetch() }}>重新加载模型状态</button></div>}
          <div className="heading-actions">
            {model.can_install && <button className="primary-button" type="button" disabled={installModelMutation.isPending} onClick={() => installModelMutation.mutate()}><Download size={16} aria-hidden="true" />{installModelMutation.isPending ? '正在提交安装' : model.state === 'MISSING' ? '下载并安装模型' : '重试模型安装'}</button>}
          </div>
        </>}
      </section>

      <div className="heading-actions index-workbench__actions">
        {retryableFailures.length > 0 && <button className="quiet-button" type="button" disabled={!status.can_retry_failed || retryMutation.isPending || rebuildMutation.isPending} onClick={submitRetry}><RotateCcw size={16} aria-hidden="true" />{retryMutation.isPending ? '正在提交重试' : `重试失败文件 (${retryableFailures.length})`}</button>}
        {status.file_counts.total > 0 && <button className="primary-button" type="button" disabled={!status.can_rebuild || retryMutation.isPending || rebuildMutation.isPending} onClick={submitRebuild}><RefreshCw size={16} aria-hidden="true" />{rebuildMutation.isPending ? '正在提交重建' : '重建当前知识库索引'}</button>}
      </div>
      <p className="index-workbench__model-state">{model ? modelStateLabel(model.state) : modelStateLabel(status.embedding_model_state)}</p>
    </>}
  </section>
}

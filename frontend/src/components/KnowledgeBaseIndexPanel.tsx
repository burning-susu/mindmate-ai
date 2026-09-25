import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, Check, LoaderCircle, RefreshCw, RotateCcw, X } from 'lucide-react'

import {
  cancelKnowledgeBaseTask,
  getKnowledgeBaseIndexStatus,
  rebuildKnowledgeBaseIndex,
  retryFailedIndexFiles,
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
  if (status === 'MISSING' || status === 'MISSING_OFFLINE') return '本地 Embedding 模型缺失'
  if (status === 'CORRUPT') return '本地 Embedding 模型校验失败'
  return '本地 Embedding 模型状态未知'
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
  const refresh = () => queryClient.invalidateQueries({ queryKey })
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

  const status = query.data
  const retryableFailures = status?.failures.filter((failure) => failure.retryable) ?? []
  const visibleTasks = status?.tasks.filter((task) => task.task_type.startsWith('INDEX_')).slice(0, 6) ?? []
  const submitRetry = () => retryMutation.mutate(retryableFailures.map((failure) => failure.file_id))
  const submitRebuild = () => {
    const accepted = window.confirm(
      `重建“${item.name}”的索引？当前 ${status?.file_counts.total ?? item.file_count} 个文件都将进入新版本构建，可能需要数分钟。已有活动版本会继续用于检索；只有新版本完整校验通过后才切换，失败时保留旧版本。`,
    )
    if (accepted) rebuildMutation.mutate()
  }
  const requestError = retryMutation.error ?? rebuildMutation.error ?? cancelMutation.error

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
      {status.embedding_model_state !== 'READY' && <div className="index-workbench__model" role="status"><AlertTriangle size={16} aria-hidden="true" /><span>{modelStateLabel(status.embedding_model_state)}；索引操作不会自动下载模型。{status.embedding_model_error_code && ` 诊断：${status.embedding_model_error_code}`}</span></div>}
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

      <div className="heading-actions index-workbench__actions">
        {retryableFailures.length > 0 && <button className="quiet-button" type="button" disabled={!status.can_retry_failed || retryMutation.isPending || rebuildMutation.isPending} onClick={submitRetry}><RotateCcw size={16} aria-hidden="true" />{retryMutation.isPending ? '正在提交重试' : `重试失败文件 (${retryableFailures.length})`}</button>}
        {status.file_counts.total > 0 && <button className="primary-button" type="button" disabled={!status.can_rebuild || retryMutation.isPending || rebuildMutation.isPending} onClick={submitRebuild}><RefreshCw size={16} aria-hidden="true" />{rebuildMutation.isPending ? '正在提交重建' : '重建当前知识库索引'}</button>}
      </div>
      <p className="index-workbench__model-state">{modelStateLabel(status.embedding_model_state)}</p>
    </>}
  </section>
}

import { Ban, CheckCircle2, Clock3, ListTodo, LoaderCircle, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'

import { apiRequest } from '../api/client'
import { getHomeOverview, type HomeTaskItem } from '../api/home'

const ACTIVE_STATUSES = new Set(['CREATED', 'QUEUED', 'RUNNING', 'BLOCKED', 'PAUSED'])
const CANCELLABLE_TASK_TYPES = new Set([
  'FILE_IMPORT',
  'INDEX_PREPROCESS',
  'INDEX_CHUNK',
  'INDEX_EMBED',
  'INDEX_FTS',
  'KB_MEMBERSHIP',
  'EMBEDDING_MODEL_INSTALL',
])

const TASK_STATUS_LABEL: Record<string, string> = {
  CREATED: '已创建',
  QUEUED: '排队',
  RUNNING: '运行中',
  BLOCKED: '等待处理',
  PAUSED: '已暂停',
  CANCELLED: '已取消',
  SUCCEEDED: '已成功',
  COMPLETED: '已完成',
  PARTIAL: '部分完成',
  FAILED: '失败',
  INTERRUPTED: '已中断',
}

const TASK_TYPE_LABEL: Record<string, string> = {
  FILE_IMPORT: '导入文件',
  FILE_REPROCESS: '重新处理文件',
  INDEX_PREPROCESS: '索引预处理',
  INDEX_CHUNK: '索引切块',
  INDEX_EMBED: '索引向量',
  INDEX_FTS: '索引全文',
  KB_MEMBERSHIP: '知识库成员',
  EMBEDDING_MODEL_INSTALL: '安装本地模型',
  BACKUP_CREATE: '创建备份',
  CHAT_GENERATION: 'AI 生成',
  LEARNING_QUESTION: '学习出题',
  LEARNING_FEEDBACK: '学习点评',
}

function taskStatusLabel(status: string): string {
  return TASK_STATUS_LABEL[status] ?? status
}

function taskTypeLabel(taskType: string): string {
  return TASK_TYPE_LABEL[taskType] ?? taskType
}

function taskProgressText(task: HomeTaskItem): string {
  if (typeof task.progress_percent === 'number') return `${task.progress_percent}%`
  if (task.phase) return task.phase
  if (task.status === 'RUNNING') return '运行中'
  return taskStatusLabel(task.status)
}

function formatTaskTime(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', { hour12: false })
}

function cancelPath(task: HomeTaskItem): string | null {
  if (!CANCELLABLE_TASK_TYPES.has(task.task_type)) return null
  if (task.task_type === 'FILE_IMPORT') return `/api/v1/file-imports/${task.task_id}/cancel`
  return `/api/v1/tasks/${task.task_id}/cancel`
}

function taskCanCancel(task: HomeTaskItem): boolean {
  return ACTIVE_STATUSES.has(task.status) && cancelPath(task) !== null
}

function taskSummary(task: HomeTaskItem): string | null {
  const parts = [task.failure_code, task.failure_summary].filter(Boolean)
  return parts.length > 0 ? parts.join(' · ') : null
}

export default function GlobalTaskDrawer() {
  const [open, setOpen] = useState(false)
  const [cancellingId, setCancellingId] = useState('')
  const [actionError, setActionError] = useState('')
  const triggerRef = useRef<HTMLButtonElement>(null)
  const closeRef = useRef<HTMLButtonElement>(null)
  const wasOpenRef = useRef(false)
  const queryClient = useQueryClient()
  const query = useQuery({
    queryKey: ['global-task-overview'],
    queryFn: () => getHomeOverview(30),
    retry: false,
    staleTime: 0,
    refetchOnMount: 'always',
    refetchInterval: (current) => {
      const tasks = current.state.data?.tasks
      if (tasks && (tasks.queued_count > 0 || tasks.running_count > 0)) return 4000
      return false
    },
  })

  useEffect(() => {
    if (open) {
      wasOpenRef.current = true
      closeRef.current?.focus()
    } else if (wasOpenRef.current) {
      wasOpenRef.current = false
      triggerRef.current?.focus()
    }
  }, [open])

  useEffect(() => {
    if (!open) return undefined
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  const tasks = query.data?.tasks
  const recent = tasks?.recent ?? []
  const activeCount = tasks ? tasks.queued_count + tasks.running_count + tasks.blocked_count : 0
  const buttonLabel = activeCount > 0 ? `打开全局任务，${activeCount} 个进行中` : '打开全局任务'

  const cancelTask = async (task: HomeTaskItem) => {
    const path = cancelPath(task)
    if (!path || cancellingId) return
    setCancellingId(task.task_id)
    setActionError('')
    try {
      await apiRequest(path, { method: 'POST' })
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['global-task-overview'] }),
        queryClient.invalidateQueries({ queryKey: ['home-overview'] }),
      ])
    } catch (error) {
      setActionError(error instanceof Error ? error.message : '取消任务失败，请重新读取任务状态。')
    } finally {
      setCancellingId('')
    }
  }

  return (
    <>
      <button
        ref={triggerRef}
        className="global-task-button"
        type="button"
        aria-label={buttonLabel}
        title="打开全局任务"
        onClick={() => setOpen(true)}
      >
        <ListTodo size={16} aria-hidden="true" />
        <span>任务</span>
        {activeCount > 0 ? <strong aria-hidden="true">{activeCount}</strong> : null}
      </button>
      {open ? (
        <div className="global-task-layer" role="presentation" onClick={() => setOpen(false)}>
          <aside
            className="global-task-panel"
            role="dialog"
            aria-modal="true"
            aria-labelledby="global-task-panel-title"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="global-task-panel__heading">
              <div>
                <span className="eyebrow">跨页面状态</span>
                <h2 id="global-task-panel-title">后台任务</h2>
              </div>
              <button ref={closeRef} className="icon-button" type="button" aria-label="关闭全局任务" title="关闭" onClick={() => setOpen(false)}>
                <X size={17} aria-hidden="true" />
              </button>
            </div>
            <p className="global-task-panel__hint">任务状态来自本地持久记录。关闭抽屉不会取消任务；刷新或重启后仍会从这里恢复。</p>
            {actionError ? <div className="global-task-panel__error" role="alert">{actionError}</div> : null}
            {query.isPending && !query.data ? <p className="global-task-panel__state" role="status"><LoaderCircle className="spin" size={16} /> 正在读取任务状态</p> : null}
            {query.isError ? (
              <div className="global-task-panel__state global-task-panel__state--error" role="alert">
                <span>任务状态暂时读不出来，当前页面不会因此停止工作。</span>
                <button className="quiet-button" type="button" onClick={() => void query.refetch()}>重新读取</button>
              </div>
            ) : null}
            {!query.isPending && !query.isError && recent.length === 0 ? (
              <p className="global-task-panel__state"><CheckCircle2 size={16} aria-hidden="true" /> 当前没有后台任务。</p>
            ) : null}
            {recent.length > 0 ? (
              <ul className="global-task-panel__list">
                {recent.map((task) => {
                  const summary = taskSummary(task)
                  const canCancel = taskCanCancel(task)
                  return (
                    <li key={task.task_id} className="global-task-panel__item">
                      <div className="global-task-panel__item-heading">
                        <div>
                          <strong>{taskTypeLabel(task.task_type)}</strong>
                          <span>{taskStatusLabel(task.status)}</span>
                        </div>
                        {task.status === 'RUNNING' ? <LoaderCircle className="spin" size={15} aria-hidden="true" /> : <Clock3 size={15} aria-hidden="true" />}
                      </div>
                      <p className="global-task-panel__meta">阶段：{task.phase || '未记录'} · 进度：{taskProgressText(task)}</p>
                      {typeof task.progress_percent === 'number' ? <progress max="100" value={task.progress_percent} aria-label={`${taskTypeLabel(task.task_type)}进度`} /> : null}
                      {summary ? <p className="global-task-panel__failure" role="status">{summary}</p> : null}
                      <p className="global-task-panel__meta">最近更新：{formatTaskTime(task.updated_at)}</p>
                      <details>
                        <summary>查看任务详情</summary>
                        <dl className="global-task-panel__detail">
                          <div><dt>任务编号</dt><dd>{task.task_id}</dd></div>
                          <div><dt>任务类型</dt><dd>{task.task_type}</dd></div>
                          <div><dt>终态</dt><dd>{taskStatusLabel(task.status)}</dd></div>
                          <div><dt>失败原因</dt><dd>{summary || '无'}</dd></div>
                        </dl>
                      </details>
                      {canCancel ? (
                        <button
                          className="quiet-button global-task-panel__cancel"
                          type="button"
                          disabled={Boolean(cancellingId)}
                          onClick={() => void cancelTask(task)}
                        >
                          <Ban size={14} aria-hidden="true" />
                          {cancellingId === task.task_id ? '正在取消' : '取消任务'}
                        </button>
                      ) : null}
                    </li>
                  )
                })}
              </ul>
            ) : null}
            {tasks && tasks.total_count > recent.length ? <p className="global-task-panel__hint">仅显示最近 30 条；更早的任务仍保留在本地记录中。</p> : null}
          </aside>
        </div>
      ) : null}
    </>
  )
}

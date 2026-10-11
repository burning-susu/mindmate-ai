import * as Dialog from '@radix-ui/react-dialog'
import { CheckCircle2, CircleAlert, CirclePause, CircleX, Clock3, ListTodo, LoaderCircle, X } from 'lucide-react'
import { useState } from 'react'
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

function TaskStatusIcon({ status }: { status: string }) {
  if (status === 'RUNNING') return <LoaderCircle className="spin" size={15} aria-label="任务运行中" />
  if (status === 'PAUSED') return <CirclePause size={15} aria-label="任务已暂停" />
  if (status === 'CANCELLED') return <CircleX size={15} aria-label="任务已取消" />
  if (status === 'SUCCEEDED' || status === 'COMPLETED') {
    return <CheckCircle2 size={15} aria-label="任务已完成" />
  }
  if (status === 'PARTIAL' || status === 'FAILED' || status === 'INTERRUPTED') {
    return <CircleAlert size={15} aria-label={`任务${taskStatusLabel(status)}`} />
  }
  return <Clock3 size={15} aria-label={`任务${taskStatusLabel(status)}`} />
}

function taskTypeLabel(taskType: string): string {
  return TASK_TYPE_LABEL[taskType] ?? taskType
}

function taskProgressText(task: HomeTaskItem): string {
  if (typeof task.progress_percent === 'number') return `${task.progress_percent}%`
  const phaseLabels: Record<string, string> = {
    PARSING: '正在解析',
    PREPARING: '正在准备',
    CHUNKING: '正在切分资料',
    EMBEDDING: '正在生成向量',
    INDEXING: '正在建立索引',
  }
  if (task.phase) return phaseLabels[task.phase] ?? taskStatusLabel(task.status)
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
  return task.failure_summary || null
}

export default function GlobalTaskDrawer() {
  const [open, setOpen] = useState(false)
  const [cancellingId, setCancellingId] = useState('')
  const [actionError, setActionError] = useState('')
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
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>
        <button className="global-task-button" type="button" aria-label={buttonLabel} title="任务">
          <ListTodo size={16} aria-hidden="true" />
          <span>任务</span>
          {activeCount > 0 ? <strong aria-hidden="true">{activeCount}</strong> : null}
        </button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="global-task-layer" />
        <Dialog.Content className="global-task-panel" aria-describedby="global-task-panel-description">
          <div className="global-task-panel__heading">
            <Dialog.Title className="global-task-panel__title">后台任务</Dialog.Title>
            <Dialog.Close asChild>
              <button className="icon-button" type="button" aria-label="关闭全局任务" title="关闭">
                <X size={17} aria-hidden="true" />
              </button>
            </Dialog.Close>
          </div>
          <Dialog.Description id="global-task-panel-description" className="global-task-panel__hint">查看正在处理和最近完成的任务。</Dialog.Description>
          {actionError ? <div className="global-task-panel__error" role="alert">{actionError}</div> : null}
          {query.isPending && !query.data ? <p className="global-task-panel__state" role="status"><LoaderCircle className="spin" size={16} /> 正在读取任务</p> : null}
          {query.isError ? (
            <div className="global-task-panel__state global-task-panel__state--error" role="alert">
              <span>任务暂时无法读取。</span>
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
                      <TaskStatusIcon status={task.status} />
                    </div>
                    <p className="global-task-panel__meta">进度：{taskProgressText(task)}</p>
                    {typeof task.progress_percent === 'number' ? <progress max="100" value={task.progress_percent} aria-label={`${taskTypeLabel(task.task_type)}进度`} /> : null}
                    {summary ? <p className="global-task-panel__failure" role="status">{summary}</p> : null}
                    <p className="global-task-panel__meta">最近更新：{formatTaskTime(task.updated_at)}</p>
                    <details>
                      <summary>查看详情</summary>
                      <dl className="global-task-panel__detail">
                        <div><dt>任务编号</dt><dd>{task.task_id}</dd></div>
                        <div><dt>处理阶段</dt><dd>{task.phase || '未记录'}</dd></div>
                        <div><dt>失败代码</dt><dd>{task.failure_code || '无'}</dd></div>
                      </dl>
                    </details>
                    {canCancel ? (
                      <button
                        className="quiet-button global-task-panel__cancel"
                        type="button"
                        disabled={Boolean(cancellingId)}
                        onClick={() => void cancelTask(task)}
                      >
                        <CircleX size={14} aria-hidden="true" />
                        {cancellingId === task.task_id ? '正在取消' : '取消任务'}
                      </button>
                    ) : null}
                  </li>
                )
              })}
            </ul>
          ) : null}
          {tasks && tasks.total_count > recent.length ? <p className="global-task-panel__hint">显示最近 30 条任务。</p> : null}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

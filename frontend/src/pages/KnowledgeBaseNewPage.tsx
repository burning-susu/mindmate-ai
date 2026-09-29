import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, BookOpen, Check, FilePlus2, FileUp, Save, X } from 'lucide-react'
import { v7 as uuidv7 } from 'uuid'
import { type ChangeEvent, type FormEvent, useMemo, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { apiRequest } from '../api/client'
import {
  addKnowledgeBaseMembers,
  createKnowledgeBase,
  type KnowledgeBaseCreate,
} from '../api/knowledgeBases'
import {
  importFiles,
  type FileImportResponse,
  type FileListResponse,
} from '../api/files'

const fileStatusLabels: Record<string, string> = {
  PARSED: '已解析',
  QUEUED: '等待解析',
  PARSING: '正在解析',
  PARSE_FAILED: '解析失败',
  IN_TRASH: '回收站',
  STORAGE_MISSING: '文件缺失',
}

type IntakeState = {
  memberTaskId: string | null
  importId: string | null
  errors: string[]
}

function intakeStorageKey(knowledgeBaseId: string) {
  return `mindmate:knowledge-base-intake:${knowledgeBaseId}`
}

function rememberIntake(knowledgeBaseId: string, intake: IntakeState) {
  try {
    window.localStorage.setItem(intakeStorageKey(knowledgeBaseId), JSON.stringify(intake))
  } catch {
    // Storage can be disabled in a private browser profile; the current page still has task IDs.
  }
}

function fileStatusLabel(status: string) {
  return fileStatusLabels[status] ?? status
}

export default function KnowledgeBaseNewPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const localInputRef = useRef<HTMLInputElement>(null)
  const submitLock = useRef(false)
  const idempotencyKeys = useRef({ members: uuidv7(), import: uuidv7() })
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [color, setColor] = useState('#176b87')
  const [selectedExisting, setSelectedExisting] = useState<string[]>([])
  const [localFiles, setLocalFiles] = useState<File[]>([])

  const filesQuery = useQuery({
    queryKey: ['knowledge-base-new-file-options'],
    queryFn: () => apiRequest<FileListResponse>('/api/v1/files?sort=name&limit=100'),
    staleTime: 0,
  })

  const candidates = useMemo(
    () => (filesQuery.data?.items ?? []).filter((file) => (
      file.deleted_at === null
      && file.content_available !== false
      && file.status !== 'IN_TRASH'
      && file.status !== 'STORAGE_MISSING'
    )),
    [filesQuery.data],
  )

  const mutation = useMutation({
    mutationFn: async (): Promise<{ item: Awaited<ReturnType<typeof createKnowledgeBase>>; intake: IntakeState }> => {
      const payload: KnowledgeBaseCreate = {
        name,
        description: description || null,
        icon: 'book-open',
        color,
      }
      const item = await createKnowledgeBase(payload)
      const intake: IntakeState = { memberTaskId: null, importId: null, errors: [] }

      if (selectedExisting.length > 0) {
        try {
          const task = await addKnowledgeBaseMembers(
            item.knowledge_base_id,
            selectedExisting,
            idempotencyKeys.current.members,
          )
          intake.memberTaskId = task.task_id
        } catch (error) {
          intake.errors.push(error instanceof Error ? error.message : '已有文件加入任务未提交。')
        }
      }

      if (localFiles.length > 0) {
        try {
          const imported: FileImportResponse = await importFiles(
            localFiles,
            { knowledge_base_id: item.knowledge_base_id },
            idempotencyKeys.current.import,
          )
          intake.importId = imported.import_id
        } catch (error) {
          intake.errors.push(error instanceof Error ? error.message : '本地文件导入任务未提交。')
        }
      }

      rememberIntake(item.knowledge_base_id, intake)
      return { item, intake }
    },
    onSuccess: ({ item, intake }) => {
      void queryClient.invalidateQueries({ queryKey: ['knowledge-bases'] })
      void navigate(`/knowledge-bases/${item.knowledge_base_id}`, { state: { intake } })
    },
    onError: () => { submitLock.current = false },
  })

  const toggleExisting = (fileId: string) => {
    setSelectedExisting((current) => current.includes(fileId)
      ? current.filter((id) => id !== fileId)
      : [...current, fileId])
  }

  const selectLocalFiles = (event: ChangeEvent<HTMLInputElement>) => {
    const incoming = Array.from(event.target.files ?? [])
    if (incoming.length > 0) {
      setLocalFiles((current) => {
        const seen = new Set(current.map((file) => `${file.name}:${file.size}:${file.lastModified}`))
        return [...current, ...incoming.filter((file) => !seen.has(`${file.name}:${file.size}:${file.lastModified}`))]
      })
    }
    event.target.value = ''
  }

  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (!name.trim() || mutation.isPending || submitLock.current) return
    submitLock.current = true
    mutation.mutate()
  }

  return <section className="detail-page">
    <Link className="back-link" to="/knowledge-bases"><ArrowLeft size={16} aria-hidden="true" />返回知识库</Link>
    <div className="detail-heading">
      <div>
        <span className="eyebrow">新建本地资料空间</span>
        <h1>新建知识库</h1>
        <p>可以先建空库，也可以在同一次提交中选择已有文件并导入本地文件。</p>
      </div>
    </div>
    <form className="knowledge-form detail-section" onSubmit={submit}>
      <div className="knowledge-form__mark" style={{ backgroundColor: color }}><BookOpen size={24} aria-hidden="true" /></div>
      <label>名称<input aria-label="知识库名称" required maxLength={100} value={name} onChange={(event) => setName(event.target.value)} autoFocus /></label>
      <label>描述<textarea aria-label="知识库描述" maxLength={2000} rows={5} value={description} onChange={(event) => setDescription(event.target.value)} /></label>
      <label>颜色<input aria-label="知识库颜色" type="color" value={color} onChange={(event) => setColor(event.target.value)} /></label>

      <section className="knowledge-intake" aria-labelledby="knowledge-intake-title">
        <div className="section-heading">
          <div><h2 id="knowledge-intake-title">初始资料</h2><p>两种来源可以混合选择；不选文件仍可创建空库。</p></div>
          <FilePlus2 size={18} aria-hidden="true" />
        </div>
        <div className="knowledge-intake__source">
          <div className="knowledge-intake__source-heading"><div><h3>选择已导入文件</h3><p>回收站和托管内容缺失的记录不会出现在这里；解析失败会保留真实状态供你判断。</p></div><span>{selectedExisting.length} 个已选</span></div>
          {filesQuery.isLoading && <div className="knowledge-intake__empty">正在加载已导入文件…</div>}
          {filesQuery.isError && <div className="inline-error" role="alert">已导入文件列表加载失败，请稍后重试。</div>}
          {!filesQuery.isLoading && !filesQuery.isError && candidates.length === 0 && <div className="knowledge-intake__empty">还没有可加入的已导入文件。</div>}
          <div className="knowledge-intake__files">
            {candidates.map((file) => <label className="knowledge-intake__file" key={file.file_id}>
              <input type="checkbox" checked={selectedExisting.includes(file.file_id)} onChange={() => toggleExisting(file.file_id)} />
              <span><strong>{file.display_name}</strong><small>{file.document_type} · <span className={`file-status file-status--${file.status.toLowerCase()}`}>{fileStatusLabel(file.status)}</span></small></span>
              {selectedExisting.includes(file.file_id) && <Check size={16} aria-label="已选择" />}
            </label>)}
          </div>
        </div>
        <div className="knowledge-intake__source">
          <div className="knowledge-intake__source-heading"><div><h3>上传本地文件</h3><p>提交后复用文件工作台的格式、大小、重复内容和持久解析任务。</p></div><button className="quiet-button" type="button" onClick={() => localInputRef.current?.click()}><FileUp size={15} aria-hidden="true" />选择文件</button></div>
          <input ref={localInputRef} className="visually-hidden" type="file" multiple accept=".pdf,.docx,.pptx,.txt,.md,.markdown" aria-label="上传本地文件" onChange={selectLocalFiles} />
          {localFiles.length === 0 && <div className="knowledge-intake__empty">尚未选择本地文件。</div>}
          {localFiles.length > 0 && <div className="knowledge-intake__files">{localFiles.map((file, index) => <div className="knowledge-intake__file" key={`${file.name}-${file.lastModified}-${index}`}><FileUp size={16} aria-hidden="true" /><span><strong>{file.name}</strong><small>{file.type || '按扩展名校验'} · {Math.ceil(file.size / 1024)} KB</small></span><button className="icon-button" type="button" aria-label={`移除待上传文件 ${file.name}`} title="移除待上传文件" onClick={() => setLocalFiles((current) => current.filter((_, currentIndex) => currentIndex !== index))}><X size={15} aria-hidden="true" /></button></div>)}</div>}
          <p className="knowledge-intake__hint">本地 File 对象只在当前页面保留。刷新前尚未提交的选择不会被伪装成已导入，请重新选择。</p>
        </div>
      </section>

      {mutation.isError && <div className="inline-error" role="alert">{mutation.error instanceof Error ? mutation.error.message : '创建失败，请重试。'}</div>}
      <div className="heading-actions"><button className="primary-button" type="submit" disabled={mutation.isPending || !name.trim()}><Save size={16} aria-hidden="true" />{mutation.isPending ? '正在创建并提交资料' : '创建知识库'}</button><Link className="quiet-button" to="/knowledge-bases">取消</Link></div>
    </form>
  </section>
}

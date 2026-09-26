import { useQuery, useQueryClient } from '@tanstack/react-query'
import { BookOpen, FileText, FileUp, GraduationCap, LoaderCircle, MessageSquare, Plus } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import { apiRequest } from '../api/client'
import { listRecentFiles, type FileItem } from '../api/files'
import { listConversationHistory, listLearningHistory, type ConversationHistoryItem, type LearningHistoryItem } from '../api/history'
import { listKnowledgeBases, type KnowledgeBaseItem } from '../api/knowledgeBases'
import { sourceStatusLabel } from '../components/sourceStatus'

function formatTime(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', { hour12: false })
}

function sessionStatusLabel(item: LearningHistoryItem): string {
  if (item.status === 'SOURCE_INVALID' || item.source_status !== 'AVAILABLE') return '资料范围已失效'
  if (item.status === 'FAILED') return '未能出题'
  if (item.answered_count > 0) return '已作答'
  if (item.status === 'IN_PROGRESS') return '未作答'
  return item.status
}

function sourceInvalid(item: LearningHistoryItem): boolean {
  return item.status === 'SOURCE_INVALID' || item.source_status !== 'AVAILABLE'
}

function ContinueLearning() {
  const recentQuery = useQuery({
    queryKey: ['home-learning-recent'],
    queryFn: () => listLearningHistory(undefined, 1),
    retry: false,
    staleTime: 0,
    refetchOnMount: 'always',
  })
  const item = recentQuery.isError ? undefined : recentQuery.data?.items[0]

  return (
    <section className="home-continue" aria-labelledby="home-continue-title">
      <div>
        <span className="eyebrow">最近学习</span>
        <h2 id="home-continue-title">继续学习</h2>
        <p>只读取最近一次已保存的学习会话。打开或刷新首页不会创建会话、题目或作答。</p>
      </div>
      {recentQuery.isLoading ? (
        <div className="history-state" role="status"><LoaderCircle className="spin" size={16} /> 正在读取最近学习</div>
      ) : null}
      {recentQuery.isError ? (
        <div className="history-state history-state--error" role="alert">
          <span>最近学习暂时读不出来，当前不能把它当作可继续的会话。</span>
          <button className="quiet-button" type="button" onClick={() => void recentQuery.refetch()}>重新加载</button>
          <Link className="quiet-button" to="/history?tab=learning">打开学习历史</Link>
        </div>
      ) : null}
      {!recentQuery.isLoading && !recentQuery.isError && !item ? (
        <div className="home-continue__empty">
          <p>还没有学习记录。开始第一次学习要先在知识库列表里选择一个索引就绪、并且有可用文件的知识库。没有资料时请先导入文件。这里不会用空白知识库直接开题。</p>
          <div className="home-continue__actions">
            <Link className="primary-button" to="/knowledge-bases">开始第一次学习</Link>
            <Link className="quiet-button" to="/files">先导入资料</Link>
          </div>
        </div>
      ) : null}
      {item ? (
        <article className="home-continue__card">
          <GraduationCap size={18} aria-hidden="true" />
          <div>
            <h3>{item.topic || '未命名学习'}</h3>
            <dl className="home-continue__facts">
              <div><dt>资料范围</dt><dd>{item.scope_name ?? '资料范围不可用'} · {item.scope_file_count} 个文件</dd></div>
              <div><dt>会话状态</dt><dd>{sessionStatusLabel(item)}</dd></div>
              <div><dt>已作答数量</dt><dd>{item.answered_count} / {item.target_question_count}</dd></div>
              <div><dt>最近学习</dt><dd>{formatTime(item.updated_at)}</dd></div>
            </dl>
            <p className="home-continue__id">会话 {item.learning_session_id}</p>
            {sourceInvalid(item) ? (
              <p className="home-continue__reason" role="status">
                不能继续作答：{sourceStatusLabel(item.source_status)}。首页不会绕过资料校验。
                {item.answered_count > 0 ? '已保存的反馈仍可打开查看。' : '这次还没有可查看的反馈。'}
              </p>
            ) : null}
            <div className="home-continue__actions">
              {!sourceInvalid(item) && item.answered_count === 0 && item.status !== 'FAILED' ? (
                <Link className="primary-button" to={`/learning/session/${item.learning_session_id}`}>继续学习</Link>
              ) : null}
              {item.answered_count > 0 ? (
                <Link className="primary-button" to={`/learning/session/${item.learning_session_id}`}>查看反馈</Link>
              ) : null}
              {sourceInvalid(item) && item.answered_count === 0 ? (
                <Link className="quiet-button" to={`/learning/session/${item.learning_session_id}`}>查看原会话</Link>
              ) : null}
              <Link className="quiet-button" to="/history?tab=learning">学习历史</Link>
            </div>
          </div>
        </article>
      ) : null}
    </section>
  )
}

function knowledgeBaseStatusLabel(status: string): string {
  if (status === 'EMPTY') return '空知识库'
  if (status === 'PREPARING') return '成员待索引'
  if (status === 'PARTIAL') return '部分资料可用'
  if (status === 'READY') return '索引就绪'
  if (status === 'FAILED') return '索引失败'
  return status || '状态不可用'
}

function canUseKnowledgeBase(item: KnowledgeBaseItem): boolean {
  return item.status === 'READY' && item.available_file_count > 0
}

function fileStatusLabel(status: string): string {
  return {
    PARSED: '已解析',
    QUEUED: '待处理',
    PARSING: '处理中',
    IN_TRASH: '回收站',
    STORAGE_MISSING: '文件缺失',
    READY: '可用',
    PARSE_FAILED: '解析失败',
  }[status] ?? (status || '状态不可用')
}

function fileFailureText(file: FileItem): string {
  const parts = [fileStatusLabel(file.status)]
  if (file.parse_failure_stage) parts.push(`阶段 ${file.parse_failure_stage}`)
  if (file.parse_error_id) parts.push(`错误 ${file.parse_error_id}`)
  return parts.join(' · ')
}

function RecentKnowledgeBases() {
  const recentQuery = useQuery({
    queryKey: ['home-knowledge-bases'],
    queryFn: () => listKnowledgeBases(4),
    retry: false,
    staleTime: 0,
    refetchOnMount: 'always',
  })
  const items = (recentQuery.data?.items ?? []).slice(0, 4)

  return (
    <section className="home-recent" aria-labelledby="home-knowledge-title">
      <div className="home-recent__heading">
        <div>
          <span className="eyebrow">最近更新</span>
          <h2 id="home-knowledge-title">最近知识库</h2>
          <p>按知识库更新时间排列，最多 4 个。这里没有最近使用时间，打开首页不会记录使用，也不会建立索引。</p>
        </div>
        <Link className="quiet-button" to="/knowledge-bases">查看全部</Link>
      </div>
      {recentQuery.isLoading ? <div className="history-state" role="status"><LoaderCircle className="spin" size={16} /> 正在读取最近知识库</div> : null}
      {recentQuery.isError ? (
        <div className="history-state history-state--error" role="alert">
          <span>最近知识库暂时读不出来。</span>
          <button className="quiet-button" type="button" onClick={() => void recentQuery.refetch()}>重新加载</button>
        </div>
      ) : null}
      {!recentQuery.isLoading && !recentQuery.isError && items.length === 0 ? (
        <p className="home-recent__empty">还没有未回收的知识库。</p>
      ) : null}
      {items.length > 0 ? (
        <div className="home-recent__list">
          {items.map((item) => {
            const usable = canUseKnowledgeBase(item)
            const fileCount = typeof item.file_count === 'number' ? `${item.file_count} 个文件` : '文件数量不可用'
            return (
              <article className="home-recent__card" key={item.knowledge_base_id}>
                <BookOpen size={18} aria-hidden="true" />
                <div>
                  <h3><Link to={`/knowledge-bases/${item.knowledge_base_id}`}>{item.name}</Link></h3>
                  <p>{item.description?.trim() || '暂无简述'}</p>
                  <dl className="home-recent__facts">
                    <div><dt>文件数量</dt><dd>{fileCount}</dd></div>
                    <div><dt>索引状态</dt><dd>{knowledgeBaseStatusLabel(item.status)}</dd></div>
                    <div><dt>最近更新</dt><dd>{formatTime(item.updated_at)}</dd></div>
                  </dl>
                  {usable ? null : (
                    <p className="home-recent__reason" role="status">当前索引未就绪或没有可用文件，首页不能直接开始学习或提问。</p>
                  )}
                  <div className="home-recent__actions">
                    {usable ? (
                      <>
                        <Link to={`/learning/new?knowledge_base_id=${encodeURIComponent(item.knowledge_base_id)}`}>开始学习</Link>
                        <Link to={`/chat?knowledge_base_id=${encodeURIComponent(item.knowledge_base_id)}`}>提问</Link>
                      </>
                    ) : (
                      <Link to={`/knowledge-bases/${item.knowledge_base_id}`}>查看知识库</Link>
                    )}
                  </div>
                </div>
              </article>
            )
          })}
        </div>
      ) : null}
    </section>
  )
}

function RecentFiles() {
  const queryClient = useQueryClient()
  const [confirmingId, setConfirmingId] = useState('')
  const [retryError, setRetryError] = useState('')
  const recentQuery = useQuery({
    queryKey: ['home-files'],
    queryFn: () => listRecentFiles(5),
    retry: false,
    staleTime: 0,
    refetchOnMount: 'always',
  })
  const items = (recentQuery.data?.items ?? []).slice(0, 5)

  const confirmRetry = async (file: FileItem) => {
    setRetryError('')
    try {
      await apiRequest(`/api/v1/files/${file.file_id}/reprocess`, { method: 'POST' })
      setConfirmingId('')
      await queryClient.invalidateQueries({ queryKey: ['home-files'] })
    } catch (error) {
      setRetryError(error instanceof Error ? error.message : '重新处理没有提交成功')
    }
  }

  return (
    <section className="home-recent" aria-labelledby="home-files-title">
      <div className="home-recent__heading">
        <div>
          <span className="eyebrow">最近更新</span>
          <h2 id="home-files-title">最近文件</h2>
          <p>按文件更新时间排列，最多 5 个。这里没有最近打开时间。处理失败时先确认，才会复用原有的重新处理。</p>
        </div>
        <Link className="quiet-button" to="/files">查看全部</Link>
      </div>
      {recentQuery.isLoading ? <div className="history-state" role="status"><LoaderCircle className="spin" size={16} /> 正在读取最近文件</div> : null}
      {recentQuery.isError ? (
        <div className="history-state history-state--error" role="alert">
          <span>最近文件暂时读不出来。</span>
          <button className="quiet-button" type="button" onClick={() => void recentQuery.refetch()}>重新加载</button>
        </div>
      ) : null}
      {!recentQuery.isLoading && !recentQuery.isError && items.length === 0 ? (
        <p className="home-recent__empty">还没有未回收的文件。</p>
      ) : null}
      {items.length > 0 ? (
        <div className="home-recent__list">
          {items.map((file) => {
            const failed = file.status === 'PARSE_FAILED'
            const tags = file.tags?.map((tag) => tag.name).filter(Boolean) ?? []
            return (
              <article className="home-recent__card" key={file.file_id}>
                <FileText size={18} aria-hidden="true" />
                <div>
                  <h3><Link to={`/files/${file.file_id}`}>{file.display_name}</Link></h3>
                  <dl className="home-recent__facts">
                    <div><dt>类型</dt><dd>{file.document_type || '类型不可用'}</dd></div>
                    <div><dt>文件夹</dt><dd>{file.folder_name?.trim() || '未分类'}</dd></div>
                    <div><dt>标签</dt><dd>{tags.length > 0 ? tags.join('、') : '无标签'}</dd></div>
                    <div><dt>处理状态</dt><dd>{failed ? fileFailureText(file) : fileStatusLabel(file.status)}</dd></div>
                    <div><dt>最近更新</dt><dd>{formatTime(file.updated_at)}</dd></div>
                  </dl>
                  <div className="home-recent__actions">
                    <Link to={`/files/${file.file_id}`}>查看文件</Link>
                    {failed && file.can_reprocess && confirmingId !== file.file_id ? (
                      <button type="button" onClick={() => { setRetryError(''); setConfirmingId(file.file_id) }}>重试处理</button>
                    ) : null}
                    {failed && file.can_reprocess && confirmingId === file.file_id ? (
                      <button type="button" onClick={() => void confirmRetry(file)}>确认重试</button>
                    ) : null}
                  </div>
                  {confirmingId === file.file_id ? <p className="home-recent__reason" role="status">确认后才会提交重新处理，取消前不会创建任务。</p> : null}
                  {retryError && confirmingId === file.file_id ? <p className="home-recent__reason" role="alert">{retryError}</p> : null}
                </div>
              </article>
            )
          })}
        </div>
      ) : null}
    </section>
  )
}

function conversationScopeLabel(item: ConversationHistoryItem): string {
  if (item.current_mode === 'KNOWLEDGE_CHAT') return item.scope_name?.trim() || '知识库范围不可用'
  return '普通对话'
}

function RecentConversations() {
  const recentQuery = useQuery({
    queryKey: ['home-conversations'],
    queryFn: () => listConversationHistory(undefined, 5),
    retry: false,
    staleTime: 0,
    refetchOnMount: 'always',
  })
  const items = (recentQuery.data?.items ?? []).slice(0, 5)

  return (
    <section className="home-recent" aria-labelledby="home-conversations-title">
      <div className="home-recent__heading">
        <div>
          <span className="eyebrow">最近活动</span>
          <h2 id="home-conversations-title">最近对话</h2>
          <p>按对话最近活动时间排列，最多 5 个。打开原对话只读取已保存内容，不会从首页自动续聊。</p>
        </div>
        <Link className="quiet-button" to="/history">查看全部</Link>
      </div>
      {recentQuery.isLoading ? <div className="history-state" role="status"><LoaderCircle className="spin" size={16} /> 正在读取最近对话</div> : null}
      {recentQuery.isError ? (
        <div className="history-state history-state--error" role="alert">
          <span>最近对话暂时读不出来。</span>
          <button className="quiet-button" type="button" onClick={() => void recentQuery.refetch()}>重新加载</button>
        </div>
      ) : null}
      {!recentQuery.isLoading && !recentQuery.isError && items.length === 0 ? (
        <p className="home-recent__empty">还没有未回收的对话。</p>
      ) : null}
      {items.length > 0 ? (
        <div className="home-recent__list">
          {items.map((item) => {
            const sourceInvalid = item.source_status !== 'AVAILABLE' && item.source_status !== 'NOT_APPLICABLE'
            return (
              <article className="home-recent__card" key={item.conversation_id}>
                <MessageSquare size={18} aria-hidden="true" />
                <div>
                  <h3><Link to={`/chat/${item.conversation_id}`}>{item.title?.trim() || '未命名对话'}</Link></h3>
                  <p>{item.summary?.trim() || '暂无摘要'}</p>
                  <dl className="home-recent__facts">
                    <div><dt>范围</dt><dd>{conversationScopeLabel(item)}</dd></div>
                    <div><dt>最近活动</dt><dd>{formatTime(item.updated_at)}</dd></div>
                  </dl>
                  {sourceInvalid ? (
                    <p className="home-recent__reason" role="status">来源已失效：{sourceStatusLabel(item.source_status)}。可以阅读原对话，首页不会自动续聊。</p>
                  ) : null}
                  <div className="home-recent__actions">
                    <Link to={`/chat/${item.conversation_id}`}>查看对话</Link>
                  </div>
                </div>
              </article>
            )
          })}
        </div>
      ) : null}
    </section>
  )
}

export default function HomePage() {
  return (
    <section className="home-page">
      <header className="page-heading">
        <div>
          <span className="eyebrow">首页</span>
          <h1>欢迎回到 MindMate</h1>
          <p>从最近一次真实学习接着看，并读取最近更新的知识库、最近更新的文件和最近活动的对话。首页统计和任务摘要仍未在这里展开。</p>
        </div>
      </header>
      <ContinueLearning />
      <RecentKnowledgeBases />
      <RecentFiles />
      <RecentConversations />
      <section className="home-shortcuts" aria-labelledby="home-shortcuts-title">
        <div>
          <span className="eyebrow">快捷入口</span>
          <h2 id="home-shortcuts-title">快捷操作</h2>
          <p>四个入口只打开已有流程。未提交表单或未发送消息前，不会新建文件、知识库、对话或学习会话。</p>
        </div>
        <div className="home-shortcuts__actions">
          <Link className="primary-button" to="/learning/new"><GraduationCap size={16} aria-hidden="true" />开始学习</Link>
          <Link className="quiet-button" to="/chat"><MessageSquare size={16} aria-hidden="true" />AI 提问</Link>
          <Link className="quiet-button" to="/files"><FileUp size={16} aria-hidden="true" />导入文件</Link>
          <Link className="quiet-button" to="/knowledge-bases/new"><Plus size={16} aria-hidden="true" />创建知识库</Link>
        </div>
      </section>
    </section>
  )
}

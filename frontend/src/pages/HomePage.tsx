import { useQuery } from '@tanstack/react-query'
import { FileUp, GraduationCap, LoaderCircle, MessageSquare, Plus } from 'lucide-react'
import { Link } from 'react-router-dom'

import { listLearningHistory, type LearningHistoryItem } from '../api/history'
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

export default function HomePage() {
  return (
    <section className="home-page">
      <header className="page-heading">
        <div>
          <span className="eyebrow">首页</span>
          <h1>欢迎回到 MindMate</h1>
          <p>从最近一次真实学习接着看。其余首页统计、最近文件和任务摘要仍未在这里展开。</p>
        </div>
      </header>
      <ContinueLearning />
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

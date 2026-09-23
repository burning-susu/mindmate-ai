import { useQuery } from '@tanstack/react-query'
import { ArrowRight, BookOpen, Plus, RefreshCw } from 'lucide-react'
import { Link } from 'react-router-dom'

import { apiRequest } from '../api/client'
import type { KnowledgeBaseListResponse } from '../api/knowledgeBases'

const statusLabels: Record<string, string> = {
  EMPTY: '空知识库',
  PREPARING: '处理中',
  READY: '可用',
  PARTIAL: '部分可用',
  FAILED: '失败',
  NEEDS_REBUILD: '需要重建',
}

export default function KnowledgeBasesPage() {
  const query = useQuery({
    queryKey: ['knowledge-bases'],
    queryFn: () => apiRequest<KnowledgeBaseListResponse>('/api/v1/knowledge-bases'),
  })

  return (
    <section className="knowledge-page">
      <div className="page-heading">
        <div>
          <span className="eyebrow">本地资料空间</span>
          <h1>知识库</h1>
          <p>把资料组织成独立主题，索引能力将在下一批接入。</p>
        </div>
        <Link className="primary-button" to="/knowledge-bases/new"><Plus size={16} aria-hidden="true" />新建知识库</Link>
      </div>

      {query.isLoading && <div className="empty-state"><RefreshCw size={22} aria-hidden="true" /><strong>正在加载知识库</strong></div>}
      {query.isError && <div className="empty-state" role="alert"><strong>知识库加载失败</strong><span>{query.error instanceof Error ? query.error.message : '请稍后重试。'}</span><button className="quiet-button" type="button" onClick={() => void query.refetch()}>重试</button></div>}
      {!query.isLoading && !query.isError && query.data?.items.length === 0 && <div className="empty-state"><BookOpen size={26} aria-hidden="true" /><strong>还没有知识库</strong><span>先创建一个空知识库，之后再添加和索引文件。</span><Link className="primary-button" to="/knowledge-bases/new"><Plus size={16} aria-hidden="true" />创建第一个知识库</Link></div>}
      <div className="knowledge-grid">
        {query.data?.items.map((item) => (
          <Link className="knowledge-card" to={`/knowledge-bases/${item.knowledge_base_id}`} key={item.knowledge_base_id}>
            <div className="knowledge-mark" style={{ backgroundColor: item.color ?? '#176b87' }}><BookOpen size={20} aria-hidden="true" /></div>
            <div className="knowledge-card__body">
              <div className="knowledge-card__title"><strong>{item.name}</strong>{item.duplicate_name && <span className="duplicate-badge">同名</span>}</div>
              <p>{item.description || '暂无描述'}</p>
              <div className="knowledge-card__meta"><span>{statusLabels[item.status] ?? item.status}</span><span>{item.file_count} 个文件</span><ArrowRight size={15} aria-hidden="true" /></div>
            </div>
          </Link>
        ))}
      </div>
    </section>
  )
}

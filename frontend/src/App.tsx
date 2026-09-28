import { QueryClientProvider, useQuery } from '@tanstack/react-query'
import { Activity, BookOpen, Boxes, FileText, History, Home, Menu, MessageSquare, RefreshCw, ServerOff, Settings2, Trash2 } from 'lucide-react'
import { Link, NavLink, Route, Routes } from 'react-router-dom'
import { create } from 'zustand'

import { LocalBackendUnavailableError } from './api/client'
import GlobalTaskDrawer from './components/GlobalTaskDrawer'
import FileDetailPage from './pages/FileDetailPage'
import FilesPage from './pages/FilesPage'
import KnowledgeBaseDetailPage from './pages/KnowledgeBaseDetailPage'
import KnowledgeBaseNewPage from './pages/KnowledgeBaseNewPage'
import KnowledgeBasesPage from './pages/KnowledgeBasesPage'
import SettingsPage from './pages/SettingsPage'
import TrashPage from './pages/TrashPage'
import ChatPage from './pages/ChatPage'
import HistoryPage from './pages/HistoryPage'
import HomePage from './pages/HomePage'
import LearningNewPage from './pages/LearningNewPage'
import LearningSessionPage from './pages/LearningSessionPage'
import { queryClient } from './queryClient'
import './App.css'

type UiState = {
  sidebarOpen: boolean
  toggleSidebar: () => void
}

const useUiStore = create<UiState>((set) => ({
  sidebarOpen: true,
  toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
}))

const navigation = [
  { to: '/', label: '首页', icon: Home, end: true },
  { to: '/learning', label: '学习', icon: BookOpen },
  { to: '/chat', label: 'AI 对话', icon: MessageSquare },
  { to: '/knowledge-bases', label: '知识库', icon: Boxes },
  { to: '/files', label: '文件', icon: FileText },
]

function useBackendHealth() {
  return useQuery({
    queryKey: ['health'],
    queryFn: async () => {
      try {
        const response = await fetch('/api/v1/health', { credentials: 'same-origin', cache: 'no-store' })
        if (!response.ok) throw new LocalBackendUnavailableError()
        return await response.json() as { status: string; version: string }
      } catch (error) {
        if (error instanceof LocalBackendUnavailableError) throw error
        throw new LocalBackendUnavailableError()
      }
    },
    retry: false,
    staleTime: 5_000,
  })
}

function BackendStatus({ query }: { query: ReturnType<typeof useBackendHealth> }) {
  const { data, isError, isLoading } = query

  const label = isLoading ? '检查本地服务' : isError ? '本地服务未启动' : `本地服务 ${data?.version ?? ''}`
  return <span className={`status-dot ${isError ? 'status-dot--error' : ''}`}>{label}</span>
}

function BackendUnavailableState({ onRetry, busy }: { onRetry: () => void; busy: boolean }) {
  return (
    <section className="backend-blocked" role="alert" aria-labelledby="backend-blocked-title">
      <ServerOff size={28} aria-hidden="true" />
      <div>
        <span className="eyebrow">本地数据通道</span>
        <h1 id="backend-blocked-title">本地服务不可用</h1>
        <p>无法读取本地文件、知识库、历史和后台任务。当前不会修改本地数据；恢复服务后可以回到原 URL。</p>
        <div className="backend-blocked__actions">
          <button className="primary-button" type="button" disabled={busy} onClick={onRetry}>
            <RefreshCw size={15} aria-hidden="true" />
            {busy ? '正在重新连接' : '重新连接'}
          </button>
          <details className="backend-blocked__guide">
            <summary>查看本地启动说明</summary>
            <p>请按项目 README 的本地启动步骤启动 API 服务，并确认回环地址 <code>127.0.0.1:8000</code> 可访问；启动后回到这里点击“重新连接”。</p>
          </details>
        </div>
      </div>
    </section>
  )
}

function Placeholder({ title, description, action }: { title: string; description: string; action?: { to: string; label: string } }) {
  return (
    <section className="placeholder-panel">
      <span className="eyebrow">V1 开发基线</span>
      <h2>{title}</h2>
      <p>{description}</p>
      {action ? <Link className="quiet-button" to={action.to}>{action.label}</Link> : null}
    </section>
  )
}

function AppShell() {
  const { sidebarOpen, toggleSidebar } = useUiStore()
  const backendHealth = useBackendHealth()

  return (
    <div className={`app-shell ${sidebarOpen ? '' : 'app-shell--collapsed'}`}>
      <aside className="sidebar" aria-label="主导航">
        <div className="brand-block">
          <div className="brand-mark">M</div>
          {sidebarOpen && (
            <div>
              <strong>MindMate</strong>
              <span>个人知识工作台</span>
            </div>
          )}
        </div>
        <nav className="nav-list">
          {navigation.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end} className={({ isActive }) => `nav-item ${isActive ? 'nav-item--active' : ''}`}>
              <Icon size={18} aria-hidden="true" />
              {sidebarOpen && <span>{label}</span>}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <NavLink to="/history" className="nav-item">
            <History size={18} aria-hidden="true" />
            {sidebarOpen && <span>历史记录</span>}
          </NavLink>
          <NavLink to="/trash" className="nav-item">
            <Trash2 size={18} aria-hidden="true" />
            {sidebarOpen && <span>回收站</span>}
          </NavLink>
          <NavLink to="/settings" className="nav-item">
            <Settings2 size={18} aria-hidden="true" />
            {sidebarOpen && <span>设置</span>}
          </NavLink>
        </div>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <button className="icon-button" type="button" onClick={toggleSidebar} aria-label="折叠或展开侧栏" title="折叠或展开侧栏">
            <Menu size={18} aria-hidden="true" />
          </button>
          <div className="topbar-status">
            <Activity size={16} aria-hidden="true" />
            <BackendStatus query={backendHealth} />
          </div>
          <GlobalTaskDrawer />
        </header>
        {backendHealth.isError ? (
          <div className="content-area">
            <BackendUnavailableState onRetry={() => void backendHealth.refetch()} busy={backendHealth.isFetching} />
          </div>
        ) : (
          <div className="content-area">
            <Routes>
              <Route path="/" element={<HomePage />} />
              <Route path="/learning" element={<Placeholder title="学习" description="最小演示从已索引就绪的知识库进入，一次只做一题。打开本页不会创建学习会话。新建学习会话使用当前选择；Mock 仍是本地规则，在线出题和点评需要分别确认费用。这仍不是完整学习计划。" action={{ to: '/history?tab=learning', label: '学习历史' }} />} />
              <Route path="/learning/new" element={<LearningNewPage />} />
              <Route path="/learning/session/:sessionId" element={<LearningSessionPage />} />
              <Route path="/chat" element={<ChatPage />} />
              <Route path="/chat/:conversationId" element={<ChatPage />} />
              <Route path="/history" element={<HistoryPage />} />
              <Route path="/knowledge-bases" element={<KnowledgeBasesPage />} />
              <Route path="/knowledge-bases/new" element={<KnowledgeBaseNewPage />} />
              <Route path="/knowledge-bases/:knowledgeBaseId" element={<KnowledgeBaseDetailPage />} />
              <Route path="/files" element={<FilesPage />} />
              <Route path="/files/:fileId" element={<FileDetailPage />} />
              <Route path="/trash" element={<TrashPage />} />
              <Route path="/settings" element={<SettingsPage />} />
            </Routes>
          </div>
        )}
      </main>
    </div>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AppShell />
    </QueryClientProvider>
  )
}

import { QueryClientProvider, useQuery } from '@tanstack/react-query'
import { Activity, BookOpen, Boxes, FileText, History, Home, Menu, MessageSquare, Settings2, Trash2 } from 'lucide-react'
import { Link, NavLink, Route, Routes } from 'react-router-dom'
import { create } from 'zustand'

import { apiRequest } from './api/client'
import FileDetailPage from './pages/FileDetailPage'
import FilesPage from './pages/FilesPage'
import KnowledgeBaseDetailPage from './pages/KnowledgeBaseDetailPage'
import KnowledgeBaseNewPage from './pages/KnowledgeBaseNewPage'
import KnowledgeBasesPage from './pages/KnowledgeBasesPage'
import SettingsPage from './pages/SettingsPage'
import TrashPage from './pages/TrashPage'
import ChatPage from './pages/ChatPage'
import HistoryPage from './pages/HistoryPage'
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

function BackendStatus() {
  const { data, isError, isLoading } = useQuery({
    queryKey: ['health'],
    queryFn: () => apiRequest<{ status: string; version: string }>('/api/v1/health'),
    retry: false,
  })

  const label = isLoading ? '检查本地服务' : isError ? '本地服务未启动' : `本地服务 ${data?.version ?? ''}`
  return <span className={`status-dot ${isError ? 'status-dot--error' : ''}`}>{label}</span>
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
            <BackendStatus />
          </div>
        </header>
        <div className="content-area">
          <Routes>
            <Route path="/" element={<Placeholder title="欢迎回到 MindMate" description="阶段 0 工程基线已建立，下一步进入本地应用壳和安全运行验证。" />} />
            <Route path="/learning" element={<Placeholder title="学习" description="最小演示从已索引就绪的知识库进入，一次只做一题。打开本页不会创建学习会话。本地规则模拟演示，未调用真实 DeepSeek。" action={{ to: '/history?tab=learning', label: '学习历史' }} />} />
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

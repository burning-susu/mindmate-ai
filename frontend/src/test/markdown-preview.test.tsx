import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import MarkdownPreview from '../components/MarkdownPreview'

describe('MarkdownPreview', () => {
  it('renders Markdown as a readable document with headings, emphasis, lists, and tables', () => {
    render(<MarkdownPreview source={'# 面试题总结\n\n**核心结论**：先完成语义结构。\n\n## 模块成绩\n\n| 项目 | 结果 |\n| --- | --- |\n| A | 通过 |\n| B | 待完善 |\n\n- HTML\n- CSS'} />)

    expect(screen.getByRole('heading', { level: 1, name: '面试题总结' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 2, name: '模块成绩' })).toBeInTheDocument()
    expect(screen.getByText('核心结论')).toBeInTheDocument()
    expect(screen.getByRole('table')).toBeInTheDocument()
    expect(screen.getByRole('cell', { name: '待完善' })).toBeInTheDocument()
    expect(screen.getByRole('list')).toBeInTheDocument()
  })

  it('renders code literally and never creates elements from raw HTML', () => {
    const { container } = render(<MarkdownPreview source={'<script>alert(1)</script>\n\n```html\n<strong>raw</strong>\n```'} />)

    expect(container.querySelector('script')).toBeNull()
    expect(container.querySelector('.markdown-preview p')).toHaveTextContent('<script>alert(1)</script>')
    expect(container.querySelector('pre code')).toHaveTextContent('<strong>raw</strong>')
  })
})

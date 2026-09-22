import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { BrowserRouter } from 'react-router-dom'

import App from '../App'

describe('stage 0 application shell', () => {
  it('renders the primary navigation', () => {
    render(
      <BrowserRouter>
        <App />
      </BrowserRouter>,
    )

    expect(screen.getByText('MindMate')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '首页' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '学习' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'AI 对话' })).toBeInTheDocument()
  })
})

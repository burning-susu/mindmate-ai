import type { ElementType, ReactNode } from 'react'

type Block =
  | { type: 'heading'; level: number; text: string }
  | { type: 'paragraph'; text: string }
  | { type: 'quote'; text: string[] }
  | { type: 'list'; ordered: boolean; items: string[] }
  | { type: 'table'; header: string[]; rows: string[][] }
  | { type: 'code'; language: string; text: string }
  | { type: 'rule' }

function splitTableRow(line: string): string[] {
  return line.trim().replace(/^\|/, '').replace(/\|$/, '').split(/(?<!\\)\|/).map((cell) => cell.trim().replace(/\\\|/g, '|'))
}

function isTableDivider(line: string): boolean {
  const cells = splitTableRow(line)
  return cells.length > 0 && cells.every((cell) => /^:?-{3,}:?$/.test(cell.replace(/\s/g, '')))
}

function startsBlock(lines: string[], index: number): boolean {
  const line = lines[index] ?? ''
  return /^\s*$/.test(line)
    || /^\s{0,3}#{1,6}\s+/.test(line)
    || /^\s{0,3}(`{3,}|~{3,})/.test(line)
    || /^\s{0,3}>/.test(line)
    || /^\s{0,3}(?:[-+*]|\d+[.)])\s+/.test(line)
    || /^\s{0,3}(?:([-*_])(?:\s*\1){2,})\s*$/.test(line)
    || (index + 1 < lines.length && line.includes('|') && isTableDivider(lines[index + 1] ?? ''))
}

function parseBlocks(source: string): Block[] {
  const lines = source.replace(/\r\n?/g, '\n').split('\n')
  const blocks: Block[] = []
  let index = 0

  while (index < lines.length) {
    const line = lines[index] ?? ''
    if (!line.trim()) {
      index += 1
      continue
    }

    const fence = line.match(/^\s{0,3}(`{3,}|~{3,})\s*([\w+-]*)[^\n]*$/)
    if (fence) {
      const marker = fence[1] ?? '```'
      const closePattern = new RegExp(`^\\s{0,3}${marker[0]}{${marker.length},}\\s*$`)
      const code: string[] = []
      index += 1
      while (index < lines.length && !closePattern.test(lines[index] ?? '')) {
        code.push(lines[index] ?? '')
        index += 1
      }
      if (index < lines.length) index += 1
      blocks.push({ type: 'code', language: fence[2] ?? '', text: code.join('\n') })
      continue
    }

    const heading = line.match(/^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$/)
    if (heading) {
      blocks.push({ type: 'heading', level: heading[1]?.length ?? 1, text: heading[2] ?? '' })
      index += 1
      continue
    }

    if (/^\s{0,3}(?:(?:-\s*){3,}|(?:\*\s*){3,}|(?:_\s*){3,})$/.test(line)) {
      blocks.push({ type: 'rule' })
      index += 1
      continue
    }

    if (line.includes('|') && index + 1 < lines.length && isTableDivider(lines[index + 1] ?? '')) {
      const header = splitTableRow(line)
      index += 2
      const rows: string[][] = []
      while (index < lines.length && (lines[index] ?? '').includes('|') && (lines[index] ?? '').trim()) {
        rows.push(splitTableRow(lines[index] ?? ''))
        index += 1
      }
      blocks.push({ type: 'table', header, rows })
      continue
    }

    if (/^\s{0,3}>/.test(line)) {
      const quote: string[] = []
      while (index < lines.length && /^\s{0,3}>/.test(lines[index] ?? '')) {
        quote.push((lines[index] ?? '').replace(/^\s{0,3}> ?/, ''))
        index += 1
      }
      blocks.push({ type: 'quote', text: quote })
      continue
    }

    const listMatch = line.match(/^\s{0,3}([-+*]|\d+[.)])\s+(.+)$/)
    if (listMatch) {
      const ordered = /^\d/.test(listMatch[1] ?? '')
      const items: string[] = []
      while (index < lines.length) {
        const item = (lines[index] ?? '').match(/^\s{0,3}([-+*]|\d+[.)])\s+(.+)$/)
        if (!item || /^\d/.test(item[1] ?? '') !== ordered) break
        items.push(item[2] ?? '')
        index += 1
      }
      blocks.push({ type: 'list', ordered, items })
      continue
    }

    const paragraph: string[] = []
    while (index < lines.length && !startsBlock(lines, index)) {
      paragraph.push(lines[index] ?? '')
      index += 1
    }
    if (paragraph.length === 0) {
      paragraph.push(line)
      index += 1
    }
    blocks.push({ type: 'paragraph', text: paragraph.join(' ') })
  }

  return blocks
}

function renderInline(source: string, keyPrefix: string): ReactNode[] {
  const token = /(`+)(.+?)\1|\*\*(.+?)\*\*|__(.+?)__|~~(.+?)~~|\*(.+?)\*|_(.+?)_|!?\[([^\]]*)\]\(([^)\s]+)(?:\s+"[^"]*")?\)/g
  const output: ReactNode[] = []
  let cursor = 0
  let match: RegExpExecArray | null
  let key = 0

  while ((match = token.exec(source)) !== null) {
    if (match.index > cursor) output.push(source.slice(cursor, match.index))
    const value = match[0]
    if (match[1]) output.push(<code key={`${keyPrefix}-${key++}`}>{match[2]}</code>)
    else if (match[3] || match[4]) output.push(<strong key={`${keyPrefix}-${key++}`}>{renderInline(match[3] ?? match[4] ?? '', `${keyPrefix}-${key}`)}</strong>)
    else if (match[5]) output.push(<del key={`${keyPrefix}-${key++}`}>{renderInline(match[5], `${keyPrefix}-${key}`)}</del>)
    else if (match[6] || match[7]) output.push(<em key={`${keyPrefix}-${key++}`}>{renderInline(match[6] ?? match[7] ?? '', `${keyPrefix}-${key}`)}</em>)
    else output.push(<span key={`${keyPrefix}-${key++}`}>{match[8]}</span>)
    cursor = match.index + value.length
  }
  if (cursor < source.length) output.push(source.slice(cursor))
  return output
}

function renderBlocks(blocks: Block[], keyPrefix: string): ReactNode[] {
  return blocks.map((block, index) => {
    const key = `${keyPrefix}-${index}`
    if (block.type === 'heading') {
      const Tag = `h${block.level}` as ElementType
      return <Tag key={key}>{renderInline(block.text, key)}</Tag>
    }
    if (block.type === 'paragraph') return <p key={key}>{renderInline(block.text, key)}</p>
    if (block.type === 'rule') return <hr key={key} />
    if (block.type === 'quote') return <blockquote key={key}>{renderBlocks(parseBlocks(block.text.join('\n')), key)}</blockquote>
    if (block.type === 'code') return <pre key={key}><code>{block.text}</code></pre>
    if (block.type === 'list') {
      const List = block.ordered ? 'ol' : 'ul'
      return <List key={key}>{block.items.map((item, itemIndex) => <li key={`${key}-${itemIndex}`}>{renderInline(item, `${key}-${itemIndex}`)}</li>)}</List>
    }
    return (
      <div className="markdown-table-wrap" key={key}>
        <table>
          <thead><tr>{block.header.map((cell, cellIndex) => <th key={`${key}-head-${cellIndex}`}>{renderInline(cell, `${key}-head-${cellIndex}`)}</th>)}</tr></thead>
          <tbody>{block.rows.map((row, rowIndex) => <tr key={`${key}-row-${rowIndex}`}>{block.header.map((_, cellIndex) => <td key={`${key}-${rowIndex}-${cellIndex}`}>{renderInline(row[cellIndex] ?? '', `${key}-${rowIndex}-${cellIndex}`)}</td>)}</tr>)}</tbody>
        </table>
      </div>
    )
  })
}

export default function MarkdownPreview({ source }: { source: string }) {
  return <article className="markdown-preview">{renderBlocks(parseBlocks(source), 'markdown')}</article>
}

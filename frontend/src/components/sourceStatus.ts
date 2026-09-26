export function sourceStatusLabel(status: string): string {
  return {
    AVAILABLE: '当前可打开',
    NOT_APPLICABLE: '普通聊天',
    SOURCE_IN_TRASH: '文件已在回收站',
    SOURCE_DELETED: '来源已永久删除',
    SOURCE_OUT_OF_SCOPE: '来源已不在当前知识库范围',
    INDEX_VERSION_RETIRED: '索引已不再就绪',
    SOURCE_VERSION_STALE: '文件版本已变化',
    SOURCE_MAPPING_INVALID: '来源定位已失效',
    PARTIAL_SOURCE: '部分来源已失效',
  }[status] ?? '来源当前不可用'
}

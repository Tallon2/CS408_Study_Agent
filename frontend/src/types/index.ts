// API 响应类型定义

export interface TokenResponse {
  access_token: string
  token_type: string
  user_id: string
  username: string
}

export interface UserResponse {
  id: string
  username: string
  email: string | null
  created_at: string
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  timestamp?: string
}

export interface PipelineEvent {
  stage: 'intent' | 'rag' | 'tool'
    | 'rag:query_rewrite' | 'rag:bm25_results' | 'rag:vector_results'
    | 'rag:rrf_fusion' | 'rag:rerank_scores' | 'rag:score_gate'
  intent?: string
  tool?: string
  context_preview?: string
  tool_name?: string
  result_preview?: string
  // RAG 管线细粒度追踪字段
  step?: string
  original?: string
  rewritten?: string[]
  count?: number
  top_keywords?: string[]
  collections?: Record<string, number>
  total_before?: number
  total_after?: number
  top_score?: number
  method?: string
  scores?: number[]
  passed?: boolean
  threshold?: number
  max_score?: number
}

export interface TaskResponse {
  id: string
  plan_id: string
  title: string
  subject: string | null
  is_done: boolean
  due_date: string | null
  created_at: string
  done_at: string | null
}

export interface PlanResponse {
  id: string
  user_id: string
  title: string
  description: string | null
  is_active: boolean
  created_at: string
  tasks: TaskResponse[]
}

export interface KnowledgeBaseResponse {
  id: string
  name: string
  description: string | null
  doc_count: number
  created_at: string
  updated_at: string
}

export interface KnowledgeDocResponse {
  id: string
  kb_id: string
  filename: string
  file_type: string
  chunk_count: number
  file_size: number | null
  status: 'pending' | 'indexing' | 'indexed' | 'failed'
  created_at: string
}

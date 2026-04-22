<template>
  <div class="rag-panel" :class="{ 'rag-panel--active': hasEvents }">
    <div class="rag-panel__header">
      <span class="rag-panel__title">⚡ RAG 管线追踪</span>
      <a-tag v-if="isStreaming" color="processing">实时</a-tag>
      <a-tag v-else-if="hasEvents" color="success">完成</a-tag>
    </div>

    <div v-if="!hasEvents && !isStreaming" class="rag-panel__empty">
      <p>等待下一次对话...</p>
    </div>

    <div v-else class="rag-panel__steps">
      <!-- 步骤1：意图识别 -->
      <div class="rag-step" :class="getStepStatus('intent')">
        <div class="rag-step__icon">🎯</div>
        <div class="rag-step__body">
          <div class="rag-step__title">意图路由</div>
          <div v-if="intentEvent" class="rag-step__detail">
            <a-tag :color="getIntentColor(intentEvent.intent)">{{ intentEvent.intent }}</a-tag>
            <span v-if="intentEvent.tool" class="rag-step__tool">→ {{ intentEvent.tool }}</span>
          </div>
          <div v-else-if="isStreaming" class="rag-step__pending">分类中...</div>
        </div>
      </div>

      <!-- 步骤2：RAG 检索（汇总） -->
      <div class="rag-step" :class="getStepStatus('rag')">
        <div class="rag-step__icon">🔍</div>
        <div class="rag-step__body">
          <div class="rag-step__title">混合检索（向量+BM25+RRF）</div>
          <div v-if="ragEvent" class="rag-step__detail">
            <div class="rag-step__preview">{{ ragEvent.context_preview }}</div>
          </div>
          <div v-else-if="isStreaming && intentEvent" class="rag-step__pending">检索中...</div>
        </div>
      </div>

      <!-- RAG 管线细粒度步骤 -->
      <div v-if="hasRagTrace" class="rag-trace">
        <!-- Query 重写 -->
        <div v-if="queryRewriteEvent" class="rag-trace__item">
          <span class="rag-trace__label">📝 查询重写</span>
          <div class="rag-trace__content">
            <span class="rag-trace__original">{{ queryRewriteEvent.original }}</span>
            <template v-if="queryRewriteEvent.rewritten && queryRewriteEvent.rewritten.length > 1">
              <span class="rag-trace__arrow">→</span>
              <a-tag v-for="rw in queryRewriteEvent.rewritten.slice(1)" :key="rw" size="small" color="blue">{{ rw }}</a-tag>
            </template>
          </div>
        </div>

        <!-- BM25 结果 -->
        <div v-if="bm25Event" class="rag-trace__item">
          <span class="rag-trace__label">📋 BM25</span>
          <div class="rag-trace__content">
            <a-tag color="orange">{{ bm25Event.count }} 条</a-tag>
            <span v-if="bm25Event.top_keywords?.length" class="rag-trace__keywords">
              {{ bm25Event.top_keywords.join(', ') }}
            </span>
          </div>
        </div>

        <!-- 向量检索结果 -->
        <div v-if="vectorEvent" class="rag-trace__item">
          <span class="rag-trace__label">🧮 向量</span>
          <div class="rag-trace__content">
            <a-tag color="cyan">{{ vectorEvent.count }} 条</a-tag>
            <template v-if="vectorEvent.collections">
              <a-tag v-for="(cnt, coll) in vectorEvent.collections" :key="coll" size="small">{{ coll }}: {{ cnt }}</a-tag>
            </template>
          </div>
        </div>

        <!-- RRF 融合 -->
        <div v-if="rrfEvent" class="rag-trace__item">
          <span class="rag-trace__label">🔗 RRF融合</span>
          <div class="rag-trace__content">
            <span>{{ rrfEvent.total_before }} → {{ rrfEvent.total_after }} 条</span>
            <a-tag color="green" size="small">top={{ rrfEvent.top_score }}</a-tag>
          </div>
        </div>

        <!-- 评分门控 -->
        <div v-if="scoreGateEvent" class="rag-trace__item">
          <span class="rag-trace__label">🚦 门控</span>
          <div class="rag-trace__content">
            <a-tag :color="scoreGateEvent.passed ? 'success' : 'error'" size="small">
              {{ scoreGateEvent.passed ? '通过' : '未通过' }}
            </a-tag>
            <span class="rag-trace__score">阈值={{ scoreGateEvent.threshold }} / 最高={{ scoreGateEvent.max_score }}</span>
          </div>
        </div>

        <!-- Rerank 精排 -->
        <div v-if="rerankEvent" class="rag-trace__item">
          <span class="rag-trace__label">🏆 精排</span>
          <div class="rag-trace__content">
            <a-tag color="purple" size="small">{{ rerankEvent.method }}</a-tag>
            <span v-if="rerankEvent.scores?.length" class="rag-trace__scores">
              [{{ rerankEvent.scores.map((s: number) => s.toFixed(2)).join(', ') }}]
            </span>
          </div>
        </div>
      </div>

      <!-- 步骤3：工具执行 -->
      <div class="rag-step" :class="getStepStatus('tool')">
        <div class="rag-step__icon">🔧</div>
        <div class="rag-step__body">
          <div class="rag-step__title">工具执行</div>
          <div v-if="toolEvent" class="rag-step__detail">
            <a-tag color="purple">{{ toolEvent.tool_name }}</a-tag>
            <div class="rag-step__preview">{{ toolEvent.result_preview }}</div>
          </div>
          <div v-else-if="isStreaming && ragEvent" class="rag-step__pending">执行中...</div>
        </div>
      </div>

      <!-- 步骤4：LLM 生成 -->
      <div class="rag-step" :class="isDone ? 'rag-step--done' : isStreaming && toolEvent ? 'rag-step--active' : 'rag-step--waiting'">
        <div class="rag-step__icon">✨</div>
        <div class="rag-step__body">
          <div class="rag-step__title">LLM 生成回复</div>
          <div v-if="isDone" class="rag-step__detail">
            <a-tag color="success">完成</a-tag>
          </div>
          <div v-else-if="isStreaming && toolEvent" class="rag-step__pending">生成中...</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { PipelineEvent } from '@/types'

const props = defineProps<{
  events: PipelineEvent[]
  isStreaming: boolean
  isDone: boolean
}>()

const hasEvents = computed(() => props.events.length > 0 || props.isStreaming)
const intentEvent = computed(() => props.events.find(e => e.stage === 'intent'))
const ragEvent    = computed(() => props.events.find(e => e.stage === 'rag'))
const toolEvent   = computed(() => props.events.find(e => e.stage === 'tool'))

// RAG 管线细粒度事件
const queryRewriteEvent = computed(() => props.events.find(e => e.stage === 'rag:query_rewrite'))
const bm25Event         = computed(() => props.events.find(e => e.stage === 'rag:bm25_results'))
const vectorEvent       = computed(() => props.events.find(e => e.stage === 'rag:vector_results'))
const rrfEvent          = computed(() => props.events.find(e => e.stage === 'rag:rrf_fusion'))
const scoreGateEvent    = computed(() => props.events.find(e => e.stage === 'rag:score_gate'))
const rerankEvent       = computed(() => props.events.find(e => e.stage === 'rag:rerank_scores'))
const hasRagTrace       = computed(() =>
  queryRewriteEvent.value || bm25Event.value || vectorEvent.value ||
  rrfEvent.value || scoreGateEvent.value || rerankEvent.value
)

function getStepStatus(stage: string) {
  const stageOrder = { intent: 0, rag: 1, tool: 2 }
  const order = stageOrder[stage as keyof typeof stageOrder]
  const currentOrder = props.events.length > 0
    ? stageOrder[props.events[props.events.length - 1].stage as keyof typeof stageOrder] ?? -1
    : -1

  if (props.events.some(e => e.stage === stage)) return 'rag-step--done'
  if (props.isStreaming && order === currentOrder + 1) return 'rag-step--active'
  if (props.isStreaming && order <= currentOrder) return 'rag-step--done'
  return 'rag-step--waiting'
}

function getIntentColor(intent?: string) {
  return { study: 'blue', plan: 'green', review: 'orange', unknown: 'default' }[intent ?? ''] ?? 'default'
}
</script>

<style scoped>
.rag-panel {
  background: #fafafa;
  border: 1px solid #e8e8e8;
  border-radius: 12px;
  padding: 16px;
  transition: all 0.3s;
}
.rag-panel--active { border-color: #1890ff; box-shadow: 0 0 0 2px rgba(24,144,255,0.1); }
.rag-panel__header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  font-weight: 600;
  color: #1a1a2e;
}
.rag-panel__empty { text-align: center; color: #999; padding: 20px 0; font-size: 13px; }
.rag-panel__steps { display: flex; flex-direction: column; gap: 8px; }
.rag-step {
  display: flex;
  gap: 12px;
  padding: 10px 12px;
  border-radius: 8px;
  border: 1px solid transparent;
  transition: all 0.3s;
}
.rag-step--waiting { background: #f5f5f5; opacity: 0.5; }
.rag-step--active {
  background: #e6f4ff;
  border-color: #1890ff;
  animation: pulse 1.5s infinite;
}
.rag-step--done { background: #f6ffed; border-color: #52c41a; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.7} }
.rag-step__icon { font-size: 18px; line-height: 1.4; }
.rag-step__body { flex: 1; min-width: 0; }
.rag-step__title { font-size: 13px; font-weight: 600; color: #333; margin-bottom: 4px; }
.rag-step__detail { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.rag-step__tool { font-size: 12px; color: #666; }
.rag-step__preview {
  font-size: 12px;
  color: #666;
  background: white;
  border-radius: 4px;
  padding: 4px 8px;
  width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-top: 4px;
}
.rag-step__pending { font-size: 12px; color: #1890ff; }

/* RAG 管线细粒度追踪 */
.rag-trace {
  margin: 4px 0 4px 30px;
  padding: 8px 12px;
  background: #f0f5ff;
  border-left: 3px solid #1890ff;
  border-radius: 0 8px 8px 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.rag-trace__item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 12px;
  line-height: 1.6;
}
.rag-trace__label {
  flex-shrink: 0;
  font-weight: 600;
  color: #1a1a2e;
  min-width: 72px;
}
.rag-trace__content {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
  color: #555;
}
.rag-trace__original {
  color: #333;
  font-weight: 500;
}
.rag-trace__arrow {
  color: #1890ff;
  font-weight: 700;
  margin: 0 2px;
}
.rag-trace__keywords,
.rag-trace__score,
.rag-trace__scores {
  font-size: 11px;
  color: #888;
  font-family: 'Courier New', monospace;
}
</style>

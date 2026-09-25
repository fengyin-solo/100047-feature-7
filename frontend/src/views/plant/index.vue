<template>
  <section class="page" data-module="plant">
    <header class="page-head">
      <div>
        <h2>厂区单元管理</h2>
        <p class="page-desc">维护工艺单元，围绕单元编码、单元名称、处理工艺、设计处理量做登记、筛选与状态流转；汇总视图按单元编码与处理工艺统计处理量、班组与减量运行占比。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记工艺单元</button>
        <button class="btn" type="button" @click="exportRows">导出厂区单元清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in statCards" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <div class="view-tabs" role="tablist">
      <button
        class="tab"
        type="button"
        role="tab"
        :class="{ active: view === 'list' }"
        @click="switchView('list')"
      >
        单元列表
      </button>
      <button
        class="tab"
        type="button"
        role="tab"
        :class="{ active: view === 'summary' }"
        @click="switchView('summary')"
      >
        处理量与班组汇总
      </button>
    </div>

    <form class="filter-bar" @submit.prevent="applyFilters">
      <label class="filter-item">
        <span>单元编码/名称</span>
        <input v-model="draftFilters.keyword" placeholder="按单元编码或名称检索" />
      </label>
      <label class="filter-item">
        <span>处理工艺</span>
        <input v-model="draftFilters.craft" placeholder="按处理工艺检索" />
      </label>
      <label class="filter-item">
        <span>运行班组</span>
        <input v-model="draftFilters.team" placeholder="按运行班组检索" />
      </label>
      <label class="filter-item">
        <span>单元状态</span>
        <select v-model="draftFilters.status">
          <option value="">全部状态</option>
          <option v-for="option in statuses" :key="option" :value="option">{{ option }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <template v-if="view === 'list'">
      <table class="data-table">
        <thead>
          <tr>
            <th v-for="column in columns" :key="column">{{ column }}</th>
            <th>可执行动作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="String(row.id)">
            <td v-for="column in columns" :key="column">{{ displayCell(row, column) }}</td>
            <td class="row-actions">
              <button
                v-for="action in actions"
                :key="action"
                class="link"
                type="button"
                @click="runAction(action, row)"
              >
                {{ action }}
              </button>
            </td>
          </tr>
          <tr v-if="!rows.length">
            <td :colspan="columns.length + 1" class="empty-state">{{ emptyHint || '暂无厂区单元数据，可先登记工艺单元' }}</td>
          </tr>
        </tbody>
      </table>

      <footer class="page-foot">
        <span>共 {{ total }} 条厂区单元记录（与汇总视图同一筛选口径）</span>
        <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
      </footer>
    </template>

    <template v-else>
      <div v-if="summary" class="summary-wrap">
        <div class="summary-overview">
          <span>筛选后单元：<strong>{{ summary.total }}</strong> 个</span>
          <span>分组数：<strong>{{ summary.group_count }}</strong> 组</span>
          <span>设计处理量合计：<strong>{{ formatVolume(summary.design_total) }}</strong></span>
          <span>实际处理量合计：<strong>{{ formatVolume(summary.actual_total) }}</strong></span>
          <span>减量运行单元：<strong class="warn-text">{{ summary.reduced_total }}</strong> 个</span>
        </div>

        <h3 class="summary-title">分组结果（按单元编码 + 处理工艺）</h3>
        <div v-if="summary.groups.length" class="group-list">
          <article v-for="group in summary.groups" :key="`${group.code}@${group.craft}`" class="group-card">
            <header class="group-head">
              <div class="group-id">
                <span class="group-code">{{ group.code }}</span>
                <span class="group-craft">{{ group.craft }}</span>
                <span v-if="group.incomplete_group" class="tag tag-warn">分组字段不完整</span>
                <span v-if="group.reduced_count" class="tag tag-warn">减量运行 {{ group.reduced_count }} 个</span>
              </div>
              <div class="group-share">
                本组 {{ group.count }} 个单元，占筛选结果 <strong>{{ formatPercent(group.count_ratio) }}</strong>
              </div>
            </header>

            <div class="ratio-lines">
              <div class="ratio-line">
                <span class="ratio-label">设计处理量</span>
                <div class="ratio-bar"><i :style="{ width: barWidth(group.design_ratio) }"></i></div>
                <span class="ratio-value">{{ formatVolume(group.design_total) }} · 占 {{ formatPercent(group.design_ratio) }}</span>
              </div>
              <div class="ratio-line">
                <span class="ratio-label">实际处理量</span>
                <div class="ratio-bar actual"><i :style="{ width: barWidth(group.actual_ratio) }"></i></div>
                <span class="ratio-value">{{ formatVolume(group.actual_total) }} · 占 {{ formatPercent(group.actual_ratio) }}</span>
              </div>
              <p v-if="group.design_missing_count || group.actual_missing_count" class="group-note">
                本组有
                <template v-if="group.design_missing_count"> {{ group.design_missing_count }} 个单元设计处理量为空</template>
                <template v-if="group.design_missing_count && group.actual_missing_count">、</template>
                <template v-if="group.actual_missing_count">{{ group.actual_missing_count }} 个单元实际处理量为空</template>
                ，未计入对应合计，明细见下方单元清单。
              </p>
            </div>

            <div class="team-line">
              <span class="team-label">运行班组：</span>
              <span v-for="team in group.teams" :key="team.team" class="team-chip">
                {{ team.team }} {{ team.count }} 人单元
                <em v-if="team.actual_count">· 实际 {{ formatVolume(team.actual_total) }}</em>
                <em v-if="team.reduced_count" class="warn-text">· 减量 {{ team.reduced_count }}</em>
              </span>
            </div>

            <table class="data-table sub-table">
              <thead>
                <tr>
                  <th>单元编码</th>
                  <th>单元名称</th>
                  <th>设计处理量</th>
                  <th>实际处理量</th>
                  <th>运行班组</th>
                  <th>投运日期</th>
                  <th>单元状态</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="unit in group.units" :key="String(unit.id)">
                  <td>{{ unit.code || '—' }}</td>
                  <td>{{ unit.name || '—' }}</td>
                  <td>
                    {{ unit.design === null ? '未填写' : formatVolume(unit.design) }}
                  </td>
                  <td :class="{ 'cell-missing': unit.actual_missing }">
                    {{ unit.actual === null ? '未填写' : formatVolume(unit.actual) }}
                  </td>
                  <td>{{ unit.team }}</td>
                  <td>{{ unit.commission_date || '—' }}</td>
                  <td>
                    <span :class="{ 'status-reduced': unit.reduced }">{{ unit.status || '—' }}</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </article>
        </div>
        <div v-else class="empty-block">{{ emptyHint || '当前筛选条件下没有分组数据' }}</div>

        <section class="issue-panel">
          <h3 class="summary-title">数据说明（逐条列出，不静默处理）</h3>
          <ul v-if="summary.issues.length" class="issue-list">
            <li v-for="(issue, index) in summary.issues" :key="index" :class="['issue-item', `issue-${issue.level}`]">
              <span class="issue-dot"></span>{{ issue.message }}
            </li>
          </ul>
          <p v-else class="empty-hint">本次汇总未发现分组缺数据、处理量为空或重复编码问题。</p>
        </section>
      </div>

      <footer class="page-foot">
        <span>汇总数量与单元列表页口径一致，均基于当前筛选条件</span>
        <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
      </footer>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { request } from '@/api/client'

type Row = Record<string, string | number | boolean | null>
type ViewMode = 'list' | 'summary'

interface Filters {
  keyword: string
  craft: string
  status: string
  team: string
}
interface SummaryUnit {
  id: number | null
  code: string
  name: string
  design: number | null
  actual: number | null
  design_missing: boolean
  actual_missing: boolean
  team: string
  status: string
  reduced: boolean
  commission_date: string
}
interface SummaryGroup {
  code: string
  craft: string
  incomplete_group: boolean
  count: number
  count_ratio: number
  design_total: number
  actual_total: number
  design_ratio: number
  actual_ratio: number
  design_missing_count: number
  actual_missing_count: number
  reduced_count: number
  teams: Array<{ team: string; count: number; actual_total: number; actual_count: number; reduced_count: number }>
  units: SummaryUnit[]
}
interface SummaryIssue {
  level: 'info' | 'warning' | 'danger'
  kind: string
  message: string
}
interface Summary {
  total: number
  group_count: number
  design_total: number
  actual_total: number
  reduced_total: number
  groups: SummaryGroup[]
  issues: SummaryIssue[]
  filters: Filters
}

const ENDPOINT = '/api/plant'
const columns = ['单元编码', '单元名称', '处理工艺', '设计处理量', '实际处理量', '运行班组', '投运日期', '单元状态']
const actions = ['完成调试', '安排减量', '停用单元']
const statuses = ['待调试', '正常运行', '减量运行', '已停用']

const route = useRoute()
const router = useRouter()

const rows = ref<Row[]>([])
const total = ref(0)
const summary = ref<Summary | null>(null)
const errorMessage = ref('')
const view = ref<ViewMode>('list')
const filters = ref<Filters>({ keyword: '', craft: '', status: '', team: '' })
const draftFilters = ref<Filters>({ keyword: '', craft: '', status: '', team: '' })

const statCards = computed(() => {
  const data = summary.value
  return [
    { label: '筛选后单元', value: data ? data.total : 0 },
    { label: '减量运行单元', value: data ? data.reduced_total : 0 },
    { label: '设计处理总量', value: data ? formatVolume(data.design_total) : 0 },
    { label: '实际处理总量', value: data ? formatVolume(data.actual_total) : 0 },
  ]
})

const emptyHint = computed(() => {
  const active = Object.entries(filters.value)
    .filter(([, value]) => value)
    .map(([key, value]) => `${FILTER_LABELS[key as keyof Filters]}「${value}」`)
  if (!active.length) return ''
  return `当前筛选条件（${active.join('、')}）下没有厂区单元数据，可重置条件后再查询`
})

const FILTER_LABELS: Record<keyof Filters, string> = {
  keyword: '单元编码/名称',
  craft: '处理工艺',
  status: '单元状态',
  team: '运行班组',
}

function displayCell(row: Row, column: string): string | number | boolean | null {
  if (column === '单元状态') {
    return (row.status as string) || '—'
  }
  const value = row[column]
  return value === null || value === undefined || value === '' ? '—' : value
}

function formatVolume(value: number | null | undefined): string | number {
  if (value === null || value === undefined) return '—'
  return Number.isInteger(value) ? value : value.toFixed(2)
}

function formatPercent(ratio: number): string {
  return `${(ratio * 100).toFixed(1)}%`
}

function barWidth(ratio: number): string {
  const width = Math.max(0, Math.min(1, ratio)) * 100
  return `${Math.round(width)}%`
}

function readQuery(): { view: ViewMode; filters: Filters } {
  const pick = (key: string) => (typeof route.query[key] === 'string' ? (route.query[key] as string) : '')
  return {
    view: route.query.view === 'summary' ? 'summary' : 'list',
    filters: {
      keyword: pick('keyword'),
      craft: pick('craft'),
      status: pick('status'),
      team: pick('team'),
    },
  }
}

function syncQuery() {
  // 用 URL 承载视图与筛选条件，页面刷新后仍能恢复出同一组结果。
  const query: Record<string, string> = { view: view.value }
  for (const [key, value] of Object.entries(filters.value)) {
    if (value) query[key] = value
  }
  void router.replace({ name: 'plant', query })
}

function buildQuery(): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(filters.value)) {
    if (value) params.set(key, value)
  }
  return params.toString()
}

async function loadSummary() {
  const query = buildQuery()
  const response = await request(`${ENDPOINT}/summary${query ? `?${query}` : ''}`)
  if (!response.ok) {
    throw new Error('处理量与班组汇总读取失败')
  }
  summary.value = (await response.json()) as Summary
}

async function loadList() {
  const query = buildQuery()
  const response = await request(`${ENDPOINT}${query ? `?${query}` : ''}`)
  if (!response.ok) {
    throw new Error('工艺单元列表读取失败')
  }
  const payload = await response.json()
  rows.value = payload.items ?? []
  total.value = payload.total ?? rows.value.length
}

async function reload() {
  errorMessage.value = ''
  syncQuery()
  try {
    // 汇总数字与列表共用同一筛选口径，两个视图都先取一份汇总保证卡片一致。
    await Promise.all([loadSummary(), view.value === 'list' ? loadList() : Promise.resolve()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '厂区单元数据读取失败'
  }
}

function applyFilters() {
  filters.value = { ...draftFilters.value }
  void reload()
}

function resetFilters() {
  const cleared: Filters = { keyword: '', craft: '', status: '', team: '' }
  draftFilters.value = { ...cleared }
  filters.value = cleared
  void reload()
}

function switchView(next: ViewMode) {
  if (view.value === next) return
  view.value = next
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '工艺单元登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    if (!response.ok) {
      throw new Error('厂区单元动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '厂区单元操作失败'
  }
}

onMounted(() => {
  const initial = readQuery()
  view.value = initial.view
  filters.value = initial.filters
  draftFilters.value = { ...initial.filters }
  void reload()
})
</script>

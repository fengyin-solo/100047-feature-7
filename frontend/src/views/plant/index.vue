<template>
  <section class="page" data-module="plant">
    <header class="page-head">
      <div>
        <h2>厂区单元管理</h2>
        <p class="page-desc">维护工艺单元，围绕单元编码、单元名称、处理工艺、设计处理量做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记工艺单元</button>
        <button class="btn" type="button" @click="exportRows">导出厂区单元清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
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
          <td :colspan="columns.length + 1" class="empty-state">暂无厂区单元数据，可先登记工艺单元</td>
        </tr>
      </tbody>
    </table>

    <section class="summary-block">
      <header class="summary-head">
        <h3>处理量与班组汇总</h3>
        <p class="page-desc">
          按单元编码与处理工艺分组，与上方列表同一筛选口径，共 {{ summaryTotal }} 条单元记录。
        </p>
      </header>
      <table class="data-table">
        <thead>
          <tr>
            <th v-for="column in summaryColumns" :key="column">{{ column }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="group in summaryGroups" :key="`${group.单元编码}-${group.处理工艺}`">
            <td>{{ group.单元编码 }}</td>
            <td>{{ group.处理工艺 }}</td>
            <td>{{ group.运行班组.length ? group.运行班组.join('、') : '—' }}</td>
            <td>{{ group.单元数量 }}</td>
            <td>{{ group.设计处理量合计 ?? '—' }}</td>
            <td>{{ group.实际处理量合计 ?? '—' }}</td>
            <td>{{ group.减量运行单元.length ? group.减量运行单元.join('、') : '无' }}</td>
            <td>{{ group.占比 }}</td>
          </tr>
          <tr v-if="!summaryGroups.length">
            <td :colspan="summaryColumns.length" class="empty-state">当前筛选条件下没有可分组的数据</td>
          </tr>
        </tbody>
      </table>
      <ul v-if="summaryNotes.length" class="note-list">
        <li v-for="(note, index) in summaryNotes" :key="index">{{ note }}</li>
      </ul>
    </section>

    <footer class="page-foot">
      <span>共 {{ total }} 条厂区单元记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

type SummaryGroup = {
  单元编码: string
  处理工艺: string
  运行班组: string[]
  单元数量: number
  设计处理量合计: number | null
  实际处理量合计: number | null
  减量运行单元: string[]
  占比: string
}

const ENDPOINT = '/api/plant'
const columns = ["单元编码", "单元名称", "处理工艺", "设计处理量", "实际处理量", "运行班组", "投运日期", "单元状态"]
const actions = ["完成调试", "安排减量", "停用单元"]
const statuses = ["待调试", "正常运行", "减量运行", "已停用"]
const stats = [{"label": "运行单元", "value": 0}, {"label": "减量运行单元", "value": 0}, {"label": "设计处理总量", "value": 0}]
const summaryColumns = ["单元编码", "处理工艺", "运行班组", "单元数量", "设计处理量合计", "实际处理量合计", "减量运行单元", "占比"]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)
const summaryGroups = ref<SummaryGroup[]>([])
const summaryNotes = ref<string[]>([])
const summaryTotal = ref(0)

function resetFilters() {
  filters.value = {}
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

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const [listResponse, summaryResponse] = await Promise.all([
      request(`${ENDPOINT}?${query}`),
      request(`${ENDPOINT}/summary?${query}`),
    ])
    if (!listResponse.ok) {
      throw new Error('工艺单元列表读取失败')
    }
    const payload = await listResponse.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    if (!summaryResponse.ok) {
      throw new Error('处理量与班组汇总读取失败')
    }
    const summary = await summaryResponse.json()
    summaryGroups.value = summary.groups ?? []
    summaryNotes.value = summary.notes ?? []
    summaryTotal.value = summary.total ?? 0
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '厂区单元列表读取失败'
  }
}

onMounted(reload)
</script>

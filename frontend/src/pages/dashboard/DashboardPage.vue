<template>
  <div>
    <h1>{{ t('dash.title') }}</h1>

    <div v-if="loading" class="di-empty">{{ t('dash.loading') }}</div>

    <template v-else>
      <div class="di-kpi-row">
        <div class="di-card di-kpi"><div class="di-kpi-num">{{ stats.total }}</div><div class="di-kpi-label">{{ t('dash.total') }}</div></div>
        <div class="di-kpi-row-item di-card di-kpi"><div class="di-kpi-num">{{ stats.recognized }}</div><div class="di-kpi-label">{{ t('dash.recognized') }}</div></div>
        <div class="di-card di-kpi"><div class="di-kpi-num">{{ stats.processing }}</div><div class="di-kpi-label">{{ t('dash.processing') }}</div></div>
        <div class="di-card di-kpi"><div class="di-kpi-num">{{ stats.pending }}</div><div class="di-kpi-label">{{ t('dash.pending') }}</div></div>
        <div class="di-card di-kpi"><div class="di-kpi-num">{{ stats.failed }}</div><div class="di-kpi-label">{{ t('dash.failed') }}</div></div>
      </div>

      <div class="di-card">
        <h3>{{ t('dash.byType') }}</h3>
        <div v-if="!recognizedRows.length" class="di-empty" style="padding:12px 0">{{ t('dash.none') }}</div>
        <div v-for="row in recognizedRows" :key="row.document_type" class="di-bar-row">
          <span class="di-bar-label">{{ typeLabel(row.document_type) }}</span>
          <div class="di-bar-track"><div class="di-bar-fill" :style="{ width: pct(row.cnt, maxByType) + '%' }" /></div>
          <span class="di-bar-val">{{ row.cnt }}</span>
        </div>
      </div>

      <div class="di-card">
        <h3>{{ t('dash.health') }}</h3>
        <div class="di-health-grid">
          <div v-for="p in health" :key="p.provider" class="di-health-card">
            <div class="di-health-top">
              <strong>{{ p.provider }}</strong>
              <span class="di-badge" :class="p.success_rate >= 90 ? 'pass' : p.success_rate >= 50 ? 'pending' : 'fail'">
                {{ p.success_rate != null ? p.success_rate + '%' : 'no data' }}
              </span>
            </div>
            <div class="di-stat">{{ p.total || 0 }} {{ t('dash.calls') }} · {{ p.total_tokens || 0 }} {{ t('home.tokens') }}</div>
          </div>
          <div v-if="!health.length" class="di-empty" style="padding:12px 0">{{ t('dash.noHealth') }}</div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import * as api from '@/api/frappe'
import { t } from '@/i18n'

const stats = ref({ total: 0, ready: 0, recognized: 0, processing: 0, pending: 0, failed: 0, by_type: [], recognized_by_type: [] })
const health = ref([])
const loading = ref(true)

const recognizedRows = computed(() => stats.value.recognized_by_type || [])
const maxByType = computed(() => Math.max(1, ...recognizedRows.value.map(r => r.cnt)))

function typeLabel(name) {
  const key = 'type.' + name
  const label = t(key)
  return label === key ? (name || '—') : label
}
function pct(n, max) { return Math.round((n / max) * 100) }

onMounted(async () => {
  try {
    const [s, h] = await Promise.all([
      api.getDocumentStats(),
      api.getProviderHealthStats().catch(() => [])
    ])
    stats.value = s
    health.value = h || []
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
h1 { font-size: 22px; margin: 0 0 16px; color: var(--di-navy); }
.di-kpi-row { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin-bottom: 18px; }
.di-kpi { text-align: center; }
.di-kpi-num { font-size: 26px; font-weight: 700; color: var(--di-navy); }
.di-kpi-label { font-size: 12px; color: var(--di-muted); margin-top: 2px; }
.di-detail-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 14px; }
h3 { font-size: 14px; margin: 0 0 12px; color: var(--di-navy); }
.di-bar-row { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; font-size: 13px; }
.di-bar-label { width: 90px; flex-shrink: 0; }
.di-bar-track { flex: 1; height: 8px; background: #e5e7eb; border-radius: 4px; overflow: hidden; }
.di-bar-fill { height: 100%; background: var(--di-blue); border-radius: 4px; }
.di-bar-val { width: 28px; text-align: right; color: var(--di-muted); }
.di-usage-line { display: flex; justify-content: space-between; font-size: 13px; margin-bottom: 6px; }
.di-item-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.di-item-table th, .di-item-table td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--di-border); }
.di-health-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 10px; }
.di-health-card { border: 1px solid var(--di-border); border-radius: 8px; padding: 10px 12px; }
.di-health-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; text-transform: capitalize; }
.di-stat { font-size: 11px; color: var(--di-muted); }
.di-card { margin-bottom: 14px; }

@media (max-width: 700px) {
  .di-kpi-row { grid-template-columns: repeat(2, 1fr); }
  .di-detail-grid { grid-template-columns: 1fr; }
}
</style>

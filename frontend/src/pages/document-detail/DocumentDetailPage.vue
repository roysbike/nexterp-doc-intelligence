<template>
  <div v-if="loading" class="di-empty">{{ t('detail.loading') }}</div>

  <div v-else-if="doc">
    <router-link to="/doc-intelligence/home" class="di-back">{{ t('detail.back') }}</router-link>

    <div class="di-card di-detail-head">
      <div>
        <h1>{{ doc.title }}</h1>
        <div class="di-detail-meta">
          <span class="di-badge" :class="doc.status.toLowerCase()">{{ t('status.' + doc.status) }}</span>
          <span>{{ t('type.' + doc.document_type) }}</span>
          <span v-if="doc.source_format">{{ doc.source_format }}</span>
          <span v-if="doc.provider_used">{{ t('home.via') }} {{ doc.provider_used }}</span>
          <span v-if="doc.token_count">{{ doc.token_count }} {{ t('home.tokens') }}</span>
          <span v-if="hasCost(doc)">{{ formatAed(doc.cost_aed) }}</span>
        </div>
      </div>
      <div class="di-detail-actions">
        <button v-if="doc.status === 'Ready'" class="di-btn primary" @click="showCreate = true">
          {{ t('detail.create') }}
        </button>
        <button class="di-btn danger" :disabled="deleting" @click="confirmDelete">
          {{ deleting ? t('detail.deleting') : (confirmingDelete ? t('detail.confirmDelete') : t('detail.delete')) }}
        </button>
      </div>
    </div>

    <div v-if="doc.status !== 'Ready'" class="di-card di-notready">
      {{ t('detail.notReady') }} <strong>{{ t('status.' + doc.status) }}</strong>
    </div>

    <div class="di-detail-grid">
      <div class="di-card" v-if="doc.summary">
        <h3>{{ t('detail.summary') }}</h3>
        <p class="di-pre">{{ doc.summary }}</p>
      </div>
      <div class="di-card" v-if="doc.key_entities">
        <h3>{{ t('detail.entities') }}</h3>
        <p class="di-pre">{{ doc.key_entities }}</p>
      </div>
    </div>

    <div class="di-card" v-if="doc.extracted_table_parsed && doc.extracted_table_parsed.length">
      <h3>{{ t('detail.table') }}</h3>
      <table class="di-item-table">
        <thead>
          <tr><th v-for="col in tableCols" :key="col">{{ col }}</th></tr>
        </thead>
        <tbody>
          <tr v-for="(row, i) in doc.extracted_table_parsed" :key="i">
            <td v-for="col in tableCols" :key="col">{{ row[col] }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="di-card" v-if="doc.status === 'Ready'">
      <h3>{{ t('detail.ask') }}</h3>
      <div v-if="doc.user_question" class="di-qa">
        <div class="di-qa-q">Q: {{ doc.user_question }}</div>
        <div class="di-qa-a">{{ doc.ai_answer }}</div>
      </div>
      <div class="di-ask-row">
        <input v-model="question" class="di-input" :placeholder="t('detail.askPlaceholder')" @keyup.enter="ask" />
        <button class="di-btn primary" :disabled="asking || !question" @click="ask">
          {{ asking ? t('detail.asking') : t('detail.askBtn') }}
        </button>
      </div>
      <div v-if="askError" class="di-error" style="margin-top:10px">{{ askError }}</div>
    </div>

    <div class="di-card" v-if="doc.status === 'Ready'">
      <h3>{{ t('detail.compare') }}</h3>
      <div class="di-ask-row">
        <select v-model="compareTarget" class="di-select">
          <option value="">{{ t('detail.chooseDoc') }}</option>
          <option v-for="d in otherReadyDocs" :key="d.name" :value="d.name">{{ d.title }}</option>
        </select>
        <input v-model="compareAspect" class="di-input" :placeholder="t('detail.aspect')" style="max-width:220px" />
        <button class="di-btn primary" :disabled="comparing || !compareTarget" @click="compare">
          {{ comparing ? t('detail.comparing') : t('detail.compareBtn') }}
        </button>
      </div>
      <div v-if="compareError" class="di-error" style="margin-top:10px">{{ compareError }}</div>
      <div v-if="compareResult" class="di-compare-result">
        <p class="di-pre">{{ compareResult.summary }}</p>
        <div v-if="compareResult.similarities?.length">
          <strong>{{ t('detail.similarities') }}</strong>
          <ul><li v-for="(s, i) in compareResult.similarities" :key="i">{{ s }}</li></ul>
        </div>
        <div v-if="compareResult.differences?.length">
          <strong>{{ t('detail.differences') }}</strong>
          <table class="di-item-table">
            <thead><tr><th>{{ t('detail.aspectCol') }}</th><th>{{ doc.title }}</th><th>{{ compareTargetTitle }}</th></tr></thead>
            <tbody>
              <tr v-for="(d, i) in compareResult.differences" :key="i">
                <td>{{ d.aspect }}</td><td>{{ d.doc_a }}</td><td>{{ d.doc_b }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-if="compareResult.recommendation" class="di-pre"><strong>{{ t('detail.recommendation') }}</strong> {{ compareResult.recommendation }}</p>
      </div>
    </div>

    <details class="di-card" v-if="doc.raw_text">
      <summary>{{ t('detail.raw') }}</summary>
      <p class="di-pre">{{ doc.raw_text }}</p>
    </details>

    <CreateRecordDialog v-if="showCreate" :doc-name="doc.name" @close="showCreate = false" @created="onCreated" />
  </div>

  <div v-else class="di-empty">{{ t('detail.missing') }}</div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import * as api from '@/api/frappe'
import CreateRecordDialog from './CreateRecordDialog.vue'
import { t } from '@/i18n'

const props = defineProps({ name: { type: String, required: true } })
const router = useRouter()

const doc = ref(null)
const loading = ref(true)
const question = ref('')
const asking = ref(false)
const askError = ref('')

const compareTarget = ref('')
const compareAspect = ref('')
const comparing = ref(false)
const compareError = ref('')
const compareResult = ref(null)
const otherReadyDocs = ref([])

const showCreate = ref(false)

const deleting = ref(false)
const confirmingDelete = ref(false)
let confirmResetTimer = null

function confirmDelete() {
  if (!confirmingDelete.value) {
    confirmingDelete.value = true
    confirmResetTimer = setTimeout(() => { confirmingDelete.value = false }, 4000)
    return
  }
  clearTimeout(confirmResetTimer)
  deleting.value = true
  api.deleteDocument(props.name)
    .then(() => router.push('/doc-intelligence/home'))
    .catch(err => {
      deleting.value = false
      confirmingDelete.value = false
      alert(err.message || 'Could not delete this document.')
    })
}

const compareTargetTitle = computed(() =>
  otherReadyDocs.value.find(d => d.name === compareTarget.value)?.title || 'Other document'
)

const tableCols = computed(() => {
  const rows = doc.value?.extracted_table_parsed
  return rows && rows.length ? Object.keys(rows[0]) : []
})

function hasCost(row) {
  return row && row.cost_aed !== null && row.cost_aed !== undefined && row.cost_aed !== ''
}

function formatAed(value) {
  const amount = Number(value)
  if (Number.isNaN(amount)) return ''
  return `${amount.toFixed(4)} AED`
}

async function load() {
  loading.value = true
  try {
    doc.value = await api.getDocument(props.name)
  } catch {
    doc.value = null
  } finally {
    loading.value = false
  }
}

async function loadOtherDocs() {
  const res = await api.listDocuments({ status: 'Ready', limit: 50 })
  otherReadyDocs.value = (res.data || []).filter(d => d.name !== props.name)
}

async function ask() {
  asking.value = true
  askError.value = ''
  try {
    const res = await api.askDocument(props.name, question.value)
    doc.value.user_question = question.value
    doc.value.ai_answer = res.answer
    question.value = ''
  } catch (err) {
    askError.value = err.message
  } finally {
    asking.value = false
  }
}

async function compare() {
  comparing.value = true
  compareError.value = ''
  compareResult.value = null
  try {
    compareResult.value = await api.compareDocuments(props.name, compareTarget.value, compareAspect.value || null)
  } catch (err) {
    compareError.value = err.message
  } finally {
    comparing.value = false
  }
}

function onCreated() {
  // leave the success step visible inside the dialog; user closes manually
}

onMounted(() => { load(); loadOtherDocs() })
watch(() => props.name, () => { load(); loadOtherDocs() })
</script>

<style scoped>
.di-back { color: var(--di-blue); text-decoration: none; font-size: 13px; display: inline-block; margin-bottom: 12px; }
.di-detail-head { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 14px; gap: 12px; flex-wrap: wrap; }
.di-detail-head h1 { font-size: 20px; margin: 0 0 6px; color: var(--di-navy); }
.di-detail-actions { display: flex; gap: 10px; flex-wrap: wrap; }
.di-detail-meta { display: flex; gap: 10px; align-items: center; font-size: 13px; color: var(--di-muted); }
.di-notready { margin-bottom: 16px; color: var(--di-muted); font-size: 14px; }
.di-detail-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 14px; }
.di-detail-grid .di-card, .di-item-table { margin-bottom: 0; }
h3 { font-size: 14px; margin: 0 0 8px; color: var(--di-navy); }
.di-pre { white-space: pre-wrap; font-size: 13px; line-height: 1.5; margin: 0; }
.di-item-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.di-item-table th, .di-item-table td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--di-border); }
.di-qa { background: #f9fafb; border-radius: 8px; padding: 10px 12px; margin-bottom: 12px; font-size: 13px; }
.di-qa-q { font-weight: 600; margin-bottom: 4px; }
.di-ask-row { display: flex; gap: 8px; }
.di-compare-result { margin-top: 12px; background: #f9fafb; border-radius: 8px; padding: 12px; }
.di-card { margin-bottom: 14px; }
details summary { cursor: pointer; font-weight: 600; font-size: 14px; color: var(--di-navy); }
details[open] summary { margin-bottom: 10px; }
</style>

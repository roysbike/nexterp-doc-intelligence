<template>
  <div class="di-modal-backdrop" @click.self="$emit('close')">
    <div class="di-modal di-card">
      <h2>{{ t('statement.title') }}</h2>
      <div v-if="error" class="di-error">{{ error }}</div>

      <template v-if="!statement">
        <p class="di-hint">{{ t('statement.extractHint') }}</p>
        <div class="di-modal-actions">
          <button class="di-btn secondary" @click="$emit('close')">{{ t('statement.cancel') }}</button>
          <button class="di-btn primary" :disabled="extracting" @click="extract">
            {{ extracting ? t('statement.extracting') : t('statement.extract') }}
          </button>
        </div>
      </template>

      <template v-else>
        <div class="di-statement-meta">
          <span v-if="statement.account_name"><strong>{{ t('statement.account') }}:</strong> {{ statement.account_name }}</span>
          <span v-if="statement.currency"><strong>{{ t('statement.currency') }}:</strong> {{ statement.currency }}</span>
          <span><strong>{{ t('statement.rows') }}:</strong> {{ rows.length }}</span>
        </div>

        <div v-if="warnings.length" class="di-warning">
          <strong>{{ t('statement.checkRows') }}</strong>
          <ul><li v-for="(warning, i) in warnings" :key="i">{{ warning }}</li></ul>
        </div>

        <div class="di-table-wrap">
          <table class="di-item-table">
            <thead>
              <tr>
                <th>{{ t('statement.date') }}</th>
                <th>{{ t('statement.description') }}</th>
                <th>{{ t('statement.reference') }}</th>
                <th>{{ t('statement.debit') }}</th>
                <th>{{ t('statement.credit') }}</th>
                <th>{{ t('statement.balance') }}</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, i) in rows" :key="i">
                <td><input v-model="row.date" type="date" class="di-input date" /></td>
                <td><input v-model="row.description" class="di-input description" /></td>
                <td><input v-model="row.reference" class="di-input reference" /></td>
                <td><input v-model.number="row.debit" type="number" min="0" step="0.01" class="di-input money" /></td>
                <td><input v-model.number="row.credit" type="number" min="0" step="0.01" class="di-input money" /></td>
                <td><input v-model.number="row.balance" type="number" step="0.01" class="di-input money" /></td>
                <td><button class="di-btn secondary remove" :title="t('statement.remove')" @click="rows.splice(i, 1)">✕</button></td>
              </tr>
            </tbody>
          </table>
        </div>

        <button class="di-btn secondary add-row" @click="addRow">{{ t('statement.addRow') }}</button>

        <div class="di-export-controls">
          <div>
            <label class="di-label">{{ t('statement.format') }}</label>
            <select v-model="target" class="di-select">
              <option value="zoho_books">Zoho Books</option>
              <option value="quickbooks">QuickBooks Online</option>
              <option value="nexterp">NextERP / ERPNext</option>
            </select>
          </div>
          <div>
            <label class="di-label">{{ t('statement.currency') }}</label>
            <input v-model="currency" class="di-input currency" maxlength="3" placeholder="AED" />
          </div>
        </div>

        <div class="di-modal-actions">
          <button class="di-btn secondary" @click="$emit('close')">{{ t('statement.cancel') }}</button>
          <button class="di-btn primary" :disabled="exporting || !rows.length" @click="download">
            {{ exporting ? t('statement.preparing') : t('statement.download') }}
          </button>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import * as api from '@/api/frappe'
import { t } from '@/i18n'

const props = defineProps({ docName: { type: String, required: true } })
defineEmits(['close'])

const statement = ref(null)
const rows = ref([])
const warnings = ref([])
const currency = ref('')
const target = ref('nexterp')
const extracting = ref(false)
const exporting = ref(false)
const error = ref('')

async function extract() {
  extracting.value = true
  error.value = ''
  try {
    const result = await api.extractBankStatement(props.docName)
    statement.value = result.statement || {}
    rows.value = (result.statement?.transactions || []).map(row => ({ ...row }))
    warnings.value = result.validation?.warnings || []
    currency.value = result.statement?.currency || ''
  } catch (err) {
    error.value = err.message
  } finally {
    extracting.value = false
  }
}

function addRow() {
  rows.value.push({ date: '', description: '', reference: '', debit: 0, credit: 0, balance: null })
}

async function download() {
  exporting.value = true
  error.value = ''
  try {
    const result = await api.exportStatementCsv(
      props.docName,
      target.value,
      rows.value,
      currency.value.toUpperCase()
    )
    const blob = new Blob([result.csv], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = result.filename
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  } catch (err) {
    error.value = err.message
  } finally {
    exporting.value = false
  }
}
</script>

<style scoped>
.di-modal-backdrop {
  position: fixed; inset: 0; z-index: 1000; background: rgba(15, 23, 42, .48);
  display: flex; align-items: center; justify-content: center; padding: 20px;
}
.di-modal { width: min(1180px, 100%); max-height: 92vh; overflow: auto; }
.di-modal h2 { margin: 0 0 14px; font-size: 17px; color: var(--di-navy); }
.di-modal-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 18px; }
.di-hint { color: var(--di-muted); font-size: 13px; }
.di-statement-meta { display: flex; flex-wrap: wrap; gap: 16px; margin-bottom: 12px; font-size: 13px; }
.di-warning { background: #fff7ed; border: 1px solid #fdba74; border-radius: 8px; padding: 10px 12px; margin-bottom: 12px; font-size: 13px; }
.di-warning ul { margin: 6px 0 0; padding-left: 20px; }
.di-table-wrap { overflow-x: auto; max-height: 52vh; }
.di-item-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.di-item-table th, .di-item-table td { padding: 5px; border-bottom: 1px solid var(--di-border); text-align: left; }
.di-item-table th { position: sticky; top: 0; background: white; z-index: 1; }
.di-input.date { min-width: 132px; }
.di-input.description { min-width: 250px; }
.di-input.reference { min-width: 120px; }
.di-input.money { min-width: 105px; }
.di-btn.remove { padding: 6px 9px; }
.add-row { margin-top: 10px; }
.di-export-controls { display: flex; gap: 14px; align-items: end; margin-top: 16px; }
.di-export-controls > div:first-child { min-width: 230px; }
.di-input.currency { width: 90px; text-transform: uppercase; }
@media (max-width: 700px) {
  .di-export-controls { align-items: stretch; flex-direction: column; }
}
</style>

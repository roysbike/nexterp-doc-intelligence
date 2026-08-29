import { defineStore } from 'pinia'
import { ref } from 'vue'
import * as api from '@/api/frappe'

export const useSettingsStore = defineStore('settings', () => {
  const settings = ref(null)
  const health = ref([])
  const testResults = ref(null)
  const loading = ref(false)
  const saving = ref(false)
  const testing = ref(false)
  const error = ref('')
  const modelOptions = ref({})   // { [providerId]: string[] }
  const modelOptionsLoading = ref({})  // { [providerId]: boolean }
  const modelOptionsError = ref({})    // { [providerId]: string }

  async function fetchSettings() {
    loading.value = true
    error.value = ''
    try {
      settings.value = await api.getProviderSettings()
      return settings.value
    } catch (err) {
      error.value = err.message
      throw err
    } finally {
      loading.value = false
    }
  }

  async function fetchHealth() {
    health.value = await api.getProviderHealthStats()
    return health.value
  }

  async function save(patch) {
    saving.value = true
    error.value = ''
    try {
      await api.saveProviderSettings({ ...settings.value, ...patch })
      await fetchSettings()
    } catch (err) {
      error.value = err.message
      throw err
    } finally {
      saving.value = false
    }
  }

  async function testAll() {
    testing.value = true
    try {
      testResults.value = await api.testProviders()
      return testResults.value
    } finally {
      testing.value = false
    }
  }

  async function fetchModelOptions(providerId) {
    modelOptionsLoading.value = { ...modelOptionsLoading.value, [providerId]: true }
    modelOptionsError.value = { ...modelOptionsError.value, [providerId]: '' }
    try {
      const res = await api.getProviderModels(providerId)
      modelOptions.value = { ...modelOptions.value, [providerId]: res.models || [] }
      if (res.error) modelOptionsError.value = { ...modelOptionsError.value, [providerId]: res.error }
      return res
    } catch (err) {
      modelOptionsError.value = { ...modelOptionsError.value, [providerId]: err.message }
      throw err
    } finally {
      modelOptionsLoading.value = { ...modelOptionsLoading.value, [providerId]: false }
    }
  }

  return {
    settings, health, testResults, loading, saving, testing, error,
    modelOptions, modelOptionsLoading, modelOptionsError,
    fetchSettings, fetchHealth, save, testAll, fetchModelOptions,
  }
})

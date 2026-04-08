<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { Building2, Hash, MapPinned, Ruler, SunMedium } from 'lucide-vue-next'
import SelectionModal from '@/components/SelectionModal.vue'
import { useAuth } from '@/stores/auth'
import { useApplicationStore, type AvailableUnit } from '@/stores/application'
import {
  fetchApplications,
  fetchFlatSelections,
  getErrorMessage,
  selectFlatAllocation,
  type FlatSelectionRecord,
} from '@/services/api'

const applicationStore = useApplicationStore()
const { applicantNric } = useAuth()

const socket = ref<WebSocket | null>(null)

const focusedUnit = ref<AvailableUnit | null>(applicationStore.selectedUnit)
const isModalOpen = ref(false)
const isSubmittingSelection = ref(false)
const loadError = ref('')
const bookingError = ref('')
const toastMessage = ref<string | null>(null)

const NETS_PAYMENT_FLOW_KEY = 'nets_payment_flow'
const NETS_FLOW_FLAT_SELECTION = 'flat-selection'
const NETS_FLAT_SELECTION_REF_KEY = 'nets_flat_selection_ref'

// Floor filter — empty set means "show all"
const selectedFloors = ref<Set<number>>(new Set())

const canSelectUnit = computed(() => applicationStore.status === 'balloted')
const displayUnit = computed(() => applicationStore.selectedUnit ?? focusedUnit.value)

const allFloors = computed(() => {
  const floors = [...new Set(applicationStore.availableUnits.map((u) => u.floor))].sort(
    (a, b) => b - a,
  )
  return floors
})

const floorRows = computed(() => {
  const groupedUnits = applicationStore.availableUnits.reduce<Record<number, AvailableUnit[]>>(
    (acc, unit) => {
      acc[unit.floor] = acc[unit.floor] ?? []
      acc[unit.floor]!.push(unit)
      return acc
    },
    {},
  )

  return Object.entries(groupedUnits)
    .map(([floor, units]) => ({
      floor: Number(floor),
      units: units.sort((a, b) => a.unitNumber.localeCompare(b.unitNumber)),
    }))
    .sort((a, b) => b.floor - a.floor) // highest floor first
    .filter((row) => selectedFloors.value.size === 0 || selectedFloors.value.has(row.floor))
})

function toggleFloor(floor: number) {
  const next = new Set(selectedFloors.value)
  if (next.has(floor)) {
    next.delete(floor)
  } else {
    next.add(floor)
  }
  selectedFloors.value = next
}

function clearFloorFilter() {
  selectedFloors.value = new Set()
}

const modalMessage = computed(() => {
  if (!focusedUnit.value) return ''
  return `Confirm booking of Unit ${focusedUnit.value.unitNumber} at ${focusedUnit.value.development}?`
})

function formatCurrency(value: number) {
  return new Intl.NumberFormat('en-SG', {
    style: 'currency',
    currency: 'SGD',
    minimumFractionDigits: 0,
  }).format(value)
}

function focusUnit(unit: AvailableUnit) {
  if (applicationStore.status === 'selected') return
  bookingError.value = ''
  focusedUnit.value = unit
}

function closeConfirmModal() {
  isModalOpen.value = false
}

function normaliseMessage(message: string | string[] | undefined, fallback: string): string {
  if (Array.isArray(message)) {
    return message.join(' ')
  }

  if (typeof message === 'string' && message.trim().length > 0) {
    return message
  }

  return fallback
}

function getRecordSortTime(record: FlatSelectionRecord): number {
  const value = Date.parse(record.updated_at ?? record.created_at ?? '')
  return Number.isNaN(value) ? 0 : value
}

function resolveSelectionId(records: FlatSelectionRecord[]): number | null {
  const eligibleRecords = records.filter((record) => record.status === 'balloted' || record.status === 'selecting')
  if (eligibleRecords.length === 0) {
    return null
  }

  const sorted = [...eligibleRecords].sort((left, right) => {
    const delta = getRecordSortTime(right) - getRecordSortTime(left)
    if (delta !== 0) {
      return delta
    }

    return right.selection_id - left.selection_id
  })

  return sorted[0]?.selection_id ?? null
}

function submitToNets(gatewayUrl: string, payload: string, hmac: string, apiKeyId: string) {
  const form = document.createElement('form')
  form.method = 'POST'
  form.action = gatewayUrl

  const fields: Record<string, string> = {
    apiKey: apiKeyId,
    payload,
    hmac,
  }

  for (const [name, value] of Object.entries(fields)) {
    const input = document.createElement('input')
    input.type = 'hidden'
    input.name = name
    input.value = value
    form.appendChild(input)
  }

  document.body.appendChild(form)
  form.submit()
  document.body.removeChild(form)
}

async function confirmUnitSelection() {
  if (!focusedUnit.value) return

  const nric = (applicantNric.value ?? applicationStore.form.nric).trim().toUpperCase()
  if (!nric) {
    bookingError.value = 'Unable to identify the applicant NRIC for this booking.'
    return
  }

  isSubmittingSelection.value = true
  bookingError.value = ''

  try {
    const selectionResponse = await fetchFlatSelections({ applicant_nric: nric })
    if (selectionResponse.status !== 200 || !Array.isArray(selectionResponse.data.data)) {
      const message = normaliseMessage(
        selectionResponse.data.message,
        'Unable to load your flat selection record at the moment.',
      )
      throw new Error(message)
    }

    const selectionId = resolveSelectionId(selectionResponse.data.data)
    if (!selectionId) {
      throw new Error('No balloted or selecting flat selection record is available for this applicant.')
    }

    const bookingResponse = await selectFlatAllocation({
      applicant_id: nric,
      selection_id: selectionId,
      flat_id: focusedUnit.value.id,
      payment_amount: 10,
    })

    if (bookingResponse.status !== 200 || !bookingResponse.data.data) {
      const message = normaliseMessage(
        bookingResponse.data.message,
        'Unable to initiate NETS payment for flat booking.',
      )
      throw new Error(message)
    }

    const result = bookingResponse.data.data
    const paymentPayload = result.payment ?? {}
    const gatewayUrl = result.gateway_url || paymentPayload.gateway_url || ''
    const payload = result.payload || paymentPayload.payload || ''
    const hmac = result.hmac || paymentPayload.hmac || ''
    const apiKeyId = result.api_key_id || paymentPayload.api_key_id || ''

    if (!gatewayUrl || !payload || !hmac || !apiKeyId) {
      throw new Error('Payment gateway payload is incomplete. Please try again.')
    }

    if (typeof window !== 'undefined') {
      window.sessionStorage.setItem(NETS_PAYMENT_FLOW_KEY, NETS_FLOW_FLAT_SELECTION)
      if (result.merchant_txn_ref) {
        window.sessionStorage.setItem(NETS_FLAT_SELECTION_REF_KEY, result.merchant_txn_ref)
      }
    }
    
    window.sessionStorage.setItem('nets_selected_flat', JSON.stringify(focusedUnit.value))
    isModalOpen.value = false
    submitToNets(gatewayUrl, payload, hmac, apiKeyId)
  } catch (error) {
    bookingError.value = getErrorMessage(error, 'Unable to start the flat booking payment workflow.')
  } finally {
    isSubmittingSelection.value = false
  }
}

function openConfirmModal() {
  if (!focusedUnit.value || !canSelectUnit.value) return
  isModalOpen.value = true
}

function showToast(message: string) {
  toastMessage.value = message
  setTimeout(() => {
    toastMessage.value = null
  }, 5000)
}

onMounted(async () => {
  loadError.value = ''

  let projectIdForUser: number | undefined
  let flatTypeForUser: string | undefined

  const nric = (applicantNric.value ?? applicationStore.form.nric).trim().toUpperCase()
  if (nric) {
    try {
      const selectionResponse = await fetchFlatSelections({ applicant_nric: nric })
      if (selectionResponse.status === 200 && Array.isArray(selectionResponse.data.data)) {
        const eligible = selectionResponse.data.data.find(
          (record) => record.status === 'balloted' || record.status === 'selecting',
        )
        if (eligible) {
          projectIdForUser = eligible.project_id

          // Now look up the application to get flat_type
          try {
            const appResponse = await fetchApplications({ main_applicant_nric: nric })
            if (appResponse.status === 200 && Array.isArray(appResponse.data.applications)) {
              const matchingApp = appResponse.data.applications.find(
                (app) => app.application_id === eligible.application_id,
              )
              if (matchingApp) {
                flatTypeForUser = matchingApp.flat_type
              }
            }
          } catch (err) {
            console.warn('Failed to fetch application for flat_type:', err)
          }
        }
      }
    } catch (error) {
      console.warn('Failed to fetch flat-selection record:', error)
    }
  }

  await applicationStore.loadAvailableUnits(projectIdForUser, flatTypeForUser)

  socket.value = new WebSocket('ws://localhost:5017')

  socket.value.onopen = () => {
    // No-op: units already loaded above
  }

  socket.value.onmessage = (event) => {
    const data = JSON.parse(event.data) as { flat_id: number; status: string }
    if (data.status === 'reserved') {
      const reservedUnit = applicationStore.availableUnits.find(u => u.id === data.flat_id)
      const unitLabel = reservedUnit ? reservedUnit.unitNumber : `Flat #${data.flat_id}`
      applicationStore.removeUnit(data.flat_id)

      const isMyBooking = applicationStore.selectedUnit?.id === data.flat_id
      if (!isMyBooking) {
        showToast(`${unitLabel} has been reserved by another applicant.`)
      }
    } else if (data.status === 'available') {
      applicationStore.loadAvailableUnits(projectIdForUser, flatTypeForUser)
    }
  }

  socket.value.onerror = (err) => {
    console.warn('WebSocket error:', err)
    applicationStore.loadAvailableUnits(projectIdForUser, flatTypeForUser)
  }
})

onUnmounted(() => {
  socket.value?.close()
  socket.value = null
})

</script>

<template>
  <section class="section">
    <div class="container">
      <header class="page-header">
        <p class="eyebrow">Flat Selection</p>
        <h1 class="page-title">{{ applicationStore.developmentName }}</h1>
        <p class="page-subtitle page-subtitle--queue">Queue Number: {{ applicationStore.queueNumber }}</p>
      </header>

      <div v-if="toastMessage" class="toast">
        {{ toastMessage }}
      </div>

      <p v-if="loadError" class="load-error">{{ loadError }}</p>

      <p v-else-if="applicationStore.isLoadingAvailableUnits" class="load-hint">Loading available flats...</p>

      <p v-if="bookingError" class="load-error">{{ bookingError }}</p>

      <div v-if="applicationStore.selectedUnit" class="surface reserved-card">
        <p class="reserved-card__label">Booked Unit</p>
        <h2>{{ applicationStore.selectedUnit.unitNumber }}</h2>
        <p>
          {{ applicationStore.selectedUnit.development }} has been reserved under your application.
        </p>
      </div>

      <div class="selection-layout">
        <div class="surface floor-picker">
          <!-- Header: just legend, no heading text -->
          <div class="floor-picker__top">
            <h2 class="floor-picker__title">Flat Booking</h2>
            <div class="floor-picker__legend">
              <span><i class="legend-dot legend-dot--available" /> Available</span>
              <span><i class="legend-dot legend-dot--focused" /> Selected</span>
              <span><i class="legend-dot legend-dot--reserved" /> Reserved</span>
            </div>
          </div>

          <!-- Floor filter -->
          <div class="floor-filter">
            <span class="floor-filter__label">Filter floors:</span>
            <button
              :class="['filter-btn', { 'filter-btn--active': selectedFloors.size === 0 }]"
              type="button"
              @click="clearFloorFilter"
            >
              All
            </button>
            <button
              v-for="floor in allFloors"
              :key="floor"
              :class="['filter-btn', { 'filter-btn--active': selectedFloors.has(floor) }]"
              type="button"
              @click="toggleFloor(floor)"
            >
              {{ floor }}F
            </button>
          </div>

          <!-- Floor rows — highest level at top -->
          <div class="floor-rows">
            <div v-for="row in floorRows" :key="row.floor" class="floor-row">
              <div class="floor-row__label">Lvl {{ row.floor }}</div>

              <div class="floor-row__units">
                <button
                  v-for="unit in row.units"
                  :key="unit.id"
                  :class="[
                    'unit-seat',
                    {
                      'unit-seat--focused':
                        displayUnit?.id === unit.id && applicationStore.status !== 'selected',
                      'unit-seat--reserved': applicationStore.selectedUnit?.id === unit.id,
                    },
                  ]"
                  type="button"
                  :disabled="
                    applicationStore.status === 'selected' &&
                    applicationStore.selectedUnit?.id !== unit.id
                  "
                  @click="focusUnit(unit)"
                >
                  <span class="unit-seat__number">{{ unit.unitNumber }}</span>
                </button>
              </div>
            </div>
          </div>

          <!-- Lift lobby at bottom -->
          <div class="lift-lobby">
            <span>↑ Lift Lobby / Common Corridor</span>
          </div>
        </div>

        <aside class="surface unit-panel">
          <template v-if="displayUnit">
            <div class="unit-panel__header">
              <div>
                <p class="unit-panel__label">Selected Unit</p>
                <h2>{{ displayUnit.unitNumber }}</h2>
              </div>
              <span
                class="status-chip"
                :class="{
                  'status-chip--success': applicationStore.selectedUnit?.id === displayUnit.id,
                }"
              >
                {{ applicationStore.selectedUnit?.id === displayUnit.id ? 'Reserved' : 'Available' }}
              </span>
            </div>

            <div class="unit-panel__meta">
              <p>
                <Building2 :size="16" />
                <span>Floor {{ displayUnit.floor }}</span>
              </p>
              <p>
                <SunMedium :size="16" />
                <span>{{ displayUnit.facing }} facing</span>
              </p>
              <p>
                <Ruler :size="16" />
                <span>{{ displayUnit.sqm }} sqm</span>
              </p>
              <p>
                <MapPinned :size="16" />
                <span>{{ displayUnit.development }}</span>
              </p>
              <p>
                <Hash :size="16" />
                <span>{{ formatCurrency(displayUnit.price) }}</span>
              </p>
            </div>

            <button
              class="btn btn-primary"
              type="button"
              :disabled="!canSelectUnit || applicationStore.status === 'selected' || isSubmittingSelection"
              @click="openConfirmModal"
            >
              {{ applicationStore.status === 'selected' ? 'Reserved Under Your Name' : 'Book This Unit' }}
            </button>
          </template>

          <template v-else>
            <p class="unit-panel__label">Unit Details</p>
            <h2>Select a unit</h2>
            <p class="unit-panel__empty">
              Click any unit on the floor plan to review its level, facing, area, and price before booking.
            </p>
          </template>
        </aside>
      </div>
    </div>

    <SelectionModal
      :open="isModalOpen"
      title="Confirm Flat Booking"
      :message="modalMessage"
      confirm-label="Book Unit"
      cancel-label="Cancel"
      :processing="isSubmittingSelection"
      processing-label="Preparing secure NETS checkout..."
      @close="closeConfirmModal"
      @confirm="confirmUnitSelection"
    />
  </section>
</template>

<style scoped>
.success-banner {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 14px 16px;
  border: 1px solid rgba(26, 127, 75, 0.2);
  border-radius: var(--radius-sm);
  color: var(--color-green);
  background: rgba(26, 127, 75, 0.08);
  font-weight: 600;
}

.page-subtitle--queue {
  display: inline-flex;
  align-items: center;
  margin-top: 8px;
  padding: 6px 12px;
  border-radius: 999px;
  background: rgba(200, 16, 46, 0.12);
  color: var(--color-red);
  font-weight: 800;
  letter-spacing: 0.03em;
}

.load-hint,
.load-error {
  margin: 8px 0 0;
  font-weight: 600;
}

.load-hint {
  color: rgba(29, 29, 31, 0.66);
}

.load-error {
  color: var(--color-red);
}

.reserved-card {
  margin-top: 20px;
  padding: 24px;
}

.reserved-card__label {
  margin: 0 0 8px;
  font-size: 0.82rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: rgba(29, 29, 31, 0.56);
}

.reserved-card h2 {
  margin: 0 0 10px;
  font-size: 1.8rem;
  line-height: 1.1;
  letter-spacing: -0.03em;
}

.reserved-card p {
  margin: 0;
  color: rgba(29, 29, 31, 0.72);
}

.selection-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.7fr) minmax(300px, 0.9fr);
  gap: 22px;
  margin-top: 24px;
}

.floor-picker,
.unit-panel {
  padding: 22px;
}

/* Header row */
.floor-picker__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  margin-bottom: 16px;
}

.floor-picker__title {
  margin: 0;
  font-size: 1.2rem;
  font-weight: 700;
  letter-spacing: -0.02em;
}

.floor-picker__legend {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  color: rgba(29, 29, 31, 0.68);
  font-size: 0.86rem;
}

.floor-picker__legend span {
  display: inline-flex;
  align-items: center;
  gap: 7px;
}

.legend-dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 999px;
}

.legend-dot--available {
  background: var(--color-grey-bg);
  border: 1px solid var(--color-border);
}

.legend-dot--focused {
  background: var(--color-red-light);
  border: 1px solid var(--color-red);
}

.legend-dot--reserved {
  background: rgba(26, 127, 75, 0.1);
  border: 1px solid var(--color-green);
}

/* Floor filter */
.floor-filter {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 18px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--color-border);
}

.floor-filter__label {
  font-size: 0.82rem;
  font-weight: 600;
  color: rgba(29, 29, 31, 0.5);
  margin-right: 2px;
}

.filter-btn {
  padding: 4px 12px;
  border: 1px solid var(--color-border);
  border-radius: 999px;
  background: var(--color-white);
  color: rgba(29, 29, 31, 0.72);
  font-size: 0.82rem;
  font-weight: 600;
  cursor: pointer;
  transition: border-color 0.15s ease, color 0.15s ease, background 0.15s ease;
}

.filter-btn:hover {
  border-color: var(--color-red);
  color: var(--color-red);
}

.filter-btn--active {
  border-color: var(--color-red);
  background: var(--color-red-light);
  color: var(--color-red);
}

/* Floor rows */
.floor-rows {
  display: grid;
  gap: 10px;
}

.floor-row {
  display: grid;
  grid-template-columns: 56px minmax(0, 1fr);
  gap: 12px;
  align-items: center;
}

.floor-row__label {
  font-size: 0.8rem;
  font-weight: 700;
  color: rgba(29, 29, 31, 0.5);
  text-align: right;
}

.floor-row__units {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

/* Smaller unit boxes */
.unit-seat {
  width: 70px;
  min-height: 52px;
  padding: 8px 6px;
  border: 1px solid var(--color-border);
  border-radius: 8px 8px 5px 5px;
  background: var(--color-grey-bg);
  color: var(--color-charcoal);
  cursor: pointer;
  transition: border-color 0.18s ease, background-color 0.18s ease, transform 0.15s ease;
}

.unit-seat:hover:not(:disabled) {
  border-color: var(--color-red);
  transform: translateY(-2px);
}

.unit-seat--focused {
  border-color: var(--color-red);
  background: var(--color-red-light);
}

.unit-seat--reserved {
  border-color: var(--color-green);
  background: rgba(26, 127, 75, 0.08);
  color: var(--color-green);
}

.unit-seat:disabled:not(.unit-seat--reserved):not(.unit-seat--focused) {
  opacity: 0.45;
  cursor: not-allowed;
}

.unit-seat__number {
  display: block;
  font-size: 0.72rem;
  font-weight: 700;
  text-align: center;
  line-height: 1.3;
}

/* Lift lobby at bottom */
.lift-lobby {
  margin-top: 16px;
  padding: 10px 16px;
  border-radius: 999px;
  background: var(--color-grey-bg);
  border: 1px solid var(--color-border);
  text-align: center;
  font-size: 0.86rem;
  font-weight: 600;
  color: rgba(29, 29, 31, 0.6);
}

/* Unit panel */
.unit-panel__header {
  display: flex;
  justify-content: space-between;
  gap: 18px;
}

.unit-panel__label {
  margin: 0 0 6px;
  font-size: 0.8rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: rgba(29, 29, 31, 0.56);
}

.unit-panel h2 {
  margin: 0;
  font-size: 1.6rem;
  line-height: 1.1;
  letter-spacing: -0.03em;
}

.status-chip {
  display: inline-flex;
  align-items: center;
  padding: 4px 12px;
  border-radius: 999px;
  font-size: 0.8rem;
  font-weight: 700;
  background: rgba(29, 29, 31, 0.06);
  color: rgba(29, 29, 31, 0.6);
  white-space: nowrap;
  height: fit-content;
}

.status-chip--success {
  background: rgba(26, 127, 75, 0.1);
  color: var(--color-green);
}

.unit-panel__meta {
  display: grid;
  gap: 10px;
  margin: 20px 0 22px;
}

.unit-panel__meta p {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  margin: 0;
  color: rgba(29, 29, 31, 0.72);
}

.unit-panel__empty {
  margin: 12px 0 0;
  color: rgba(29, 29, 31, 0.65);
  line-height: 1.6;
}

@media (max-width: 960px) {
  .selection-layout {
    grid-template-columns: 1fr;
  }

  .floor-row {
    grid-template-columns: 48px 1fr;
  }

  .floor-picker__top {
    flex-direction: column;
    align-items: flex-start;
  }
}
  .toast {
    position: fixed;
    bottom: 28px;
    right: 28px;
    z-index: 999;
    padding: 14px 20px;
    border-radius: 12px;
    background: var(--color-charcoal);
    color: var(--color-white);
    font-weight: 600;
    font-size: 0.95rem;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.18);
  }
</style>

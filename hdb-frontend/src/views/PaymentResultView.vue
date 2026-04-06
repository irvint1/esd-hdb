<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { AlertCircle, CheckCircle2, Clock3, FileWarning, XCircle } from 'lucide-vue-next'
import { useApplicationStore } from '@/stores/application'
import {
  abandonNetsPayment,
  completeApplyBtoSubmission,
  demoForceApplyBtoSuccess,
  getErrorMessage,
  type ApplyBtoCompletionResult,
} from '@/services/api'

const route = useRoute()
const router = useRouter()
const applicationStore = useApplicationStore()
const NETS_PAYMENT_REF_KEY = 'nets_last_merchant_txn_ref'
const NETS_ACTIVE_PAYMENT_REF_KEY = 'nets_active_merchant_txn_ref'
const PENDING_POLL_INTERVAL_MS = 4000
const PENDING_TIMEOUT_MS = 13000

function getStoredPaymentRef(): string | undefined {
  if (typeof window === 'undefined') {
    return undefined
  }

  const refValue = window.sessionStorage.getItem(NETS_PAYMENT_REF_KEY)
  return refValue && refValue !== 'unknown' ? refValue : undefined
}

function clearStoredPaymentRef() {
  if (typeof window === 'undefined') {
    return
  }

  window.sessionStorage.removeItem(NETS_PAYMENT_REF_KEY)
  window.sessionStorage.removeItem(NETS_ACTIVE_PAYMENT_REF_KEY)
}

const queryRef = computed(() => route.query.ref as string | undefined)
const paymentRef = computed(() => {
  if (queryRef.value && queryRef.value !== 'unknown') {
    return queryRef.value
  }

  return getStoredPaymentRef()
})

const completionStatus = ref<number | null>(null)
const wrapperResult = ref<ApplyBtoCompletionResult | null>(null)
const statusMessage = ref('Finalising your application through Apply BTO...')
const verificationError = ref('')
const isVerifying = ref(true)
const isForcingDemoSuccess = ref(false)
const pendingStartedAt = ref<number | null>(null)
const pendingAutoCancelTriggered = ref(false)

let pendingPollHandle: number | null = null

const applicationStatus = computed(() => wrapperResult.value?.application_status ?? null)
const ineligibilityReasons = computed(() => wrapperResult.value?.ineligibility_reasons ?? [])
const workflowStage = computed(() => wrapperResult.value?.stage ?? 'unknown')
const paymentStatus = computed(() => wrapperResult.value?.payment_status ?? 'unknown')
const isEligible = computed(() => wrapperResult.value?.eligible)

const viewState = computed(() => {
  if (isVerifying.value) {
    return 'verifying'
  }

  if (completionStatus.value === 200) {
    if (isEligible.value === false || applicationStatus.value === 'UNSUCCESSFUL') {
      return 'application-unsuccessful'
    }

    return 'application-successful'
  }

  if (completionStatus.value === 202) {
    return 'pending'
  }

  if (completionStatus.value === 402) {
    return paymentStatus.value === 'cancelled' ? 'cancelled' : 'payment-failed'
  }

  if (completionStatus.value === 404) {
    return 'unknown-ref'
  }

  if (completionStatus.value === 502) {
    return 'downstream-error'
  }

  return 'unknown'
})

function clearPendingPoll() {
  if (pendingPollHandle !== null && typeof window !== 'undefined') {
    window.clearTimeout(pendingPollHandle)
    pendingPollHandle = null
  }
}

function schedulePendingPoll() {
  clearPendingPoll()

  if (typeof window === 'undefined') {
    return
  }

  pendingPollHandle = window.setTimeout(() => {
    void finaliseWorkflow()
  }, PENDING_POLL_INTERVAL_MS)
}

function formatApplicationStatus(status?: string) {
  if (!status) {
    return 'Not available'
  }

  return status
    .toLowerCase()
    .split('_')
    .map((chunk) => chunk.charAt(0).toUpperCase() + chunk.slice(1))
    .join(' ')
}

function formatStage(stage?: string) {
  if (!stage) {
    return 'Unknown'
  }

  return stage
    .split('_')
    .map((chunk) => chunk.charAt(0).toUpperCase() + chunk.slice(1))
    .join(' ')
}

function buildCompletedMessage(result: ApplyBtoCompletionResult) {
  if (result.summary) {
    return result.summary
  }

  if (result.eligible === false || result.application_status === 'UNSUCCESSFUL') {
    return 'Your payment succeeded, but the application did not pass the post-payment checks.'
  }

  if (result.eligible === true || result.application_status === 'SUCCESSFUL') {
    return 'Your payment succeeded and the application passed the post-payment checks.'
  }

  return result.message || 'The Apply BTO workflow completed successfully.'
}

async function finaliseWorkflow() {
  clearPendingPoll()
  isVerifying.value = true
  verificationError.value = ''

  if (!paymentRef.value) {
    completionStatus.value = 404
    statusMessage.value = 'Missing transaction reference. Unable to finalise this Apply BTO workflow.'
    isVerifying.value = false
    return
  }

  try {
    const response = await completeApplyBtoSubmission(paymentRef.value)
    completionStatus.value = response.status
    wrapperResult.value = response.data

    if (response.status === 200) {
      pendingStartedAt.value = null
      pendingAutoCancelTriggered.value = false
      statusMessage.value = buildCompletedMessage(response.data)
      clearStoredPaymentRef()
      const completedSuccessfully =
        response.data.eligible === true || response.data.application_status === 'SUCCESSFUL'

      applicationStore.status = completedSuccessfully ? 'successful' : 'editing'
      applicationStore.queueNumber = null
      applicationStore.lastSubmittedAt = new Date().toISOString()
      return
    }

    if (response.status === 202) {
      if (pendingStartedAt.value === null) {
        pendingStartedAt.value = Date.now()
      }

      const elapsedMs = Date.now() - pendingStartedAt.value
      if (elapsedMs >= PENDING_TIMEOUT_MS && !pendingAutoCancelTriggered.value && paymentRef.value) {
        pendingAutoCancelTriggered.value = true
        statusMessage.value = 'Payment stayed pending for too long. Cancelling this transaction now...'

        const abandonResponse = await abandonNetsPayment(paymentRef.value)
        if (abandonResponse.status === 200) {
          const abandonData = abandonResponse.data.data
          const abandonMessage =
            (abandonData && typeof abandonData.message === 'string' && abandonData.message.trim())
              ? abandonData.message
              : 'Payment was cancelled after timing out in pending state.'

          completionStatus.value = 402
          wrapperResult.value = {
            merchant_txn_ref: paymentRef.value,
            stage: 'payment_failed',
            payment_status: 'cancelled',
            message: abandonMessage,
          }
          statusMessage.value = abandonMessage
          clearStoredPaymentRef()
          pendingStartedAt.value = null
          return
        }

        pendingAutoCancelTriggered.value = false
      }

      statusMessage.value = response.data.message || 'Payment is still pending.'
      schedulePendingPoll()
      return
    }

    if (response.status === 402) {
      pendingStartedAt.value = null
      pendingAutoCancelTriggered.value = false
      statusMessage.value = response.data.message || 'Payment did not complete successfully.'
      clearStoredPaymentRef()
      return
    }

    if (response.status === 404) {
      pendingStartedAt.value = null
      pendingAutoCancelTriggered.value = false
      statusMessage.value = response.data.message || 'The Apply BTO transaction reference could not be found.'
      clearStoredPaymentRef()
      return
    }

    if (response.status === 502) {
      statusMessage.value =
        response.data.message ||
        'Payment may have succeeded, but the application could not be finalised yet.'
      return
    }

    statusMessage.value = response.data.message || 'Unable to determine the final outcome of this submission.'
  } catch (error) {
    verificationError.value = getErrorMessage(error, 'Unable to finalise the Apply BTO workflow.')
    statusMessage.value = verificationError.value
  } finally {
    isVerifying.value = false
  }
}

async function handleDemoForceSuccess() {
  if (!paymentRef.value) {
    completionStatus.value = 404
    statusMessage.value = 'Missing transaction reference. Unable to force payment success for this demo.'
    return
  }

  clearPendingPoll()
  verificationError.value = ''
  isVerifying.value = false
  isForcingDemoSuccess.value = true
  statusMessage.value = 'Forcing payment success for demo mode and completing your application...'

  try {
    const response = await demoForceApplyBtoSuccess(paymentRef.value)
    completionStatus.value = response.status
    wrapperResult.value = response.data

    if (response.status === 200) {
      statusMessage.value = buildCompletedMessage(response.data)
      clearStoredPaymentRef()
      const completedSuccessfully =
        response.data.eligible === true || response.data.application_status === 'SUCCESSFUL'

      applicationStore.status = completedSuccessfully ? 'successful' : 'editing'
      applicationStore.queueNumber = null
      applicationStore.lastSubmittedAt = new Date().toISOString()
      return
    }

    statusMessage.value = response.data.message || 'Unable to force payment success for this demo.'
  } catch (error) {
    verificationError.value = getErrorMessage(error, 'Unable to force payment success for this demo.')
    statusMessage.value = verificationError.value
  } finally {
    isForcingDemoSuccess.value = false
  }
}

onMounted(() => {
  pendingStartedAt.value = null
  pendingAutoCancelTriggered.value = false
  void finaliseWorkflow()
})

onBeforeUnmount(() => {
  clearPendingPoll()
})
</script>

<template>
  <section class="section result-page">
    <div class="container result-shell">
      <div v-if="viewState === 'verifying'" class="surface result-card">
        <div class="result-icon">
          <Clock3 :size="32" />
        </div>
        <h1>Finalising Application</h1>
        <p>{{ statusMessage }}</p>

        <div v-if="paymentRef" class="txn-ref">
          <span class="txn-ref__label">Transaction Reference</span>
          <span class="txn-ref__value">{{ paymentRef }}</span>
        </div>
      </div>

      <div v-else-if="viewState === 'application-successful'" class="surface result-card result-card--success">
        <div class="result-icon result-icon--success">
          <CheckCircle2 :size="32" />
        </div>
        <h1>Application Successful</h1>
        <p>{{ statusMessage }}</p>

        <div class="result-summary">
          <div class="result-summary__row">
            <span>Workflow Stage</span>
            <strong>{{ formatStage(workflowStage) }}</strong>
          </div>
          <div class="result-summary__row">
            <span>Payment Status</span>
            <strong>{{ formatApplicationStatus(paymentStatus) }}</strong>
          </div>
          <div v-if="applicationStatus" class="result-summary__row">
            <span>Application Status</span>
            <strong>{{ formatApplicationStatus(applicationStatus) }}</strong>
          </div>
        </div>

        <div v-if="paymentRef" class="txn-ref">
          <span class="txn-ref__label">Transaction Reference</span>
          <span class="txn-ref__value">{{ paymentRef }}</span>
        </div>

        <div class="result-actions">
          <button class="btn btn-primary" type="button" @click="router.push({ path: '/', hash: '#dashboard' })">
            View Dashboard
          </button>
        </div>
      </div>

      <div
        v-else-if="viewState === 'application-unsuccessful'"
        class="surface result-card result-card--warning"
      >
        <div class="result-icon result-icon--warning">
          <FileWarning :size="32" />
        </div>
        <h1>Application Unsuccessful</h1>
        <p>{{ statusMessage }}</p>

        <div class="result-summary">
          <div class="result-summary__row">
            <span>Workflow Stage</span>
            <strong>{{ formatStage(workflowStage) }}</strong>
          </div>
          <div class="result-summary__row">
            <span>Payment Status</span>
            <strong>{{ formatApplicationStatus(paymentStatus) }}</strong>
          </div>
          <div v-if="applicationStatus" class="result-summary__row">
            <span>Application Status</span>
            <strong>{{ formatApplicationStatus(applicationStatus) }}</strong>
          </div>
        </div>

        <div v-if="ineligibilityReasons.length > 0" class="result-reasons">
          <p class="result-reasons__title">Ineligibility Reasons</p>
          <ul>
            <li v-for="reason in ineligibilityReasons" :key="reason">{{ reason }}</li>
          </ul>
        </div>

        <div class="result-actions">
          <button class="btn btn-primary" type="button" @click="router.push({ path: '/', hash: '#dashboard' })">
            Return Home
          </button>
        </div>
      </div>

      <div v-else-if="viewState === 'payment-failed'" class="surface result-card result-card--failed">
        <div class="result-icon result-icon--failed">
          <XCircle :size="32" />
        </div>
        <h1>Payment Failed</h1>
        <p>{{ statusMessage || 'Your payment could not be processed. Please try again.' }}</p>

        <div v-if="paymentRef" class="txn-ref">
          <span class="txn-ref__label">Transaction Reference</span>
          <span class="txn-ref__value">{{ paymentRef }}</span>
        </div>

        <div class="result-actions">
          <button class="btn btn-secondary" type="button" @click="router.push('/apply/payment')">
            Try Again
          </button>
          <button
            class="btn btn-secondary"
            type="button"
            :disabled="isForcingDemoSuccess"
            @click="handleDemoForceSuccess"
          >
            {{ isForcingDemoSuccess ? 'Forcing Demo Success...' : 'Demo: Force Success' }}
          </button>
          <button class="btn btn-primary" type="button" @click="router.push('/')">
            Return Home
          </button>
        </div>
      </div>

      <div v-else-if="viewState === 'cancelled'" class="surface result-card result-card--cancelled">
        <div class="result-icon result-icon--cancelled">
          <AlertCircle :size="32" />
        </div>
        <h1>Payment Cancelled</h1>
        <p>{{ statusMessage || 'You cancelled the payment. Your application has not been submitted.' }}</p>

        <div class="result-actions">
          <button class="btn btn-secondary" type="button" @click="router.push('/apply/payment')">
            Go Back to Payment
          </button>
          <button class="btn btn-primary" type="button" @click="router.push('/')">
            Return Home
          </button>
        </div>
      </div>

      <div v-else-if="viewState === 'pending'" class="surface result-card">
        <div class="result-icon">
          <Clock3 :size="32" />
        </div>
        <h1>Payment Still Pending</h1>
        <p>{{ statusMessage || "We're still waiting for the payment workflow to complete." }}</p>

        <div v-if="wrapperResult" class="result-summary">
          <div class="result-summary__row">
            <span>Current Stage</span>
            <strong>{{ formatStage(wrapperResult.stage) }}</strong>
          </div>
          <div class="result-summary__row">
            <span>Payment Status</span>
            <strong>{{ formatApplicationStatus(wrapperResult.payment_status) }}</strong>
          </div>
        </div>

        <div v-if="paymentRef" class="txn-ref">
          <span class="txn-ref__label">Transaction Reference</span>
          <span class="txn-ref__value">{{ paymentRef }}</span>
        </div>

        <div class="result-actions">
          <button class="btn btn-secondary" type="button" @click="finaliseWorkflow">
            Check Again
          </button>
          <button class="btn btn-primary" type="button" @click="router.push('/')">
            Return Home
          </button>
        </div>
      </div>

      <div v-else-if="viewState === 'downstream-error'" class="surface result-card result-card--warning">
        <div class="result-icon result-icon--warning">
          <AlertCircle :size="32" />
        </div>
        <h1>Payment Received, Processing Incomplete</h1>
        <p>{{ statusMessage }}</p>

        <div v-if="wrapperResult" class="result-summary">
          <div class="result-summary__row">
            <span>Current Stage</span>
            <strong>{{ formatStage(wrapperResult.stage) }}</strong>
          </div>
          <div class="result-summary__row">
            <span>Payment Status</span>
            <strong>{{ formatApplicationStatus(wrapperResult.payment_status) }}</strong>
          </div>
        </div>

        <div class="result-actions">
          <button class="btn btn-secondary" type="button" @click="finaliseWorkflow">
            Retry Finalisation
          </button>
          <button class="btn btn-primary" type="button" @click="router.push('/')">
            Return Home
          </button>
        </div>
      </div>

      <div v-else-if="viewState === 'unknown-ref'" class="surface result-card">
        <div class="result-icon">
          <AlertCircle :size="32" />
        </div>
        <h1>Unknown Transaction</h1>
        <p>{{ statusMessage }}</p>

        <div class="result-actions">
          <button class="btn btn-primary" type="button" @click="router.push('/')">
            Return Home
          </button>
        </div>
      </div>

      <div v-else class="surface result-card">
        <div class="result-icon">
          <AlertCircle :size="32" />
        </div>
        <h1>Unable to Determine Outcome</h1>
        <p>{{ verificationError || statusMessage || "We couldn't determine the submission outcome." }}</p>

        <div v-if="wrapperResult" class="result-summary">
          <div class="result-summary__row">
            <span>Current Stage</span>
            <strong>{{ formatStage(wrapperResult.stage) }}</strong>
          </div>
          <div class="result-summary__row">
            <span>Payment Status</span>
            <strong>{{ formatApplicationStatus(wrapperResult.payment_status) }}</strong>
          </div>
        </div>

        <div class="result-actions">
          <button v-if="paymentRef" class="btn btn-secondary" type="button" @click="finaliseWorkflow">
            Check Again
          </button>
          <button class="btn btn-primary" type="button" @click="router.push('/')">
            Return Home
          </button>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.result-page {
  background: var(--color-grey-bg);
  min-height: calc(100vh - var(--nav-height));
}

.result-shell {
  display: flex;
  justify-content: center;
  padding-top: 60px;
}

.result-card {
  width: min(100%, 620px);
  padding: 40px;
  text-align: center;
}

.result-card--success {
  border-top: 4px solid var(--color-green);
}

.result-card--failed {
  border-top: 4px solid var(--color-red);
}

.result-card--cancelled {
  border-top: 4px solid #d97706;
}

.result-card--warning {
  border-top: 4px solid #d97706;
}

.result-icon {
  display: inline-grid;
  place-items: center;
  width: 64px;
  height: 64px;
  border-radius: 999px;
  background: rgba(29, 29, 31, 0.06);
  color: rgba(29, 29, 31, 0.5);
  margin: 0 auto 20px;
}

.result-icon--success {
  background: rgba(26, 127, 75, 0.1);
  color: var(--color-green);
}

.result-icon--failed {
  background: rgba(163, 18, 25, 0.08);
  color: var(--color-red);
}

.result-icon--cancelled,
.result-icon--warning {
  background: rgba(217, 119, 6, 0.1);
  color: #d97706;
}

.result-card h1 {
  margin: 0 0 12px;
  font-size: 1.8rem;
  letter-spacing: -0.03em;
}

.result-card p {
  margin: 0 0 24px;
  color: rgba(29, 29, 31, 0.68);
  line-height: 1.6;
}

.txn-ref {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 10px;
  margin-bottom: 24px;
  padding: 10px 16px;
  border-radius: 8px;
  background: rgba(29, 29, 31, 0.04);
}

.txn-ref__label {
  font-size: 0.82rem;
  font-weight: 600;
  color: rgba(29, 29, 31, 0.5);
}

.txn-ref__value {
  font-size: 0.88rem;
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-weight: 600;
  color: var(--color-charcoal);
}

.result-summary {
  margin: 0 0 24px;
  padding: 16px 18px;
  border-radius: 12px;
  border: 1px solid rgba(29, 29, 31, 0.08);
  background: rgba(29, 29, 31, 0.03);
  text-align: left;
}

.result-summary__row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 6px 0;
}

.result-summary__row + .result-summary__row {
  border-top: 1px solid rgba(29, 29, 31, 0.08);
}

.result-summary__row span {
  color: rgba(29, 29, 31, 0.62);
  font-size: 0.9rem;
}

.result-summary__row strong {
  font-size: 0.92rem;
  text-align: right;
  word-break: break-word;
}

.result-reasons {
  margin: 0 0 24px;
  padding: 18px 20px;
  border-radius: 12px;
  background: rgba(163, 18, 25, 0.06);
  text-align: left;
}

.result-reasons__title {
  margin: 0 0 10px;
  font-size: 0.86rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--color-red);
}

.result-reasons ul {
  margin: 0;
  padding-left: 18px;
  color: rgba(29, 29, 31, 0.76);
}

.result-reasons li + li {
  margin-top: 8px;
}

.result-actions {
  display: flex;
  justify-content: center;
  gap: 12px;
  flex-wrap: wrap;
}
</style>

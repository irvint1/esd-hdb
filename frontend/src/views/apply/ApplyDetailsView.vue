<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { CirclePlus, FileText, FolderInput, HousePlus, LockKeyhole, Users } from 'lucide-vue-next'
import SelectionModal from '@/components/SelectionModal.vue'
import HouseholdMemberFormCard from '@/components/HouseholdMemberFormCard.vue'
import { useApplicationStore } from '@/stores/application'
import { getMyInfoProfile } from '@/services/myinfo'
import { looksLikeNric } from '@/utils/validation'
import { fetchAvailableFlats } from '@/services/api'

const router = useRouter()
const applicationStore = useApplicationStore()

const maritalStatusOptions = ['Single', 'Married', 'Divorced', 'Widowed', 'Separated']
const citizenshipStatusOptions = ['Citizen', 'PR', 'Foreigner']
const flatTypeOptions = ref<string[]>([])
const isLoadingFlatTypes = ref(false)

async function loadFlatTypesForTown(town: string) {
  if (!town) {
    flatTypeOptions.value = []
    return
  }
  const project = applicationStore.projectByTown?.get(town)
  if (!project) {
    flatTypeOptions.value = []
    return
  }
  isLoadingFlatTypes.value = true
  try {
    const { status, data } = await fetchAvailableFlats({ project_id: project.project_id })
    if (status === 200 && Array.isArray(data.data)) {
      const unique = [...new Set(data.data.map((f) => f.flat_type))].sort()
      flatTypeOptions.value = unique
      // Clear the selected flat type if it's no longer valid for this project
      if (applicationStore.form.flatType && !unique.includes(applicationStore.form.flatType)) {
        applicationStore.form.flatType = ''
      }
    } else {
      flatTypeOptions.value = []
    }
  } finally {
    isLoadingFlatTypes.value = false
  }
}

watch(
  () => applicationStore.form.preferredTown,
  (town) => { void loadFlatTypesForTown(town) },
  { immediate: true },
)
const relationshipOptions = [
  'Spouse',
  'Fiance/Fiancee',
  'Child',
  'Parent',
  'Parent-in-law',
  'Sibling',
  'Sibling-in-law',
  'Grandparent',
  'Other',
]

const isRetrievingMain = ref(false)
const retrieveMainSuccess = ref(false)
const retrieveMainError = ref('')
const showResetModal = ref(false)
const showSubmissionSummary = ref(false)

const isCurrentSubmitted = computed(() => applicationStore.isCurrentSubmitted)
const hasSupportingMembers = computed(
  () => applicationStore.coApplicants.length > 0 || applicationStore.occupiers.length > 0,
)
const hasCoApplicant = computed(() => applicationStore.coApplicants.length >= 1)
const primaryCoApplicant = computed(() => applicationStore.coApplicants[0] ?? null)
const mainApplicantIdentityLocked = computed(() => applicationStore.mainApplicantProfileLocked)
const mainApplicantIncomeLocked = computed(
  () => mainApplicantIdentityLocked.value && applicationStore.form.monthlyIncome.trim().length > 0,
)
const submitLabel = computed(() =>
  isCurrentSubmitted.value ? 'View Submitted Application' : 'Submit Application',
)

async function retrieveMainApplicantFromMyInfo() {
  isRetrievingMain.value = true
  retrieveMainSuccess.value = false
  retrieveMainError.value = ''

  try {
    const trimmedNric = applicationStore.form.nric.trim().toUpperCase()
    // Prefer explicit NRIC lookup for complete profile fields (income, marital, contact).
    // Session profile can be minimal depending on auth-code claims returned by MockPass.
    let persona = trimmedNric ? await getMyInfoProfile(trimmedNric) : null

    // Fallback to session profile only when explicit lookup is unavailable.
    if (!persona) {
      persona = await getMyInfoProfile()
    }

    if (!persona) {
      retrieveMainError.value = 'No MyInfo profile found. Please sign in first or enter a valid NRIC.'
      return
    }

    applicationStore.fillMainApplicantFromMyInfo(persona)
    retrieveMainSuccess.value = true
  } catch {
    retrieveMainError.value = 'Unable to retrieve MyInfo data right now.'
  } finally {
    isRetrievingMain.value = false
  }
}

function addCoApplicant() {
  applicationStore.addHouseholdMember('CO_APPLICANT')
}

function addOccupier() {
  applicationStore.addHouseholdMember('OCCUPANT')
}

function handleFileChange(event: Event, documentKey: 'incomePdfName' | 'hfeLetterPdfName') {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0] ?? null
  applicationStore.setDocument(documentKey, file)
}

async function handlePrimaryAction() {
  if (isCurrentSubmitted.value) {
    await router.push('/apply/review')
    return
  }

  if (!applicationStore.validateApplicationDetails()) {
    return
  }

  showSubmissionSummary.value = true
}

async function continueToPayment() {
  showSubmissionSummary.value = false
  await router.push('/apply/payment')
}

function resetApplication() {
  applicationStore.resetFormProgress()
  retrieveMainSuccess.value = false
  retrieveMainError.value = ''
  showResetModal.value = false
  showSubmissionSummary.value = false
}

function startFreshApplication() {
  applicationStore.beginNewApplication()
  retrieveMainSuccess.value = false
  retrieveMainError.value = ''
  showResetModal.value = false
  showSubmissionSummary.value = false
}

onMounted(() => {
  void applicationStore.ensureProjectCatalogLoaded()
})
</script>

<template>
  <div class="surface step-card">
    <div class="step-card__copy">
      <h2>Application Details</h2>
      <p>Fill in your household details, upload documents, and continue to payment.</p>
    </div>

    <section class="form-section">
      <div v-if="isCurrentSubmitted" class="submitted-banner">
        <div>
          <strong>Current application is in submitted mode</strong>
          <p>This page is read-only because the store is still pointing at your submitted application.</p>
        </div>
        <button class="btn btn-secondary" type="button" @click="startFreshApplication">
          Start Fresh Application
        </button>
      </div>

      <div class="form-section__header">
        <div>
          <div class="form-section__title-row">
            <HousePlus :size="20" />
            <h3>Main Applicant</h3>
          </div>
          <p>Retrieve details from MyInfo. Contact number and email stay editable.</p>
        </div>
      </div>

      <div class="singpass-retrieve">
        <button
          class="btn btn-singpass"
          type="button"
          :disabled="isRetrievingMain || isCurrentSubmitted"
          @click="retrieveMainApplicantFromMyInfo"
        >
          <span v-if="isRetrievingMain">Retrieving...</span>
          <span v-else>Retrieve from MyInfo</span>
        </button>
        <p class="singpass-retrieve__hint">Uses signed-in MyInfo session, or your entered NRIC as fallback.</p>
      </div>

      <p v-if="retrieveMainSuccess" class="retrieve-success">Main applicant details loaded.</p>
      <div v-if="mainApplicantIdentityLocked" class="locked-banner">
        <LockKeyhole :size="18" />
        <div>
          <strong>Read-only from Singpass</strong>
          <p>Identity, marital, and contact fields cannot be edited.</p>
        </div>
      </div>
      <p v-if="retrieveMainError" class="retrieve-error">{{ retrieveMainError }}</p>

      <div class="form-grid">
        <div :class="{ 'field-group--locked': mainApplicantIdentityLocked }">
          <label class="field-label field-label--locked" for="full-name">
            <span>Full Name</span>
            <span v-if="mainApplicantIdentityLocked" class="lock-badge">
              <LockKeyhole :size="12" />
              Read-only
            </span>
          </label>
          <input
            id="full-name"
            v-model="applicationStore.form.fullName"
            :class="['field', { 'field--locked': mainApplicantIdentityLocked }]"
            type="text"
            :disabled="isCurrentSubmitted || mainApplicantIdentityLocked"
          />
        </div>

        <div :class="{ 'field-group--locked': mainApplicantIdentityLocked }">
          <label class="field-label field-label--locked" for="nric">
            <span>NRIC</span>
            <span v-if="mainApplicantIdentityLocked" class="lock-badge">
              <LockKeyhole :size="12" />
              Read-only
            </span>
          </label>
          <input
            id="nric"
            v-model="applicationStore.form.nric"
            :class="['field', { 'field--locked': mainApplicantIdentityLocked }]"
            type="text"
            :disabled="isCurrentSubmitted || mainApplicantIdentityLocked"
          />
        </div>

        <div :class="{ 'field-group--locked': mainApplicantIdentityLocked }">
          <label class="field-label field-label--locked" for="dob">
            <span>Date of Birth</span>
            <span v-if="mainApplicantIdentityLocked" class="lock-badge">
              <LockKeyhole :size="12" />
              Read-only
            </span>
          </label>
          <input
            id="dob"
            v-model="applicationStore.form.dateOfBirth"
            :class="['field', { 'field--locked': mainApplicantIdentityLocked }]"
            type="date"
            :disabled="isCurrentSubmitted || mainApplicantIdentityLocked"
          />
        </div>

        <div :class="{ 'field-group--locked': mainApplicantIncomeLocked }">
          <label class="field-label field-label--locked" for="monthly-income">
            <span>Monthly Income (SGD)</span>
            <span v-if="mainApplicantIncomeLocked" class="lock-badge">
              <LockKeyhole :size="12" />
              Read-only
            </span>
          </label>
          <input
            id="monthly-income"
            v-model="applicationStore.form.monthlyIncome"
            :class="['field', { 'field--locked': mainApplicantIncomeLocked }]"
            type="number"
            min="0"
            step="0.01"
            :disabled="isCurrentSubmitted || mainApplicantIncomeLocked"
          />
        </div>

        <div :class="{ 'field-group--locked': mainApplicantIdentityLocked }">
          <label class="field-label field-label--locked" for="citizenship-status">
            <span>Citizenship / Residency Status</span>
            <span v-if="mainApplicantIdentityLocked" class="lock-badge">
              <LockKeyhole :size="12" />
              Read-only
            </span>
          </label>
          <select
            id="citizenship-status"
            v-model="applicationStore.form.citizenshipStatus"
            :class="['field', { 'field--locked': mainApplicantIdentityLocked }]"
            :disabled="isCurrentSubmitted || mainApplicantIdentityLocked"
          >
            <option disabled value="">Select a status</option>
            <option v-for="option in citizenshipStatusOptions" :key="option" :value="option">{{ option }}</option>
          </select>
        </div>

        <div :class="{ 'field-group--locked': mainApplicantIdentityLocked }">
          <label class="field-label field-label--locked" for="marital-status">
            <span>Marital Status</span>
            <span v-if="mainApplicantIdentityLocked" class="lock-badge">
              <LockKeyhole :size="12" />
              Read-only
            </span>
          </label>
          <select
            id="marital-status"
            v-model="applicationStore.form.maritalStatus"
            :class="['field', { 'field--locked': mainApplicantIdentityLocked }]"
            :disabled="isCurrentSubmitted || mainApplicantIdentityLocked"
          >
            <option disabled value="">Select a marital status</option>
            <option v-for="option in maritalStatusOptions" :key="option" :value="option">{{ option }}</option>
          </select>
        </div>

        <div>
          <label class="field-label" for="contact-number">Contact Number</label>
          <input
            id="contact-number"
            v-model="applicationStore.form.contactNumber"
            class="field"
            type="tel"
            :disabled="isCurrentSubmitted"
          />
        </div>

        <div>
          <label class="field-label" for="email">Email</label>
          <input
            id="email"
            v-model="applicationStore.form.email"
            class="field"
            type="email"
            :disabled="isCurrentSubmitted"
          />
        </div>
      </div>
    </section>

    <section class="form-section">
      <div class="form-section__header">
        <div>
          <div class="form-section__title-row">
            <Users :size="20" />
            <h3>Household Members</h3>
          </div>
        </div>
        <div v-if="!isCurrentSubmitted" class="section-actions">
          <button class="btn btn-secondary" type="button" :disabled="hasCoApplicant" @click="addCoApplicant">
            <CirclePlus :size="16" />
            <span>Add Co-applicant</span>
          </button>
          <button class="btn btn-secondary" type="button" @click="addOccupier">
            <CirclePlus :size="16" />
            <span>Add Occupier</span>
          </button>
        </div>
      </div>

      <div v-if="!hasSupportingMembers" class="empty-members">
        <p>No co-applicants or occupiers added yet.</p>
      </div>

      <div v-if="applicationStore.coApplicants.length > 0" class="member-stack">
        <HouseholdMemberFormCard
          v-for="(member, index) in applicationStore.coApplicants"
          :key="member.id"
          :member="member"
          :title="`Co-applicant ${index + 1}`"
          description="Person applying together with the main applicant."
          :disabled="isCurrentSubmitted"
          :relationship-options="relationshipOptions"
          :marital-status-options="maritalStatusOptions"
          :citizenship-status-options="citizenshipStatusOptions"
          @remove="applicationStore.removeHouseholdMember('CO_APPLICANT', member.id)"
        />
      </div>

      <div v-if="applicationStore.occupiers.length > 0" class="member-stack">
        <HouseholdMemberFormCard
          v-for="(member, index) in applicationStore.occupiers"
          :key="member.id"
          :member="member"
          :title="`Occupier ${index + 1}`"
          description="Household member who is not a co-applicant."
          :disabled="isCurrentSubmitted"
          :relationship-options="relationshipOptions"
          :marital-status-options="maritalStatusOptions"
          :citizenship-status-options="citizenshipStatusOptions"
          @remove="applicationStore.removeHouseholdMember('OCCUPANT', member.id)"
        />
      </div>
    </section>

    <section class="form-section">
      <div class="form-section__header">
        <div>
          <div class="form-section__title-row">
            <FolderInput :size="20" />
            <h3>Supporting Documents</h3>
          </div>
          <p>Upload the required PDFs.</p>
        </div>
      </div>

      <div class="upload-grid">
        <div class="upload-card">
          <div class="upload-card__header">
            <FileText :size="18" />
            <strong>Income PDF</strong>
            <span class="doc-hint">CPF Contribution History</span>
          </div>

          <input
            class="field field--file"
            type="file"
            accept=".pdf,application/pdf"
            :disabled="isCurrentSubmitted"
            @change="handleFileChange($event, 'incomePdfName')"
          />

          <p v-if="applicationStore.documents.incomePdfName" class="filename-tag">
            {{ applicationStore.documents.incomePdfName }}
          </p>
          <p v-else class="doc-note">No income PDF selected yet.</p>
        </div>

        <div class="upload-card">
          <div class="upload-card__header">
            <FileText :size="18" />
            <strong>HFE Letter PDF</strong>
            <span class="doc-hint">HDB Flat Eligibility</span>
          </div>

          <input
            class="field field--file"
            type="file"
            accept=".pdf,application/pdf"
            :disabled="isCurrentSubmitted"
            @change="handleFileChange($event, 'hfeLetterPdfName')"
          />

          <p v-if="applicationStore.documents.hfeLetterPdfName" class="filename-tag">
            {{ applicationStore.documents.hfeLetterPdfName }}
          </p>
          <p v-else class="doc-note">No HFE letter selected yet.</p>
        </div>
      </div>
    </section>

    <section class="form-section">
      <div class="form-section__header">
        <div>
          <div class="form-section__title-row">
            <HousePlus :size="20" />
            <h3>Flat Preferences</h3>
          </div>
          <p>Select your preferred town and flat type.</p>
        </div>
      </div>

      <div class="form-grid">
        <div>
          <label class="field-label" for="preferred-town">Preferred Town Area</label>
          <select
            id="preferred-town"
            v-model="applicationStore.form.preferredTown"
            class="field"
            :disabled="isCurrentSubmitted"
          >
            <option disabled value="">Select a town</option>
            <option v-for="option in applicationStore.townOptions" :key="option" :value="option">{{ option }}</option>
          </select>
        </div>

        <div>
          <label class="field-label" for="flat-type">Flat Type</label>
          <select
            id="flat-type"
            v-model="applicationStore.form.flatType"
            class="field"
            :disabled="isCurrentSubmitted"
          >
            <option disabled value="">Select a flat type</option>
            <option v-for="option in flatTypeOptions" :key="option" :value="option">{{ option }}</option>
          </select>
        </div>
      </div>
    </section>

    <div class="step-actions">
      <button class="btn btn-secondary" type="button" @click="router.push('/')">Back</button>
      <div class="step-actions__group">
        <button
          v-if="!isCurrentSubmitted"
          class="btn btn-secondary"
          type="button"
          @click="showResetModal = true"
        >
          Start Over
        </button>
        <button class="btn btn-primary" type="button" @click="handlePrimaryAction">
          {{ submitLabel }}
        </button>
      </div>
    </div>

    <p v-if="applicationStore.applicationError" class="retrieve-error feedback-message">
      {{ applicationStore.applicationError }}
    </p>

    <SelectionModal
      :open="showSubmissionSummary"
      eyebrow="Final Review"
      title="Review your application before payment"
      message="Check the details below. Go back to edit if needed."
      size="wide"
      confirm-label="Looks Correct, Continue"
      cancel-label="Go Back and Edit"
      @close="showSubmissionSummary = false"
      @confirm="continueToPayment"
    >
      <div class="summary-preview">
        <div class="summary-hero">
          <div class="summary-hero__item">
            <span>Main Applicant</span>
            <strong>{{ applicationStore.form.fullName || '-' }}</strong>
          </div>
          <div class="summary-hero__item">
            <span>Co-applicant</span>
            <strong>{{ primaryCoApplicant?.fullName || 'Not added' }}</strong>
          </div>
          <div class="summary-hero__item">
            <span>Preferred Town</span>
            <strong>{{ applicationStore.form.preferredTown || '-' }}</strong>
          </div>
        </div>

        <div class="summary-preview__section summary-preview__section--person">
          <p class="summary-preview__heading">Main Applicant</p>
          <div class="summary-preview__row">
            <span>Name</span>
            <strong>{{ applicationStore.form.fullName || '-' }}</strong>
          </div>
          <div class="summary-preview__row">
            <span>NRIC / FIN</span>
            <strong>{{ applicationStore.form.nric || '-' }}</strong>
          </div>
          <div class="summary-preview__row">
            <span>Date of Birth</span>
            <strong>{{ applicationStore.form.dateOfBirth || '-' }}</strong>
          </div>
          <div class="summary-preview__row">
            <span>Monthly Income</span>
            <strong>{{ applicationStore.form.monthlyIncome || '-' }}</strong>
          </div>
          <div class="summary-preview__row">
            <span>Citizenship Status</span>
            <strong>{{ applicationStore.form.citizenshipStatus || '-' }}</strong>
          </div>
          <div class="summary-preview__row">
            <span>Marital Status</span>
            <strong>{{ applicationStore.form.maritalStatus || '-' }}</strong>
          </div>
          <div class="summary-preview__row">
            <span>Relationship</span>
            <strong>Self</strong>
          </div>
          <div class="summary-preview__row">
            <span>Contact Number</span>
            <strong>{{ applicationStore.form.contactNumber || '-' }}</strong>
          </div>
          <div class="summary-preview__row">
            <span>Email</span>
            <strong>{{ applicationStore.form.email || '-' }}</strong>
          </div>
        </div>

        <div class="summary-preview__section summary-preview__section--person">
          <p class="summary-preview__heading">Co-applicant</p>
          <template v-if="primaryCoApplicant">
            <div class="summary-preview__row">
              <span>Name</span>
              <strong>{{ primaryCoApplicant.fullName || '-' }}</strong>
            </div>
            <div class="summary-preview__row">
              <span>NRIC / FIN</span>
              <strong>{{ primaryCoApplicant.nric || '-' }}</strong>
            </div>
            <div class="summary-preview__row">
              <span>Date of Birth</span>
              <strong>{{ primaryCoApplicant.dateOfBirth || '-' }}</strong>
            </div>
            <div class="summary-preview__row">
              <span>Monthly Income</span>
              <strong>{{ primaryCoApplicant.monthlyIncome || '-' }}</strong>
            </div>
            <div class="summary-preview__row">
              <span>Citizenship Status</span>
              <strong>{{ primaryCoApplicant.citizenshipStatus || '-' }}</strong>
            </div>
            <div class="summary-preview__row">
              <span>Marital Status</span>
              <strong>{{ primaryCoApplicant.maritalStatus || '-' }}</strong>
            </div>
            <div class="summary-preview__row">
              <span>Relationship</span>
              <strong>{{ primaryCoApplicant.relationshipToMain || '-' }}</strong>
            </div>
            <div class="summary-preview__row">
              <span>Contact Number</span>
              <strong>{{ primaryCoApplicant.contactNumber || '-' }}</strong>
            </div>
            <div class="summary-preview__row">
              <span>Email</span>
              <strong>{{ primaryCoApplicant.email || '-' }}</strong>
            </div>
          </template>
          <p v-else class="summary-preview__empty">No co-applicant added.</p>
        </div>

        <div class="summary-preview__section summary-preview__section--wide">
          <p class="summary-preview__heading">Occupiers</p>
          <p v-if="applicationStore.occupiers.length === 0" class="summary-preview__empty">No occupiers added.</p>

          <div v-if="applicationStore.occupiers.length > 0" class="summary-member-list">
            <div
              v-for="(member, index) in applicationStore.occupiers"
              :key="`occupier-${member.id}`"
              class="summary-preview__member"
            >
              <span class="summary-preview__member-role">Occupier {{ index + 1 }}</span>
              <strong>{{ member.fullName || '-' }}</strong>
              <span><strong>Relationship:</strong> {{ member.relationshipToMain || '-' }}</span>
              <span><strong>Monthly Income:</strong> {{ member.monthlyIncome || '-' }}</span>
              <span><strong>Contact Number:</strong> {{ member.contactNumber || '-' }}</span>
              <span><strong>Email:</strong> {{ member.email || '-' }}</span>
            </div>
          </div>
        </div>

        <div class="summary-preview__section">
          <p class="summary-preview__heading">Supporting Documents</p>
          <div class="summary-preview__row">
            <span>Income PDF</span>
            <strong>{{ applicationStore.documents.incomePdfName || '-' }}</strong>
          </div>
          <div class="summary-preview__row">
            <span>HFE Letter PDF</span>
            <strong>{{ applicationStore.documents.hfeLetterPdfName || '-' }}</strong>
          </div>
        </div>

        <div class="summary-preview__section">
          <p class="summary-preview__heading">Flat Preferences</p>
          <div class="summary-preview__row">
            <span>Preferred Town Area</span>
            <strong>{{ applicationStore.form.preferredTown || '-' }}</strong>
          </div>
          <div class="summary-preview__row">
            <span>Flat Type</span>
            <strong>{{ applicationStore.form.flatType || '-' }}</strong>
          </div>
        </div>
      </div>
    </SelectionModal>

    <SelectionModal
      :open="showResetModal"
      eyebrow="Start Over"
      title="Start a fresh application?"
      message="This clears the household details and selected document names stored on this device for your current application in progress."
      confirm-label="Clear Progress"
      @close="showResetModal = false"
      @confirm="resetApplication"
    />
  </div>
</template>

<style scoped>
.step-card {
  padding: 32px;
}

.step-card__copy h2 {
  margin: 0 0 10px;
  font-size: 1.7rem;
  line-height: 1.1;
  letter-spacing: -0.03em;
}

.step-card__copy p {
  margin: 0 0 24px;
  color: rgba(29, 29, 31, 0.72);
}

.workflow-note {
  margin-bottom: 18px;
  padding: 18px 20px;
  border-radius: 14px;
  background: linear-gradient(135deg, rgba(200, 16, 46, 0.05), rgba(255, 255, 255, 0.95));
  border: 1px solid rgba(200, 16, 46, 0.12);
}

.workflow-note__title {
  margin: 0 0 8px;
  font-size: 0.84rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-red);
}

.workflow-note p:last-child {
  margin: 0;
  color: rgba(29, 29, 31, 0.72);
  line-height: 1.6;
}

.progress-note {
  margin: 0 0 20px;
  font-size: 0.9rem;
  font-weight: 600;
  color: rgba(29, 29, 31, 0.6);
}

.submitted-banner {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: center;
  padding: 16px 18px;
  margin-bottom: 18px;
  border: 1px solid rgba(200, 16, 46, 0.18);
  border-radius: 12px;
  background: linear-gradient(135deg, rgba(200, 16, 46, 0.06), rgba(255, 255, 255, 0.96));
}

.submitted-banner p {
  margin: 6px 0 0;
  color: rgba(29, 29, 31, 0.7);
}

.form-section + .form-section {
  margin-top: 28px;
}

.form-section__header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  margin-bottom: 18px;
}

.form-section__title-row {
  display: inline-flex;
  align-items: center;
  gap: 10px;
}

.form-section__header h3 {
  margin: 0;
  font-size: 1.16rem;
}

.form-section__header p {
  margin: 8px 0 0;
  color: rgba(29, 29, 31, 0.64);
  line-height: 1.5;
}

.section-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.section-actions .btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.singpass-retrieve {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: center;
  margin-bottom: 16px;
  padding: 16px 18px;
  border-radius: 12px;
  background: #f5f5f7;
}

.singpass-retrieve__hint {
  margin: 0;
  color: rgba(29, 29, 31, 0.58);
  font-size: 0.88rem;
  line-height: 1.5;
}

.btn-singpass {
  align-self: flex-start;
  padding: 10px 20px;
  border-radius: 8px;
  border: none;
  background: #c8102e;
  color: #fff;
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
}

.btn-singpass:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.retrieve-success {
  margin: 0 0 12px;
  font-size: 0.875rem;
  color: rgba(29, 29, 31, 0.72);
}

.locked-banner {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 12px;
  margin: 0 0 16px;
  padding: 15px 16px;
  border-radius: 12px;
  background: repeating-linear-gradient(
    -45deg,
    rgba(29, 29, 31, 0.04),
    rgba(29, 29, 31, 0.04) 10px,
    rgba(29, 29, 31, 0.08) 10px,
    rgba(29, 29, 31, 0.08) 20px
  );
  border: 1px solid rgba(29, 29, 31, 0.24);
  color: var(--color-charcoal);
}

.locked-banner strong {
  display: block;
  margin-bottom: 4px;
  font-size: 0.96rem;
}

.locked-banner p {
  margin: 0;
  color: rgba(29, 29, 31, 0.68);
  line-height: 1.5;
}

.retrieve-error {
  margin: 0;
  font-size: 0.875rem;
  color: #c8102e;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
  align-items: start;
}

.form-grid > div {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
}

.form-grid :deep(.field-label) {
  width: 100%;
}

.form-grid :deep(.field) {
  width: 100%;
  min-height: 44px;
  box-sizing: border-box;
}

.field-label--locked {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: center;
}

.field-group--locked .field:disabled,
.field--locked:disabled {
  opacity: 1;
  color: rgba(29, 29, 31, 0.86);
  background: linear-gradient(135deg, rgba(29, 29, 31, 0.04), rgba(29, 29, 31, 0.1));
  border-color: rgba(29, 29, 31, 0.3);
  box-shadow: inset 0 0 0 1px rgba(29, 29, 31, 0.12);
  cursor: not-allowed;
}

.lock-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  border-radius: 999px;
  border: 1px dashed rgba(29, 29, 31, 0.38);
  background: rgba(29, 29, 31, 0.08);
  color: rgba(29, 29, 31, 0.78);
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  flex-shrink: 0;
}

.member-limit-note {
  margin: 0 0 16px;
  font-size: 0.88rem;
  color: rgba(29, 29, 31, 0.58);
}

.empty-members {
  padding: 18px 20px;
  border: 1px dashed var(--color-border);
  border-radius: 12px;
  color: rgba(29, 29, 31, 0.58);
  background: rgba(29, 29, 31, 0.02);
}

.empty-members p {
  margin: 0;
}

.member-stack {
  display: grid;
  gap: 16px;
}

.member-stack + .member-stack {
  margin-top: 16px;
}

.upload-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
}

.upload-card {
  padding: 20px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-white);
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.upload-card__header {
  display: flex;
  align-items: center;
  gap: 10px;
}

.doc-hint {
  font-size: 0.76rem;
  color: rgba(29, 29, 31, 0.42);
  font-weight: 500;
}

.field--file {
  padding-top: 10px;
  padding-bottom: 10px;
}

.filename-tag {
  margin: 0;
  font-size: 0.86rem;
  font-weight: 600;
  color: var(--color-red);
}

.doc-note {
  margin: 0;
  font-size: 0.86rem;
  color: rgba(29, 29, 31, 0.56);
}

.submit-note {
  margin-top: 18px;
  padding: 16px 18px;
  border-radius: 10px;
  background: rgba(29, 29, 31, 0.04);
}

.submit-note p {
  margin: 0;
  color: rgba(29, 29, 31, 0.68);
  line-height: 1.5;
}

.step-actions {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-top: 32px;
}

.step-actions__group {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.feedback-message {
  margin-top: 14px;
}

.summary-preview {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.summary-hero {
  grid-column: 1 / -1;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.summary-hero__item {
  padding: 16px 18px;
  border-radius: 14px;
  background: linear-gradient(140deg, rgba(200, 16, 46, 0.08), rgba(255, 244, 232, 0.9));
  border: 1px solid rgba(200, 16, 46, 0.12);
}

.summary-hero__item span {
  display: block;
  margin-bottom: 8px;
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: rgba(29, 29, 31, 0.56);
}

.summary-hero__item strong {
  font-size: 1.02rem;
  line-height: 1.35;
}

.summary-preview__section {
  padding: 16px;
  border: 1px solid var(--color-border);
  border-radius: 12px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.95), rgba(29, 29, 31, 0.02));
}

.summary-preview__section--wide {
  grid-column: 1 / -1;
}

.summary-preview__section--person {
  min-height: 100%;
}

.summary-preview__heading {
  margin: 0 0 12px;
  font-size: 0.82rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: rgba(29, 29, 31, 0.52);
}

.summary-preview__row {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding: 6px 0;
}

.summary-preview__row span {
  color: rgba(29, 29, 31, 0.6);
}

.summary-preview__row strong {
  text-align: right;
  word-break: break-word;
}

.summary-member-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
}

.summary-preview__member {
  display: grid;
  gap: 6px;
  padding: 14px;
  border: 1px solid rgba(29, 29, 31, 0.08);
  border-radius: 12px;
  background: rgba(29, 29, 31, 0.02);
}

.summary-preview__member-role {
  display: inline-flex;
  width: fit-content;
  padding: 4px 8px;
  border-radius: 999px;
  background: rgba(200, 16, 46, 0.08);
  color: var(--color-red);
  font-size: 0.74rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.summary-preview__member span {
  color: rgba(29, 29, 31, 0.64);
}

.summary-preview__empty {
  margin: 0;
  color: rgba(29, 29, 31, 0.6);
}

@media (max-width: 840px) {
  .form-section__header,
  .singpass-retrieve {
    flex-direction: column;
    align-items: flex-start;
  }
}

@media (max-width: 720px) {
  .form-grid,
  .upload-grid {
    grid-template-columns: 1fr;
  }

  .summary-preview,
  .summary-hero {
    grid-template-columns: 1fr;
  }

  .step-actions {
    flex-direction: column-reverse;
  }

  .step-actions__group {
    flex-direction: column;
  }

  .summary-preview__row {
    flex-direction: column;
    gap: 4px;
  }

  .summary-preview__row strong {
    text-align: left;
  }
}
</style>

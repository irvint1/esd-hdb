<script setup lang="ts">
import { computed, ref } from 'vue'
import { LockKeyhole, Trash2, UserRoundPlus } from 'lucide-vue-next'
import { getMyInfoProfile } from '@/services/myinfo'
import type { HouseholdMemberForm } from '@/stores/application'
import { useApplicationStore } from '@/stores/application'

const props = defineProps<{
  title: string
  description: string
  disabled?: boolean
  relationshipOptions: string[]
  maritalStatusOptions: string[]
  citizenshipStatusOptions: string[]
}>()

const emit = defineEmits<{
  remove: []
}>()

const member = defineModel<HouseholdMemberForm>('member', { required: true })
const applicationStore = useApplicationStore()
const memberProfileLocked = computed(() => props.disabled || member.value.isRetrievedFromMyInfo)
const memberIncomeLocked = computed(
  () =>
    (props.disabled || member.value.isRetrievedFromMyInfo) &&
    member.value.monthlyIncome.trim().length > 0,
)

const isRetrieving = ref(false)
const retrieveSuccess = ref(false)
const retrieveError = ref('')

async function retrieveFromSingPass() {
  if (!member.value.nric.trim()) {
    retrieveError.value = 'Enter the household member NRIC / FIN first.'
    retrieveSuccess.value = false
    return
  }

  isRetrieving.value = true
  retrieveSuccess.value = false
  retrieveError.value = ''

  try {
    const persona = await getMyInfoProfile(member.value.nric)
    if (!persona) {
      retrieveError.value = 'No MyInfo data found for this NRIC / FIN.'
      return
    }

    applicationStore.fillHouseholdMemberFromMyInfo(member.value.id, persona)
    retrieveSuccess.value = true
  } catch {
    retrieveError.value = 'Unable to retrieve MyInfo data right now.'
  } finally {
    isRetrieving.value = false
  }
}
</script>

<template>
  <article class="surface member-card">
    <div class="member-card__header">
      <div>
        <div class="member-card__title-row">
          <UserRoundPlus :size="18" />
          <h3>{{ title }}</h3>
        </div>
        <p>{{ description }}</p>
      </div>
      <button
        v-if="!disabled"
        class="member-card__remove"
        type="button"
        @click="emit('remove')"
      >
        <Trash2 :size="16" />
        <span>Remove</span>
      </button>
    </div>

    <div class="member-card__toolbar">
      <button class="btn btn-secondary" type="button" :disabled="disabled || isRetrieving" @click="retrieveFromSingPass">
        {{ isRetrieving ? 'Retrieving...' : 'Retrieve from Singpass' }}
      </button>
      <p class="member-card__hint">Enter NRIC / FIN first.</p>
    </div>

    <p v-if="retrieveSuccess" class="member-card__feedback member-card__feedback--success">
      Member details loaded.
    </p>
    <div v-if="member.isRetrievedFromMyInfo" class="locked-banner">
      <LockKeyhole :size="16" />
      <div>
        <strong>Read-only from Singpass</strong>
        <p>Identity fields cannot be edited. Relationship, contact number, and email stay editable.</p>
      </div>
    </div>
    <p v-if="retrieveError" class="member-card__feedback member-card__feedback--error">
      {{ retrieveError }}
    </p>

    <div class="member-grid">
      <!-- Locked Fields Section -->
      <div :class="{ 'field-group--locked': member.isRetrievedFromMyInfo }">
        <label class="field-label field-label--locked" :for="`${member.id}-nric`">
          <span>NRIC / FIN</span>
          <span v-if="member.isRetrievedFromMyInfo" class="lock-badge">
            <LockKeyhole :size="12" />
            Read-only
          </span>
        </label>
        <input
          :id="`${member.id}-nric`"
          v-model="member.nric"
          :class="['field', { 'field--locked': member.isRetrievedFromMyInfo }]"
          type="text"
          :disabled="memberProfileLocked"
        />
      </div>

      <div :class="{ 'field-group--locked': member.isRetrievedFromMyInfo }">
        <label class="field-label field-label--locked" :for="`${member.id}-name`">
          <span>Full Name</span>
          <span v-if="member.isRetrievedFromMyInfo" class="lock-badge">
            <LockKeyhole :size="12" />
            Read-only
          </span>
        </label>
        <input
          :id="`${member.id}-name`"
          v-model="member.fullName"
          :class="['field', { 'field--locked': member.isRetrievedFromMyInfo }]"
          type="text"
          :disabled="memberProfileLocked"
        />
      </div>

      <div :class="{ 'field-group--locked': member.isRetrievedFromMyInfo }">
        <label class="field-label field-label--locked" :for="`${member.id}-dob`">
          <span>Date of Birth</span>
          <span v-if="member.isRetrievedFromMyInfo" class="lock-badge">
            <LockKeyhole :size="12" />
            Read-only
          </span>
        </label>
        <input
          :id="`${member.id}-dob`"
          v-model="member.dateOfBirth"
          :class="['field', { 'field--locked': member.isRetrievedFromMyInfo }]"
          type="date"
          :disabled="memberProfileLocked"
        />
      </div>

      <div :class="{ 'field-group--locked': memberIncomeLocked }">
        <label class="field-label field-label--locked" :for="`${member.id}-monthly-income`">
          <span>Monthly Income (SGD)</span>
          <span v-if="memberIncomeLocked" class="lock-badge">
            <LockKeyhole :size="12" />
            Read-only
          </span>
        </label>
        <input
          :id="`${member.id}-monthly-income`"
          v-model="member.monthlyIncome"
          :class="['field', { 'field--locked': memberIncomeLocked }]"
          type="number"
          min="0"
          step="0.01"
          :disabled="memberIncomeLocked"
        />
      </div>

      <div :class="{ 'field-group--locked': member.isRetrievedFromMyInfo }">
        <label class="field-label field-label--locked" :for="`${member.id}-citizenship`">
          <span>Citizenship / Residency Status</span>
          <span v-if="member.isRetrievedFromMyInfo" class="lock-badge">
            <LockKeyhole :size="12" />
            Read-only
          </span>
        </label>
        <select
          :id="`${member.id}-citizenship`"
          v-model="member.citizenshipStatus"
          :class="['field', { 'field--locked': member.isRetrievedFromMyInfo }]"
          :disabled="memberProfileLocked"
        >
          <option disabled value="">Select a status</option>
          <option
            v-for="option in props.citizenshipStatusOptions"
            :key="option"
            :value="option"
          >
            {{ option }}
          </option>
        </select>
      </div>

      <div :class="{ 'field-group--locked': member.isRetrievedFromMyInfo }">
        <label class="field-label field-label--locked" :for="`${member.id}-marital`">
          <span>Marital Status</span>
          <span v-if="member.isRetrievedFromMyInfo" class="lock-badge">
            <LockKeyhole :size="12" />
            Read-only
          </span>
        </label>
        <select
          :id="`${member.id}-marital`"
          v-model="member.maritalStatus"
          :class="['field', { 'field--locked': member.isRetrievedFromMyInfo }]"
          :disabled="memberProfileLocked"
        >
          <option disabled value="">Select a marital status</option>
          <option v-for="option in props.maritalStatusOptions" :key="option" :value="option">{{ option }}</option>
        </select>
      </div>

      <div>
        <label class="field-label" :for="`${member.id}-relationship`">Relationship to Main Applicant</label>
        <select
          :id="`${member.id}-relationship`"
          v-model="member.relationshipToMain"
          class="field"
          :disabled="disabled"
        >
          <option disabled value="">Select a relationship</option>
          <option v-for="option in props.relationshipOptions" :key="option" :value="option">{{ option }}</option>
        </select>
      </div>

      <div>
        <label class="field-label" :for="`${member.id}-contact-number`">Contact Number</label>
        <input
          :id="`${member.id}-contact-number`"
          v-model="member.contactNumber"
          class="field"
          type="tel"
          :disabled="disabled"
        />
      </div>

      <div>
        <label class="field-label" :for="`${member.id}-email`">Email</label>
        <input
          :id="`${member.id}-email`"
          v-model="member.email"
          class="field"
          type="email"
          :disabled="disabled"
        />
      </div>
    </div>
  </article>
</template>

<style scoped>
.member-card {
  padding: 22px;
}

.member-card__header {
  display: flex;
  justify-content: space-between;
  gap: 18px;
  margin-bottom: 18px;
}

.member-card__title-row {
  display: inline-flex;
  align-items: center;
  gap: 10px;
}

.member-card__header h3 {
  margin: 0;
  font-size: 1.08rem;
}

.member-card__header p {
  margin: 8px 0 0;
  color: rgba(29, 29, 31, 0.64);
  line-height: 1.5;
}

.member-card__remove {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: fit-content;
  padding: 10px 14px;
  border: 1px solid rgba(200, 16, 46, 0.16);
  border-radius: 10px;
  background: rgba(200, 16, 46, 0.04);
  color: var(--color-red);
  font-weight: 600;
  cursor: pointer;
}

.member-card__toolbar {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: center;
  margin-bottom: 16px;
}

.member-card__hint {
  margin: 0;
  color: rgba(29, 29, 31, 0.58);
  font-size: 0.88rem;
  line-height: 1.5;
}

.member-card__feedback {
  margin: 0 0 14px;
  font-size: 0.88rem;
  font-weight: 600;
}

.member-card__feedback--success {
  color: rgba(29, 29, 31, 0.72);
}

.locked-banner {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 12px;
  margin: 0 0 16px;
  padding: 14px 16px;
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
  font-size: 0.94rem;
}

.locked-banner p {
  margin: 0;
  color: rgba(29, 29, 31, 0.66);
  line-height: 1.5;
}

.member-card__feedback--error {
  color: #c8102e;
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

.member-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  align-items: start;
}

.member-grid > div {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
}

.member-grid :deep(.field-label) {
  width: 100%;
}

.member-grid :deep(.field) {
  width: 100%;
  min-height: 44px;
  box-sizing: border-box;
}

@media (max-width: 720px) {
  .member-card__header,
  .member-card__toolbar {
    flex-direction: column;
    align-items: flex-start;
  }

  .member-grid {
    grid-template-columns: 1fr;
  }
}
</style>

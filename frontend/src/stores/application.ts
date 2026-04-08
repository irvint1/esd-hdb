import { computed, ref, watch } from 'vue'
import { defineStore } from 'pinia'
import { getCitizenshipStatusFromProfile, getMonthlyIncomeFromProfile, mapMaritalStatus } from '@/services/myinfo'
import {
  type ApplicationMemberRequest,
  type ApplyBtoApplicationPayload,
  type ApplicationMemberRecord,
  type ApplicationRecord,
  type ProjectRecord,
  fetchProjects,
  fetchAvailableFlats,
  fetchFlatSelections,
} from '@/services/api'
import type { MyInfoPersona } from '@/data/myinfoPersonas'

const STORAGE_KEY = 'hdb-flat-portal-application'

export type ApplicationStatus = 'editing' | 'processing' | 'successful' | 'balloted' | 'selected'
export type HouseholdMemberRole = 'CO_APPLICANT' | 'OCCUPANT'

export interface ApplicationForm {
  fullName: string
  nric: string
  dateOfBirth: string
  monthlyIncome: string
  contactNumber: string
  email: string
  maritalStatus: string
  citizenshipStatus: string
  preferredTown: string
  flatType: string
}

export interface HouseholdMemberForm {
  id: string
  memberRole: HouseholdMemberRole
  fullName: string
  nric: string
  dateOfBirth: string
  monthlyIncome: string
  relationshipToMain: string
  citizenshipStatus: string
  maritalStatus: string
  contactNumber: string
  email: string
  isRetrievedFromMyInfo: boolean
}

export interface ApplicationDocuments {
  incomePdfName: string
  hfeLetterPdfName: string
}

interface ApplicationDocumentFiles {
  incomePdfFile: File | null
  hfeLetterPdfFile: File | null
}

export interface AvailableUnit {
  id: number
  unitNumber: string
  floor: number
  facing: string
  sqm: number
  price: number
  development: string
}

interface PersistedApplicationState {
  form: ApplicationForm
  mainApplicantProfileLocked: boolean
  coApplicants: HouseholdMemberForm[]
  occupiers: HouseholdMemberForm[]
  documents: ApplicationDocuments
  status: ApplicationStatus
  queueNumber: string | null
  selectedUnit: AvailableUnit | null
  lastSubmittedAt: string | null
  linkedApplications: ApplicationRecord[]
  linkedNric: string | null
  currentApplicationId: number | null
}

const REQUIRED_SUBMISSION_FIELDS: Array<keyof ApplicationForm> = [
  'fullName',
  'nric',
  'dateOfBirth',
  'monthlyIncome',
  'contactNumber',
  'email',
  'maritalStatus',
  'citizenshipStatus',
  'preferredTown',
  'flatType',
]

const fieldLabels: Record<keyof ApplicationForm, string> = {
  fullName: 'Full name',
  nric: 'NRIC',
  dateOfBirth: 'Date of birth',
  monthlyIncome: 'Monthly income',
  contactNumber: 'Contact number',
  email: 'Email',
  maritalStatus: 'Marital status',
  citizenshipStatus: 'Citizenship / residency status',
  preferredTown: 'Preferred town',
  flatType: 'Flat type',
}

const fallbackTownOptions = ['Tengah', 'Kallang/Whampoa', 'Queenstown', 'Punggol'] as const

const developmentByTown: Record<string, string> = {
  Tengah: 'Tengah Garden Walk',
  'Kallang/Whampoa': 'Kallang RiverFront',
  Queenstown: 'Queenstown SkyGrove',
  Punggol: 'Punggol SeaVista',
}

const projectIdByTown: Record<string, number> = {
  Tengah: 40,
  'Kallang/Whampoa': 43,
  Queenstown: 42,
  Punggol: 41,
}

const townByProjectId: Record<number, string> = Object.fromEntries(
  Object.entries(projectIdByTown).map(([town, projectId]) => [projectId, town]),
) as Record<number, string>


function createDefaultForm(): ApplicationForm {
  return {
    fullName: '',
    nric: '',
    dateOfBirth: '',
    monthlyIncome: '',
    contactNumber: '',
    email: '',
    maritalStatus: '',
    citizenshipStatus: '',
    preferredTown: '',
    flatType: '',
  }
}

function createDefaultDocuments(): ApplicationDocuments {
  return {
    incomePdfName: '',
    hfeLetterPdfName: '',
  }
}

function createDefaultDocumentFiles(): ApplicationDocumentFiles {
  return {
    incomePdfFile: null,
    hfeLetterPdfFile: null,
  }
}

function createMemberId(): string {
  return `member-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function createHouseholdMember(role: HouseholdMemberRole): HouseholdMemberForm {
  return {
    id: createMemberId(),
    memberRole: role,
    fullName: '',
    nric: '',
    dateOfBirth: '',
    monthlyIncome: '',
    relationshipToMain: '',
    citizenshipStatus: '',
    maritalStatus: '',
    contactNumber: '',
    email: '',
    isRetrievedFromMyInfo: false,
  }
}

function mergeHouseholdMember(member: Partial<HouseholdMemberForm> | undefined, role: HouseholdMemberRole) {
  return {
    ...createHouseholdMember(role),
    ...member,
    memberRole: role,
    id: member?.id ?? createMemberId(),
  }
}

function buildQueueNumber(nric: string): string {
  const digits = nric.replace(/\D/g, '').slice(0, 5) || '20481'
  return `Q${digits}`
}


function mapFlatServiceRowToUnit(row: {
  flat_id: number
  floor_number: number
  unit_number: string
  area_sqm: number
  price: number
  project_name: string
}): AvailableUnit {
  const floorNumber = Number.isFinite(row.floor_number) ? Number(row.floor_number) : 0
  const unit = String(row.unit_number ?? '').trim()
  const unitNumber = unit.includes('-')
    ? unit
    : unit
      ? `${String(floorNumber).padStart(2, '0')}-${unit}`
      : String(row.flat_id)

  return {
    id: row.flat_id,
    unitNumber,
    floor: floorNumber,
    facing: 'N/A',
    sqm: Number(row.area_sqm ?? 0),
    price: Number(row.price ?? 0),
    development: row.project_name || 'HDB Development',
  }
}

function readPersistedState(): PersistedApplicationState | null {
  if (typeof window === 'undefined') {
    return null
  }

  const rawState = window.localStorage.getItem(STORAGE_KEY)
  if (!rawState) {
    return null
  }

  try {
    return JSON.parse(rawState) as PersistedApplicationState
  } catch {
    window.localStorage.removeItem(STORAGE_KEY)
    return null
  }
}

function toTimestamp(value: string | null): number {
  if (!value) {
    return 0
  }

  const timestamp = Date.parse(value)
  return Number.isNaN(timestamp) ? 0 : timestamp
}

function sortApplications(applications: ApplicationRecord[]): ApplicationRecord[] {
  return [...applications].sort((left, right) => {
    const rightTime =
      toTimestamp(right.updated_at) || toTimestamp(right.submitted_at) || toTimestamp(right.created_at)
    const leftTime =
      toTimestamp(left.updated_at) || toTimestamp(left.submitted_at) || toTimestamp(left.created_at)

    if (rightTime !== leftTime) {
      return rightTime - leftTime
    }

    return right.application_id - left.application_id
  })
}

function hasText(value: string): boolean {
  return value.trim().length > 0
}

function normaliseNric(value: string): string {
  return value.trim().toUpperCase()
}

function buildDocumentLabel(documentId: number | null, fallback: string): string {
  return typeof documentId === 'number' && documentId > 0 ? `${fallback} #${documentId}` : ''
}

function mapApplicationMemberToForm(member: ApplicationMemberRecord): HouseholdMemberForm {
  return {
    id: String(member.member_id),
    memberRole: member.member_role === 'CO_APPLICANT' ? 'CO_APPLICANT' : 'OCCUPANT',
    fullName: member.full_name,
    nric: member.nric_fin,
    dateOfBirth: member.date_of_birth ?? '',
    monthlyIncome: member.income_amount !== null ? String(member.income_amount) : '',
    relationshipToMain: member.relationship_to_main,
    citizenshipStatus: member.citizenship_status,
    maritalStatus: member.marital_status ?? '',
    contactNumber: member.contact_number ?? '',
    email: member.email ?? '',
    isRetrievedFromMyInfo: false,
  }
}

function isValidEmail(value: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim())
}

function isPdfSelection(file: File | null, fileName: string): boolean {
  const normalisedName = fileName.trim().toLowerCase()

  if (file) {
    return file.type === 'application/pdf' || file.name.trim().toLowerCase().endsWith('.pdf')
  }

  return normalisedName.endsWith('.pdf')
}

function parseIncomeAmount(value: string): number | null {
  const normalised = value
    .replace(/,/g, '')
    .replace(/[^0-9.\-]/g, '')
    .trim()
  if (!normalised) {
    return null
  }

  const parsed = Number.parseFloat(normalised)
  if (Number.isNaN(parsed) || parsed < 0) {
    return null
  }

  return Number.parseFloat(parsed.toFixed(2))
}

export const useApplicationStore = defineStore('application', () => {
  const persistedState = readPersistedState()

  const form = ref<ApplicationForm>({
    ...createDefaultForm(),
    ...(persistedState?.form ?? {}),
  })
  const mainApplicantProfileLocked = ref(persistedState?.mainApplicantProfileLocked ?? false)
  const coApplicants = ref<HouseholdMemberForm[]>(
    (persistedState?.coApplicants ?? []).map((member) => mergeHouseholdMember(member, 'CO_APPLICANT')),
  )
  const occupiers = ref<HouseholdMemberForm[]>(
    (persistedState?.occupiers ?? []).map((member) => mergeHouseholdMember(member, 'OCCUPANT')),
  )
  const documents = ref<ApplicationDocuments>({
    ...createDefaultDocuments(),
    ...(persistedState?.documents ?? {}),
  })
  const documentFiles = ref<ApplicationDocumentFiles>(createDefaultDocumentFiles())
  const status = ref<ApplicationStatus>(persistedState?.status ?? 'editing')
  const queueNumber = ref<string | null>(persistedState?.queueNumber ?? null)
  const selectedUnit = ref<AvailableUnit | null>(persistedState?.selectedUnit ?? null)
  const lastSubmittedAt = ref<string | null>(persistedState?.lastSubmittedAt ?? null)
  const linkedApplications = ref<ApplicationRecord[]>(
    sortApplications(persistedState?.linkedApplications ?? []),
  )
  const linkedNric = ref<string | null>(persistedState?.linkedNric ?? null)
  const currentApplicationId = ref<number | null>(persistedState?.currentApplicationId ?? null)
  const applicationError = ref('')
  const availableUnitsState = ref<AvailableUnit[]>([])
  const isLoadingAvailableUnits = ref(false)
  const projectCatalog = ref<ProjectRecord[]>([])
  const isLoadingProjectCatalog = ref(false)

  const availableUnits = computed(() => availableUnitsState.value)
  const projectByTown = computed(() => {
    const map = new Map<string, ProjectRecord>()

    for (const project of projectCatalog.value) {
      if (project.status !== 'open') {
        continue
      }

      const existing = map.get(project.town_name)
      if (!existing) {
        map.set(project.town_name, project)
        continue
      }

      if (
        project.exercise_id > existing.exercise_id
        || (project.exercise_id === existing.exercise_id && project.project_id > existing.project_id)
      ) {
        map.set(project.town_name, project)
      }
    }

    return map
  })

  const townOptions = computed(() => {
    const liveTowns = [...projectByTown.value.keys()].sort((left, right) => left.localeCompare(right))
    if (liveTowns.length > 0) {
      return liveTowns
    }

    return [...fallbackTownOptions]
  })

  const developmentName = computed(() => {
    const project = projectByTown.value.get(form.value.preferredTown)
    if (project) {
      return project.project_name
    }

    return developmentByTown[form.value.preferredTown] ?? 'HDB Development'
  })
  const hasBallotAccess = computed(() => ['balloted', 'selected'].includes(status.value))
  const hasRequiredDocuments = computed(
    () => hasText(documents.value.incomePdfName) && hasText(documents.value.hfeLetterPdfName),
  )
  const submittedApplications = computed(() =>
    linkedApplications.value.filter((application) => application.application_status === 'SUBMITTED'),
  )
  const latestApplication = computed(() => linkedApplications.value[0] ?? null)
  const hasExistingApplications = computed(() => linkedApplications.value.length > 0)
  const currentApplication = computed(
    () =>
      linkedApplications.value.find((application) => application.application_id === currentApplicationId.value) ?? null,
  )
  const isCurrentSubmitted = computed(
    () =>
      currentApplication.value?.application_status === 'SUBMITTED' ||
      currentApplication.value?.application_status === 'SUCCESSFUL' ||
      status.value === 'processing' ||
      status.value === 'successful',
  )
  const firstSubmitted = computed(() => submittedApplications.value[0] ?? null)
  const hasSubmittedApplication = computed(() => submittedApplications.value.length > 0)
  const householdMembers = computed(() => [...coApplicants.value, ...occupiers.value])
  const householdMemberCount = computed(() => householdMembers.value.length)

  function persistState() {
    if (typeof window === 'undefined') {
      return
    }

    const payload: PersistedApplicationState = {
      form: form.value,
      mainApplicantProfileLocked: mainApplicantProfileLocked.value,
      coApplicants: coApplicants.value,
      occupiers: occupiers.value,
      documents: documents.value,
      status: status.value,
      queueNumber: queueNumber.value,
      selectedUnit: selectedUnit.value,
      lastSubmittedAt: lastSubmittedAt.value,
      linkedApplications: linkedApplications.value,
      linkedNric: linkedNric.value,
      currentApplicationId: currentApplicationId.value,
    }

    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(payload))
  }

  watch(
    [
      form,
      mainApplicantProfileLocked,
      coApplicants,
      occupiers,
      documents,
      status,
      queueNumber,
      selectedUnit,
      lastSubmittedAt,
      linkedApplications,
      linkedNric,
      currentApplicationId,
    ],
    persistState,
    { deep: true },
  )

  watch([form, coApplicants, occupiers], () => {
    applicationError.value = ''
  }, { deep: true })

  function clearLocalWorkflowState() {
    status.value = 'editing'
    queueNumber.value = null
    selectedUnit.value = null
    lastSubmittedAt.value = null
    availableUnitsState.value = []
  }

  function clearSubmissionCache() {
    applicationError.value = ''
  }

  function setLinkedApplications(nric: string, applications: ApplicationRecord[]) {
    linkedNric.value = normaliseNric(nric)
    linkedApplications.value = sortApplications(applications)

    if (
      currentApplicationId.value !== null &&
      !linkedApplications.value.some((application) => application.application_id === currentApplicationId.value)
    ) {
      currentApplicationId.value = null
    }
  }

  function replaceLinkedApplicationsForNric(nric: string, applications: ApplicationRecord[]) {
    setLinkedApplications(nric, applications)
  }

  function clearLinkedApplications() {
    linkedApplications.value = []
    linkedNric.value = null
    currentApplicationId.value = null
  }

  function syncSessionApplications(nric: string) {
    const formattedNric = normaliseNric(nric)
    if (!formattedNric) {
      clearLinkedApplications()
      return []
    }

    if (linkedNric.value && linkedNric.value !== formattedNric) {
      linkedApplications.value = []
      currentApplicationId.value = null
    }

    linkedNric.value = formattedNric

    if (
      currentApplicationId.value !== null &&
      !linkedApplications.value.some((application) => application.application_id === currentApplicationId.value)
    ) {
      currentApplicationId.value = null
    }

    return linkedApplications.value
  }

  async function ensureProjectCatalogLoaded(forceRefresh = false) {
    if (!forceRefresh && projectCatalog.value.length > 0) {
      return projectCatalog.value
    }

    if (isLoadingProjectCatalog.value) {
      return projectCatalog.value
    }

    isLoadingProjectCatalog.value = true
    try {
      const openProjectsResponse = await fetchProjects({ status: 'open' })
      if (openProjectsResponse.status === 200 && Array.isArray(openProjectsResponse.data.data)) {
        projectCatalog.value = openProjectsResponse.data.data
        return projectCatalog.value
      }

      return projectCatalog.value
    } finally {
      isLoadingProjectCatalog.value = false
    }
  }

  function resolvePreferredProject(town: string): ProjectRecord | null {
    const project = projectByTown.value.get(town)
    if (project) {
      return project
    }

    const fallbackProjectId = projectIdByTown[town]
    if (!fallbackProjectId) {
      return null
    }

    return {
      project_id: fallbackProjectId,
      exercise_id: 6,
      project_name: developmentByTown[town] ?? `${town} Project`,
      town_name: town,
      flat_types: '',
      status: 'open',
    }
  }

  function storeApplicationRecord(application: ApplicationRecord) {
    const formattedNric = normaliseNric(application.main_applicant_nric)

    if (linkedNric.value && linkedNric.value !== formattedNric) {
      linkedApplications.value = []
      currentApplicationId.value = null
    }

    setLinkedApplications(formattedNric, [
      ...linkedApplications.value.filter((existing) => existing.application_id !== application.application_id),
      application,
    ])
  }

  function beginNewApplication() {
    const preservedNric = normaliseNric(form.value.nric)
    const preservedName = form.value.fullName

    form.value = {
      ...createDefaultForm(),
      nric: preservedNric,
      fullName: preservedName,
    }
    mainApplicantProfileLocked.value = false
    coApplicants.value = []
    occupiers.value = []
    documents.value = createDefaultDocuments()
    documentFiles.value = createDefaultDocumentFiles()
    currentApplicationId.value = null
    clearSubmissionCache()
    clearLocalWorkflowState()
  }

  function startApplicationLogin(nric: string, name = '') {
    const formattedNric = normaliseNric(nric)

    form.value = {
      ...createDefaultForm(),
      nric: formattedNric,
      fullName: name || form.value.fullName,
    }
    mainApplicantProfileLocked.value = false
    coApplicants.value = []
    occupiers.value = []
    documents.value = createDefaultDocuments()
    documentFiles.value = createDefaultDocumentFiles()
    currentApplicationId.value = null
    clearSubmissionCache()
    clearLocalWorkflowState()
    syncSessionApplications(formattedNric)
  }

  function addHouseholdMember(role: HouseholdMemberRole) {
    if (role === 'CO_APPLICANT' && coApplicants.value.length >= 1) {
      return coApplicants.value[0]
    }

    const member = createHouseholdMember(role)

    if (role === 'CO_APPLICANT') {
      coApplicants.value = [...coApplicants.value, member]
    } else {
      occupiers.value = [...occupiers.value, member]
    }

    clearSubmissionCache()
    return member
  }

  function removeHouseholdMember(role: HouseholdMemberRole, memberId: string) {
    if (role === 'CO_APPLICANT') {
      coApplicants.value = coApplicants.value.filter((member) => member.id !== memberId)
    } else {
      occupiers.value = occupiers.value.filter((member) => member.id !== memberId)
    }

    clearSubmissionCache()
  }

  function fillMainApplicantFromMyInfo(persona: MyInfoPersona) {
    form.value.fullName = persona.name?.value ?? form.value.fullName
    form.value.nric = normaliseNric(form.value.nric || persona.uinfin?.value || '')
    form.value.dateOfBirth = persona.dob?.value ?? ''
    form.value.monthlyIncome = getMonthlyIncomeFromProfile(persona)
    form.value.contactNumber = persona.mobileno?.nbr?.value ?? ''
    form.value.email = persona.email?.value ?? ''
    form.value.maritalStatus = mapMaritalStatus(persona.marital?.code)
    form.value.citizenshipStatus = getCitizenshipStatusFromProfile(persona)
    mainApplicantProfileLocked.value = true
    clearSubmissionCache()
  }

  function fillHouseholdMemberFromMyInfo(memberId: string, persona: MyInfoPersona) {
    const applyProfile = (member: HouseholdMemberForm) => {
      member.fullName = persona.name?.value ?? member.fullName
      member.nric = normaliseNric(member.nric || persona.uinfin?.value || '')
      member.dateOfBirth = persona.dob?.value ?? ''
      member.monthlyIncome = getMonthlyIncomeFromProfile(persona)
      member.contactNumber = persona.mobileno?.nbr?.value ?? member.contactNumber
      member.email = persona.email?.value ?? member.email
      member.maritalStatus = mapMaritalStatus(persona.marital?.code)
      member.citizenshipStatus = getCitizenshipStatusFromProfile(persona)
      member.isRetrievedFromMyInfo = true
      clearSubmissionCache()
    }

    const coApplicant = coApplicants.value.find((member) => member.id === memberId)
    if (coApplicant) {
      applyProfile(coApplicant)
      return
    }

    const occupier = occupiers.value.find((member) => member.id === memberId)
    if (occupier) {
      applyProfile(occupier)
    }
  }

  function buildApplicationMembersPayload(): ApplicationMemberRequest[] {
    return [
      {
        member_role: 'MAIN_APPLICANT',
        nric_fin: normaliseNric(form.value.nric),
        full_name: form.value.fullName.trim(),
        relationship_to_main: 'Self',
        date_of_birth: form.value.dateOfBirth,
        citizenship_status: form.value.citizenshipStatus,
        marital_status: form.value.maritalStatus || null,
        contact_number: form.value.contactNumber.trim(),
        email: form.value.email.trim(),
        income_amount: parseIncomeAmount(form.value.monthlyIncome),
      },
      ...coApplicants.value.map((member) => ({
        member_role: 'CO_APPLICANT' as const,
        nric_fin: normaliseNric(member.nric),
        full_name: member.fullName.trim(),
        relationship_to_main: member.relationshipToMain,
        date_of_birth: member.dateOfBirth,
        citizenship_status: member.citizenshipStatus,
        marital_status: member.maritalStatus || null,
        contact_number: member.contactNumber.trim(),
        email: member.email.trim(),
        income_amount: parseIncomeAmount(member.monthlyIncome),
      })),
      ...occupiers.value.map((member) => ({
        member_role: 'OCCUPANT' as const,
        nric_fin: normaliseNric(member.nric),
        full_name: member.fullName.trim(),
        relationship_to_main: member.relationshipToMain,
        date_of_birth: member.dateOfBirth,
        citizenship_status: member.citizenshipStatus,
        marital_status: member.maritalStatus || null,
        contact_number: member.contactNumber.trim(),
        email: member.email.trim(),
        income_amount: parseIncomeAmount(member.monthlyIncome),
      })),
    ]
  }

  async function buildApplyBtoApplicationPayload(): Promise<ApplyBtoApplicationPayload | null> {
    await ensureProjectCatalogLoaded()

    const resolvedProject = resolvePreferredProject(form.value.preferredTown)
    if (!resolvedProject) {
      return null
    }

    return {
      main_applicant_nric: normaliseNric(form.value.nric),
      exercise_id: resolvedProject.exercise_id,
      project_id: resolvedProject.project_id,
      flat_type: form.value.flatType,
      members: buildApplicationMembersPayload(),
    }
  }

  async function getApplyBtoInitiationPayload() {
    applicationError.value = ''

    if (isCurrentSubmitted.value) {
      applicationError.value = 'This application has already been submitted.'
      return null
    }

    if (firstSubmitted.value) {
      applicationError.value =
        'You already have a submitted application on file. Please review that application instead.'
      return null
    }

    if (!validateApplicationDetails()) {
      return null
    }

    const incomeDocument = documentFiles.value.incomePdfFile
    const hfeDocument = documentFiles.value.hfeLetterPdfFile

    if (!incomeDocument || !hfeDocument) {
      applicationError.value = 'Please attach both PDFs again before continuing to payment.'
      return null
    }

    const applicationPayload = await buildApplyBtoApplicationPayload()
    if (!applicationPayload) {
      applicationError.value = 'Unable to resolve project and exercise for the selected town right now.'
      return null
    }

    return {
      application: applicationPayload,
      incomeDocument,
      hfeDocument,
    }
  }

  function getMemberLabel(role: HouseholdMemberRole, index: number) {
    return role === 'CO_APPLICANT' ? `Co-applicant ${index + 1}` : `Occupier ${index + 1}`
  }

  function validateHouseholdMembers(): string[] {
    const errors: string[] = []
    const seenNrics = new Set<string>()

    const mainApplicantNric = normaliseNric(form.value.nric)
    if (mainApplicantNric) {
      seenNrics.add(mainApplicantNric)
    }

    const validateMemberCollection = (members: HouseholdMemberForm[], role: HouseholdMemberRole) => {
      members.forEach((member, index) => {
        const label = getMemberLabel(role, index)

        if (!hasText(member.fullName)) {
          errors.push(`${label}: full name is required.`)
        }

        if (!hasText(member.nric)) {
          errors.push(`${label}: NRIC / FIN is required.`)
        } else {
          const memberNric = normaliseNric(member.nric)
          if (seenNrics.has(memberNric)) {
            errors.push(`${label}: NRIC / FIN must be unique within the application.`)
          } else {
            seenNrics.add(memberNric)
          }
        }

        if (!hasText(member.dateOfBirth)) {
          errors.push(`${label}: date of birth is required.`)
        }

        if (!hasText(member.monthlyIncome)) {
          errors.push(`${label}: monthly income is required.`)
        } else if (parseIncomeAmount(member.monthlyIncome) === null) {
          errors.push(`${label}: monthly income must be a valid non-negative number.`)
        }

        if (!hasText(member.relationshipToMain)) {
          errors.push(`${label}: relationship to main applicant is required.`)
        }

        if (!hasText(member.citizenshipStatus)) {
          errors.push(`${label}: citizenship / residency status is required.`)
        }

        if (!hasText(member.maritalStatus)) {
          errors.push(`${label}: marital status is required.`)
        }

        if (!hasText(member.contactNumber)) {
          errors.push(`${label}: contact number is required.`)
        }

        if (!hasText(member.email)) {
          errors.push(`${label}: email is required.`)
        } else if (!isValidEmail(member.email)) {
          errors.push(`${label}: email must be a valid email address.`)
        }
      })
    }

    validateMemberCollection(coApplicants.value, 'CO_APPLICANT')
    validateMemberCollection(occupiers.value, 'OCCUPANT')

    return errors
  }

  function getSubmissionValidationErrors(): string[] {
    const errors: string[] = []

    if (coApplicants.value.length > 1) {
      errors.push('Only one co-applicant can be added to this application.')
    }

    for (const fieldName of REQUIRED_SUBMISSION_FIELDS) {
      if (!hasText(form.value[fieldName])) {
        errors.push(`${fieldLabels[fieldName]} is required before submission.`)
      }
    }

    if (hasText(form.value.email) && !isValidEmail(form.value.email)) {
      errors.push('Enter a valid email address before submission.')
    }

    if (hasText(form.value.monthlyIncome) && parseIncomeAmount(form.value.monthlyIncome) === null) {
      errors.push('Main applicant monthly income must be a valid non-negative number.')
    }

    errors.push(...validateHouseholdMembers())

    if (!hasRequiredDocuments.value) {
      errors.push('Both the income PDF and HFE letter PDF must be selected before submission.')
    }

    if (
      hasText(documents.value.incomePdfName) &&
      !isPdfSelection(documentFiles.value.incomePdfFile, documents.value.incomePdfName)
    ) {
      errors.push('Income document must be uploaded as a PDF file.')
    }

    if (
      hasText(documents.value.hfeLetterPdfName) &&
      !isPdfSelection(documentFiles.value.hfeLetterPdfFile, documents.value.hfeLetterPdfName)
    ) {
      errors.push('HFE letter must be uploaded as a PDF file.')
    }

    if (!documentFiles.value.incomePdfFile || !documentFiles.value.hfeLetterPdfFile) {
      errors.push('Please attach both PDFs before submission.')
    }

    return errors
  }

  function validateApplicationDetails() {
    applicationError.value = ''

    const validationErrors = getSubmissionValidationErrors()
    if (validationErrors.length > 0) {
      applicationError.value = validationErrors[0] ?? 'Please complete all required fields before submission.'
      return false
    }

    return true
  }

  function openApplication(application: ApplicationRecord) {
    storeApplicationRecord(application)

    const openingCurrentApplication = currentApplicationId.value === application.application_id

    currentApplicationId.value = application.application_id
    if (!openingCurrentApplication) {
      clearLocalWorkflowState()
      if (application.application_status === 'SUCCESSFUL') {
        status.value = 'successful'
      } else if (application.application_status === 'SUBMITTED') {
        status.value = 'processing'
      } else {
        status.value = 'editing'
      }
    }

    lastSubmittedAt.value = application.submitted_at

    const mainApplicantMember =
      application.members.find((member) => member.member_role === 'MAIN_APPLICANT') ?? application.members[0]

    form.value = {
      ...createDefaultForm(),
      fullName: mainApplicantMember?.full_name ?? '',
      nric: application.main_applicant_nric,
      dateOfBirth: mainApplicantMember?.date_of_birth ?? '',
      monthlyIncome: mainApplicantMember?.income_amount !== null && mainApplicantMember?.income_amount !== undefined
        ? String(mainApplicantMember.income_amount)
        : '',
      contactNumber: mainApplicantMember?.contact_number ?? '',
      email: mainApplicantMember?.email ?? '',
      maritalStatus: mainApplicantMember?.marital_status ?? '',
      citizenshipStatus: mainApplicantMember?.citizenship_status ?? '',
      preferredTown:
        projectCatalog.value.find((project) => project.project_id === application.project_id)?.town_name
        ?? townByProjectId[application.project_id]
        ?? '',
      flatType: application.flat_type,
    }
    mainApplicantProfileLocked.value = false
    // Fetch real queue number from flat-selection service
    if (application.main_applicant_nric) {
      void fetchFlatSelections({ applicant_nric: application.main_applicant_nric })
        .then(({ status: respStatus, data }) => {
          if (respStatus === 200 && Array.isArray(data.data) && data.data.length > 0) {
            const record = data.data.find((r) => r.application_id === application.application_id) ?? data.data[0]
            if (record) {
              queueNumber.value = `Q${record.queue_number}`
              // Mark as balloted so the "Book This Unit" button becomes clickable
              if (status.value !== 'selected') {
                status.value = 'balloted'
              }
            }
          }
        })
        .catch(() => { /* ignore */ })
    }

    coApplicants.value = application.members
      .filter((member) => member.member_role === 'CO_APPLICANT')
      .map(mapApplicationMemberToForm)
    occupiers.value = application.members
      .filter((member) => member.member_role === 'OCCUPANT')
      .map(mapApplicationMemberToForm)

    documents.value = {
      incomePdfName: buildDocumentLabel(application.income_document_id, 'Income document'),
      hfeLetterPdfName: buildDocumentLabel(application.hfe_document_id, 'HFE letter'),
    }

    documentFiles.value = createDefaultDocumentFiles()
    clearSubmissionCache()
  }

  function resetFormProgress() {
    beginNewApplication()
  }

  function markBalloted() {
    status.value = 'balloted'
    queueNumber.value = buildQueueNumber(form.value.nric)
  }

  async function reserveUnit(unit: AvailableUnit) {
  await fetch(`http://localhost:5006/flats/${unit.id}/reserve`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ applicant_id: form.value.nric }),
  })

  selectedUnit.value = unit
  status.value = 'selected'
  }

  function removeUnit(flatId: number) {
  availableUnitsState.value = availableUnitsState.value.filter((u) => u.id !== flatId)
  }

  async function loadAvailableUnits() {
    console.log('[loadAvailableUnits] called', {
      preferredTown: form.value.preferredTown,
      currentApplicationId: currentApplicationId.value,
      linkedAppsCount: linkedApplications.value.length,
    })
    void ensureProjectCatalogLoaded()
    

    // Fallback: if preferredTown is empty (e.g. user navigated directly to
    // /select-flat from an existing application), derive it from the currently
    // linked application so we can still query flats by project_id.
    let preferredTown = form.value.preferredTown
    let fallbackProjectId: number | undefined
    let fallbackFlatType: string | undefined

    if (!hasText(preferredTown) && currentApplicationId.value !== null) {
      const activeApp = linkedApplications.value.find(
        (app) => app.application_id === currentApplicationId.value,
      )
      if (activeApp) {
        fallbackProjectId = activeApp.project_id
        fallbackFlatType = activeApp.flat_type
        preferredTown =
          projectCatalog.value.find((p) => p.project_id === activeApp.project_id)?.town_name
          ?? ''
      }
    }

    if (!hasText(preferredTown) && fallbackProjectId === undefined) {
      availableUnitsState.value = []
      return
    }

    const params: { town?: string; flat_type?: string; project_id?: number } = {}

    if (hasText(preferredTown)) {
      params.town = preferredTown
      const resolvedProject = resolvePreferredProject(preferredTown)
      if (resolvedProject) {
        params.project_id = resolvedProject.project_id
      }
    }

    if (fallbackProjectId !== undefined) {
      params.project_id = fallbackProjectId
    }

    const flatType = hasText(form.value.flatType) ? form.value.flatType : (fallbackFlatType ?? '')
    if (hasText(flatType)) {
      params.flat_type = flatType
    }

    isLoadingAvailableUnits.value = true
    try {
      const { status: httpStatus, data } = await fetchAvailableFlats(params)
      if (httpStatus === 200 && Array.isArray(data.data)) {
        availableUnitsState.value = data.data.map((row) => mapFlatServiceRowToUnit(row))
        return
      }

      availableUnitsState.value = []
    } catch {
      availableUnitsState.value = []
    } finally {
      isLoadingAvailableUnits.value = false
    }
  }

  function setDocument(documentKey: 'incomePdfName' | 'hfeLetterPdfName', file: File | null) {
    const fileName = file?.name ?? ''
    documents.value = {
      ...documents.value,
      [documentKey]: fileName,
    }

    documentFiles.value = {
      ...documentFiles.value,
      ...(documentKey === 'incomePdfName'
        ? { incomePdfFile: file }
        : { hfeLetterPdfFile: file }),
    }

    clearSubmissionCache()
  }

  function resetApplication() {
    form.value = createDefaultForm()
    mainApplicantProfileLocked.value = false
    coApplicants.value = []
    occupiers.value = []
    documents.value = createDefaultDocuments()
    documentFiles.value = createDefaultDocumentFiles()
    clearSubmissionCache()
    clearLocalWorkflowState()
    clearLinkedApplications()

    if (typeof window !== 'undefined') {
      window.localStorage.removeItem(STORAGE_KEY)
    }
  }

  return {
    townOptions,
    projectByTown,
    form,
    mainApplicantProfileLocked,
    coApplicants,
    occupiers,
    householdMembers,
    householdMemberCount,
    documents,
    status,
    queueNumber,
    selectedUnit,
    lastSubmittedAt,
    linkedApplications,
    linkedNric,
    currentApplicationId,
    currentApplication,
    firstSubmitted,
    submittedApplications,
    applicationError,
    latestApplication,
    hasExistingApplications,
    hasSubmittedApplication,
    isCurrentSubmitted,
    availableUnits,
    isLoadingAvailableUnits,
    developmentName,
    hasBallotAccess,
    hasRequiredDocuments,
    isLoadingProjectCatalog,
    ensureProjectCatalogLoaded,
    syncSessionApplications,
    replaceLinkedApplicationsForNric,
    storeApplicationRecord,
    clearLinkedApplications,
    beginNewApplication,
    startApplicationLogin,
    addHouseholdMember,
    removeHouseholdMember,
    fillMainApplicantFromMyInfo,
    fillHouseholdMemberFromMyInfo,
    validateApplicationDetails,
    getApplyBtoInitiationPayload,
    openApplication,
    resetFormProgress,
    markBalloted,
    reserveUnit,
    loadAvailableUnits,
    setDocument,
    resetApplication,
    removeUnit,
  }
})

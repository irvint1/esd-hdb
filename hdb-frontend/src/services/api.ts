import axios from 'axios'

export const APPLY_BTO_URL = import.meta.env.VITE_APPLY_BTO_URL ?? 'http://localhost:5010'
export const PROCESS_BALLOT_URL = import.meta.env.VITE_PROCESS_BALLOT_URL ?? 'http://localhost:5011'
export const PROJECT_URL = import.meta.env.VITE_PROJECT_URL ?? 'http://localhost:5012'
export const BALLOT_AUDIT_URL = import.meta.env.VITE_BALLOT_AUDIT_URL ?? 'http://localhost:5000'
export const FLAT_SELECTION_URL = import.meta.env.VITE_FLAT_SELECTION_URL ?? 'http://localhost:5002'
export const APPLICATION_URL = import.meta.env.VITE_APPLICATION_URL ?? 'http://localhost:5004'
export const FLAT_URL = import.meta.env.VITE_FLAT_URL ?? 'http://localhost:5006'

type ApiMessage = string | string[]

export interface ApiEnvelope<T> {
  code: number
  data?: T
  message?: ApiMessage
  error?: string
  details?: string[]
}

export interface BallotAuditRecord {
  audit_id: number
  exercise_id: number
  run_at: string
  executed_at: string | null
  cron_expression: string | null
  next_run_at: string | null
  error_reason: string | null
  status: 'scheduled' | 'in progress' | 'completed' | 'error' | 'cancelled'
}

export interface BallotQueueEntry {
  application_id: number | null
  main_applicant_nric: string | null
  co_applicant_nric: string | null
  flat_type: string | null
  final_chance: number
  ticket_weight: number
  queue_number: number
  queue_result: 'queued'
  flat_selection: {
    created: boolean
    selection_id: number | null
    message: string
  }
}

export interface BallotProjectResult {
  project_id: number
  project_name: string
  town_name: string
  submitted_count: number
  queue_assigned_count: number
  queue_start: number
  queue_end: number
  flat_selection_entries_created: number
  entries: BallotQueueEntry[]
}

export interface ProcessBallotRunResult {
  run_id: string
  exercise_id: number
  audit_id: number | null
  audit_status: string
  trigger_source: string
  started_at: string
  completed_at: string
  projects: BallotProjectResult[]
  totals: {
    submitted_count: number
    queue_assigned_count: number
    projects_processed: number
    flat_selection_entries_created: number
    validated_count: number
    ineligible_count: number
    eligible_after_validation_count: number
  }
  validation: {
    validated_applications: unknown[]
    ineligible_applications: unknown[]
  }
  warnings: string[]
}

export interface ProcessBallotRunRequest {
  exercise_id: number
  audit_id?: number
  skip_audit?: boolean
  trigger_source?: string
}

export interface ProcessBallotRunResponse extends ApiEnvelope<ProcessBallotRunResult> {
  errors?: string[]
}

export interface ProjectRecord {
  project_id: number
  exercise_id: number
  project_name: string
  town_name: string
  flat_types: string
  status: 'open' | 'closed'
}

export interface FlatSelectionRecord {
  selection_id: number
  application_id: number
  applicant_nric: string
  co_applicant_nric: string | null
  project_id: number
  queue_number: number
  flat_id: number | null
  status: 'balloted' | 'selecting' | 'reserved' | 'paid' | 'forfeited' | 'not_called' | 'no_flat_selected'
  reserved_at: string | null
  created_at: string | null
  updated_at: string | null
}

export interface FlatServiceRecord {
  flat_id: number
  block: string
  street_name: string
  floor_number: number
  unit_number: string
  flat_type: string
  area_sqm: number
  price: number
  status: string
  project_name: string
  town: string
}

export type ServiceApplicationStatus = 'SUBMITTED' | 'SUCCESSFUL' | 'UNSUCCESSFUL' | 'CANCELLED'

export interface ApplicationMemberRecord {
  member_id: number
  member_role: 'MAIN_APPLICANT' | 'CO_APPLICANT' | 'OCCUPANT'
  nric_fin: string
  full_name: string
  relationship_to_main: string
  date_of_birth: string | null
  citizenship_status: string
  marital_status: string | null
  contact_number: string | null
  email: string | null
  income_amount: number | null
  created_at: string | null
  updated_at: string | null
}

export interface ApplicationMemberRequest {
  member_role: 'MAIN_APPLICANT' | 'CO_APPLICANT' | 'OCCUPANT'
  nric_fin: string
  full_name: string
  relationship_to_main: string
  date_of_birth: string
  citizenship_status: string
  marital_status?: string | null
  contact_number: string
  email: string
  income_amount?: number | null
}

export interface ApplicationRecord {
  application_id: number
  exercise_id: number
  project_id: number
  flat_type: string
  main_applicant_nric: string
  income_document_id: number | null
  hfe_document_id: number | null
  application_status: ServiceApplicationStatus
  submitted_at: string | null
  created_at: string | null
  updated_at: string | null
  members: ApplicationMemberRecord[]
}

export interface ApplyBtoApplicationPayload {
  exercise_id: number
  project_id: number
  flat_type: string
  main_applicant_nric: string
  members: ApplicationMemberRequest[]
}

export interface ApplyBtoInitiateRequest {
  application: ApplyBtoApplicationPayload
  income_document: File
  hfe_document: File
}

export interface ApplyBtoPaymentRequestPayload {
  gateway_url: string
  payload: string
  hmac: string
  api_key_id: string
  merchant_txn_ref: string
}

export interface ApplyBtoCompletionResult {
  merchant_txn_ref: string
  stage: string
  payment_status: string
  application_status?: ServiceApplicationStatus
  eligible?: boolean
  summary?: string
  ineligibility_reasons?: string[]
  message?: string
}


const applyBtoApi = axios.create({
  baseURL: APPLY_BTO_URL,
  timeout: 30000,
})

const processBallotApi = axios.create({
  baseURL: PROCESS_BALLOT_URL,
  timeout: 30000,
})

const projectApi = axios.create({
  baseURL: PROJECT_URL,
  timeout: 30000,
})

const ballotAuditApi = axios.create({
  baseURL: BALLOT_AUDIT_URL,
  timeout: 30000,
})

const flatSelectionApi = axios.create({
  baseURL: FLAT_SELECTION_URL,
  timeout: 30000,
})

const applicationApi = axios.create({
  baseURL: APPLICATION_URL,
  timeout: 30000,
})

const flatApi = axios.create({
  baseURL: FLAT_URL,
  timeout: 30000,
})

function normaliseMessage(message: ApiMessage | undefined, fallback: string): string {
  if (Array.isArray(message)) {
    return message.join(' ')
  }

  if (typeof message === 'string' && message.trim().length > 0) {
    return message
  }

  return fallback
}

function normaliseErrorPayload(payload: Partial<ApiEnvelope<unknown>> | undefined, fallback: string): string {
  if (!payload) {
    return fallback
  }

  if (typeof payload.error === 'string' && payload.error.trim().length > 0) {
    return payload.error
  }

  if (Array.isArray(payload.details) && payload.details.length > 0) {
    return payload.details.join(' ')
  }

  return normaliseMessage(payload.message, fallback)
}

export function getErrorMessage(error: unknown, fallback = 'Unable to complete your request.'): string {
  if (axios.isAxiosError<ApiEnvelope<unknown>>(error)) {
    return normaliseErrorPayload(error.response?.data, fallback)
  }

  if (error instanceof Error && error.message.trim().length > 0) {
    return error.message
  }

  return fallback
}

export async function initiateApplyBtoSubmission(
  payload: ApplyBtoInitiateRequest,
): Promise<ApplyBtoCompletionResult & { payment: ApplyBtoPaymentRequestPayload }> {
  const formData = new FormData()
  formData.append('application', JSON.stringify(payload.application))
  formData.append('income_document', payload.income_document)
  formData.append('hfe_document', payload.hfe_document)

  const response = await applyBtoApi.post<ApplyBtoCompletionResult & { payment: ApplyBtoPaymentRequestPayload }>(
    '/apply-bto/initiate',
    formData,
  )

  return response.data
}

export async function completeApplyBtoSubmission(
  merchantTxnRef: string,
): Promise<{ status: number; data: ApplyBtoCompletionResult }> {
  const response = await applyBtoApi.post<ApplyBtoCompletionResult>(
    `/apply-bto/complete/${encodeURIComponent(merchantTxnRef)}`,
    undefined,
    {
      validateStatus: () => true,
    },
  )

  return {
    status: response.status,
    data: response.data,
  }
}

export async function runProcessBallot(
  payload: ProcessBallotRunRequest,
): Promise<{ status: number; data: ProcessBallotRunResponse }> {
  const response = await processBallotApi.post<ProcessBallotRunResponse>('/process-ballot/run', payload, {
    validateStatus: () => true,
  })

  return {
    status: response.status,
    data: response.data,
  }
}

export async function fetchBallotAudits(): Promise<{ status: number; data: ApiEnvelope<BallotAuditRecord[]> }> {
  const response = await ballotAuditApi.get<ApiEnvelope<BallotAuditRecord[]>>('/ballot-audits', {
    validateStatus: () => true,
  })

  return {
    status: response.status,
    data: response.data,
  }
}

export async function fetchProjects(
  params?: { exercise_id?: number; status?: ProjectRecord['status'] },
): Promise<{ status: number; data: ApiEnvelope<ProjectRecord[]> }> {
  const response = await projectApi.get<ApiEnvelope<ProjectRecord[]>>('/projects', {
    validateStatus: () => true,
    params,
  })

  return {
    status: response.status,
    data: response.data,
  }
}

export async function createBallotAudit(
  payload: {
    exercise_id: number
    run_at?: string
    status?: 'scheduled' | 'in progress' | 'completed' | 'error' | 'cancelled'
    cron_expression?: string | null
    executed_at?: string | null
    error_reason?: string | null
  },
): Promise<{ status: number; data: ApiEnvelope<BallotAuditRecord> }> {
  const response = await ballotAuditApi.post<ApiEnvelope<BallotAuditRecord>>('/ballot-audits', payload, {
    validateStatus: () => true,
  })

  return {
    status: response.status,
    data: response.data,
  }
}

export async function updateBallotAudit(
  auditId: number,
  payload: {
    status?: 'scheduled' | 'in progress' | 'completed' | 'error' | 'cancelled'
    run_at?: string | null
    executed_at?: string | null
    cron_expression?: string | null
    error_reason?: string | null
  },
): Promise<{ status: number; data: ApiEnvelope<BallotAuditRecord> }> {
  const response = await ballotAuditApi.put<ApiEnvelope<BallotAuditRecord>>(
    `/ballot-audits/${encodeURIComponent(String(auditId))}`,
    payload,
    {
      validateStatus: () => true,
    },
  )

  return {
    status: response.status,
    data: response.data,
  }
}

export async function fetchScheduledBallotAudits(): Promise<{ status: number; data: ApiEnvelope<BallotAuditRecord[]> }> {
  const response = await ballotAuditApi.get<ApiEnvelope<BallotAuditRecord[]>>('/ballot-audits', {
    validateStatus: () => true,
    params: { status: 'scheduled' },
  })

  return {
    status: response.status,
    data: response.data,
  }
}

export async function fetchFlatSelections(
  params?: { status?: FlatSelectionRecord['status']; project_id?: number; applicant_nric?: string },
): Promise<{ status: number; data: ApiEnvelope<FlatSelectionRecord[]> }> {
  const response = await flatSelectionApi.get<ApiEnvelope<FlatSelectionRecord[]>>('/flat-selection', {
    validateStatus: () => true,
    params,
  })

  return {
    status: response.status,
    data: response.data,
  }
}

export async function fetchApplications(
  params?: {
    nric?: string
    main_applicant_nric?: string
    exercise_id?: number
    project_id?: number
    application_status?: ServiceApplicationStatus
  },
): Promise<{ status: number; data: { applications: ApplicationRecord[] } }> {
  const response = await applicationApi.get<{ applications?: ApplicationRecord[] }>('/applications', {
    validateStatus: () => true,
    params,
  })

  return {
    status: response.status,
    data: {
      applications: Array.isArray(response.data?.applications) ? response.data.applications : [],
    },
  }
}

export async function fetchAvailableFlats(
  params?: { town?: string; flat_type?: string; project_id?: number },
): Promise<{ status: number; data: ApiEnvelope<FlatServiceRecord[]> }> {
  const response = await flatApi.get<ApiEnvelope<FlatServiceRecord[]>>('/flats', {
    validateStatus: () => true,
    params,
  })

  return {
    status: response.status,
    data: response.data,
  }
}

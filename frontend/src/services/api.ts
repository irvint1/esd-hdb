import axios from 'axios'

const API_GATEWAY_URL = import.meta.env.VITE_API_GATEWAY_URL ?? 'http://localhost:8000'

export const APPLY_BTO_URL = import.meta.env.VITE_APPLY_BTO_URL ?? API_GATEWAY_URL
export const PROCESS_BALLOT_URL = import.meta.env.VITE_PROCESS_BALLOT_URL ?? API_GATEWAY_URL
export const PROJECT_URL = import.meta.env.VITE_PROJECT_URL ?? API_GATEWAY_URL
export const BALLOT_AUDIT_URL = import.meta.env.VITE_BALLOT_AUDIT_URL ?? API_GATEWAY_URL
export const FLAT_SELECTION_URL = import.meta.env.VITE_FLAT_SELECTION_URL ?? API_GATEWAY_URL
export const APPLICATION_URL = import.meta.env.VITE_APPLICATION_URL ?? API_GATEWAY_URL
export const FLAT_URL = import.meta.env.VITE_FLAT_URL ?? API_GATEWAY_URL
export const NETS_PAYMENT_URL = import.meta.env.VITE_NETS_PAYMENT_URL ?? API_GATEWAY_URL
export const DOCUMENT_URL = import.meta.env.VITE_DOCUMENT_URL ?? API_GATEWAY_URL
export const FLAT_ALLOCATION_URL = import.meta.env.VITE_FLAT_ALLOCATION_URL ?? API_GATEWAY_URL
const PROCESS_BALLOT_API_KEY = import.meta.env.VITE_PROCESS_BALLOT_API_KEY ?? 'ballot-cron-job-secret'

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
  status: 'balloted' | 'selecting' | 'reserved' | 'paid' | 'selected' | 'forfeited' | 'not_called' | 'no_flat_selected'
  reserved_at: string | null
  created_at: string | null
  updated_at: string | null
}

export interface FlatAllocationSelectRequest {
  applicant_id: string
  selection_id: number
  flat_id: number
  payment_amount: number
}

export interface FlatAllocationSelectResponse {
  merchant_txn_ref: string
  stage?: string
  gateway_url?: string
  payload?: string
  hmac?: string
  api_key_id?: string
  payment?: {
    gateway_url?: string
    payload?: string
    hmac?: string
    api_key_id?: string
  }
  message?: string
}

export interface FlatAllocationCompleteResponse {
  merchant_txn_ref: string
  stage?: string
  payment_status?: 'success' | 'failed' | 'cancelled' | 'pending' | 'unknown'
  transaction_id?: string | null
  applicant_id?: string | number
  selection_id?: number
  flat_id?: number
  payment_amount?: number
  message?: string
}

export interface NetsPaymentStatusResult {
  merchant_txn_ref: string
  status: 'success' | 'failed' | 'cancelled' | 'pending' | 'unknown'
  transaction_id?: string | null
  message?: string
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
  formatted_ineligibility_reasons?: string
  message?: string
}

export interface DocumentRecord {
  document_id: number
  application_id: number
  document_type: 'income' | 'hfe' | string
  storage_path: string
  status: string
  fields: Record<string, unknown> | null
  uploaded_at: string | null
}

export interface DocumentExtractResult {
  document_id: number
  application_id: number
  document_type: 'income' | 'hfe' | string
  status: string
  fields: Record<string, unknown>
}


const applyBtoApi = axios.create({
  baseURL: APPLY_BTO_URL,
  timeout: 30000,
})

const processBallotApi = axios.create({
  baseURL: PROCESS_BALLOT_URL,
  timeout: 120000,
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

const documentApi = axios.create({
  baseURL: DOCUMENT_URL,
  timeout: 60000,
})

const flatAllocationApi = axios.create({
  baseURL: FLAT_ALLOCATION_URL,
  timeout: 30000,
})

const netsPaymentApi = axios.create({
  baseURL: NETS_PAYMENT_URL,
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
  try {
    const response = await applyBtoApi.post<ApplyBtoCompletionResult>(
      `/apply-bto/complete/${encodeURIComponent(merchantTxnRef)}`
    );
    return {
      status: response.status,
      data: response.data,
    };
  } catch (error: any) {
    if (error.response) {
      // Backend returned an error status code (e.g., 404, 402, 502)
      return {
        status: error.response.status,
        data: error.response.data,
      };
    }
    throw error;
  }
}

export async function demoForceApplyBtoSuccess(
  merchantTxnRef: string,
): Promise<{ status: number; data: ApplyBtoCompletionResult }> {
  const response = await applyBtoApi.post<ApplyBtoCompletionResult>(
    `/apply-bto/demo-force-success/${encodeURIComponent(merchantTxnRef)}`,
    undefined,
    {
      headers: {
        apikey: PROCESS_BALLOT_API_KEY,
      },
      validateStatus: () => true,
    },
  )

  return {
    status: response.status,
    data: response.data,
  }
}

export async function abandonNetsPayment(
  merchantTxnRef: string,
): Promise<{ status: number; data: ApiEnvelope<{ merchant_txn_ref: string; status: string; message: string }> }> {
  const response = await netsPaymentApi.post<ApiEnvelope<{ merchant_txn_ref: string; status: string; message: string }>>(
    `/payment/abandon/${encodeURIComponent(merchantTxnRef)}`,
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
  const response = await processBallotApi.post<ProcessBallotRunResponse>(
    '/process-ballot/run',
    payload,
    {
      headers: {
        apikey: PROCESS_BALLOT_API_KEY,
      },
      validateStatus: () => true,
    },
  )

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

export async function selectFlatAllocation(
  payload: FlatAllocationSelectRequest,
): Promise<{ status: number; data: ApiEnvelope<FlatAllocationSelectResponse> }> {
  const response = await flatAllocationApi.post<ApiEnvelope<FlatAllocationSelectResponse> | FlatAllocationSelectResponse>(
    '/select-flat',
    payload,
    {
      validateStatus: () => true,
    },
  )

  const responseData = response.data as ApiEnvelope<FlatAllocationSelectResponse>
  const directPayload = response.data as FlatAllocationSelectResponse
  const isEnvelope = typeof responseData?.code === 'number'

  return {
    status: response.status,
    data: isEnvelope
      ? responseData
      : {
          code: response.status,
          data: directPayload,
        },
  }
}

export async function completeFlatAllocation(
  merchantTxnRef: string,
): Promise<{ status: number; data: ApiEnvelope<FlatAllocationCompleteResponse> }> {
  const response = await flatAllocationApi.post<ApiEnvelope<FlatAllocationCompleteResponse> | FlatAllocationCompleteResponse>(
    `/select-flat/complete/${encodeURIComponent(merchantTxnRef)}`,
    undefined,
    {
      validateStatus: () => true,
    },
  )

  const responseData = response.data as ApiEnvelope<FlatAllocationCompleteResponse>
  const directPayload = response.data as FlatAllocationCompleteResponse
  const isEnvelope = typeof responseData?.code === 'number'

  return {
    status: response.status,
    data: isEnvelope
      ? responseData
      : {
          code: response.status,
          data: directPayload,
        },
  }
}

export async function fetchNetsPaymentStatus(
  merchantTxnRef: string,
): Promise<{ status: number; data: ApiEnvelope<NetsPaymentStatusResult> }> {
  const response = await netsPaymentApi.get<ApiEnvelope<NetsPaymentStatusResult>>(
    `/payment/status/${encodeURIComponent(merchantTxnRef)}`,
    {
      validateStatus: () => true,
    },
  )

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

export async function fetchFlatById(
  flatId: number,
): Promise<{ status: number; data: ApiEnvelope<FlatServiceRecord> }> {
  const response = await flatApi.get<ApiEnvelope<FlatServiceRecord>>(
    `/flats/${encodeURIComponent(String(flatId))}`,
    {
      validateStatus: () => true,
    },
  )

  return {
    status: response.status,
    data: response.data,
  }
}

export async function extractDocument(
  payload: { application_id: number; file: File },
): Promise<{ status: number; data: DocumentExtractResult | { error: string } }> {
  const formData = new FormData()
  formData.append('application_id', String(payload.application_id))
  formData.append('file', payload.file)

  const response = await documentApi.post<DocumentExtractResult | { error: string }>(
    '/extract',
    formData,
    {
      validateStatus: () => true,
    },
  )

  return {
    status: response.status,
    data: response.data,
  }
}

export async function fetchDocuments(
  params?: { application_id?: number },
): Promise<{ status: number; data: { documents: DocumentRecord[] } | { error: string } }> {
  const response = await documentApi.get<{ documents?: DocumentRecord[] } | { error: string }>(
    '/documents',
    {
      validateStatus: () => true,
      params,
    },
  )

  if ('documents' in response.data && Array.isArray(response.data.documents)) {
    return {
      status: response.status,
      data: { documents: response.data.documents },
    }
  }

  return {
    status: response.status,
    data: (response.data as { error: string }) ?? { error: 'Unable to load documents.' },
  }
}

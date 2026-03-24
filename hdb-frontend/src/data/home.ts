export type JourneySlide = {
  id: string
  stage: string
  title: string
  summary: string
  bullets: string[]
  metric: string
  metricLabel: string
}

export type LaunchItem = {
  id: string
  month: string
  town: string
  project: string
  summary: string
  window: string
  flatTypes: string[]
  status: string
}

export type ProcessStep = {
  id: string
  label: string
  title: string
  detail: string
}

export type DemoUser = {
  nric: string
  password: string
  name: string
  age: number
  household: string
  status: string
  preferredTown: string
}

export const journeySlides: JourneySlide[] = [
  {
    id: 'discover',
    stage: 'Scenario 1',
    title: 'Review launches with clarity before you apply.',
    summary:
      'A calmer launch overview helps households compare towns, flat types, and application windows without the clutter of a typical promo page.',
    bullets: [
      'View launch timing and current application milestone',
      'Compare flat mix in one concise panel',
      'Understand what to prepare before submitting',
    ],
    metric: '3 launch clusters',
    metricLabel: 'highlighted in the current planning cycle',
  },
  {
    id: 'ballot',
    stage: 'Scenario 2',
    title: 'Make the ballot stage feel easier to understand.',
    summary:
      'The experience reframes the ballot journey into simple, readable status updates so applicants know what the next meaningful step is.',
    bullets: [
      'Explain ballot status without heavy system language',
      'Clarify queue relevance for later selection',
      'Keep key applicant information close at hand',
    ],
    metric: '1 guided path',
    metricLabel: 'from application to ballot awareness',
  },
  {
    id: 'select',
    stage: 'Scenario 3',
    title: 'Move into selection with a practical view of what matters.',
    summary:
      'Availability, readiness, and launch context are grouped into a single flow so the user can focus on decision-making instead of searching.',
    bullets: [
      'Review flat availability with less visual noise',
      'Keep profile and household context accessible',
      'Stay aligned with the launch timeline and next action',
    ],
    metric: '4 key moments',
    metricLabel: 'from browse to shortlist to selection readiness',
  },
]

export const upcomingLaunches: LaunchItem[] = [
  {
    id: 'garden-vista',
    month: 'July 2026',
    town: 'Tengah',
    project: 'Garden Vista',
    summary:
      'A greenery-led launch with courtyard planning, family-sized layouts, and strong access to future west-side growth nodes.',
    window: 'Applications open in 6 days',
    flatTypes: ['2-Room Flexi', '3-Room', '4-Room', '5-Room'],
    status: 'Upcoming',
  },
  {
    id: 'north-haven',
    month: 'August 2026',
    town: 'Woodlands',
    project: 'North Haven',
    summary:
      'A practical transport-connected launch designed for younger households seeking convenience and a simpler commute.',
    window: 'Preview details arriving next week',
    flatTypes: ['3-Room', '4-Room', '5-Room'],
    status: 'Preview soon',
  },
  {
    id: 'skyline-commons',
    month: 'September 2026',
    town: 'Bishan',
    project: 'Skyline Commons',
    summary:
      'A rarer central launch with compact urban planning, elevated shared spaces, and a more premium location profile.',
    window: 'Indicative pricing to be released soon',
    flatTypes: ['3-Room', '4-Room'],
    status: 'Early view',
  },
]

export const processSteps: ProcessStep[] = [
  {
    id: 'explore',
    label: '01',
    title: 'Explore launch windows',
    detail: 'Shortlist towns, compare flat types, and review the current application period.',
  },
  {
    id: 'ballot',
    label: '02',
    title: 'Understand ballot status',
    detail: 'See where your application stands and what ballot outcomes mean for your next move.',
  },
  {
    id: 'select',
    label: '03',
    title: 'Prepare for selection',
    detail: 'Review profile details, check launch readiness, and move into flat selection confidently.',
  },
]

export const demoUsers: DemoUser[] = [
  {
    nric: 'S1234567A',
    password: 'apple123',
    name: 'Rachel Tan',
    age: 29,
    household: 'Fiance/Fiancee Scheme',
    status: 'First-timer household',
    preferredTown: 'Tengah',
  },
  {
    nric: 'S7654321D',
    password: 'redhome',
    name: 'Marcus Lee',
    age: 34,
    household: 'Married couple',
    status: 'First-timer household',
    preferredTown: 'Woodlands',
  },
]

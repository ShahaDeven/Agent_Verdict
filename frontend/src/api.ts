// Typed client for the Agent Verdict backend (agent_verdict/server.py).

export type Flag = 'yellow' | 'green' | 'red'

export interface Summary {
  judged: number
  to_review: number
  reviewed: number
  overridden: number
  auto_decided: number
  flags: Partial<Record<Flag, number>>
  auto_accuracy_vs_experts: number | null
  auto_runs_with_expert_label: number
  accuracy_with_reviews: number | null
  reviewed_with_expert_label: number
  reviews_matching_experts: number
  looped: number
  looped_by_experts: number
  looping_agreement: number | null
  cost_per_1000_runs: number | null
  judging_enabled: boolean
}

export interface LiveItem {
  id: number
  key: string
  source: string
  agent: string | null
  goal: string
  final_message: string | null
  created_at: string
  flag: Flag | null
  success: number | null
  failure_type: string | null
  looping: number | null
  confidence: 'high' | 'medium' | 'low' | null
  needs_review: number | null
  cost_usd: number | null
  latency_s: number | null
  judged_at: string | null
}

export interface QueueItem {
  id: number
  key: string
  benchmark: string | null
  agent: string | null
  goal: string
  flag: Flag
  success: number | null
  failure_type: string | null
  confidence: 'high' | 'medium' | 'low' | null
  needs_review: number
  review_decision: 'agree' | 'override' | null
}

export interface Step {
  n: number
  url: string
  action: string
  reasoning: string
}

export interface Verdict {
  judge: string
  flag: Flag
  success: number | null
  claimed_success: number | null
  failure_type: string | null
  side_effect: number | null
  side_effect_detail: string | null
  looping: number | null
  evidence_step: number | null
  evidence_screenshot: string | null
  evidence_quote: string | null
  confidence: 'high' | 'medium' | 'low' | null
  needs_review: number
  reasoning: string | null
  frames: string[]
  cost_usd: number | null
  latency_s: number | null
  tokens_in: number | null
  tokens_out: number | null
  reasoning_tokens: number | null
  effort: string | null
  model: string | null
}

export interface Review {
  id: number
  decision: 'agree' | 'override'
  success: number
  note: string | null
  created_at: string
}

export interface Run {
  id: number
  key: string
  source: string
  benchmark: string | null
  agent: string | null
  task: string | null
  goal: string
  steps: Step[]
  n_states: number
  final_message: string | null
  screens: number[]
  ref_success: number | null
  verdict: Verdict | null
  reviews: Review[]
}

async function get<T>(path: string): Promise<T> {
  const r = await fetch(path)
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`)
  return r.json() as Promise<T>
}

export const api = {
  summary: () => get<Summary>('/api/summary'),
  queue: (status: 'to_review' | 'reviewed' | 'auto' | 'all' = 'to_review', limit = 500) =>
    get<{ total: number; items: QueueItem[] }>(`/api/queue?status=${status}&limit=${limit}`),
  run: (id: number) => get<Run>(`/api/runs/${id}`),
  featured: () => get<{ id: number | null; run: Run | null }>('/api/featured'),
  live: () => get<{ items: LiveItem[]; judging_enabled: boolean }>('/api/live'),
  screenUrl: (id: number, state: number) => `/api/runs/${id}/screens/${state}`,
  review: async (id: number, success: boolean, agreesWithJudge: boolean, note?: string) => {
    const r = await fetch(`/api/runs/${id}/review`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ decision: agreesWithJudge ? 'agree' : 'override', success, note: note || null }),
    })
    if (!r.ok) throw new Error(`${r.status} ${await r.text()}`)
    return r.json() as Promise<Review>
  },
}

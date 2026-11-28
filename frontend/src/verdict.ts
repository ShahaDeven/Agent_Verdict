// Plain-English wording for verdicts. One place, so every screen says the same thing.
import type { Flag, Run, Verdict } from './api'

export const FLAG: Record<Flag, { word: string; bg: string; ink: string }> = {
  yellow: { word: 'Person decides', bg: 'bg-flag-yellow', ink: 'text-ink' },
  red: { word: 'Failed', bg: 'bg-flag-red', ink: 'text-white' },
  green: { word: 'Succeeded', bg: 'bg-flag-green', ink: 'text-white' },
}

const FAILURE: Record<string, string> = {
  false_completion: 'claimed done, but not done',
  wrong_answer: 'the answer looks wrong or unsupported',
  gave_up: 'it stopped before finishing',
  looping: 'it repeated itself without progress',
  blocked: 'something on the site blocked it',
  wrong_target: 'it worked on the wrong thing',
  other: 'something else went wrong',
}

export function failureWords(type: string | null): string {
  return (type && FAILURE[type]) || 'something went wrong'
}

/** The one-line race-control message. It never contradicts the "what the agent said" column. */
export function headline(v: Verdict, run: Run): string {
  const said = Boolean(run.final_message)
  if (v.success) {
    return v.side_effect
      ? 'Looks done, but the agent may have changed something nobody asked for.'
      : 'Looks done, but the judge wants a second pair of eyes.'
  }
  switch (v.failure_type) {
    case 'false_completion':
      return said ? "The agent says it's done. The screen says it isn't." : "The agent stopped as if it were done. It isn't."
    case 'wrong_answer':
      return "The agent answered, but the screens don't back the answer up."
    case 'gave_up':
      return 'The agent stopped before the job was done.'
    case 'looping':
      return 'The agent kept repeating itself and got nowhere.'
    case 'blocked':
      return 'Something on the site stopped the agent.'
    case 'wrong_target':
      return 'The agent worked on the wrong thing.'
    default:
      return 'The run went wrong in an unusual way.'
  }
}

export function judgeCall(v: Verdict): string {
  return v.success ? 'it succeeded' : `it failed: ${failureWords(v.failure_type)}`
}

/** Index of the last page state: the page after the final action (labelled END). */
export function endState(run: Run): number {
  return run.n_states - 1
}

/** "FINAL" is the last state; "S9" is the screen the agent saw at step 9 (state index 8). */
function labelToState(run: Run, label: string): number | null {
  if (label === 'FINAL') return endState(run)
  const m = label.match(/^S(\d+)$/)
  if (!m) return null
  const s = Number(m[1]) - 1
  return s >= 0 && s < run.n_states ? s : null
}

/** The screen the judge names as proof. */
export function proofState(run: Run): number | null {
  const label = run.verdict?.evidence_screenshot
  return label ? labelToState(run, label) : null
}

/** Every screen the proof points to: the named one first, then any the quote mentions ("S9", "FINAL"). */
export function proofStates(run: Run): number[] {
  const out: number[] = []
  const add = (s: number | null) => { if (s != null && !out.includes(s)) out.push(s) }
  add(proofState(run))
  for (const m of (run.verdict?.evidence_quote ?? '').matchAll(/\b(S\d+|FINAL)\b/g)) add(labelToState(run, m[1]))
  return out
}

/** The judge's quote with its shorthand spelled out: "S9" -> "the screen at step 9", "FINAL" -> "the final screen". */
export function plainQuote(quote: string): string {
  return quote
    .replace(/\bS(\d+)\b/g, 'the screen at step $1')
    .replace(/\bFINAL\b/g, 'the final screen')
}

export function screenName(run: Run, state: number): string {
  return state === endState(run) ? 'Final screen' : `Step ${state + 1}`
}

export function agentSaid(run: Run): string {
  return run.final_message ? `“${run.final_message.replace(/\\n/g, ' ')}”` : 'Nothing: it sent the user no message.'
}

/** "0.09¢" for a fraction of a cent, "$0.012" above a cent. */
export function money(usd: number | null): string {
  if (usd == null) return '–'
  if (usd === 0) return '$0'
  return usd < 0.01 ? `${(usd * 100).toFixed(2)}¢` : `$${usd.toFixed(3)}`
}

/** A short, readable site name from a benchmark key or URL. */
export function siteName(run: { benchmark?: string | null; steps?: Run['steps']; source: string }): string {
  const names: Record<string, string> = {
    webarena: 'WebArena', visualwebarena: 'VisualWebArena', workarena: 'WorkArena', assistantbench: 'AssistantBench',
  }
  if (run.benchmark && names[run.benchmark]) return names[run.benchmark]
  const url = run.steps?.[0]?.url ?? ''
  const demo: [string, string][] = [['/shop/', 'Lakeshore Supply'], ['/bistro/', 'Harbor Bistro'], ['/desk/', 'Northpoint Help Desk']]
  for (const [path, name] of demo) if (url.includes(path)) return name
  try {
    return new URL(run.steps?.[0]?.url ?? '').host || run.source
  } catch {
    return run.source
  }
}

/** "GenericAgent-anthropic_claude-3.7-sonnet" -> "claude-3.7-sonnet". */
export function agentName(agent: string | null): string {
  if (!agent) return 'agent'
  return agent.replace(/^GenericAgent-/, '').replace(/^[^_]+_/, '')
}

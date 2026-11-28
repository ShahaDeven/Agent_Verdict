import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { api, type QueueItem, type Run, type Summary } from '../api'
import { Header } from '../components/Header'
import { Replay, isEnd } from '../components/Replay'
import { Screen } from '../components/Screen'
import { Tag } from './Front'
import {
  agentName, agentSaid, endState, FLAG, headline, judgeCall, money, plainQuote, proofState, proofStates, screenName, siteName,
} from '../verdict'

// #/review/<run id>; without an id, the first run in the queue.
function idFromHash(): number | null {
  const m = window.location.hash.match(/^#\/review\/(\d+)/)
  return m ? Number(m[1]) : null
}

// Runs are fetched once and kept, and the next run is fetched ahead, so moving through the queue is instant.
const runCache = new Map<number, Promise<Run>>()
function loadRun(id: number, fresh = false): Promise<Run> {
  if (fresh || !runCache.has(id)) {
    const p = api.run(id)
    p.catch(() => runCache.delete(id))
    runCache.set(id, p)
  }
  return runCache.get(id)!
}
function prefetch(id: number) {
  loadRun(id).then((r) => {
    const s = proofState(r)
    if (s != null && r.screens.includes(s)) new Image().src = api.screenUrl(r.id, s)
  }, () => undefined)
}

export function ReviewPage() {
  const [queue, setQueue] = useState<QueueItem[] | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [id, setId] = useState<number | null>(idFromHash)

  // The queue is fixed for the session (least confident first), so decided runs keep their place.
  useEffect(() => {
    api.queue('to_review').then((q) => {
      setQueue(q.items)
      setId((cur) => cur ?? q.items[0]?.id ?? null)
    }, (e: Error) => setErr(e.message))
  }, [])
  useEffect(() => {
    const on = () => setId(idFromHash())
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])

  const pos = queue && id != null ? queue.findIndex((q) => q.id === id) : -1
  const nextId = queue?.length ? queue[((pos < 0 ? -1 : pos) + 1) % queue.length].id : null
  const go = useCallback((d: number) => {
    if (!queue?.length) return
    const next = queue[((pos < 0 ? 0 : pos) + d + queue.length) % queue.length]
    window.location.hash = `#/review/${next.id}`
  }, [queue, pos])
  useEffect(() => { if (nextId != null && nextId !== id) prefetch(nextId) }, [nextId, id])

  return (
    <div className="flex min-h-screen flex-col">
      <Header>
        {queue?.length ? (
          <span className="flex items-center gap-2">
            <span className="text-[15px]">
              {pos >= 0 ? <>Run <strong>{pos + 1}</strong> of {queue.length} to review</> : <>{queue.length} to review</>}
            </span>
            <button type="button" onClick={() => go(-1)} aria-label="Previous run"
                    className="size-11 border-2 border-ink bg-transparent text-lg hover:bg-paper-2">←</button>
            <button type="button" onClick={() => go(1)} aria-label="Next run"
                    className="size-11 border-2 border-ink bg-transparent text-lg hover:bg-paper-2">→</button>
          </span>
        ) : null}
      </Header>
      {err ? <Notice>Can't reach the backend ({err}). Start it with <code className="font-mono">agent-verdict serve</code>.</Notice> : null}
      {queue && queue.length === 0 && id == null ? <Notice>Nothing to review: every run was decided by the judge. <a href="#/">Back to the front page</a>.</Notice> : null}
      {id != null ? <RunView key={id} id={id} inQueue={pos >= 0} onNext={() => go(1)} /> : <Skeleton />}
    </div>
  )
}

function Notice({ children }: { children: ReactNode }) {
  return <p role="alert" className="mx-5 mt-8 border-2 border-ink bg-card p-4 sm:mx-10">{children}</p>
}

function Skeleton() {
  return (
    <div aria-busy="true" aria-label="Loading run" className="animate-pulse">
      <div className="h-[52px] bg-ink" />
      <div className="mx-auto flex w-full max-w-[1280px] flex-col gap-6 px-5 pt-8 sm:px-10">
        <div className="h-4 w-72 bg-paper-2" />
        <div className="h-9 w-3/4 bg-paper-2" />
        <div className="flex flex-wrap gap-6">
          <div className="h-40 flex-[1_1_300px] bg-paper-2" />
          <div className="h-[420px] flex-[2_1_520px] bg-paper-2" />
        </div>
      </div>
    </div>
  )
}

function RunView({ id, inQueue, onNext }: { id: number; inQueue: boolean; onNext: () => void }) {
  const [run, setRun] = useState<Run | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [picked, setPicked] = useState<number | null>(null)
  const [fullGoal, setFullGoal] = useState(false)
  const [saving, setSaving] = useState(false)
  const [after, setAfter] = useState<{ before: Summary | null; now: Summary } | null>(null)

  useEffect(() => {
    loadRun(id).then(setRun, (e: Error) => setErr(e.message))
  }, [id])

  const decide = useCallback(async (success: boolean) => {
    if (!run?.verdict || saving || run.reviews.length) return
    setSaving(true)
    try {
      const before = await api.summary().catch(() => null)
      await api.review(run.id, success, success === Boolean(run.verdict.success))
      const [fresh, now] = await Promise.all([loadRun(run.id, true), api.summary()])
      setRun(fresh)
      setAfter({ before, now })
    } catch (e) {
      setErr((e as Error).message)
    } finally {
      setSaving(false)
    }
  }, [run, saving])

  // Keyboard: F = failed, S = succeeded, → = next run (ignored while typing).
  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement
      if (e.metaKey || e.ctrlKey || e.altKey || t.closest('input, textarea, select, [contenteditable]')) return
      if (e.key === 'f' || e.key === 'F') decide(false)
      else if (e.key === 's' || e.key === 'S') decide(true)
      else if (e.key === 'ArrowRight') onNext()
    }
    window.addEventListener('keydown', on)
    return () => window.removeEventListener('keydown', on)
  }, [decide, onNext])

  if (err) return <Notice>Couldn't load run {id} ({err}).</Notice>
  if (!run) return <Skeleton />
  if (!run.verdict) return <Notice>Run {id} hasn't been judged yet.</Notice>

  const v = run.verdict
  const proof = proofState(run)
  const proofs = proofStates(run)
  const state = picked ?? proof ?? endState(run)
  const decided = run.reviews.at(-1) ?? null
  const f = FLAG[v.flag]
  const lastMsgStep = [...run.steps].reverse().find((s) => s.action.startsWith('send_msg_to_user'))
  const [goalHead, ...goalRest] = run.goal.trim().split(/\n\s*\n/)
  const goalMore = goalRest.join('\n\n').trim()
  const judgeOk = Boolean(v.success)
  const showingProof = proofs.includes(state)

  return (
    <>
      {/* race-control message */}
      <div role="status" className="flex flex-wrap items-stretch bg-ink text-paper">
        <span className={`flex items-center px-6 py-3 font-display text-xl font-extrabold tracking-[0.04em] sm:pl-10 ${decided ? 'bg-paper-2 text-ink' : `${f.bg} ${f.ink}`}`}>
          {decided ? 'DECIDED' : f.word.toUpperCase()}
        </span>
        <span className="flex flex-[1_1_420px] flex-wrap items-center gap-x-4 gap-y-1 px-6 py-3 sm:pr-10">
          <span className="font-display text-[22px] font-bold uppercase tracking-[0.03em]">Run {run.id}: {headline(v, run)}</span>
          {v.looping ? <span className="border border-paper px-1.5 py-px font-mono text-xs font-semibold">LOOPED</span> : null}
          {v.side_effect ? <span className="border border-paper px-1.5 py-px font-mono text-xs font-semibold">SIDE EFFECT?</span> : null}
        </span>
      </div>

      {/* Ember, on every verdict */}
      <div className="border-b border-rule bg-paper-2">
        <p className="mx-auto m-0 flex w-full max-w-[1280px] flex-wrap gap-x-5 gap-y-1 px-5 py-2.5 font-mono text-[13px] text-ink-2 sm:px-10">
          <span><strong className="text-ink">This verdict:</strong> Muse Ember ({v.model ?? 'muse-ember-1.0'}) at {v.effort ?? 'minimal'} effort</span>
          <span>{money(v.cost_usd)}</span>
          {v.tokens_in != null ? <span>{v.tokens_in.toLocaleString()} tokens in · {(v.tokens_out ?? 0).toLocaleString()} out</span> : null}
          {v.frames.length ? <span>{v.frames.length} screenshots read</span> : null}
          {v.latency_s != null ? <span>{v.latency_s.toFixed(1)}s</span> : null}
        </p>
      </div>

      <main className="mx-auto flex w-full max-w-[1280px] flex-col gap-7 px-5 pb-14 pt-8 sm:px-10">
        <section className="flex flex-col gap-1.5">
          <span className="font-mono text-[13px] text-ink-3">
            THE GOAL · {siteName(run)} · agent {agentName(run.agent)} · {run.n_states} screens
            {!inQueue ? ' · not in the review queue' : ''}
          </span>
          <h1 className={`m-0 max-w-[980px] text-[26px] font-semibold leading-snug sm:text-[30px] ${fullGoal ? '' : 'line-clamp-4'}`}>
            {goalHead}
          </h1>
          {goalMore && fullGoal ? (
            <p className="m-0 max-w-[980px] whitespace-pre-line text-[15px] leading-relaxed text-ink-2">{goalMore}</p>
          ) : null}
          {goalMore ? (
            <button type="button" onClick={() => setFullGoal((x) => !x)}
                    className="w-fit border-0 bg-transparent p-0 text-sm font-semibold underline">
              {fullGoal ? 'Show less' : 'Show the full goal'}
            </button>
          ) : null}
        </section>

        {/* said vs shows */}
        <section className="flex flex-wrap items-start gap-6">
          <div className="flex min-w-0 flex-[1_1_300px] flex-col gap-3 border-t-[6px] border-ink pt-3.5">
            <h2 className="m-0 font-display text-[22px] font-extrabold tracking-[0.03em]">WHAT THE AGENT SAID</h2>
            <p className="m-0 text-2xl font-medium leading-snug [overflow-wrap:anywhere]">{agentSaid(run)}</p>
            <span className="text-sm text-ink-3">
              {lastMsgStep
                ? `Its last message, at step ${lastMsgStep.n}.${v.claimed_success ? ' It claimed the job was done.' : ''}`
                : v.claimed_success
                  ? 'It ended the run as if the job were done.'
                  : 'It ended the run without saying anything.'}
            </span>
          </div>
          <figure className={`m-0 flex min-w-0 flex-[2_1_520px] flex-col gap-3 border-t-[6px] pt-3.5 ${showingProof ? 'border-flag-yellow' : 'border-ink'}`}>
            <figcaption className="flex flex-wrap items-baseline gap-x-3 gap-y-1.5">
              <span className="font-display text-[22px] font-extrabold tracking-[0.03em]">WHAT THE SCREEN SHOWS</span>
              <span className="text-sm text-ink-3">
                {isEnd(run, state) ? 'the final screen: what the user sees now' : `the screen at step ${state + 1}, before the agent acted`}
              </span>
            </figcaption>
            <Screen src={run.screens.includes(state) ? api.screenUrl(run.id, state) : null}
                    url={run.steps[state]?.url ?? ''} alt={`${screenName(run, state)} of run ${run.id}`} />
            {v.evidence_quote ? (
              <div className="flex flex-col gap-2 border-l-4 border-flag-yellow bg-card px-3.5 py-2.5">
                <p className="m-0 text-[15px] leading-relaxed">
                  <span className="mr-2 border border-ink bg-flag-yellow px-1.5 py-0.5 font-mono text-xs font-semibold">PROOF</span>
                  {plainQuote(v.evidence_quote)}
                </p>
                {proofs.length ? (
                  <div className="flex flex-wrap items-center gap-2 text-sm">
                    <span className="text-ink-3">The judge points to:</span>
                    {proofs.map((s) => (
                      <button key={s} type="button" onClick={() => setPicked(s)} aria-pressed={s === state}
                              className={`border-2 border-ink px-2.5 py-1 font-semibold ${s === state ? 'bg-ink text-paper' : 'bg-transparent text-ink hover:bg-paper-2'}`}>
                        {screenName(run, s)}
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : null}
          </figure>
        </section>

        {/* the judge's reasoning, in the open */}
        <section aria-label="Why the judge thinks so" className="flex max-w-[980px] flex-col gap-2">
          <h2 className="m-0 font-display text-[22px] font-extrabold tracking-[0.03em]">WHY THE JUDGE THINKS SO</h2>
          <p className="m-0 text-[17px] leading-relaxed">{plainQuote(v.reasoning ?? "")}</p>
          <p className="m-0 flex flex-wrap gap-2 text-sm text-ink-2">
            <Tag>{judgeCall(v).toUpperCase()}</Tag>
            <Tag>{(v.confidence ?? 'unknown').toUpperCase()} CONFIDENCE</Tag>
            {v.looping ? <Tag>LOOPED</Tag> : null}
            {v.side_effect ? <Tag>SIDE EFFECT?</Tag> : null}
          </p>
          {v.side_effect && v.side_effect_detail ? <p className="m-0 text-sm text-ink-2">Possible side effect: {v.side_effect_detail}</p> : null}
        </section>

        <Replay run={run} state={state} proofs={proofs} onPick={setPicked} />

        {/* the call */}
        <section aria-label="Your call" className="flex flex-col gap-3.5 border-t-2 border-ink pt-6">
          <h2 className="m-0 font-display text-[30px] font-extrabold tracking-[0.02em]">DID THE AGENT DO WHAT WAS ASKED?</h2>
          <p className="m-0 text-base text-ink-2">
            The judge thinks <strong>{judgeCall(v)}</strong>
            {v.needs_review ? `, but isn't sure enough to decide alone (${v.confidence} confidence).` : '.'}
          </p>
          {!decided ? (
            <div className="flex flex-wrap items-center gap-3">
              <button type="button" disabled={saving} onClick={() => decide(false)}
                      className="min-h-14 border-2 border-ink bg-ink px-7 text-[17px] font-semibold text-paper hover:bg-ink-2 disabled:opacity-60">
                No, it failed <kbd className="ml-2 font-mono text-xs opacity-70">F</kbd>
              </button>
              <button type="button" disabled={saving} onClick={() => decide(true)}
                      className="min-h-14 border-2 border-ink bg-transparent px-7 text-[17px] font-semibold text-ink hover:bg-paper-2 disabled:opacity-60">
                Yes, it succeeded <kbd className="ml-2 font-mono text-xs opacity-70">S</kbd>
              </button>
              {saving ? <span role="status" className="text-sm text-ink-3">Recording…</span> : null}
            </div>
          ) : (
            <Recorded run={run} judgeOk={judgeOk} after={after} onNext={onNext} />
          )}
        </section>
      </main>
    </>
  )
}

/** What a decision did: recorded, agreed or overrode, how it compares with the experts, and the updated numbers. */
function Recorded({ run, judgeOk, after, onNext }: {
  run: Run; judgeOk: boolean; after: { before: Summary | null; now: Summary } | null; onNext: () => void
}) {
  const d = run.reviews.at(-1)!
  const agreed = Boolean(d.success) === judgeOk
  const now = after?.now
  const before = after?.before
  const pct = (x: number | null | undefined) => (x == null ? '–' : `${(x * 100).toFixed(1)}%`)
  return (
    <div role="status" className="flex flex-col gap-4 border-2 border-ink bg-card p-5">
      <p className="m-0 text-[19px] font-semibold">
        <span aria-hidden="true" className="mr-2 inline-block size-3 bg-flag-green align-middle" />
        Recorded: {d.success ? 'it succeeded' : 'it failed'}. {agreed ? 'You agreed with the judge.' : 'You overrode the judge.'}
      </p>
      {run.ref_success != null ? (
        <p className="m-0 text-[15px] text-ink-2">
          {run.source === 'live' ? "The site's own records say" : "The benchmark's experts said"} {run.ref_success ? 'it succeeded' : 'it failed'}
          {Boolean(run.ref_success) === Boolean(d.success) ? ', the same as you.' : ', unlike you.'}
        </p>
      ) : null}
      {now ? (
        <dl className="m-0 grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-4">
          <Stat label="Still to review" value={String(now.to_review)} was={before ? String(before.to_review) : null} />
          <Stat label="Reviewed by people" value={String(now.reviewed)} was={before ? String(before.reviewed) : null} />
          <Stat label="People overrode the judge" value={String(now.overridden)} was={before ? String(before.overridden) : null} />
          <Stat label="Accuracy with your reviews" value={pct(now.accuracy_with_reviews ?? now.auto_accuracy_vs_experts)}
                was={before ? pct(before.accuracy_with_reviews ?? before.auto_accuracy_vs_experts) : null} />
        </dl>
      ) : null}
      {now ? (
        <p className="m-0 text-[13px] text-ink-3">
          Accuracy with your reviews: the judge's own calls on the {now.auto_runs_with_expert_label.toLocaleString()} runs it
          decided alone, plus people's calls on the {now.reviewed_with_expert_label} runs reviewed so far, checked against the
          experts. {agreed ? '' : 'Overrides also go into the judge’s accuracy report.'}
        </p>
      ) : null}
      <button type="button" onClick={onNext}
              className="min-h-12 w-fit border-2 border-ink bg-ink px-5 font-semibold text-paper hover:bg-ink-2">
        Next run →
      </button>
    </div>
  )
}

function Stat({ label, value, was }: { label: string; value: string; was: string | null }) {
  const changed = was != null && was !== value
  return (
    <div className="flex flex-col">
      <dt className="text-[13px] text-ink-3">{label}</dt>
      <dd className="m-0 font-display text-[30px] font-extrabold leading-tight">
        {value}
        {changed ? <span className="ml-2 font-mono text-xs font-normal text-ink-3">was {was}</span> : null}
      </dd>
    </div>
  )
}

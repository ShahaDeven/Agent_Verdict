import type { Run } from '../api'

export function isEnd(run: Run, state: number): boolean {
  return state === run.n_states - 1 && (run.steps[state]?.action ?? 'None') === 'None'
}

export function stateLabel(run: Run, state: number): string {
  return isEnd(run, state) ? 'END' : String(state + 1)
}

/** One box per page state: numbered steps, then END (the page the user is left with). */
export function Replay({ run, state, proofs, onPick }: {
  run: Run; state: number; proofs: number[]; onPick: (s: number) => void
}) {
  const shots = new Set(run.screens)
  const step = run.steps[state]
  const end = isEnd(run, state)
  return (
    <section aria-label="Replay" className="flex flex-col gap-3">
      <h2 className="m-0 font-display text-[22px] font-extrabold tracking-[0.03em]">
        REPLAY{' '}
        <span className="font-sans text-sm font-normal tracking-normal text-ink-3">pick a step to see what the agent did</span>
      </h2>
      <div role="group" aria-label="Steps" className="flex flex-wrap gap-1.5">
        {Array.from({ length: run.n_states }, (_, i) => {
          const on = i === state
          return (
            <button key={i} type="button" onClick={() => onPick(i)} aria-pressed={on}
                    aria-label={isEnd(run, i) ? 'End: what the user sees now' : `Step ${i + 1}`}
                    className={`flex h-[58px] min-w-[52px] flex-col items-center justify-between border-2 border-ink px-2 py-1 ${on ? 'bg-ink text-paper' : 'bg-transparent text-ink hover:bg-paper-2'}`}>
              <span className="font-mono text-[15px] font-semibold">{stateLabel(run, i)}</span>
              <span aria-hidden="true" className="flex h-3 items-center gap-1">
                {shots.has(i) ? <span className={`size-2 rounded-full ${on ? 'bg-paper' : 'bg-ink'}`} /> : null}
                {proofs.includes(i) ? <span className="h-2.5 w-3.5 border border-ink bg-flag-yellow" /> : null}
              </span>
            </button>
          )
        })}
      </div>
      <div className="flex flex-col gap-1 border-l-4 border-ink py-1 pl-3.5">
        {end ? (
          <>
            <code className="font-mono text-[15px]">No more actions.</code>
            <span className="text-sm text-ink-2">This is the page the user is left with.</span>
          </>
        ) : (
          <>
            <code className="font-mono text-[15px] [overflow-wrap:anywhere]">Step {state + 1}: {step?.action}</code>
            {step?.reasoning && step.reasoning !== 'None' ? (
              <span className="max-h-40 overflow-auto text-sm text-ink-2">Agent's reasoning: {step.reasoning}</span>
            ) : null}
          </>
        )}
      </div>
      <p className="m-0 text-[13px] text-ink-3">A dot means the judge saw that screen. A yellow flag marks a screen the judge points to as proof.</p>
    </section>
  )
}

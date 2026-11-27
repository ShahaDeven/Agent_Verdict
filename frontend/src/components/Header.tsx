import type { ReactNode } from 'react'

export function Wordmark() {
  return (
    <a href="#/" className="flex items-center gap-3 text-ink no-underline">
      <span aria-hidden="true" className="checker size-6 border-2 border-ink" />
      <span className="font-display text-[24px] font-extrabold tracking-[0.04em]">AGENT VERDICT</span>
    </a>
  )
}

/** The judge, named where people look: every page carries it. */
export function EmberBadge() {
  return (
    <span className="inline-flex items-center gap-2 border-2 border-ink bg-ink px-3 py-1.5 text-paper">
      <span className="font-mono text-[11px] uppercase tracking-[0.08em] text-paper/75">Judged by</span>
      <span className="font-display text-[18px] font-bold leading-none tracking-[0.03em]">MUSE EMBER</span>
    </span>
  )
}

function NavLink({ href, label, active }: { href: string; label: ReactNode; active: boolean }) {
  return (
    <a href={href} aria-current={active ? 'page' : undefined}
       className={`px-3 py-2 text-[15px] font-semibold no-underline ${active ? 'bg-paper-2 text-ink underline decoration-2 underline-offset-[6px]' : 'text-ink-2 hover:bg-paper-2'}`}>
      {label}
    </a>
  )
}

export function Header({ children }: { children?: ReactNode }) {
  const hash = window.location.hash || '#/'
  return (
    <header className="flex flex-wrap items-center gap-x-6 gap-y-3 border-b-2 border-ink px-5 py-3.5 sm:px-10">
      <Wordmark />
      <nav aria-label="Sections" className="flex flex-wrap gap-1">
        <NavLink href="#/review" label="Review queue" active={hash.startsWith('#/review')} />
        <NavLink href="#/live" label="Live" active={hash.startsWith('#/live')} />
      </nav>
      <div className="ml-auto flex flex-wrap items-center gap-3">
        {children}
        <EmberBadge />
      </div>
    </header>
  )
}

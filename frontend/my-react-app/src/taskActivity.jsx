// A tiny shared "is anything running right now" counter, so a single loader
// in the header reflects background activity from any tab/component —
// uploads, crawls, saved-source runs, and analysis runs all report into it
// rather than each having their own disconnected spinner.
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'

const TaskActivityContext = createContext(null)

export function TaskActivityProvider({ children }) {
  const [count, setCount] = useState(0)
  const begin = useCallback(() => setCount((c) => c + 1), [])
  const end = useCallback(() => setCount((c) => Math.max(0, c - 1)), [])
  const value = useMemo(() => ({ count, begin, end }), [count, begin, end])
  return <TaskActivityContext.Provider value={value}>{children}</TaskActivityContext.Provider>
}

export function useTaskActivity() {
  const ctx = useContext(TaskActivityContext)
  if (!ctx) throw new Error('useTaskActivity must be used within a TaskActivityProvider')
  return ctx
}

// Reports a boolean "am I busy" flag into the shared counter, incrementing
// on the false->true transition and decrementing on true->false (or on
// unmount while still busy, so a component going away never leaves the
// counter stuck above zero).
export function useReportBusy(isBusy) {
  const { begin, end } = useTaskActivity()
  const wasBusy = useRef(false)

  useEffect(() => {
    if (isBusy && !wasBusy.current) {
      wasBusy.current = true
      begin()
    } else if (!isBusy && wasBusy.current) {
      wasBusy.current = false
      end()
    }
  }, [isBusy, begin, end])

  useEffect(() => () => {
    if (wasBusy.current) {
      wasBusy.current = false
      end()
    }
  }, [end])
}

export function GlobalLoader() {
  const { count } = useTaskActivity()
  if (count === 0) return null
  return (
    <span
      className="global-loader"
      role="status"
      title={`${count} background task${count > 1 ? 's' : ''} running`}
    >
      <span className="spinner" aria-hidden="true" />
      {count > 1 ? `${count} running…` : 'running…'}
    </span>
  )
}

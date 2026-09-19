import { useCallback, useState } from 'react'

// A manual refresh against a local API often resolves in well under the
// ~100ms a human needs to perceive feedback at all — verified live: a
// Refresh click was firing a real request every time (confirmed via
// network-request counts), but with no visible sign of it, it looked
// broken. This enforces a minimum visible "Refreshing…" duration so a
// click always has *some* perceptible feedback, regardless of how fast
// the actual response was.
const MIN_VISIBLE_MS = 400

// Wrap a `load` callback (called silently by auto-refresh intervals) so a
// manual button click also shows a transient busy state. Returns
// `refreshing` (for disabling/labeling the button) and `handleClick` (the
// button's onClick).
export function useRefreshButton(load) {
  const [refreshing, setRefreshing] = useState(false)

  const handleClick = useCallback(async () => {
    setRefreshing(true)
    const start = Date.now()
    await load()
    const remaining = MIN_VISIBLE_MS - (Date.now() - start)
    if (remaining > 0) await new Promise((r) => setTimeout(r, remaining))
    setRefreshing(false)
  }, [load])

  return { refreshing, handleClick }
}

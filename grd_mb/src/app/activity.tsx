import { useCallback, useState } from 'react';
import { Alert, Platform } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { Btn, Card, ErrorCard, KV, Screen, Segmented, fmtTime, statusColor } from '@/components/ui';
import { Spacing } from '@/constants/theme';
import { deleteException, listActivity, listExceptions } from '@/lib/api';

type Event = {
  id: string;
  at: string;
  type: string;
  ticker: string | null;
  title: string;
  detail: string | null;
  status: string | null;
};
type ExceptionRow = {
  id: number;
  created_at: string;
  source: string;
  message: string;
  context: Record<string, unknown> | null;
  traceback: string | null;
};

const TYPE_LABELS: Record<string, string> = {
  run_started: 'Run started',
  run_finished: 'Run finished',
  agent_decision: 'Agent decision',
  signal: 'Signal',
  report: 'Report',
  alert: 'Alert',
  ingestion_started: 'Ingest started',
  ingestion_finished: 'Ingest finished',
};

function ActivityFeed() {
  const [events, setEvents] = useState<Event[]>([]);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setEvents(await listActivity(150));
      setErr(null);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      throw e;
    }
  }, []);

  return (
    <Screen
      title="Activity"
      subtitle="Runs, agent decisions, signals, reports, alerts and ingestions — newest first. Refreshes every 5s."
      onRefresh={load}
      pollMs={5000}>
      <ErrorCard message={err} />
      {events.length === 0 && !err && (
        <ThemedText type="small" themeColor="textSecondary">
          No activity yet.
        </ThemedText>
      )}
      {events.map((e) => (
        <Card key={e.id}>
          <ThemedView style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
            <ThemedText type="smallBold">{TYPE_LABELS[e.type] ?? e.type}</ThemedText>
            <ThemedText type="small" style={{ color: statusColor(e.status) }}>
              {e.status ?? ''}
            </ThemedText>
          </ThemedView>
          <ThemedText type="small">{e.title}</ThemedText>
          {!!e.detail && (
            <ThemedText type="small" themeColor="textSecondary">
              {e.detail}
            </ThemedText>
          )}
          <ThemedText type="small" themeColor="textSecondary">
            {e.ticker ? `${e.ticker} · ` : ''}
            {fmtTime(e.at)}
          </ThemedText>
        </Card>
      ))}
    </Screen>
  );
}

function confirmDelete(): Promise<boolean> {
  const text = 'Permanently delete this exception log entry? This cannot be undone.';
  if (Platform.OS === 'web') return Promise.resolve(window.confirm(text));
  return new Promise((resolve) =>
    Alert.alert('Delete entry', text, [
      { text: 'Cancel', style: 'cancel', onPress: () => resolve(false) },
      { text: 'Delete', style: 'destructive', onPress: () => resolve(true) },
    ]),
  );
}

function ExceptionList() {
  const [rows, setRows] = useState<ExceptionRow[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [open, setOpen] = useState<number | null>(null);

  const load = useCallback(async () => {
    try {
      setRows(await listExceptions(200));
      setErr(null);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      throw e;
    }
  }, []);

  const remove = async (id: number) => {
    if (!(await confirmDelete())) return;
    try {
      await deleteException(id);
      setRows((prev) => prev.filter((r) => r.id !== id));
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <Screen
      title="Exceptions"
      subtitle="Unexpected failures: API errors and Celery task failures. Expected errors (a plain 404) are not logged."
      onRefresh={load}>
      <ErrorCard message={err} />
      {rows.length === 0 && !err && (
        <ThemedText type="small" themeColor="textSecondary">
          No exceptions logged.
        </ThemedText>
      )}
      {rows.map((r) => (
        <Card key={r.id}>
          <ThemedText type="smallBold">{r.source}</ThemedText>
          <ThemedText type="small">{r.message}</ThemedText>
          <KV k="When" v={fmtTime(r.created_at)} />
          {!!r.context && Object.keys(r.context).length > 0 && (
            <ThemedText type="small" themeColor="textSecondary">
              {JSON.stringify(r.context)}
            </ThemedText>
          )}
          {open === r.id && !!r.traceback && (
            <ThemedText type="code" style={{ marginTop: Spacing.one }}>
              {r.traceback}
            </ThemedText>
          )}
          <ThemedView style={{ flexDirection: 'row', gap: Spacing.two }}>
            {!!r.traceback && (
              <Btn ghost label={open === r.id ? 'Hide traceback' : 'View traceback'} onPress={() => setOpen(open === r.id ? null : r.id)} />
            )}
            <Btn ghost label="Delete" onPress={() => remove(r.id)} />
          </ThemedView>
        </Card>
      ))}
    </Screen>
  );
}

export default function ActivityScreen() {
  const [view, setView] = useState<'activity' | 'exceptions'>('activity');
  return (
    <ThemedView style={{ flex: 1 }}>
      <ThemedView style={{ paddingHorizontal: Spacing.four, paddingTop: Spacing.six }}>
        <Segmented
          value={view}
          options={[
            { key: 'activity', label: 'Activity' },
            { key: 'exceptions', label: 'Exceptions' },
          ]}
          onChange={setView}
        />
      </ThemedView>
      {view === 'activity' ? <ActivityFeed /> : <ExceptionList />}
    </ThemedView>
  );
}

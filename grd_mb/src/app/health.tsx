import { useCallback, useState } from 'react';
import { Linking } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { BAD, Btn, Card, ErrorCard, GOOD, KV, Screen, statusColor } from '@/components/ui';
import { Spacing } from '@/constants/theme';
import { API_BASE, healthServices } from '@/lib/api';

type Service = {
  status: 'up' | 'down' | 'unknown';
  detail?: string;
  link?: string;
  hint?: string;
  info?: Record<string, unknown>;
};

const LABELS: Record<string, string> = {
  postgres: 'Postgres',
  redis: 'Redis',
  qdrant: 'Qdrant',
  celery_worker: 'Celery worker',
  celery_beat: 'Celery beat',
};
const ORDER = ['postgres', 'redis', 'qdrant', 'celery_worker', 'celery_beat'];

// The API reports its own view of localhost; a phone needs the dev machine's address instead.
function reachable(url: string) {
  try {
    return url.replace(/\/\/(localhost|127\.0\.0\.1)/, `//${new URL(API_BASE).hostname}`);
  } catch {
    return url;
  }
}

export default function HealthScreen() {
  const [services, setServices] = useState<Record<string, Service>>({});
  const [checkedAt, setCheckedAt] = useState<Date | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await healthServices();
      setServices(res.services ?? {});
      setCheckedAt(new Date());
      setErr(null);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      throw e;
    }
  }, []);

  const anyDown = ORDER.some((k) => services[k]?.status === 'down');

  return (
    <Screen
      title="Health"
      subtitle={checkedAt ? `Checked ${checkedAt.toLocaleTimeString()} · refreshes every 10s` : 'Checking…'}
      onRefresh={load}
      pollMs={10000}>
      <ErrorCard message={err} />
      {anyDown && (
        <Card>
          <ThemedText type="small" style={{ color: BAD }}>
            A dependency is down — uploads and analysis will fail until it is restarted (usually
            docker compose up -d postgres redis qdrant mailhog, or restart the Celery worker).
          </ThemedText>
        </Card>
      )}
      {ORDER.map((key) => {
        const s = services[key];
        if (!s) return null;
        const info = s.info && Object.keys(s.info).length ? s.info : null;
        const isOpen = open === key;
        return (
          <Card key={key}>
            <ThemedView style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
              <ThemedText type="smallBold">{LABELS[key]}</ThemedText>
              <ThemedText
                type="smallBold"
                style={{ color: s.status === 'up' ? GOOD : s.status === 'down' ? BAD : statusColor(s.status) }}>
                {s.status}
              </ThemedText>
            </ThemedView>
            {!!s.detail && (
              <ThemedText type="small" themeColor="textSecondary">
                {s.detail}
              </ThemedText>
            )}
            <ThemedView style={{ flexDirection: 'row', gap: Spacing.two, flexWrap: 'wrap' }}>
              {!!s.link && <Btn ghost label="Open dashboard ↗" onPress={() => Linking.openURL(reachable(s.link as string))} />}
              {(info || s.hint) && (
                <Btn ghost label={isOpen ? 'Hide details' : 'View details'} onPress={() => setOpen(isOpen ? null : key)} />
              )}
            </ThemedView>
            {isOpen && (
              <ThemedView style={{ gap: Spacing.one, marginTop: Spacing.one }}>
                {info && Object.entries(info).map(([k, v]) => <KV key={k} k={k} v={String(v)} />)}
                {!!s.hint && (
                  <ThemedText type="small" themeColor="textSecondary">
                    {s.hint}
                  </ThemedText>
                )}
              </ThemedView>
            )}
          </Card>
        );
      })}
      <ThemedText type="small" themeColor="textSecondary">
        The Qdrant dashboard opens on the API host, port 6333 — reachable from a phone only if
        that port is exposed on your network.
      </ThemedText>
    </Screen>
  );
}

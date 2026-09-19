import { useCallback, useEffect, useRef, useState } from 'react';
import { Pressable, RefreshControl, ScrollView, StyleSheet } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { BottomTabInset, MaxContentWidth, Spacing } from '@/constants/theme';
import { useAuth } from '@/context/auth';
import { useTheme } from '@/hooks/use-theme';
import { AuthError } from '@/lib/api';

export const GOOD = '#1a7f37';
export const BAD = '#b42318';

export function statusColor(status?: string | null) {
  if (!status) return undefined;
  if (['error', 'failed', 'down', 'sell', 'AVOID', 'Weak', 'Watch', 'Rich'].includes(status)) return BAD;
  if (['done', 'ok', 'up', 'buy', 'sent', 'SUCCESS', 'Strong', 'Positive', 'Attractive/Low'].includes(status)) {
    return GOOD;
  }
  return undefined;
}

export function fmtTime(iso?: string | null) {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

// A "Manual Document Analysis" run has no ticker in its context at all.
export function runLabel(context?: { ticker?: string; kind?: string } | null) {
  if (context?.ticker) return context.ticker;
  if (context?.kind === 'document') return '📄 Document';
  return '—';
}

/** Scrolling page with a title, pull-to-refresh and optional polling. */
export function Screen({
  title,
  subtitle,
  onRefresh,
  pollMs,
  children,
}: {
  title: string;
  subtitle?: string;
  onRefresh?: () => Promise<void> | void;
  pollMs?: number;
  children: React.ReactNode;
}) {
  const insets = useSafeAreaInsets();
  const theme = useTheme();
  const { signOut } = useAuth();
  const [refreshing, setRefreshing] = useState(false);
  const cb = useRef(onRefresh);
  useEffect(() => {
    cb.current = onRefresh;
  });

  const run = useCallback(async () => {
    try {
      await cb.current?.();
    } catch (e) {
      if (e instanceof AuthError) signOut();
    }
  }, [signOut]);

  useEffect(() => {
    run();
    if (!pollMs) return undefined;
    const t = setInterval(run, pollMs);
    return () => clearInterval(t);
  }, [run, pollMs]);

  return (
    <ScrollView
      style={[styles.scroll, { backgroundColor: theme.background }]}
      contentContainerStyle={[
        styles.content,
        { paddingTop: insets.top + Spacing.four, paddingBottom: insets.bottom + BottomTabInset + Spacing.four },
      ]}
      refreshControl={
        onRefresh ? (
          <RefreshControl
            refreshing={refreshing}
            onRefresh={async () => {
              setRefreshing(true);
              await run();
              setRefreshing(false);
            }}
          />
        ) : undefined
      }>
      <ThemedView style={styles.container}>
        <ThemedText type="title" style={styles.title}>
          {title}
        </ThemedText>
        {!!subtitle && (
          <ThemedText type="small" themeColor="textSecondary">
            {subtitle}
          </ThemedText>
        )}
        {children}
      </ThemedView>
    </ScrollView>
  );
}

export function Card({ children, style }: { children: React.ReactNode; style?: object }) {
  return (
    <ThemedView type="backgroundElement" style={[styles.card, style]}>
      {children}
    </ThemedView>
  );
}

export function ErrorCard({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <Card>
      <ThemedText style={{ color: BAD }}>{message}</ThemedText>
    </Card>
  );
}

export function Btn({
  label,
  onPress,
  disabled,
  ghost,
}: {
  label: string;
  onPress: () => void;
  disabled?: boolean;
  ghost?: boolean;
}) {
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      style={({ pressed }) => [
        styles.btn,
        ghost ? styles.btnGhost : styles.btnSolid,
        { opacity: disabled ? 0.5 : pressed ? 0.8 : 1 },
      ]}>
      <ThemedText type="smallBold" style={{ color: ghost ? '#208AEF' : '#fff' }}>
        {label}
      </ThemedText>
    </Pressable>
  );
}

/** Switch between sections of one screen. */
export function Segmented<T extends string>({
  value,
  options,
  onChange,
}: {
  value: T;
  options: { key: T; label: string }[];
  onChange: (k: T) => void;
}) {
  return (
    <ThemedView style={styles.segRow}>
      {options.map((o) => (
        <Pressable key={o.key} onPress={() => onChange(o.key)} style={{ flex: 1 }}>
          <ThemedView type={value === o.key ? 'backgroundSelected' : 'backgroundElement'} style={styles.seg}>
            <ThemedText type="smallBold" themeColor={value === o.key ? 'text' : 'textSecondary'}>
              {o.label}
            </ThemedText>
          </ThemedView>
        </Pressable>
      ))}
    </ThemedView>
  );
}

export function KV({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <ThemedView style={styles.kv}>
      <ThemedText type="small" themeColor="textSecondary" style={{ flex: 1 }}>
        {k}
      </ThemedText>
      <ThemedText type="small" style={{ flex: 1, textAlign: 'right' }}>
        {v}
      </ThemedText>
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  scroll: { flex: 1 },
  content: { flexDirection: 'row', justifyContent: 'center' },
  container: { width: '100%', maxWidth: MaxContentWidth, paddingHorizontal: Spacing.four, gap: Spacing.three },
  title: { fontSize: 32, lineHeight: 38 },
  card: { borderRadius: Spacing.three, padding: Spacing.three, gap: Spacing.one },
  btn: { borderRadius: Spacing.two, paddingVertical: Spacing.two, paddingHorizontal: Spacing.three, alignItems: 'center' },
  btnSolid: { backgroundColor: '#208AEF' },
  btnGhost: { borderWidth: 1, borderColor: '#208AEF' },
  segRow: { flexDirection: 'row', gap: Spacing.two },
  seg: { borderRadius: Spacing.two, paddingVertical: Spacing.two, alignItems: 'center' },
  kv: { flexDirection: 'row', justifyContent: 'space-between', gap: Spacing.two },
});

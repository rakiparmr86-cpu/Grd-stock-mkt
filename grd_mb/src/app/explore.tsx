import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Linking, Platform, Pressable, RefreshControl, ScrollView, StyleSheet } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { AnalysisResult, type ReportPayload } from '@/components/analysis-result';
import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { BottomTabInset, MaxContentWidth, Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { runLabel } from '@/components/ui';
import { listReports, listRuns, reportExcelUrl, reportHtmlUrl } from '@/lib/api';

type Run = {
  id: number;
  trigger: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  context: { ticker?: string; kind?: string; outcome?: string; reason?: string };
};

function fmt(iso: string | null) {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

function outcomeLabel(run: Run) {
  const outcome = run.context?.outcome;
  if (outcome === 'ok') return 'report generated';
  if (outcome === 'no_signal') return 'no signal fired';
  if (outcome === 'skipped') return `skipped (${run.context?.reason ?? 'unknown'})`;
  return run.status;
}

type ReportRef = { id: number; html: boolean; excel: boolean };

type ExpandedState = {
  runId: number;
  loading: boolean;
  ref: ReportRef | null;
  report: ReportPayload | null;
  error: string | null;
};

export default function HistoryScreen() {
  const theme = useTheme();
  const insets = useSafeAreaInsets();
  const [runs, setRuns] = useState<Run[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<ExpandedState | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await listRuns();
      setRuns(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const onRefresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  const toggleRun = async (runId: number) => {
    if (expanded?.runId === runId) {
      setExpanded(null);
      return;
    }
    setExpanded({ runId, loading: true, ref: null, report: null, error: null });
    try {
      const reports = await listReports(runId);
      const first = reports?.[0];
      const payload = first?.payload ?? null;
      const ref: ReportRef | null = first
        ? {
            id: first.id,
            html: Boolean(first.html_path),
            excel: Boolean(
              payload?.fundamentals_report || payload?.ratio_report || payload?.document_analysis,
            ),
          }
        : null;
      setExpanded({ runId, loading: false, ref, report: payload, error: null });
    } catch (err) {
      setExpanded({
        runId, loading: false, ref: null, report: null,
        error: err instanceof Error ? err.message : String(err),
      });
    }
  };

  return (
    <ScrollView
      style={[styles.scrollView, { backgroundColor: theme.background }]}
      contentContainerStyle={[
        styles.contentContainer,
        { paddingTop: insets.top + Spacing.four, paddingBottom: insets.bottom + BottomTabInset + Spacing.four },
      ]}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}>
      <ThemedView style={styles.container}>
        <ThemedText type="title" style={styles.title}>
          History
        </ThemedText>
        <ThemedText type="small" themeColor="textSecondary" style={styles.subtitle}>
          Recent runs from this account, newest first.
        </ThemedText>

        {error && (
          <ThemedView type="backgroundElement" style={styles.errorCard}>
            <ThemedText style={styles.errorText}>{error}</ThemedText>
          </ThemedView>
        )}

        {runs.length === 0 && !error && (
          <ThemedText type="small" themeColor="textSecondary">
            No runs yet — analyze a ticker from the Analyze tab.
          </ThemedText>
        )}

        {runs.map((run) => {
          const isOpen = expanded?.runId === run.id;
          return (
            <ThemedView key={run.id}>
              <Pressable
                onPress={() => toggleRun(run.id)}
                style={({ pressed }) => pressed && styles.pressed}>
                <ThemedView type="backgroundElement" style={styles.row}>
                  <ThemedView style={styles.rowHeader}>
                    <ThemedText type="smallBold">{runLabel(run.context)}</ThemedText>
                    <ThemedText type="small" themeColor="textSecondary">
                      #{run.id}
                    </ThemedText>
                  </ThemedView>
                  <ThemedText type="small" themeColor="textSecondary">
                    {outcomeLabel(run)} · {fmt(run.started_at)}
                  </ThemedText>
                </ThemedView>
              </Pressable>

              {isOpen && (
                <ThemedView style={styles.expanded}>
                  {expanded.loading && <ActivityIndicator />}
                  {expanded.error && <ThemedText style={styles.errorText}>{expanded.error}</ThemedText>}
                  {!expanded.loading && !expanded.error && !expanded.report && (
                    <ThemedText type="small" themeColor="textSecondary">
                      No report was persisted for this run.
                    </ThemedText>
                  )}
                  {expanded.ref && (
                    <ThemedView style={{ flexDirection: 'row', gap: Spacing.two }}>
                      {expanded.ref.html && (
                        <Pressable onPress={() => Linking.openURL(reportHtmlUrl(expanded.ref!.id))}>
                          <ThemedText type="link">View HTML</ThemedText>
                        </Pressable>
                      )}
                      {expanded.ref.excel && (
                        <Pressable onPress={() => Linking.openURL(reportExcelUrl(expanded.ref!.id))}>
                          <ThemedText type="link">Download Excel</ThemedText>
                        </Pressable>
                      )}
                    </ThemedView>
                  )}
                  {expanded.report && <AnalysisResult report={expanded.report} />}
                </ThemedView>
              )}
            </ThemedView>
          );
        })}

        {Platform.OS === 'web' && runs.length > 0 && (
          <ThemedText type="small" themeColor="textSecondary" style={styles.hint}>
            Pull down (or tap the browser refresh) to reload.
          </ThemedText>
        )}
      </ThemedView>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scrollView: {
    flex: 1,
  },
  contentContainer: {
    flexDirection: 'row',
    justifyContent: 'center',
  },
  container: {
    width: '100%',
    maxWidth: MaxContentWidth,
    paddingHorizontal: Spacing.four,
    gap: Spacing.three,
  },
  title: {
    fontSize: 32,
    lineHeight: 38,
  },
  subtitle: {
    marginBottom: Spacing.two,
  },
  expanded: {
    marginTop: Spacing.two,
    marginBottom: Spacing.one,
    paddingLeft: Spacing.two,
  },
  row: {
    borderRadius: Spacing.three,
    padding: Spacing.three,
    gap: Spacing.half,
  },
  rowHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  pressed: {
    opacity: 0.7,
  },
  errorCard: {
    borderRadius: Spacing.three,
    padding: Spacing.three,
  },
  errorText: {
    color: '#d92d20',
  },
  hint: {
    textAlign: 'center',
  },
});

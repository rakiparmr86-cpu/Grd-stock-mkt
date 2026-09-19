import { useState } from 'react';
import {
  ActivityIndicator,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Switch,
  TextInput,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { AnalysisResult, type ReportPayload } from '@/components/analysis-result';
import { PriceChart } from '@/components/price-chart';
import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { useAuth } from '@/context/auth';
import { BottomTabInset, MaxContentWidth, Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { getRun, getTask, listReports, triggerRun } from '@/lib/api';

type State =
  | { phase: 'idle' }
  | { phase: 'running'; note: string }
  | { phase: 'error'; message: string }
  | { phase: 'done'; report: ReportPayload | null; outcome: string | null; reason: string | null };

// The Celery task's own return value only carries {run_id, ticker, status} —
// NOT the report (see app/workers/tasks/analysis.py:analyze_ticker_task).
// The actual report has to be fetched separately by run_id once the task
// finishes, same as the web frontend does.
type TaskStatus = {
  ready: boolean;
  status: string;
  error?: string | null;
  result?: { run_id?: number; status?: string } | null;
};

async function pollTask(taskId: string, onNote: (n: string) => void): Promise<TaskStatus> {
  for (let attempt = 0; attempt < 40; attempt++) {
    const status = await getTask(taskId);
    if (status.ready) return status;
    onNote(`working… (${status.status.toLowerCase()})`);
    await new Promise((r) => setTimeout(r, 1500));
  }
  throw new Error('timed out waiting for the analysis — a worker may not be running');
}

export default function AnalyzeScreen() {
  const { user, signOut } = useAuth();
  const theme = useTheme();
  const insets = useSafeAreaInsets();
  const [ticker, setTicker] = useState('');
  const [forceAgents, setForceAgents] = useState(true);
  const [state, setState] = useState<State>({ phase: 'idle' });

  const submit = async () => {
    const t = ticker.trim().toUpperCase();
    if (!t) return;
    setState({ phase: 'running', note: 'queuing…' });
    try {
      const res = await triggerRun({ ticker: t, async_: true, force_agents: forceAgents });
      const finalStatus = await pollTask(res.task_id, (note) => setState({ phase: 'running', note }));
      if (finalStatus.status !== 'SUCCESS') {
        setState({ phase: 'error', message: finalStatus.error || 'analysis failed' });
        return;
      }
      const runId = finalStatus.result?.run_id;
      if (runId == null) {
        setState({ phase: 'error', message: 'analysis finished but no run id was returned' });
        return;
      }
      // the run's own record carries *why* (context.outcome/reason) — see
      // app/api/v1/runs.py / app/workers/tasks/analysis.py
      const run = await getRun(runId);
      const outcome: string | null = run.context?.outcome ?? null;
      if (outcome === 'ok') {
        const reports = await listReports(runId);
        setState({ phase: 'done', report: reports?.[0]?.payload ?? null, outcome, reason: null });
      } else {
        setState({
          phase: 'done',
          report: null,
          outcome: outcome ?? run.status ?? 'unknown',
          reason: run.context?.reason ?? null,
        });
      }
    } catch (err) {
      setState({ phase: 'error', message: err instanceof Error ? err.message : String(err) });
    }
  };

  const busy = state.phase === 'running';

  return (
    <ScrollView
      style={styles.scrollView}
      contentContainerStyle={[
        styles.contentContainer,
        { paddingTop: insets.top + Spacing.four, paddingBottom: insets.bottom + BottomTabInset + Spacing.four },
      ]}>
      <ThemedView style={styles.container}>
        <ThemedView style={styles.headerRow}>
          <ThemedView>
            <ThemedText type="title" style={styles.title}>
              Analyze
            </ThemedText>
            <ThemedText type="small" themeColor="textSecondary">
              {user?.email}
            </ThemedText>
          </ThemedView>
          <Pressable onPress={signOut} hitSlop={8}>
            <ThemedText type="link">Sign out</ThemedText>
          </Pressable>
        </ThemedView>

        <ThemedText type="smallBold" themeColor="textSecondary">
          1 · ANALYSIS RUN
        </ThemedText>
        <ThemedView type="backgroundElement" style={styles.form}>
          <ThemedText type="smallBold" style={styles.label}>
            Company / ticker
          </ThemedText>
          <TextInput
            style={[styles.input, { color: theme.text, borderColor: theme.backgroundSelected }]}
            value={ticker}
            onChangeText={setTicker}
            placeholder="e.g. RELIANCE"
            placeholderTextColor={theme.textSecondary}
            autoCapitalize="characters"
            autoCorrect={false}
            returnKeyType="go"
            onSubmitEditing={submit}
            editable={!busy}
          />

          <ThemedView style={styles.toggleRow}>
            <ThemedText type="small">Always run full analysis</ThemedText>
            <Switch value={forceAgents} onValueChange={setForceAgents} disabled={busy} />
          </ThemedView>

          <Pressable
            onPress={submit}
            disabled={busy || !ticker.trim()}
            style={({ pressed }) => [
              styles.button,
              { opacity: busy || !ticker.trim() ? 0.5 : pressed ? 0.8 : 1 },
            ]}>
            {busy ? <ActivityIndicator color="#fff" /> : <ThemedText style={styles.buttonText}>Analyze</ThemedText>}
          </Pressable>

          {state.phase === 'running' && (
            <ThemedText type="small" themeColor="textSecondary" style={styles.note}>
              {state.note}
            </ThemedText>
          )}
        </ThemedView>

        {state.phase === 'error' && (
          <ThemedView type="backgroundElement" style={styles.errorCard}>
            <ThemedText style={styles.errorText}>{state.message}</ThemedText>
          </ThemedView>
        )}

        {state.phase === 'done' && state.report && <AnalysisResult report={state.report} />}

        {state.phase === 'done' && !state.report && (
          <ThemedView type="backgroundElement" style={styles.errorCard}>
            <ThemedText type="smallBold">No report for this run</ThemedText>
            <ThemedText type="small" themeColor="textSecondary" style={styles.note}>
              {state.outcome === 'no_signal'
                ? 'No active rule matched the latest data — this is expected, not an error. Toggle "always run full analysis" on to force a full report anyway.'
                : state.outcome === 'skipped'
                  ? `Skipped: ${state.reason === 'insufficient_data' ? 'not enough price history for this ticker' : state.reason || 'unknown reason'}.`
                  : state.outcome === 'ok'
                    ? 'The run completed but no report was found for it — try again.'
                    : `Outcome: ${state.outcome}`}
            </ThemedText>
          </ThemedView>
        )}

        <ThemedText type="smallBold" themeColor="textSecondary">
          2 · GRAPH &amp; PREDICTION
        </ThemedText>
        <PriceChart />

        {Platform.OS === 'web' && state.phase === 'idle' && (
          <ThemedText type="small" themeColor="textSecondary" style={styles.hint}>
            Enter a ticker already known to the platform (e.g. one with price history ingested) and
            tap Analyze.
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
    gap: Spacing.four,
  },
  headerRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
  },
  title: {
    fontSize: 32,
    lineHeight: 38,
  },
  form: {
    borderRadius: Spacing.four,
    padding: Spacing.four,
    gap: Spacing.two,
  },
  label: {
    marginBottom: Spacing.one,
  },
  input: {
    borderWidth: 1,
    borderRadius: Spacing.two,
    paddingHorizontal: Spacing.three,
    paddingVertical: Spacing.two,
    fontSize: 16,
  },
  toggleRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: Spacing.two,
  },
  button: {
    backgroundColor: '#208AEF',
    borderRadius: Spacing.two,
    paddingVertical: Spacing.three,
    alignItems: 'center',
    justifyContent: 'center',
  },
  buttonText: {
    color: '#fff',
    fontWeight: '600',
  },
  note: {
    marginTop: Spacing.one,
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

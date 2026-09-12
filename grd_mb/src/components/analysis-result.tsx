import { StyleSheet } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { Spacing } from '@/constants/theme';

type Forecast = Record<
  string,
  {
    cagr_pct: number | null;
    trend_direction: string;
    forecast_next: number;
    confidence_interval_95: { low: number; high: number };
  }
>;

export type ReportPayload = {
  title: string;
  recommendation: { action: string; confidence: number; thesis: string };
  indicators: Record<string, number>;
  forecast: Forecast | null;
  sections: { heading: string; body: string; bullets: string[] }[];
};

const ACTION_COLOR: Record<string, string> = {
  BUY: '#1a7f37',
  HOLD: '#a15c00',
  AVOID: '#b42318',
};

function fmt(n: number) {
  return Number.isFinite(n) ? n.toLocaleString(undefined, { maximumFractionDigits: 2 }) : '—';
}

export function AnalysisResult({ report }: { report: ReportPayload }) {
  const actionColor = ACTION_COLOR[report.recommendation?.action] ?? '#60646C';

  return (
    <ThemedView style={styles.wrap}>
      <ThemedView style={styles.headerRow}>
        <ThemedView style={[styles.actionBadge, { backgroundColor: actionColor }]}>
          <ThemedText style={styles.actionText}>{report.recommendation?.action ?? '—'}</ThemedText>
        </ThemedView>
        <ThemedText themeColor="textSecondary" type="small">
          confidence {Math.round((report.recommendation?.confidence ?? 0) * 100)}%
        </ThemedText>
      </ThemedView>

      {!!report.recommendation?.thesis && (
        <ThemedText style={styles.thesis}>{report.recommendation.thesis}</ThemedText>
      )}

      {!!report.indicators && Object.keys(report.indicators).length > 0 && (
        <ThemedView type="backgroundElement" style={styles.card}>
          <ThemedText type="smallBold" style={styles.cardTitle}>
            Key indicators
          </ThemedText>
          <ThemedView style={styles.indicatorGrid}>
            {Object.entries(report.indicators)
              .slice(0, 8)
              .map(([k, v]) => (
                <ThemedView key={k} style={styles.indicatorCell}>
                  <ThemedText type="small" themeColor="textSecondary">
                    {k}
                  </ThemedText>
                  <ThemedText type="smallBold">{fmt(v)}</ThemedText>
                </ThemedView>
              ))}
          </ThemedView>
        </ThemedView>
      )}

      {!!report.forecast && (
        <ThemedView type="backgroundElement" style={styles.card}>
          <ThemedText type="smallBold" style={styles.cardTitle}>
            Fundamentals forecast
          </ThemedText>
          {Object.entries(report.forecast).map(([metric, f]) => (
            <ThemedView key={metric} style={styles.forecastRow}>
              <ThemedText type="small" style={styles.forecastMetric}>
                {metric.replace('_', ' ')}
              </ThemedText>
              <ThemedText type="small" themeColor="textSecondary">
                {f.cagr_pct != null ? `${f.cagr_pct.toFixed(1)}% CAGR, ` : ''}
                trending {f.trend_direction} · next: {fmt(f.forecast_next)} (
                {fmt(f.confidence_interval_95.low)}–{fmt(f.confidence_interval_95.high)})
              </ThemedText>
            </ThemedView>
          ))}
        </ThemedView>
      )}

      {report.sections?.map((s) => (
        <ThemedView key={s.heading} type="backgroundElement" style={styles.card}>
          <ThemedText type="smallBold" style={styles.cardTitle}>
            {s.heading}
          </ThemedText>
          {!!s.body && <ThemedText type="small">{s.body}</ThemedText>}
          {s.bullets?.map((b, i) => (
            <ThemedText key={i} type="small" themeColor="textSecondary" style={styles.bullet}>
              • {b}
            </ThemedText>
          ))}
        </ThemedView>
      ))}
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  wrap: {
    gap: Spacing.three,
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.two,
  },
  actionBadge: {
    paddingHorizontal: Spacing.three,
    paddingVertical: Spacing.one,
    borderRadius: Spacing.two,
  },
  actionText: {
    color: '#fff',
    fontWeight: '700',
  },
  thesis: {
    lineHeight: 22,
  },
  card: {
    borderRadius: Spacing.three,
    padding: Spacing.three,
    gap: Spacing.one,
  },
  cardTitle: {
    marginBottom: Spacing.one,
  },
  indicatorGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: Spacing.three,
  },
  indicatorCell: {
    minWidth: 90,
  },
  forecastRow: {
    marginBottom: Spacing.one,
  },
  forecastMetric: {
    textTransform: 'capitalize',
    fontWeight: '700',
  },
  bullet: {
    marginTop: Spacing.half,
  },
});

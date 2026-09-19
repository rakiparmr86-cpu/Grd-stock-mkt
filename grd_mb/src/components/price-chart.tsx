import { useCallback, useEffect, useMemo, useState } from 'react';
import { type LayoutChangeEvent, Linking, Pressable, ScrollView, StyleSheet, Switch, useWindowDimensions } from 'react-native';
import Svg, { G, Line, Polygon, Polyline, Rect, Text as SvgText } from 'react-native-svg';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { BAD, Btn, Card, ErrorCard, GOOD, Segmented } from '@/components/ui';
import { MaxContentWidth, Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import {
  type Forecast,
  type ForecastPoint,
  forecastExportUrl,
  getForecast,
  getOhlcv,
  listPriceTickers,
} from '@/lib/api';

type Bar = { ts: string; open: number; high: number; low: number; close: number; volume: number };
type TickerInfo = { ticker: string; bars: number };

const AHEAD = 20;
const H = 240;
const PAD = { l: 44, r: 6, t: 6, b: 18 };
const VOL_H = 34;
const PRICE_BOTTOM = H - PAD.b - VOL_H - 4;

function fmt(n: number) {
  return Number.isFinite(n) ? n.toLocaleString(undefined, { maximumFractionDigits: 2 }) : '—';
}

function fmtDay(ts: string) {
  const d = new Date(ts);
  return Number.isNaN(d.getTime()) ? ts : d.toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
}

function sma(closes: number[], n: number): (number | null)[] {
  return closes.map((_, i) => {
    if (i < n - 1) return null;
    let s = 0;
    for (let k = i - n + 1; k <= i; k++) s += closes[k];
    return s / n;
  });
}

function Chart({
  bars,
  width,
  mode,
  showSma,
  forecast,
}: {
  bars: Bar[];
  width: number;
  mode: 'candles' | 'line';
  showSma: boolean;
  forecast: ForecastPoint[];
}) {
  const theme = useTheme();
  const [hover, setHover] = useState<number | null>(null);
  const fc = forecast;
  const total = bars.length + fc.length;

  const geo = useMemo(() => {
    let lo = Math.min(...bars.map((b) => b.low), ...fc.map((f) => f.low));
    let hi = Math.max(...bars.map((b) => b.high), ...fc.map((f) => f.high));
    const pad = (hi - lo) * 0.06 || 1;
    lo -= pad;
    hi += pad;
    const plotW = width - PAD.l - PAD.r;
    const step = plotW / total;
    return {
      lo,
      hi,
      step,
      x: (i: number) => PAD.l + step * i + step / 2,
      y: (v: number) => PAD.t + ((hi - v) / (hi - lo)) * (PRICE_BOTTOM - PAD.t),
      maxVol: Math.max(...bars.map((b) => b.volume), 1),
    };
  }, [bars, fc, total, width]);

  const sma20 = useMemo(() => sma(bars.map((b) => b.close), 20), [bars]);
  const yTicks = Array.from({ length: 4 }, (_, i) => geo.lo + ((geo.hi - geo.lo) * i) / 3);
  const allTs = [...bars.map((b) => b.ts), ...fc.map((f) => f.ts)];
  const xTicks = [0, 0.5, 1].map((f) => Math.round(f * (total - 1)));
  const candleW = Math.max(1, geo.step * 0.62);
  const axis = theme.textSecondary;

  const pick = (locationX: number) => {
    const idx = Math.floor((locationX - PAD.l) / geo.step);
    setHover(idx >= 0 && idx < total ? idx : null);
  };

  const hoverFc = hover != null && hover >= bars.length ? fc[hover - bars.length] : null;
  const shown = hover != null && !hoverFc ? bars[hover] : bars[bars.length - 1];
  const prev = hover != null && !hoverFc ? bars[hover - 1] : bars[bars.length - 2];
  const change = prev ? ((shown.close - prev.close) / prev.close) * 100 : null;

  const linePts = bars.map((b, i) => `${geo.x(i)},${geo.y(b.close)}`).join(' ');
  const smaPts = sma20
    .map((v, i) => (v == null ? null : `${geo.x(i)},${geo.y(v)}`))
    .filter(Boolean)
    .join(' ');

  return (
    <ThemedView>
      {hoverFc ? (
        <ThemedText type="small">
          {fmtDay(hoverFc.ts)} · forecast {fmt(hoverFc.value)} (95%: {fmt(hoverFc.low)}–{fmt(hoverFc.high)})
        </ThemedText>
      ) : (
      <ThemedText type="small">
        {fmtDay(shown.ts)} · O {fmt(shown.open)} H {fmt(shown.high)} L {fmt(shown.low)} C {fmt(shown.close)}
        {change != null && (
          <ThemedText type="small" style={{ color: change >= 0 ? GOOD : BAD }}>
            {'  '}
            {change >= 0 ? '+' : ''}
            {change.toFixed(2)}%
          </ThemedText>
        )}
      </ThemedText>
      )}
      <ThemedView
        onTouchStart={(e) => pick(e.nativeEvent.locationX)}
        onTouchMove={(e) => pick(e.nativeEvent.locationX)}
        onTouchEnd={() => setHover(null)}>
        <Svg width={width} height={H}>
          {yTicks.map((t) => (
            <Line key={`g${t}`} x1={PAD.l} x2={width - PAD.r} y1={geo.y(t)} y2={geo.y(t)} stroke={axis} strokeOpacity={0.2} />
          ))}
          {yTicks.map((t) => (
            <SvgText key={`t${t}`} x={PAD.l - 4} y={geo.y(t) + 3} fontSize={10} fill={axis} textAnchor="end">
              {fmt(t)}
            </SvgText>
          ))}
          {xTicks.map((i) => (
            <SvgText key={`x${i}`} x={geo.x(i)} y={H - 4} fontSize={10} fill={axis} textAnchor="middle">
              {fmtDay(allTs[i])}
            </SvgText>
          ))}
          {bars.map((b, i) => {
            const h = (b.volume / geo.maxVol) * VOL_H;
            return (
              <Rect
                key={`v${i}`}
                x={geo.x(i) - candleW / 2}
                y={H - PAD.b - h}
                width={candleW}
                height={h}
                fill={b.close >= b.open ? GOOD : BAD}
                opacity={0.35}
              />
            );
          })}
          {mode === 'line' ? (
            <>
              <Polygon
                points={`${geo.x(0)},${PRICE_BOTTOM} ${linePts} ${geo.x(bars.length - 1)},${PRICE_BOTTOM}`}
                fill="#208AEF"
                opacity={0.14}
              />
              <Polyline points={linePts} fill="none" stroke="#208AEF" strokeWidth={2} />
            </>
          ) : (
            bars.map((b, i) => {
              const color = b.close >= b.open ? GOOD : BAD;
              const top = geo.y(Math.max(b.open, b.close));
              const bodyH = Math.max(1, Math.abs(geo.y(b.open) - geo.y(b.close)));
              return (
                <G key={i}>
                  <Line x1={geo.x(i)} x2={geo.x(i)} y1={geo.y(b.high)} y2={geo.y(b.low)} stroke={color} strokeWidth={1} />
                  <Rect x={geo.x(i) - candleW / 2} y={top} width={candleW} height={bodyH} fill={color} />
                </G>
              );
            })
          )}
          {fc.length > 0 && (
            <>
              <Polygon
                points={[
                  ...fc.map((f, j) => `${geo.x(bars.length + j)},${geo.y(f.high)}`),
                  ...[...fc].reverse().map((f, j) => `${geo.x(total - 1 - j)},${geo.y(f.low)}`),
                ].join(' ')}
                fill="#d97706"
                opacity={0.18}
              />
              <Polyline
                points={[
                  `${geo.x(bars.length - 1)},${geo.y(bars[bars.length - 1].close)}`,
                  ...fc.map((f, j) => `${geo.x(bars.length + j)},${geo.y(f.value)}`),
                ].join(' ')}
                fill="none"
                stroke="#d97706"
                strokeWidth={2}
                strokeDasharray="6 4"
              />
            </>
          )}
          {showSma && !!smaPts && <Polyline points={smaPts} fill="none" stroke="#7c3aed" strokeWidth={1.5} />}
          {hover != null && (
            <Line x1={geo.x(hover)} x2={geo.x(hover)} y1={PAD.t} y2={H - PAD.b} stroke={axis} strokeDasharray="3 3" />
          )}
        </Svg>
      </ThemedView>
    </ThemedView>
  );
}

export function PriceChart() {
  const [tickers, setTickers] = useState<TickerInfo[]>([]);
  const [ticker, setTicker] = useState('');
  const [limit, setLimit] = useState<'60' | '120' | '250'>('120');
  const [mode, setMode] = useState<'candles' | 'line'>('candles');
  const [showSma, setShowSma] = useState(true);
  const [showForecast, setShowForecast] = useState(true);
  const [forecast, setForecast] = useState<Forecast | null>(null);
  const [fcNote, setFcNote] = useState<string | null>(null);
  const [bars, setBars] = useState<Bar[]>([]);
  const [measured, setMeasured] = useState(0);
  const win = useWindowDimensions();
  // best guess until onLayout reports the real width (screen minus page + card padding)
  const guess = Math.min(win.width, MaxContentWidth) - 2 * Spacing.four - 2 * Spacing.three;
  const width = measured || Math.max(200, Math.floor(guess));
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    listPriceTickers()
      .then((list: TickerInfo[]) => {
        if (!alive) return;
        setTickers(list);
        setTicker((cur) => cur || list[0]?.ticker || '');
      })
      .catch((e: unknown) => alive && setErr(e instanceof Error ? e.message : String(e)));
    return () => {
      alive = false;
    };
  }, []);

  const loadBars = useCallback(async () => {
    if (!ticker) return;
    try {
      const res = await getOhlcv(ticker, Number(limit));
      setBars(res.bars);
      setErr(null);
    } catch (e) {
      setBars([]);
      setErr(e instanceof Error ? e.message : String(e));
    }
  }, [ticker, limit]);

  useEffect(() => {
    loadBars();
  }, [loadBars]);

  useEffect(() => {
    let alive = true;
    if (!ticker || !showForecast) return undefined;
    getForecast(ticker, Number(limit), AHEAD)
      .then((f) => {
        if (!alive) return;
        setForecast(f);
        setFcNote(null);
      })
      .catch((e: unknown) => {
        if (!alive) return;
        setForecast(null);
        setFcNote(e instanceof Error ? e.message : String(e));
      });
    return () => {
      alive = false;
    };
  }, [ticker, limit, showForecast]);

  const openExport = async (kind: 'html' | 'excel') => {
    Linking.openURL(await forecastExportUrl(ticker, kind, Number(limit), AHEAD));
  };

  const onLayout = (e: LayoutChangeEvent) => setMeasured(Math.floor(e.nativeEvent.layout.width));

  return (
    <Card style={{ gap: Spacing.two }}>
      <ThemedText type="smallBold">Price chart</ThemedText>
      {tickers.length === 0 && !err && (
        <ThemedText type="small" themeColor="textSecondary">
          No price data yet. Upload a price CSV (rows, ohlcv) from the Uploads tab.
        </ThemedText>
      )}
      {tickers.length > 0 && (
        <>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: Spacing.two }}>
            {tickers.map((t) => (
              <Pressable key={t.ticker} onPress={() => setTicker(t.ticker)}>
                <ThemedView type={ticker === t.ticker ? 'backgroundSelected' : 'backgroundElement'} style={styles.chip}>
                  <ThemedText type="smallBold">{t.ticker}</ThemedText>
                </ThemedView>
              </Pressable>
            ))}
          </ScrollView>
          <Segmented
            value={limit}
            options={[
              { key: '60', label: '60' },
              { key: '120', label: '120' },
              { key: '250', label: '250' },
            ]}
            onChange={setLimit}
          />
          <Segmented
            value={mode}
            options={[
              { key: 'candles', label: 'Candles' },
              { key: 'line', label: 'Line' },
            ]}
            onChange={setMode}
          />
          <ThemedView style={styles.smaRow}>
            <ThemedText type="small">20-bar average</ThemedText>
            <Switch value={showSma} onValueChange={setShowSma} />
          </ThemedView>
          <ThemedView style={styles.smaRow}>
            <ThemedText type="small">Show {AHEAD}-day forecast</ThemedText>
            <Switch value={showForecast} onValueChange={setShowForecast} />
          </ThemedView>
          <ThemedView onLayout={onLayout}>
            {width > 0 && bars.length > 1 && (
              <Chart bars={bars} width={width} mode={mode} showSma={showSma} forecast={showForecast ? (forecast?.forecast ?? []) : []} />
            )}
          </ThemedView>
          {showForecast && !!fcNote && (
            <ThemedText type="small" themeColor="textSecondary">
              Forecast not shown: {fcNote}
            </ThemedText>
          )}
          {showForecast && !!forecast && (
            <ThemedText type="small" themeColor="textSecondary">
              {forecast.method.toUpperCase()} forecast: {fmt(forecast.last_close)} → {fmt(forecast.forecast_end)} in{' '}
              {forecast.ahead} bars ({(forecast.forecast_change_pct ?? 0) >= 0 ? '+' : ''}
              {(forecast.forecast_change_pct ?? 0).toFixed(1)}%). 95% interval shaded; a trend extrapolation, not advice.
            </ThemedText>
          )}
          <ThemedView style={{ flexDirection: 'row', gap: Spacing.two }}>
            <Btn ghost label="Prediction HTML" onPress={() => openExport('html')} />
            <Btn ghost label="Prediction Excel" onPress={() => openExport('excel')} />
          </ThemedView>
        </>
      )}
      <ErrorCard message={err} />
    </Card>
  );
}

const styles = StyleSheet.create({
  chip: { borderRadius: Spacing.two, paddingHorizontal: Spacing.three, paddingVertical: Spacing.one },
  smaRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
});

import * as DocumentPicker from 'expo-document-picker';
import { useCallback, useState } from 'react';
import { TextInput } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { Btn, Card, ErrorCard, KV, Screen, Segmented, fmtTime, statusColor } from '@/components/ui';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import {
  type PickedFile,
  type UploadOptions,
  listSources,
  runSource,
  triggerDocumentRun,
  uploadFiles,
  uploadsTracker,
} from '@/lib/api';

type Item = {
  id: number;
  source_name: string;
  ticker: string | null;
  status: string;
  finished_at: string | null;
  started_at: string | null;
  stats: Record<string, unknown> | null;
  error: string | null;
  analyzed: boolean;
};
type Tracker = { total: number; analyzed: number; pending: number; items: Item[] };
type Source = {
  id: number;
  name: string;
  connector: string;
  is_active: boolean;
  schedule_cron: string | null;
  last_status: string | null;
  last_run_at: string | null;
};

const POLL_MS = 5000;

function Chips<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: { key: T; label: string }[];
  onChange: (v: T) => void;
}) {
  return (
    <ThemedView style={{ gap: Spacing.one }}>
      <ThemedText type="small" themeColor="textSecondary">
        {label}
      </ThemedText>
      <Segmented value={value} options={options} onChange={onChange} />
    </ThemedView>
  );
}

function UploadForm({ onDone }: { onDone: () => void }) {
  const theme = useTheme();
  const [files, setFiles] = useState<PickedFile[]>([]);
  const [mode, setMode] = useState<UploadOptions['mode']>('ingest_once');
  const [excelMode, setExcelMode] = useState<UploadOptions['excelMode']>('docs');
  const [rowKind, setRowKind] = useState<UploadOptions['rowKind']>('ohlcv');
  const [ticker, setTicker] = useState('');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const tickerRequired = excelMode === 'rows';

  const pick = async () => {
    const res = await DocumentPicker.getDocumentAsync({ multiple: true, copyToCacheDirectory: true });
    if (res.canceled) return;
    setFiles(
      res.assets.map((a) => ({ uri: a.uri, name: a.name, mimeType: a.mimeType, file: a.file })),
    );
  };

  const submit = async () => {
    setBusy(true);
    setErr(null);
    setMsg(null);
    try {
      const res = await uploadFiles(files, { mode, excelMode, rowKind, ticker });
      const failed = (res.items ?? []).filter((i: { error?: string }) => i.error);
      setMsg(`Queued ${(res.items ?? []).length - failed.length} file(s) — watch the list below.`);
      if (failed.length) setErr(failed.map((i: { filename: string; error: string }) => `${i.filename}: ${i.error}`).join('\n'));
      setFiles([]);
      setTimeout(onDone, 800);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card style={{ gap: Spacing.two }}>
      <ThemedText type="smallBold">Upload files</ThemedText>
      <ThemedText type="small" themeColor="textSecondary">
        CSV / Excel / PDF / images. Uploading only stores the data; analysis is a separate step.
      </ThemedText>
      <Btn ghost label={files.length ? `${files.length} file(s) selected — change` : 'Choose files'} onPress={pick} />
      {files.map((f) => (
        <ThemedText key={f.uri} type="small" themeColor="textSecondary">
          • {f.name}
        </ThemedText>
      ))}
      <Chips
        label="Mode"
        value={mode}
        options={[
          { key: 'ingest_once', label: 'Ingest once' },
          { key: 'save_source', label: 'Save source' },
        ]}
        onChange={setMode}
      />
      <Chips
        label="Excel as"
        value={excelMode}
        options={[
          { key: 'docs', label: 'Documents' },
          { key: 'rows', label: 'Rows' },
        ]}
        onChange={setExcelMode}
      />
      {excelMode === 'rows' && (
        <Chips
          label="Row kind"
          value={rowKind}
          options={[
            { key: 'ohlcv', label: 'Prices (ohlcv)' },
            { key: 'fundamental', label: 'Fundamentals' },
          ]}
          onChange={setRowKind}
        />
      )}
      <ThemedText type="small" themeColor="textSecondary">
        Ticker{tickerRequired ? ' (required for rows)' : ' (optional)'}
      </ThemedText>
      <TextInput
        value={ticker}
        onChangeText={setTicker}
        autoCapitalize="characters"
        autoCorrect={false}
        placeholder="e.g. ADITYABIRLA"
        placeholderTextColor={theme.textSecondary}
        style={{
          borderWidth: 1,
          borderColor: theme.backgroundSelected,
          color: theme.text,
          borderRadius: Spacing.two,
          paddingHorizontal: Spacing.three,
          paddingVertical: Spacing.two,
          fontSize: 16,
        }}
      />
      <Btn
        label={busy ? 'Uploading…' : 'Upload'}
        onPress={submit}
        disabled={busy || files.length === 0 || (tickerRequired && !ticker.trim())}
      />
      {!!msg && <ThemedText type="small" style={{ color: '#1a7f37' }}>{msg}</ThemedText>}
      <ErrorCard message={err} />
    </Card>
  );
}

function UploadsList() {
  const [data, setData] = useState<Tracker | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  const load = useCallback(async () => {
    try {
      setData(await uploadsTracker(100));
      setErr(null);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      throw e;
    }
  }, []);

  const analyze = async (id: number) => {
    setBusyId(id);
    try {
      await triggerDocumentRun(id);
      setTimeout(() => load().catch(() => undefined), 1200);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <Screen
      title="Uploads"
      subtitle={data ? `${data.total} tracked · ${data.analyzed} analyzed · ${data.pending} not yet` : 'Loading…'}
      onRefresh={load}
      pollMs={POLL_MS}>
      <UploadForm onDone={() => load().catch(() => undefined)} />
      <ErrorCard message={err} />
      {data?.items.length === 0 && (
        <ThemedText type="small" themeColor="textSecondary">
          No uploads yet.
        </ThemedText>
      )}
      {data?.items.map((it) => {
        const hasText = Number((it.stats as { chunks?: number } | null)?.chunks ?? 0) > 0;
        return (
          <Card key={it.id}>
            <ThemedText type="smallBold">{it.source_name}</ThemedText>
            <KV k="When" v={fmtTime(it.finished_at || it.started_at)} />
            <KV k="Ticker" v={it.ticker || '—'} />
            <KV
              k="Status"
              v={<ThemedText type="small" style={{ color: statusColor(it.status) }}>{it.finished_at ? it.status : 'running…'}</ThemedText>}
            />
            <KV k="Analyzed" v={it.analyzed ? 'yes' : 'not yet'} />
            {!!it.error && <ThemedText type="small" style={{ color: '#b42318' }}>{it.error}</ThemedText>}
            {hasText ? (
              <Btn
                ghost
                label={busyId === it.id ? 'Queuing…' : 'Analyze document'}
                onPress={() => analyze(it.id)}
                disabled={busyId === it.id}
              />
            ) : (
              <ThemedText type="small" themeColor="textSecondary">
                No document text (rows upload) — analyze it from the Analyze tab by ticker.
              </ThemedText>
            )}
          </Card>
        );
      })}
    </Screen>
  );
}

function SourcesList() {
  const [rows, setRows] = useState<Source[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setRows(await listSources());
      setErr(null);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      throw e;
    }
  }, []);

  const run = async (id: number) => {
    setNote(null);
    try {
      await runSource(id);
      setNote('Run queued.');
      setTimeout(() => load().catch(() => undefined), 1500);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <Screen title="Saved sources" subtitle="Reusable inputs you saved with mode “Save source”." onRefresh={load}>
      <ErrorCard message={err} />
      {!!note && <ThemedText type="small" style={{ color: '#1a7f37' }}>{note}</ThemedText>}
      {rows.length === 0 && (
        <ThemedText type="small" themeColor="textSecondary">
          No saved sources.
        </ThemedText>
      )}
      {rows.map((s) => (
        <Card key={s.id}>
          <ThemedText type="smallBold">{s.name}</ThemedText>
          <KV k="Connector" v={s.connector} />
          <KV k="Schedule" v={s.schedule_cron || '—'} />
          <KV
            k="Last run"
            v={`${s.last_status ?? '—'} · ${fmtTime(s.last_run_at)}`}
          />
          <Btn ghost label="Run now" onPress={() => run(s.id)} />
        </Card>
      ))}
    </Screen>
  );
}

export default function UploadsScreen() {
  const [view, setView] = useState<'uploads' | 'sources'>('uploads');
  return (
    <ThemedView style={{ flex: 1 }}>
      <ThemedView style={{ paddingHorizontal: Spacing.four, paddingTop: Spacing.six, paddingBottom: 0 }}>
        <Segmented
          value={view}
          options={[
            { key: 'uploads', label: 'Uploads' },
            { key: 'sources', label: 'Saved sources' },
          ]}
          onChange={setView}
        />
      </ThemedView>
      {view === 'uploads' ? <UploadsList /> : <SourcesList />}
    </ThemedView>
  );
}

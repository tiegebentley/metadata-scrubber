"use client";

import { ChangeEvent, DragEvent, ReactNode, useEffect, useMemo, useRef, useState } from "react";
import {
  Check, Copy, Download, FolderOpen, Gauge, History, Info, Lock, Menu, RefreshCw,
  ScanSearch, Scissors, Settings, ShieldCheck, Upload, WandSparkles, X, Layers,
} from "lucide-react";

/* ---------- types ---------- */

type Tool = "scrub" | "convert" | "inspect" | "editor" | "generator" | "export" | "duplicates" | "history" | "settings";
type Health = "checking" | "online" | "offline";

type DownloadResult = { download_url: string; output_file: string; inspection?: Inspection; preset?: string };
type ScrubResult = {
  download_url: string;
  diff: { source_file: string; scrubbed_file: string; replacement_metadata: { make: string; model: string; timestamp: string; gps: null | string }; note: string };
};
type Inspection = {
  filename: string; size: number; format_name: string | null; duration: number | null; bit_rate: number | null;
  format_tags: Record<string, string>;
  streams: { index: number; type: string; codec: string; width?: number; height?: number; frame_rate?: string; sample_rate?: string; channels?: number; tags: Record<string, string> }[];
};
type Preset = { width: number; height: number; label: string };
type DupeMatch = { a: string; b: string; similarity: number; kind: "exact" | "near" };
type HistoryItem = { id: string; tool: string; name: string; size: number; completedAt: string; output: string };

const MAX = 500 * 1024 * 1024;
const ACCEPT = ".jpg,.jpeg,.tif,.tiff,.png,.webp,.heic,.mp4,.mov,.m4v,.mkv,.webm,.gif";
const ACCEPT_IMAGES = ".jpg,.jpeg,.png,.webp,.tif,.tiff,.gif";

const tools: { id: Tool; label: string; icon: typeof ShieldCheck }[] = [
  { id: "scrub", label: "Scrub", icon: ShieldCheck },
  { id: "inspect", label: "Inspector", icon: ScanSearch },
  { id: "convert", label: "Convert", icon: RefreshCw },
  { id: "editor", label: "Editor", icon: Scissors },
  { id: "generator", label: "Generator", icon: WandSparkles },
  { id: "export", label: "Export", icon: Layers },
  { id: "duplicates", label: "Duplicates", icon: Copy },
];

/* ---------- API helper ---------- */

async function api<T>(path: string, body: FormData, headers: Record<string, string> = {}): Promise<T> {
  const r = await fetch(`/backend${path}`, { method: "POST", body, headers });
  const text = await r.text();
  let json: any = null;
  try { json = JSON.parse(text); } catch { /* non-JSON error body */ }
  if (!r.ok) {
    const detail = json?.detail ?? text ?? "Request failed";
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return json as T;
}

function bytes(n: number) { return n < 1048576 ? (n / 1024).toFixed(1) + " KB" : (n / 1048576).toFixed(2) + " MB"; }
function secs(n: number | null | undefined) { return n == null ? "—" : `${n.toFixed(2)} s`; }

/* ---------- root ---------- */

export default function Home() {
  const picker = useRef<HTMLInputElement>(null);
  const multiPicker = useRef<HTMLInputElement>(null);
  const [tool, setTool] = useState<Tool>("scrub");
  const [file, setFile] = useState<File | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [owned, setOwned] = useState(false);
  const [health, setHealth] = useState<Health>("checking");
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [mobile, setMobile] = useState(false);

  useEffect(() => {
    try { setHistory(JSON.parse(localStorage.getItem("scrubmeta-history") || "[]")); } catch { /* ignore */ }
    void ping();
  }, []);

  async function ping() {
    setHealth("checking");
    try { setHealth((await fetch("/backend/healthz", { cache: "no-store" })).ok ? "online" : "offline"); }
    catch { setHealth("offline"); }
  }

  function pick(f: File | null) {
    if (f && f.size > MAX) { alert("Maximum file size is 500 MB."); return; }
    setFile(f);
  }
  function onInput(e: ChangeEvent<HTMLInputElement>) { pick(e.target.files?.[0] || null); e.target.value = ""; }
  function onMultiInput(e: ChangeEvent<HTMLInputElement>) { setFiles(Array.from(e.target.files || []).slice(0, 100)); e.target.value = ""; }
  function drop(e: DragEvent<HTMLElement>) {
    e.preventDefault();
    if (tool === "duplicates") setFiles(Array.from(e.dataTransfer.files || []).slice(0, 100));
    else pick(e.dataTransfer.files?.[0] || null);
  }
  function record(item: Omit<HistoryItem, "id" | "completedAt">) {
    setHistory((prev) => {
      const next = [{ ...item, id: crypto.randomUUID(), completedAt: new Date().toISOString() }, ...prev].slice(0, 50);
      try { localStorage.setItem("scrubmeta-history", JSON.stringify(next)); } catch { /* ignore */ }
      return next;
    });
  }
  function selectTool(t: Tool) { setTool(t); setMobile(false); }

  const common = { file, owned, setOwned, choose: () => picker.current?.click(), clear: () => pick(null), drop, record };

  return (
    <div className="desktop">
      <aside className={mobile ? "sidebar open" : "sidebar"}>
        <div className="windowDots"><i /><i /><i /></div>
        <button className="logo" onClick={() => selectTool("scrub")}><span><ShieldCheck /></span><b>Scrubmeta</b></button>
        <small className="version">Private media utility</small>
        <div className="nav">
          {tools.map((t) => <Nav key={t.id} label={t.label} icon={t.icon} active={tool === t.id} onClick={() => selectTool(t.id)} />)}
        </div>
        <div className="nav bottom">
          <Nav label="History" icon={History} active={tool === "history"} onClick={() => selectTool("history")} />
          <Nav label="Settings" icon={Settings} active={tool === "settings"} onClick={() => selectTool("settings")} />
          <div className={`processor ${health}`}><i />{health === "online" ? "Processor online" : health === "offline" ? "Processor offline" : "Checking processor"}</div>
        </div>
      </aside>

      <section className="shell">
        <header className="mobileHead"><button onClick={() => setMobile((v) => !v)} aria-label="Menu"><Menu /></button><b>Scrubmeta</b><div className={`healthDot ${health}`} /></header>
        {tool === "scrub" && <Scrub {...common} />}
        {tool === "inspect" && <Inspect {...common} />}
        {tool === "convert" && <Convert {...common} />}
        {tool === "editor" && <Editor {...common} />}
        {tool === "generator" && <Generator {...common} />}
        {tool === "export" && <Export {...common} />}
        {tool === "duplicates" && <Duplicates files={files} owned={owned} setOwned={setOwned} choose={() => multiPicker.current?.click()} clear={() => setFiles([])} drop={drop} record={record} />}
        {tool === "history" && <HistoryView items={history} clear={() => { setHistory([]); try { localStorage.removeItem("scrubmeta-history"); } catch { /* ignore */ } }} />}
        {tool === "settings" && <SettingsView health={health} ping={ping} />}
      </section>

      <input ref={picker} type="file" accept={ACCEPT} hidden onChange={onInput} />
      <input ref={multiPicker} type="file" accept={ACCEPT_IMAGES} multiple hidden onChange={onMultiInput} />
    </div>
  );
}

/* ---------- shared props ---------- */

type ToolProps = {
  file: File | null; owned: boolean; setOwned: (v: boolean) => void;
  choose: () => void; clear: () => void; drop: (e: DragEvent<HTMLElement>) => void;
  record: (item: Omit<HistoryItem, "id" | "completedAt">) => void;
};

function useRun<T>() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<T | null>(null);
  async function run(fn: () => Promise<T>) {
    setBusy(true); setError(""); setResult(null);
    try { setResult(await fn()); } catch (e) { setError(e instanceof Error ? e.message : "Request failed"); }
    finally { setBusy(false); }
  }
  return { busy, error, result, run, reset: () => { setResult(null); setError(""); } };
}

/* ---------- tools ---------- */

function Scrub(p: ToolProps) {
  const { busy, error, result, run } = useRun<ScrubResult>();
  async function go() {
    if (!p.file) return;
    const body = new FormData(); body.append("file", p.file);
    await run(async () => {
      const r = await api<ScrubResult>("/api/scrub", body, { "X-I-Own-This-Content": "1" });
      p.record({ tool: "Scrub", name: p.file!.name, size: p.file!.size, output: r.diff.scrubbed_file });
      return r;
    });
  }
  return (
    <ToolPage tabs={["Metadata scrub"]} active={0}>
      <FileTitle file={p.file} clear={p.clear} />
      {!p.file ? <DropZone title="Drop a photo or video" sub="JPEG, TIFF, MP4, MOV, M4V today · PNG, HEIC, MKV, WebM as handlers ship · up to 500 MB" choose={p.choose} drop={p.drop} /> : (
        <div className="workGrid">
          <Preview file={p.file} />
          <div className="controls">
            <ControlTitle title="Privacy scrub" />
            <p className="muted">Remove identifying embedded metadata and write generic replacement values. Pixels and audio are left byte-for-byte unchanged.</p>
            <div className="infoRows"><Row label="GPS" value="Removed" /><Row label="Device make / model" value="Generic / Camera" /><Row label="Content credentials" value="Preserved by default" /><Row label="Output" value="New scrubbed file" /></div>
            <Ownership owned={p.owned} setOwned={p.setOwned} />
          </div>
        </div>
      )}
      {result && <ResultBar title="Scrub complete" sub={`${result.diff.scrubbed_file} · GPS removed · ${result.diff.replacement_metadata.make} / ${result.diff.replacement_metadata.model}`} href={result.download_url} />}
      {error && <div className="error">{error}</div>}
      <Action disabled={!p.file || !p.owned || busy} busy={busy} onClick={go}>Start scrub</Action>
    </ToolPage>
  );
}

function Inspect(p: ToolProps) {
  const { busy, error, result, run } = useRun<Inspection>();
  async function go() {
    if (!p.file) return;
    const body = new FormData(); body.append("file", p.file);
    await run(() => api<Inspection>("/api/inspect", body));
  }
  return (
    <ToolPage tabs={["File inspector"]} active={0}>
      <div className="centerTitle"><h1>Metadata Inspector</h1><p>See exactly which container tags and streams a file carries before you scrub it.</p></div>
      <FileTitle file={p.file} clear={p.clear} />
      {!p.file ? <DropZone title="Drop a file to inspect" sub="Nothing leaves this machine — inspection runs on the local processor." choose={p.choose} drop={p.drop} /> : (
        <div className="panel">
          <div className="inspectGrid"><Row label="File name" value={p.file.name} /><Row label="Size" value={bytes(p.file.size)} /><Row label="Browser type" value={p.file.type || "Unknown"} /><Row label="Last modified" value={new Date(p.file.lastModified).toLocaleString()} /></div>
          <Ownership owned={p.owned} setOwned={p.setOwned} />
        </div>
      )}
      {result && <InspectionView data={result} />}
      {error && <div className="error">{error}</div>}
      <Action disabled={!p.file || !p.owned || busy} busy={busy} onClick={go}>Inspect embedded metadata</Action>
    </ToolPage>
  );
}

function InspectionView({ data }: { data: Inspection }) {
  const tags = Object.entries(data.format_tags || {});
  return (
    <div className="panel">
      <h3>Container</h3>
      <div className="inspectGrid"><Row label="Format" value={data.format_name || "—"} /><Row label="Duration" value={secs(data.duration)} /><Row label="Bit rate" value={data.bit_rate ? `${Math.round(data.bit_rate / 1000)} kb/s` : "—"} /><Row label="Size" value={bytes(data.size)} /></div>
      <h3>Container tags ({tags.length})</h3>
      {tags.length ? <div className="tagList">{tags.map(([k, v]) => <Row key={k} label={k} value={String(v)} />)}</div> : <p className="muted">No container-level tags.</p>}
      <h3>Streams</h3>
      {data.streams.map((s) => {
        const st = Object.entries(s.tags || {});
        return (
          <div key={s.index} className="tagList">
            <Row label={`#${s.index} ${s.type}`} value={`${s.codec}${s.width ? ` · ${s.width}×${s.height}` : ""}${s.frame_rate ? ` · ${s.frame_rate} fps` : ""}${s.sample_rate ? ` · ${s.sample_rate} Hz` : ""}${s.channels ? ` · ${s.channels} ch` : ""}`} />
            {st.map(([k, v]) => <Row key={k} label={`  ${k}`} value={String(v)} />)}
          </div>
        );
      })}
    </div>
  );
}

function Convert(p: ToolProps) {
  const [tab, setTab] = useState(0);
  const [quality, setQuality] = useState(90);
  const [fps, setFps] = useState("");
  const [width, setWidth] = useState("");
  const [height, setHeight] = useState("");
  const targets = ["gif", "mp4", "jpg"] as const;
  const { busy, error, result, run } = useRun<DownloadResult>();
  async function go() {
    if (!p.file) return;
    const body = new FormData(); body.append("file", p.file); body.append("target", targets[tab]); body.append("quality", String(quality));
    if (fps) body.append("fps", fps); if (width) body.append("width", width); if (height) body.append("height", height);
    await run(async () => {
      const r = await api<DownloadResult>("/api/convert", body);
      p.record({ tool: `Convert → ${targets[tab].toUpperCase()}`, name: p.file!.name, size: p.file!.size, output: r.output_file });
      return r;
    });
  }
  return (
    <ToolPage tabs={["Convert to GIF", "Convert to MP4", "Convert to JPEG"]} active={tab} setActive={setTab}>
      <FileTitle file={p.file} clear={p.clear} />
      {!p.file ? <DropZone title="Choose media to convert" sub="Local ffmpeg. Output is re-encoded at the quality you pick." choose={p.choose} drop={p.drop} /> : (
        <div className="workGrid">
          <Preview file={p.file} />
          <div className="controls">
            <ControlTitle title="Output settings" />
            <div className="two"><Field label="Width (px)" value={width} onChange={setWidth} placeholder="auto" /><Field label="Height (px)" value={height} onChange={setHeight} placeholder="auto" /></div>
            <div className="two"><Field label="Frame rate" value={fps} onChange={setFps} placeholder="source" /><div /></div>
            <Range label="Quality" value={quality} onChange={setQuality} />
            <Ownership owned={p.owned} setOwned={p.setOwned} />
          </div>
        </div>
      )}
      {result && <ResultBar title="Conversion complete" sub={`${result.output_file}${result.inspection?.duration ? ` · ${secs(result.inspection.duration)}` : ""}`} href={result.download_url} />}
      {error && <div className="error">{error}</div>}
      <Action disabled={!p.file || !p.owned || busy} busy={busy} onClick={go}>Start conversion</Action>
    </ToolPage>
  );
}

function Editor(p: ToolProps) {
  const [start, setStart] = useState("0");
  const [end, setEnd] = useState("");
  const [quality, setQuality] = useState(90);
  const [speed, setSpeed] = useState(100);
  const { busy, error, result, run } = useRun<DownloadResult>();
  async function go() {
    if (!p.file) return;
    const body = new FormData(); body.append("file", p.file); body.append("start", start || "0");
    if (end) body.append("end", end); body.append("quality", String(quality)); body.append("speed", String(speed / 100));
    await run(async () => {
      const r = await api<DownloadResult>("/api/edit", body);
      p.record({ tool: "Edit", name: p.file!.name, size: p.file!.size, output: r.output_file });
      return r;
    });
  }
  return (
    <ToolPage tabs={["Trim & export"]} active={0}>
      <FileTitle file={p.file} clear={p.clear} />
      {!p.file ? <DropZone title="Choose a video" sub="Trim to a range, change playback speed, export as MP4." choose={p.choose} drop={p.drop} /> : (
        <div className="workGrid">
          <Preview file={p.file} />
          <div className="controls">
            <ControlTitle title="Export settings" />
            <div className="two"><Field label="Start (s)" value={start} onChange={setStart} placeholder="0" /><Field label="End (s)" value={end} onChange={setEnd} placeholder="end of file" /></div>
            <Range label="Quality" value={quality} onChange={setQuality} />
            <Range label="Speed" value={speed} onChange={setSpeed} min={25} max={400} suffix="%" />
            <Ownership owned={p.owned} setOwned={p.setOwned} />
          </div>
        </div>
      )}
      {result && <ResultBar title="Export complete" sub={`${result.output_file} · ${secs(result.inspection?.duration)}`} href={result.download_url} />}
      {error && <div className="error">{error}</div>}
      <Action disabled={!p.file || !p.owned || busy} busy={busy} onClick={go}>Start export</Action>
    </ToolPage>
  );
}

function Generator(p: ToolProps) {
  const [tab, setTab] = useState(0);
  const [start, setStart] = useState("0");
  const [duration, setDuration] = useState("10");
  const [at, setAt] = useState("0");
  const { busy, error, result, run, reset } = useRun<DownloadResult>();
  async function go() {
    if (!p.file) return;
    const body = new FormData(); body.append("file", p.file);
    const path = tab === 0 ? "/api/generate/clip" : "/api/generate/frame";
    if (tab === 0) { body.append("start", start || "0"); body.append("duration", duration || "10"); } else { body.append("at", at || "0"); }
    await run(async () => {
      const r = await api<DownloadResult>(path, body);
      p.record({ tool: tab === 0 ? "Clip" : "Frame", name: p.file!.name, size: p.file!.size, output: r.output_file });
      return r;
    });
  }
  return (
    <ToolPage tabs={["Clip", "Frame"]} active={tab} setActive={(n) => { setTab(n); reset(); }}>
      <FileTitle file={p.file} clear={p.clear} />
      {!p.file ? <DropZone title="Choose a source video" sub="Cut a clip or pull a single frame as JPEG." choose={p.choose} drop={p.drop} /> : (
        <div className="workGrid">
          <Preview file={p.file} />
          <div className="controls">
            <ControlTitle title={tab === 0 ? "Clip generator" : "Frame extractor"} />
            {tab === 0
              ? <div className="two"><Field label="Start (s)" value={start} onChange={setStart} /><Field label="Duration (s)" value={duration} onChange={setDuration} /></div>
              : <div className="two"><Field label="At (s)" value={at} onChange={setAt} /><div /></div>}
            <Row label="Output" value={tab === 0 ? "MP4 clip" : "JPEG frame"} />
            <Ownership owned={p.owned} setOwned={p.setOwned} />
          </div>
        </div>
      )}
      {result && <ResultBar title={tab === 0 ? "Clip ready" : "Frame ready"} sub={result.output_file} href={result.download_url} />}
      {error && <div className="error">{error}</div>}
      <Action disabled={!p.file || !p.owned || busy} busy={busy} onClick={go}>Start</Action>
    </ToolPage>
  );
}

function Export(p: ToolProps) {
  const [presets, setPresets] = useState<Record<string, Preset>>({});
  const [preset, setPreset] = useState("vertical");
  const [quality, setQuality] = useState(90);
  const { busy, error, result, run } = useRun<DownloadResult>();
  useEffect(() => { fetch("/backend/api/export-presets").then((r) => r.json()).then(setPresets).catch(() => setPresets({})); }, []);
  async function go() {
    if (!p.file) return;
    const body = new FormData(); body.append("file", p.file); body.append("preset", preset); body.append("quality", String(quality));
    await run(async () => {
      const r = await api<DownloadResult>("/api/variations", body);
      p.record({ tool: `Export ${presets[preset]?.label ?? preset}`, name: p.file!.name, size: p.file!.size, output: r.output_file });
      return r;
    });
  }
  return (
    <ToolPage tabs={["Canvas export"]} active={0}>
      <FileTitle file={p.file} clear={p.clear} />
      {!p.file ? <DropZone title="Choose a video to export" sub="Fit the whole frame onto a fixed canvas (vertical, square, landscape, HD). Letterboxed, never cropped." choose={p.choose} drop={p.drop} /> : (
        <div className="workGrid">
          <Preview file={p.file} />
          <div className="controls">
            <ControlTitle title="Canvas preset" />
            <div className="presetGrid">
              {Object.entries(presets).map(([id, pr]) => (
                <button key={id} className={preset === id ? "preset active" : "preset"} onClick={() => setPreset(id)}><b>{pr.label}</b><small>{pr.width} × {pr.height}</small></button>
              ))}
            </div>
            <Range label="Quality" value={quality} onChange={setQuality} />
            <p className="notice"><Info />Same input and preset always produce the same output. There is no randomization.</p>
            <Ownership owned={p.owned} setOwned={p.setOwned} />
          </div>
        </div>
      )}
      {result && <ResultBar title="Export complete" sub={`${result.output_file} · ${presets[result.preset ?? ""]?.label ?? result.preset}`} href={result.download_url} />}
      {error && <div className="error">{error}</div>}
      <Action disabled={!p.file || !p.owned || busy || !presets[preset]} busy={busy} onClick={go}>Export</Action>
    </ToolPage>
  );
}

function Duplicates(p: { files: File[]; owned: boolean; setOwned: (v: boolean) => void; choose: () => void; clear: () => void; drop: (e: DragEvent<HTMLElement>) => void; record: ToolProps["record"] }) {
  const [threshold, setThreshold] = useState(90);
  const { busy, error, result, run } = useRun<{ threshold: number; files_scanned: number; matches: DupeMatch[] }>();
  const total = p.files.reduce((n, f) => n + f.size, 0);
  async function go() {
    if (!p.files.length) return;
    const body = new FormData(); p.files.forEach((f) => body.append("files", f)); body.append("threshold", String(threshold));
    await run(async () => {
      const r = await api<{ threshold: number; files_scanned: number; matches: DupeMatch[] }>("/api/duplicates", body);
      p.record({ tool: "Duplicate scan", name: `${r.files_scanned} images`, size: total, output: `${r.matches.length} match${r.matches.length === 1 ? "" : "es"}` });
      return r;
    });
  }
  return (
    <ToolPage tabs={["Duplicate finder"]} active={0}>
      <div className="centerTitle"><h1>Find duplicates in your library</h1><p>Select up to 100 of your own images. Exact copies and near-duplicates (resized, re-saved) are grouped together.</p></div>
      {!p.files.length ? <DropZone title="Drop a set of images" sub="JPEG, PNG, WebP, TIFF, GIF · up to 100 files, 500 MB total" choose={p.choose} drop={p.drop} /> : (
        <div className="panel">
          <div className="fileTitle"><span>{p.files.length} images · {bytes(total)}</span><div><button onClick={p.choose} title="Choose different files"><FolderOpen /></button><button onClick={p.clear} title="Clear"><X /></button></div></div>
          <div className="fileChips">{p.files.slice(0, 24).map((f) => <span key={f.name + f.size}>{f.name}</span>)}{p.files.length > 24 && <span>+{p.files.length - 24} more</span>}</div>
          <Range label="Similarity threshold" value={threshold} onChange={setThreshold} min={50} max={100} suffix="%" />
          <Ownership owned={p.owned} setOwned={p.setOwned} />
        </div>
      )}
      {result && (
        <div className="panel">
          <h3>{result.matches.length} match{result.matches.length === 1 ? "" : "es"} at ≥ {result.threshold}% across {result.files_scanned} files</h3>
          {result.matches.length ? (
            <div className="dupeList">{result.matches.map((m, i) => <div className="dupe" key={i}><span>{m.a}</span><i>↔</i><span>{m.b}</span><b><span className={`chip ${m.kind}`}>{m.kind}</span> {m.similarity.toFixed(1)}%</b></div>)}</div>
          ) : <p className="muted">No pairs met the threshold. Lower it to catch looser near-duplicates.</p>}
        </div>
      )}
      {error && <div className="error">{error}</div>}
      <Action disabled={p.files.length < 2 || !p.owned || busy} busy={busy} onClick={go}>Scan for duplicates</Action>
    </ToolPage>
  );
}

function HistoryView({ items, clear }: { items: HistoryItem[]; clear: () => void }) {
  return (
    <ToolPage tabs={["History"]} active={0}>
      <div className="centerTitle"><h1>Processing history</h1><p>Stored only in this browser. Files themselves are never kept.</p></div>
      {items.length ? (
        <div className="panel">
          {items.map((x) => <div className="historyRow" key={x.id}><History /><div><b>{x.tool} · {x.name}</b><span>{x.output} · {bytes(x.size)} · {new Date(x.completedAt).toLocaleString()}</span></div><Check /></div>)}
          <button className="textButton" onClick={clear}>Clear local history</button>
        </div>
      ) : <Empty text="Nothing processed yet." />}
    </ToolPage>
  );
}

function SettingsView({ health, ping }: { health: Health; ping: () => void }) {
  return (
    <ToolPage tabs={["Settings"]} active={0}>
      <div className="centerTitle"><h1>Settings</h1><p>Local processor status and the safeguards this tool runs under.</p></div>
      <div className="settingsCards">
        <Setting icon={Gauge} title="Processor" text={`Status: ${health}. This UI proxies to the scrubmeta backend set by SCRUBMETA_API_URL.`} />
        <Setting icon={Lock} title="Privacy" text="No analytics, cloud library, or telemetry. Every operation runs on the local processor and downloads are one-time." />
        <Setting icon={ShieldCheck} title="Provenance" text="C2PA content credentials are preserved by default. Stripping them requires explicit ownership flags at the CLI." />
        <Setting icon={Info} title="Scope" text="Personal privacy on files you own. Not a tool for evading moderation, provenance, or copyright systems. See factory/MISSION.md." />
      </div>
      <Action onClick={ping}>Recheck processor</Action>
    </ToolPage>
  );
}

/* ---------- primitives ---------- */

function Nav({ label, icon: Icon, active, onClick }: { label: string; icon: typeof ShieldCheck; active: boolean; onClick: () => void }) {
  return <button className={active ? "navItem active" : "navItem"} onClick={onClick}><Icon /><span>{label}</span></button>;
}
function ToolPage({ tabs, active, setActive, children }: { tabs: string[]; active: number; setActive?: (n: number) => void; children: ReactNode }) {
  return <main className="toolPage"><div className="segmented">{tabs.map((t, i) => <button key={t} className={active === i ? "active" : ""} onClick={() => setActive?.(i)}>{t}</button>)}</div>{children}</main>;
}
function FileTitle({ file, clear }: { file: File | null; clear?: () => void }) {
  if (!file) return null;
  return <div className="fileTitle"><span>{file.name}</span><div><FolderOpen />{clear && <button onClick={clear} title="Remove"><X /></button>}</div></div>;
}
function DropZone({ title, sub, choose, drop }: { title: string; sub: string; choose: () => void; drop: (e: DragEvent<HTMLElement>) => void }) {
  return <button className="dropZone" onClick={choose} onDragOver={(e) => e.preventDefault()} onDrop={drop}><Upload /><b>{title}</b><span>{sub}</span></button>;
}
function Preview({ file }: { file: File }) {
  const url = useMemo(() => URL.createObjectURL(file), [file]);
  useEffect(() => () => URL.revokeObjectURL(url), [url]);
  const video = file.type.startsWith("video");
  return <div className="previewWrap"><div className="preview">{video ? <video src={url} controls /> : <img src={url} alt="Selected media preview" />}</div><small>{bytes(file.size)}</small></div>;
}
function ControlTitle({ title }: { title: string }) { return <div className="controlTitle"><span>{title}</span><Check /></div>; }
function Row({ label, value }: { label: string; value: string }) { return <div className="row"><span>{label}</span><b title={value}>{value}</b></div>; }
function Field({ label, value, onChange, placeholder }: { label: string; value: string; onChange: (v: string) => void; placeholder?: string }) {
  const id = `f-${label.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
  return <label className="field" htmlFor={id}><span>{label}</span><input id={id} inputMode="decimal" value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} /></label>;
}
function Range({ label, value, onChange, min = 1, max = 100, suffix = "" }: { label: string; value: number; onChange: (v: number) => void; min?: number; max?: number; suffix?: string }) {
  const id = `r-${label.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
  return <label className="range" htmlFor={id}><span>{label}<b>{value}{suffix}</b></span><input id={id} type="range" min={min} max={max} value={value} onChange={(e) => onChange(Number(e.target.value))} /></label>;
}
function Ownership({ owned, setOwned }: { owned: boolean; setOwned: (v: boolean) => void }) {
  return <label className="ownership"><input id="ownership" type="checkbox" checked={owned} onChange={(e) => setOwned(e.target.checked)} /><span><b>I own or am authorized to process this content</b><small>Required before any operation runs.</small></span></label>;
}
function ResultBar({ title, sub, href }: { title: string; sub: string; href: string }) {
  return <div className="resultBar"><Check /><div><b>{title}</b><span>{sub}</span></div><a href={`/backend${href}`}><Download />Download</a></div>;
}
function Action({ disabled, busy, onClick, children }: { disabled?: boolean; busy?: boolean; onClick?: () => void; children: ReactNode }) {
  return <><div className="divider" /><button className="start" disabled={disabled} onClick={onClick}>{busy ? <><RefreshCw className="spin" />Processing…</> : children}</button></>;
}
function Setting({ icon: Icon, title, text }: { icon: typeof ShieldCheck; title: string; text: string }) {
  return <div className="setting"><Icon /><div><b>{title}</b><span>{text}</span></div></div>;
}
function Empty({ text }: { text: string }) { return <div className="empty"><ScanSearch /><b>{text}</b></div>; }

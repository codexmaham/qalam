import { useEffect, useRef, useState } from "react";
import {
  downloadPdf,
  fetchCatalogue,
  fetchPreview,
  fetchStyles,
  fetchVoice,
  setDefaultStyle,
  styleFields,
  transcribeAudio,
  type Catalogue,
  type Language,
} from "../api";

const STYLE_KEY = "qalam.defaultStyle";

export function VoicePage() {
  const [catalogue, setCatalogue] = useState<Catalogue | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [languageId, setLanguageId] = useState("en");
  const [detect, setDetect] = useState(true);
  const [template, setTemplate] = useState("four-line");
  const [styleId, setStyleId] = useState("school-neat");
  const [styleName, setStyleName] = useState("Neat school notes");
  const [userDefaultId, setUserDefaultId] = useState("");
  const [model, setModel] = useState("base");
  const [text, setText] = useState("");
  const [name, setName] = useState("");
  const [date, setDate] = useState("");
  const [pages, setPages] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [recording, setRecording] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const session = useRef<RecordSession | null>(null);
  const requestId = useRef(0);

  const language = catalogue?.languages.find((item) => item.id === languageId);

  useEffect(() => {
    setDate(
      new Date().toLocaleDateString(undefined, {
        day: "numeric",
        month: "short",
        year: "numeric",
      }),
    );
    Promise.all([fetchCatalogue(), fetchStyles(), fetchVoice()])
      .then(([data, styles, voice]) => {
        setCatalogue(data);
        const chosen = styles.default || "school-neat";
        setStyleId(chosen);
        setUserDefaultId(styles.user_default || "");
        setStyleName(styles.styles.find((item) => item.id === chosen)?.name || "Neat school notes");
        try {
          localStorage.setItem(STYLE_KEY, chosen);
        } catch {
          /* the API remembers the handwriting */
        }
        if (voice.model) setModel(voice.model);
        if (voice.error) setError(voice.error);
        const english = data.languages.find((item) => item.id === "en") ?? data.languages[0];
        setLanguageId(english.id);
        setTemplate(english.recommended[0] ?? "single-ruled");
      })
      .catch((err: Error) => setLoadError(err.message));
    drawIdle(canvasRef.current);
    return () => {
      session.current?.stop(false);
      session.current = null;
    };
  }, []);

  useEffect(() => {
    if (!catalogue || !language || !text.trim()) {
      setPages([]);
      return;
    }
    const controller = new AbortController();
    const id = ++requestId.current;
    const handle = window.setTimeout(() => {
      setBusy(true);
      fetchPreview(
        {
          text,
          language: language.id,
          template,
          ink: "sample",
          name,
          date,
          ...styleFields(styleId),
        },
        controller.signal,
      )
        .then((preview) => {
          if (id !== requestId.current) return;
          setPages(preview.pages);
          setError(null);
        })
        .catch((err: Error) => {
          if (err.name !== "AbortError" && id === requestId.current) setError(err.message);
        })
        .finally(() => {
          if (id === requestId.current) setBusy(false);
        });
    }, 280);
    return () => {
      window.clearTimeout(handle);
      controller.abort();
    };
  }, [catalogue, language, text, template, name, date, styleId]);

  async function onRecord() {
    if (recording) {
      session.current?.stop(true);
      session.current = null;
      setRecording(false);
      drawIdle(canvasRef.current);
      return;
    }
    setError(null);
    setMessage(null);
    try {
      const next = await RecordSession.start(canvasRef.current, (file) => {
        void onAudio(file);
      });
      session.current = next;
      setRecording(true);
    } catch {
      setError("This browser did not open the microphone. You can upload a recording instead.");
      setRecording(false);
    }
  }

  async function onAudio(file: File) {
    setTranscribing(true);
    setError(null);
    setMessage("Transcribing on this computer…");
    try {
      const result = await transcribeAudio(file, detect ? "" : languageId);
      if (result.model) setModel(result.model);
      if (!result.text.trim()) {
        setText("");
        setMessage(null);
        setError("No speech was heard in that recording.");
        return;
      }
      setText(result.text);
      if (result.language_id) {
        setLanguageId(result.language_id);
        setDetect(false);
        const next = catalogue?.languages.find((item) => item.id === result.language_id);
        if (next && result.template) setTemplate(result.template);
      }
      setMessage(null);
    } catch (err) {
      setMessage(null);
      setError(err instanceof Error ? err.message : "Could not transcribe that recording.");
    } finally {
      setTranscribing(false);
    }
  }

  async function useSchoolNotes() {
    setError(null);
    try {
      const result = await setDefaultStyle("school-neat");
      setUserDefaultId(result.user_default || "");
      const next = result.default || "school-neat";
      setStyleId(next);
      setStyleName("Neat school notes");
      try {
        localStorage.setItem(STYLE_KEY, next);
      } catch {
        /* the data directory already has the preset */
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not change the default handwriting.");
    }
  }

  async function onDownload() {
    if (!language || !text.trim()) return;
    setDownloading(true);
    try {
      await downloadPdf({
        text,
        language: language.id,
        template,
        ink: "sample",
        name,
        date,
        ...styleFields(styleId),
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not build the PDF.");
    } finally {
      setDownloading(false);
    }
  }

  if (loadError) {
    return (
      <main className="banner">
        <h1>The notebook renderer is not running.</h1>
        <p>Start it from the backend folder, then refresh this page.</p>
        <pre>python3 -m uvicorn qalam.main:app --host 127.0.0.1 --port 8000</pre>
      </main>
    );
  }

  if (!catalogue || !language) {
    return (
      <main className="banner">
        <p>Opening the notebook…</p>
      </main>
    );
  }

  return (
    <main className="workspace">
      <form
        className="panel"
        onSubmit={(event) => {
          event.preventDefault();
          void onDownload();
        }}
      >
        <h1 className="voice-title">Voice to handwriting</h1>
        <p className="note">Speak a lesson, or upload a recording. The transcript is written into the notebook.</p>
        <button className={recording ? "mic live" : "mic"} type="button" onClick={() => void onRecord()} aria-pressed={recording}>
          <span className="mic-dot" />
          {recording ? "Stop" : "Record"}
        </button>
        <canvas ref={canvasRef} className="wave" width={640} height={144} aria-hidden="true" />
        <label className="file">
          <input
            type="file"
            accept="audio/*,.wav,.mp3,.m4a,.ogg,.webm"
            onChange={(event) => {
              const file = event.target.files?.[0];
              event.target.value = "";
              if (file) void onAudio(file);
            }}
          />
          Upload an audio file
        </label>
        {message && <p className="note">{message}</p>}
        {error && <p className="error">{error}</p>}

        <label className="field">
          <span>Language</span>
          <select
            value={detect ? "auto" : languageId}
            onChange={(event) => {
              const next = event.target.value;
              if (next === "auto") {
                setDetect(true);
                return;
              }
              setDetect(false);
              const chosen = catalogue.languages.find((item) => item.id === next);
              if (chosen) chooseLanguage(chosen, setLanguageId, setTemplate, template);
            }}
          >
            <option value="auto">Detect automatically</option>
            {catalogue.languages.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name} · {item.native}
              </option>
            ))}
          </select>
        </label>

        <label className="field grow">
          <span>Transcript</span>
          <textarea
            value={text}
            dir={language.direction}
            lang={language.id}
            rows={8}
            placeholder="The words appear here. Edit them before printing."
            onChange={(event) => setText(event.target.value)}
          />
        </label>

        <div className="split">
          <label>
            Name
            <input value={name} onChange={(event) => setName(event.target.value)} placeholder="Amina" />
          </label>
          <label>
            Date
            <input value={date} onChange={(event) => setDate(event.target.value)} />
          </label>
        </div>

        <fieldset>
          <legend>Paper</legend>
          <div className="templates">
            {catalogue.templates.map((item) => (
              <button
                key={item.id}
                type="button"
                className={item.id === template ? "template on" : "template"}
                aria-pressed={item.id === template}
                onClick={() => setTemplate(item.id)}
              >
                <span className={`sketch sketch-${item.id}`} />
                <strong>{item.name}</strong>
                <small>{item.description}</small>
              </button>
            ))}
          </div>
        </fieldset>

        <div className="actions">
          <button className="download" type="submit" disabled={downloading || !text.trim()}>
            {downloading ? "Preparing…" : "Download A4 PDF"}
          </button>
        </div>
        {userDefaultId && (
          <p className="confirm">
            Your handwriting is now the default
            <button className="quiet" type="button" onClick={() => void useSchoolNotes()}>
              Use Neat school notes
            </button>
          </p>
        )}
        <p className="fine">
          Whisper {model} runs on this computer. The first recording downloads the model. Handwriting: {styleName}. Nothing is uploaded.
        </p>
      </form>

      <section className="stage">
        <div className={busy || transcribing ? "sheet busy" : "sheet"}>
          {pages[0] ? (
            <img src={`data:image/png;base64,${pages[0]}`} alt={`${language.name} notebook from the recording`} />
          ) : (
            <div className="sheet-wait">{transcribing ? "Transcribing on this computer…" : "The page appears after you speak."}</div>
          )}
        </div>
      </section>
    </main>
  );
}

function chooseLanguage(
  next: Language,
  setLanguageId: (id: string) => void,
  setTemplate: (id: string) => void,
  template: string,
) {
  setLanguageId(next.id);
  if (!next.recommended.includes(template)) setTemplate(next.recommended[0]);
}

function drawIdle(canvas: HTMLCanvasElement | null) {
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.strokeStyle = "#c9b8a4";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(0, canvas.height / 2);
  ctx.lineTo(canvas.width, canvas.height / 2);
  ctx.stroke();
}

class RecordSession {
  private raf = 0;

  private constructor(
    private readonly context: AudioContext,
    private readonly stream: MediaStream,
    private readonly recorder: MediaRecorder,
  ) {}

  static async start(canvas: HTMLCanvasElement | null, onFile: (file: File) => void): Promise<RecordSession> {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    let context: AudioContext;
    try {
      context = new AudioContext();
    } catch (error) {
      stream.getTracks().forEach((track) => track.stop());
      throw error;
    }
    const source = context.createMediaStreamSource(stream);
    const analyser = context.createAnalyser();
    analyser.fftSize = 2048;
    source.connect(analyser);
    const chunks: Blob[] = [];
    let recorder: MediaRecorder;
    try {
      recorder = new MediaRecorder(stream);
    } catch (error) {
      stream.getTracks().forEach((track) => track.stop());
      void context.close();
      throw error;
    }
    recorder.ondataavailable = (event) => {
      if (event.data.size) chunks.push(event.data);
    };
    recorder.onstop = () => {
      const type = recorder.mimeType || "audio/webm";
      const blob = new Blob(chunks, { type });
      const ext = type.includes("mp4") ? "m4a" : type.includes("ogg") ? "ogg" : type.includes("wav") ? "wav" : "webm";
      onFile(new File([blob], `recording.${ext}`, { type }));
    };
    recorder.start();
    const session = new RecordSession(context, stream, recorder);
    session.draw(canvas, analyser);
    return session;
  }

  stop(deliver: boolean) {
    window.cancelAnimationFrame(this.raf);
    if (!deliver) {
      this.recorder.onstop = null;
      this.recorder.ondataavailable = null;
    }
    if (this.recorder.state !== "inactive") this.recorder.stop();
    this.stream.getTracks().forEach((track) => track.stop());
    void this.context.close();
  }

  private draw(canvas: HTMLCanvasElement | null, analyser: AnalyserNode) {
    const data = new Uint8Array(analyser.fftSize);
    const tick = () => {
      if (!canvas) return;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      analyser.getByteTimeDomainData(data);
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.strokeStyle = "#9d2c1c";
      ctx.lineWidth = 2;
      ctx.beginPath();
      for (let i = 0; i < data.length; i += 1) {
        const x = (i / (data.length - 1)) * canvas.width;
        const y = (data[i] / 255) * canvas.height;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();
      this.raf = window.requestAnimationFrame(tick);
    };
    this.raf = window.requestAnimationFrame(tick);
  }
}

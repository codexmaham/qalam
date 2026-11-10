import { useEffect, useMemo, useRef, useState } from "react";
import {
  downloadPdf,
  downloadPng,
  downloadStyleSheet,
  fetchCatalogue,
  fetchPractice,
  fetchPreview,
  fetchStyles,
  setDefaultStyle,
  styleFields,
  uploadHandwriting,
  uploadPagePhoto,
  type Catalogue,
  type Language,
  type StyleInfo,
} from "../api";

const STYLE_KEY = "qalam.defaultStyle";

export function NotesPage() {
  const [catalogue, setCatalogue] = useState<Catalogue | null>(null);
  const [styles, setStyles] = useState<StyleInfo[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [languageId, setLanguageId] = useState("en");
  const [template, setTemplate] = useState("four-line");
  const [ink, setInk] = useState("sample");
  const [styleId, setStyleId] = useState("school-neat");
  const [userDefaultId, setUserDefaultId] = useState("");
  const [handwritingNote, setHandwritingNote] = useState("");
  const [transcript, setTranscript] = useState("");
  const [filledSheet, setFilledSheet] = useState(false);
  const [pagePhotoId, setPagePhotoId] = useState("");
  const [pagePreview, setPagePreview] = useState("");
  const [pageLines, setPageLines] = useState(0);
  const [pageEmpty, setPageEmpty] = useState(0);
  const [pageNote, setPageNote] = useState("");
  const [uploading, setUploading] = useState<"hand" | "page" | null>(null);
  const [text, setText] = useState("");
  const [name, setName] = useState("");
  const [date, setDate] = useState("");
  const [className, setClassName] = useState("");
  const [pageSize, setPageSize] = useState("a4");
  const [marginId, setMarginId] = useState("standard");
  const [thickness, setThickness] = useState(1);
  const [trace, setTrace] = useState(false);
  const [seed, setSeed] = useState(1);
  const [styleName, setStyleName] = useState("My handwriting");
  const [glyphPreview, setGlyphPreview] = useState("");
  const [pages, setPages] = useState<string[]>([]);
  const [page, setPage] = useState(0);
  const [truncated, setTruncated] = useState(false);
  const [busy, setBusy] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);
  const textWasSample = useRef(true);

  useEffect(() => {
    setDate(
      new Date().toLocaleDateString(undefined, {
        day: "numeric",
        month: "short",
        year: "numeric",
      }),
    );
    Promise.all([fetchCatalogue(), fetchStyles()])
      .then(([data, styleData]) => {
        setCatalogue(data);
        setStyles(styleData.styles);
        const chosen = styleData.default || "school-neat";
        setStyleId(chosen);
        setUserDefaultId(styleData.user_default || "");
        if (styleData.user_default) setHandwritingNote("Your handwriting is now the default");
        try {
          localStorage.setItem(STYLE_KEY, chosen);
        } catch {
          /* the API copy is the one that survives a restart */
        }
        const english = data.languages.find((item) => item.id === "en") ?? data.languages[0];
        setLanguageId(english.id);
        setTemplate(english.recommended[0] ?? "single-ruled");
        setText(english.sample);
        textWasSample.current = true;
      })
      .catch((error: Error) => setLoadError(error.message));
  }, []);

  const language = catalogue?.languages.find((item) => item.id === languageId);

  const requestId = useRef(0);

  useEffect(() => {
    if (!catalogue || !language) return;
    const controller = new AbortController();
    const id = ++requestId.current;
    const handle = window.setTimeout(() => {
      setBusy(true);
      fetchPreview(
        {
          text,
          language: language.id,
          template,
          ink,
          name,
          date,
          class_name: className,
          page_size: pageSize,
          margin: marginId,
          thickness,
          trace,
          seed,
          ...styleFields(styleId),
          page_photo_id: pagePhotoId,
        },
        controller.signal,
      )
        .then((preview) => {
          if (id !== requestId.current) return;
          setPages(preview.pages);
          setTruncated(preview.truncated);
          setPage((current) => Math.min(current, Math.max(preview.page_count - 1, 0)));
          setPreviewError(null);
        })
        .catch((error: Error) => {
          if (error.name !== "AbortError" && id === requestId.current) setPreviewError(error.message);
        })
        .finally(() => {
          if (id === requestId.current) setBusy(false);
        });
    }, 280);
    return () => {
      window.clearTimeout(handle);
      controller.abort();
    };
  }, [catalogue, language, text, template, ink, name, date, className, pageSize, marginId, thickness, trace, seed, styleId, pagePhotoId]);

  function chooseLanguage(next: Language) {
    const previous = language;
    setLanguageId(next.id);
    if (!text.trim() || (previous && textWasSample.current)) {
      setText(next.sample);
      textWasSample.current = true;
    }
    if (!next.recommended.includes(template)) {
      setTemplate(next.recommended[0]);
    }
  }

  function noteBody() {
    return {
      text,
      language: language?.id ?? "en",
      template,
      ink,
      name,
      date,
      class_name: className,
      page_size: pageSize,
      margin: marginId,
      thickness,
      trace,
      seed,
      ...styleFields(styleId),
      page_photo_id: pagePhotoId,
    };
  }

  async function onDownload() {
    if (!language) return;
    setDownloading(true);
    try {
      await downloadPdf(noteBody());
    } catch (error) {
      setPreviewError(error instanceof Error ? error.message : "Could not build the PDF.");
    } finally {
      setDownloading(false);
    }
  }

  async function onDownloadPng() {
    if (!language) return;
    setDownloading(true);
    try {
      await downloadPng(noteBody());
    } catch (error) {
      setPreviewError(error instanceof Error ? error.message : "Could not build the image.");
    } finally {
      setDownloading(false);
    }
  }

  async function onHandwriting(file: File) {
    setUploading("hand");
    setPreviewError(null);
    try {
      const style = await uploadHandwriting(file, transcript, filledSheet ? "template" : "notes", styleName);
      const fresh = await fetchStyles();
      setStyles(fresh.styles);
      setStyleId(style.id);
      setUserDefaultId(fresh.user_default || style.id);
      setHandwritingNote(style.message || "Your handwriting is now the default");
      try {
        localStorage.setItem(STYLE_KEY, style.id);
      } catch {
        /* the saved file in the data directory is the source of truth */
      }
      setInk("sample");
      setGlyphPreview(style.preview || "");
    } catch (error) {
      setPreviewError(error instanceof Error ? error.message : "Could not read that handwriting.");
    } finally {
      setUploading(null);
    }
  }

  async function onPractice(kind: "letters" | "words") {
    if (!language) return;
    setPreviewError(null);
    try {
      const sheet = await fetchPractice(language.id, kind);
      setText(sheet.text);
      setTemplate(sheet.template);
      setTrace(true);
      textWasSample.current = false;
    } catch (error) {
      setPreviewError(error instanceof Error ? error.message : "Could not build that practice sheet.");
    }
  }

  async function useSchoolNotes() {
    setPreviewError(null);
    try {
      const result = await setDefaultStyle("school-neat");
      setUserDefaultId(result.user_default || "");
      setStyleId(result.default || "school-neat");
      setHandwritingNote("");
      try {
        localStorage.setItem(STYLE_KEY, result.default || "school-neat");
      } catch {
        /* the data directory already has the preset */
      }
    } catch (error) {
      setPreviewError(error instanceof Error ? error.message : "Could not change the default handwriting.");
    }
  }

  async function onPagePhoto(file: File) {
    setUploading("page");
    setPreviewError(null);
    try {
      const page = await uploadPagePhoto(file);
      setPagePhotoId(page.id);
      setPagePreview(page.preview);
      setPageLines(page.lines);
      setPageEmpty(page.empty ?? page.lines);
      setPageNote(page.note ?? "");
    } catch (error) {
      setPreviewError(error instanceof Error ? error.message : "Could not read that page.");
    } finally {
      setUploading(null);
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
        <label className="field">
          <span>Language</span>
          <LanguagePicker
            languages={catalogue.languages}
            current={language}
            onChange={chooseLanguage}
          />
        </label>
        {language.font_style === "text" && <p className="note">{language.font_note}</p>}

        <label className="field">
          <span>Handwriting</span>
          <select
            value={styleId}
            onChange={(event) => {
              const next = event.target.value;
              setStyleId(next);
              if (next === "qalam-fonts") setInk("blue");
              else setInk("sample");
            }}
          >
            {styles.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
        {handwritingNote && <p className="confirm">{handwritingNote}</p>}
        <p className="note">
          {styles.find((item) => item.id === styleId)?.note ||
            styles.find((item) => item.id === styleId)?.description}
        </p>
        {userDefaultId && (
          <button className="quiet" type="button" onClick={() => void useSchoolNotes()}>
            Use Neat school notes
          </button>
        )}

        <fieldset>
          <legend>Your handwriting</legend>
          <label className="file">
            <input
              type="file"
              accept="image/*"
              onChange={(event) => {
                const file = event.target.files?.[0];
                event.target.value = "";
                if (file) void onHandwriting(file);
              }}
            />
            {uploading === "hand" ? "Reading the sample…" : "Upload a handwriting photo"}
          </label>
          <label className="check">
            <input type="checkbox" checked={filledSheet} onChange={(event) => setFilledSheet(event.target.checked)} />
            I filled the template sheet
          </label>
          <textarea
            value={transcript}
            rows={3}
            placeholder="Transcript, if this is a page of notes. One photo line per line."
            onChange={(event) => setTranscript(event.target.value)}
          />
          <label className="field">
            <span>Style name</span>
            <input value={styleName} onChange={(event) => setStyleName(event.target.value)} placeholder="My handwriting" />
          </label>
          <button className="quiet" type="button" onClick={() => void downloadStyleSheet()}>
            Download the handwriting sheet
          </button>
          {glyphPreview && (
            <img className="glyph-strip" src={`data:image/png;base64,${glyphPreview}`} alt="Letters cut from the handwriting sample" />
          )}
        </fieldset>

        <fieldset>
          <legend>Your page</legend>
          {pagePreview ? (
            <div className="page-preview">
              <img src={`data:image/jpeg;base64,${pagePreview}`} alt="Straightened notebook page" />
              <p className="note">
                {pageNote ||
                  (pageEmpty < pageLines
                    ? `${pageLines} ruled lines, ${pageEmpty} empty. Writing starts on the first free line.`
                    : `${pageLines} ruled lines. Writing sits on the rules, just past the margin.`)}
              </p>
              <button
                className="quiet"
                type="button"
                onClick={() => {
                  setPagePhotoId("");
                  setPagePreview("");
                  setPageLines(0);
                  setPageNote("");
                  setPageEmpty(0);
                }}
              >
                Use blank paper
              </button>
            </div>
          ) : (
            <label className="file">
              <input
                type="file"
                accept="image/*"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  event.target.value = "";
                  if (file) void onPagePhoto(file);
                }}
              />
              {uploading === "page" ? "Straightening the page…" : "Upload a photo of your page"}
            </label>
          )}
        </fieldset>

        <label className="field grow">
          <span>Text</span>
          <textarea
            value={text}
            dir={language.direction}
            lang={language.id}
            rows={8}
            placeholder="Paste a lesson, a list, a paragraph."
            onChange={(event) => {
              textWasSample.current = false;
              setText(event.target.value);
            }}
          />
        </label>
        <div className="row-actions">
          <button
            className="quiet"
            type="button"
            onClick={() => {
              setText(language.sample);
              textWasSample.current = true;
              setTrace(false);
            }}
          >
            Use the {language.name} sample
          </button>
          <button className="quiet" type="button" onClick={() => void onPractice("letters")}>
            Letter practice
          </button>
          <button className="quiet" type="button" onClick={() => void onPractice("words")}>
            Word practice
          </button>
        </div>
        <p className="note"># Heading, - bullet, --- rule, __word__ underline, x^2 and $1/2$.</p>

        <div className="split three">
          <label>
            Name
            <input value={name} onChange={(event) => setName(event.target.value)} placeholder="Amina" />
          </label>
          <label>
            Date
            <input value={date} onChange={(event) => setDate(event.target.value)} />
          </label>
          <label>
            Class
            <input value={className} onChange={(event) => setClassName(event.target.value)} placeholder="4B" />
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

        <div className="split">
          <label>
            Page
            <select value={pageSize} onChange={(event) => setPageSize(event.target.value)}>
              {(catalogue.pages || [
                { id: "a4", name: "A4" },
                { id: "letter", name: "US Letter" },
              ]).map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Margin
            <select value={marginId} onChange={(event) => setMarginId(event.target.value)}>
              {(catalogue.margins || [
                { id: "narrow", name: "Narrow" },
                { id: "standard", name: "Standard" },
                { id: "wide", name: "Wide" },
              ]).map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
        </div>
        <label className="field">
          <span>Pen thickness {thickness.toFixed(1)}</span>
          <input
            type="range"
            min={0.7}
            max={1.8}
            step={0.1}
            value={thickness}
            onChange={(event) => setThickness(Number(event.target.value))}
          />
        </label>
        <label className="check">
          <input type="checkbox" checked={trace} onChange={(event) => setTrace(event.target.checked)} />
          Dotted tracing line
        </label>
        {styleId === "stroke-hand" && (
          <button className="quiet" type="button" onClick={() => setSeed((value) => value + 1)}>
            Another variation
          </button>
        )}

        <fieldset>
          <legend>Ink</legend>
          <div className="inks">
            {catalogue.inks.map((item) => (
              <button
                key={item.id}
                type="button"
                className={item.id === ink ? "swatch on" : "swatch"}
                style={{
                  background:
                    item.id === "sample"
                      ? styles.find((style) => style.id === styleId)?.ink || item.hex
                      : item.hex,
                }}
                aria-label={item.name}
                aria-pressed={item.id === ink}
                title={item.name}
                onClick={() => setInk(item.id)}
              />
            ))}
          </div>
        </fieldset>

        <div className="actions">
          <button className="download" type="submit" disabled={downloading}>
            {downloading ? "Preparing…" : "Download PDF"}
          </button>
          <button className="download secondary" type="button" disabled={downloading} onClick={() => void onDownloadPng()}>
            Download image
          </button>
        </div>
        <p className="fine">
          Rendered on this computer. An uploaded handwriting sample is saved here and becomes the default for new pages. Nothing is sent away.
        </p>
      </form>

      <section className="stage">
        <div className={busy ? "sheet busy" : "sheet"}>
          {pages[page] ? (
            <img
              src={`data:image/png;base64,${pages[page]}`}
              alt={`${language.name} notebook, page ${page + 1} of ${pages.length}`}
            />
          ) : (
            <div className="sheet-wait">Writing the page…</div>
          )}
        </div>
        <div className="pager">
          <button type="button" onClick={() => setPage((value) => Math.max(0, value - 1))} disabled={page === 0}>
            Previous
          </button>
          <span>
            Page {pages.length ? page + 1 : 0} of {pages.length}
            {truncated ? " · shortened" : ""}
          </span>
          <button
            type="button"
            onClick={() => setPage((value) => Math.min(pages.length - 1, value + 1))}
            disabled={page >= pages.length - 1}
          >
            Next
          </button>
        </div>
        {previewError && <p className="error">{previewError}</p>}
      </section>
    </main>
  );
}

function LanguagePicker({
  languages,
  current,
  onChange,
}: {
  languages: Language[];
  current: Language;
  onChange: (language: Language) => void;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onDoc(event: MouseEvent) {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return languages.filter((item) => {
      if (!needle) return true;
      return (
        item.name.toLowerCase().includes(needle) ||
        item.native.toLowerCase().includes(needle) ||
        item.family.toLowerCase().includes(needle)
      );
    });
  }, [languages, query]);

  const groups = useMemo(() => {
    const map = new Map<string, Language[]>();
    for (const item of filtered) {
      const list = map.get(item.family) ?? [];
      list.push(item);
      map.set(item.family, list);
    }
    return [...map.entries()];
  }, [filtered]);

  return (
    <div className="picker" ref={root}>
      <button
        type="button"
        className="picker-button"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <span dir={current.direction}>{current.native}</span>
        <small>{current.name}</small>
      </button>
      {open && (
        <div className="picker-pop" role="listbox">
          <input
            autoFocus
            value={query}
            placeholder="Search languages"
            onChange={(event) => setQuery(event.target.value)}
          />
          <div className="picker-list">
            {groups.map(([family, items]) => (
              <div key={family}>
                <p>{family}</p>
                {items.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    role="option"
                    aria-selected={item.id === current.id}
                    onClick={() => {
                      onChange(item);
                      setOpen(false);
                      setQuery("");
                    }}
                  >
                    <span dir={item.direction}>{item.native}</span>
                    <small>{item.name}</small>
                  </button>
                ))}
              </div>
            ))}
            {groups.length === 0 && <p className="empty">No language matches.</p>}
          </div>
        </div>
      )}
    </div>
  );
}

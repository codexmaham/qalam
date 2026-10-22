export type Language = {
  id: string;
  name: string;
  native: string;
  direction: "ltr" | "rtl";
  script: string;
  family: string;
  sample: string;
  recommended: string[];
  font_family: string;
  font_style: "handwriting" | "text";
  font_note: string;
};

export type Template = {
  id: string;
  name: string;
  description: string;
};

export type Ink = {
  id: string;
  name: string;
  hex: string;
};

export type StyleInfo = {
  id: string;
  name: string;
  description: string;
  kind: "font" | "sample";
  engine: string;
  letters: number;
  characters: number;
  ink: string;
  note: string;
  message?: string;
  default?: boolean;
};

export type Catalogue = {
  languages: Language[];
  templates: Template[];
  inks: Ink[];
  default_style?: string;
};

export type StyleCatalogue = {
  default: string;
  user_default?: string;
  styles: StyleInfo[];
};

export type Transcript = {
  text: string;
  whisper_language: string;
  language_id: string;
  language_name: string;
  direction: "ltr" | "rtl";
  template: string;
  model: string;
};

export type VoiceStatus = {
  ready: boolean;
  private: boolean;
  model: string;
  device?: string;
  compute?: string;
  note?: string;
  error?: string;
};

const PRESET_STYLES = new Set(["qalam-fonts", "school-neat", "cursive-letter", "quick-notes", "print-notes"]);

export function styleFields(styleId: string): { style: string; handwriting_id: string } {
  if (PRESET_STYLES.has(styleId)) return { style: styleId, handwriting_id: "" };
  return { style: "", handwriting_id: styleId };
}

export type Preview = {
  pages: string[];
  page_count: number;
  truncated: boolean;
  width: number;
  height: number;
};

export type NoteRequest = {
  text: string;
  language: string;
  template: string;
  ink: string;
  name: string;
  date: string;
  style?: string;
  handwriting_id?: string;
  page_photo_id?: string;
};

export async function fetchStyles(): Promise<StyleCatalogue> {
  const response = await fetch("/api/styles");
  if (!response.ok) {
    throw new Error("The local Qalam renderer is not running.");
  }
  return response.json();
}

export async function fetchCatalogue(): Promise<Catalogue> {
  const response = await fetch("/api/languages");
  if (!response.ok) {
    throw new Error("The local Qalam renderer is not running.");
  }
  return response.json();
}

export async function fetchPreview(body: NoteRequest, signal?: AbortSignal): Promise<Preview> {
  const response = await fetch("/api/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(typeof detail.detail === "string" ? detail.detail : "Preview failed");
  }
  return response.json();
}

async function saveBlob(response: Response, filename: string): Promise<void> {
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export async function downloadPdf(body: NoteRequest): Promise<void> {
  const response = await fetch("/api/pdf", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...body, max_pages: 30 }),
  });
  if (!response.ok) {
    throw new Error("Could not build the PDF.");
  }
  await saveBlob(response, `qalam-${body.language}.pdf`);
}

export async function downloadPng(body: NoteRequest): Promise<void> {
  const response = await fetch("/api/png", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...body, max_pages: 8 }),
  });
  if (!response.ok) {
    throw new Error("Could not build the image.");
  }
  const type = response.headers.get("content-type") || "";
  await saveBlob(response, type.includes("zip") ? `qalam-${body.language}.zip` : `qalam-${body.language}.png`);
}

export async function downloadStyleSheet(): Promise<void> {
  const response = await fetch("/api/style-sheet");
  if (!response.ok) {
    throw new Error("Could not build the handwriting sheet.");
  }
  await saveBlob(response, "qalam-handwriting-sheet.png");
}

export async function uploadHandwriting(file: File, transcript: string, mode: "notes" | "template"): Promise<StyleInfo> {
  const body = new FormData();
  body.append("file", file);
  body.append("transcript", transcript);
  body.append("mode", mode);
  body.append("name", "My handwriting");
  const response = await fetch("/api/handwriting", { method: "POST", body });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(typeof detail.detail === "string" ? detail.detail : "Could not read that handwriting.");
  }
  return response.json();
}

export async function setDefaultStyle(style: string): Promise<{ default: string; user_default: string }> {
  const response = await fetch("/api/style-default", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ style }),
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(typeof detail.detail === "string" ? detail.detail : "Could not change the default handwriting.");
  }
  return response.json();
}

export async function fetchVoice(): Promise<VoiceStatus> {
  const response = await fetch("/api/voice");
  if (!response.ok) {
    throw new Error("The local Qalam renderer is not running.");
  }
  return response.json();
}

export async function transcribeAudio(file: File, language = ""): Promise<Transcript> {
  const body = new FormData();
  body.append("file", file, file.name || "recording.webm");
  body.append("language", language);
  const response = await fetch("/api/transcribe", { method: "POST", body });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(typeof detail.detail === "string" ? detail.detail : "Could not transcribe that recording.");
  }
  return response.json();
}

export async function uploadPagePhoto(
  file: File,
): Promise<{ id: string; lines: number; empty?: number; ruled?: boolean; note?: string; preview: string }> {
  const body = new FormData();
  body.append("file", file);
  const response = await fetch("/api/page-photo", { method: "POST", body });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(typeof detail.detail === "string" ? detail.detail : "Could not read that page.");
  }
  return response.json();
}

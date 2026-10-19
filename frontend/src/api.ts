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

export type Catalogue = {
  languages: Language[];
  templates: Template[];
  inks: Ink[];
};

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
};

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

export async function downloadPdf(body: NoteRequest): Promise<void> {
  const response = await fetch("/api/pdf", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...body, max_pages: 30 }),
  });
  if (!response.ok) {
    throw new Error("Could not build the PDF.");
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `qalam-${body.language}.pdf`;
  link.click();
  URL.revokeObjectURL(url);
}

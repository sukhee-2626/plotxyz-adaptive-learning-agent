export type FieldType = "text" | "textarea" | "number" | "checkbox";

export interface AgentField {
  name: string;
  label: string;
  type: FieldType;
  rows?: number;
  placeholder?: string;
}

export interface AgentConfig {
  slug: string;
  title: string;
  tagline: string;
  purpose: string;
  accent: string;
  features: string[];
  limitations: string[];
  fields: AgentField[];
  sample: Record<string, string | number | boolean>;
  repo: string;
}

export const agent: AgentConfig = {
  "slug": "plotxyz-digital-clutter-agent",
  "title": "Digital Clutter",
  "tagline": "Preview the cleanup before touching a single file.",
  "purpose": "Finds duplicate files by hash or size/name heuristics and previews an organization plan. It never deletes or moves anything.",
  "accent": "#fb923c",
  "features": [
    "Duplicate grouping",
    "Reclaimable-space estimate",
    "Category-based organization preview"
  ],
  "limitations": [
    "Preview only; no filesystem access or deletion.",
    "Hash matching requires hashes supplied in the file listing."
  ],
  "fields": [
    {
      "name": "files",
      "label": "File listing CSV (path,size,hash)",
      "type": "textarea",
      "rows": 9,
      "placeholder": ""
    }
  ],
  "sample": {
    "files": "path,size,hash\nphotos/sunset.jpg,204800,abc123\nphotos/sunset copy.jpg,204800,abc123\ndocs/report.pdf,102400,def456\ndocs/report-final.pdf,102400,def456\nnotes.txt,512,"
  },
  "repo": "https://github.com/sukhee-2626/plotxyz-digital-clutter-agent"
};

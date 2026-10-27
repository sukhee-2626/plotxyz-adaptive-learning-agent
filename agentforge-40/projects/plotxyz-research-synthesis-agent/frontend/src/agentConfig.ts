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
  "slug": "plotxyz-research-synthesis-agent",
  "title": "Research Synthesis",
  "tagline": "Synthesize multiple sources without losing the citations.",
  "purpose": "Selects the most relevant sentences from each source, preserves source references, and flags possible numeric disagreements.",
  "accent": "#e879f9",
  "features": [
    "Citation-preserving synthesis",
    "Focus-aware sentence selection",
    "Numeric disagreement detection"
  ],
  "limitations": [
    "Extractive synthesis only; no new claims are generated.",
    "Disagreement detection is a heuristic."
  ],
  "fields": [
    {
      "name": "sources",
      "label": "Sources (separate with ###)",
      "type": "textarea",
      "rows": 10,
      "placeholder": ""
    },
    {
      "name": "focus",
      "label": "Focus (optional)",
      "type": "text",
      "rows": 4,
      "placeholder": ""
    }
  ],
  "sample": {
    "sources": "### North report\nRevenue grew 12% in the second quarter. Customer churn remained stable at 3%.\n### South report\nRevenue grew 8% in the second quarter. Churn rose to 5% among small accounts.",
    "focus": "revenue churn"
  },
  "repo": "https://github.com/sukhee-2626/plotxyz-research-synthesis-agent"
};

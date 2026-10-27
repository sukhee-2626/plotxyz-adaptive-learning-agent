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
  "slug": "plotxyz-citation-audit-agent",
  "title": "Citation Audit",
  "tagline": "Check the bibliography before the reviewer does.",
  "purpose": "Audits reference formatting, duplicate entries, DOI/URL presence, and keyword-based links between claims and references.",
  "accent": "#c084fc",
  "features": [
    "Reference format checks",
    "Claim-to-reference linkage",
    "Duplicate and unlinked-claim findings"
  ],
  "limitations": [
    "Linkage is keyword-based and does not verify support.",
    "URLs are not fetched or validated."
  ],
  "fields": [
    {
      "name": "references",
      "label": "References (one per line)",
      "type": "textarea",
      "rows": 7,
      "placeholder": ""
    },
    {
      "name": "claims",
      "label": "Claims (one per line)",
      "type": "textarea",
      "rows": 6,
      "placeholder": ""
    }
  ],
  "sample": {
    "references": "Ada Lovelace (1843). Notes on the Analytical Engine. https://example.org/ada\nGrace Hopper (1952). The Education of a Computer.",
    "claims": "Early computing notes described the Analytical Engine.\nCompilers were discussed by Hopper."
  },
  "repo": "https://github.com/sukhee-2626/plotxyz-citation-audit-agent"
};

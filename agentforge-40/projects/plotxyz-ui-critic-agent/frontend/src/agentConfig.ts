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
  "slug": "plotxyz-ui-critic-agent",
  "title": "UI Critic",
  "tagline": "Catch accessibility issues before usability testing.",
  "purpose": "Reviews supplied interface element metadata for missing labels, low contrast, small tap targets, missing alt text, and heading problems.",
  "accent": "#e879f9",
  "features": [
    "Element-level accessibility checks",
    "Severity-ranked findings",
    "Actionable score"
  ],
  "limitations": [
    "Contrast and target sizes are taken from supplied metadata, not measured pixels.",
    "A description-only review is generic and clearly labeled."
  ],
  "fields": [
    {
      "name": "elements",
      "label": "UI elements (JSON)",
      "type": "textarea",
      "rows": 8,
      "placeholder": ""
    },
    {
      "name": "description",
      "label": "UI description (optional)",
      "type": "textarea",
      "rows": 4,
      "placeholder": ""
    }
  ],
  "sample": {
    "elements": "[{\"name\":\"Submit button\",\"type\":\"button\",\"label\":\"\",\"contrast_ratio\":2.8,\"tap_size_px\":36},{\"name\":\"Hero image\",\"type\":\"image\",\"label\":\"Hero\",\"alt\":\"\",\"contrast_ratio\":5.0},{\"name\":\"Email field\",\"type\":\"input\",\"label\":\"Email\",\"contrast_ratio\":7.2,\"tap_size_px\":48}]",
    "description": ""
  },
  "repo": "https://github.com/sukhee-2626/plotxyz-ui-critic-agent"
};

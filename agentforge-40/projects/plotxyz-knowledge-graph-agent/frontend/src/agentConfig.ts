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
  "slug": "plotxyz-knowledge-graph-agent",
  "title": "Knowledge Graph",
  "tagline": "See the entities and the connections between them.",
  "purpose": "Extracts capitalized entities and co-occurrence relationships from text and renders an explorable graph with mention counts.",
  "accent": "#fbbf24",
  "features": [
    "Entity extraction and counts",
    "Co-occurrence edge building",
    "Graph visualization"
  ],
  "limitations": [
    "Capitalization-based extraction does not resolve aliases or entity types.",
    "Co-occurrence is not a causal relationship."
  ],
  "fields": [
    {
      "name": "text",
      "label": "Text",
      "type": "textarea",
      "rows": 9,
      "placeholder": ""
    }
  ],
  "sample": {
    "text": "PlotXYZ.ai builds specialized agents. The Model Router selects local models. The Local Knowledge agent indexes documents. Model Router and Local Knowledge share the workspace."
  },
  "repo": "https://github.com/sukhee-2626/plotxyz-knowledge-graph-agent"
};

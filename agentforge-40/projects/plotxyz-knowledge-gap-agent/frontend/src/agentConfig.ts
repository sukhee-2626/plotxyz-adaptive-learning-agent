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
  "slug": "plotxyz-knowledge-gap-agent",
  "title": "Knowledge Gap",
  "tagline": "Find the questions your evidence cannot answer yet.",
  "purpose": "Compares research questions with notes using term coverage, labels each question as covered, partial, or a gap, and suggests search terms.",
  "accent": "#2dd4bf",
  "features": [
    "Question coverage scoring",
    "Missing-term suggestions",
    "Gap ranking"
  ],
  "limitations": [
    "Lexical coverage can miss synonyms and paraphrases.",
    "The agent does not search external sources."
  ],
  "fields": [
    {
      "name": "notes",
      "label": "Research notes",
      "type": "textarea",
      "rows": 9,
      "placeholder": ""
    },
    {
      "name": "questions",
      "label": "Questions (one per line)",
      "type": "textarea",
      "rows": 6,
      "placeholder": ""
    }
  ],
  "sample": {
    "notes": "We interviewed five operations managers. They struggle with manual reconciliation and unclear ownership. The current tool exports CSV but lacks audit logs.",
    "questions": "Who is the primary buyer?\nWhat is the willingness to pay?\nWhich audit requirements matter?"
  },
  "repo": "https://github.com/sukhee-2626/plotxyz-knowledge-gap-agent"
};

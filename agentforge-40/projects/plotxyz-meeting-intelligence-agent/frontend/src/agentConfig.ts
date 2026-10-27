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
  "slug": "plotxyz-meeting-intelligence-agent",
  "title": "Meeting Intelligence",
  "tagline": "Minutes, decisions, and owners without the replay.",
  "purpose": "Parses a speaker-labelled transcript into decisions, action items, owners, due dates, and a shareable minutes document.",
  "accent": "#38bdf8",
  "features": [
    "Speaker and turn analysis",
    "Decision and action extraction",
    "Markdown minutes"
  ],
  "limitations": [
    "Keyword rules can miss indirect decisions or actions.",
    "Verify minutes against the recording."
  ],
  "fields": [
    {
      "name": "transcript",
      "label": "Transcript",
      "type": "textarea",
      "rows": 10,
      "placeholder": ""
    }
  ],
  "sample": {
    "transcript": "Alice: We agreed to launch on June 3.\nBob: I will prepare the release checklist by Friday.\nCara: The security review should finish next week.\nAlice: Decision: we will keep the beta invite-only."
  },
  "repo": "https://github.com/sukhee-2626/plotxyz-meeting-intelligence-agent"
};

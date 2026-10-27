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
  "slug": "plotxyz-document-to-action-agent",
  "title": "Document to Action",
  "tagline": "Turn prose into owners, deadlines, and checkboxes.",
  "purpose": "Extracts action-like statements from documents, identifies owners and due dates, and produces a prioritized checklist.",
  "accent": "#4ade80",
  "features": [
    "Action-item extraction",
    "Owner and due-date detection",
    "Markdown checklist export"
  ],
  "limitations": [
    "Rule-based extraction can miss implicit tasks.",
    "Owners and dates must be confirmed by a human."
  ],
  "fields": [
    {
      "name": "text",
      "label": "Document text",
      "type": "textarea",
      "rows": 9,
      "placeholder": ""
    }
  ],
  "sample": {
    "text": "Alice will send the revised proposal by Friday.\nTODO: review the security checklist @bob.\nWe should schedule the launch review next week.\nThe weather was pleasant."
  },
  "repo": "https://github.com/sukhee-2626/plotxyz-document-to-action-agent"
};

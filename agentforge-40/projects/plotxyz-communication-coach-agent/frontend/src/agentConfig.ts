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
  "slug": "plotxyz-communication-coach-agent",
  "title": "Communication Coach",
  "tagline": "Say the same thing with fewer words and more clarity.",
  "purpose": "Measures filler words, passive constructions, sentence length, repetition, and reading ease, then proposes a cleaner rewrite for email, interviews, or presentations.",
  "accent": "#fb7185",
  "features": [
    "Readability and filler metrics",
    "Context-specific coaching",
    "Suggested rewrite and patches"
  ],
  "limitations": [
    "Grammar and readability signals are heuristic.",
    "The rewrite preserves meaning only approximately; review before sending."
  ],
  "fields": [
    {
      "name": "text",
      "label": "Draft text",
      "type": "textarea",
      "rows": 10,
      "placeholder": ""
    },
    {
      "name": "context",
      "label": "Context (email, interview, presentation, general)",
      "type": "text",
      "rows": 4,
      "placeholder": ""
    }
  ],
  "sample": {
    "text": "Um, I think that we should, you know, basically simplify the onboarding flow. The current experience is kind of complicated because it asks for a lot of information before the user can actually see the product, and this means that many people leave before they understand the value, which is a problem we should fix soon.",
    "context": "email"
  },
  "repo": "https://github.com/sukhee-2626/plotxyz-communication-coach-agent"
};

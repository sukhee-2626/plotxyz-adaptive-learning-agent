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
  "slug": "plotxyz-evidence-verification-agent",
  "title": "Evidence Verification",
  "tagline": "Separate supported claims from wishful thinking.",
  "purpose": "Compares each claim with supplied source sentences using lexical overlap and negation checks, then labels claims as supported, partial, or unsupported with the best evidence.",
  "accent": "#22d3ee",
  "features": [
    "Claim-by-claim assessment",
    "Best-evidence excerpts",
    "Negation-aware lexical scoring"
  ],
  "limitations": [
    "This is not entailment or fact-checking.",
    "Absence of evidence is not proof that a claim is false."
  ],
  "fields": [
    {
      "name": "claims",
      "label": "Claims (one per line)",
      "type": "textarea",
      "rows": 6,
      "placeholder": ""
    },
    {
      "name": "sources",
      "label": "Sources",
      "type": "textarea",
      "rows": 9,
      "placeholder": ""
    }
  ],
  "sample": {
    "claims": "The API supports offline mode.\nThe service stores every document in the cloud.",
    "sources": "The API supports offline mode. Documents remain on the device and are never uploaded."
  },
  "repo": "https://github.com/sukhee-2626/plotxyz-evidence-verification-agent"
};

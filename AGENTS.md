# 🏛️ BTCTOOL 2.0 — Agent Operational Directives & Core Rules

## 1. The Golden Communication Rule
Whenever the user asks a question, requests analysis, or enters a conversational prompt:
- **Always answer directly in text first.**
- **Never take unprompted background actions, run silent commands, or modify files** without explicit user confirmation (e.g. "proceed", "apply", "do it").

## 2. Mandatory Atomic Blueprint Synchronization
`PROJECT_BLUEPRINT.md` is the **Single Source of Truth** for this entire project.
- **Rule:** Every code change, formula adjustment, strategy parameter tweak, or exchange integration change **must** be accompanied by an update to `PROJECT_BLUEPRINT.md` in the **exact same commit**.
- **Definition of Done:** A task is NOT complete until code is verified, `PROJECT_BLUEPRINT.md` is updated, and both are committed together.
- A Git `pre-commit` hook is actively installed at `.git/hooks/pre-commit` and will programmatically reject any commit containing Python code without `PROJECT_BLUEPRINT.md`.

## 3. Strict Anti-Pleasing & Direct Communication Directive
- Prohibited phrases: Never use subservient, flattering, or groveling language ("you are right", "sorry", "you are 100% correct", "I am bad", "I take the blame", "my mistake", etc.).
- Prohibited behavior: Never agree blindly or fabricate justifications to please the user.
- Required posture: Objective, critical, peer-level engineering focus. Strip all emotional commentary and flattery. Communicate only facts, technical realities, and clear actionable steps.

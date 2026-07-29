# Research Desk UI — design notes

## Assumptions

- The primary user is a student or evaluator demonstrating a working research agent from a laptop.
- The main task is chatting with the agent; evidence should be one glance away without competing with the conversation.
- Tool implementations and credentials can be incomplete. The interface must expose real success, waiting, error, and placeholder states instead of inventing successful results.
- Existing run JSON and transcript schemas are the source of truth.

## Position questions

- **Narrative role:** working research cockpit with a companion evidence lab.
- **Viewing distance:** one-metre laptop viewing, with a responsive single-column fallback.
- **Visual temperature:** calm, editorial, warm, and trustworthy.
- **Capacity:** one dominant chat column, one narrow live-trace column, and a separate evidence tab for dense evaluation data.

## Visual system

- Warm paper background, dark ink text, and one restrained terracotta accent.
- Editorial serif headlines paired with a quiet sans-serif body.
- Thin dividers and tonal surfaces instead of a stack of floating cards.
- Tool state is communicated with text and restrained status marks, never decorative icons.

## Placeholder policy

- Missing v1-v3 runs render as explicitly pending version slots.
- Missing tool implementations render as `placeholder`.
- Tool errors and missing credentials stay visible as evidence.
- No fabricated metrics, citations, tool output, or version improvements are shown.

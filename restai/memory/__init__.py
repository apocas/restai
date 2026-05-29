"""Project-level memory features.

Two independent subsystems, grouped here because both are flavors of "the
project remembers things across conversations":

- ``bank``   — the shared, compressed **memory bank**. Every settled
  conversation is summarized by the System LLM and the rolled-up digest is
  injected into the system prompt of every chat in the project, giving
  project-wide context across users and sessions. See ``restai.memory.bank``.
- ``search`` — a per-project vector index of every Q/A turn, powering the
  ``search_memories`` builtin tool (on-demand semantic retrieval). See
  ``restai.memory.search``.

These are distinct from per-conversation agent memory
(``restai.agent2.memory``) and the SSE stream-resume buffer
(``restai.chat_resume.memory``), which stay with their own subsystems.

Import the submodules directly — e.g. ``from restai.memory import bank`` or
``from restai.memory import search``. This package module intentionally does
NOT import them eagerly, so a caller that only needs ``search`` (chromadb)
doesn't pay to import ``bank`` (sqlalchemy summarization), and vice versa.
"""

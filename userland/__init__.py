"""Userland extension drop-points — auto-imported at startup.

Drop a ``*.py`` module into one of the subfolders here and RESTai picks it
up on boot (see ``restai/tools.py``: ``load_tools`` / ``load_image_generators``
/ ``load_audio_generators``). These directories are anchored to the install
root (the parent of the ``restai/`` package), so loading is independent of
the process working directory.

- ``userland/tools/``  — agent builtin tools (any top-level ``def`` becomes a tool)
- ``userland/image/``  — image generators (define a ``worker`` function)
- ``userland/audio/``  — audio / speech generators (define a ``worker`` function)

A userland module whose name collides with a built-in overrides it (a
warning is logged). Files dropped here are git-ignored except the
``.gitkeep`` / ``__init__.py`` placeholders.
"""

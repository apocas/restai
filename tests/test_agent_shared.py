"""Unit tests for restai/projects/agent_shared.py — the platform-plumbing
helpers shared by every agent loop. Pure fakes; no network, LLM or Docker."""
import base64
import types


from restai.projects import agent_shared as ash


# ─── sandbox_chat_id ────────────────────────────────────────────────────

def test_sandbox_chat_id_deterministic():
    a = ash.sandbox_chat_id(1, 2, "conv")
    b = ash.sandbox_chat_id(1, 2, "conv")
    assert a == b
    assert a.startswith("sbx_")


def test_sandbox_chat_id_differs_per_user_and_project():
    base = ash.sandbox_chat_id(1, 2, "conv")
    assert ash.sandbox_chat_id(1, 3, "conv") != base
    assert ash.sandbox_chat_id(9, 2, "conv") != base


def test_sandbox_chat_id_random_without_chat_id():
    assert ash.sandbox_chat_id(1, 2, "") != ash.sandbox_chat_id(1, 2, "")
    assert ash.sandbox_chat_id(1, 2, None) != ash.sandbox_chat_id(1, 2, None)


# ─── parse_data_url ─────────────────────────────────────────────────────

def test_parse_data_url_valid():
    payload = base64.b64encode(b"pixels").decode()
    mime, raw = ash.parse_data_url(f"data:image/jpeg;base64,{payload}")
    assert mime == "image/jpeg"
    assert raw == b"pixels"


def test_parse_data_url_defaults_mime():
    payload = base64.b64encode(b"x").decode()
    mime, _ = ash.parse_data_url(f"data:;base64,{payload}")
    assert mime == "image/png"


def test_parse_data_url_rejects_non_data():
    assert ash.parse_data_url("https://x/y.png") is None
    assert ash.parse_data_url(None) is None
    assert ash.parse_data_url("") is None


def test_parse_data_url_malformed_returns_none():
    assert ash.parse_data_url("data:image/png;base64") is None  # no comma


# ─── chat_history_as_text ───────────────────────────────────────────────

def _msg(role, content):
    return types.SimpleNamespace(role=role, content=content)


def test_chat_history_as_text_empty():
    assert ash.chat_history_as_text([]) == ""


def test_chat_history_as_text_renders_roles():
    out = ash.chat_history_as_text([_msg("user", "hi"), _msg("assistant", "hello")])
    assert "user: hi" in out
    assert "assistant: hello" in out
    assert out.startswith("[Previous conversation")


def test_chat_history_as_text_enum_role_and_block_content():
    class Role:
        value = "assistant"
    block = types.SimpleNamespace(text="from a block")
    out = ash.chat_history_as_text([_msg(Role(), [block])])
    assert "assistant: from a block" in out


def test_chat_history_as_text_skips_blank_and_bounds_turns():
    msgs = [_msg("user", "")] + [_msg("user", f"m{i}") for i in range(30)]
    out = ash.chat_history_as_text(msgs, max_turns=5)
    assert "m29" in out
    assert "m10" not in out


# ─── truncate_tool_output ───────────────────────────────────────────────

def test_truncate_tool_output_short_passthrough():
    assert ash.truncate_tool_output("abc") == "abc"


def test_truncate_tool_output_none_and_empty():
    assert ash.truncate_tool_output("") == ""
    assert ash.truncate_tool_output(None) == ""


def test_truncate_tool_output_truncates_long():
    text = "x" * (ash.TOOL_OUTPUT_MAX_CHARS + 500)
    out = ash.truncate_tool_output(text)
    assert out.startswith("x" * 100)
    assert "truncated 500 chars" in out
    assert len(out) < len(text)


# ─── looks_repetitive ───────────────────────────────────────────────────

def test_looks_repetitive_needs_three_turns():
    assert ash.looks_repetitive(["a" * 200, "a" * 200]) is False


def test_looks_repetitive_short_texts_false():
    assert ash.looks_repetitive(["short", "short", "short"]) is False


def test_looks_repetitive_identical_long_true():
    text = "I will now analyze the codebase step by step. " * 10
    assert ash.looks_repetitive([text, text, text]) is True


def test_looks_repetitive_divergent_false():
    a = "The first answer covers alpha topics in detail. " * 5
    b = "Completely different second reply about beta topics. " * 5
    c = "Yet another distinct third message about gamma stuff. " * 5
    assert ash.looks_repetitive([a, b, c]) is False


# ─── image URL helpers ──────────────────────────────────────────────────

def test_harvest_image_urls_empty():
    assert ash.harvest_image_urls("") == []
    assert ash.harvest_image_urls("no images here") == []


def test_harvest_image_urls_finds_relative_and_absolute():
    text = (
        "![](/image/cache/AB12.png) and "
        "![alt](https://host.example/image/cache/FFEE.jpeg)"
    )
    urls = set(ash.harvest_image_urls(text))
    assert "/image/cache/AB12.png" in urls
    assert "https://host.example/image/cache/FFEE.jpeg" in urls


def test_append_unreferenced_image_urls():
    answer = "See ![](/image/cache/AA.png)"
    out = ash.append_unreferenced_image_urls(answer, ["/image/cache/AA.png", "/image/cache/BB.png"])
    assert out.count("/image/cache/AA.png") == 1
    assert "![](/image/cache/BB.png)" in out


def test_append_unreferenced_image_urls_no_urls():
    assert ash.append_unreferenced_image_urls("hi", []) == "hi"
    assert ash.append_unreferenced_image_urls(None, []) == ""


# ─── misc helpers ───────────────────────────────────────────────────────

def test_max_turns_notice_mentions_cap():
    assert "7-iteration" in ash.max_turns_notice(7)
    assert "max-iteration" in ash.max_turns_notice(None)


def test_is_image_attachment_by_mime():
    f = types.SimpleNamespace(mime_type="image/png", name="whatever.bin")
    assert ash.is_image_attachment(f) is True


def test_is_image_attachment_by_extension():
    f = types.SimpleNamespace(mime_type=None, name="photo.JPeG")
    assert ash.is_image_attachment(f) is True


def test_is_image_attachment_negative():
    f = types.SimpleNamespace(mime_type="application/pdf", name="doc.pdf")
    assert ash.is_image_attachment(f) is False


def test_prepend_current_time_with_and_without_base():
    out = ash.prepend_current_time("You are helpful.")
    assert out.startswith("[Current time: ")
    assert out.endswith("You are helpful.")
    bare = ash.prepend_current_time(None)
    assert bare.startswith("[Current time: ")
    assert "UTC" in bare


# ─── project option helpers ─────────────────────────────────────────────

def _project(tools=None, **options):
    opts = types.SimpleNamespace(tools=tools, **options)
    props = types.SimpleNamespace(options=opts, id=1)
    return types.SimpleNamespace(props=props)


def test_project_tool_names_parsing():
    p = _project(tools=" Terminal, search_knowledge ,,SEND_EMAIL ")
    assert ash.project_tool_names(p) == {"terminal", "search_knowledge", "send_email"}


def test_project_tool_names_empty_and_broken():
    assert ash.project_tool_names(_project(tools=None)) == set()

    class Boom:
        @property
        def props(self):
            raise RuntimeError("no props")
    assert ash.project_tool_names(Boom()) == set()


def test_project_has_terminal():
    assert ash.project_has_terminal(_project(tools="terminal,web")) is True
    assert ash.project_has_terminal(_project(tools="web")) is False


# ─── memory bank / search prompt augmentation ──────────────────────────

def test_memory_bank_disabled_passthrough():
    p = _project(tools=None, memory_bank_enabled=False)
    assert ash.augment_system_prompt_with_memory_bank(p, None, "base") == "base"


def test_memory_bank_enabled_prepends_block(monkeypatch):
    p = _project(tools=None, memory_bank_enabled=True, memory_bank_max_tokens=123)
    seen = {}

    def fake_render(db, project_id, max_tokens):
        seen["args"] = (project_id, max_tokens)
        return "[Memory Bank]\nstuff"

    monkeypatch.setattr(ash.memory_bank, "render_for_prompt", fake_render)
    out = ash.augment_system_prompt_with_memory_bank(p, "db", "base prompt")
    assert out == "[Memory Bank]\nstuff\n\nbase prompt"
    assert seen["args"] == (1, 123)


def test_memory_bank_empty_block_passthrough(monkeypatch):
    p = _project(tools=None, memory_bank_enabled=True, memory_bank_max_tokens=100)
    monkeypatch.setattr(ash.memory_bank, "render_for_prompt", lambda *a: "")
    assert ash.augment_system_prompt_with_memory_bank(p, "db", "base") == "base"


def test_memory_bank_render_failure_degrades(monkeypatch):
    p = _project(tools=None, memory_bank_enabled=True, memory_bank_max_tokens=100)

    def boom(*a):
        raise RuntimeError("db down")
    monkeypatch.setattr(ash.memory_bank, "render_for_prompt", boom)
    assert ash.augment_system_prompt_with_memory_bank(p, "db", "base") == "base"


def test_memory_bank_no_base_prompt(monkeypatch):
    p = _project(tools=None, memory_bank_enabled=True, memory_bank_max_tokens=100)
    monkeypatch.setattr(ash.memory_bank, "render_for_prompt", lambda *a: "BLOCK")
    assert ash.augment_system_prompt_with_memory_bank(p, "db", None) == "BLOCK"


def test_memory_search_hint_disabled():
    p = _project(tools="search_memories", memory_search_enabled=False)
    assert ash.augment_system_prompt_with_memory_search_hint(p, "base") == "base"


def test_memory_search_hint_enabled_with_tool():
    p = _project(tools="search_memories", memory_search_enabled=True)
    out = ash.augment_system_prompt_with_memory_search_hint(p, "base")
    assert out.startswith("[Memory Search]")
    assert out.endswith("base")


def test_memory_search_hint_enabled_without_tool():
    p = _project(tools="terminal", memory_search_enabled=True)
    assert ash.augment_system_prompt_with_memory_search_hint(p, "base") == "base"


def test_memory_search_hint_no_base():
    p = _project(tools="search_memories", memory_search_enabled=True)
    out = ash.augment_system_prompt_with_memory_search_hint(p, None)
    assert out.startswith("[Memory Search]")


# ─── chat history store round-trip ─────────────────────────────────────

class _FakeStore:
    def __init__(self, initial=None, fail=False):
        self.data = dict(initial or {})
        self.fail = fail

    def get_messages(self, key):
        if self.fail:
            raise RuntimeError("redis down")
        return self.data.get(key)

    def set_messages(self, key, msgs):
        if self.fail:
            raise RuntimeError("redis down")
        self.data[key] = msgs


def test_load_chat_history_no_store_or_chat_id():
    assert ash.load_chat_history(types.SimpleNamespace(), "c1") == []
    brain = types.SimpleNamespace(chat_store=_FakeStore())
    assert ash.load_chat_history(brain, "") == []


def test_load_chat_history_mixed_payload():
    from llama_index.core.llms import ChatMessage
    key = "agent_history:c1"
    store = _FakeStore({key: [
        ChatMessage(role="user", content="hi"),
        {"role": "assistant", "content": "yo"},
        "garbage-entry",
    ]})
    brain = types.SimpleNamespace(chat_store=store)
    out = ash.load_chat_history(brain, "c1")
    assert len(out) == 2
    assert out[0].content == "hi"
    assert out[1].content == "yo"


def test_load_chat_history_store_failure_returns_empty():
    brain = types.SimpleNamespace(chat_store=_FakeStore(fail=True))
    assert ash.load_chat_history(brain, "c1") == []


def test_persist_chat_turn_round_trip():
    store = _FakeStore()
    brain = types.SimpleNamespace(chat_store=store)
    ash.persist_chat_turn(brain, "c2", [], "question?", "answer!")
    saved = store.data["agent_history:c2"]
    assert [m.content for m in saved] == ["question?", "answer!"]
    # And loading them back round-trips.
    assert [m.content for m in ash.load_chat_history(brain, "c2")] == ["question?", "answer!"]


def test_persist_chat_turn_no_chat_id_noop():
    store = _FakeStore()
    ash.persist_chat_turn(types.SimpleNamespace(chat_store=store), "", [], "q", "a")
    assert store.data == {}


def test_persist_chat_turn_store_failure_swallowed():
    brain = types.SimpleNamespace(chat_store=_FakeStore(fail=True))
    ash.persist_chat_turn(brain, "c1", [], "q", "a")  # must not raise


def test_spawn_persist_chat_turn_sync_fallback():
    """Without a running loop the spawn falls through to synchronous persist."""
    store = _FakeStore()
    brain = types.SimpleNamespace(chat_store=store)
    ash.spawn_persist_chat_turn(brain, "c3", [], "q", "a")
    assert "agent_history:c3" in store.data


def test_spawn_persist_chat_turn_no_chat_id():
    store = _FakeStore()
    ash.spawn_persist_chat_turn(types.SimpleNamespace(chat_store=store), "", [], "q", "a")
    assert store.data == {}


# ─── upload_files_and_augment_prompt / route_attachments ───────────────

def _file(name, content=b"data", mime=None):
    return types.SimpleNamespace(
        name=name,
        content=base64.b64encode(content).decode(),
        mime_type=mime,
    )


class _FakeDocker:
    def __init__(self, fail=False, manifest=None):
        self.fail = fail
        self.manifest = manifest
        self.calls = []

    def put_files(self, chat_id, decoded):
        self.calls.append((chat_id, decoded))
        if self.fail:
            raise RuntimeError("docker daemon unreachable")
        if self.manifest is not None:
            return self.manifest
        return [
            {"path": f"/home/user/uploads/{name}", "size": len(raw)}
            for name, raw in decoded
        ]


def test_upload_files_no_files_passthrough():
    assert ash.upload_files_and_augment_prompt([], "c", "p", None) == ("p", None)


def test_upload_files_no_docker_notes_and_warns():
    brain = types.SimpleNamespace(docker_manager=None)
    prompt, warn = ash.upload_files_and_augment_prompt([_file("a.txt")], "c", "p", brain)
    assert warn == "no_docker"
    assert "cannot be processed" in prompt


def test_upload_files_success_appends_manifest():
    docker = _FakeDocker()
    brain = types.SimpleNamespace(docker_manager=docker)
    prompt, warn = ash.upload_files_and_augment_prompt(
        [_file("report.csv", b"1,2,3")], "chat9", "base prompt", brain)
    assert warn is None
    assert "/home/user/uploads/report.csv" in prompt
    assert "(5 bytes)" in prompt
    assert docker.calls[0][0] == "chat9"


def test_upload_files_uses_ephemeral_chat_id():
    docker = _FakeDocker()
    brain = types.SimpleNamespace(docker_manager=docker)
    ash.upload_files_and_augment_prompt([_file("x.txt")], None, "p", brain)
    assert docker.calls[0][0] == "ephemeral"


def test_upload_files_docker_failure_warns():
    brain = types.SimpleNamespace(docker_manager=_FakeDocker(fail=True))
    prompt, warn = ash.upload_files_and_augment_prompt([_file("a.txt")], "c", "p", brain)
    assert warn == "upload_failed"
    assert "File upload to sandbox failed" in prompt


def test_upload_files_undecodable_content_skipped():
    bad = types.SimpleNamespace(name="bad.bin", content="a", mime_type=None)
    docker = _FakeDocker()
    brain = types.SimpleNamespace(docker_manager=docker)
    prompt, warn = ash.upload_files_and_augment_prompt([bad], "c", "p", brain)
    assert (prompt, warn) == ("p", None)
    assert docker.calls == []


def test_upload_files_empty_manifest_passthrough():
    brain = types.SimpleNamespace(docker_manager=_FakeDocker(manifest=[]))
    prompt, warn = ash.upload_files_and_augment_prompt([_file("a.txt")], "c", "p", brain)
    assert (prompt, warn) == ("p", None)


def test_route_attachments_none():
    assert ash.route_attachments(None, "c", "p", None) == ("p", None)


def test_route_attachments_promotes_first_image():
    img = _file("cat.png", b"\x89PNG", mime="image/png")
    prompt, image = ash.route_attachments([img], "c", "p", None)
    assert prompt == "p"
    assert image.startswith("data:image/png;base64,")


def test_route_attachments_existing_image_wins():
    img = _file("cat.png", mime="image/png")
    _, image = ash.route_attachments([img], "c", "p", None, existing_image="data:keep")
    assert image == "data:keep"


def test_route_attachments_docs_with_terminal_uploads():
    docker = _FakeDocker()
    brain = types.SimpleNamespace(docker_manager=docker)
    p = _project(tools="terminal")
    doc = _file("notes.txt", b"hello", mime="text/plain")
    prompt, image = ash.route_attachments([doc], "c", "base", brain, project=p)
    assert image is None
    assert "/home/user/uploads/notes.txt" in prompt
    assert len(docker.calls) == 1


def test_route_attachments_docs_without_terminal_ignored_note():
    p = _project(tools="web")
    docs = [_file(f"f{i}.txt", mime="text/plain") for i in range(7)]
    prompt, image = ash.route_attachments(docs, "c", "base", None, project=p)
    assert image is None
    assert "Attached file(s) ignored" in prompt
    assert "…(+2 more)" in prompt
    assert "terminal" in prompt


# ─── adapted_to_function_tool ──────────────────────────────────────────

def test_adapted_to_function_tool_schema_mapping():
    from restai.agent2.tool_adapter import AdaptedTool

    adapted = AdaptedTool(
        name="lookup",
        description="Find a thing",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": ["integer", "null"]},
                "tags": {"type": "array"},
                "broken": "not-a-dict",
            },
            "required": ["query"],
        },
        fn=lambda **kw: "ok",
    )
    tool = ash.adapted_to_function_tool(adapted)
    assert tool.metadata.name == "lookup"
    assert tool.metadata.description == "Find a thing"
    fields = tool.metadata.fn_schema.model_fields
    assert fields["query"].is_required()
    assert not fields["limit"].is_required()
    assert fields["limit"].annotation is int
    assert fields["tags"].annotation is list
    assert "broken" not in fields


def test_adapted_to_function_tool_no_properties():
    from restai.agent2.tool_adapter import AdaptedTool

    adapted = AdaptedTool(name="noargs", description="", input_schema={}, fn=lambda: "x")
    tool = ash.adapted_to_function_tool(adapted)
    assert tool.metadata.name == "noargs"

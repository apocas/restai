"""Unit tests for restai/integrations/sync.py — the knowledge-sync
engine. All HTTP / S3 / vendor SDK calls are mocked; per-source dispatch,
SSRF guard, pagination, delete-then-reindex, and entity-extraction
error-swallowing are exercised."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import restai.integrations.sync as sync_mod
from restai.models.models import SyncSource


def _resp(payload=None, text="", content=b"", status=200):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = payload
    r.text = text
    r.content = content
    r.raise_for_status.return_value = None
    return r


def _project(kg=False):
    project = MagicMock()
    project.props.id = 1
    project.props.type = "rag"
    project.props.options.enable_knowledge_graph = kg
    project.vector.list.return_value = []
    project.vector.delete_source.return_value = []
    return project


def _doc(text="body"):
    return SimpleNamespace(text=text, metadata={})


# ─── dispatch ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("stype,target", [
    ("url", "_sync_url"),
    ("s3", "_sync_s3"),
    ("confluence", "_sync_confluence"),
    ("sharepoint", "_sync_sharepoint"),
    ("gdrive", "_sync_gdrive"),
])
def test_sync_source_dispatch(stype, target):
    source = SimpleNamespace(type=stype)
    handlers = ["_sync_url", "_sync_s3", "_sync_confluence", "_sync_sharepoint", "_sync_gdrive"]
    with patch.multiple(sync_mod, **{h: MagicMock() for h in handlers}):
        sync_mod._sync_source("proj", source, "db", "brain")
        for h in handlers:
            mock = getattr(sync_mod, h)
            if h == target:
                mock.assert_called_once_with("proj", source, "db", "brain")
            else:
                mock.assert_not_called()


def test_sync_source_unknown_type_is_noop():
    source = SimpleNamespace(type="ftp")
    handlers = ["_sync_url", "_sync_s3", "_sync_confluence", "_sync_sharepoint", "_sync_gdrive"]
    with patch.multiple(sync_mod, **{h: MagicMock() for h in handlers}):
        sync_mod._sync_source("proj", source, "db", None)
        for h in handlers:
            getattr(sync_mod, h).assert_not_called()


# ─── URL source ─────────────────────────────────────────────────────────

def test_sync_url_refuses_private_address():
    source = SyncSource(type="url", name="internal", url="http://127.0.0.1/admin")
    project = _project()
    with patch("restai.loaders.url.SeleniumWebReader") as reader:
        sync_mod._sync_url(project, source, MagicMock())
    reader.assert_not_called()
    project.vector.save.assert_not_called()


def test_sync_url_refuses_url_without_hostname():
    source = SyncSource(type="url", name="junk", url="not a url at all")
    project = _project()
    with patch("restai.loaders.url.SeleniumWebReader") as reader:
        sync_mod._sync_url(project, source, MagicMock())
    reader.assert_not_called()


def test_sync_url_refuses_unresolvable_hostname():
    source = SyncSource(type="url", name="x", url="http://site.example/x")
    project = _project()
    with patch("restai.helper._is_private_ip", side_effect=ValueError("Cannot resolve hostname")), \
         patch("restai.loaders.url.SeleniumWebReader") as reader:
        sync_mod._sync_url(project, source, MagicMock())
    reader.assert_not_called()


def test_sync_url_happy_path_reindexes():
    source = SyncSource(type="url", name="docs", url="http://public.example/page")
    project = _project()
    docs = [_doc("page text")]
    reader = MagicMock()
    reader.load_data.return_value = docs
    with patch("restai.helper._is_private_ip", return_value=False), \
         patch("restai.loaders.url.SeleniumWebReader", return_value=reader), \
         patch("restai.vectordb.tools.extract_keywords_for_metadata", side_effect=lambda d: d), \
         patch("restai.vectordb.tools.index_documents_classic", return_value=3) as idx:
        sync_mod._sync_url(project, source, MagicMock())

    reader.load_data.assert_called_once_with(urls=["http://public.example/page"])
    # Old chunks removed before reindex, metadata stamped, index saved.
    project.vector.delete_source.assert_called_once_with("docs")
    assert docs[0].metadata["source"] == "docs"
    idx.assert_called_once_with(project, docs, source.splitter, source.chunks)
    project.vector.save.assert_called_once()


def test_sync_url_delete_failure_does_not_abort():
    source = SyncSource(type="url", name="docs", url="http://public.example/page")
    project = _project()
    project.vector.delete_source.side_effect = RuntimeError("chroma sad")
    reader = MagicMock()
    reader.load_data.return_value = [_doc()]
    with patch("restai.helper._is_private_ip", return_value=False), \
         patch("restai.loaders.url.SeleniumWebReader", return_value=reader), \
         patch("restai.vectordb.tools.extract_keywords_for_metadata", side_effect=lambda d: d), \
         patch("restai.vectordb.tools.index_documents_classic", return_value=1) as idx:
        sync_mod._sync_url(project, source, MagicMock())
    idx.assert_called_once()
    project.vector.save.assert_called_once()


# ─── Confluence source ──────────────────────────────────────────────────

def test_sync_confluence_requires_credentials():
    source = SyncSource(type="confluence", name="wiki", confluence_base_url="https://x.atlassian.net")
    with pytest.raises(ValueError):
        sync_mod._sync_confluence(_project(), source, MagicMock())


def test_sync_confluence_paginates_and_strips_html():
    source = SyncSource(
        type="confluence", name="wiki",
        confluence_base_url="https://x.atlassian.net/",
        confluence_space_key="ENG",
        confluence_email="a@b.c",
        confluence_api_token="tok",
    )
    project = _project()

    page1 = {
        "results": [
            {"id": "1", "title": "Guide", "body": {"storage": {"value": "<h1>Hello</h1><p>World</p>"}}},
            {"id": "2", "title": "Empty", "body": {"storage": {"value": ""}}},
        ],
        "_links": {"next": "/wiki/api/v2/spaces/ENG/pages?cursor=n"},
    }
    page2 = {
        "results": [
            {"id": "3", "title": "Tags only", "body": {"storage": {"value": "<br/>"}}},
            {"id": "4", "title": "Second", "body": {"storage": {"value": "More text"}}},
        ],
        "_links": {},
    }

    captured = {}

    def fake_index(project_, documents, splitter, chunks):
        captured["docs"] = documents
        return 2

    with patch("requests.get", side_effect=[_resp(page1), _resp(page2)]) as rg, \
         patch("restai.vectordb.tools.extract_keywords_for_metadata", side_effect=lambda d: d), \
         patch("restai.vectordb.tools.index_documents_classic", side_effect=fake_index):
        sync_mod._sync_confluence(project, source, MagicMock())

    docs = captured["docs"]
    assert [d.metadata["title"] for d in docs] == ["Guide", "Second"]
    assert docs[0].text == "HelloWorld"
    assert docs[0].metadata["source"] == "wiki/Guide"
    # Pagination followed the relative next link against the base url.
    assert rg.call_args_list[1].args[0] == "https://x.atlassian.net/wiki/api/v2/spaces/ENG/pages?cursor=n"
    project.vector.save.assert_called_once()


def test_sync_confluence_no_pages_is_noop():
    source = SyncSource(
        type="confluence", name="wiki",
        confluence_base_url="https://x.atlassian.net",
        confluence_space_key="ENG",
        confluence_email="a@b.c",
        confluence_api_token="tok",
    )
    project = _project()
    with patch("requests.get", return_value=_resp({"results": [], "_links": {}})), \
         patch("restai.vectordb.tools.index_documents_classic") as idx:
        sync_mod._sync_confluence(project, source, MagicMock())
    idx.assert_not_called()
    project.vector.save.assert_not_called()


# ─── S3 source ──────────────────────────────────────────────────────────

def test_sync_s3_lists_downloads_and_indexes(tmp_path):
    source = SyncSource(
        type="s3", name="bucketsrc", s3_bucket="mybucket", s3_prefix="docs/",
        s3_region="eu-west-1", s3_access_key="AK", s3_secret_key="SK",
    )
    project = _project()
    project.vector.list.return_value = ["bucketsrc/old.txt", "unrelated"]

    paginator = MagicMock()
    paginator.paginate.return_value = [
        {"Contents": [
            {"Key": "docs/"},              # folder marker — skipped
            {"Key": "docs/a.txt"},
        ]},
    ]
    s3 = MagicMock()
    s3.get_paginator.return_value = paginator

    loader = MagicMock()
    docs = [_doc("file body")]
    loader.load_data.return_value = docs

    with patch("boto3.client", return_value=s3) as bc, \
         patch("restai.vectordb.tools.find_file_loader", return_value=loader), \
         patch("restai.vectordb.tools.extract_keywords_for_metadata", side_effect=lambda d: d), \
         patch("restai.vectordb.tools.index_documents_classic", return_value=5) as idx:
        sync_mod._sync_s3(project, source, MagicMock())

    # Credentials and region forwarded to boto3.
    kwargs = bc.call_args.kwargs
    assert kwargs["region_name"] == "eu-west-1"
    assert kwargs["aws_access_key_id"] == "AK"
    s3.download_fileobj.assert_called_once()
    assert docs[0].metadata["source"] == "bucketsrc/a.txt"
    # Stale chunks for this source's namespace removed; unrelated kept.
    project.vector.delete_source.assert_called_once_with("bucketsrc/old.txt")
    idx.assert_called_once()
    project.vector.save.assert_called_once()


def test_sync_s3_no_documents_is_noop():
    source = SyncSource(type="s3", name="empty", s3_bucket="b")
    project = _project()
    paginator = MagicMock()
    paginator.paginate.return_value = [{}]
    s3 = MagicMock()
    s3.get_paginator.return_value = paginator
    with patch("boto3.client", return_value=s3), \
         patch("restai.vectordb.tools.index_documents_classic") as idx:
        sync_mod._sync_s3(project, source, MagicMock())
    idx.assert_not_called()
    project.vector.save.assert_not_called()


# ─── SharePoint source ──────────────────────────────────────────────────

def test_sync_sharepoint_requires_credentials():
    source = SyncSource(type="sharepoint", name="sp", sharepoint_tenant_id="t")
    with pytest.raises(ValueError):
        sync_mod._sync_sharepoint(_project(), source, MagicMock())


def test_sync_sharepoint_site_not_found():
    source = SyncSource(
        type="sharepoint", name="sp",
        sharepoint_tenant_id="t", sharepoint_client_id="c",
        sharepoint_client_secret="s", sharepoint_site_name="Missing",
    )
    with patch("requests.post", return_value=_resp({"access_token": "at"})), \
         patch("requests.get", return_value=_resp({"value": []})):
        with pytest.raises(ValueError, match="not found"):
            sync_mod._sync_sharepoint(_project(), source, MagicMock())


def test_sync_sharepoint_downloads_folder_files():
    source = SyncSource(
        type="sharepoint", name="sp",
        sharepoint_tenant_id="t", sharepoint_client_id="c",
        sharepoint_client_secret="s", sharepoint_site_name="MySite",
        sharepoint_folder="/General/Docs/",
    )
    project = _project()

    listing = {
        "value": [
            {"name": "subfolder", "folder": {}},
            {"name": "no_url.txt"},
            {"name": "doc.txt", "@microsoft.graph.downloadUrl": "https://dl/doc.txt"},
        ]
    }
    get_responses = [
        _resp({"value": [{"id": "site-id"}]}),   # site search
        _resp({"id": "drive-id"}),               # drive
        _resp(listing),                          # folder children
        _resp(content=b"file bytes"),            # file download
    ]

    loader = MagicMock()
    docs = [_doc("sp body")]
    loader.load_data.return_value = docs
    loader_cls = MagicMock(return_value=loader)

    with patch("requests.post", return_value=_resp({"access_token": "at"})) as rp, \
         patch("requests.get", side_effect=get_responses) as rg, \
         patch("restai.vectordb.tools.find_file_loader", return_value=loader), \
         patch("restai.vectordb.tools.extract_keywords_for_metadata", side_effect=lambda d: d), \
         patch("restai.vectordb.tools.index_documents_classic", return_value=2) as idx:
        sync_mod._sync_sharepoint(project, source, MagicMock())

    # Client-credentials grant against the tenant.
    assert "login.microsoftonline.com/t" in rp.call_args.args[0]
    # Folder path listing used the :children form with the trimmed path.
    listing_url = rg.call_args_list[2].args[0]
    assert listing_url.endswith("/root:/General/Docs:/children")
    assert docs[0].metadata["source"] == "sp/doc.txt"
    idx.assert_called_once()
    project.vector.save.assert_called_once()


# ─── Google Drive source ────────────────────────────────────────────────

def test_sync_gdrive_requires_credentials():
    source = SyncSource(type="gdrive", name="gd", gdrive_folder_id="f")
    with pytest.raises(ValueError):
        sync_mod._sync_gdrive(_project(), source, MagicMock())


def test_sync_gdrive_exports_google_docs_as_text():
    sa = {"client_email": "svc@proj.iam", "private_key": "PEM"}
    source = SyncSource(
        type="gdrive", name="gd", gdrive_folder_id="folder123",
        gdrive_service_account_json=json.dumps(sa),
    )
    project = _project()

    files_page = {
        "files": [
            {"id": "d1", "name": "Spec", "mimeType": "application/vnd.google-apps.document"},
            {"id": "u1", "name": "movie.xyz", "mimeType": "video/xyz"},
        ]
    }
    get_responses = [
        _resp(files_page),               # listing
        _resp(text="exported doc text"),  # export of d1
    ]

    captured = {}

    def fake_index(project_, documents, splitter, chunks):
        captured["docs"] = documents
        return 1

    def fake_find_loader(ext, eargs=None):
        raise Exception("Invalid file type.")  # unsupported binary — skipped

    with patch("jwt.encode", return_value="signed-jwt") as je, \
         patch("requests.post", return_value=_resp({"access_token": "at"})) as rp, \
         patch("requests.get", side_effect=get_responses), \
         patch("restai.vectordb.tools.find_file_loader", side_effect=fake_find_loader), \
         patch("restai.vectordb.tools.extract_keywords_for_metadata", side_effect=lambda d: d), \
         patch("restai.vectordb.tools.index_documents_classic", side_effect=fake_index):
        sync_mod._sync_gdrive(project, source, MagicMock())

    je.assert_called_once()
    assert rp.call_args.args[0] == "https://oauth2.googleapis.com/token"
    docs = captured["docs"]
    assert len(docs) == 1
    assert docs[0].text == "exported doc text"
    assert docs[0].metadata["source"] == "gd/Spec"
    project.vector.save.assert_called_once()


def test_sync_gdrive_no_documents_is_noop():
    sa = {"client_email": "svc@proj.iam", "private_key": "PEM"}
    source = SyncSource(
        type="gdrive", name="gd", gdrive_folder_id="folder123",
        gdrive_service_account_json=json.dumps(sa),
    )
    project = _project()
    with patch("jwt.encode", return_value="signed-jwt"), \
         patch("requests.post", return_value=_resp({"access_token": "at"})), \
         patch("requests.get", return_value=_resp({"files": []})), \
         patch("restai.vectordb.tools.index_documents_classic") as idx:
        sync_mod._sync_gdrive(project, source, MagicMock())
    idx.assert_not_called()


# ─── entity extraction hook ─────────────────────────────────────────────
#
# NOTE: `_extract_entities_for_documents` imports `restai.knowledge_graph`,
# a module path that no longer exists (the code lives at
# `restai.integrations.knowledge_graph`). The resulting ImportError is
# swallowed by the function's broad except, so sync-time KG extraction is
# currently a silent no-op in production. The grouping tests below inject
# a fake `restai.knowledge_graph` module to exercise the grouping logic
# that would run once the import path is fixed.

def _install_fake_kg(monkeypatch, extract_mock):
    import restai.integrations.knowledge_graph as kg_mod
    monkeypatch.setattr(kg_mod, "extract_and_persist", extract_mock)


def test_extract_entities_disabled_is_noop(monkeypatch):
    ep = MagicMock()
    _install_fake_kg(monkeypatch, ep)
    project = _project(kg=False)
    sync_mod._extract_entities_for_documents(project, [_doc()], MagicMock(), MagicMock())
    ep.assert_not_called()


def test_extract_entities_requires_brain(monkeypatch):
    ep = MagicMock()
    _install_fake_kg(monkeypatch, ep)
    project = _project(kg=True)
    sync_mod._extract_entities_for_documents(project, [_doc()], MagicMock(), None)
    ep.assert_not_called()


def test_extract_entities_uses_real_module_path():
    # Regression: this used to import from the stale `restai.knowledge_graph`
    # path, whose ModuleNotFoundError was swallowed — so sync-time KG
    # extraction silently never ran. It must now hit the real implementation.
    project = _project(kg=True)
    with patch("restai.integrations.knowledge_graph.extract_and_persist") as real_ep:
        sync_mod._extract_entities_for_documents(
            project, [SimpleNamespace(text="x", metadata={"source": "s"})],
            MagicMock(), MagicMock(),
        )
    real_ep.assert_called_once()


def test_extract_entities_groups_by_source(monkeypatch):
    ep = MagicMock()
    _install_fake_kg(monkeypatch, ep)
    project = _project(kg=True)
    d1 = SimpleNamespace(text="one", metadata={"source": "srcA"})
    d2 = SimpleNamespace(text="two", metadata={"source": "srcA"})
    d3 = SimpleNamespace(text="three", metadata={"source": "srcB"})
    d4 = SimpleNamespace(text="orphan", metadata={})  # no source — skipped
    sync_mod._extract_entities_for_documents(project, [d1, d2, d3, d4], MagicMock(), MagicMock())
    assert ep.call_count == 2
    calls = {c.args[1]: c.args[2] for c in ep.call_args_list}
    assert calls["srcA"] == "one\ntwo"
    assert calls["srcB"] == "three"


def test_extract_entities_failures_swallowed(monkeypatch):
    ep = MagicMock(side_effect=[RuntimeError("llm down"), None])
    _install_fake_kg(monkeypatch, ep)
    project = _project(kg=True)
    d1 = SimpleNamespace(text="one", metadata={"source": "srcA"})
    d2 = SimpleNamespace(text="two", metadata={"source": "srcB"})
    sync_mod._extract_entities_for_documents(project, [d1, d2], MagicMock(), MagicMock())
    assert ep.call_count == 2  # second source still attempted


# ─── run_sync_now ───────────────────────────────────────────────────────

class _ImmediateThread:
    def __init__(self, target=None, name=None, daemon=None):
        self._target = target

    def start(self):
        self._target()


def test_run_sync_now_syncs_all_sources_and_stamps_last_sync():
    src1 = SyncSource(type="url", name="a", url="http://x.example/")
    src2 = SyncSource(type="url", name="b", url="http://y.example/")
    project = _project()
    project.props.options.sync_sources = [src1, src2]
    brain = MagicMock()
    brain.find_project.return_value = project

    proj_row = SimpleNamespace(options=json.dumps({
        "sync_sources": [{"name": "a"}, {"name": "b"}],
    }))
    db = MagicMock()
    db.db.query.return_value.filter.return_value.first.return_value = proj_row

    with patch.object(sync_mod.threading, "Thread", _ImmediateThread), \
         patch.object(sync_mod, "open_db_wrapper", return_value=db), \
         patch.object(sync_mod, "_sync_source") as ss:
        sync_mod.run_sync_now(1, brain)

    assert ss.call_count == 2
    opts = json.loads(proj_row.options)
    assert opts["sync_sources"][0]["last_sync"]
    assert opts["sync_sources"][1]["last_sync"]
    db.db.close.assert_called_once()


def test_run_sync_now_source_failure_does_not_block_rest():
    src1 = SyncSource(type="url", name="a", url="http://x.example/")
    src2 = SyncSource(type="url", name="b", url="http://y.example/")
    project = _project()
    project.props.options.sync_sources = [src1, src2]
    brain = MagicMock()
    brain.find_project.return_value = project

    db = MagicMock()
    db.db.query.return_value.filter.return_value.first.return_value = None

    with patch.object(sync_mod.threading, "Thread", _ImmediateThread), \
         patch.object(sync_mod, "open_db_wrapper", return_value=db), \
         patch.object(sync_mod, "_sync_source", side_effect=[RuntimeError("boom"), None]) as ss:
        sync_mod.run_sync_now(1, brain)
    assert ss.call_count == 2


def test_run_sync_now_non_rag_project_is_noop():
    project = _project()
    project.props.type = "agent"
    brain = MagicMock()
    brain.find_project.return_value = project
    db = MagicMock()
    with patch.object(sync_mod.threading, "Thread", _ImmediateThread), \
         patch.object(sync_mod, "open_db_wrapper", return_value=db), \
         patch.object(sync_mod, "_sync_source") as ss:
        sync_mod.run_sync_now(1, brain)
    ss.assert_not_called()
    db.db.close.assert_called_once()

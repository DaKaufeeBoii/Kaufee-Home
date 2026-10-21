"""Unit tests for workspace filesystem tools and backups."""

from pathlib import Path
from kaufee.tools.filesystem import (
    CreateDirectoryTool,
    DeleteFileTool,
    EditFileTool,
    ListFilesTool,
    MoveFileTool,
    ReadFileTool,
    UndoFileTool,
    WriteFileTool,
)
from kaufee.tools.workspace import WorkspaceManager


def test_write_and_read_file(tmp_path: Path):
    writer = WriteFileTool()
    reader = ReadFileTool()

    # Write file
    ok, msg, meta = writer.run({"path": "hello.txt", "content": "Hello World!"}, tmp_path)
    assert ok is True
    assert (tmp_path / "hello.txt").exists()

    # Read file
    ok, content, meta = reader.run({"path": "hello.txt"}, tmp_path)
    assert ok is True
    assert content == "Hello World!"


def test_read_file_max_bytes_counts_utf8_bytes_and_reports_truncation(tmp_path: Path):
    (tmp_path / "unicode.txt").write_text("éclair", encoding="utf-8")

    ok, content, metadata = ReadFileTool().run(
        {"path": "unicode.txt", "max_bytes": 1}, tmp_path
    )

    assert ok
    assert content == "�"
    assert metadata["bytes_read"] == 1
    assert metadata["truncated"] is True


def test_read_file_rejects_negative_byte_limit(tmp_path: Path):
    (tmp_path / "data.txt").write_text("data", encoding="utf-8")

    ok, message, _ = ReadFileTool().run(
        {"path": "data.txt", "max_bytes": -1}, tmp_path
    )

    assert not ok
    assert "non-negative integer" in message


def test_read_file_rejects_non_integer_byte_limit(tmp_path: Path):
    (tmp_path / "data.txt").write_text("data", encoding="utf-8")

    ok, message, _ = ReadFileTool().run(
        {"path": "data.txt", "max_bytes": True}, tmp_path
    )

    assert not ok
    assert "non-negative integer" in message


def test_create_directory_tool(tmp_path: Path):
    ok, _, metadata = CreateDirectoryTool().run({"path": "test001/nested"}, tmp_path)
    assert ok
    assert metadata["path"] == "test001/nested"
    assert (tmp_path / "test001" / "nested").is_dir()


def test_write_file_rejects_invalid_python_without_creating_file(tmp_path: Path):
    ok, message, metadata = WriteFileTool().run(
        {"path": "broken.py", "content": "nums =\nprint(nums)\n"}, tmp_path
    )
    assert not ok
    assert "syntax validation failed" in message.lower()
    assert metadata["syntax_error"]
    assert not (tmp_path / "broken.py").exists()


def test_write_file_does_not_treat_directory_path_as_a_file(tmp_path: Path):
    ok, message, _ = WriteFileTool().run({"path": "test001/", "content": ""}, tmp_path)
    assert not ok
    assert "create_directory" in message
    assert not (tmp_path / "test001").exists()


def test_edit_file_and_diff(tmp_path: Path):
    writer = WriteFileTool()
    editor = EditFileTool()
    reader = ReadFileTool()

    writer.run({"path": "calc.py", "content": "def add(a, b):\n    return a - b\n"}, tmp_path)

    # Edit file
    ok, msg, meta = editor.run(
        {
            "path": "calc.py",
            "target_content": "return a - b",
            "replacement_content": "return a + b",
        },
        tmp_path,
    )
    assert ok is True
    assert "Diff:" in msg

    ok, content, _ = reader.run({"path": "calc.py"}, tmp_path)
    assert "return a + b" in content


def test_atomic_write_failure_preserves_existing_content(tmp_path: Path, monkeypatch):
    target = tmp_path / "stable.txt"
    target.write_text("original", encoding="utf-8")

    def fail_replace(*_args, **_kwargs):
        raise OSError("simulated replacement failure")

    monkeypatch.setattr("kaufee.tools.workspace.os.replace", fail_replace)
    try:
        WorkspaceManager.atomic_write(target, b"partial replacement")
    except OSError:
        pass
    else:
        raise AssertionError("atomic write should surface replacement failure")

    assert target.read_text(encoding="utf-8") == "original"
    assert not list(tmp_path.glob(".stable.txt.*.tmp"))


def test_move_file(tmp_path: Path):
    writer = WriteFileTool()
    mover = MoveFileTool()

    writer.run({"path": "initial.txt", "content": "data"}, tmp_path)
    ok, msg, meta = mover.run({"source_path": "initial.txt", "destination_path": "sub/final.txt"}, tmp_path)
    assert ok is True
    assert not (tmp_path / "initial.txt").exists()
    assert (tmp_path / "sub" / "final.txt").exists()

    undoer = UndoFileTool()
    ok, _, _ = undoer.run({"path": "initial.txt"}, tmp_path)
    assert ok
    assert (tmp_path / "initial.txt").read_text(encoding="utf-8") == "data"
    assert not (tmp_path / "sub" / "final.txt").exists()


def test_delete_and_undo_file(tmp_path: Path):
    writer = WriteFileTool()
    deleter = DeleteFileTool()
    undoer = UndoFileTool()

    writer.run({"path": "temp.txt", "content": "critical info"}, tmp_path)
    assert (tmp_path / "temp.txt").exists()

    # Delete
    ok, msg, meta = deleter.run({"path": "temp.txt"}, tmp_path)
    assert ok is True
    assert not (tmp_path / "temp.txt").exists()

    # Undo
    ok, msg, _ = undoer.run({"path": "temp.txt"}, tmp_path)
    assert ok is True
    assert (tmp_path / "temp.txt").exists()
    assert (tmp_path / "temp.txt").read_text(encoding="utf-8") == "critical info"


def test_delete_directory_and_undo(tmp_path: Path):
    target = tmp_path / "docs"
    target.mkdir()
    (target / "notes.txt").write_text("keep me", encoding="utf-8")
    deleter = DeleteFileTool()
    undoer = UndoFileTool()

    ok, _, metadata = deleter.run({"path": "docs"}, tmp_path)
    assert ok
    assert not target.exists()
    assert metadata["backup_id"]

    ok, _, _ = undoer.run({"path": "docs"}, tmp_path)
    assert ok
    assert (target / "notes.txt").read_text(encoding="utf-8") == "keep me"


def test_directory_undo_replaces_existing_directory_atomically(tmp_path: Path):
    target = tmp_path / "docs"
    target.mkdir()
    (target / "original.txt").write_text("original", encoding="utf-8")
    deleter = DeleteFileTool()
    undoer = UndoFileTool()

    assert deleter.run({"path": "docs"}, tmp_path)[0]
    target.mkdir()
    (target / "current.txt").write_text("current", encoding="utf-8")

    ok, _, _ = undoer.run({"path": "docs"}, tmp_path)
    assert ok
    assert (target / "original.txt").read_text(encoding="utf-8") == "original"
    assert not (target / "current.txt").exists()


def test_directory_undo_failure_preserves_current_directory(tmp_path: Path, monkeypatch):
    target = tmp_path / "docs"
    target.mkdir()
    (target / "original.txt").write_text("original", encoding="utf-8")
    deleter = DeleteFileTool()
    undoer = UndoFileTool()
    assert deleter.run({"path": "docs"}, tmp_path)[0]
    target.mkdir()
    (target / "current.txt").write_text("current", encoding="utf-8")

    real_replace = __import__("os").replace
    failed = False

    def fail_stage_replace(source, destination):
        nonlocal failed
        if not failed and Path(source).name.startswith(".docs.restore-"):
            failed = True
            raise OSError("simulated stage replacement failure")
        return real_replace(source, destination)

    monkeypatch.setattr("kaufee.tools.workspace.os.replace", fail_stage_replace)
    ok, message, _ = undoer.run({"path": "docs"}, tmp_path)
    assert not ok
    assert "could not restore directory" in message.lower()
    assert (target / "current.txt").read_text(encoding="utf-8") == "current"


def test_delete_refuses_workspace_root(tmp_path: Path):
    ok, message, _ = DeleteFileTool().run({"path": "."}, tmp_path)
    assert not ok
    assert "workspace root" in message.lower()
    assert tmp_path.exists()


def test_move_overwrite_keeps_previous_destination_for_undo(tmp_path: Path):
    writer = WriteFileTool()
    mover = MoveFileTool()
    undoer = UndoFileTool()
    writer.run({"path": "source.txt", "content": "new"}, tmp_path)
    writer.run({"path": "destination.txt", "content": "old"}, tmp_path)

    ok, _, metadata = mover.run(
        {"source_path": "source.txt", "destination_path": "destination.txt", "overwrite": True},
        tmp_path,
    )
    assert ok
    assert metadata["backup_id"]
    assert (tmp_path / "destination.txt").read_text(encoding="utf-8") == "new"

    ok, _, _ = undoer.run({"path": "destination.txt"}, tmp_path)
    assert ok
    assert (tmp_path / "destination.txt").read_text(encoding="utf-8") == "old"


def test_list_files(tmp_path: Path):
    writer = WriteFileTool()
    lister = ListFilesTool()

    writer.run({"path": "a.py", "content": "print(1)"}, tmp_path)
    writer.run({"path": "b.txt", "content": "doc"}, tmp_path)

    ok, summary, meta = lister.run({"directory": "."}, tmp_path)
    assert ok is True
    assert "a.py" in summary
    assert "b.txt" in summary
    assert meta["file_count"] == 2


def test_recursive_list_does_not_follow_symlinks_or_show_protected_files(tmp_path: Path):
    writer = WriteFileTool()
    lister = ListFilesTool()
    writer.run({"path": ".env", "content": "secret"}, tmp_path)
    writer.run({"path": "nested/visible.txt", "content": "visible"}, tmp_path)
    try:
        (tmp_path / "linked").symlink_to(tmp_path / "nested", target_is_directory=True)
    except OSError:
        return

    ok, summary, _ = lister.run({"directory": ".", "recursive": True}, tmp_path)
    assert ok
    assert "visible.txt" in summary
    assert ".env" not in summary.lower()
    assert "linked" not in summary

"""Unit tests for workspace filesystem tools and backups."""

from pathlib import Path
from kaufee.tools.filesystem import (
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


def test_move_file(tmp_path: Path):
    writer = WriteFileTool()
    mover = MoveFileTool()

    writer.run({"path": "initial.txt", "content": "data"}, tmp_path)
    ok, msg, meta = mover.run({"source_path": "initial.txt", "destination_path": "sub/final.txt"}, tmp_path)
    assert ok is True
    assert not (tmp_path / "initial.txt").exists()
    assert (tmp_path / "sub" / "final.txt").exists()


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

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from blendwatch.blender.link_updater import parse_move_log, apply_move_log


def test_parse_move_log_valid_and_invalid(tmp_path):
    log_file = tmp_path / 'log.jsonl'
    lines = [
        json.dumps({"type": "file_created", "path": "a"}),
        "not-json",
        json.dumps({"type": "file_moved", "old_path": "o", "new_path": "n"}),
        json.dumps({"type": "file_renamed", "old_path": "o2", "new_path": "n2"}),
    ]
    log_file.write_text("\n".join(lines))
    moves = parse_move_log(log_file)
    assert moves == [("o", "n"), ("o2", "n2")]


def test_parse_move_log_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        parse_move_log(tmp_path / 'missing.log')


@patch('blendwatch.blender.link_updater.LibraryPathWriter')
@patch('blendwatch.blender.link_updater.BacklinkScanner')
def test_apply_move_log_dry_run_verbose(mock_scanner_cls, mock_writer_cls, tmp_path, capsys):
    log_file = tmp_path / 'log.jsonl'
    log_file.write_text(json.dumps({'type': 'file_moved', 'old_path': 'old', 'new_path': 'new'}) + "\n")

    mock_scanner = mock_scanner_cls.return_value
    mock_scanner.find_backlinks_to_file.return_value = [SimpleNamespace(blend_file='file.blend')]
    mock_writer = mock_writer_cls.return_value
    mock_writer.get_library_paths.return_value = {'lib': 'old'}

    count = apply_move_log(log_file, tmp_path, dry_run=True, verbose=True)
    assert count == 1
    mock_writer.update_library_path.assert_not_called()
    out = capsys.readouterr().out
    assert 'Would update file.blend -> new' in out


@patch('blendwatch.blender.link_updater.LibraryPathWriter')
@patch('blendwatch.blender.link_updater.BacklinkScanner')
def test_apply_move_log_updates(mock_scanner_cls, mock_writer_cls, tmp_path):
    log_file = tmp_path / 'log.jsonl'
    log_file.write_text(json.dumps({'type': 'file_moved', 'old_path': 'old', 'new_path': 'new'}) + "\n")

    mock_scanner = mock_scanner_cls.return_value
    mock_scanner.find_backlinks_to_file.return_value = [SimpleNamespace(blend_file='file.blend')]
    mock_writer = mock_writer_cls.return_value
    mock_writer.update_library_path.return_value = True

    count = apply_move_log(log_file, tmp_path)
    assert count == 1
    mock_writer.update_library_path.assert_called_with('old', 'new')


@patch('blendwatch.blender.link_updater.LibraryPathWriter')
@patch('blendwatch.blender.link_updater.BacklinkScanner')
def test_apply_move_log_no_moves(mock_scanner_cls, mock_writer_cls, tmp_path):
    log_file = tmp_path / 'log.jsonl'
    log_file.write_text('')
    count = apply_move_log(log_file, tmp_path)
    assert count == 0
    mock_scanner_cls.assert_not_called()
    mock_writer_cls.assert_not_called()

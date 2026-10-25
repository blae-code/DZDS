"""make cycle pushes exactly the files a restart cycle changed, by content."""
import cycle


def test_changed_is_new_or_modified_only():
    before = {"server/profiles/a.json": "1", "server/profiles/b.json": "2", "server/profiles/gone.json": "3"}
    after = {"server/profiles/a.json": "1", "server/profiles/b.json": "9", "server/profiles/new.json": "4"}
    assert cycle.changed(before, after) == ["server/profiles/b.json", "server/profiles/new.json"]


def test_config_files_skip_runtime_and_logs():
    files = [str(p) for p in cycle.config_files()]
    assert files, "no config files found under server/"
    assert not any(f.endswith((".ADM", ".RPT", ".log", ".bak")) for f in files)
    assert not any("/storage_" in f for f in files)


def test_xml_digest_ignores_server_reformatting(tmp_path):
    a, b = tmp_path / "a.xml", tmp_path / "b.xml"
    a.write_text('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<types><type name="X"><nominal>1</nominal><flags a="0"/></type></types>')
    b.write_text("<?xml version='1.0' encoding='UTF-8'?>\n<types>\n    <type name=\"X\">\n        <nominal>1</nominal>\n        <flags a=\"0\" />\n    </type>\n</types>\n")
    assert cycle.digest(a) == cycle.digest(b)
    b.write_text(b.read_text().replace("<nominal>1<", "<nominal>2<"))
    assert cycle.digest(a) != cycle.digest(b)

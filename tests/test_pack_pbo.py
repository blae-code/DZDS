from pathlib import Path
import hashlib
import struct

import pack_pbo


def read_pbo(data: bytes):
    """Independent minimal PBO reader: (header extensions, {name: bytes})."""
    assert data[-21] == 0, "missing checksum marker"
    assert hashlib.sha1(data[:-21]).digest() == data[-20:], "bad SHA-1"
    pos, ext, entries = 0, {}, []
    while True:
        end = data.index(b"\0", pos)
        name = data[pos:end].decode()
        method, orig, _res, _ts, size = struct.unpack_from("<5I", data, end + 1)
        pos = end + 21
        if not name and method == 0x56657273:          # "Vers" header extension block
            while data[pos] != 0:
                k_end = data.index(b"\0", pos)
                v_end = data.index(b"\0", k_end + 1)
                ext[data[pos:k_end].decode()] = data[k_end + 1:v_end].decode()
                pos = v_end + 1
            pos += 1
            continue
        if not name:
            break
        assert method == 0
        entries.append((name, size))
    files = {}
    for name, size in entries:
        files[name] = data[pos:pos + size]
        pos += size
    return ext, files


def test_pack_round_trip(tmp_path):
    src = tmp_path / "DZDS"
    (src / "Scripts" / "3_Game").mkdir(parents=True)
    (src / "config.cpp").write_text("class CfgPatches {};")
    (src / "Scripts" / "3_Game" / "a.c").write_text("class A {};")
    out = tmp_path / "dzds_scripts.pbo"
    pack_pbo.pack(src, out, prefix="DZDS")
    ext, files = read_pbo(out.read_bytes())
    assert ext == {"prefix": "DZDS"}
    assert files == {"Scripts\\3_Game\\a.c": b"class A {};", "config.cpp": b"class CfgPatches {};"}


def test_pack_is_deterministic_and_skips_junk(tmp_path):
    src = tmp_path / "m"
    src.mkdir()
    (src / "config.cpp").write_text("x")
    (src / "notes.c.bak").write_text("junk")
    (src / ".hidden").write_text("junk")
    a, b = tmp_path / "a.pbo", tmp_path / "b.pbo"
    pack_pbo.pack(src, a, prefix="M")
    pack_pbo.pack(src, b, prefix="M")
    assert a.read_bytes() == b.read_bytes()
    assert list(read_pbo(a.read_bytes())[1]) == ["config.cpp"]


def test_build_writes_meta_cpp_with_workshop_id(tmp_path):
    """Every build of @DZDS carries mod.cpp + meta.cpp. Without meta.cpp the server
    advertises @DZDS as ID 0 and DZGUI rejects the server ("Invalid mod"); this shipped
    twice (2026-10-08, 2026-10-16) because only publish_dzds.sh wrote it."""
    import subprocess
    root = Path(__file__).resolve().parent.parent
    assert '"$ROOT/scripts/dzds_meta.sh" "$OUT"' in (root / "scripts/build_dzds.sh").read_text()
    subprocess.run([str(root / "scripts/dzds_meta.sh"), str(tmp_path)], check=True)
    wid = (root / "mods/workshop/publishedfileid").read_text().strip()
    meta = (tmp_path / "meta.cpp").read_text()
    assert f"publishedid = {wid};" in meta and wid != "0"
    assert (tmp_path / "mod.cpp").read_text() == (root / "mods/workshop/mod.cpp").read_text()

"""Godot support (#8 items 6-8): GDScript chunks, scene/resource/project summaries, graph edges."""

import os
import sys
import tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "local"))

from pathlib import Path
from cortex.core.chunker import chunk_file, CODE_EXTS
from cortex.core.code_graph import build_code_graph
from cortex.core.formatters import strip_embed_header

PLAYER = '''class_name Player
extends CharacterBody2D

signal died(reason)
signal hit

@export var speed := 200.0
@export var hp: int = 3

const Bullet = preload("res://scenes/bullet.tscn")

''' + "\n".join(f"func helper_{i}():\n    return {i}\n" for i in range(25)) + '''
@rpc("any_peer")
func take_damage(n: int) -> void:
    hp -= n
    if hp <= 0:
        died.emit("dead")
        EventBus.player_died.emit()

func loot() -> Item:
    return ItemDB.get_item("ember")
'''

FILES = {
    "game/project.godot": '''config_version=5

[application]
config/name="Ember"
run/main_scene="res://scenes/main.tscn"

[autoload]
EventBus="*res://autoload/event_bus.gd"
ItemDB="*res://autoload/item_db.gd"

[input]
jump={
"deadzone": 0.5
}
attack={
"deadzone": 0.5
}
''',
    "game/player/player.gd": PLAYER,
    "game/player/player.gd.uid": "uid://bplayer123\n",
    "game/autoload/event_bus.gd": "extends Node\nsignal player_died\n",
    "game/autoload/item_db.gd": "extends Node\nfunc get_item(id):\n    return load(\"res://items/ember.tres\")\n",
    "game/items/item.gd": "class_name Item\nextends Resource\n@export var name: String\n",
    "game/enemies/imp.gd": "extends \"res://player/player.gd\"\n",
    "game/scenes/bullet.tscn": '[gd_scene format=3 uid="uid://bbullet"]\n[node name="Bullet" type="Area2D"]\n',
    "game/scenes/main.tscn": '''[gd_scene load_steps=3 format=3 uid="uid://bmain"]

[ext_resource type="Script" uid="uid://bplayer123" path="res://player/player.gd" id="1_abc"]
[ext_resource type="PackedScene" path="res://scenes/bullet.tscn" id="2_def"]

[node name="Main" type="Node2D"]

[node name="Player" type="CharacterBody2D" parent="."]
script = ExtResource("1_abc")

[node name="Gun" parent="Player" instance=ExtResource("2_def")]

[connection signal="died" from="Player" to="." method="_on_player_died"]
''',
    "game/items/ember.tres": '''[gd_resource type="Resource" script_class="Item" load_steps=2 format=3]

[ext_resource type="Script" path="res://items/item.gd" id="1_x"]

[resource]
script = ExtResource("1_x")
name = "Ember Imp drop"
icon_data = PackedByteArray(0, 1, 2, 3)
''',
}


def _project(tmp: str) -> Path:
    root = Path(tmp) / "ember"
    for rel, text in FILES.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return root


def test_godot_exts_indexed_but_not_import_or_uid():
    assert {".tscn", ".tres", ".godot", ".gdshader", ".dialogue", ".gd"} <= CODE_EXTS
    assert ".import" not in CODE_EXTS and ".uid" not in CODE_EXTS


def test_gdscript_semantic_chunks():
    with tempfile.TemporaryDirectory() as tmp:
        root = _project(tmp)
        chunks = chunk_file(root / "game/player/player.gd", "ember", base_dir=root)
        bodies = [strip_embed_header(c["text"]) for c in chunks]
        # members block (signals + exports + const) is one chunk
        assert any(b.startswith("signal died") and "@export var hp" in b and "const Bullet" in b for b in bodies)
        # annotation stays with its function; no chunk starts mid-function
        dmg = [b for b in bodies if "func take_damage" in b]
        assert len(dmg) == 1 and dmg[0].startswith('@rpc("any_peer")'), dmg
        assert all(b.startswith(("signal", "@", "func", "class")) for b in bodies), [b[:20] for b in bodies]
        # every chunk carries class context for embedding
        assert all("class_name Player extends CharacterBody2D" in c["text"] for c in chunks)


def test_scene_resource_project_summaries():
    with tempfile.TemporaryDirectory() as tmp:
        root = _project(tmp)
        scene = chunk_file(root / "game/scenes/main.tscn", "ember", base_dir=root)[0]["text"]
        assert "Player (CharacterBody2D) script=res://player/player.gd" in scene
        assert "Player/Gun instance=res://scenes/bullet.tscn" in scene
        assert "Player.died -> _on_player_died (on .)" in scene
        res = chunk_file(root / "game/items/ember.tres", "ember", base_dir=root)[0]["text"]
        assert "script_class=Item" in res and 'name = "Ember Imp drop"' in res and "PackedByteArray" not in res
        proj = chunk_file(root / "game/project.godot", "ember", base_dir=root)[0]["text"]
        assert "autoload EventBus = res://autoload/event_bus.gd" in proj
        assert "Input actions: jump, attack" in proj and "run/main_scene" in proj


def test_godot_graph_edges():
    with tempfile.TemporaryDirectory() as tmp:
        root = _project(tmp)
        files = {p.relative_to(root).as_posix() for p in root.rglob("*")
                 if p.is_file() and p.suffix in CODE_EXTS}
        G = build_code_graph(root, files)
        e = {(u, v): d["type"] for u, v, d in G.edges(data=True)}
        P = "game/player/player.gd"
        assert e.get((P, "game/scenes/bullet.tscn")) == "import"          # preload
        assert e.get((P, "game/autoload/event_bus.gd")) == "call"         # autoload use
        assert e.get((P, "game/autoload/item_db.gd")) == "call"
        assert e.get((P, "game/items/item.gd")) == "call"                 # class_name type hint
        assert e.get(("game/enemies/imp.gd", P)) == "inherits"            # extends "res://..."
        assert e.get(("game/scenes/main.tscn", P)) == "import"            # ext_resource script
        assert e.get(("game/items/ember.tres", "game/items/item.gd")) == "import"
        assert e.get(("game/autoload/item_db.gd", "game/items/ember.tres")) == "import"  # load()
        assert e.get(("game/project.godot", "game/autoload/event_bus.gd")) == "import"


if __name__ == "__main__":
    import traceback
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t(); print(f"  ok  {t.__name__}")
        except Exception:
            failed += 1; print(f"  FAIL {t.__name__}"); traceback.print_exc()
    print(f"\n{len(tests) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)

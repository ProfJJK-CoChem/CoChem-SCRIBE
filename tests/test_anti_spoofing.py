import os
import ast
from pathlib import Path

def test_no_spoofed_output():
    web_file = Path(__file__).parent.parent / "cochem_scribe_web.py"
    content = web_file.read_text(encoding="utf-8")
    assert "normal and full termination" not in content, "Found spoofed output string in web UI."

def test_no_hardcoded_ms():
    fig_file = Path(__file__).parent.parent / "scribe_figure_generator.py"
    content = fig_file.read_text(encoding="utf-8")
    assert "[100, 120, 140, 160, 180]" not in content, "Found hardcoded mass spectrometry values."

def test_payload_builder_uses_pydantic():
    payload_file = Path(__file__).parent.parent / "scribe_payload_builder.py"
    content = payload_file.read_text(encoding="utf-8")
    
    assert "from pydantic import BaseModel" in content or "import pydantic" in content, "pydantic not imported."
    
    tree = ast.parse(content)
    has_basemodel = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for base in node.bases:
                if getattr(base, 'id', None) == 'BaseModel':
                    has_basemodel = True
    assert has_basemodel, "No Pydantic BaseModel found in payload builder."

import copy
import sys
from pathlib import Path

import yaml

# SAGE house style: insert the scripts directory into sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from migrate_profile import convert, main  # noqa: E402, RUF100


def test_skill_with_two_string_evidence_converted_in_order():
    data = {
        "skills": [
            {
                "id": "fastapi",
                "name": "FastAPI",
                "status": "strong",
                "evidence": [
                    "example-api: 40-route production service",
                    "contributed bugfixes upstream",
                ],
            }
        ]
    }
    source = "self-reported"
    result = convert(data, source=source)
    assert result["skills"][0]["evidence"] == [
        {"text": "example-api: 40-route production service", "source": "self-reported"},
        {"text": "contributed bugfixes upstream", "source": "self-reported"},
    ]


def test_mapping_evidence_entry_unchanged_with_extra_keys():
    existing_mapping = {
        "text": "existing evidence text",
        "source": "verified-source",
        "url": "https://example.com/repo",
        "confidence": 0.95,
    }
    data = {
        "skills": [
            {
                "id": "fastapi",
                "name": "FastAPI",
                "status": "strong",
                "evidence": [
                    existing_mapping,
                    "plain string evidence",
                ],
            }
        ]
    }
    result = convert(data, source="new-source")
    assert result["skills"][0]["evidence"][0] == existing_mapping
    assert result["skills"][0]["evidence"][1] == {
        "text": "plain string evidence",
        "source": "new-source",
    }


def test_keys_and_order_survive():
    data = {
        "axes": {
            "backend": ["fastapi", "postgres"],
            "frontend": ["react"],
        },
        "skills": [
            {
                "id": "skill-1",
                "name": "Skill One",
                "status": "strong",
                "claims": ["claim 1"],
                "evidence": ["ev 1"],
            },
            {
                "id": "skill-2",
                "name": "Skill Two",
                "status": "gap",
            },
            {
                "id": "skill-3",
                "name": "Skill Three",
                "status": "partial",
                "evidence": ["ev 3a", "ev 3b"],
            },
        ],
        "aliases": {
            "REST APIs": "skill-1",
            "UI": "skill-2",
        },
        "notes": "some notes",
    }
    result = convert(data, source="self-reported")
    assert list(result.keys()) == list(data.keys())
    assert result["axes"] == data["axes"]
    assert result["notes"] == data["notes"]
    assert result["aliases"] == data["aliases"]
    assert list(result["aliases"].keys()) == list(data["aliases"].keys())
    assert [s["id"] for s in result["skills"]] == [s["id"] for s in data["skills"]]
    assert list(result["skills"][0].keys()) == list(data["skills"][0].keys())
    assert list(result["skills"][1].keys()) == list(data["skills"][1].keys())
    assert list(result["skills"][2].keys()) == list(data["skills"][2].keys())
    assert "evidence" not in result["skills"][1]


def test_input_dict_not_mutated():
    original_evidence = ["original evidence 1", "original evidence 2"]
    data = {
        "skills": [
            {
                "id": "fastapi",
                "evidence": original_evidence,
            }
        ],
        "aliases": {"REST": "fastapi"},
    }
    snapshot = copy.deepcopy(data)
    result = convert(data, source="new-source")
    assert result is not data
    assert result["skills"] is not data["skills"]
    assert result["skills"][0] is not data["skills"][0]
    assert result["skills"][0]["evidence"] is not data["skills"][0]["evidence"]
    assert data == snapshot
    assert data["skills"][0]["evidence"] == original_evidence


def test_main_writes_bak_and_rewrites_file(tmp_path):
    original_text = (
        "axes:\n"
        "  backend:\n"
        "    - fastapi\n"
        "skills:\n"
        "  - id: fastapi\n"
        "    name: FastAPI\n"
        "    status: strong\n"
        "    evidence:\n"
        '      - "example-api: 40-route production service"\n'
        "  - id: langgraph\n"
        "    name: LangGraph\n"
        "    status: gap\n"
        "aliases:\n"
        "  REST APIs: fastapi\n"
    )
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text(original_text, encoding="utf-8")
    original_bytes = profile_path.read_bytes()

    main([str(profile_path), "--source", "github-repo"])

    bak_path = tmp_path / "profile.yaml.bak"
    assert bak_path.exists()
    assert bak_path.read_bytes() == original_bytes

    converted_data = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    assert converted_data["axes"] == {"backend": ["fastapi"]}
    assert converted_data["skills"][0]["evidence"] == [
        {"text": "example-api: 40-route production service", "source": "github-repo"}
    ]
    assert "evidence" not in converted_data["skills"][1]
    assert converted_data["aliases"] == {"REST APIs": "fastapi"}


def test_main_default_source(tmp_path):
    original_text = (
        "skills:\n"
        "  - id: fastapi\n"
        "    evidence:\n"
        "      - sample evidence\n"
    )
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text(original_text, encoding="utf-8")
    original_bytes = profile_path.read_bytes()

    main([str(profile_path)])

    bak_path = tmp_path / "profile.yaml.bak"
    assert bak_path.exists()
    assert bak_path.read_bytes() == original_bytes

    converted_data = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    assert converted_data["skills"][0]["evidence"] == [
        {"text": "sample evidence", "source": "self-reported"}
    ]

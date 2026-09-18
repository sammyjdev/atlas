"""Migrate profile evidence strings to text-plus-source mappings."""
import argparse
import copy
from collections.abc import Mapping
from pathlib import Path

import yaml


def convert(data: dict, source: str) -> dict:
    """Convert plain string evidence entries into mappings with text and source."""
    result = {}
    for key, val in data.items():
        if key == "skills" and isinstance(val, list):
            new_skills = []
            for skill in val:
                if isinstance(skill, Mapping):
                    new_skill = {}
                    for sk, sv in skill.items():
                        if sk == "evidence" and isinstance(sv, list):
                            new_evidence = []
                            for entry in sv:
                                if isinstance(entry, str):
                                    new_evidence.append({"text": entry, "source": source})
                                elif isinstance(entry, Mapping):
                                    new_evidence.append(copy.deepcopy(entry))
                                else:
                                    new_evidence.append(copy.deepcopy(entry))
                            new_skill[sk] = new_evidence
                        else:
                            new_skill[sk] = copy.deepcopy(sv)
                    new_skills.append(new_skill)
                else:
                    new_skills.append(copy.deepcopy(skill))
            result[key] = new_skills
        else:
            result[key] = copy.deepcopy(val)
    return result


def main(argv: list[str] | None = None) -> None:
    """Entry point for migrating profile evidence in place."""
    parser = argparse.ArgumentParser(
        description="Migrate profile evidence strings to text-plus-source mappings."
    )
    parser.add_argument("path", help="Path to profile YAML file to migrate")
    parser.add_argument(
        "--source",
        default="self-reported",
        help="Evidence source string (default: self-reported)",
    )
    args = parser.parse_args(argv)

    target_path = Path(args.path)
    original_bytes = target_path.read_bytes()

    bak_path = Path(f"{target_path}.bak")
    bak_path.write_bytes(original_bytes)

    data = yaml.safe_load(original_bytes)
    if data is None:
        data = {}

    converted = convert(data, source=args.source)
    converted_yaml = yaml.safe_dump(converted, sort_keys=False, allow_unicode=True)
    target_path.write_text(converted_yaml, encoding="utf-8")


if __name__ == "__main__":
    main()

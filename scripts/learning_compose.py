#!/usr/bin/env python3
"""Apply a learning-agent diff to the current profile sections.

Reads:
  /tmp/ctx.json          — Stage 2 consolidated context (has current_profile)
  /tmp/diff.json         — Stage 3 synthesis output

Writes:
  /tmp/new_sections.json — full sections object, ready for update_profile

Exits non-zero on unresolvable structural problems (missing current profile,
trait-remove target not found, section referenced in diff but missing from
profile). The learning-agent runbook's Stage 5d treats any non-zero exit as
a hard fail and aborts the run.

Merge semantics per section:
  traits_removed  — remove traits whose `trait` field matches (case-sensitive).
                    Missing targets are a hard fail.
  traits_updated  — find the trait by name, overlay `change`, `new_confidence`,
                    `new_last_validated` fields.
  traits_added    — append full trait dict (with `evidence`, `confidence`, etc.)
                    Duplicate trait names are a hard fail.

The diff's `section_updates` keys must all already exist in the current
profile's sections. We do not create new top-level sections here.
"""
import json
import sys


def fail(msg: str) -> None:
    print(f"learning_compose: {msg}", file=sys.stderr)
    sys.exit(3)


def find_trait_index(traits: list, name: str) -> int:
    for i, t in enumerate(traits):
        if isinstance(t, dict) and t.get("trait") == name:
            return i
    return -1


def apply_section_update(section_name: str, section: dict, update: dict) -> None:
    traits = section.get("traits")
    if not isinstance(traits, list):
        fail(f"section {section_name!r} has no `traits` list")

    for name in update.get("traits_removed", []) or []:
        idx = find_trait_index(traits, name)
        if idx < 0:
            fail(f"traits_removed target {name!r} not found in section {section_name!r}")
        traits.pop(idx)

    for upd in update.get("traits_updated", []) or []:
        name = upd.get("trait")
        if not name:
            fail(f"traits_updated entry in {section_name!r} missing `trait`")
        idx = find_trait_index(traits, name)
        if idx < 0:
            fail(f"traits_updated target {name!r} not found in section {section_name!r}")
        if "change" in upd:
            traits[idx]["change_note"] = upd["change"]
        if "new_confidence" in upd:
            traits[idx]["confidence"] = upd["new_confidence"]
        if "new_last_validated" in upd:
            traits[idx]["last_validated"] = upd["new_last_validated"]

    for add in update.get("traits_added", []) or []:
        name = add.get("trait")
        if not name:
            fail(f"traits_added entry in {section_name!r} missing `trait`")
        if find_trait_index(traits, name) >= 0:
            fail(f"traits_added duplicate {name!r} already present in {section_name!r}")
        traits.append(add)


def main() -> None:
    with open("/tmp/ctx.json") as f:
        ctx = json.load(f)
    with open("/tmp/diff.json") as f:
        diff = json.load(f)

    current = ctx.get("current_profile")
    if not current:
        fail("current_profile is null — bootstrap user_profile before running")

    sections = current.get("sections")
    if not isinstance(sections, dict):
        fail("current_profile.sections is not an object")

    updates = diff.get("section_updates") or {}
    for section_name, update in updates.items():
        if section_name not in sections:
            fail(f"section_updates targets unknown section {section_name!r}")
        apply_section_update(section_name, sections[section_name], update)

    with open("/tmp/new_sections.json", "w") as f:
        json.dump(sections, f, indent=2, default=str)

    total_added = sum(len(u.get("traits_added") or []) for u in updates.values())
    total_updated = sum(len(u.get("traits_updated") or []) for u in updates.values())
    total_removed = sum(len(u.get("traits_removed") or []) for u in updates.values())
    print(
        f"learning_compose ok: sections={len(sections)} "
        f"added={total_added} updated={total_updated} removed={total_removed}"
    )


if __name__ == "__main__":
    main()

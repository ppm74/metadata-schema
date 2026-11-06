"""Tests for the cell components -> parts migration step (#128).

Covers the transform directly (correctness, key order, idempotency, conflicts)
and end-to-end through the engine against the current JSON schema using the
fixture under ``tests/migrations/``, including an in-place YAML migration that
keeps comments. Also covers the check that the ``contact`` of cell components
references existing electrolyte names.
"""

# ********************************************************************
#  This file is part of mdstools.
#
#        Copyright (C) 2026 Albert Engstfeld
#
#  mdstools is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  mdstools is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with mdstools. If not, see <https://www.gnu.org/licenses/>.
# ********************************************************************

import shutil

import pytest
import yaml
from packaging.version import Version

from mdstools.schema.migrate import MetadataMigrator, migrate_file
from mdstools.schema.migrations import (
    MIGRATIONS,
    UNRELEASED,
    Migration,
    _cell_components_to_parts,
)
from mdstools.schema.validator import (
    validate_electrolyte_references,
    validate_metadata,
)

FIXTURE = "tests/migrations/minimum_echemdb_cell_components.yaml"
SCHEMA = "schemas/minimum_echemdb.json"


def _register(monkeypatch):
    """Register the step under a concrete version so the engine applies it.

    UNRELEASED steps are skipped for concrete targets until a release stamps
    them; this mirrors what finalize_migrations does at release time.
    """
    monkeypatch.setattr(
        "mdstools.schema.migrate.MIGRATIONS",
        [Migration("0.9.0", "cell parts", _cell_components_to_parts)],
    )


def _cell(components):
    return {"system": {"electrochemicalCell": {"components": components}}}


def test_registry_registers_step():
    """The step is registered once, unreleased or stamped to a version > 0.8.4."""
    steps = [m for m in MIGRATIONS if m.apply is _cell_components_to_parts]
    assert len(steps) == 1
    to_version = steps[0].to_version
    assert to_version == UNRELEASED or Version(to_version) > Version("0.8.4")


def test_transform_turns_each_entry_into_a_part():
    """Each entry becomes a part named after ``part`` with one component."""
    after = _cell_components_to_parts(
        _cell(
            [
                {"name": "glass", "part": "cell", "description": "Open beaker"},
                {"name": "nafion", "part": "membrane"},
            ]
        )
    )
    assert after["system"]["electrochemicalCell"] == {
        "parts": [
            {
                "name": "cell",
                "description": "Open beaker",
                "components": [{"name": "glass"}],
            },
            {"name": "membrane", "components": [{"name": "nafion"}]},
        ]
    }


def test_transform_does_not_guess_material():
    """The old ``name`` is not copied into ``material``."""
    after = _cell_components_to_parts(_cell([{"name": "glass", "part": "cell"}]))
    component = after["system"]["electrochemicalCell"]["parts"][0]["components"][0]
    assert "material" not in component


def test_transform_uses_name_when_part_is_missing():
    """An entry without ``part`` still gets a part name."""
    after = _cell_components_to_parts(_cell([{"name": "glass"}]))
    assert after["system"]["electrochemicalCell"]["parts"] == [
        {"name": "glass", "components": [{"name": "glass"}]}
    ]


def test_transform_keeps_key_order():
    """``parts`` takes the position of ``components``."""
    before = {
        "system": {
            "electrochemicalCell": {
                "type": "glass cell",
                "components": [{"name": "glass", "part": "cell"}],
                "cellDescription": "A cell.",
            }
        }
    }
    after = _cell_components_to_parts(before)
    assert list(after["system"]["electrochemicalCell"]) == [
        "type",
        "parts",
        "cellDescription",
    ]


def test_transform_is_idempotent():
    """Applying the transform twice is a no-op."""
    once = _cell_components_to_parts(_cell([{"name": "glass", "part": "cell"}]))
    assert _cell_components_to_parts(once) == once


def test_transform_noop_without_components():
    """Documents without the old field are returned unchanged."""
    for doc in (
        {},
        {"system": {}},
        {"system": {"electrochemicalCell": {"parts": []}}},
    ):
        assert _cell_components_to_parts(doc) == doc


def test_transform_drops_null_components():
    """Null components are removed without creating an empty list."""
    after = _cell_components_to_parts(_cell(None))
    assert after == {"system": {"electrochemicalCell": {}}}


def test_transform_conflict_raises():
    """Both ``components`` and ``parts`` present is ambiguous."""
    before = _cell([{"name": "glass", "part": "cell"}])
    before["system"]["electrochemicalCell"]["parts"] = [{"name": "cell"}]
    with pytest.raises(ValueError, match="both"):
        _cell_components_to_parts(before)


def test_transform_rejects_non_list():
    """A mapping under ``components`` is not silently converted."""
    with pytest.raises(ValueError, match="not a list"):
        _cell_components_to_parts(_cell({"name": "glass", "part": "cell"}))


def test_transform_does_not_mutate_input():
    """The transform does not mutate its input document."""
    before = _cell([{"name": "glass", "part": "cell"}])
    _cell_components_to_parts(before)
    assert before == _cell([{"name": "glass", "part": "cell"}])


def test_fixture_fails_current_schema_but_validates_after_migration(monkeypatch):
    """The old-layout fixture fails the current schema but validates once migrated."""
    with open(FIXTURE, encoding="utf-8") as handle:
        data = yaml.safe_load(handle)

    with pytest.raises(ValueError):
        validate_metadata(data, SCHEMA)

    _register(monkeypatch)
    migrated = MetadataMigrator(data, "0.9.0").migrated()

    cell = migrated["system"]["electrochemicalCell"]
    assert "components" not in cell
    assert [part["name"] for part in cell["parts"]] == ["cell", "membrane"]
    assert migrated["echemdbSchemaVersion"] == "0.9.0"
    validate_metadata(migrated, SCHEMA)


def test_in_place_yaml_migration_keeps_comments(monkeypatch, tmp_path):
    """Migrating the fixture in place keeps its comments and validates."""
    target = tmp_path / "metadata.yaml"
    shutil.copy(FIXTURE, target)
    _register(monkeypatch)

    migrate_file(str(target), target_version="0.9.0", in_place=True)

    text = target.read_text(encoding="utf-8")
    assert "# source describing the setup" in text
    reloaded = yaml.safe_load(text)
    assert reloaded["system"]["electrochemicalCell"]["parts"][0]["name"] == "cell"
    validate_metadata(reloaded, SCHEMA)


def _system_with_contact(contact):
    component = {"name": "frit"}
    if contact is not None:
        component["contact"] = contact
    return {
        "system": {
            "electrolytes": [{"name": "catholyte"}, {"name": "anolyte"}],
            "electrochemicalCell": {
                "parts": [{"name": "degasser", "components": [component]}]
            },
        }
    }


def test_contact_references_resolve():
    """Component contacts that name listed electrolytes pass."""
    assert not validate_electrolyte_references(
        _system_with_contact(["catholyte", "anolyte"])
    )


def test_component_without_contact_passes():
    """A component close to but not in contact with an electrolyte omits contact."""
    assert not validate_electrolyte_references(_system_with_contact(None))


def test_contact_references_dangling():
    """A component contact that names no listed electrolyte is reported."""
    errors = validate_electrolyte_references(_system_with_contact(["KOH"]))
    assert len(errors) == 1
    assert "component 'frit'" in errors[0]
    assert "'KOH'" in errors[0]


def test_validate_detects_dangling_contact(monkeypatch):
    """The migrator's validation fails on a dangling component contact."""
    with open(FIXTURE, encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    _register(monkeypatch)
    migrated = MetadataMigrator(data, "0.9.0").migrated()
    migrated["system"]["electrochemicalCell"]["parts"][0]["components"][0][
        "contact"
    ] = ["NotListed"]
    with pytest.raises(ValueError, match="Reference validation"):
        MetadataMigrator(data, "0.9.0").validate("minimum_echemdb", data=migrated)

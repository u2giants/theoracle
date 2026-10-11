"""TS worker identity guards must cover the identity manifest's forbidden lists."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _forbidden(role: str) -> list[str]:
    lines = (ROOT / "dev/oracle2/runtime-identities.yaml").read_text().splitlines()
    start = lines.index(f"{role}:")
    names, in_list = [], False
    for line in lines[start + 1:]:
        if line and not line.startswith(" "):
            break
        if line.strip() == "forbidden:":
            in_list = True
        elif in_list and line.strip().startswith("- "):
            names.append(line.strip()[2:])
        elif in_list:
            in_list = False
    return names


def test_ts_guards_cover_manifest():
    for role, task in (("extractor", "oracle2-run.ts"), ("projector", "oracle2-project.ts"),
                       ("holistic", "oracle2-holistic.ts")):
        source = (ROOT / "apps/workers/src/trigger" / task).read_text()
        names = _forbidden(role)
        assert names, role
        for name in names:
            assert f"process.env.{name}" in source, (role, name)


def test_holistic_task_has_dedicated_preview_config_and_identity():
    config = (ROOT / "apps/workers/trigger.oracle2-holistic.config.ts").read_text()
    task = (ROOT / "apps/workers/src/trigger/oracle2-holistic.ts").read_text()
    manifest = (ROOT / "dev/oracle2/runtime-identities.yaml").read_text()
    assert "oracle2_holistic" in manifest
    assert "oracle2-holistic-answer" in task
    assert "./oracle2-python/oracle_brain/holistic_runtime.py" in task
    assert "dedicated-oracle2-holistic-preview" in manifest
    assert "scripts: ['./oracle2-python/oracle_brain/**/*.py']" in config
    assert "oracle2-holistic.ts" in config

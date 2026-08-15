from __future__ import annotations

import ast
import re
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).parents[1]
DOCS_ROOT = ROOT / "docs"
REQUIRED_DOCUMENTS = {
    ROOT / "README.md",
    ROOT / "AGENTS.md",
    DOCS_ROOT / "architecture.md",
    DOCS_ROOT / "configuration.md",
    DOCS_ROOT / "data-model.md",
    DOCS_ROOT / "modules.md",
    DOCS_ROOT / "troubleshooting.md",
    DOCS_ROOT / "domain" / "missions.md",
    DOCS_ROOT / "decisions" / "README.md",
}
MARKDOWN_LINK = re.compile(r"(?<!!)\[[^]]*]\(([^)]+)\)")


def _command_name(decorator: ast.expr, function_name: str) -> str | None:
    if not isinstance(decorator, ast.Call):
        return None
    function = decorator.func
    if not isinstance(function, ast.Attribute) or function.attr != "command":
        return None
    if not isinstance(function.value, ast.Name) or function.value.id != "app_commands":
        return None
    for keyword in decorator.keywords:
        if keyword.arg == "name" and isinstance(keyword.value, ast.Constant):
            return str(keyword.value.value)
    return function_name


def _slash_commands(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    commands: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            name = _command_name(decorator, node.name)
            if name:
                commands.add(name)
    return commands


def test_required_documentation_exists() -> None:
    missing = sorted(str(path.relative_to(ROOT)) for path in REQUIRED_DOCUMENTS if not path.is_file())
    assert not missing, f"Missing documentation: {missing}"


def test_relative_markdown_links_resolve() -> None:
    missing: list[str] = []
    for document in REQUIRED_DOCUMENTS:
        if not document.is_file():
            continue
        for raw_target in MARKDOWN_LINK.findall(document.read_text(encoding="utf-8")):
            target = raw_target.strip().split()[0].strip("<>")
            if target.startswith(("#", "http://", "https://", "mailto:")):
                continue
            relative_path = unquote(target.split("#", 1)[0])
            if not relative_path:
                continue
            resolved = (document.parent / relative_path).resolve()
            if not resolved.exists():
                missing.append(f"{document.relative_to(ROOT)} -> {target}")
    assert not missing, f"Broken relative Markdown links: {missing}"


def test_module_catalog_covers_every_cog_and_active_slash_command() -> None:
    catalog = (DOCS_ROOT / "modules.md").read_text(encoding="utf-8")
    missing_cogs: list[str] = []
    missing_commands: list[str] = []

    for cog in sorted((ROOT / "Cogs").glob("*.py")):
        if cog.name not in catalog:
            missing_cogs.append(cog.name)
        for command in sorted(_slash_commands(cog)):
            if f"/{command}" not in catalog:
                missing_commands.append(command)

    assert not missing_cogs, f"Cogs missing from docs/modules.md: {missing_cogs}"
    assert not missing_commands, f"Slash commands missing from docs/modules.md: {missing_commands}"


def test_tests_do_not_reference_the_real_database_or_discord_api() -> None:
    forbidden = ("db/bot.db", "db\\bot.db", "discord.com/api")
    references: list[str] = []
    for test_file in sorted((ROOT / "tests").glob("*.py")):
        if test_file == Path(__file__):
            continue
        content = test_file.read_text(encoding="utf-8").lower()
        if any(value in content for value in forbidden):
            references.append(test_file.name)
    assert not references, f"Tests reference production resources: {references}"


def test_repository_agent_instructions_define_the_local_done_check() -> None:
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "pipenv run check" in agents
    assert "db/bot.db" in agents
    assert "yoyo" in agents.lower()

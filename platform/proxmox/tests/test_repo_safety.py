"""Static safety checks over the repository itself.

These are the rules the migration promises to follow. A promise that is not
tested is a preference, so each one is asserted here and enforced in CI.
"""

import re
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.repo

MONOREPO_ROOT = Path(__file__).resolve().parents[3]
HOMELAB_SERVICES_ROOT = MONOREPO_ROOT / "services/homelab-services"
HOMELAB_TEMPLATES = HOMELAB_SERVICES_ROOT / "config/templates/stage-d"

# Operations that destroy data or make a host unrecoverable. Every one of these
# must sit on a task (or inside a block) tagged BOTH `never` and `destructive`,
# so it cannot run without an explicit `--tags all,destructive` opt-in on top of
# the approval variables.
DESTRUCTIVE_PATTERNS = [
    re.compile(r"\bqm\W+destroy\b"),
    re.compile(r"\bpct\W+destroy\b"),
    re.compile(r"\bpvecm\W+delnode\b"),
    re.compile(r"\bpvecm\W+create\b"),
    re.compile(r"\bpvecm\W+add\b"),
    re.compile(r"\bqmrestore\b"),
    re.compile(r"\bpct\W+restore\b"),
    re.compile(r"\bqm\W+shutdown\b"),
    re.compile(r"\bwipefs\b|\bsgdisk\b|\bmkfs\b"),
    re.compile(r"\bdd\b[^\n]*\bof=/dev/"),
    re.compile(r"upgrade:\s*dist"),
    re.compile(r"ansible\.builtin\.reboot"),
]

# Things that must not appear anywhere in the repository.
FORBIDDEN_PATTERNS = {
    "ignore_errors on any task": re.compile(r"^\s*ignore_errors:\s*(true|yes)", re.MULTILINE),
    "rm -rf": re.compile(r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f\b|\brm\s+-[a-zA-Z]*f[a-zA-Z]*r\b"),
    "pvecm expected": re.compile(r"\bpvecm\s+expected\b"),
    "StrictHostKeyChecking disabled": re.compile(r"StrictHostKeyChecking\s*[= ]\s*no"),
    "host_key_checking disabled": re.compile(r"host_key_checking\s*=\s*(False|false|no)"),
    "ansible password variable": re.compile(r"^\s*ansible_(ssh_)?pass(word)?\s*:", re.MULTILINE),
    "become password": re.compile(r"^\s*ansible_become_pass(word)?\s*:", re.MULTILINE),
    "private key material": re.compile(r"BEGIN (OPENSSH|RSA|EC|DSA|PGP) PRIVATE KEY"),
    "vault password file": re.compile(r"vault_password_file\s*="),
    "backup pruning enabled": re.compile(
        r"--prune-backups[ \t]+(?!keep-all=1|\"?\{\{)", re.MULTILINE
    ),
    "vzdump remove flag": re.compile(r"vzdump[^\n]*--remove\s+1"),
}

SKIP_FORBIDDEN_SCAN = {"tests/test_repo_safety.py", ".gitleaks.toml", ".gitignore"}


def _is_vendored(path, repo_root):
    """Galaxy installs third-party collections under ansible/collections/."""
    return "collections" in path.relative_to(repo_root).parts


def _yaml_files(repo_root):
    for path in sorted(repo_root.rglob("*.yml")):
        rel = path.relative_to(repo_root).as_posix()
        if rel.startswith((".venv/", ".ansible/", "artifacts/", "host-configs/")):
            continue
        if _is_vendored(path, repo_root):
            continue
        yield path


def _text_files(repo_root):
    for path in sorted(repo_root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(repo_root).as_posix()
        if rel.startswith(
            (
                ".venv/",
                ".ansible/",
                ".git/",
                "collections/",
                "artifacts/",
                "host-configs/",
                ".pytest_cache/",
                ".ruff_cache/",
                "__pycache__/",
            )
        ):
            continue
        if "/__pycache__/" in rel or "/.pytest_cache/" in rel:
            continue
        if _is_vendored(path, repo_root):
            continue
        if rel in SKIP_FORBIDDEN_SCAN:
            continue
        if path.suffix in {".png", ".jpg", ".gz", ".zst", ".pyc"}:
            continue
        yield path


def _walk_tasks(tasks, inherited):
    """Yield (task, effective_tags) for every task, descending into blocks."""
    if not isinstance(tasks, list):
        return
    for task in tasks:
        if not isinstance(task, dict):
            continue
        own = task.get("tags", [])
        if isinstance(own, str):
            own = [own]
        tags = set(inherited) | set(own or [])
        nested = False
        for key in ("block", "rescue", "always"):
            if key in task:
                nested = True
                yield from _walk_tasks(task[key], tags)
        if not nested:
            yield task, tags


def _plays(path):
    with path.open(encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    return doc if isinstance(doc, list) else []


# ---------------------------------------------------------------------------
# Playbook structure
# ---------------------------------------------------------------------------
def test_every_playbook_is_serial_one_and_fatal_on_error(repo_root):
    problems = []
    for path in sorted((repo_root / "ansible/playbooks").rglob("*.yml")):
        for play in _plays(path):
            if not isinstance(play, dict):
                continue
            name = f"{path.name}::{play.get('name', '?')}"
            if play.get("any_errors_fatal") is not True:
                problems.append(f"{name}: any_errors_fatal is not true")
            targets_hosts = play.get("hosts") not in ("localhost", "127.0.0.1")
            if targets_hosts and play.get("serial") != 1:
                problems.append(f"{name}: serial is not 1")
    assert not problems, "\n".join(problems)


def test_no_unattended_aggregate_playbook_exists(repo_root):
    names = {p.name for p in (repo_root / "ansible/playbooks/migration").glob("*.yml")}
    for banned in ("site.yml", "main.yml", "all.yml", "40-deploy.yml", "migrate.yml"):
        assert banned not in names


def test_makefile_has_no_aggregate_target(repo_root):
    text = (repo_root / "Makefile").read_text()
    for banned in ("deploy-all:", "migrate-all:", "run-all:", "everything:"):
        assert banned not in text, f"aggregate target {banned} must not exist"


def test_home_lab_terraform_is_import_first_and_destroy_protected(repo_root):
    terraform_root = repo_root / "terraform" / "homelab-guests"
    main = (terraform_root / "main.tf").read_text()
    imports = (terraform_root / "imports.tf").read_text()
    versions = (terraform_root / "versions.tf").read_text()
    makefile = (repo_root / "Makefile").read_text()

    assert main.count("prevent_destroy = true") == 2
    assert len(re.findall(r"^\s*purge_on_destroy\s*=\s*false$", main, re.MULTILINE)) == 2
    assert (
        len(
            re.findall(
                r"^\s*delete_unreferenced_disks_on_destroy\s*=\s*false$",
                main,
                re.MULTILINE,
            )
        )
        == 2
    )
    assert 'id = "pve2/300"' in imports
    assert 'id = "pve1/310"' in imports
    assert 'version = "0.107.0"' in versions
    assert "terraform-apply:" not in makefile
    assert "terraform-destroy:" not in makefile


def test_every_vm300_application_has_declarative_compose_and_ansible_selection(repo_root):
    expected = {
        "homepage",
        "it-tools",
        "linkding",
        "netknife",
        "npm",
        "pairdrop",
        "speedtest-tracker",
        "uptime-kuma",
    }
    compose_root = HOMELAB_TEMPLATES / "compose"
    actual = {path.parent.name for path in compose_root.glob("*/compose.yaml")}
    defaults = (
        HOMELAB_SERVICES_ROOT / "ansible/roles/homelab_services/defaults/main.yml"
    ).read_text()

    assert actual == expected
    for service in expected:
        assert f"  - {service}\n" in defaults


def test_declarative_proxy_covers_every_home_lab_site(repo_root):
    proxy = (HOMELAB_TEMPLATES / "config/npm/http.conf").read_text()
    expected_hosts = {
        "home.lab.example.com",
        "status.lab.example.com",
        "tools.lab.example.com",
        "netknife.lab.example.com",
        "links.lab.example.com",
        "drop.lab.example.com",
        "speed.lab.example.com",
        "grafana.lab.example.com",
        "prometheus.lab.example.com",
        "alert.lab.example.com",
        "netbox.lab.example.com",
        "ipam.lab.example.com",
        "bao.lab.example.com",
    }
    for host in expected_hosts:
        assert host in proxy


def test_makefile_supports_structured_approval_variables(repo_root):
    text = (repo_root / "Makefile").read_text()
    assert "EXTRA_JSON_ARG =" in text
    assert "-e '$(EXTRA_JSON)'" in text
    assert "EXTRA_JSON_ARG) $(EXTRA)" in text


# ---------------------------------------------------------------------------
# Destructive tagging
# ---------------------------------------------------------------------------
def test_destructive_tasks_carry_never_and_destructive(repo_root):
    problems = []
    for path in _yaml_files(repo_root):
        rel = path.relative_to(repo_root).as_posix()
        if rel.startswith("tests/"):
            continue
        with path.open(encoding="utf-8") as fh:
            doc = yaml.safe_load(fh)
        task_lists = []
        if isinstance(doc, list) and doc and isinstance(doc[0], dict) and "hosts" in doc[0]:
            for play in doc:
                play_tags = play.get("tags", [])
                if isinstance(play_tags, str):
                    play_tags = [play_tags]
                for section in ("pre_tasks", "tasks", "post_tasks", "handlers"):
                    task_lists.append((play.get(section) or [], set(play_tags)))
        elif isinstance(doc, list):
            task_lists.append((doc, set()))
        for tasks, base in task_lists:
            for task, tags in _walk_tasks(tasks, base):
                body = yaml.safe_dump(task)
                # A `debug:` message that merely *documents* a command is not the
                # command itself.
                if "ansible.builtin.debug" in body or "ansible.builtin.assert" in body:
                    continue
                for pattern in DESTRUCTIVE_PATTERNS:
                    if pattern.search(body):
                        if not {"never", "destructive"}.issubset(tags):
                            problems.append(
                                f"{rel}: task '{task.get('name', '?')}' matches "
                                f"{pattern.pattern!r} but has tags {sorted(tags)}"
                            )
                        break
    assert not problems, "\n".join(problems)


# ---------------------------------------------------------------------------
# Forbidden constructs
# ---------------------------------------------------------------------------
def _is_prose(path, line: str) -> bool:
    """Documentation that *warns* about a dangerous command is not that command.

    Markdown files, YAML comments and the human-readable text inside fail_msg /
    debug blocks are allowed to name `pvecm expected 1` in order to say "never
    do this".
    """
    if path.suffix in {".md", ".j2"}:
        return True
    stripped = line.strip()
    if stripped.startswith("#"):
        return True
    # Human-readable guidance inside fail_msg / debug blocks that tells the
    # operator NOT to do something.
    return bool(re.search(r"\b(do not|never|must not|Do NOT)\b", line, re.IGNORECASE))


@pytest.mark.parametrize("label,pattern", sorted(FORBIDDEN_PATTERNS.items()))
def test_forbidden_construct_absent(repo_root, label, pattern):
    hits = []
    for path in _text_files(repo_root):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        lines = text.splitlines()
        for match in pattern.finditer(text):
            index = text[: match.start()].count("\n")
            line = lines[index] if index < len(lines) else ""
            if _is_prose(path, line):
                continue
            hits.append(f"{path.relative_to(repo_root)}:{index + 1}: {match.group(0)[:80]}")
    assert not hits, f"{label} found:\n" + "\n".join(hits)


def test_no_archive_is_ever_deleted(repo_root):
    danger = re.compile(r"(rm|unlink|state:\s*absent)[^\n]*(\.vma|\.tar\.zst|/dump/)")
    hits = []
    for path in _text_files(repo_root):
        if path.suffix not in {".yml", ".sh", ".py"}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in danger.finditer(text):
            hits.append(f"{path.relative_to(repo_root)}: {match.group(0)[:80]}")
    assert not hits, "backup archives must never be deleted:\n" + "\n".join(hits)


def test_archive_verifier_captures_pipeline_status_outside_command_substitution(repo_root):
    script = (repo_root / "ansible/roles/backup_verify/files/verify-archives.sh").read_text()
    assert 'out=$(zstdcat "$archive" | vma verify' not in script
    assert 'zstdcat "$archive" 2>>"$verify_output" | vma verify' in script
    assert 'local pipe_status=("${PIPESTATUS[@]}")' in script


def test_empty_guest_checks_do_not_use_failure_on_no_match_globs(repo_root):
    bad = re.compile(r"ls\s+-1\s+/etc/pve/qemu-server/\*\.conf")
    hits = []
    for path in _yaml_files(repo_root):
        text = path.read_text(encoding="utf-8")
        if bad.search(text):
            hits.append(path.relative_to(repo_root).as_posix())
    assert not hits, f"empty guest checks must use find, not an unmatched ls glob: {hits}"


def test_upgrade_precheck_classifies_only_active_repositories(repo_root):
    tasks = (repo_root / "ansible/roles/pve_upgrade_precheck/tasks/main.yml").read_text()
    assert "register: pve_upgrade_precheck_repo_policy" in tasks
    for key in ("has_enterprise", "has_no_subscription", "has_test", "has_ceph"):
        line = next(line for line in tasks.splitlines() if line.lstrip().startswith(f"{key}:"))
        assert "pve_upgrade_precheck_repo_policy.stdout" in line
        assert "pve_upgrade_precheck_repos.stdout" not in line


def test_upgrade_precheck_requires_parseable_pve8to9_output(repo_root):
    tasks = (repo_root / "ansible/roles/pve_upgrade_precheck/tasks/main.yml").read_text()
    assert "pve_upgrade_precheck_current is version(pve8_minimum_before_upgrade, '>=')" in tasks
    assert "Require a successful and parseable pve8to9 result" in tasks
    assert "(pve_upgrade_precheck_pve8to9.rc | int) == 0" in tasks
    assert "FAILURES:\\\\s*\\\\d+" in tasks
    assert "WARNINGS:\\\\s*\\\\d+" in tasks


def test_live_upgrade_rechecks_pve8to9_before_repository_change(repo_root):
    playbook = (repo_root / "ansible/playbooks/migration/41-upgrade-pve1.yml").read_text()
    check = playbook.index("Require a successful and parseable final pve8to9 result")
    repo_change = playbook.index("Rewrite the repositories for Debian Trixie / PVE 9")
    assert check < repo_change
    assert "(upgrade_pve8to9_final.rc | int) == 0" in playbook
    assert "(upgrade_pve8to9_failures | int) == 0" in playbook
    assert "(upgrade_pve8to9_warnings | int) == 0" in playbook


def test_live_upgrade_guards_bootloader_remediation(repo_root):
    playbook = (repo_root / "ansible/playbooks/migration/41-upgrade-pve1.yml").read_text()
    diagnose = playbook.index("Assert this host is using the diagnosed GRUB boot layout")
    simulate = playbook.index("Simulate removal of the conflicting systemd-boot meta-package")
    remove = playbook.index("Remove the systemd-boot meta-package rejected by pve8to9")
    final_check = playbook.index("Run pve8to9 again on the fully updated PVE 8")
    repo_change = playbook.index("Rewrite the repositories for Debian Trixie / PVE 9")
    assert diagnose < simulate < remove < final_check < repo_change
    assert "not upgrade_proxmox_boot_uuids.stat.exists" in playbook
    assert "upgrade_grub_efi_loader.stat.exists" in playbook
    assert "apt-get, -s, remove, systemd-boot" in playbook
    assert "Remv (proxmox-ve|pve-manager|proxmox-kernel|grub)" in playbook


def test_backup_verification_generations_are_visible_to_every_play(repo_root):
    """The localhost adjudication play must see the same generation scope as the role."""
    gv = _group_vars(repo_root)
    assert gv["backup_verify_generations"] == ["initial", "final"]
    role_defaults = yaml.safe_load(
        (repo_root / "ansible/roles/backup_verify/defaults/main.yml").read_text(encoding="utf-8")
    )
    assert "backup_verify_generations" not in role_defaults


def test_ansible_cfg_keeps_host_key_checking_on(repo_root):
    text = (repo_root / "ansible/ansible.cfg").read_text()
    assert re.search(r"host_key_checking\s*=\s*True", text)
    assert re.search(r"gathering\s*=\s*explicit", text)
    assert "BatchMode=yes" in text
    assert "PreferredAuthentications=publickey" in text


# ---------------------------------------------------------------------------
# Approval gates
# ---------------------------------------------------------------------------
def _group_vars(repo_root):
    with (MONOREPO_ROOT / "inventory/group_vars/all.yml").open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def test_every_allow_flag_defaults_to_false(repo_root):
    gv = _group_vars(repo_root)
    flags = {k: v for k, v in gv.items() if k.startswith("allow_")}
    assert flags, "no approval flags found"
    for key, value in flags.items():
        assert value is False, f"{key} must default to false, got {value!r}"


def test_every_confirmation_defaults_to_empty(repo_root):
    gv = _group_vars(repo_root)
    for key, value in gv.items():
        if key.endswith("_confirmation") or re.match(r".*confirmation_pve\d+$", key):
            assert value == "", f"{key} must default to an empty string, got {value!r}"


def test_required_confirmation_strings_are_exact(repo_root):
    gv = _group_vars(repo_root)
    assert gv["join_confirmation_pve3_required"] == ("JOIN pve3 192.168.0.13 TO homelab")
    assert (
        gv["destroy_confirmation_pve2_required"]
        == "DESTROY pve2 192.168.0.12 AND DISCARD ALL FIVE GUESTS"
    )


# Every approval flag and the exact-confirmation variable it is paired with.
# `allow_configure_nfs_storage` is deliberately absent: adding a storage
# definition is additive and reversible, so it needs a flag but not a passphrase.
APPROVAL_PAIRS = {
    "allow_guest_shutdown": "guest_shutdown_confirmation",
    "allow_repo_change_pve1": "repo_change_confirmation_pve1",
    "allow_upgrade_pve1": "upgrade_confirmation_pve1",
    "allow_create_cluster": "create_cluster_confirmation",
    "allow_join_pve3": "join_confirmation_pve3",
    "allow_destroy_pve2": "destroy_confirmation_pve2",
    "allow_join_pve2": "join_confirmation_pve2",
    "allow_restore_pve2": "restore_confirmation_pve2",
    "allow_start_restored_guests": "start_restored_confirmation",
    "allow_delete_test_restore": "delete_test_restore_confirmation",
}


def test_every_allow_flag_has_a_paired_confirmation(repo_root):
    gv = _group_vars(repo_root)
    flags = {k for k in gv if k.startswith("allow_")} - {"allow_configure_nfs_storage"}
    assert flags == set(APPROVAL_PAIRS), (
        "an approval flag was added or removed without updating APPROVAL_PAIRS: "
        f"{flags ^ set(APPROVAL_PAIRS)}"
    )
    for flag, confirmation in APPROVAL_PAIRS.items():
        assert gv[flag] is False
        assert gv[confirmation] == ""
        assert gv[f"{confirmation}_required"], f"{confirmation}_required must be non-empty"


def test_every_gate_is_enforced_by_a_playbook_or_role(repo_root):
    """A variable that nothing checks is decoration, not a gate."""
    sources = "\n".join(
        p.read_text(encoding="utf-8")
        for p in list((repo_root / "ansible/playbooks/migration").rglob("*.yml"))
        + list((repo_root / "ansible/roles").rglob("*.yml"))
    )
    for flag, confirmation in APPROVAL_PAIRS.items():
        assert flag in sources, f"{flag} is never checked"
        assert confirmation in sources, f"{confirmation} is never checked"


def test_reinstall_acknowledgements_default_to_false(repo_root):
    gv = _group_vars(repo_root)
    for key in (
        "pve3_reinstalled",
        "pve3_fingerprint_verified",
        "pve2_reinstalled",
        "pve2_fingerprint_verified",
        "console_access_confirmed_pve1",
    ):
        assert gv[key] is False, f"{key} must default to false"


def test_pruning_is_disabled_by_policy(repo_root):
    gv = _group_vars(repo_root)
    assert gv["never_prune_backups"] is True
    text = (MONOREPO_ROOT / "platform/nas/ansible/roles/synology_nfs/defaults/main.yml").read_text()
    assert "keep-all=1" in text


def test_ha_is_not_enabled(repo_root):
    assert _group_vars(repo_root)["enable_ha"] is False


def test_capacity_margin_is_at_least_thirty_percent(repo_root):
    assert _group_vars(repo_root)["backup_capacity_margin_pct"] >= 30


# ---------------------------------------------------------------------------
# Jinja / YAML interaction
# ---------------------------------------------------------------------------
def test_no_regex_backreference_inside_a_folded_scalar(repo_root):
    """A backreference in a folded (>-) or literal (|-) block scalar is silently
    passed through verbatim by Ansible, so `regex_search(..., '\\1')` yields the
    string "\\1" instead of the captured group.

    This was not theoretical: the pve8to9 FAILURES/WARNINGS counters were written
    that way, evaluated to 0 via `| int`, and the upgrade gate would have passed
    an upgrade that the official checklist had actually failed. Plain and
    double-quoted scalars behave correctly; block scalars do not.
    """
    block_open = re.compile(r":\s*[>|]-?\s*$")
    # `.*` not `[^)]*`: the regex being audited contains its own ")" from the
    # capture group, which would end the character class early.
    backref = re.compile(r"regex_(search|replace|findall)\(.*\\\\[0-9]")
    offenders = []

    for path in _yaml_files(repo_root):
        rel = path.relative_to(repo_root).as_posix()
        if rel.startswith("tests/"):
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        in_block_at_indent = None
        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue
            indent = len(line) - len(line.lstrip())
            if in_block_at_indent is not None and indent <= in_block_at_indent:
                in_block_at_indent = None
            if block_open.search(line):
                in_block_at_indent = indent
                continue
            if in_block_at_indent is not None and backref.search(line):
                offenders.append(f"{rel}:{i + 1}: {stripped[:90]}")

    assert not offenders, (
        "regex backreference inside a folded/literal block scalar — it will "
        "evaluate to the literal backslash-digit. Use a double-quoted scalar, or "
        "avoid the backreference entirely:\n" + "\n".join(offenders)
    )


def test_cluster_mac_validation_ignores_snapshot_history(repo_root):
    tasks = (repo_root / "ansible/roles/validation/tasks/main.yml").read_text(encoding="utf-8")
    assert "awk '/^\\[/{exit} {print}'" in tasks


# Components split out of this repository in Phase 1 run their playbooks under
# their own ansible.cfg and must not lose the controller's SSH safety settings.
PROXMOX_LINEAGE_CFGS = (
    "platform/proxmox/ansible/ansible.cfg",
    "platform/nas/ansible/ansible.cfg",
    "services/homelab-services/ansible/ansible.cfg",
    "services/netbox/ansible/ansible.cfg",
    "security/aaa-freeradius/ansible/ansible.cfg",
)


@pytest.mark.parametrize("cfg", PROXMOX_LINEAGE_CFGS)
def test_split_components_keep_ssh_safety_settings(cfg):
    text = (MONOREPO_ROOT / cfg).read_text(encoding="utf-8")
    assert re.search(r"host_key_checking\s*=\s*True", text)
    assert re.search(r"gathering\s*=\s*explicit", text)
    assert "BatchMode=yes" in text
    assert "PreferredAuthentications=publickey" in text


def test_every_monorepo_ansible_cfg_keeps_host_key_checking_on():
    cfgs = [
        p
        for p in MONOREPO_ROOT.rglob("ansible.cfg")
        if not {".venv", ".ansible", "collections", "public"} & set(p.parts)
    ]
    assert len(cfgs) >= len(PROXMOX_LINEAGE_CFGS)
    for path in cfgs:
        assert re.search(r"host_key_checking\s*=\s*True", path.read_text(encoding="utf-8")), path


ANCHORED_PATH = re.compile(r"\{\{\s*(playbook_dir|role_path)\s*\}\}(/[^\"'\s{]*)?")
ANSIBLE_SOURCE_ROOTS = ("platform", "services", "security", "observability")


def _ansible_sources(kind):
    for component in ANSIBLE_SOURCE_ROOTS:
        for path in sorted((MONOREPO_ROOT / component).rglob(f"ansible/{kind}/**/*.yml")):
            if not {".venv", ".ansible", "collections"} & set(path.parts):
                yield path


def _playbook_dirs_running(role):
    uses = re.compile(rf"^\s*-\s*(?:role:\s*)?{re.escape(role)}\s*$", re.MULTILINE)
    return {p.parent for p in _ansible_sources("playbooks") if uses.search(p.read_text("utf-8"))}


def test_every_playbook_dir_and_role_path_reference_resolves():
    """Phase 1 moved templates to config/ and playbooks one level deeper, which
    left five role asset roots pointing at directories that no longer existed.
    Syntax checks cannot see that; a live run fails on the first copy."""
    problems = []
    for path in [*_ansible_sources("playbooks"), *_ansible_sources("roles")]:
        text = path.read_text(encoding="utf-8")
        parts = path.parts
        role_dir = None
        if "roles" in parts:
            role_dir = Path(*parts[: parts.index("roles") + 2])
        refs = []
        for line in text.splitlines():
            is_output = line.strip().startswith("dest:")
            refs += [(a, s, is_output) for a, s in ANCHORED_PATH.findall(line)]
        for anchor, suffix, is_output in refs:
            if anchor == "role_path":
                bases = {role_dir} if role_dir else set()
            elif role_dir is None:
                bases = {path.parent}
            else:
                bases = _playbook_dirs_running(role_dir.name)
            if not bases:
                problems.append(f"{path.relative_to(MONOREPO_ROOT)}: no base for {anchor}")
            for base in bases:
                target = base / (suffix or "").lstrip("/")
                # An output (dest:) need not exist yet, but its directory must.
                if not (target.parent if is_output else target).exists():
                    rel = path.relative_to(MONOREPO_ROOT).as_posix()
                    problems.append(f"{rel}: {anchor}{suffix} from {base.name}")
    assert not problems, problems


def test_project_root_is_the_migration_controller_root():
    """artifacts/, host-configs/ and scripts/ hang off project_root; a wrong
    value writes backup evidence and captures into the wrong directory."""
    with (MONOREPO_ROOT / "inventory/group_vars/all.yml").open(encoding="utf-8") as fh:
        fallback = yaml.safe_load(fh)["project_root"]
    assert fallback == "{{ playbook_dir | dirname | dirname | dirname }}"
    migration = MONOREPO_ROOT / "platform/proxmox/ansible/playbooks/migration"
    assert migration.parent.parent.parent == MONOREPO_ROOT / "platform/proxmox"
    assert (migration.parent.parent.parent / "scripts").is_dir()
    proxmox_make = (MONOREPO_ROOT / "platform/proxmox/Makefile").read_text(encoding="utf-8")
    assert re.search(r"^PB\s+=.*-e 'project_root=\$\(CURDIR\)'", proxmox_make, re.MULTILINE)
    nas_make = (MONOREPO_ROOT / "platform/nas/Makefile").read_text(encoding="utf-8")
    assert "PROJECT_ROOT ?= $(abspath ../proxmox)" in nas_make
    assert "-e 'project_root=$(PROJECT_ROOT)'" in nas_make


def test_every_role_task_include_resolves():
    """The Phase 1 playbook rename rewrote role-internal includes to names that
    did not exist, which would have failed the backup and join stages at
    runtime. Every static include in every component's roles must resolve."""
    include = re.compile(
        r"^\s*(?:ansible\.builtin\.)?(?:include|import)_tasks:\s*([\w./-]+\.ya?ml)\s*$"
    )
    problems = []
    for component in ("platform", "services", "security", "observability"):
        for path in sorted((MONOREPO_ROOT / component).rglob("roles/*/tasks/*.yml")):
            rel = path.relative_to(MONOREPO_ROOT).as_posix()
            if any(part in {".venv", ".ansible", "collections"} for part in path.parts):
                continue
            for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                match = include.match(line)
                if match and not (path.parent / match[1]).is_file():
                    problems.append(f"{rel}:{i} -> {match[1]}")
    assert not problems, problems


# ---------------------------------------------------------------------------
# Homepage honesty
# ---------------------------------------------------------------------------
# Homepage is the operator's first view of the Home Lab. A card with a health
# check implies "this is deployed and I am watching it". A planned component
# that gets a siteMonitor either shows a permanent red dot (noise) or, worse,
# a green dot borrowed from the NPM wildcard fallback page (a lie). So planned
# entries carry no siteMonitor, and — until a real route exists — no href.
HOMEPAGE_PLANNED_GROUP = "Planned and recovery"
HOMEPAGE_PLANNED_ENTRIES = set()

# Deployed containers that get a user-facing card. Internal exporters
# (node-exporter, Alloy, blackbox, snmp, pve-exporter) stay off Homepage:
# they have no operator UI. cAdvisor is the exception: its data is the
# Grafana Docker dashboard, which is a real clickable UI.
HOMEPAGE_MONITORED_SERVICES = {
    "Nginx Proxy Manager",
    "Uptime Kuma",
    "IT-Tools",
    "NetKnife",
    "Linkding",
    "PairDrop",
    "Speedtest Tracker",
    "Proxmox cluster",
    "Synology",
    "NetBox",
    "OpenBao",
    "Grafana",
    "Prometheus",
    "Alertmanager",
    "Loki",
    "cAdvisor",
}


def _homepage_services(repo_root):
    path = HOMELAB_TEMPLATES / "config/homepage/services.yaml"
    with path.open(encoding="utf-8") as fh:
        groups = yaml.safe_load(fh)
    flattened = {}
    for group in groups:
        ((group_name, entries),) = group.items()
        for entry in entries:
            ((entry_name, body),) = entry.items()
            flattened[entry_name] = (group_name, body or {})
    return flattened


def test_homepage_planned_entries_are_never_presented_as_running(repo_root):
    services = _homepage_services(repo_root)
    problems = []
    for name in sorted(HOMEPAGE_PLANNED_ENTRIES):
        if name not in services:
            problems.append(f"{name}: missing from Homepage entirely")
            continue
        group, body = services[name]
        if group != HOMEPAGE_PLANNED_GROUP:
            problems.append(f"{name}: in group {group!r}, not {HOMEPAGE_PLANNED_GROUP!r}")
        if "siteMonitor" in body:
            problems.append(f"{name}: planned entries must not carry a siteMonitor")
        if "href" in body:
            problems.append(f"{name}: planned entries must not link until a real route exists")
        if "not deployed" not in body.get("description", "").lower() and (
            "not completed" not in body.get("description", "").lower()
        ):
            problems.append(f"{name}: description must state that it is not deployed")
    assert not problems, "\n".join(problems)


def test_homepage_deployed_cards_all_have_health_checks(repo_root):
    services = _homepage_services(repo_root)
    problems = []
    for name, (group, body) in sorted(services.items()):
        if group == HOMEPAGE_PLANNED_GROUP:
            continue
        if name not in HOMEPAGE_MONITORED_SERVICES:
            problems.append(f"{name}: undeclared card — add it here or to the planned group")
        if "siteMonitor" not in body:
            problems.append(f"{name}: deployed cards must carry a siteMonitor")
        if "href" not in body:
            problems.append(f"{name}: deployed cards must link somewhere")
    missing = HOMEPAGE_MONITORED_SERVICES - set(services)
    problems.extend(f"{name}: declared as deployed but has no Homepage card" for name in missing)
    assert not problems, "\n".join(problems)


def test_homepage_covers_every_deployed_observability_ui(repo_root):
    """Loki is deployed on VM 310 and was missing from Homepage until now."""
    services = _homepage_services(repo_root)
    expected_monitors = {
        "Grafana": "http://192.168.0.31:3000/api/health",
        "Prometheus": "http://192.168.0.31:9090/-/ready",
        "Alertmanager": "http://192.168.0.31:9093/-/ready",
        "Loki": "http://192.168.0.31:3100/ready",
        "cAdvisor": "http://192.168.0.31:3000/api/health",
    }
    for name, monitor in expected_monitors.items():
        group, body = services[name]
        assert group == "Observability", f"{name} is not in the Observability group"
        assert body["siteMonitor"] == monitor, f"{name} has the wrong health endpoint"


# ---------------------------------------------------------------------------
# NetBox (planned)
# ---------------------------------------------------------------------------
# NetBox is the first create-mode Terraform in this repository. Everything
# adopted so far was import-first over a guest that already existed, so these
# assertions exist to keep a brand-new VM from inheriting weaker guarantees
# than the two protected guests already have.
def test_netbox_terraform_is_create_mode_but_destroy_protected(repo_root):
    root = MONOREPO_ROOT / "services/netbox/terraform/proxmox-guest"
    main = (root / "main.tf").read_text()
    variables = (root / "variables.tf").read_text()
    versions = (root / "versions.tf").read_text()
    makefile = (repo_root / "Makefile").read_text()

    assert "prevent_destroy = true" in main
    assert re.search(r"^\s*purge_on_destroy\s*=\s*false$", main, re.MULTILINE)
    assert re.search(r"^\s*delete_unreferenced_disks_on_destroy\s*=\s*false$", main, re.MULTILINE)
    assert re.search(r"^\s*protection\s*=\s*true$", main, re.MULTILINE)
    # A new guest must not start or auto-boot until its backup and restore
    # drills pass, exactly as VMs 300 and 310 were gated.
    assert re.search(r"^\s*on_boot\s*=\s*false$", main, re.MULTILINE)
    assert re.search(r"^\s*started\s*=\s*var\.start_after_create$", main, re.MULTILINE)
    assert 'variable "start_after_create"' in variables
    assert re.search(r'variable "start_after_create"[^}]*default\s*=\s*false', variables, re.S)
    assert 'version = "0.107.0"' in versions

    # Separate root from the import-first guests, and still no apply/destroy.
    assert "netbox-terraform-plan:" in makefile
    assert "netbox-terraform-apply:" not in makefile
    assert "netbox-terraform-destroy:" not in makefile


def test_netbox_terraform_is_a_separate_root_from_the_adopted_guests(repo_root):
    """A drift plan for VMs 300/310 must never also propose creating VM 330."""
    adopted = (repo_root / "terraform" / "homelab-guests" / "main.tf").read_text()
    assert "netbox" not in adopted.lower()


def test_netbox_vmid_and_mac_do_not_collide_with_reserved_identities(repo_root):
    variables = (MONOREPO_ROOT / "services/netbox/terraform/proxmox-guest/variables.tf").read_text()
    vm_id = int(re.search(r'variable "netbox_vm_id".*?default\s*=\s*(\d+)', variables, re.S)[1])
    mac = re.search(
        r'variable "netbox_mac_address".*?default\s*=\s*"([0-9A-F:]+)"', variables, re.S
    )[1]

    # 300/310/399 are live or retained; 320-322 are reserved for OpenBao voters.
    assert vm_id not in {300, 310, 399, 320, 321, 322}
    # A retired guest's MAC stays on this list. Freeing it would let a future VM
    # reuse an address that still appears in router DHCP reservations, neighbour
    # caches and monitoring history - VM 297's MAC was still cached against
    # 192.168.0.73 on 2026-09-19, days after the guest was destroyed.
    reserved_macs = {
        "52:54:00:00:00:00",  # VM 290 net0
        "52:54:00:00:00:00",  # VM 290 net1
        "52:54:00:00:00:00",  # VM 297 - RETIRED 2026-09-19, stays reserved
        "52:54:00:00:00:00",  # VM 300
        "52:54:00:00:00:00",  # VM 310
        "52:54:00:00:00:00",  # VM 399 restore test
        "52:54:00:00:00:00",  # planned OpenBao voters
        "52:54:00:00:00:00",
        "52:54:00:00:00:00",
    }
    assert mac not in reserved_macs


def test_netbox_deployment_is_gated_by_flag_and_exact_confirmation(repo_root):
    defaults_path = MONOREPO_ROOT / "services/netbox/ansible/roles/netbox_app/defaults/main.yml"
    with defaults_path.open(encoding="utf-8") as fh:
        defaults = yaml.safe_load(fh)
    tasks = (MONOREPO_ROOT / "services/netbox/ansible/roles/netbox_app/tasks/main.yml").read_text()

    assert defaults["netbox_app_allow_first_deployment"] is False
    assert defaults["netbox_app_first_deployment_confirmation"] == ""
    assert defaults["netbox_app_first_deployment_confirmation_expected"].strip()
    assert "netbox_app_allow_first_deployment" in tasks
    assert "netbox_app_first_deployment_confirmation" in tasks


def test_netbox_has_no_aggregate_target(repo_root):
    text = (repo_root / "Makefile").read_text()
    for banned in ("netbox-all:", "netbox-deploy-all:", "netbox-everything:"):
        assert banned not in text
    names = {p.name for p in (MONOREPO_ROOT / "services/netbox/ansible/playbooks").glob("*.yml")}
    assert names == {
        "30-preflight.yml",
        "31-configure-guest.yml",
        "40-deploy.yml",
        "50-configure-backups.yml",
    }


def test_netbox_backup_dumps_postgres_and_never_prunes(repo_root):
    """A file copy of a live PostgreSQL data directory is not a backup."""
    program = (MONOREPO_ROOT / "services/netbox/config/templates/stage-b/backup.py").read_text()
    assert "pg_dump" in program
    assert "--serializable-deferrable" in program
    assert "append-only; no automatic pruning" in program
    for banned in ("shutil.rmtree", "os.remove", "unlink(", "--prune"):
        assert banned not in program, f"the backup program must never remove data: {banned}"


def test_netbox_secrets_are_operator_installed_and_never_generated(repo_root):
    tasks = (MONOREPO_ROOT / "services/netbox/ansible/roles/netbox_app/tasks/main.yml").read_text()
    with (MONOREPO_ROOT / "services/netbox/ansible/roles/netbox_app/defaults/main.yml").open(
        encoding="utf-8"
    ) as fh:
        defaults = yaml.safe_load(fh)

    assert defaults["netbox_app_required_secrets"]
    assert "no_log: true" in tasks
    assert "'0400', '0600'" in tasks
    for banned in ("password:", "lookup('password'", "random_password", "SECRET_KEY:"):
        assert banned not in tasks, f"secrets must not be generated or embedded: {banned}"

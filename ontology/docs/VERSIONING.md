# Versioning Strategy

This document explains the versioning strategy for `oxp-ontology`.

## Per-Component Versioning

The bundled ontology set has five components, each versioned independently in `VERSION`
(one `component=version` line each) and in that component's own `owl:versionInfo`:

```
mas=2.0.1
semantic=1.0.1
metrics=2.0.1
analysis=2.0.1
insight=2.0.1
```

`mas`, `metrics`, `analysis`, and `insight` are kept in **lockstep** (bumped together — CI's
`version-check` job in `test.yml` enforces they match). `semantic` is versioned
**independently** and is not expected to match the others. `pyproject.toml` and the Python
package version track the `mas` component only.

Most `scripts/version_manager.py` commands take an optional `component` argument
(`mas | semantic | metrics | analysis | insight | all`), defaulting to `mas` for `get`/`get-full`
and to `all` for `bump`/`set`:

```bash
python3 scripts/version_manager.py get                 # mas version (used by CI)
python3 scripts/version_manager.py get all             # every component's version
python3 scripts/version_manager.py bump rc             # bump RC for all components
python3 scripts/version_manager.py bump minor semantic # bump only semantic
python3 scripts/version_manager.py set 1.2.0 mas       # set only mas
```

The `task version*` targets below operate on the default (`mas`) component unless you call
`version_manager.py` directly with a component argument.

## Version Format

We follow [Semantic Versioning](https://semver.org/) with PEP 440-compliant local version identifiers:

- **Release versions**: `MAJOR.MINOR.PATCH` (e.g., `1.0.0`, `1.2.3`)
- **Release candidates**: `MAJOR.MINOR.PATCH-rcN` (e.g., `1.0.0-rc0`, `1.0.0-rc1`)
- **RC with commit SHA**: `MAJOR.MINOR.PATCH-rcN+gSHA` (e.g., `1.0.0-rc0+ga3f5c21`)

## Versioning Rules

### Release Candidates (RC)

**Purpose**: Pre-release versions for testing before final release.

**Build artifacts**:
- **Include commit SHA** in package version: `1.0.0-rc0+ga3f5c21`
- **GitHub Pages docs** display version with SHA in footer
- **Tagged as pre-release** in GitHub Releases

**When to use**:
- During development iterations before stable release
- When testing breaking changes
- For stakeholder preview builds

**Multiple RC merges**:
- Each merge to `main` with an RC version generates **unique artifacts** (commit SHA differentiates them)
- No accidental overwrites — each RC build is traceable to its commit

**Bumping RC versions**:
```bash
# Increment RC number: rc0 -> rc1
task version-bump-rc

# Or manually
python3 scripts/version_manager.py bump rc
```

### Final Releases

**Purpose**: Stable, production-ready versions.

**Build artifacts**:
- **NO commit SHA** in package version: `1.0.0` (clean)
- **GitHub Pages docs** display clean version
- **Tagged as release** in GitHub Releases

**When to use**:
- After RC testing is complete
- When ontologies are stable and validated
- For consumers to install via pip

**Bumping final versions**:
```bash
# Remove RC, increment minor: 1.0.0-rc3 -> 1.1.0
task version-bump-minor

# Remove RC, increment major: 1.0.0-rc3 -> 2.0.0
task version-bump-major

# Or manually
python3 scripts/version_manager.py bump minor
python3 scripts/version_manager.py bump major
```

## Version Management Commands

### Check Version

```bash
# Get base version from VERSION file
task version
# Output: 1.0.0-rc0

# Get full version with commit SHA (if RC)
task version-full
# Output: 1.0.0-rc0+ga3f5c21
```

### Bump Version

```bash
# Increment RC: rc0 -> rc1
task version-bump-rc

# Finalize to next minor version: 1.0.0-rc0 -> 1.1.0
task version-bump-minor

# Finalize to next major version: 1.0.0-rc0 -> 2.0.0
task version-bump-major
```

### Set Specific Version

```bash
# Set exact version
task version-set -- 1.1.0-rc0

# Or with script
python3 scripts/version_manager.py set 1.1.0-rc0
```

### Verify Consistency

```bash
# Check VERSION matches pyproject.toml
task version-check
```

## Workflow Integration

### On PR Submission

- **Tests run** via `.github/workflows/test.yml`
- **TTL validation** ensures ontologies are syntactically correct
- **Version consistency check** verifies VERSION ↔ pyproject.toml

### On Merge to Main

**For RC versions** (`1.0.0-rc0`):
1. GitHub Actions builds docs with version `1.0.0-rc0+g<sha>`
2. Deploys to GitHub Pages with SHA in footer
3. Package artifacts include commit SHA (if published)

**For final releases** (`1.0.0`):
1. GitHub Actions builds docs with clean version `1.0.0`
2. Deploys to GitHub Pages
3. Creates GitHub Release with packages

### Publishing Package

Triggered via **workflow_dispatch** or **tag push**:

```bash
# Option 1: Manual workflow trigger with version bump
# Go to Actions → Publish Python Package → Run workflow
# Select bump type: rc, minor, major

# Option 2: Push tag
git tag v1.0.0
git push origin v1.0.0
```

**Behavior**:
- **RC versions**: Creates pre-release with SHA-tagged artifacts
- **Final versions**: Creates release with clean artifacts

## Best Practices

1. **Use RC versions during development**
   - Merge PRs to `main` with RC versions (`1.0.0-rc0`)
   - Each merge creates traceable artifacts (commit SHA ensures uniqueness)
   - No risk of overwriting previous RC builds

2. **Bump RC number when needed**
   - Before major milestones: `task version-bump-rc` (rc0 → rc1)
   - Communicates progress to stakeholders

3. **Finalize version before stable release**
   - Run `task version-bump-minor` or `task version-bump-major`
   - Removes RC suffix, increments version
   - Commit and push: `git add VERSION pyproject.toml && git commit -m "chore: release v1.0.0"`

4. **Never manually edit VERSION without updating pyproject.toml**
   - Always use `task version-set` or `version_manager.py`
   - Ensures consistency (verified by CI)

5. **Tag releases after merging**
   - After merging finalized version: `git tag v1.0.0 && git push origin v1.0.0`
   - Triggers package publication workflow

## Examples

### Scenario 1: Iterating on RC

```bash
# Current: 1.0.0-rc0
git checkout -b feat/new-feature
# Make changes to ontologies
git commit -m "feat: add new classes"
git push

# PR merged to main
# → Docs deployed with version 1.0.0-rc0+ga3f5c21

# Continue development
git checkout -b fix/typo
# Fix issues
git commit -m "fix: correct typos"
git push

# PR merged to main
# → Docs deployed with version 1.0.0-rc0+gb4e8a92 (different SHA!)
```

### Scenario 2: Releasing Final Version

```bash
# Current: 1.0.0-rc3
# Testing complete, ready to release

# Bump to final version
task version-bump-minor
# VERSION now: 1.1.0
# pyproject.toml updated

git add VERSION pyproject.toml
git commit -m "chore: release v1.1.0"
git push

# Tag release
git tag v1.1.0
git push origin v1.1.0

# → Docs deployed with clean version 1.1.0
# → GitHub Release created with packages
```

### Scenario 3: Starting Next Development Cycle

```bash
# Current: 1.1.0 (stable release)
# Start next iteration

task version-set -- 1.1.0-rc0
# VERSION now: 1.1.0-rc0

git add VERSION pyproject.toml
git commit -m "chore: start 1.1.0 development cycle"
git push

# Future merges will generate 1.1.0-rc0+g<sha> artifacts
```

## Implementation Details

### `scripts/version_manager.py`

Python script for version manipulation:
- Parses VERSION file (format: `MAJOR.MINOR.PATCH[-rcN]`)
- Updates both VERSION and pyproject.toml atomically
- Generates full version with commit SHA for RC builds (PEP 440 compliant)

### GitHub Actions Workflows

- **`test.yml`**: Runs on PR, validates version consistency
- **`deploy-docs-multi.yml`**: Deploys docs with appropriate version
- **`publish-package.yml`**: Publishes package with version metadata

### Taskfile Tasks

- `task version`: Show current version
- `task version-full`: Show version with commit SHA (if RC)
- `task version-bump-rc`: Increment RC number
- `task version-bump-minor`: Finalize and bump minor version
- `task version-bump-major`: Finalize and bump major version
- `task version-set -- <version>`: Set specific version
- `task version-check`: Verify VERSION ↔ pyproject.toml consistency

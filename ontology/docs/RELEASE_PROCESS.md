# Release Process

This document describes the complete release process for `oxp-ontology`.

## Overview

The release process ensures that:
- All tests pass
- Documentation is up-to-date
- Versions are properly tagged
- Artifacts are published with traceability
- Downstream consumers can integrate smoothly

## Release Types

### Release Candidate (RC)
Used during development for testing and stakeholder previews.

### Final Release
Stable version for production use.

---

## Pre-Release Checklist

Before starting any release (RC or final):

- [ ] All tests passing locally (`task test`)
- [ ] TTL files validated (`task validate-ttl`)
- [ ] Version consistency verified (`task version-check`)
- [ ] No uncommitted changes (`git status`)
- [ ] Branch is up-to-date with `main`
- [ ] PR reviews completed (if applicable)

---

## RC Release Process

Release Candidates are for testing iterations before stable release.

### 1. Verify Current State

```bash
cd oxp-ontology
git checkout feat/metrics-ontology  # or your feature branch
git pull origin feat/metrics-ontology

# Check current version
task version
# Output: 1.0.0-rc0
```

### 2. Run Tests

```bash
# Run all tests locally
task test

# Validate TTL files
task validate-ttl

# Check version consistency
task version-check
```

### 3. Merge PR to Main

1. Ensure PR is approved and ready
2. Merge via GitHub UI (squash or merge commit)
3. Pull latest main locally:

```bash
git checkout main
git pull origin main
```

### 4. Automatic Build (No Action Required)

After merge, GitHub Actions automatically:
- ✅ Runs test workflow (`.github/workflows/test.yml`)
- ✅ Deploys multi-ontology docs (`.github/workflows/deploy-docs-multi.yml`)
  - Adds commit SHA to version: `1.0.0-rc0+g<sha>`
  - Deploys to GitHub Pages with version in footer

**Result**: Docs available at `https://outshift-open.github.io/oxp-ontology/`

### 5. (Optional) Publish RC Package

If you need to publish the Python package for testing:

1. Go to GitHub Actions → **Publish Python Package**
2. Click **Run workflow**
3. Select `main` branch
4. Bump type: `none` (or `rc` to increment rc0 → rc1)
5. Run workflow

**Result**: Pre-release created on GitHub Releases with artifacts tagged as `v1.0.0-rc0+g<sha>`

### 6. Increment RC Number (If Continuing Development)

If you want to signal progress to stakeholders:

```bash
task version-bump-rc
# 1.0.0-rc0 → 1.0.0-rc1

git add VERSION pyproject.toml
git commit -m "chore: bump to rc1"
git push origin main
```

---

## Final Release Process

Use this process when RC testing is complete and you're ready for a stable release.

### 1. Verify RC Testing Complete

- [ ] All RC testing passed
- [ ] Stakeholders approved
- [ ] No known blocking issues
- [ ] Downstream integrations tested (MCE can import package)

### 2. Finalize Version

```bash
cd oxp-ontology
git checkout main
git pull origin main

# Remove RC, increment version
task version-bump-minor   # 1.0.0-rc3 → 1.1.0
# OR
task version-bump-major   # 1.0.0-rc3 → 2.0.0

# Check result
task version
# Output: 1.1.0
```

### 3. Update CHANGELOG

Edit `CHANGELOG.md`:

```markdown
## [1.1.0] - 2026-02-12

### Added
- Unit tests for Python package with pytest
- Multi-ontology documentation (mas/metrics)
- Versioning system with commit SHA for RC builds

### Changed
- Documentation now covers both deployed ontologies
- Test workflow runs on every PR

### Fixed
- TTL validation integrated into CI/CD

[1.1.0]: https://github.com/outshift-open/observe-and-explain-platform/ontology/compare/v1.0.0...v1.1.0
```

### 4. Commit and Push

```bash
git add VERSION pyproject.toml CHANGELOG.md
git commit -m "chore: release v1.1.0"
git push origin main
```

### 5. Create Git Tag

```bash
git tag v1.1.0
git push origin v1.1.0
```

**Result**: Pushing the tag triggers `.github/workflows/publish-package.yml` which:
- ✅ Builds Python package with clean version (no commit SHA)
- ✅ Creates GitHub Release (not pre-release)
- ✅ Uploads package artifacts (`.whl`, `.tar.gz`)
- ✅ Generates release notes

### 6. Verify Release

1. Check GitHub Releases: `https://github.com/outshift-open/observe-and-explain-platform/releases`
2. Verify artifacts are attached
3. Check GitHub Pages docs have clean version: `https://outshift-open.github.io/oxp-ontology/`

### 7. (Optional) Publish to PyPI

If publishing to public PyPI or private registry:

```bash
# Build package
task build

# Check package
twine check dist/*

# Upload (replace with your registry)
twine upload dist/* --repository-url <your-registry-url>
```

### 8. Start Next Development Cycle

```bash
# Bump to next RC
task version-set -- 1.1.0-rc0

git add VERSION pyproject.toml
git commit -m "chore: start v1.1.0 development cycle"
git push origin main
```

---

## Hotfix Release Process

For urgent fixes to production releases:

### 1. Create Hotfix Branch

```bash
git checkout v1.1.0  # Last stable release
git checkout -b hotfix/1.1.1
```

### 2. Apply Fix

```bash
# Make changes to TTL files or code
git add .
git commit -m "fix: correct owl:Class definition"
```

### 3. Test

```bash
task test
task validate-ttl
```

### 4. Bump Patch Version

```bash
task version-set -- 1.1.1

git add VERSION pyproject.toml
git commit -m "chore: hotfix release v1.1.1"
```

### 5. Merge to Main

```bash
git checkout main
git merge hotfix/1.1.1
git push origin main
```

### 6. Tag and Release

```bash
git tag v1.1.1
git push origin v1.1.1
```

---

## Rollback Process

If a release has critical issues:

### Option 1: New Hotfix Release

Create `v1.1.1` hotfix following process above.

### Option 2: Delete Tag and Re-Release

**⚠️ Only if release was just published and not yet consumed**

```bash
# Delete remote tag
git push --delete origin v1.1.0

# Delete local tag
git tag -d v1.1.0

# Delete GitHub Release via UI

# Fix issues, re-tag, and re-release
```

---

## Post-Release Tasks

After a final release:

- [ ] Update downstream repositories:
  - [ ] `oxp-lib/mce`: Update `oxp-ontology` dependency in `pyproject.toml`
  - [ ] `oxp-backend`: Update if using ontology directly
- [ ] Announce release in team channels
- [ ] Update documentation if ontology structure changed significantly
- [ ] Archive old RC documentation (if needed)

---

## Release Automation Summary

| Trigger | Workflow | Action |
|---------|----------|--------|
| **PR to main** | `test.yml` | Run tests, validate TTL, check version |
| **Merge to main** | `deploy-docs-multi.yml` | Generate docs for all ontologies |
| **Push tag `vX.Y.Z`** | `publish-package.yml` | Build package, create GitHub Release |
| **Manual workflow** | `publish-package.yml` | Publish RC with optional version bump |

---

## Troubleshooting

### Tests Fail on CI But Pass Locally

```bash
# Ensure you're testing with same Python versions
task test  # Uses local Python

# Check CI logs for specific failure
# Often due to missing dependencies or version mismatches
```

### Documentation Not Deploying

- Check `.github/workflows/deploy-docs-multi.yml` logs
- Verify Java 17, Node 18, Python 3.11 installed on runner
- Check Widoco JAR download succeeded
- Verify TTL files parse correctly: `task validate-ttl`

### Version Mismatch Error

```bash
# Fix manually
task version-check  # Shows mismatch

# Update pyproject.toml to match VERSION
python3 scripts/version_manager.py set $(cat VERSION)
```

### Package Build Fails

```bash
# Clean and rebuild
task clean
task build

# Check pyproject.toml syntax
python3 -m build --wheel --outdir dist/
```

### Can't Push Tag (Already Exists)

```bash
# Check existing tags
git tag -l "v1.*"

# If you need to re-tag (⚠️ dangerous):
git tag -d v1.1.0
git push --delete origin v1.1.0
git tag v1.1.0
git push origin v1.1.0
```

---

## References

- [VERSIONING.md](VERSIONING.md) - Versioning strategy details
- [README.md](../README.md) - General project documentation
- [CHANGELOG.md](../CHANGELOG.md) - Release history
- [Semantic Versioning](https://semver.org/)
- [PEP 440](https://peps.python.org/pep-0440/) - Python version identifiers

---

## Quick Reference

```bash
# Check current version
task version

# Run tests
task test

# Validate TTL
task validate-ttl

# Bump versions
task version-bump-rc      # rc0 → rc1
task version-bump-minor   # 1.0.0-rc3 → 1.1.0
task version-bump-major   # 1.0.0-rc3 → 2.0.0

# Build package
task build

# Release workflow
git add VERSION pyproject.toml CHANGELOG.md
git commit -m "chore: release vX.Y.Z"
git push origin main
git tag vX.Y.Z
git push origin vX.Y.Z
```

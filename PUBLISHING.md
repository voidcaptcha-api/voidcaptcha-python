# Publishing voidcaptcha to PyPI

No API token is stored anywhere. PyPI trusts one workflow file in one repository
(Trusted Publishing). You set that up once; every release after that is a GitHub release.

## One-time setup

**1. Push this folder to GitHub**

- On github.com, in the `voidcaptcha-api` organisation: **New repository** → name
  `voidcaptcha-python` → Public → no README/licence (this folder has them) → **Create**.
- Then, in this folder:

```bash
git remote add origin https://github.com/voidcaptcha-api/voidcaptcha-python.git
git push -u origin main
```

- The **CI** workflow runs on that push. Check the Actions tab is green.

**2. Add a pending publisher on PyPI** (works before the project exists)

- pypi.org → log in → your account menu → **Your projects** → **Publishing** (left side).
- Under **Add a new pending publisher** → **GitHub** tab, fill in exactly:

| Field | Value |
|---|---|
| PyPI Project Name | `voidcaptcha` |
| Owner | `voidcaptcha-api` |
| Repository name | `voidcaptcha-python` |
| Workflow name | `release.yml` |
| Environment name | `pypi` |

- **Add**.

**3. Create the `pypi` environment on GitHub**

- Repo → **Settings** → **Environments** → **New environment** → `pypi` → **Configure**.
- Optional but recommended: **Required reviewers** → add yourself. Then every publish waits
  for your click in the Actions tab.

## Releasing a version

1. Set the version in `src/voidcaptcha/_version.py` and add a line to `CHANGELOG.md`. Commit, push.
2. GitHub → repo → **Releases** → **Draft a new release** → **Choose a tag** → type `v0.1.0`
   (must be `v` + the version in `_version.py`) → **Create new tag** → title `v0.1.0` → **Publish release**.
3. Actions tab → **Release** run → approve if you set reviewers. It tests, builds and publishes.
4. Check https://pypi.org/project/voidcaptcha/ and `pip install voidcaptcha`.

The first publish turns the pending publisher into a normal one; nothing else to do.
A version number can never be reused on PyPI, even after deleting it.

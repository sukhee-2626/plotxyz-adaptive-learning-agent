# Publishing status and recovery

The 40 projects are generated under `projects/`. Local validation is recorded in
`validation-tests.json`, `validation-builds.json`, `manifest.json`, and `PROGRESS.md`.

## Authentication

- GitHub account: `sukhee-2626`
- `gh` CLI is not installed in this environment.
- Repository creation and verification use the authenticated GitHub REST API.
- Git pushes use the credential already configured for `github.com`.

Never print or commit the access token.

## Verified repositories

See `PROGRESS.md` for the authoritative per-repository table. The first ten
repositories were created and verified before GitHub applied a temporary
secondary content-creation limit. The scheduled retry job creates the remaining
repositories after the reset window and verifies each `main` branch with
`git ls-remote`.

## Manual recovery for one repository

```powershell
$slug = "plotxyz-example-agent"
$path = "C:\Users\HP\todo-app\agentforge-40\projects\$slug"

# Create the repository through the authenticated REST API, then:
Push-Location $path
git init -b main
git config user.name "sukhee-2626"
git config user.email "sukhee-2626@users.noreply.github.com"
git add -A
git commit -m "Initial PlotXYZ.ai agent MVP"
git remote add origin "https://github.com/sukhee-2626/$slug.git"
git push -u origin main
git ls-remote --heads origin main
Pop-Location
```

Do not report a URL as published until `git ls-remote` returns `refs/heads/main`
and the GitHub API reports the repository as public.

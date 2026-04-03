# Web Skill Scanner

This folder contains a Flask-based workflow for:

1. submitting a GitHub repository URL and optional skill name
2. cloning or refreshing the repository locally
3. locating `SKILL.md` candidates
4. running the existing analyzer for one selected skill
5. rendering a concise result page

## Run Locally

From repo root:

```bash
python -m flask --app web.app run --debug
```

Open `http://127.0.0.1:5000`.

## Workspace Paths

- Repositories cache: `web/workspaces/repos`
- Analyzer run outputs: `web/workspaces/runs`

The app persists only one case JSON per scan target:

- `web/workspaces/runs/<repo-name>/<skill-name>/<skill-name>.json`

Intermediate analyzer artifacts are generated in temporary directories and cleaned automatically.

## Routes

- `GET /` - input form
- `POST /scan` - initial scan attempt
- `POST /scan/select-skill` - fallback selection flow

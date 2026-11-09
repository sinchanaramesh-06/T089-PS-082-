# GitHub hand-off guide

Run these commands from the `carbon_exchange_week2` project root.

## First upload
```bash
git init
git add .
git commit -m "Week 2: add carbon exchange core flows and sample data"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/carbon-exchange.git
git push -u origin main
```

## Regular commits
After completing a module or fixing a tested issue:
```bash
git add .
git commit -m "Add auction clearing and pro-rata allocation"
git push
```

## Share with mentor
- If the repository is private, open GitHub repository Settings → Collaborators and invite the mentor's GitHub username.
- Send the repository URL to your mentor.
- Do not commit `.venv/`, API keys, passwords, or local environment files.

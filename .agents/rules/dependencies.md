# Dependency & Environment Policy

1. **Local Installation Only**:
   - All packages, dependencies, and libraries must ONLY be installed within this project directory (`d:\Earth_College\sem 5\SDL\Prototype`).
   - Never install packages globally or outside this project workspace.

2. **Python Virtual Environment**:
   - Always use the local virtual environment located at `.venv`:
     - Windows PowerShell / CMD: `.\.venv\Scripts\python.exe` and `.\.venv\Scripts\pip.exe`
     - Activate script: `.\.venv\Scripts\Activate.ps1`
   - When installing Python packages:
     `.\.venv\Scripts\pip.exe install <package>` or `.\.venv\Scripts\python.exe -m pip install <package>`
   - Never run global `pip install` or `pip install --user`.

3. **Node.js / Web Dependencies (if applicable)**:
   - Always run `npm install` within this project root so dependencies reside in local `./node_modules`.
   - Never use `-g` (global) install.

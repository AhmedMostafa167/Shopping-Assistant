# mini-rag

a minimal implementation on RAG focusing on system design

## Requirements 

- Python 3.11 or above

### install python 

- Download & install using this [python.org](Link)

### install uv for environment management

```bash
pip install uv
```

### Create a Virtual Environment

Set up an isolated environment for your project using uv.

Inside your project folder, Run:

```bash
uv init
uv venv
```

This creates a .venv directory with a fresh Python environment

### Activate the Environment
Activate the virtual environment to use its Python interpreter.

Activation commands:

Linux/macOS: 
```bash
source .venv/bin/activate
```

Windows PowerShell: 
```bash
.venv\Scripts\Activate.ps1
```

### install dependencies

```bash
uv pip install .
```

### setup environment variables

```bash
cp .env.example .env
```
and then set your environment variables like API keys
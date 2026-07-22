# mini-rag

a minimal implementation on RAG focusing on system design

## Requirements 

- Python 3.11 or above

### install python 

- Download & install using this [python.org](Link)

### install uv for environment management
- I love it cuz it makes my life easier when dealing with dependencies!
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
Linux: 
```bash
source .venv/bin/activate
```
### install dependencies

```bash
uv pip install .
```
### dependencies for Ubuntu or any other Linux distribution

```bash
sudo apt update
sudo apt install libpq-dev gcc python3-dev
```
### setup environment variables

```bash
cp .env.example .env
```
and then set your environment variables like API keys
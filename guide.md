# Kaufee-Home User Guide

## Windows 10/11

1. Install Python 3.11 or newer and Git.
2. Open PowerShell and clone the project:

   ```powershell
   git clone https://github.com/DaKaufeeBoii/Kaufee-Home.git
   cd Kaufee-Home
   ```

3. Create and activate a virtual environment:

   ```powershell
   py -3.11 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

4. Install Kaufee:

   ```powershell
   python -m pip install --upgrade pip
   pip install -e .
   ```

5. Check the installation and try an offline task:

   ```powershell
   kaufee --help
   kaufee run "List the files in the workspace" --provider mock
   ```

6. Run your own task:

   ```powershell
   kaufee run "Create a Python program that prints Hello World"
   ```

   To create a folder and put a program in it, describe both in the goal. Kaufee creates parent folders for file paths automatically. For example:

   ```powershell
   kaufee run "Create a folder named test001 and write a Python program in it that reads numbers from the user and prints the largest" --workspace "C:\\Users\\YourName\\KaufeeWork"
   ```

7. Use `--workspace` to choose where Kaufee works:

   ```powershell
   kaufee run "List the files in the workspace" --workspace "C:\Users\YourName\Documents\KaufeeWork" --provider mock
   ```

8. To restore the latest backup for a path:

   ```powershell
   kaufee undo hello.py
   ```

## macOS and Linux

1. Install Python 3.11 or newer and Git using your operating system's package manager.
2. Open a terminal and clone the project:

   ```bash
   git clone https://github.com/DaKaufeeBoii/Kaufee-Home.git
   cd Kaufee-Home
   ```

3. Create and activate a virtual environment:

   ```bash
   python3.11 -m venv .venv
   source .venv/bin/activate
   ```

4. Install Kaufee:

   ```bash
   python -m pip install --upgrade pip
   pip install -e .
   ```

5. Check the installation and try an offline task:

   ```bash
   kaufee --help
   kaufee run "List the files in the workspace" --provider mock
   ```

6. Run your own task:

   ```bash
   kaufee run "Create a Python program that prints Hello World"
   ```

7. Select a workspace when needed:

   ```bash
   kaufee run "List the files in the workspace" --workspace "$HOME/KaufeeWork" --provider mock
   ```

8. Restore the latest backup for a path:

   ```bash
   kaufee undo hello.py
   ```

## Chromebook

1. Enable the Linux development environment in Chromebook settings, if available.
2. Open the Linux Terminal.
3. Follow the macOS/Linux installation steps above.

## Android with Termux

1. Install and open Termux from a trusted distribution source.
2. Install Python and Git:

   ```bash
   pkg update
   pkg install python git
   ```

3. Clone the project and install it:

   ```bash
   git clone https://github.com/DaKaufeeBoii/Kaufee-Home.git
   cd Kaufee-Home
   python -m venv .venv
   source .venv/bin/activate
   python -m pip install --upgrade pip
   pip install -e .
   ```

4. Check it and run a task:

   ```bash
   kaufee --help
   kaufee run "List the files in the workspace" --provider mock
   ```

## iPhone, iPad, or a device that cannot install Python

1. Install an SSH terminal client on the device.
2. Set up Kaufee on a computer or server you control, following its Windows or macOS/Linux installation steps.
3. Connect from the device to that computer or server using SSH.
4. In the remote terminal, change to the project directory and activate its virtual environment.
5. Run Kaufee on the remote machine:

   ```bash
   kaufee run "List the files in the workspace" --provider mock
   ```

## Choose a language model

1. Use the mock provider for offline trial runs:

   ```bash
   kaufee run "List the files in the workspace" --provider mock
   ```

2. To use a local Ollama model, install Ollama on the computer running Kaufee, start Ollama, and download a model:

   ```bash
   ollama serve
   ollama pull qwen2.5-coder:7b
   ```

   Then run Kaufee without `--provider mock`:

   ```bash
   kaufee run "Create a Python program that prints Hello World"
   ```

3. To use a remote OpenAI-compatible provider, set these values in a `.env` file in the project directory:

   ```ini
   KAUFEE_LLM_PROVIDER=remote
   REMOTE_API_BASE_URL=https://api.openai.com/v1
   REMOTE_API_KEY=your-api-key
   REMOTE_MODEL=gpt-4o-mini
   ```

4. Run Kaufee with the remote provider:

   ```bash
   kaufee run "Create a Python program that prints Hello World" --provider remote
   ```

5. To tune Ollama model residency and response length, optionally add these settings to `.env`:

   ```ini
   KAUFEE_OLLAMA_KEEP_ALIVE=10m
   KAUFEE_OLLAMA_NUM_PREDICT=2048
   ```

   A lower token limit can reduce long generations but may truncate a complex plan.

## Interactive use

1. Start the interactive session:

   ```bash
   kaufee interactive
   ```

2. Enter a task at the `kaufee>` prompt.
3. Enter `undo <path>` to restore a backup, or `exit` to close the session.

## Other commands

```bash
kaufee benchmark
kaufee audit
kaufee config
```

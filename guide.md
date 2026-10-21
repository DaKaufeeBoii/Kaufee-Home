# Kaufee-Home: Step-by-Step User Guide

Follow the section for your device. You do not need to understand Python code to give Kaufee a task. You do need Python installed on the computer that runs Kaufee.

## 1. Install Kaufee on Windows

1. Install **Python 3.11 or newer** and **Git**. During Python setup, enable the option to add Python to PATH if the installer offers it.
2. Open **PowerShell**.
3. Copy and run these commands one at a time:

   ```powershell
   git clone https://github.com/DaKaufeeBoii/Kaufee-Home.git
   cd Kaufee-Home
   py -3.11 -m venv .venv
   .\.venv\Scripts\python.exe -m pip install --upgrade pip
   .\.venv\Scripts\python.exe -m pip install -e .
   ```

   If `py -3.11` says Python 3.11 is not installed, install a supported Python version or replace `-3.11` with the version you installed, such as `-3.12`.

4. Check that Kaufee installed:

   ```powershell
   .\.venv\Scripts\kaufee.exe --version
   ```

5. Try the offline example:

   ```powershell
   .\.venv\Scripts\kaufee.exe run "List the files in the workspace" --provider mock
   ```

## 2. Install Kaufee on macOS or Linux

1. Install **Python 3.11 or newer** and **Git** using your operating system's normal installer or package manager.
2. Open **Terminal**.
3. Copy and run these commands one at a time:

   ```bash
   git clone https://github.com/DaKaufeeBoii/Kaufee-Home.git
   cd Kaufee-Home
   python3 -m venv .venv
   .venv/bin/python -m pip install --upgrade pip
   .venv/bin/python -m pip install -e .
   ```

4. Check that Kaufee installed:

   ```bash
   .venv/bin/kaufee --version
   ```

5. Try the offline example:

   ```bash
   .venv/bin/kaufee run "List the files in the workspace" --provider mock
   ```

## 3. Install Kaufee on a Chromebook or Android device

1. On a Chromebook, turn on the **Linux development environment** in Chromebook settings. On Android, install and open **Termux** from its official distribution source.
2. Open the Linux Terminal or Termux.
3. Install Python and Git:

   **Chromebook (Debian-based Linux):**

   ```bash
   sudo apt update
   sudo apt install python3 python3-venv git
   ```

   **Android (Termux):**

   ```bash
   pkg update
   pkg install python git
   ```

4. Check that `python3 --version` (Chromebook) or `python --version` (Termux) says **3.11 or newer**. If it is older, update Python before continuing.
5. Clone and install Kaufee. Use the matching commands for your device:

   **Chromebook:**

   ```bash
   git clone https://github.com/DaKaufeeBoii/Kaufee-Home.git
   cd Kaufee-Home
   python3 -m venv .venv
   .venv/bin/python -m pip install --upgrade pip
   .venv/bin/python -m pip install -e .
   ```

   **Android (Termux):**

   ```bash
   git clone https://github.com/DaKaufeeBoii/Kaufee-Home.git
   cd Kaufee-Home
   python -m venv .venv
   .venv/bin/python -m pip install --upgrade pip
   .venv/bin/python -m pip install -e .
   ```

6. Test the installation with `.venv/bin/kaufee --version`, then try `.venv/bin/kaufee run "List the files in the workspace" --provider mock`.
7. Keep the terminal app open while Kaufee works. Some mobile devices may stop background tasks, and small devices may not have enough memory to run a local AI model.

## 4. Use Kaufee from an iPhone, iPad, or another device without Python

Kaufee does not include a website or a native iPhone/iPad app. Run it on a computer or server you control, then connect to that computer from your device using an SSH terminal app.

1. Install Kaufee on the computer or server by following section 1 or 2.
2. Set up SSH access on that computer using its normal operating-system instructions.
3. Install an SSH terminal app on your phone or tablet and connect to your computer.
4. In the remote terminal, go to the Kaufee-Home folder.
5. Activate the environment on the computer that is running Kaufee:

   **Windows computer (PowerShell):**

   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```

   **macOS/Linux computer:**

   ```bash
   source .venv/bin/activate
   ```

6. Run Kaufee in that terminal. The task and files are handled by the computer you connected to, not by the phone or tablet:

   ```bash
   kaufee run "List the files in the workspace" --provider mock
   ```

## 5. Choose how Kaufee gets its AI responses

Use **one** of these options. The `mock` option is only for checking the installation; it cannot handle every kind of task.

### Option A: Quick offline installation check

Run a simple example with no AI model:

```text
kaufee run "List the files in the workspace" --provider mock
```

On Windows, if you did not activate the virtual environment, use:

```powershell
.\.venv\Scripts\kaufee.exe run "List the files in the workspace" --provider mock
```

### Option B: Use a model on your own computer with Ollama

1. Install Ollama on the computer that runs Kaufee.
2. Start Ollama. Leave it running while you use Kaufee.
3. In a terminal, download the default coding model:

   ```bash
   ollama pull qwen2.5-coder:7b
   ```

4. Run a real task from the Kaufee-Home folder:

   ```text
   kaufee run "Create a Python file named hello.py that prints Hello"
   ```

Kaufee uses Ollama by default. If your device is slow or does not have enough memory, use a smaller model that Ollama supports, or use a remote model instead.

### Option C: Use a remote AI provider

1. Open a terminal in the Kaufee-Home folder.
2. Make a private settings file by copying the example:

   **Windows PowerShell:**

   ```powershell
   Copy-Item .env.example .env
   notepad .env
   ```

   **macOS/Linux/Chromebook/Termux:**

   ```bash
   cp .env.example .env
   nano .env
   ```

3. In `.env`, set the provider and fill in the API key and model name your provider gave you:

   ```ini
   KAUFEE_LLM_PROVIDER=remote
   REMOTE_API_BASE_URL=https://api.openai.com/v1
   REMOTE_API_KEY=paste-your-private-key-here
   REMOTE_MODEL=gpt-4o-mini
   ```

4. Save and close the file.
5. Run a task with the remote provider:

   ```text
   kaufee run "Create a Python file named hello.py that prints Hello" --provider remote
   ```

6. Never paste your API key into a task, share it in a screenshot, or commit the `.env` file to Git. A remote provider receives the prompts sent to it; use Ollama if you need the prompts to stay on your computer.

## 6. Give Kaufee a task

1. Open a terminal in the Kaufee-Home folder. If you are not in that folder, activate its virtual environment first.
2. Put your request in quotation marks after `kaufee run`:

   ```text
   kaufee run "Create a Python file named hello.py that prints Hello"
   ```

3. To choose exactly where Kaufee works, add `--workspace` and a folder path:

   **Windows PowerShell:**

   ```powershell
   kaufee run "List the files in the workspace" --workspace "C:\Users\YourName\KaufeeWork"
   ```

   **macOS/Linux:**

   ```bash
   kaufee run "List the files in the workspace" --workspace "$HOME/KaufeeWork"
   ```

4. By default, Kaufee uses a folder named `workspace` under the folder where you run the command.
5. If you want a **folder**, say “create a folder named …”. If you want a **file inside it**, say that too. Example:

   ```text
   kaufee run "Create a folder named test001 and create a Python file named largest.py inside it. The program must ask me for numbers and print the largest number."
   ```

   A folder is created with directory tools; a file is created with file tools. Naming a folder alone does not make it a Python file.

## 7. Approve actions safely

1. Read every approval prompt before answering. It shows the action, risk, and arguments.
2. Type **yes** only if you understand the action and trust the task. Type **no** or press Enter to reject it.
3. Kaufee asks for approval before running generated Python and before deleting files by default.
4. Do not add `--yes` or `-y` unless you intentionally want Kaufee to approve risky actions without asking you.
5. Generated Python is **not isolated** from your computer. Approved code can use the files, network, and account permissions available to your operating-system user. Do not run tasks or code you do not trust.

## 8. Check results, undo, and exit

1. A green **Task Completed Successfully** result means Kaufee's checks passed. A red **Task Did Not Complete Successfully** result means the task did not pass; read the reason shown in the terminal.
2. If Kaufee changed a file and you want to restore its latest backup, run:

   ```text
   kaufee undo hello.py
   ```

   Add the same `--workspace "path"` option if the file is in a workspace other than the default one. Undo needs a backup created by Kaufee.

3. Useful commands:

   ```text
   kaufee --help
   kaufee config
   kaufee audit
   kaufee benchmark
   kaufee interactive
   ```

4. If you started `kaufee interactive`, type `exit` to close it. Type `help` inside it to see its special commands.

## 9. Fix common installation problems

1. If the terminal says **`kaufee` is not recognized** or **`command not found`**, either activate the virtual environment or run the Kaufee executable directly:

   **Windows PowerShell:** `.\.venv\Scripts\Activate.ps1`, then run `kaufee ...`; or use `.\.venv\Scripts\kaufee.exe ...`.

   **macOS/Linux/Chromebook/Termux:** `source .venv/bin/activate`, then run `kaufee ...`; or use `.venv/bin/kaufee ...`.

2. If Kaufee cannot connect to Ollama, make sure Ollama is installed and running on the **same computer** that runs Kaufee.
3. If a task is too slow, use a smaller Ollama model or increase the model request timeout with `--timeout 600`.
4. If Python reports that a package is missing, return to the Kaufee-Home folder, activate `.venv`, and run `python -m pip install -e .` again.

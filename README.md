# AI Code Tutor 🚀

An intelligent web application that serves as a programming tutor. Instead of simply giving away answers to coding errors, it executes user code and provides guided, multi-tiered hints.

## 🛠️ Tech Stack
* **Backend:** Python (Flask / FastAPI)
* **Code Execution:** Self-hosted [Judge0](https://judge0.com/) instance via Docker Desktop
* **AI Engine:** Groq API (LLaMA-3) for generating 3-level progressive hints

## ⚙️ How It Works
1. **Submit Code:** The user writes and submits Python code in the browser interface.
2. **Secure Execution:** The backend sends the code to the local Judge0 container running on port `2358`.
3. **Analyze Error:** If the code fails, the execution error is sent to the Groq API.
4. **Smart Hints:** The AI evaluates the stack trace and returns a conceptual hint, a structural hint, and a solution hint without spoiling the answer right away.

## 🚀 How to Run Locally
1. Start **Docker Desktop** and ensure the `judge0` containers are running.
2. Start the web application:
   ```bash
   python app.py

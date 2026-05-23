# Code Helper

A web-based coding assistant that helps you practice data structures and algorithms. Write code, run it locally with [Judge0](https://github.com/judge0/judge0), and get progressive AI-powered hints when you're stuck—without spoiling the answer upfront.

## Features

- **Problem + code workspace** — Enter a problem statement and your solution side by side.
- **Run code** — Execute Python, Java, or C with optional custom stdin via Judge0.
- **Progressive hints** — Three levels of hints (general → approach → specific), revealed one at a time.
- **Full solution** — Optional complete solution after you've worked through the hints.
- **Correct-code detection** — If your solution is already correct, you get a success message instead of more hints.
- **Multi-language support** — Python, Java, and C.

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | [Flask](https://flask.palletsprojects.com/) |
| AI hints | [Groq](https://groq.com/) (Llama 3.3 70B) |
| Code execution | [Judge0](https://github.com/judge0/judge0) (Docker) |
| Frontend | HTML, Tailwind CSS (CDN) |

## Prerequisites

- **Python 3.10+** (Windows: use `py` if `python` is not on PATH)
- **Docker Desktop** (for Judge0)
- **Groq API key** — [Get one free](https://console.groq.com/)

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git
cd YOUR_REPO
```

### 2. Install Python dependencies

```bash
py -m pip install -r requirements.txt
```

On Linux/macOS, use `python3 -m pip` instead of `py`.

### 3. Configure environment variables

Create a `.env` file in the project root:

```env
GROQ_API_KEY=your_groq_api_key_here

# Optional — defaults to http://localhost:2358
JUDGE0_URL=http://localhost:2358
```

> **Note:** `.env` is listed in `.gitignore` and should never be committed.

### 4. Start Judge0 (Docker)

Download and extract [Judge0 v1.13.1](https://github.com/judge0/judge0/releases) into a folder named `judge0-v1.13.1` at the project root (this folder is gitignored).

From inside that directory:

```bash
docker compose up -d
```

Verify Judge0 is running:

```bash
curl http://localhost:2358/about
```

Or run the included test script:

```bash
py test_judge0.py
```

### 5. Run the Flask app

```bash
py app.py
```

Open **http://127.0.0.1:5000** in your browser.

## Usage

1. Paste or type your **problem statement**.
2. Write your **code** and select the language (Python, Java, or C).
3. Click **Run Code** to execute with optional custom input.
4. Click **Get Hint** for AI feedback:
   - If your code is **correct**, you'll see a green success message—no hints.
   - Otherwise, you'll get **Hint 1**, then unlock Hints 2 and 3, and optionally the full solution.

## Project Structure

```
.
├── app.py                 # Flask routes, Judge0 execution, Groq hints API
├── requirements.txt       # Python dependencies
├── templates/
│   └── index.html         # Web UI
├── test_judge0.py         # Quick Judge0 connectivity check
├── judge0-v1.13.1/        # Judge0 Docker setup (not in git — see Setup)
│   ├── docker-compose.yml
│   └── judge0.conf
└── .env                   # Secrets (not in git)
```

## API Routes

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Main UI |
| `POST` | `/run-code` | Execute code via Judge0 |
| `POST` | `/get-hints` | Analyze code and return hints or correct status |

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GROQ_API_KEY` | Yes | API key for Groq (AI hints) |
| `JUDGE0_URL` | No | Judge0 base URL (default: `http://localhost:2358`) |

## Troubleshooting

| Issue | What to try |
|-------|-------------|
| `Cannot connect to Judge0` | Ensure Docker is running and `docker compose up` was run in `judge0-v1.13.1`. |
| `Groq client not initialized` | Check `GROQ_API_KEY` in `.env` and restart the app. |
| `python` not found (Windows) | Use `py app.py` instead of `python app.py`. |
| Hints not parsing | Retry; the AI is prompted to return JSON only. |

## License

This project is open source. Add your preferred license (e.g. MIT) before publishing.

## Acknowledgments

- [Judge0](https://github.com/judge0/judge0) — Secure code execution
- [Groq](https://groq.com/) — Fast LLM inference for hints

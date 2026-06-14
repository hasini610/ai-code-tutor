from flask import Flask, render_template, request, jsonify, abort, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from groq import Groq
import ast
import os
import re
import html
import requests
import json
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, timezone# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'default-secret-key-change-me')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)

class SolvedProblem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    problem_id = db.Column(db.Integer, nullable=False)

class Submission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    problem_id = db.Column(db.Integer, nullable=False)
    code = db.Column(db.Text, nullable=False)
    language = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(50), nullable=False)  # 'passed', 'partial', 'failed'
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

with app.app_context():
    db.create_all()


# Debug API key loading
api_key = os.getenv('GROQ_API_KEY')
if api_key:
    print("API Key Loaded")
else:
    print("API Key Missing")

# Initialize Groq client
groq_client = None
try:
    if api_key:
        groq_client = Groq(api_key=api_key)
        print("Groq client initialized successfully")
        print(f"Groq client type: {type(groq_client)}")
    else:
        print("Cannot initialize Groq client: No API key provided")
except Exception as e:
    print(f"Error initializing Groq client: {e}")
    print(f"Exception type: {type(e)}")
    groq_client = None

# Debug: Check final state
print(f"Final groq_client state: {groq_client is not None}")

# Judge0 API configuration
JUDGE0_URL = os.getenv('JUDGE0_URL', 'http://localhost:2358').rstrip('/')
JUDGE0_LANGUAGE_IDS = {
    'python': 71,
    'java': 62,
    'c': 50,
}

PROCESSED_PROBLEMS_PATH = Path(__file__).resolve().parent / 'processed_problems.json'
_problems_by_id: dict[int, dict] | None = None


def load_problems_dataset() -> dict:
    if not PROCESSED_PROBLEMS_PATH.is_file():
        return {'problems': [], 'counts_by_difficulty': {}}
    with PROCESSED_PROBLEMS_PATH.open(encoding='utf-8') as f:
        return json.load(f)


def get_problems_by_id() -> dict[int, dict]:
    global _problems_by_id
    if _problems_by_id is None:
        data = load_problems_dataset()
        _problems_by_id = {}
        for problem in data.get('problems', []):
            pid = problem.get('id')
            if pid is not None:
                _problems_by_id[int(pid)] = problem
    return _problems_by_id


def parse_llm_json_response(raw_text: str) -> dict:
    """Parse Groq JSON-only responses, tolerating fenced markdown blocks."""
    hints_text = raw_text.strip()
    if '```' in hints_text:
        parts = hints_text.split('```')
        if len(parts) >= 2:
            hints_text = parts[1].strip()
            if hints_text.lower().startswith('json'):
                hints_text = hints_text[4:].strip()
    try:
        data = json.loads(hints_text)
        if not isinstance(data, dict):
            raise ValueError('Invalid response format')
        return data
    except json.JSONDecodeError:
        data = eval(hints_text)  # noqa: S307 — legacy fallback for malformed LLM output
        if not isinstance(data, dict):
            raise ValueError('Invalid response format')
        return data


def format_failing_tests_for_prompt(failing_tests: list) -> str:
    if not failing_tests:
        return 'No failing test results were provided. Infer likely issues from the code and problem statement.'
    blocks = []
    for case in failing_tests:
        blocks.append(
            f"- {case.get('label', 'Test case')} ({case.get('status', 'unknown')}):\n"
            f"  Message: {case.get('message', '')}\n"
            f"  stdin: {repr(case.get('stdin', ''))}\n"
            f"  Expected stdout: {repr(case.get('expected', ''))}\n"
            f"  Actual stdout: {repr(case.get('actual', ''))}"
        )
    return '\n'.join(blocks)


COACH_SYSTEM_PROMPT = """You are a Socratic coding tutor and elite technical interviewer at a top-tier software company.

Your job is to coach a candidate who is stuck on a coding problem using the Socratic method. You will receive:
- The full problem statement
- Their current (broken or failing) solution
- Concrete failing test case details (stdin, expected vs actual output, errors)

Analyze their code and identify the ROOT issue. Prioritize problems in this strict order:
1. CONCEPT: Do they fundamentally misunderstand the problem, algorithm, or required approach?
2. SYNTAX/STRUCTURE: Are there language-level errors, wrong constructs, or logical structure issues?
3. EDGE CASES: Are there specific inputs or boundary conditions they have not handled?
4. COMPLEXITY: Is their solution correct but uses an inefficient algorithm or data structure?

Always address the HIGHEST priority issue first across all three hints.

Respond ONLY with a valid JSON object. No markdown, no text outside JSON.

If their solution clearly passes all provided failing tests and is correct, respond:
{"status": "correct", "message": "brief encouraging message", "hint1": "", "hint2": "", "hint3": ""}

Otherwise respond:
{"status": "needs_hints", "hint1": "...", "hint2": "...", "hint3": "..."}

The three hints MUST follow the Socratic method — each hint MUST be phrased as a QUESTION that guides the student to discover the answer themselves:
1. hint1 — CONCEPTUAL QUESTION: Ask a broad question about problem understanding, the right approach, or a key pattern. Do NOT state what is wrong — make them think about it.
2. hint2 — STRUCTURAL QUESTION: Ask a more directed question about their specific algorithm, data structures, or step-by-step logic. Still a question, not a statement.
3. hint3 — TARGETED QUESTION: Ask a very specific question pointing to the exact flaw — a particular edge case, a specific line behaviour, or a subtle logical mistake. Still NO code revealed.

Strict rules:
- NEVER include a "solution" field
- NEVER output fenced code blocks or any code syntax in any hint
- NEVER state the answer — ALWAYS ask a guiding question
- ALL THREE hints must end with a question mark (?)
- Do not spell out the fix as literal code or pseudo-code
- Reference failing tests when relevant (wrong output, runtime error, etc.)
- Be concise but insightful (1-3 sentences per hint, must end with ?)"""


def format_problem_description(text: str) -> str:
    """Escape HTML and lightly format markdown-style backticks and paragraphs."""
    if not text:
        return ''
    escaped = html.escape(text)

    def code_replacer(match: re.Match) -> str:
        return (
            f'<code class="rounded bg-slate-800 px-1.5 py-0.5 text-sm text-indigo-300 font-mono">'
            f'{match.group(1)}</code>'
        )

    escaped = re.sub(r'`([^`\n]+)`', code_replacer, escaped)
    paragraphs = [p.strip() for p in escaped.split('\n\n') if p.strip()]
    if not paragraphs:
        return ''
    return ''.join(
        f'<p class="mb-4 last:mb-0">{p.replace(chr(10), "<br>")}</p>' for p in paragraphs
    )


JUDGE0_ACCEPTED_STATUS_ID = 3


def clean_output(text: str | None) -> str:
    """Normalize Judge0 stdout / expected output for comparison."""
    if not text:
        return ''
    return text.replace('\r\n', '\n').replace('\r', '\n').strip()


def find_balanced_expressions(text: str) -> list[str]:
    """Extract top-level bracketed/parenthesized literals from noisy stdout."""
    pairs = [('(', ')'), ('[', ']'), ('{', '}')]
    found: list[str] = []
    for open_b, close_b in pairs:
        i = 0
        while i < len(text):
            if text[i] != open_b:
                i += 1
                continue
            depth = 0
            for j in range(i, len(text)):
                if text[j] == open_b:
                    depth += 1
                elif text[j] == close_b:
                    depth -= 1
                    if depth == 0:
                        found.append(text[i : j + 1])
                        i = j + 1
                        break
            else:
                break
    return found


def output_parse_candidates(text: str) -> list[str]:
    """Build candidate strings to parse from raw program stdout."""
    cleaned = clean_output(text)
    if not cleaned:
        return []

    candidates: list[str] = [cleaned]
    seen: set[str] = set()

    def add(value: str) -> None:
        value = value.strip()
        if value and value not in seen:
            seen.add(value)
            candidates.append(value)

    add(re.sub(
        r'^(?:output|result|answer|return|stdout)\s*[:=]\s*',
        '',
        cleaned,
        count=1,
        flags=re.IGNORECASE,
    ))

    for line in cleaned.split('\n'):
        line = line.strip()
        if not line:
            continue
        add(line)
        add(re.sub(
            r'^(?:output|result|answer|return|stdout)\s*[:=]\s*',
            '',
            line,
            count=1,
            flags=re.IGNORECASE,
        ))

    for expr in find_balanced_expressions(cleaned):
        add(expr)

    return candidates


def parse_output_value(text: str):
    """Parse stdout into a comparable Python value when possible."""
    for candidate in output_parse_candidates(text):
        try:
            return ast.literal_eval(candidate)
        except (ValueError, SyntaxError):
            continue

    cleaned = clean_output(text)
    if not cleaned:
        return ''

    low = cleaned.lower()
    if low in ('true', 'false'):
        return low == 'true'

    stripped = re.sub(
        r'^(?:output|result|answer|return|stdout)\s*[:=]\s*',
        '',
        cleaned,
        count=1,
        flags=re.IGNORECASE,
    ).strip()
    if stripped != cleaned:
        try:
            if '.' in stripped:
                return float(stripped)
            return int(stripped)
        except ValueError:
            return stripped

    try:
        if '.' in cleaned:
            return float(cleaned)
        return int(cleaned)
    except ValueError:
        return cleaned


def outputs_match(actual: str, expected: str) -> bool:
    """Compare outputs semantically (e.g. [5,4,3] equals [5, 4, 3])."""
    actual_clean = clean_output(actual)
    expected_clean = clean_output(expected)
    if actual_clean == expected_clean:
        return True

    actual_val = parse_output_value(actual_clean)
    expected_val = parse_output_value(expected_clean)
    return actual_val == expected_val


def is_test_case_configured(test_case: dict) -> bool:
    stdin = (test_case.get('input') or '').strip()
    expected = (test_case.get('expected_output') or '').strip()
    return bool(stdin or expected)


def evaluate_test_case(source_code: str, language: str, test_case: dict, index: int) -> dict:
    label = f'Test Case {index}'
    stdin = test_case.get('input') or ''
    expected = clean_output(test_case.get('expected_output'))

    if not is_test_case_configured(test_case):
        return {
            'index': index,
            'label': label,
            'passed': None,
            'status': 'skipped',
            'message': 'Not configured yet (empty input and expected output).',
            'expected': '',
            'actual': '',
            'stdin': stdin,
        }

    # Ensure stdin ends with a newline so C scanf loops terminate correctly
    if stdin and not stdin.endswith('\n'):
        stdin = f"{stdin}\n"

    execution = execute_code(source_code, language, stdin=stdin)
    actual = clean_output(execution.get('stdout'))
    status_id = execution.get('status_id')
    status_desc = execution.get('status') or ''

    # Map Judge0 status IDs to user-friendly messages
    friendly_msg = ''
    if status_id == 5:
        friendly_msg = 'Time Limit Exceeded'
    elif status_id == 6:
        friendly_msg = 'Memory Limit Exceeded'
    elif status_id == 7:
        # Runtime error – could be killed (SIGKILL) or other crash
        friendly_msg = 'Runtime Error'
        # Include any stderr/killed info
        if execution.get('stderr'):
            friendly_msg += f": {extract_first_line(execution.get('stderr'))}"
        elif execution.get('error'):
            friendly_msg += f": {extract_first_line(execution.get('error'))}"
    elif status_id and status_id != JUDGE0_ACCEPTED_STATUS_ID:
        friendly_msg = status_desc or 'Execution failed'

    if execution.get('error') and status_id != JUDGE0_ACCEPTED_STATUS_ID:
        detail = execution.get('compile_output') or execution.get('stderr') or execution.get('error') or 'Execution failed'
        return {
            'index': index,
            'label': label,
            'passed': False,
            'status': 'error',
            'message': friendly_msg or str(detail).strip()[:500],
            'expected': expected,
            'actual': actual,
            'stdin': stdin,
        }

    if status_id != JUDGE0_ACCEPTED_STATUS_ID:
        detail = execution.get('stderr') or execution.get('status') or 'Program did not complete successfully'
        return {
            'index': index,
            'label': label,
            'passed': False,
            'status': 'error',
            'message': friendly_msg or str(detail).strip()[:500],
            'expected': expected,
            'actual': actual,
            'stdin': stdin,
        }

    if outputs_match(actual, expected):
        return {
            'index': index,
            'label': label,
            'passed': True,
            'status': 'passed',
            'message': 'Passed',
            'expected': expected,
            'actual': actual,
            'stdin': stdin,
        }

    return {
        'index': index,
        'label': label,
        'passed': False,
        'status': 'failed',
        'message': f'Failed — Expected {expected!r} but got {actual!r}',
        'expected': expected,
        'actual': actual,
        'stdin': stdin,
    }


def run_test_suite(source_code: str, language: str, test_cases: list) -> dict:
    results = []
    for i, test_case in enumerate(test_cases, start=1):
        results.append(evaluate_test_case(source_code, language, test_case, i))

    runnable = [r for r in results if r['status'] != 'skipped']
    passed_count = sum(1 for r in runnable if r['passed'] is True)
    total_runnable = len(runnable)
    all_passed = total_runnable > 0 and passed_count == total_runnable

    return {
        'results': results,
        'passed': passed_count,
        'total': total_runnable,
        'all_passed': all_passed,
    }


def execute_code(script, language='python', stdin=''):
    """Execute code using local Judge0 API."""
    try:
        language_id = JUDGE0_LANGUAGE_IDS.get(language, JUDGE0_LANGUAGE_IDS['python'])
        payload = {
            'source_code': script,
            'language_id': language_id,
            'stdin': stdin or '',
        }
        url = f'{JUDGE0_URL}/submissions?wait=true&base64_encoded=false'
        print(f'Judge0 request: language={language} (id={language_id}), stdin={repr(stdin)}')

        response = requests.post(url, json=payload, timeout=60)
        print(f'Judge0 response status: {response.status_code}')

        if response.status_code != 201 and response.status_code != 200:
            return {
                'error': f'Judge0 API error: {response.status_code}',
                'stdout': '',
                'stderr': response.text,
                'compile_output': '',
                'time': '',
                'memory': '',
                'exit_code': response.status_code,
                'status': 'Error',
            }

        result = response.json()
        print(f'Judge0 result status: {result.get("status", {}).get("description")}')

        stdout = result.get('stdout') or ''
        stderr = result.get('stderr') or ''
        compile_output = result.get('compile_output') or ''
        status_info = result.get('status') or {}
        status_id = status_info.get('id')
        status_desc = status_info.get('description', 'Unknown')

        return {
            'stdout': stdout,
            'stderr': stderr,
            'compile_output': compile_output,
            'time': result.get('time', ''),
            'memory': result.get('memory', ''),
            'exit_code': result.get('exit_code', ''),
            'status_id': status_id,
            'status': status_desc,
            'error': None if status_id == 3 else status_desc,
        }

    except requests.exceptions.Timeout:
        return {'error': 'Code execution timeout', 'stdout': '', 'stderr': '', 'compile_output': ''}
    except requests.exceptions.ConnectionError:
        return {
            'error': 'Cannot connect to Judge0. Make sure Docker is running (docker compose up in judge0-v1.13.1).',
            'stdout': '',
            'stderr': '',
            'compile_output': '',
        }
    except requests.exceptions.RequestException as e:
        return {'error': f'Network error: {str(e)}', 'stdout': '', 'stderr': '', 'compile_output': ''}
    except Exception as e:
        return {'error': f'Execution error: {str(e)}', 'stdout': '', 'stderr': '', 'compile_output': ''}

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('problems_list'))
    
    next_page = request.args.get('next')
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        
        if not username or not email or not password:
            flash('All fields are required.', 'error')
            return redirect(request.url)
            
        existing_user = User.query.filter((User.username == username) | (User.email == email)).first()
        if existing_user:
            flash('Username or email already exists.', 'error')
            return redirect(request.url)
            
        hashed_pw = generate_password_hash(password)
        new_user = User(username=username, email=email, password_hash=hashed_pw)
        db.session.add(new_user)
        db.session.commit()
        
        flash('Registration successful! Please log in.', 'success')
        if next_page:
            return redirect(url_for('login', next=next_page))
        return redirect(url_for('login'))
        
    return render_template('register.html', next_page=next_page)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('problems_list'))
        
    next_page = request.args.get('next')
        
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            if next_page:
                return redirect(next_page)
            return redirect(url_for('problems_list'))
        else:
            flash('Invalid email or password.', 'error')
            
    return render_template('login.html', next_page=next_page)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
def home():
    return render_template('landing.html')

@app.route('/problems')
def problems_list():
    data = load_problems_dataset()
    problems = data.get('problems', [])
    counts = data.get('counts_by_difficulty', {})
    
    problem_statuses = {}
    if current_user.is_authenticated:
        submissions = Submission.query.filter_by(user_id=current_user.id).all()
        for sub in submissions:
            pid = sub.problem_id
            # Priority: passed > partial > failed > In Progress
            current_status = problem_statuses.get(pid, 'failed')
            if sub.status == 'passed' or current_status == 'passed':
                problem_statuses[pid] = 'passed'
            elif sub.status == 'partial' or current_status == 'partial':
                problem_statuses[pid] = 'partial'
            else:
                problem_statuses[pid] = 'failed'
                
        # Fallback to older SolvedProblem if Submission isn't populated
        solved_records = SolvedProblem.query.filter_by(user_id=current_user.id).all()
        for r in solved_records:
            problem_statuses[r.problem_id] = 'passed'
        
    return render_template(
        'dashboard.html',
        problems=problems,
        easy_count=counts.get('Easy', 0),
        medium_count=counts.get('Medium', 0),
        problem_statuses=problem_statuses
    )

@app.route('/problems/next-unsolved')
@login_required
def next_unsolved():
    current_pid = request.args.get('current', type=int)
    data = load_problems_dataset()
    problems = data.get('problems', [])
    if not problems:
        return redirect(url_for('problems_list'))
        
    problem_ids = [p['id'] for p in problems]
    
    # Get solved problems
    solved_pids = set()
    subs = Submission.query.filter_by(user_id=current_user.id, status='passed').all()
    for s in subs:
        solved_pids.add(s.problem_id)
    # Fallback to old SolvedProblem table
    solved_records = SolvedProblem.query.filter_by(user_id=current_user.id).all()
    for r in solved_records:
        solved_pids.add(r.problem_id)
        
    # Find next unsolved
    next_pid = None
    if current_pid:
        try:
            idx = problem_ids.index(current_pid)
            # check remaining
            for pid in problem_ids[idx+1:]:
                if pid not in solved_pids:
                    next_pid = pid
                    break
        except ValueError:
            pass
            
    # If not found after current, wrap around
    if not next_pid:
        for pid in problem_ids:
            if pid not in solved_pids and pid != current_pid:
                next_pid = pid
                break
                
    if next_pid:
        return redirect(url_for('problem', problem_id=next_pid))
    else:
        flash("You've solved all problems!", "info")
        return redirect(url_for('problems_list'))

@app.route('/sandbox')
def sandbox():
    return render_template('sandbox.html')


@app.route('/problem/<int:problem_id>')
def problem(problem_id: int):
    record = get_problems_by_id().get(problem_id)
    if not record:
        abort(404)
    problem_view = dict(record)
    problem_view['description_html'] = format_problem_description(
        record.get('description', '')
    )
    
    user_submissions = []
    if current_user.is_authenticated:
        subs = Submission.query.filter_by(user_id=current_user.id, problem_id=problem_id).order_by(Submission.timestamp.desc()).all()
        for s in subs:
            user_submissions.append({
                'id': s.id,
                'code': s.code,
                'language': s.language,
                'status': s.status,
                'timestamp': s.timestamp.strftime('%b %d, %H:%M')
            })

    return render_template('problem.html', problem=problem_view, user_submissions=user_submissions)

@app.route('/api/problems/<int:problem_id>/submit', methods=['POST'])
def submit_problem(problem_id: int):
    record = get_problems_by_id().get(problem_id)
    if not record:
        return jsonify({'error': 'Problem not found'}), 404

    data = request.get_json(silent=True) or {}
    source_code = (data.get('source_code') or '').strip()
    language = data.get('language', 'python')

    if not source_code:
        return jsonify({'error': 'Please provide source_code'}), 400

    if language not in JUDGE0_LANGUAGE_IDS:
        return jsonify({'error': f'Unsupported language: {language}'}), 400

    test_cases = record.get('test_cases') or []
    if not test_cases:
        return jsonify({'error': 'This problem has no test cases defined yet.'}), 400

    summary = run_test_suite(source_code, language, test_cases)
    configured = summary['total']
    if configured == 0:
        return jsonify({
            'error': 'All test cases are empty placeholders. Add input and expected_output in processed_problems.json.',
            'problem_id': problem_id,
            'results': summary['results'],
        }), 400

    save_submission = data.get('save_submission', True)

    if current_user.is_authenticated and save_submission:
        if summary['all_passed']:
            status_val = 'passed'
        elif summary['passed'] > 0:
            status_val = 'partial'
        else:
            status_val = 'failed'
            
        new_submission = Submission(
            user_id=current_user.id,
            problem_id=problem_id,
            code=source_code,
            language=language,
            status=status_val
        )
        db.session.add(new_submission)
        
        # Keep old table synced for passed tests
        if status_val == 'passed':
            solved = SolvedProblem.query.filter_by(user_id=current_user.id, problem_id=problem_id).first()
            if not solved:
                new_solved = SolvedProblem(user_id=current_user.id, problem_id=problem_id)
                db.session.add(new_solved)
                
        db.session.commit()

    return jsonify({
        'problem_id': problem_id,
        'passed': summary['passed'],
        'total': summary['total'],
        'all_passed': summary['all_passed'],
        'results': summary['results'],
    })


@app.route('/api/problems/<int:problem_id>/coach', methods=['POST'])
def problem_coach(problem_id: int):
    try:
        if groq_client is None:
            return jsonify({'error': 'Groq client not initialized. Please check your GROQ_API_KEY.'}), 500

        record = get_problems_by_id().get(problem_id)
        if not record:
            return jsonify({'error': 'Problem not found'}), 404

        data = request.get_json(silent=True) or {}
        source_code = (data.get('source_code') or '').strip()
        language = data.get('language', 'python')
        failing_tests = data.get('failing_tests') or []
        problem_statement = (data.get('problem_statement') or record.get('description') or '').strip()

        if not source_code:
            return jsonify({'error': 'Please provide source_code'}), 400

        if language not in JUDGE0_LANGUAGE_IDS:
            return jsonify({'error': f'Unsupported language: {language}'}), 400

        user_prompt = f"""Problem title: {record.get('title', 'Unknown')}
Difficulty: {record.get('difficulty', 'Unknown')}

Problem statement:
{problem_statement}

Language: {language}

Candidate code:
{source_code}

Failing / errored test cases from our automated judge:
{format_failing_tests_for_prompt(failing_tests)}

Return JSON only. Use status "needs_hints" with hint1 (Conceptual), hint2 (Structural), hint3 (Solution-revealing)."""

        response = groq_client.chat.completions.create(
            model='llama-3.3-70b-versatile',
            messages=[
                {'role': 'system', 'content': COACH_SYSTEM_PROMPT},
                {'role': 'user', 'content': user_prompt},
            ],
            temperature=0.6,
            max_tokens=1200,
        )

        hints_text = response.choices[0].message.content.strip()
        print(f'AI Coach response: {hints_text[:500]}...')

        try:
            response_data = parse_llm_json_response(hints_text)
        except Exception:
            print('AI Coach JSON parse failed')
            return jsonify({'error': 'Failed to parse AI response. Please try again.'}), 500

        if response_data.get('status') == 'correct':
            return jsonify({
                'status': 'correct',
                'message': response_data.get('message', 'Your approach looks solid!'),
            })

        for key in ('hint1', 'hint2', 'hint3'):
            if key not in response_data or not str(response_data.get(key, '')).strip():
                return jsonify({'error': 'Failed to parse AI response. Please try again.'}), 500

        return jsonify({
            'status': 'needs_hints',
            'hint1': response_data['hint1'],
            'hint2': response_data['hint2'],
            'hint3': response_data['hint3'],
            'levels': {
                'hint1': 'Conceptual',
                'hint2': 'Structural',
                'hint3': 'Solution-revealing',
            },
        })

    except Exception as e:
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500


@app.route('/get-hints', methods=['POST'])
def get_hints():
    try:
        print(f"get_hints called, groq_client is None: {groq_client is None}")
        if groq_client is None:
            error_msg = 'Groq client not initialized. Please check your API key.'
            print(f"Returning error: {error_msg}")
            return jsonify({
                'error': error_msg,
                'hint1': 'Start by understanding the problem requirements and breaking it down into smaller steps.',
                'hint2': 'Consider the appropriate data structures and algorithms for this type of problem.',
                'hint3': 'Think about edge cases and how to optimize your solution for efficiency.'
            }), 500
            
        data = request.get_json()
        problem_statement = data.get('problemStatement', '')
        user_code = data.get('userCode', '')
        language = data.get('language', 'python')
        
        if not problem_statement and not user_code:
            return jsonify({'error': 'Please provide either a problem statement or user code'}), 400
        
        # Execute code first using Judge0 (without stdin for hints)
        execution_result = execute_code(user_code, language, stdin='')

        if execution_result.get('error') and not execution_result.get('stdout'):
            exec_context = (
                f"Execution failed: {execution_result.get('error')}. "
                f"stderr: {execution_result.get('stderr', '')}. "
                f"compile_output: {execution_result.get('compile_output', '')}"
            )
        else:
            parts = []
            if execution_result.get('stdout'):
                parts.append(f"stdout: {execution_result['stdout']}")
            if execution_result.get('stderr'):
                parts.append(f"stderr: {execution_result['stderr']}")
            if execution_result.get('compile_output'):
                parts.append(f"compile_output: {execution_result['compile_output']}")
            parts.append(f"status: {execution_result.get('status', 'unknown')}")
            exec_context = ' | '.join(parts) if parts else 'No output produced.'
        
        # System prompt for DSA Coach (Socratic method)
        system_prompt = """You are a Socratic DSA Coach. Analyze the given problem statement and user code.

        CRITICAL: You must respond ONLY with a valid JSON object. No other text, no explanations, no markdown formatting.

        IMPORTANT: First determine if the code is already correct by checking:
        1. Does the code execute without errors?
        2. Does the code produce the expected output for the given problem?
        3. Is the code well-structured and follows best practices?

        If the code is already correct and produces the expected output, respond with:
        {"status": "correct", "message": "Your code is already correct! No hints needed.", "hint1": "", "hint2": "", "hint3": ""}

        Otherwise, identify the ROOT issue using this priority order:
        1. CONCEPT: Does the student fundamentally misunderstand the problem or required algorithm?
        2. SYNTAX/STRUCTURE: Are there language errors, wrong constructs, or logical structure problems?
        3. EDGE CASES: Are there boundary conditions or special inputs not handled?
        4. COMPLEXITY: Is the solution correct but inefficient?

        Address the HIGHEST priority issue in all three hints. Respond in this format:
        {"status": "needs_hints", "hint1": "question?", "hint2": "question?", "hint3": "question?"}

        The Socratic method rules — ALL hints MUST be phrased as QUESTIONS:
        - hint1: Broad conceptual question — make them think about the problem approach
        - hint2: More directed question about their algorithm or structure
        - hint3: Specific question pointing at the exact flaw without revealing the fix
        - EVERY hint must end with a question mark (?)
        - NEVER state what is wrong — ALWAYS ask a guiding question
        - NEVER include code snippets, pseudo-code, or the direct solution in any hint
        - NEVER include a solution field
        - DO NOT include any text outside the JSON object
        - DO NOT use markdown formatting"""
        
        user_prompt = f"""Problem Statement: {problem_statement}
        
        User Code ({language}):
        {user_code}
        
        Execution Context: {exec_context}
        
        Please analyze this {language} code and provide feedback based on the language-specific syntax, conventions, and best practices.
        
        Based on this and the code provided, give the 3 leveled hints.
        
        If the code is correct, respond ONLY with:
        {{"status": "correct", "message": "Your code is correct! Well done.", "hint1": "", "hint2": "", "hint3": ""}}
        
        If the code needs improvement, respond ONLY with:
        {{"status": "needs_hints", "hint1": "conceptual question?", "hint2": "structural question?", "hint3": "targeted question?"}}
        
        No other text, no explanations, just the JSON."""
        
        # Call Groq API
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=1000
        )
        
        hints_text = response.choices[0].message.content.strip()
        print(f"AI Response: {hints_text}")

        try:
            response_data = parse_llm_json_response(hints_text)
        except Exception:
            print('Both JSON parsing methods failed')
            return jsonify({'error': 'Failed to parse AI response. Please try again.'}), 500

        if response_data.get('status') == 'correct':
            return jsonify({
                'status': 'correct',
                'message': response_data.get('message', 'Your code is correct! Well done.'),
            })

        if 'hint1' not in response_data or 'hint2' not in response_data or 'hint3' not in response_data:
            print('Invalid hints structure')
            return jsonify({'error': 'Failed to parse AI response. Please try again.'}), 500

        if 'solution' not in response_data:
            response_data['solution'] = '# Solution not available'

        response_data['status'] = 'needs_hints'
        return jsonify(response_data)
        
    except Exception as e:
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500

@app.route('/run-code', methods=['POST'])
def run_code():
    try:
        data = request.get_json()
        source_code = data.get('source_code', '')
        language = data.get('language', 'python')
        stdin = data.get('stdin', '')
        
        if not source_code.strip():
            return jsonify({'error': 'Please provide some code to execute'}), 400
        
        execution_result = execute_code(source_code, language, stdin)

        if execution_result.get('error') and execution_result.get('status_id') is None:
            return jsonify({
                'error': execution_result['error'],
                'stdout': '',
                'stderr': execution_result.get('stderr', ''),
                'compile_output': execution_result.get('compile_output', ''),
                'time': '',
                'memory': '',
                'exit_code': '',
                'status': 'Error',
            }), 500

        return jsonify({
            'stdout': execution_result.get('stdout', ''),
            'stderr': execution_result.get('stderr', ''),
            'compile_output': execution_result.get('compile_output', ''),
            'time': execution_result.get('time', ''),
            'memory': execution_result.get('memory', ''),
            'exit_code': execution_result.get('exit_code', ''),
            'status': execution_result.get('status', 'Success'),
        })
        
    except Exception as e:
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(debug=True)

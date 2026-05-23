from flask import Flask, render_template, request, jsonify
from groq import Groq
import os
import requests
import json
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

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

@app.route('/')
def index():
    return render_template('index.html')

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
        
        # System prompt for DSA Coach
        system_prompt = """You are a DSA Coach. Analyze the given problem statement and user code for logical errors or efficiency issues. 

        CRITICAL: You must respond ONLY with a valid JSON object. No other text, no explanations, no markdown formatting.
        
        IMPORTANT: First determine if the code is already correct by checking:
        1. Does the code execute without errors?
        2. Does the code produce the expected output for the given problem?
        3. Is the code well-structured and follows best practices?
        
        If the code is already correct and produces the expected output, respond with:
        {"status": "correct", "message": "Your code is already correct! No hints needed.", "hint1": "", "hint2": "", "hint3": "", "solution": ""}
        
        Otherwise, respond with hints in this format:
        {"status": "needs_hints", "hint1": "text", "hint2": "text", "hint3": "text", "solution": "code"}
        
        Constraints:
        - ALWAYS check if code is correct first before providing hints
        - If code executes successfully and produces reasonable output, consider it correct
        - If code is correct, set status to "correct" and provide positive feedback
        - Only provide hints if code has errors, inefficiencies, or can be improved
        - The hints must be progressive (vague to specific)
        - Hints MUST NOT contain any code snippets or the direct solution
        - Hint 1 should be very general and conceptual
        - Hint 2 should provide some guidance on approach
        - Hint 3 should give more specific direction but still no code
        - The solution should contain the complete, correct code implementation
        - Focus on algorithmic thinking, data structures, and problem-solving strategies
        - DO NOT include any text outside the JSON object
        - DO NOT use markdown formatting"""
        
        user_prompt = f"""Problem Statement: {problem_statement}
        
        User Code ({language}):
        {user_code}
        
        Execution Context: {exec_context}
        
        Please analyze this {language} code and provide feedback based on the language-specific syntax, conventions, and best practices.
        
        Based on this and the code provided, give the 3 leveled hints.
        
        If the code is correct, respond ONLY with:
        {{"status": "correct", "message": "Your code is correct! Well done."}}
        
        If the code needs improvement, respond ONLY with:
        {{"status": "needs_hints", "hint1": "general hint", "hint2": "approach hint", "hint3": "specific hint", "solution": "complete code"}}
        
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
        
        # Extract and parse the response
        hints_text = response.choices[0].message.content.strip()
        if '```' in hints_text:
            parts = hints_text.split('```')
            if len(parts) >= 2:
                hints_text = parts[1].strip()
                if hints_text.lower().startswith('json'):
                    hints_text = hints_text[4:].strip()
        print(f"AI Response: {hints_text}")

        try:
            response_data = json.loads(hints_text)
            if not isinstance(response_data, dict):
                raise ValueError('Invalid response format')
        except json.JSONDecodeError:
            try:
                response_data = eval(hints_text)
                if not isinstance(response_data, dict):
                    raise ValueError('Invalid response format')
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

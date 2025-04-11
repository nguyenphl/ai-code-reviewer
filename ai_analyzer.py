import json
import os
import subprocess
from typing import List, Dict, Any
from github_client import create_comment, get_file_content
import google.generativeai as Client
from unidiff import Hunk, PatchedFile

from pr_details import PRDetails

github_token = os.environ.get('GITHUB_TOKEN')

def get_file_contents(owner, repo, path, ref="main"):
    command = "get_file_contents"
    args = ["--owner", owner, "--repo", repo, "--path", path, "--ref", ref]
    return call_mcp_server(command, args)

def get_pull_request(owner, repo, pull_number):
    command = "get_pull_request"
    args = ["--owner", owner, "--repo", repo, "--pullNumber", str(pull_number)]
    return call_mcp_server(command, args)

def call_mcp_server(command, args):
    process = subprocess.run(
        ["docker", "run", "-i", "--rm", "-e", "GITHUB_PERSONAL_ACCESS_TOKEN=" + github_token, "ghcr.io/github/github-mcp-server"] + args,
        input=command,
        text=True,
        capture_output=True
    )
    return json.loads(process.stdout)

def analyze_code(parsed_diff: List[Dict[str, Any]], pr_details: PRDetails) -> List[Dict[str, Any]]:
    """Analyzes the code changes using Gemini and generates review comments."""
    print("Starting analyze_code...")
    print(f"Number of files to analyze: {len(parsed_diff)}")
    comments = []
    #print(f"Initial comments list: {comments}")

    for file_data in parsed_diff:
        file_path = file_data.get('path', '')
        print(f"\nProcessing file: {file_path}")

        if not file_path or file_path == "/dev/null":
            continue

        class FileInfo:
            def __init__(self, path):
                self.path = path

        file_info = FileInfo(file_path)

        hunks = file_data.get('hunks', [])
        print(f"Hunks in file: {len(hunks)}")

        for hunk_data in hunks:
            print(f"\nHunk content: {json.dumps(hunk_data, indent=2)}")
            hunk_lines = hunk_data.get('lines', [])
            print(f"Number of lines in hunk: {len(hunk_lines)}")

            if not hunk_lines:
                continue

            hunk = Hunk()
            hunk.source_start = 1
            hunk.source_length = len(hunk_lines)
            hunk.target_start = 1
            hunk.target_length = len(hunk_lines)
            hunk.content = '\n'.join(hunk_lines)
            full_file_content = get_file_content(pr_details.owner, pr_details.repo, file_info.path, pr_details.pull_number)

            prompt = create_prompt(file_info, hunk, pr_details, full_file_content)
            print("Sending prompt to Gemini...")
            ai_response = get_ai_response(prompt)
            print(f"AI response received: {ai_response}")

            if ai_response:
                new_comments = create_comment(file_info, hunk, ai_response)
                print(f"Comments created from AI response: {new_comments}")
                if new_comments:
                    comments.extend(new_comments)
                    print(f"Updated comments list: {comments}")

    print(f"\nFinal comments list: {comments}")
    return comments


def create_prompt(file: PatchedFile, hunk: Hunk, pr_details: PRDetails, full_file_content: str) -> str:
    """Creates the prompt for the Gemini model."""
    return f"""
    You are a senior C# developer reviewing a pull request for a .NET project targeting .NET 9.0. Your task is to analyze the code changes in the provided diff, considering the full file content and related files for context. Provide actionable, specific feedback focusing on C# best practices, .NET-specific issues, and broader software engineering principles.

    ### Instructions
    - Respond in JSON format: `{{"reviews": [{{"lineNumber": <line_number>, "reviewComment": "<review comment>"}}]}}`
    - Only provide comments if there are issues or improvements needed; otherwise, return an empty `"reviews"` array.
    - Use GitHub Markdown in comments for clarity (e.g., `**bold**`, ```code```).
    - Focus on:
    - **C# Best Practices**:
        - **Async/Await**: Ensure proper use of asynchronous operations, avoid blocking calls like `.Result` or `.Wait()`.
        - **Naming Conventions**: Verify PascalCase for classes/methods, camelCase for local variables/parameters.
        - **Resource Management**: Check for proper use of `using` statements or `IDisposable` to release resources.
        - **Error Handling**: Ensure exceptions are caught and handled appropriately, avoiding sensitive information exposure.
        - **Thread Safety**: Verify safety for concurrent access in multithreaded scenarios.
    - **.NET-Specific Issues**:
        - **Asynchronous APIs**: Prefer async methods (e.g., `HttpClient.GetAsync` over `Get`).
        - **Deadlocks**: Avoid deadlock risks in async code or incorrect `ConfigureAwait(false)` usage.
        - **Compatibility**: Ensure code aligns with .NET 9.0.
        - **Performance**: Identify bottlenecks (e.g., large loops, suboptimal database queries).
    - **Design Patterns**: Suggest appropriate patterns (e.g., Repository, Dependency Injection) if applicable.
    - **Scalability**: Highlight code that may not scale under load (e.g., tight loops, excessive memory usage).
    - **Security**: Check for vulnerabilities (e.g., SQL injection, invalidate input, improper logging of sensitive data).
    - Use the full file content and related files to understand class references, method calls, or dependencies.
    - NEVER suggest adding code comments or documentation unless explicitly related to a bug or security issue.

    Review the following code diff in the file "{file.path}" and take the pull request title and description into account when writing the response.
    ### Pull Request Details
    Pull request title: {pr_details.title}
    Pull request description: 

    ---
    {pr_details.description or 'No description provided'}
    ---

    Git diff to review:

    ```diff
    {hunk.content}
    ```
    ### File Context
    - **File Path**: {file.path}
    - **Full File Content**:
    ```csharp
    {full_file_content[:5000]}  # Truncated for brevity
    """

def get_ai_response(prompt: str) -> List[Dict[str, str]]:
    """Sends the prompt to Gemini API and retrieves the response."""
    # Use 'gemini-2.0-flash-001' as a fallback default value if the environment variable isn't set
    gemini_model = Client.GenerativeModel(os.environ.get('GEMINI_MODEL', 'gemini-2.0-flash-001'))

    generation_config = {
        "max_output_tokens": 8192,
        "temperature": 0.8,
        "top_p": 0.95,
    }

    print("===== The promt sent to Gemini is: =====")
    print(prompt)
    try:
        response = gemini_model.generate_content(prompt, generation_config=generation_config)

        response_text = response.text.strip()
        if response_text.startswith('```json'):
            response_text = response_text[7:]  # Remove ```json
        if response_text.endswith('```'):
            response_text = response_text[:-3]  # Remove ```
        response_text = response_text.strip()

        print(f"Cleaned response text: {response_text}")

        try:
            data = json.loads(response_text)
            print(f"Parsed JSON data: {data}")

            if "reviews" in data and isinstance(data["reviews"], list):
                reviews = data["reviews"]
                valid_reviews = []
                for review in reviews:
                    if "lineNumber" in review and "reviewComment" in review:
                        valid_reviews.append(review)
                    else:
                        print(f"Invalid review format: {review}")
                return valid_reviews
            else:
                print("Error: Response doesn't contain valid 'reviews' array")
                print(f"Response content: {data}")
                return []
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON response: {e}")
            print(f"Raw response: {response_text}")
            return []
    except Exception as e:
        print(f"Error during Gemini API call: {e}")
        return []
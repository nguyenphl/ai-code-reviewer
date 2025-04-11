import json
import os
from typing import List, Dict, Any
from github import Github
import requests
from unidiff import Hunk
from type import FileInfo

GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
gh = Github(GITHUB_TOKEN)

def get_diff(owner: str, repo: str, pull_number: int) -> str:
    """Fetches the diff of the pull request from GitHub API."""
    # Use the correct repository name format
    repo_name = f"{owner}/{repo}"
    print(f"Attempting to get diff for: {repo_name} PR#{pull_number}")

    repo = gh.get_repo(repo_name)
    pr = repo.get_pull(pull_number)

    # Use the GitHub API URL directly
    api_url = f"https://api.github.com/repos/{repo_name}/pulls/{pull_number}"

    headers = {
        'Authorization': f'Bearer {GITHUB_TOKEN}',  # Changed to Bearer format
        'Accept': 'application/vnd.github.v3.diff'
    }

    response = requests.get(f"{api_url}.diff", headers=headers)

    if response.status_code == 200:
        diff = response.text
        print(f"Retrieved diff length: {len(diff) if diff else 0}")
        return diff
    else:
        print(f"Failed to get diff. Status code: {response.status_code}")
        print(f"Response content: {response.text}")
        print(f"URL attempted: {api_url}.diff")
        return ""
    

def create_comment(file: FileInfo, hunk: Hunk, ai_responses: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """Creates comment objects from AI responses."""
    print("AI responses in create_comment:", ai_responses)
    print(f"Hunk details - start: {hunk.source_start}, length: {hunk.source_length}")
    print(f"Hunk content:\n{hunk.content}")

    comments = []
    for ai_response in ai_responses:
        try:
            line_number = int(ai_response["lineNumber"])
            print(f"Original AI suggested line: {line_number}")

            # Ensure the line number is within the hunk's range
            if line_number < 1 or line_number > hunk.source_length:
                print(f"Warning: Line number {line_number} is outside hunk range")
                continue

            comment = {
                "body": ai_response["reviewComment"],
                "path": file.path,
                "position": line_number
            }
            print(f"Created comment: {json.dumps(comment, indent=2)}")
            comments.append(comment)

        except (KeyError, TypeError, ValueError) as e:
            print(f"Error creating comment from AI response: {e}, Response: {ai_response}")
    return comments

def get_file_content(owner: str, repo: str, file_path: str, pull_number: int) -> str:
    """
    Fetches the content of a specific file from the PR's head commit.
    Returns empty string if file not found or error occurs.
    """
    try:
        gh = Github(os.environ["GITHUB_TOKEN"])
        repo_name = f"{owner}/{repo}"
        repo = gh.get_repo(repo_name)
        pr = repo.get_pull(pull_number)
        
        # Get the head commit of the PR
        head_sha = pr.head.sha
        
        # Fetch file content from the head commit
        try:
            file_content = repo.get_contents(file_path, ref=head_sha)
            return file_content.decoded_content.decode('utf-8')
        except Exception as e:
            print(f"Could not fetch file {file_path}: {e}")
            return ""
    except Exception as e:
        print(f"Error fetching file content for {file_path}: {e}")
        return ""
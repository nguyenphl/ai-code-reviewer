from typing import List, Dict, Any
from github import Github
import json
import os

def create_review_comment(
    owner: str,
    repo: str,
    pull_number: int,
    comments: List[Dict[str, Any]],
):
    """Submits the review comments to the GitHub API."""
    print(f"Attempting to create {len(comments)} review comments")
    print(f"Comments content: {json.dumps(comments, indent=2)}")

    gh = Github(os.environ["GITHUB_TOKEN"])
    repo = gh.get_repo(f"{owner}/{repo}")
    pr = repo.get_pull(pull_number)
    try:
        review = pr.create_review(
            body="Gemini AI Code Reviewer Comments",
            comments=comments,
            event="COMMENT"
        )
        print(f"Review created successfully with ID: {review.id}")
    except Exception as e:
        print(f"Error creating review: {str(e)}")
        print(f"Error type: {type(e)}")
        print(f"Review payload: {comments}")
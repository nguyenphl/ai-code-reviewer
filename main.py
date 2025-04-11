import json
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fnmatch
from pr_details import get_pr_details, PRDetails
from github_client import get_diff
from diff_parser import parse_diff
from ai_analyzer import analyze_code
from review_commenter import create_review_comment

def main():
    """Main function to execute the code review process."""
    pr_details = get_pr_details()
    event_data = json.load(open(os.environ["GITHUB_EVENT_PATH"], "r"))

    event_name = os.environ.get("GITHUB_EVENT_NAME")
    if event_name == "issue_comment":
        # Process comment trigger
        if not event_data.get("issue", {}).get("pull_request"):
            print("Comment was not on a pull request")
            return

        diff = get_diff(pr_details.owner, pr_details.repo, pr_details.pull_number)
        if not diff:
            print("There is no diff found")
            return

        parsed_diff = parse_diff(diff)

        # Get and clean exclude patterns, handle empty input
        exclude_patterns_raw = os.environ.get("INPUT_EXCLUDE", "")
        print(f"Raw exclude patterns: {exclude_patterns_raw}")  # Debug log
        
        # Only split if we have a non-empty string
        exclude_patterns = []
        if exclude_patterns_raw and exclude_patterns_raw.strip():
            exclude_patterns = [p.strip() for p in exclude_patterns_raw.split(",") if p.strip()]
        print(f"Exclude patterns: {exclude_patterns}")  # Debug log

        # Filter files before analysis
        filtered_diff = []
        for file in parsed_diff:
            file_path = file.get('path', '')
            should_exclude = any(fnmatch.fnmatch(file_path, pattern) for pattern in exclude_patterns)
            if should_exclude:
                print(f"Excluding file: {file_path}")  # Debug log
                continue
            filtered_diff.append(file)

        print(f"Files to analyze after filtering: {[f.get('path', '') for f in filtered_diff]}")  # Debug log
        
        comments = analyze_code(filtered_diff, pr_details)
        if comments:
            try:
                create_review_comment(
                    pr_details.owner, pr_details.repo, pr_details.pull_number, comments
                )
            except Exception as e:
                print("Error in create_review_comment:", e)
    else:
        print("Unsupported event:", os.environ.get("GITHUB_EVENT_NAME"))
        return


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("Error:", error)
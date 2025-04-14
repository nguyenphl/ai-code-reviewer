const { spawn } = require('child_process');
const parseDiff = require('parse-diff');
const fs = require('fs');
const { GoogleGenAI } = require('@google/genai');


const GEMINI_API_KEY = process.env.GEMINI_API_KEY;
const GEMINI_MODEL = process.env.GEMINI_MODEL || 'gemini-2.0-flash-001';

const ai = new GoogleGenAI({apiKey: GEMINI_API_KEY});

// Start the MCP server in stdio mode
const mcpServer = spawn('./github-mcp-server/cmd/github-mcp-server/github-mcp-server', ['stdio'], {
  env: { ...process.env, GITHUB_PERSONAL_ACCESS_TOKEN: process.env.GITHUB_TOKEN }
});

// Function to send JSON-RPC requests to the MCP server
function sendRequest(request) {
  return new Promise((resolve, reject) => {
    mcpServer.stdin.write(JSON.stringify(request) + '\n');
    mcpServer.stdout.once('data', (data) => {
      const response = JSON.parse(data.toString());
      if (response.error) {
        reject(response.error);
      } else {
        resolve(response.result);
      }
    });
  });
}

function readPullRequestDetail() {
    const eventPath = process.env.GITHUB_EVENT_PATH;
    if (!eventPath) {
      throw new Error('GITHUB_EVENT_PATH is not set');
    }
    const eventData = JSON.parse(fs.readFileSync(eventPath, 'utf8'));

    // Extract data
    const repoOwner = eventData.repository.owner.login;
    const repoName = eventData.repository.name;
    const prNumber = eventData.issue.number;
    const prBody = eventData.issue.body;

    return { repoOwner, repoName, prNumber, prBody };
}

// System prompt for Gemini
const systemPrompt = `
You are an expert code reviewer. Review the provided pull request diff and the full content of the changed files. Provide a structured response with the following sections:
- **Summary**: A brief overview of the changes.
- **Strengths**: Positive aspects of the code changes.
- **Issues**: Potential problems or bugs, with specific line references if applicable.
- **Suggestions**: Recommendations for improvement.
- Use GitHub Markdown in comments for clarity (e.g., **bold**, code).
 - Use the full file content and related files to understand class references, method calls, or dependencies.
Return your response in markdown format, suitable for posting as a GitHub comment.
`;

async function main() {
  try {

    var { repoOwner, repoName, prNumber, prBody } = readPullRequestDetail();
    // Fetch the pull request diff
    const diffRequest = {
      jsonrpc: '2.0',
      method: 'get_pull_request_diff',  // Assumed tool name
      params: {
        owner: repoOwner,
        repo: repoName,
        prNumber: prNumber
      },
      id: 1
    };
    const diff = await sendRequest(diffRequest);

    // Parse the diff to identify changed files
    const files = parseDiff(diff);
    let reviewPrompts = [];

    for (const file of files) {
      if (file.to === '/dev/null') continue;  // Skip deleted files

      // Fetch the full content of the file at the PR head
      const contentUri = `repo://${process.env.GITHUB_REPOSITORY_OWNER}/${process.env.GITHUB_REPOSITORY_NAME}/refs/pull/${process.env.PR_NUMBER}/head/contents/${file.to}`;
      const contentRequest = {
        jsonrpc: '2.0',
        method: 'readResource',
        params: { uri: contentUri },
        id: 2
      };
      const fileContent = await sendRequest(contentRequest);

      // Extract the file's diff
      const fileDiff = file.chunks.map(chunk => chunk.changes.map(change => change.content).join('\n')).join('\n');

      // Build prompt for this file
      const filePrompt = `File: ${file.to}\n\nDiff:\n${fileDiff}\n\nFull Content:\n${fileContent}`;
      reviewPrompts.push(filePrompt);
    }

    // Combine all prompts with the system prompt
    const fullPrompt = `${systemPrompt}\n\n${reviewPrompts.join('\n\n')}`;

    // Send to Gemini for review (replace with actual Gemini API endpoint)
    const response = await ai.models.generateContent({
        model: GEMINI_MODEL,
        contents: fullPrompt,
      });

    const review = response.data.text;

    // Post the review as a comment on the pull request
    const commentRequest = {
      jsonrpc: '2.0',
      method: 'add_issue_comment',
      params: {
        owner: repoOwner,
        repo: repoName,
        issue_number: prNumber,
        body: review
      },
      id: 3
    };
    await sendRequest(commentRequest);

    console.log('Review comment posted successfully.');
  } catch (error) {
    console.error('Error:', error);
  } finally {
    mcpServer.stdin.end();  // Close the MCP server
  }
}

main();
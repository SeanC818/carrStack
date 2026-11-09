---
name: leaving-pr-comments
description: Use whenever leaving comments on Azure DevOps pull requests.
---

# Leaving PR Comments

Azure DevOps does not render GitHub `> [!NOTE]` callouts. Start every
agent-authored comment left on the user's behalf with this single blockquote
line:

```md
> 🤖 **<model> responding on behalf of <user>**

Actual comment starts here.
```

Use the verified public name of the model that wrote the comment, and the
user's display name. If the harness does not expose a model name, use the
harness name. Do not guess.

Keep the attribution inside the quote and the reply outside it. Do not add a
horizontal rule, heading, signature footer, or second attribution.

Apply this to new threads, inline comments, replies to reviewers, and written
reasons before resolving a thread. Do not add it to PR descriptions, commit
messages, or text the user asked to post verbatim.

Write the comment in a direct style:

- Lead with the conclusion.
- Cite the relevant code, behavior, build, or reproduction.
- Keep it concise. Avoid filler, canned thanks, and status narration.
- Distinguish verified facts from judgment.

Before posting, check the entire comment for secrets and private details.

## Posting

Write the JSON body to a temp file. `ORG`, the project, and the repo come from
the checkout's ADO remote (see `babysit-pr`).

New thread (`status` 1 is active). For an inline comment, add
`"threadContext": {"filePath": "/path/file.cs", "rightFileStart": {"line": 10, "offset": 1}, "rightFileEnd": {"line": 10, "offset": 1}}`:

```bash
# body: {"comments":[{"parentCommentId":0,"content":"<markdown>","commentType":1}],"status":1}
az devops invoke --org $ORG --area git --resource pullRequestThreads --http-method POST \
  --route-parameters project=<project> repositoryId=<repo> pullRequestId=<n> \
  --in-file body.json --api-version 7.1
```

Reply in a thread:

```bash
# body: {"content":"<markdown>","parentCommentId":1,"commentType":1}
az devops invoke --org $ORG --area git --resource pullRequestThreadComments --http-method POST \
  --route-parameters project=<project> repositoryId=<repo> pullRequestId=<n> threadId=<t> \
  --in-file body.json --api-version 7.1
```

Resolve a thread. Use `fixed` after a fix, and `wontFix` or `byDesign` after a
written reason:

```bash
# body: {"status":"fixed"}
az devops invoke --org $ORG --area git --resource pullRequestThreads --http-method PATCH \
  --route-parameters project=<project> repositoryId=<repo> pullRequestId=<n> threadId=<t> \
  --in-file body.json --api-version 7.1
```

After posting, confirm the response contains the new comment `id`. Resolve a
thread only after its reply posted successfully. Link to a thread with
`<pr url>?discussionId=<thread id>`.

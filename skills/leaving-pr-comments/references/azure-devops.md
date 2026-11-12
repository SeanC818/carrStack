# Azure DevOps

Azure DevOps does not render GitHub `> [!NOTE]` callouts. Use this single
blockquote line, with the user's display name:

```md
> 🤖 **<model> responding on behalf of <user>**

Actual comment starts here.
```

## Posting

Write the JSON body to a temp file. `$ORG`, the project, and the repo come
from the checkout's ADO remote, as described in
[babysit-pr's Azure DevOps reference](../../babysit-pr/references/azure-devops.md).

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

After posting, confirm the response contains the new comment `id`. Link to a
thread with `<pr url>?discussionId=<thread id>`.

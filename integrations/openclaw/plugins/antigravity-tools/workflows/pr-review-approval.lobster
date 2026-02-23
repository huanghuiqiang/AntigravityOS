workflow "pr-review-approval" {
  step "prepare" {
    run tool "github_repo_activity" with {
      owner: "${owner}",
      repo: "${repo}",
      hours: 24
    }
  }

  step "approve" {
    approval message "是否将以下评论发布到 PR？"
  }

  step "comment" {
    run tool "github_comment_pr" with {
      owner: "${owner}",
      repo: "${repo}",
      prNumber: ${prNumber},
      body: "${body}",
      dryRun: false
    }
  }
}

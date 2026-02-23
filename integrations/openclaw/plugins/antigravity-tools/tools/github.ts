import { callAntigravityTool, JsonValue } from "./antigravity";
import { PluginApi, ToolResult, ToolContext } from "../index";

export interface GithubListOpenPrsParams {
  owner: string;
  repo: string;
  per_page?: number;
}

export interface GithubCommitStatsParams {
  owner: string;
  repo: string;
  since: string;
  until: string;
}

export interface GithubRepoActivityParams {
  owner: string;
  repo: string;
  hours: number;
}

export interface GithubCommentPrParams {
  owner: string;
  repo: string;
  prNumber: number;
  body: string;
  dryRun?: boolean;
}

function contentFromData(data: { [key: string]: JsonValue } | undefined): ToolResult {
  return {
    content: [{ type: "text", text: JSON.stringify(data ?? {}) }],
  };
}

export function registerGithubTools(api: PluginApi): void {
  api.registerTool<GithubListOpenPrsParams>({
    name: "github_list_open_prs",
    description: "List open pull requests for a repository",
    execute: async (context: ToolContext, params: GithubListOpenPrsParams): Promise<ToolResult> => {
      const result = await callAntigravityTool(
        "github_list_open_prs",
        {
          owner: params.owner,
          repo: params.repo,
          per_page: params.per_page ?? 20,
        },
        context.traceId,
      );
      return contentFromData(result.data);
    },
  });

  api.registerTool<GithubCommitStatsParams>({
    name: "github_commit_stats",
    description: "Get commit stats in a time window",
    execute: async (context: ToolContext, params: GithubCommitStatsParams): Promise<ToolResult> => {
      const result = await callAntigravityTool(
        "github_commit_stats",
        {
          owner: params.owner,
          repo: params.repo,
          since: params.since,
          until: params.until,
        },
        context.traceId,
      );
      return contentFromData(result.data);
    },
  });

  api.registerTool<GithubRepoActivityParams>({
    name: "github_repo_activity",
    description: "Summarize repository activity in recent hours",
    execute: async (context: ToolContext, params: GithubRepoActivityParams): Promise<ToolResult> => {
      const result = await callAntigravityTool(
        "github_repo_activity",
        {
          owner: params.owner,
          repo: params.repo,
          hours: params.hours,
        },
        context.traceId,
      );
      return contentFromData(result.data);
    },
  });

  api.registerTool<GithubCommentPrParams>({
    name: "github_comment_pr",
    description: "Comment on PR through Antigravity gateway with dryRun support",
    execute: async (context: ToolContext, params: GithubCommentPrParams): Promise<ToolResult> => {
      const result = await callAntigravityTool(
        "github_comment_pr",
        {
          owner: params.owner,
          repo: params.repo,
          prNumber: params.prNumber,
          body: params.body,
          dryRun: params.dryRun ?? true,
        },
        context.traceId,
      );
      return contentFromData(result.data);
    },
  });
}

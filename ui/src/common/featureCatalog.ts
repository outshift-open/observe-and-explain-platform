/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

export const featureCatalog: Record<string, string> = {
  n_tools: 'Total number of tool calls made in the session',
  n_unique_tools: 'Number of distinct tools invoked',
  tool_diversity_ratio:
    'Ratio of unique tools to total tool calls (higher = more varied tool usage)',
  loop_ratio:
    'Fraction of tool calls that are repeated consecutively (indicator of looping/stuck behaviour)',
  mean_result_len:
    'Average character length of tool call results (proxy for data volume returned)',
  context_growth_rate:
    'Rate at which LLM context window grows across calls in the session',
  peak_context_len:
    'Maximum context window length reached during the session',
  n_retries: 'Number of tool call retries (indicator of failures/errors)',
  cost: 'Estimated monetary cost of all LLM calls in the session (USD)',
  llm_calls_via_edges:
    'Number of LLM calls detected via graph relationships',
  llm_calls_via_session_property:
    'Number of LLM calls detected via session property',
  llm_call_source_disagreement:
    'Boolean: LLM call counts differ between edge and property sources (data quality flag)',
  n_agentcalls: 'Total number of agent invocations in the session',
  n_unique_agents_called: 'Number of distinct agents called',
  agent_reuse_ratio:
    'Proportion of agent calls that reuse already-seen agents (higher = less delegation breadth)',
  repeated_agentcall_ratio_anywhere:
    'Fraction of agent calls that are repeat invocations of the same agent',
  agent_loop_count_anywhere:
    'Count of agent re-invocations after first appearance (loop indicator)',
  max_same_agent_streak:
    'Longest consecutive sequence of calls to the same agent',
  mean_agent_toolset_size_in_session:
    'Average number of distinct tools used per agent across the session',
  n_calls_from_zero_tool_agents:
    'Count of agent calls from agents that have no tools assigned in the baseline',
  ratio_calls_from_zero_tool_agents:
    'Fraction of agent calls from tool-less agents',
  n_calls_tool_access_mismatch:
    "Count of agent calls where tools used were not in the agent's baseline toolset",
  ratio_calls_tool_access_mismatch:
    'Fraction of agent calls with tool access mismatches',
  n_calls_expected_tools_but_none:
    'Count of calls from agents expected to use tools (per baseline) but used none',
  ratio_calls_expected_tools_but_none:
    'Fraction of such calls out of total agent calls',
  n_calls_zero_tool_agent_used_tools:
    'Count of calls from tool-less agents that unexpectedly used tools',
  mean_tool_count_per_nonzero_tool_agent_call:
    'Average number of tools used per call by agents that have tools'
};

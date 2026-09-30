/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { useQuery } from '@tanstack/react-query';

// const KG_API_BASE_URL = 'http://localhost:8000/api/v1';
const KG_API_BASE_URL = 'http://localhost:10000';
const OCE_API_BASE_URL = window.restApiUrl ?? import.meta.env.VITE_REST_API_URL;
// const OCE_API_BASE_URL = 'http://localhost:8000/api/v1';

const fetchSessions = async (): Promise<string[]> => {
  const response = await fetch(`${KG_API_BASE_URL}/sessions`);

  if (!response.ok) {
    throw new Error(`Failed to fetch sessions: ${response.statusText}`);
  }

  return response.json();
};

export const useSessions = () => {
  return useQuery({
    queryKey: ['sessions'],
    queryFn: () => fetchSessions()
  });
};

export interface StateMachineResponse {
  [key: string]: unknown;
}

const fetchStateMachine = async (sessionId: string, levels: string[]): Promise<StateMachineResponse> => {
  const levelParam = levels.join(',');
  const response = await fetch(`${OCE_API_BASE_URL}/sessions/${sessionId}/timeline?level=${levelParam}`);

  if (!response.ok) {
    throw new Error(`Failed to fetch state machine: ${response.statusText}`);
  }

  return response.json();
};

export const useStateMachine = (sessionId: string, levels: string[]) => {
  return useQuery({
    queryKey: ['stateMachine', sessionId, levels],
    queryFn: () => fetchStateMachine(sessionId, levels),
    enabled: !!sessionId && levels.length > 0
  });
};

export interface AgentNodeData {
  agent_name: string;
  operation_count: number;
  total_duration: number;
  avg_duration: number;
  tool_call_count: number;
  tools_used: string[];
  llm_call_count: number;
  total_tokens: number;
  prompt_tokens: number;
  completion_tokens: number;
  active: boolean;
}

export interface AgentNode {
  id: string;
  label: string;
  type: string;
  data: AgentNodeData;
  metadata: {
    color: string;
    shape: string;
    size: number;
    opacity?: number;
  };
}

export interface AgentEdgeData {
  handoff_count: number;
  from_agent: string;
  to_agent: string;
  total_duration: number;
  avg_duration: number;
  tool_call_count: number;
  tools_used: string[];
  first_handoff: number;
  last_handoff: number;
}

export interface AgentEdge {
  id: string;
  source: string;
  target: string;
  label: string;
  type: string;
  data: AgentEdgeData;
  metadata: {
    color: string;
  };
}

export interface AgentNetworkMetadata {
  graph_type: string;
  node_count: number;
  edge_count: number;
  agent_count: number;
  active_agent_count: number;
  inactive_agent_count: number;
  include_inactive: boolean;
  expected_agents: string[];
  excluded_agents: string[];
  source: string;
}

export interface AgentNetworkResponse {
  nodes: AgentNode[];
  edges: AgentEdge[];
  session_id: string;
  hierarchy_level: string | null;
  metadata: AgentNetworkMetadata;
}

export interface AgentNetworkParams {
  expectedAgents?: string[];
  includeInactive?: boolean;
}

const fetchAgentNetwork = async (sessionId: string, params?: AgentNetworkParams): Promise<AgentNetworkResponse> => {
  const searchParams = new URLSearchParams();

  if (params?.expectedAgents && params.expectedAgents.length > 0) {
    searchParams.set('expected_agents', params.expectedAgents.join(','));
  }

  if (params?.includeInactive !== undefined) {
    searchParams.set('include_inactive', String(params.includeInactive));
  }

  const queryString = searchParams.toString();
  const url = `${KG_API_BASE_URL}/graph/agents/${sessionId}${queryString ? `?${queryString}` : ''}`;

  const response = await fetch(url);

  if (!response.ok) {
    throw new Error(`Failed to fetch agent network: ${response.statusText}`);
  }

  return response.json();
};

export const useAgentNetwork = (sessionId: string, params?: AgentNetworkParams) => {
  return useQuery({
    queryKey: ['agentNetwork', sessionId, params],
    queryFn: () => fetchAgentNetwork(sessionId, params),
    enabled: !!sessionId
  });
};

export interface TaskGraphResponse {
  [key: string]: unknown;
}

const fetchTaskGraph = async (sessionId: string): Promise<TaskGraphResponse> => {
  const response = await fetch(`${KG_API_BASE_URL}/graph/tasks/${sessionId}`);

  if (!response.ok) {
    throw new Error(`Failed to fetch task graph: ${response.statusText}`);
  }

  return response.json();
};

export const useTaskGraph = (sessionId: string) => {
  return useQuery({
    queryKey: ['taskGraph', sessionId],
    queryFn: () => fetchTaskGraph(sessionId),
    enabled: !!sessionId
  });
};

export interface OntologySchemaResponse {
  [key: string]: unknown;
}

const fetchOntologySchema = async (): Promise<OntologySchemaResponse> => {
  const response = await fetch(`${KG_API_BASE_URL}/schema`);

  if (!response.ok) {
    throw new Error(`Failed to fetch ontology schema: ${response.statusText}`);
  }

  return response.json();
};

export const useOntologySchema = () => {
  return useQuery({
    queryKey: ['ontologySchema'],
    queryFn: () => fetchOntologySchema()
  });
};

// MAS Execution Hierarchy types
export interface HierarchyNodeData {
  session_id?: string;
  transition_id?: string;
  level: string;
  call_type?: string;
  tool_name?: string;
  agent_name?: string;
  duration?: number;
  edge_type?: string;
  timestamp?: number;
  execution_id?: string;
  input_params?: Record<string, unknown>;
  is_hitl?: boolean;
  input?: string;
  output?: string;
  parent_agent_exec_id?: string;
  model_name?: string;
  provider?: string | null;
  prompt_tokens?: number;
  completion_tokens?: number;
  total_tokens?: number;
  cache_read_tokens?: number;
  temperature?: number;
  finish_reason?: string | null;
  total_duration?: number;
  avg_duration?: number;
  tool_call_count?: number;
  tools_used?: string[];
  first_handoff?: number;
  last_handoff?: number;
}

export interface HierarchyNode {
  id: string;
  label: string;
  type: 'session' | 'mas' | 'agent' | 'call';
  data: HierarchyNodeData;
  metadata: Record<string, unknown>;
}

export interface HierarchyEdgeData {
  relationship: 'contains' | 'followed_by';
  sequence_number?: number;
  sequence?: number;
}

export interface HierarchyEdge {
  id: string;
  source: string;
  target: string;
  label: string;
  type: 'hierarchy' | 'sequence';
  data: HierarchyEdgeData;
  metadata: Record<string, unknown>;
}

export interface HierarchyMetadata {
  graph_type: string;
  node_count: number;
  edge_count: number;
  levels: {
    session?: number;
    mas?: number;
    agent?: number;
    call?: number;
  };
  source: string;
}

export interface HierarchyResponse {
  nodes: HierarchyNode[];
  edges: HierarchyEdge[];
  session_id: string;
  hierarchy_level: string | null;
  metadata: HierarchyMetadata;
}

const fetchHierarchy = async (sessionId: string): Promise<HierarchyResponse> => {
  const response = await fetch(`${OCE_API_BASE_URL}/sessions/${sessionId}/execution-graph`);
  //const response = await fetch(`${KG_API_BASE_URL}/graph/hierarchy/${sessionId}`);

  if (!response.ok) {
    throw new Error(`Failed to fetch hierarchy: ${response.statusText}`);
  }

  return response.json();
};

export const useHierarchy = (sessionId: string) => {
  return useQuery({
    queryKey: ['hierarchy', sessionId],
    queryFn: () => fetchHierarchy(sessionId),
    enabled: !!sessionId
  });
};

// Agent conversation types
export interface AgentConversationMessage {
  transition_id: string;
  agent_name: string | null;
  execution_id: string | null;
  timestamp: number;
  duration: number;
  edge_type: string;
  input: string | null;
  output: string | null;
}

export interface AgentConversationMetadata {
  graph_type: string;
  message_count: number;
  source: string;
}

export interface AgentConversationResponse {
  session_id: string;
  messages: AgentConversationMessage[];
  metadata: AgentConversationMetadata;
}

const fetchAgentConversation = async (
  sessionId: string
): Promise<AgentConversationResponse> => {
  const response = await fetch(`${OCE_API_BASE_URL}/sessions/${sessionId}/conversation`);

  if (!response.ok) {
    throw new Error(`Failed to fetch conversation: ${response.statusText}`);
  }

  return response.json();
};

export const useAgentConversation = (sessionId: string) => {
  return useQuery({
    queryKey: ['agent-conversation', sessionId],
    queryFn: () => fetchAgentConversation(sessionId),
    enabled: !!sessionId
  });
};

/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { Application } from './oxp.type';

export interface ApplicationsResponse {
  applications: Application[];
}

export interface LiveSession {
  session_id: string;
  start_time: string;
  end_time: string;
  status: string;
}

export interface LiveSessionsResponse {
  sessions: LiveSession[];
}

export interface LiveTopologyNode {
  id: string;
  name: string;
  type: string;
  status: string;
  start_time: string | null;
  end_time: string | null;
  description: string | null;
  data: {
    input?: Record<string, unknown>;
    tools?: unknown[];
  };
}

export interface LiveTopologyEdge {
  source: string;
  target: string;
  label: string;
}

export interface SessionsCountResponse {
  count: number;
}

export interface ApplicationStatefulEvalTotals {
  applicationName: string;
  totalFatal: number;
  totalMinor: number;
}

export interface LiveTopologySessionResponse {
  session_id: string;
  session_status: string;
  nodes: LiveTopologyNode[];
  edges: LiveTopologyEdge[];
  last_updated: string;
}

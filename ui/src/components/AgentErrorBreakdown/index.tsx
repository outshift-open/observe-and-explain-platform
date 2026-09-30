/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { AgentErrorBreakdownTable } from './AgentErrorBreakdownTable';
import type { ErrorItem } from '@/types/oxp.type';

interface AgentErrorBreakdownProps {
  data: ErrorItem[];
}

const AgentErrorBreakdown = ({ data }: AgentErrorBreakdownProps) => {
  return <AgentErrorBreakdownTable data={data} isLoading={false} isError={false} onReload={() => {}} />;
};

export default AgentErrorBreakdown;

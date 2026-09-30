/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import React from 'react';
import { PATHS } from '@/routes/routes.tsx';
import { useNavigate } from 'react-router-dom';

interface ClickableDotProps {
  agentId: string;
  cx?: number;
  cy?: number;
  payload?: any;
  onClick?: (payload: any) => void;
  fill?: string;
  r?: number;
}

export const ClickableDot: React.FC<ClickableDotProps> = ({ cx, cy, payload, fill = 'red', r = 5, agentId }) => {
  const navigate = useNavigate();

  if (cx === undefined || cy === undefined) return null;

  return (
    <circle
      cx={cx}
      cy={cy}
      r={r}
      fill={fill}
      style={{ cursor: 'pointer' }}
      // onClick={() => navigate(`${PATHS.monitoring}/${PATHS.applications}/noa${PATHS.sessions}/${payload.id}${PATHS.agents}/${agentId}`)}
    />
  );
};

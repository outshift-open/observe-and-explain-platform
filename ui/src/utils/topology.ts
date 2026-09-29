/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { StaticTopologyTool } from '@/types/oxp.type';

export const isToolDataArray = (data: string | StaticTopologyTool[]): data is StaticTopologyTool[] => {
  return Array.isArray(data) && data.length > 0 && typeof data[0] === 'object' && 'isTool' in data[0];
};

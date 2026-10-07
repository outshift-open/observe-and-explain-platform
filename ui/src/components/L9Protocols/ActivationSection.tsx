/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { Stack, Typography } from '@mui/material';
import { L9Protocol } from '@/types/oxp.type';
import {
  MetricRow,
  NotAvailable,
  Reason,
  SubSection,
  YesNoTag
} from './primitives';

// Activation is shown for every protocol, activated or not. `expected` is only
// shown for protocols that track it (absent = not tracked).
export const ActivationSection = ({ protocol }: { protocol: L9Protocol }) => {
  const tracksExpected = protocol.expected !== undefined;

  return (
    <SubSection title="Activation">
      <Stack direction="column" gap="8px">
        <MetricRow label="Activated">
          <YesNoTag value={protocol.activated} />
        </MetricRow>
        <MetricRow label="Activated at">
          {protocol.activated && protocol.activatedAt ? (
            <Typography variant={'body2'}>{protocol.activatedAt}</Typography>
          ) : (
            <NotAvailable />
          )}
        </MetricRow>
        {tracksExpected && (
          <MetricRow
            label="Expected"
            description="Was the protocol actually needed, based on the trace?"
          >
            {!protocol.expected || protocol.expected.expected === null ? (
              <NotAvailable />
            ) : (
              <Stack direction="column" gap="6px" alignItems="flex-start">
                <YesNoTag
                  value={protocol.expected.expected}
                  yesTone="info"
                  noTone="info"
                />
                <Reason text={protocol.expected.reason} />
              </Stack>
            )}
          </MetricRow>
        )}
      </Stack>
    </SubSection>
  );
};

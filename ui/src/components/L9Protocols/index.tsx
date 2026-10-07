/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { useMemo } from 'react';
import { Stack } from '@mui/material';
import { L9Protocol } from '@/types/oxp.type';
import { ProtocolSection } from './ProtocolSection';

// A protocol is listed when it applies to the session. A protocol that was
// expected but is not enabled is listed too, so a missed activation is visible.
const isListed = (protocol: L9Protocol) =>
  protocol.enabled || protocol.expected?.expected === true;

// Renders the protocols provided by the API, in the order they are provided.
export const L9Protocols = ({ protocols }: { protocols: L9Protocol[] }) => {
  const listed = useMemo(() => protocols.filter(isListed), [protocols]);
  const activatedProtocols = useMemo(
    () => new Set(listed.filter((p) => p.activated).map((p) => p.protocol)),
    [listed]
  );

  return (
    <Stack direction="column" gap="16px">
      {listed.map((protocol) => (
        <ProtocolSection
          key={protocol.protocol}
          protocol={protocol}
          activatedProtocols={activatedProtocols}
        />
      ))}
    </Stack>
  );
};

export const hasListedProtocols = (protocols: L9Protocol[]) =>
  protocols.some(isListed);

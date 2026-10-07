/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { ReactNode } from 'react';
import { Stack, Typography } from '@mui/material';
import { Accordion } from '@open-ui-kit/core';
import {
  L9_CONCORD,
  isAccordProtocol,
  isConcordProtocol
} from '@/common/l9Protocols';
import { L9Protocol } from '@/types/oxp.type';
import { ActivationSection } from './ActivationSection';
import { ConcordDetails } from './ConcordDetails';
import { AccordDetails } from './AccordDetails';
import { InfoTooltip, StatusTag } from './primitives';

// What a protocol view can know about the other protocols of the session.
interface L9ViewContext {
  activatedProtocols: Set<string>;
}

type ProtocolView = (
  protocol: L9Protocol,
  context: L9ViewContext
) => ReactNode | null;

const defineView =
  <T extends L9Protocol>(
    matches: (protocol: L9Protocol) => protocol is T,
    render: (protocol: T, context: L9ViewContext) => ReactNode
  ): ProtocolView =>
  (protocol, context) =>
    matches(protocol) ? render(protocol, context) : null;

// Protocols with a dedicated metrics view. A protocol that is not registered
// here is still listed, with its activation only.
const PROTOCOL_VIEWS: ProtocolView[] = [
  defineView(isConcordProtocol, (protocol) => (
    <ConcordDetails protocol={protocol} />
  )),
  defineView(isAccordProtocol, (protocol, context) => (
    <AccordDetails
      protocol={protocol}
      concordActivated={context.activatedProtocols.has(L9_CONCORD)}
    />
  ))
];

export const ProtocolSection = ({
  protocol,
  activatedProtocols
}: {
  protocol: L9Protocol;
  activatedProtocols: Set<string>;
}) => {
  const name = protocol.displayName ?? protocol.protocol;

  const details = protocol.activated
    ? PROTOCOL_VIEWS.map((view) => view(protocol, { activatedProtocols })).find(
        (node) => node !== null
      )
    : null;

  return (
    <Accordion
      contained
      size="large"
      title={name}
      sx={{
        backgroundColor: 'transparent',
        '&:hover:not(.Mui-disabled)': { borderColor: 'transparent' }
      }}
      titleEndIcon={
        protocol.description ? (
          <InfoTooltip description={protocol.description} size={16} />
        ) : undefined
      }
      endSlot={
        <StatusTag
          label={protocol.enabled ? 'Enabled' : 'Disabled'}
          tone={protocol.enabled ? 'positive' : 'neutral'}
        />
      }
    >
      <Stack direction="column" gap="12px">
        <ActivationSection protocol={protocol} />

        {!protocol.activated && (
          <Typography variant={'body2'}>
            {`${name} was not activated in this session.`}
          </Typography>
        )}

        {protocol.activated &&
          (details ?? (
            <Typography variant={'body2'}>
              No detailed metrics view is available for this protocol.
            </Typography>
          ))}
      </Stack>
    </Accordion>
  );
};

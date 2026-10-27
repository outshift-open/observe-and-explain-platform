/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { ReactNode } from 'react';
import { Stack, Typography } from '@mui/material';
import { Accordion } from '@open-ui-kit/core';
import {
  COGNITION_CONCORD,
  isAccordProtocol,
  isConcordProtocol
} from '@/common/cognitionProtocols';
import { CognitionProtocol } from '@/types/oxp.type';
import { ActivationSection } from './ActivationSection';
import { ConcordDetails } from './ConcordDetails';
import { AccordDetails } from './AccordDetails';
import { MetricsView, hasMetrics } from './MetricsView';
import { InfoTooltip, StatusTag } from './primitives';

// What a protocol view can know about the other protocols of the session.
interface CognitionViewContext {
  activatedProtocols: Set<string>;
}

type ProtocolView = (
  protocol: CognitionProtocol,
  context: CognitionViewContext
) => ReactNode | null;

const defineView =
  <T extends CognitionProtocol>(
    matches: (protocol: CognitionProtocol) => protocol is T,
    render: (protocol: T, context: CognitionViewContext) => ReactNode
  ): ProtocolView =>
  (protocol, context) =>
    matches(protocol) ? render(protocol, context) : null;

// Protocols with a dedicated metrics view, used when the API did not return a
// generic `metrics` list. A protocol that is not registered here is still
// listed, with its activation only.
const PROTOCOL_VIEWS: ProtocolView[] = [
  defineView(isConcordProtocol, (protocol) => (
    <ConcordDetails protocol={protocol} />
  )),
  defineView(isAccordProtocol, (protocol, context) => (
    <AccordDetails
      protocol={protocol}
      concordActivated={context.activatedProtocols.has(COGNITION_CONCORD)}
    />
  ))
];

export const ProtocolSection = ({
  protocol,
  activatedProtocols
}: {
  protocol: CognitionProtocol;
  activatedProtocols: Set<string>;
}) => {
  const name = protocol.displayName ?? protocol.protocol;

  // The metrics list returned by the API takes precedence over the dedicated
  // views, which expect structured sections.
  const details = !protocol.activated ? null : hasMetrics(protocol) ? (
    <MetricsView protocol={protocol} />
  ) : (
    PROTOCOL_VIEWS.map((view) => view(protocol, { activatedProtocols })).find(
      (node) => node !== null
    )
  );

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
        <Stack direction="row" gap="8px">
          <StatusTag
            label={protocol.enabled ? 'Enabled' : 'Disabled'}
            tone={protocol.enabled ? 'positive' : 'neutral'}
          />
          <StatusTag
            label={protocol.activated ? 'Activated' : 'Not activated'}
            tone={protocol.activated ? 'positive' : 'negative'}
          />
        </Stack>
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

/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { useState } from 'react';
import { Accordion, Box, Stack, Tab, Tabs } from '@open-ui-kit/core';
import { Divider, Typography, useTheme } from '@mui/material';
import { TabPanel } from '@/components/TabPanel.tsx';
import { Attribute, AttributeType, SpanDetails } from '@/types/oxp.type';
import { format } from 'date-fns';

interface SpanDrawerContentProps {
  span: SpanDetails;
  spanDuration: number;
  startTime: number;
  endTime: number;
}

const inputOutputAttributeKeys = ['.input', '.output', 'gen_ai.prompt', 'gen_ai.completion'];

export const SpanDrawerContent = ({ span, spanDuration = 0, startTime = 0, endTime = 0 }: SpanDrawerContentProps) => {
  const [tab, setTab] = useState(0);

  const theme = useTheme();

  const getAttributes = (attributes: Attribute[]) => {
    return attributes
      .map((attribute: Attribute) => {
        const isJson = attribute.attributeType === AttributeType.Json;

        if (isJson || attribute.value?.length > 25) {
          let displayValue = attribute.value;

          try {
            displayValue = JSON.stringify(JSON.parse(attribute.value), null, 2);
          } catch {
            displayValue = attribute.value;
          }

          return (
            <Accordion contained title={attribute.key} size="medium" sx={{ marginLeft: '-20px', '&.Mui-expanded': { marginLeft: '-20px' } }}>
              <Typography variant={'body2'} component={'pre'} sx={{ fontFamily: 'monospace', marginLeft: '16px' }}>
                {displayValue}
              </Typography>
            </Accordion>
          );
        }

        return (
          <Stack direction={'row'} justifyContent={'space-between'}>
            <Typography variant={'body2'}>{attribute.key}</Typography>
            <Typography variant={'body2'}>{attribute.value}</Typography>
          </Stack>
        );
      })
      .filter((attribute) => attribute !== null);
  };

  const getGeneralAttributes = () => {
    const generalAttributes = span.attributes.filter(
      (attribute) => !inputOutputAttributeKeys.some((inputOutputAttributeKey) => attribute.key.includes(inputOutputAttributeKey))
    );

    return getAttributes(generalAttributes);
  };

  const getInputOutputAttributes = () => {
    const inputOutputAttributes = span.attributes.filter((attribute) =>
      inputOutputAttributeKeys.some((inputOutputAttributeKey) => attribute.key.includes(inputOutputAttributeKey))
    );

    // Group gen_ai.prompt.{i} and gen_ai.completion.{i}
    const promptAttributes = inputOutputAttributes.filter((a) => a.key.startsWith('gen_ai.prompt.'));
    const completionAttributes = inputOutputAttributes.filter((a) => a.key.startsWith('gen_ai.completion.'));
    const otherAttributes = inputOutputAttributes.filter((a) => !a.key.startsWith('gen_ai.prompt.') && !a.key.startsWith('gen_ai.completion.'));

    const extractIndex = (key: string) => {
      const match = key.match(/^gen_ai\.(?:prompt|completion)\.(\d+)/);
      return match ? parseInt(match[1], 10) : Number.MAX_SAFE_INTEGER;
    };

    const sortedPrompts = [...promptAttributes].sort((a, b) => extractIndex(a.key) - extractIndex(b.key));
    const sortedCompletions = [...completionAttributes].sort((a, b) => extractIndex(a.key) - extractIndex(b.key));

    // Ensure for non-gen_ai keys that `.input` entries appear before `.output` entries
    const otherInputs = otherAttributes.filter((a) => a.key.includes('.input'));
    const otherOutputs = otherAttributes.filter((a) => a.key.includes('.output'));

    const orderedAttributes = [...sortedPrompts, ...sortedCompletions, ...otherInputs, ...otherOutputs];

    const keyValueAttributes = getAttributes(orderedAttributes);

    return keyValueAttributes;
  };

  return (
    <Box sx={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <Stack direction={'row'} sx={{ width: '100%' }} alignItems={'flex-end'}>
        <Tabs
          value={tab}
          onChange={(_, val) => {
            setTab(val);
          }}
          slotProps={{ indicator: { sx: { backgroundColor: `${theme.palette.vars.neutralTextDefault} !important` } } }}
          sx={{ width: '100%' }}
        >
          <Tab label={'General'} />
          <Tab label={'Input / Output'} />
        </Tabs>
        <Divider sx={{ borderColor: theme.palette.vars.neutralTextDefault, height: '1px', flex: 1 }} orientation={'horizontal'} />
      </Stack>
      <TabPanel value={tab} index={0} sx={{ width: '100%', padding: '16px 16px 0 16px', flex: 1, minHeight: 0, overflow: 'auto' }}>
        <Stack direction={'column'} gap={'4px'}>
          <Stack direction={'row'} justifyContent={'space-between'}>
            <Typography variant={'body2'}>Start Time</Typography>
            <Typography variant={'body2'}>{format(new Date(startTime), 'MMM d, yyyy HH:mm:ss')}</Typography>
          </Stack>
          <Stack direction={'row'} justifyContent={'space-between'}>
            <Typography variant={'body2'}>End Time</Typography>
            <Typography variant={'body2'}>{format(new Date(endTime), 'MMM d, yyyy HH:mm:ss')}</Typography>
          </Stack>
          <Stack direction={'row'} justifyContent={'space-between'}>
            <Typography variant={'body2'}>Duration</Typography>
            <Typography variant={'body2'}>{spanDuration}ms</Typography>
          </Stack>

          {getGeneralAttributes()}
        </Stack>
      </TabPanel>
      <TabPanel value={tab} index={1} sx={{ padding: '16px 16px 0 16px', flex: 1, minHeight: 0, overflow: 'auto' }}>
        <Stack direction={'column'}>
          {getInputOutputAttributes()}
          {span.exception && (
            <Accordion contained title="Exception" size="medium" sx={{ marginLeft: '-20px', '&.Mui-expanded': { marginLeft: '-20px' } }}>
              <Typography variant={'body2'} component={'pre'} sx={{ fontFamily: 'monospace', marginLeft: '16px' }}>
                {span.exception}
              </Typography>
            </Accordion>
          )}
        </Stack>
      </TabPanel>
    </Box>
  );
};

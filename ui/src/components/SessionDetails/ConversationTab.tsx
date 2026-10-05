/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { useState } from 'react';
import { Box, IconButton, Stack, Typography, useTheme } from '@mui/material';
import KeyboardArrowRightIcon from '@mui/icons-material/KeyboardArrowRight';
import KeyboardArrowDownIcon from '@mui/icons-material/KeyboardArrowDown';
import { useParams } from 'react-router';
import { Spinner } from '@open-ui-kit/core';
import {
  AgentSubCallMessage,
  useAgentConversation
} from '@/api/kgInspectorApi';
import { getHierarchyColor } from '@/utils/graphUtils';
import { GLOBAL_BACKGROUND_COLOR } from '@/common/styles';

const SUB_CALL_LABELS: Record<AgentSubCallMessage['call_type'], string> = {
  llm: 'LLM call',
  tool: 'Tool call'
};

// 'llm' reuses the timeline's "call" row color (both represent the same
// capability-call concept); 'tool' gets its own distinct teal, matching
// the timeline's call-type legend.
const getSubCallColor = (
  callType: AgentSubCallMessage['call_type'],
  theme: ReturnType<typeof useTheme>
): string =>
  callType === 'tool' ? '#74FFC7' : getHierarchyColor('call', theme);

const formatTimestamp = (timestamp: number): string => {
  if (!timestamp) return '';
  const date = new Date(timestamp * 1000);
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleString();
};

export const ConversationTab = () => {
  const { sessionId } = useParams();
  const theme = useTheme();
  const { data, isLoading, error } = useAgentConversation(sessionId ?? '');
  // null = "not yet touched by the user" -- every agent turn starts collapsed
  // by default, without needing an effect keyed off when `data` first loads.
  const [collapsedIds, setCollapsedIds] = useState<Set<string> | null>(null);

  if (!sessionId) {
    return null;
  }

  if (isLoading) {
    return (
      <Stack
        alignItems="center"
        justifyContent="center"
        sx={{ width: '100%', height: '100%', minHeight: '200px' }}
      >
        <Spinner />
      </Stack>
    );
  }

  if (error) {
    return (
      <Box
        sx={{
          p: 2,
          borderRadius: 1,
          backgroundColor: theme.palette.error.dark,
          color: theme.palette.error.contrastText
        }}
      >
        <Typography variant="body1">Error: {error.message}</Typography>
      </Box>
    );
  }

  const messages = data?.messages ?? [];

  if (messages.length === 0) {
    return (
      <Box sx={{ p: 2 }}>
        <Typography variant="body2" sx={{ color: theme.palette.text.secondary }}>
          No agent messages found for this session.
        </Typography>
      </Box>
    );
  }

  const effectiveCollapsedIds =
    collapsedIds ?? new Set(messages.map((message) => message.transition_id));

  const toggleCollapsed = (transitionId: string) => {
    const next = new Set(effectiveCollapsedIds);
    if (next.has(transitionId)) {
      next.delete(transitionId);
    } else {
      next.add(transitionId);
    }
    setCollapsedIds(next);
  };

  return (
    <Box
      sx={{
        height: '100%',
        overflow: 'auto',
        backgroundColor: GLOBAL_BACKGROUND_COLOR,
        borderRadius: 1,
        p: 2
      }}
    >
      <Stack direction="column" gap={2}>
        {messages.map((message) => {
          const agentColor = getHierarchyColor('agent', theme);
          const isCollapsed = effectiveCollapsedIds.has(message.transition_id);
          const lastLlmCall = [...message.calls]
            .reverse()
            .find((call) => call.call_type === 'llm');

          const renderCall = (call: AgentSubCallMessage) => {
            const callColor = getSubCallColor(call.call_type, theme);
            return (
              <Box
                key={call.transition_id}
                sx={{
                  borderRadius: 1,
                  border: `1px solid ${theme.palette.divider}`,
                  borderLeft: `3px solid ${callColor}`,
                  p: 1,
                  backgroundColor: theme.palette.action.hover
                }}
              >
                <Stack
                  direction="row"
                  alignItems="baseline"
                  justifyContent="space-between"
                  sx={{ mb: 0.5 }}
                >
                  <Typography
                    variant="caption"
                    sx={{ color: callColor, fontWeight: 600 }}
                  >
                    {call.name || SUB_CALL_LABELS[call.call_type]}
                  </Typography>
                  <Typography
                    variant="caption"
                    sx={{ color: theme.palette.text.secondary }}
                  >
                    {call.duration.toFixed(0)}ms
                  </Typography>
                </Stack>

                {call.input && (
                  <Box sx={{ mb: 0.5 }}>
                    <Typography
                      variant="caption"
                      sx={{
                        color: theme.palette.text.secondary,
                        fontWeight: 600,
                        textTransform: 'uppercase'
                      }}
                    >
                      {call.call_type === 'llm' ? 'Prompt' : 'Input'}
                    </Typography>
                    <Typography
                      variant="body2"
                      sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}
                    >
                      {call.input}
                    </Typography>
                  </Box>
                )}

                {call.output && (
                  <Box>
                    <Typography
                      variant="caption"
                      sx={{
                        color: theme.palette.text.secondary,
                        fontWeight: 600,
                        textTransform: 'uppercase'
                      }}
                    >
                      {call.call_type === 'llm' ? 'Response' : 'Output'}
                    </Typography>
                    <Typography
                      variant="body2"
                      sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}
                    >
                      {call.output}
                    </Typography>
                  </Box>
                )}
              </Box>
            );
          };

          return (
            <Box
              key={message.transition_id}
              sx={{
                borderRadius: 1.5,
                border: `1px solid ${theme.palette.divider}`,
                borderLeft: `3px solid ${agentColor}`,
                p: 1.5,
                backgroundColor: theme.palette.background.paper
              }}
            >
              <Stack
                direction="row"
                alignItems="baseline"
                justifyContent="space-between"
                sx={{ mb: isCollapsed ? 0 : 1, cursor: 'pointer' }}
                onClick={() => toggleCollapsed(message.transition_id)}
              >
                <Stack direction="row" alignItems="center" gap={0.5}>
                  <IconButton
                    size="small"
                    sx={{ p: 0 }}
                    aria-label={isCollapsed ? 'Expand' : 'Collapse'}
                  >
                    {isCollapsed ? (
                      <KeyboardArrowRightIcon fontSize="small" />
                    ) : (
                      <KeyboardArrowDownIcon fontSize="small" />
                    )}
                  </IconButton>
                  <Typography
                    variant="subtitle2"
                    sx={{ color: agentColor, fontWeight: 600 }}
                  >
                    {message.agent_name || 'Agent'}
                  </Typography>
                  {message.calls.length > 0 && (
                    <Typography
                      variant="caption"
                      sx={{ color: theme.palette.text.secondary }}
                    >
                      ({message.calls.length} call
                      {message.calls.length > 1 ? 's' : ''})
                    </Typography>
                  )}
                </Stack>
                <Stack direction="row" gap={1.5}>
                  {message.timestamp ? (
                    <Typography
                      variant="caption"
                      sx={{ color: theme.palette.text.secondary }}
                    >
                      {formatTimestamp(message.timestamp)}
                    </Typography>
                  ) : null}
                  <Typography
                    variant="caption"
                    sx={{ color: theme.palette.text.secondary }}
                  >
                    {message.duration.toFixed(0)}ms
                  </Typography>
                </Stack>
              </Stack>

              {message.input && (
                <Box sx={{ mb: 1 }}>
                  <Typography
                    variant="caption"
                    sx={{
                      color: theme.palette.text.secondary,
                      fontWeight: 600,
                      textTransform: 'uppercase'
                    }}
                  >
                    Input
                  </Typography>
                  <Typography
                    variant="body2"
                    sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}
                  >
                    {message.input}
                  </Typography>
                </Box>
              )}

              {isCollapsed && lastLlmCall?.output && (
                <Box>
                  <Typography
                    variant="caption"
                    sx={{
                      color: theme.palette.text.secondary,
                      fontWeight: 600,
                      textTransform: 'uppercase'
                    }}
                  >
                    Response
                  </Typography>
                  <Typography
                    variant="body2"
                    sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}
                  >
                    {lastLlmCall.output}
                  </Typography>
                </Box>
              )}

              {!isCollapsed && (
                <>
                  {message.output && (
                    <Box sx={{ mb: message.calls.length > 0 ? 1 : 0 }}>
                      <Typography
                        variant="caption"
                        sx={{
                          color: theme.palette.text.secondary,
                          fontWeight: 600,
                          textTransform: 'uppercase'
                        }}
                      >
                        Output
                      </Typography>
                      <Typography
                        variant="body2"
                        sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}
                      >
                        {message.output}
                      </Typography>
                    </Box>
                  )}

                  {message.calls.length > 0 && (
                    <Stack direction="column" gap={1} sx={{ mt: 1, pl: 2 }}>
                      {message.calls.map((call) => renderCall(call))}
                    </Stack>
                  )}
                </>
              )}
            </Box>
          );
        })}
      </Stack>
    </Box>
  );
};

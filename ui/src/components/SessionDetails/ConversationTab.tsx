/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { Box, Stack, Typography, useTheme } from '@mui/material';
import { useParams } from 'react-router';
import { Spinner } from '@open-ui-kit/core';
import { useAgentConversation } from '@/api/kgInspectorApi';
import { getHierarchyColor } from '@/utils/graphUtils';
import { GLOBAL_BACKGROUND_COLOR } from '@/common/styles';

const formatTimestamp = (timestamp: number): string => {
  if (!timestamp) return '';
  const date = new Date(timestamp * 1000);
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleString();
};

export const ConversationTab = () => {
  const { sessionId } = useParams();
  const theme = useTheme();
  const { data, isLoading, error } = useAgentConversation(sessionId ?? '');

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
                sx={{ mb: 1 }}
              >
                <Typography
                  variant="subtitle2"
                  sx={{ color: agentColor, fontWeight: 600 }}
                >
                  {message.agent_name || 'Agent'}
                </Typography>
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

              {message.output && (
                <Box>
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
            </Box>
          );
        })}
      </Stack>
    </Box>
  );
};

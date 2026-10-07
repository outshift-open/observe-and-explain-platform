/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import {
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
  useTheme
} from '@mui/material';
import ChevronRightIcon from '@mui/icons-material/ChevronRight';
import { Tooltip } from '@open-ui-kit/core';
import { format } from 'date-fns';
import { useNavigate, useParams } from 'react-router-dom';
import { PATHS } from '@/routes/routes';
import { SessionWithL9Protocols } from '@/types/oxp.type';
import {
  NotAvailable,
  StatusTag,
  formatCount
} from '../L9Protocols/primitives';
import { shortProtocolName } from './utils';

const HEADERS = ['Session ID', 'Timestamp', 'L9 protocols', 'Tokens', ''];

// The sessions with an L9 protocol, each linking to its L9 Protocols tab.
export const SessionsTable = ({
  sessions
}: {
  sessions: SessionWithL9Protocols[];
}) => {
  const theme = useTheme();
  const navigate = useNavigate();
  const { applicationId } = useParams();

  if (sessions.length === 0) {
    return <NotAvailable text="No sessions with an L9 protocol" />;
  }

  const onSessionClick = (session: SessionWithL9Protocols) => {
    navigate(
      PATHS.applicationCollectSessionTab
        .replace(':applicationId', applicationId ?? '')
        .replace(':sessionId', encodeURIComponent(session.sessionId))
        .replace(':sessionTab', 'l9-protocols')
    );
  };

  return (
    <Table size="small">
      <TableHead>
        <TableRow>
          {HEADERS.map((header, index) => (
            <TableCell
              key={index}
              align={header === 'Tokens' ? 'right' : 'left'}
            >
              <Typography
                variant={'captionSemibold'}
                sx={{ color: theme.palette.vars.baseTextWeak }}
              >
                {header}
              </Typography>
            </TableCell>
          ))}
        </TableRow>
      </TableHead>
      <TableBody>
        {sessions.map((session) => (
          <TableRow
            key={session.sessionId}
            hover
            onClick={() => onSessionClick(session)}
            sx={{ cursor: 'pointer' }}
          >
            <TableCell sx={{ maxWidth: '280px' }}>
              <Tooltip title={session.sessionId} placement={'top'}>
                <Typography
                  variant={'body2'}
                  sx={{
                    textOverflow: 'ellipsis',
                    overflow: 'hidden',
                    whiteSpace: 'nowrap'
                  }}
                >
                  {session.sessionId}
                </Typography>
              </Tooltip>
            </TableCell>
            <TableCell>
              <Typography variant={'body2'}>
                {session.timestamp
                  ? format(
                      new Date(Number(session.timestamp) * 1000),
                      'MMM d, yyyy HH:mm:ss'
                    )
                  : ''}
              </Typography>
            </TableCell>
            <TableCell>
              <Stack direction="row" gap="6px" flexWrap="wrap">
                {(session.l9Protocols ?? [])
                  .filter((protocol) => protocol.enabled || protocol.activated)
                  .map((protocol) => (
                    <StatusTag
                      key={protocol.protocol}
                      label={`${shortProtocolName(protocol.protocol)}: ${
                        protocol.activated ? 'Activated' : 'Not activated'
                      }`}
                      tone={protocol.activated ? 'positive' : 'info'}
                    />
                  ))}
              </Stack>
            </TableCell>
            <TableCell align="right">
              <Typography variant={'body2'}>
                {formatCount(session.tokens)}
              </Typography>
            </TableCell>
            <TableCell align="right">
              <ChevronRightIcon
                sx={{
                  color: theme.palette.vars.baseTextWeak,
                  display: 'block'
                }}
              />
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
};

/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { SideDrawer, Stack, Typography, Button } from '@open-ui-kit/core';
import { useTheme } from '@mui/material';
import JsonView from '@uiw/react-json-view';
import { darkTheme } from '@uiw/react-json-view/dark';
import { useNavigate } from 'react-router-dom';

interface GenericGraphDrawerProps {
  open: boolean;
  onClose: () => void;
  title: string;
  data: any;
}

export const GenericGraphDrawer = ({
  open,
  onClose,
  title,
  data
}: GenericGraphDrawerProps) => {
  const theme = useTheme();
  const navigate = useNavigate();

  const handleSessionClick = (session: string) => {
    navigate(
      `/g6-kg-inspector?tab=executionTree&session=${encodeURIComponent(session)}`
    );
    onClose();
  };

  return (
    <SideDrawer
      open={open}
      onClose={onClose}
      titleNode={
        <Typography variant="h6" sx={{ color: theme.palette.text.primary }}>
          {title}
        </Typography>
      }
      copyURL={''}
      hideTitleAction={true}
      hidePrev={true}
      hideNext={true}
      hideActionButtons={true}
      hideFooter={true}
      paperProps={{
        '&.MuiPaper-root': {
          width: '600px',
          minWidth: '600px',
          overflowX: 'hidden',
          overflowY: 'auto'
        },

        '&.MuiPaper-root > .MuiBox-root': {
          width: '600px',
          padding: '16px 8px 24px 16px'
        },
        '&.MuiPaper-root > .MuiBox-root:nth-child(2)': {
          height: '100%',
          padding: '0 16px',
          overflowX: 'hidden',
          overflowY: 'auto'
        }
      }}
    >
      <Stack
        direction="column"
        gap="8px"
        sx={{ height: '100%', width: '100%' }}
      >
        {data?.data?.sessions ? (
          <Stack direction="column" gap="4px">
            <Typography variant="h6">Occured in sessions:</Typography>
            {data?.data?.sessions.map((session: string) => {
              return (
                <Button
                  key={session}
                  onClick={() => handleSessionClick(session)}
                >
                  {session}
                </Button>
              );
            })}
          </Stack>
        ) : null}

        <JsonView
          value={data}
          collapsed={false}
          displayDataTypes={false}
          displayObjectSize={true}
          enableClipboard={true}
          shortenTextAfterLength={0}
          style={
            theme.palette.mode === 'dark'
              ? ({
                  ...darkTheme,
                  '--w-rjv-background-color': 'transparent',
                  fontSize: '14px',
                  fontFamily: 'monospace',
                  width: '100%'
                } as React.CSSProperties)
              : {
                  fontSize: '14px',
                  fontFamily: 'monospace',
                  width: '100%'
                }
          }
        />
      </Stack>
    </SideDrawer>
  );
};

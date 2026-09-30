/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import {
  AppBar,
  Box,
  IconButton,
  Toolbar,
  Typography,
  useTheme
} from '@mui/material';

const TopBar = () => {
  const theme = useTheme();

  return (
    <AppBar
      position="static"
      elevation={0}
      sx={{
        backgroundColor: theme.palette.vars.baseBackgroundStrong
      }}
    >
      <Toolbar
        variant="dense"
        sx={{
          '&.MuiToolbar-root': {
            minHeight: '32px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '8px 36px'
          }
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'flex-end', gap: '4px' }}>
          <Typography
            variant="h6"
            component="div"
            sx={{
              fontWeight: 700,
              letterSpacing: '0.3px',
              color: theme.palette.vars.baseTextStrong
            }}
          >
            OXP
          </Typography>
        </Box>
      </Toolbar>
    </AppBar>
  );
};

export default TopBar;
export { TopBar };

/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { Stack, Typography, useTheme } from '@mui/material';

interface TabLabelProps {
  label: string;
  count?: number;
}

export const TabLabel = ({ label, count }: TabLabelProps) => {
  const theme = useTheme();

  return (
    <Stack direction="row" alignItems="center" justifyContent="center" spacing={1}>
      <Typography variant="subtitle1" color={theme.palette.vars.neutralTextDefault}>
        {label}
      </Typography>
      <Typography variant="subtitle2" color={theme.palette.vars.neutralTextDefault}>
        {count}
      </Typography>
    </Stack>
  );
};

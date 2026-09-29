/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { WastefulSession } from '@/types/oxp.type';
import { Box, Stack, Typography } from '@mui/material';
import { colorTokens } from '@/theme/colors';
import { GeneralSize, Tag } from '@open-ui-kit/core';
import { CustomTooltip } from '@/components/CustomTooltip';
import { formatTwoDecimals } from '@/utils';
import { GLOBAL_BACKGROUND_COLOR } from '@/common/styles';

interface InefficientSessionCardProps {
  session: WastefulSession;
  isSelected?: boolean;
  onSessionClick?: (session: WastefulSession) => void;
}

export const InefficientSessionCard = ({
  session,
  isSelected = false,
  onSessionClick
}: InefficientSessionCardProps) => {
  return (
    <Stack
      onClick={() => onSessionClick?.(session)}
      direction="column"
      gap={'8px'}
      sx={{
        border: `1px solid ${isSelected ? colorTokens.activeBorder : colorTokens.defaultBorder}`,
        backgroundColor: isSelected
          ? colorTokens.activeBackground
          : colorTokens.inactiveBackground,
        borderRadius: '16px',
        padding: '16px',
        width: '300px',
        cursor: 'pointer',
        userSelect: 'none'
      }}
    >
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <CustomTooltip
          title={session.sessionId}
          placement="top"
          enterDelay={1500}
        >
          <Typography
            variant="h6"
            sx={{
              color: colorTokens.disabledBlue1Text,
              overflow: 'hidden',
              whiteSpace: 'nowrap',
              textOverflow: 'ellipsis',
              maxWidth: '196px',
              minWidth: 0,
              display: 'block'
            }}
          >
            {session.sessionId}
          </Typography>
        </CustomTooltip>
        <Typography variant="body1" sx={{ color: colorTokens.errorText }}>
          {formatTwoDecimals(session.estimatedWaste)}$
        </Typography>
      </Stack>

      <CustomTooltip
        title={session.semanticGroup}
        placement="top"
        enterDelay={1500}
      >
        <Box>
          <Tag
            sx={{
              backgroundColor: GLOBAL_BACKGROUND_COLOR,
              border: `1px solid ${colorTokens.inactiveBorder}`
            }}
            size={GeneralSize.Medium}
          >
            {session.semanticGroup}
          </Tag>
        </Box>
      </CustomTooltip>
    </Stack>
  );
};

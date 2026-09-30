/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { SxProps, Typography, useTheme } from '@mui/material';
import { Card, CardContent, Stack, Tooltip } from '@open-ui-kit/core';
import InfoOutlineIcon from '@mui/icons-material/InfoOutline';
import { CustomTooltip } from '../CustomTooltip';

interface WidgetCardProps {
  title?: string;
  content: React.ReactNode;
  caption?: string;
  cardSx?: SxProps;
  description?: React.ReactNode;
  disabled?: boolean;
  onClick?: () => void;
  tooltip?: React.ReactNode;
  contentSx?: SxProps;
}

export const WidgetCard = ({
  title,
  content,
  cardSx,
  description,
  disabled,
  onClick,
  tooltip,
  contentSx
}: WidgetCardProps) => {
  const card = (
    <Card
      aria-disabled={disabled ? true : undefined}
      connector
      sx={{
        height: 'fit-content',
        width: '300px',
        padding: 0,
        border: 'none',
        outline: 'none',
        alignItems: 'flex-start',
        //  backgroundColor: theme.palette.vars.baseBackgroundStrong,
        '& .MuiCardContent-root': {
          padding: '8px 12px 6px 12px !important'
        },
        ...(disabled ? { opacity: 0.5 } : {}),
        ...cardSx
      }}
      onClick={onClick}
    >
      <CardContent sx={{ width: '100%' }}>
        <Stack direction={'row'} alignItems={'center'} gap={'4px'}>
          {title && <Typography variant="captionSemibold">{title}</Typography>}

          {description && (
            <CustomTooltip
              title={
                typeof description === 'string' ? (
                  <Typography
                    variant={'caption'}
                    sx={{ whiteSpace: 'pre-line' }}
                  >
                    {description}
                  </Typography>
                ) : (
                  description
                )
              }
              placement={'top'}
              sx={{ maxWidth: '550px' }}
            >
              <InfoOutlineIcon
                sx={{
                  width: '14px',
                  height: '14px',
                  cursor: disabled ? 'cursor' : 'pointer',
                  ...(disabled ? { color: 'text.disabled' } : {})
                }}
              />
            </CustomTooltip>
          )}
        </Stack>
        <Stack
          direction={'column'}
          sx={{ alignItems: 'flex-start', ...contentSx }}
        >
          {content}
        </Stack>
      </CardContent>
    </Card>
  );

  if (tooltip) {
    return (
      <Tooltip title={tooltip} placement="top">
        {card}
      </Tooltip>
    );
  }

  return card;
};

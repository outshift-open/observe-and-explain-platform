/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { Box, Stack, Typography, useTheme } from '@mui/material';
import {
  Button,
  GeneralSize,
  Tag,
  TagBackgroundColorVariants
} from '@open-ui-kit/core';
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline';
import ThumbUpAltOutlinedIcon from '@mui/icons-material/ThumbUpAltOutlined';
import RemoveCircleOutlineIcon from '@mui/icons-material/RemoveCircleOutline';
import WarningAmberIcon from '@mui/icons-material/WarningAmber';
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutline';
import { GradientScoreSlider } from '@/components';

export interface HealthScoreProps {
  score: number;
  onLearnMore?: () => void;
}

const getScoreLabel = (score: number): string => {
  if (score >= 80) return 'Excellent';
  if (score >= 60) return 'Good';
  if (score >= 40) return 'Ok';
  if (score >= 20) return 'Poor';
  return 'Critical';
};

const getScoreRecommendation = (score: number): string => {
  if (score >= 80)
    return 'Your application is running smoothly. Keep up the good work!';
  if (score >= 60)
    return 'Your application is performing well. Minor optimizations could help.';
  if (score >= 40)
    return 'To reach 100%, reduce corrective loops and optimize workflows.';
  if (score >= 20)
    return 'Performance issues detected. Review agent configurations.';
  return 'Critical issues found. Immediate attention required.';
};

export const HealthScore = ({ score, onLearnMore }: HealthScoreProps) => {
  const theme = useTheme();
  const scoreLabel = getScoreLabel(score);
  const recommendation = getScoreRecommendation(score);

  const getScoreIcon = () => {
    const iconSize = { width: '16px', height: '16px' };
    if (score >= 80)
      return (
        <CheckCircleOutlineIcon
          sx={{ ...iconSize, fill: theme.palette.vars.successIconDefault }}
        />
      );
    if (score >= 60)
      return (
        <ThumbUpAltOutlinedIcon
          sx={{ ...iconSize, fill: theme.palette.vars.infoIconDefault }}
        />
      );
    if (score >= 40)
      return (
        <RemoveCircleOutlineIcon
          sx={{ ...iconSize, fill: theme.palette.vars.warningIconDefault }}
        />
      );
    if (score >= 20)
      return (
        <WarningAmberIcon
          sx={{
            ...iconSize,
            fill: theme.palette.vars.severeWarningIconDefault
          }}
        />
      );
    return (
      <ErrorOutlineIcon
        sx={{ ...iconSize, fill: theme.palette.vars.negativeIconDefault }}
      />
    );
  };

  return (
    <Stack direction="column" gap="16px" sx={{ width: '500px' }}>
      <Stack
        direction="row"
        alignItems="center"
        justifyContent="space-between"
        gap="24px"
      >
        <Typography variant="h3" fontWeight={400}>
          {score}%
        </Typography>

        {recommendation && (
          <Tag
            color={TagBackgroundColorVariants.Primary}
            size={GeneralSize.Medium}
            icon={getScoreIcon()}
          >
            {recommendation}
          </Tag>
        )}
      </Stack>

      <Stack direction="row" gap="8px" alignItems="center">
        <Typography
          variant="captionMedium"
          sx={{ flexShrink: 0, color: theme.palette.vars.baseTextMedium }}
        >
          HEALTH SCORE
        </Typography>
        <Box sx={{ position: 'relative', flex: 1, minWidth: 0 }}>
          <GradientScoreSlider
            value={score}
            min={0}
            max={100}
            height={8}
            gradient="linear-gradient(270deg, #0A60FF 0%, #02C8FF 25%, #02C8FF 50%, #FF9000 75%, #FF007F 100%)"
          />
          <Typography
            variant="caption"
            sx={{
              position: 'absolute',
              top: '-20px',
              left: `${score}%`,
              transform: 'translateX(-50%)',
              color: theme.palette.vars.baseTextMedium
            }}
          >
            {scoreLabel}
          </Typography>
        </Box>
      </Stack>

      {onLearnMore && (
        <Stack direction="row" justifyContent="flex-end">
          <Button variant="gradient" size="small" onClick={onLearnMore}>
            Learn More
          </Button>
        </Stack>
      )}
    </Stack>
  );
};

export default HealthScore;

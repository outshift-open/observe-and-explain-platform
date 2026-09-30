/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import { styled } from '@mui/material/styles';
import Tooltip, { tooltipClasses, TooltipProps } from '@mui/material/Tooltip';

const StyledTooltip = styled((customTooltipProps: TooltipProps) => (
  <Tooltip {...customTooltipProps} classes={{ popper: customTooltipProps.className }}>
    {customTooltipProps.children}
  </Tooltip>
))({
  [`& .${tooltipClasses.tooltip}`]: {
    maxWidth: 'none'
  }
});

export const CustomTooltip = ({ ...props }: TooltipProps) => {
  return <StyledTooltip {...props}>{props.children}</StyledTooltip>;
};

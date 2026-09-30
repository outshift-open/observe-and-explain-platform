/*
 * Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
 * SPDX-License-Identifier: Apache-2.0
 */

import ListAltRoundedIcon from '@mui/icons-material/ListAltRounded';
import CompareArrowsIcon from '@mui/icons-material/CompareArrows';
import SmartToyOutlinedIcon from '@mui/icons-material/SmartToyOutlined';
import EastRoundedIcon from '@mui/icons-material/EastRounded';
import ChatBubbleOutlineIcon from '@mui/icons-material/ChatBubbleOutline';
import { Transport } from '@/assets/icons';
import { TraceType } from '@/types/trace-types.ts';

export const getIconFromTraceType = (traceType?: TraceType) => {
  switch (traceType) {
    case 'task':
      return ListAltRoundedIcon;
    case 'agp':
      return CompareArrowsIcon;
    case 'agent':
      return SmartToyOutlinedIcon;
    case 'connection':
      return EastRoundedIcon;
    case 'chat':
      return ChatBubbleOutlineIcon;
    case 'tool':
      return EastRoundedIcon;
    case 'transport':
      return Transport;
    case 'slim':
      return Transport;
    case 'start_end':
      return undefined;
    default:
      return SmartToyOutlinedIcon;
  }
};

export const getBackgroundColorFromTraceType = (traceType?: TraceType) => {
  switch (traceType) {
    case 'task':
      // TODO create a spark light theme variable
      return '#DFF1F5';
    case 'agp':
      return '#FAECFF';
    case 'agent':
      return '#E8F1FF';
    case 'connection':
      return '#E4FAFF';
    case 'chat':
      return '#E4FAFF';
    case 'tool':
      return '#E4FAFF';
    case 'workflow':
      return '#E8F1FF';
    case 'transport':
      return '#E4FAFF';
    default:
      return '#E8F1FF';
  }
};

export const getColorFromTraceType = (traceType?: TraceType) => {
  switch (traceType) {
    case 'task':
      // TODO create a spark light theme variable
      return '#3D91BE';
    case 'agp':
      return '#FAECFF';
    case 'agent':
      return '#187ADC';
    case 'connection':
      return '#0AB6FF';
    case 'chat':
      return '#0AB6FF';
    case 'tool':
      return '#0AB6FF';
    case 'workflow':
      return '#187ADC';
    case 'transport':
      return '#0AB6FF';
    default:
      return '#187ADC';
  }
};
